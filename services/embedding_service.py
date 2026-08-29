"""
SkillPulse AI Dense Embedding Service (384-dimensional).
Generates dense vector representations for job descriptions and candidate resumes.
Uses sentence-transformers (e.g. all-MiniLM-L6-v2) when available, with a fast,
deterministic lightweight pseudo-semantic fallback for testing and offline environments.
"""

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import requests

from config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = settings.EMBEDDING_MODEL

_MODEL_INSTANCE = None
_MODEL_LOADED = False


class EmbeddingUnavailableError(RuntimeError):
    """The configured embedding provider did not produce a usable vector."""


@dataclass(frozen=True)
class EmbeddingResult:
    vector: List[float]
    model: str


def _call_cloudflare_workers_ai(texts: Union[str, List[str]]) -> Optional[List[List[float]]]:
    """
    Invoke Cloudflare Workers AI embedding endpoint (@cf/baai/bge-small-en-v1.5, 384 dimensions).
    Endpoint: https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
    """
    account_id = settings.CF_ACCOUNT_ID
    api_token = settings.CF_API_TOKEN
    if not account_id or not api_token:
        return None

    model = settings.CF_EMBEDDING_MODEL or "@cf/baai/bge-small-en-v1.5"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"

    payload = {"text": texts if isinstance(texts, list) else [texts]}
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        result = data.get("result")
        if isinstance(result, dict) and "data" in result:
            vectors = result["data"]
            if isinstance(vectors, list) and len(vectors) > 0:
                # Ensure each vector is normalized and exactly 384 dimensions
                out = []
                for v in vectors:
                    if isinstance(v, list):
                        norm = _normalize_vector(np.array(v, dtype=np.float32)).tolist()
                        out.append(norm)
                return out if out else None
        elif isinstance(result, list):
            out = []
            for v in result:
                if isinstance(v, list):
                    norm = _normalize_vector(np.array(v, dtype=np.float32)).tolist()
                    out.append(norm)
            return out if out else None
    except Exception:
        logger.warning(
            "embedding_provider_unavailable",
            extra={"event": "embedding_provider_unavailable", "provider": "cloudflare"},
        )
        return None

    return None


def _load_transformer_model():
    """Lazily load sentence-transformers model if installed."""
    global _MODEL_INSTANCE, _MODEL_LOADED
    if _MODEL_LOADED:
        return _MODEL_INSTANCE

    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading dense embedding model: {DEFAULT_MODEL_NAME}")
        _MODEL_INSTANCE = SentenceTransformer(DEFAULT_MODEL_NAME)
    except Exception:
        logger.info(
            "embedding_provider_unavailable",
            extra={"event": "embedding_provider_unavailable", "provider": "sentence_transformers"},
        )
        _MODEL_INSTANCE = None

    _MODEL_LOADED = True
    return _MODEL_INSTANCE


def _normalize_vector(vec: np.ndarray) -> np.ndarray:
    """Normalize vector to unit length (L2 norm)."""
    norm = np.linalg.norm(vec)
    if norm > 1e-12:
        return vec / norm
    return vec


