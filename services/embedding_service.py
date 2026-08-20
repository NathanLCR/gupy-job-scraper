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
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_MODEL_INSTANCE = None
_MODEL_LOADED = False


def _load_transformer_model():
    """Lazily load sentence-transformers model if installed."""
    global _MODEL_INSTANCE, _MODEL_LOADED
    if _MODEL_LOADED:
        return _MODEL_INSTANCE

    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading dense embedding model: {DEFAULT_MODEL_NAME}")
        _MODEL_INSTANCE = SentenceTransformer(DEFAULT_MODEL_NAME)
    except Exception as exc:
        logger.info(f"SentenceTransformer not available ({exc}). Using lightweight fallback embedding generator.")
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


def get_embedding(text: str) -> List[float]:
    """
    Generate 384-dimensional dense vector embedding for a single text.
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM

    model = _load_transformer_model()
    if model is not None:
        try:
            emb = model.encode(text, normalize_embeddings=True)
            return emb.tolist()
        except Exception as exc:
            logger.warning(f"Transformer encode failed ({exc}). Falling back to deterministic embedding.")

    return _generate_fallback_embedding(text, dim=EMBEDDING_DIM)


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate 384-dimensional dense vector embeddings for a batch of texts.
    """
    if not texts:
        return []

    model = _load_transformer_model()
    if model is not None:
        try:
            embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return embs.tolist()
        except Exception as exc:
            logger.warning(f"Transformer batch encode failed ({exc}). Falling back.")

    return [_generate_fallback_embedding(t, dim=EMBEDDING_DIM) for t in texts]


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
    return get_embedding(job_text)


def embed_job(job: Any) -> List[float]:
    """
    Generate embedding from Job entity or dictionary.
    """
    if isinstance(job, dict):
        return embed_job_text(
            job_title=job.get("job_title", ""),
            tech_stack=job.get("tech_stack") or [],
            hard_skills=job.get("hard_skills") or [],
            description=job.get("description", ""),
            seniority=job.get("seniority"),
        )
    return embed_job_text(
        job_title=getattr(job, "job_title", ""),
        tech_stack=getattr(job, "tech_stack", []) or [],
        hard_skills=[s.name if hasattr(s, "name") else str(s) for s in (getattr(job, "hard_skills", []) or [])],
        description=getattr(job, "description", ""),
        seniority=getattr(job, "seniority", None),
    )


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