def _generate_fallback_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Deterministic pseudo-semantic dense embedding generator (384-d) for test & offline modes.
    Hashes n-grams and vocabulary tokens to pseudorandom unit basis vectors with TF-IDF weighting,
    guaranteeing that semantically related texts (sharing skills/keywords) have high cosine similarity.
    """
    cleaned = (text or "").lower().strip()
    if not cleaned:
        return [0.0] * dim

    # Tokenize words and character 3-grams
    words = re.findall(r"[a-zA-Z0-9_#+.-]+", cleaned)
    if not words:
        return [0.0] * dim

    vec = np.zeros(dim, dtype=np.float32)

    # Word frequencies
    word_counts: Dict[str, int] = {}
    for w in words:
        word_counts[w] = word_counts.get(w, 0) + 1

    total_words = len(words)
    for word, count in word_counts.items():
        tf = 1.0 + math.log(count)
        # Deterministic seed for each token
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        rng = np.random.RandomState(h % (2**32 - 1))
        # Dense random projection
        word_vec = rng.randn(dim).astype(np.float32)
        word_vec = _normalize_vector(word_vec)
        vec += word_vec * tf

    # Add character n-grams for typo & morphology robustness
    if len(cleaned) >= 3:
        for i in range(len(cleaned) - 2):
            trigram = cleaned[i : i + 3]
            h = int(hashlib.md5(trigram.encode("utf-8")).hexdigest(), 16)
            rng = np.random.RandomState(h % (2**32 - 1))
            tri_vec = rng.randn(dim).astype(np.float32) * 0.2
            vec += tri_vec

    norm_vec = _normalize_vector(vec)
    return norm_vec.tolist()


def embed_query_checked(text: str) -> EmbeddingResult:
    """Embed with one configured provider and report the model that produced it."""
    if not text or not text.strip():
        return EmbeddingResult([0.0] * EMBEDDING_DIM, settings.ACTIVE_EMBEDDING_MODEL)

    provider = settings.EMBEDDING_PROVIDER
    if provider == "cloudflare":
        cf_res = _call_cloudflare_workers_ai(text)
        if cf_res and len(cf_res) == 1 and len(cf_res[0]) == EMBEDDING_DIM:
            return EmbeddingResult(cf_res[0], settings.CF_EMBEDDING_MODEL)

    elif provider == "sentence_transformers":
        model = _load_transformer_model()
        if model is not None:
            try:
                emb = model.encode(text, normalize_embeddings=True)
                vector = emb.tolist()
                if len(vector) == EMBEDDING_DIM:
                    return EmbeddingResult(vector, settings.EMBEDDING_MODEL)
            except Exception:
                logger.warning(
                    "embedding_provider_unavailable",
                    extra={"event": "embedding_provider_unavailable", "provider": provider},
                )
    elif provider != "hash_dev_only":
        raise EmbeddingUnavailableError("Embedding provider is not supported")

    if settings.ENVIRONMENT.lower() == "production":
        raise EmbeddingUnavailableError("Embedding provider is unavailable")
    return EmbeddingResult(
        _generate_fallback_embedding(text, dim=EMBEDDING_DIM), "hash-dev-v1"
    )


def get_embedding(text: str) -> List[float]:
    """Compatibility wrapper returning only the checked vector."""
    return embed_query_checked(text).vector


def embed_batch_checked(texts: List[str]) -> List[EmbeddingResult]:
    if not texts:
        return []

    provider = settings.EMBEDDING_PROVIDER
    if provider == "cloudflare":
        cf_res = _call_cloudflare_workers_ai(texts)
        if (
            cf_res
            and len(cf_res) == len(texts)
            and all(len(vector) == EMBEDDING_DIM for vector in cf_res)
        ):
            return [
                EmbeddingResult(vector, settings.CF_EMBEDDING_MODEL)
                for vector in cf_res
            ]

    elif provider == "sentence_transformers":
        model = _load_transformer_model()
        if model is not None:
            try:
                vectors = model.encode(
                    texts, normalize_embeddings=True, show_progress_bar=False
                ).tolist()
                if len(vectors) == len(texts) and all(
                    len(vector) == EMBEDDING_DIM for vector in vectors
                ):
                    return [
                        EmbeddingResult(vector, settings.EMBEDDING_MODEL)
                        for vector in vectors
                    ]
            except Exception:
                logger.warning(
                    "embedding_provider_unavailable",
                    extra={"event": "embedding_provider_unavailable", "provider": provider},
                )
    elif provider != "hash_dev_only":
        raise EmbeddingUnavailableError("Embedding provider is not supported")

    if settings.ENVIRONMENT.lower() == "production":
        raise EmbeddingUnavailableError("Embedding provider is unavailable")
    return [
        EmbeddingResult(_generate_fallback_embedding(text, EMBEDDING_DIM), "hash-dev-v1")
        for text in texts
    ]


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Compatibility wrapper returning vectors from checked batch results."""
    return [result.vector for result in embed_batch_checked(texts)]


def _format_job_text(
    job_title: str,
    tech_stack: Optional[List[str]] = None,
    hard_skills: Optional[List[str]] = None,
    description: Optional[str] = None,
    seniority: Optional[str] = None,
) -> str:
    """Format canonical job text representation for embedding."""
    parts = []
    if job_title:
        parts.append(f"Title: {job_title}")
    if seniority:
        parts.append(f"Seniority: {seniority}")
    if tech_stack:
        parts.append(f"Tech Stack: {', '.join(tech_stack)}")
    if hard_skills:
        parts.append(f"Required Skills: {', '.join(hard_skills)}")
    if description:
        parts.append(f"Description: {description[:1000]}")
    return " | ".join(parts)


def _format_resume_text(
    resume_text: str,
    extracted_skills: Optional[Dict[str, Any]] = None,
) -> str:
    """Format candidate resume document representation for embedding."""
    parts = []
    if resume_text:
        parts.append(resume_text[:2000])

    if extracted_skills:
        hard = extracted_skills.get("hard_skills") or []
        tech = extracted_skills.get("tech_stack") or []
        soft = extracted_skills.get("soft_skills") or []
        if hard:
            parts.append(f"Skills: {', '.join(hard)}")
        if tech:
            parts.append(f"Technologies: {', '.join(tech)}")
        if soft:
            parts.append(f"Competencies: {', '.join(soft)}")

    return "\n".join(parts)


def embed_job_text(
    job_title: str,
    tech_stack: Optional[List[str]] = None,
    hard_skills: Optional[List[str]] = None,
    description: Optional[str] = None,
    seniority: Optional[str] = None,
) -> List[float]:
    """
    Construct canonical job document representation and generate dense vector embedding.
    """
    job_text = _format_job_text(
        job_title=job_title,
        tech_stack=tech_stack,
        hard_skills=hard_skills,
        description=description,
        seniority=seniority,
    )
    return embed_query_checked(job_text).vector


def embed_job_text_checked(
    job_title: str,
    tech_stack: Optional[List[str]] = None,
    hard_skills: Optional[List[str]] = None,
    description: Optional[str] = None,
    seniority: Optional[str] = None,
) -> EmbeddingResult:
    job_text = _format_job_text(
        job_title=job_title,
        tech_stack=tech_stack,
        hard_skills=hard_skills,
        description=description,
        seniority=seniority,
    )
    return embed_query_checked(job_text)


_JOB_EMBEDDING_CACHE: Dict[Any, List[float]] = {}


def embed_job(job: Any) -> List[float]:
    """
    Generate embedding from Job entity or dictionary with in-memory caching.
    """
    job_id = None
    if isinstance(job, dict):
        job_id = job.get("id") or job.get("job_id")
    elif hasattr(job, "id"):
        job_id = getattr(job, "id", None)

    if job_id is not None and job_id in _JOB_EMBEDDING_CACHE:
        return _JOB_EMBEDDING_CACHE[job_id]

    if isinstance(job, dict):
        emb = embed_job_text(
            job_title=job.get("job_title", ""),
            tech_stack=job.get("tech_stack") or [],
            hard_skills=job.get("hard_skills") or [],
            description=job.get("description", ""),
            seniority=job.get("seniority"),
        )
    else:
        emb = embed_job_text(
            job_title=getattr(job, "job_title", ""),
            tech_stack=getattr(job, "tech_stack", []) or [],
            hard_skills=[s.name if hasattr(s, "name") else str(s) for s in (getattr(job, "hard_skills", []) or [])],
            description=getattr(job, "description", ""),
            seniority=getattr(job, "seniority", None),
        )

    if job_id is not None:
        _JOB_EMBEDDING_CACHE[job_id] = emb

    return emb


def embed_jobs_batch(jobs: List[Any]) -> List[List[float]]:
    """
    Generate dense vector embeddings for a batch of jobs (entities or dicts).
    """
    if not jobs:
        return []

    texts = []
    for job in jobs:
        if isinstance(job, dict):
            text = _format_job_text(
                job_title=job.get("job_title", ""),
                tech_stack=job.get("tech_stack") or [],
                hard_skills=job.get("hard_skills") or [],
                description=job.get("description", ""),
                seniority=job.get("seniority"),
            )
        else:
            text = _format_job_text(
                job_title=getattr(job, "job_title", ""),
                tech_stack=getattr(job, "tech_stack", []) or [],
                hard_skills=[s.name if hasattr(s, "name") else str(s) for s in (getattr(job, "hard_skills", []) or [])],
                description=getattr(job, "description", ""),
                seniority=getattr(job, "seniority", None),
            )
        texts.append(text)

    return get_embeddings_batch(texts)


def embed_resume_text(
    resume_text: str,
    extracted_skills: Optional[Dict[str, Any]] = None,
) -> List[float]:
    """
    Construct candidate resume document representation and generate dense vector embedding.
    """
    doc_text = _format_resume_text(resume_text=resume_text, extracted_skills=extracted_skills)
    return get_embedding(doc_text)


def embed_candidate(candidate: Any) -> List[float]:
    """
    Generate dense vector embedding for candidate profile entity or extracted skills dict.
    """
    if isinstance(candidate, dict):
        raw_text = candidate.get("raw_resume_text") or candidate.get("description") or ""
        return embed_resume_text(raw_text, extracted_skills=candidate)
    raw_text = getattr(candidate, "raw_resume_text", "") or ""
    skills = getattr(candidate, "parsed_skills", {}) or {}
    return embed_resume_text(raw_text, extracted_skills=skills)


def embed_resumes_batch(
    resumes: List[Union[str, Dict[str, Any], Tuple[str, Optional[Dict[str, Any]]]]]
) -> List[List[float]]:
    """
    Generate dense vector embeddings for a batch of candidate resumes.
    Accepts list of raw resume strings, tuples of (text, extracted_skills), or dicts with keys 'resume_text' / 'extracted_skills'.
    """
    if not resumes:
        return []

    texts = []
    for item in resumes:
        if isinstance(item, str):
            texts.append(_format_resume_text(item))
        elif isinstance(item, tuple) and len(item) >= 2:
            texts.append(_format_resume_text(item[0], item[1]))
        elif isinstance(item, dict):
            texts.append(_format_resume_text(item.get("resume_text", ""), item.get("extracted_skills")))
        else:
            texts.append(_format_resume_text(str(item)))

    return get_embeddings_batch(texts)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Compute cosine similarity between two dense vectors (-1.0 to 1.0, clamped to 0.0 to 1.0).
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0

    dot = float(np.dot(a, b) / (norm_a * norm_b))
    # Clamp cosine similarity to [0.0, 1.0] for matching fit calculation
    return max(0.0, min(1.0, dot))


def batch_cosine_similarity(query_vec: List[float], candidate_vecs: List[List[float]]) -> List[float]:
    """
    Compute cosine similarities of a query vector against multiple candidate vectors.
    """
    if not query_vec or not candidate_vecs:
        return []

    q = np.array(query_vec, dtype=np.float32)
    norm_q = np.linalg.norm(q)
    if norm_q < 1e-12:
        return [0.0] * len(candidate_vecs)

    q_unit = q / norm_q
    matrix = np.array(candidate_vecs, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    matrix_unit = matrix / norms

    dots = np.dot(matrix_unit, q_unit)
    clipped = np.clip(dots, 0.0, 1.0)
    return clipped.tolist()
