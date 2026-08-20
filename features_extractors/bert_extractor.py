"""
Tier 2 Contextual NER with JobBERT / Token Classification.
Extracts emerging technical skills, contextual terminology, and domain attributes (~30ms).
Includes graceful fallback heuristics when heavy PyTorch/Transformers runtimes are offline.
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_JOBBERT_MODEL = "TechWolf/JobBERT-v3"
OUTPUT_CSV = "extracted_jobs_bert.csv"


class JobBERTExtractor:
    """
    Token classification NER extractor for contextual job skill identification.
    Uses TechWolf/JobBERT-v3 pipeline when available, with intelligent fallback.
    """

    def __init__(self, model_name: str = DEFAULT_JOBBERT_MODEL):
        self.model_name = model_name
        self._pipeline = None
        self._initialized = False

    def _init_pipeline(self) -> bool:
        if self._initialized:
            return self._pipeline is not None

        self._initialized = True
        try:
            from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, do_lower_case=False)
            model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            self._pipeline = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")
            logger.info(f"Loaded JobBERT pipeline successfully ({self.model_name})")
            return True
        except Exception as exc:
            logger.debug(f"JobBERT transformers pipeline not available, using heuristic fallback: {exc}")
            self._pipeline = None
            return False

    def extract(self, text: str, confidence_threshold: float = 0.5) -> Dict[str, Any]:
        """
        Extract entities from job posting text.
        """
        if not text or not text.strip():
            return {
                "hard_skills": [],
                "soft_skills": [],
                "emerging_skills": [],
                "salary": None,
                "confidence_score": 0.0,
            }

        cleaned_text = text.strip()[:2000]

        if self._init_pipeline() and self._pipeline is not None:
            return self._extract_with_model(cleaned_text, confidence_threshold)

        return self._extract_fallback(cleaned_text)

    def _extract_with_model(self, text: str, confidence_threshold: float) -> Dict[str, Any]:
        entities = self._pipeline(text)
        hard_skills: List[str] = []
        soft_skills: List[str] = []
        salary = None
        conf_scores: List[float] = []

        for ent in entities:
            score = float(ent.get("score", 1.0))
            if score < confidence_threshold:
                continue

            label = str(ent.get("entity_group", "")).upper()
            word = str(ent.get("word", "")).strip()

            if not word or len(word) < 2:
                continue

            conf_scores.append(score)

            if "SOFT" in label or "COMPETENCE" in label:
                soft_skills.append(word)
            elif "SALARY" in label or "MONEY" in label:
                salary = word
            elif "SKILL" in label or "TECH" in label or "TOOL" in label:
                hard_skills.append(word)

        avg_conf = sum(conf_scores) / len(conf_scores) if conf_scores else 0.5

        # Deduplicate while preserving order
        dedup_hard = list(dict.fromkeys(hard_skills))
        dedup_soft = list(dict.fromkeys(soft_skills))

        return {
            "hard_skills": dedup_hard,
            "soft_skills": dedup_soft,
            "emerging_skills": [s for s in dedup_hard if len(s.split()) >= 2],
            "salary": salary,
            "confidence_score": round(avg_conf, 2),
        }

    def _extract_fallback(self, text: str) -> Dict[str, Any]:
        """
        Contextual heuristic extractor identifying skill patterns, libraries, and tools
        following action phrases ('experiência com', 'conhecimento em', 'skills in', 'proficient with').
        """
        pattern = re.compile(
            r'(?:experi[êe]ncia\s+(?:com|em)|conhecimento\s+(?:de|em)|dom[íi]nio\s+de|'
            r'viv[êe]ncia\s+em|familiaridade\s+com|habilidade\s+com|'
            r'experience\s+with|proficient\s+in|knowledge\s+of|skills?\s+in)\s+'
            r'([A-Za-z0-9\+\#\.\s\/\-]{2,60}?)(?=[\.,;\n]|\s+e\s+|\s+and\s+|$)',
            re.I,
        )

        matches = pattern.findall(text)
        candidates: List[str] = []
        for m in matches:
            cleaned = m.strip().strip(":,.-_")
            if cleaned and len(cleaned) >= 2 and not cleaned.lower().startswith(("anos", "meses", "years", "months")):
                candidates.append(cleaned)

        dedup = list(dict.fromkeys(candidates))
        return {
            "hard_skills": dedup,
            "soft_skills": [],
            "emerging_skills": dedup,
            "salary": None,
            "confidence_score": 0.6 if dedup else 0.3,
        }


# Singleton instance
_extractor = JobBERTExtractor()


def extract(text: str, confidence_threshold: float = 0.5) -> Dict[str, Any]:
    """Top-level Tier 2 contextual extraction function."""
    return _extractor.extract(text, confidence_threshold=confidence_threshold)


def extract_jobs_to_csv():
    """Batch extraction to CSV across DB JobPost records."""
    import pandas as pd
    from sqlalchemy import select
    from database import SessionLocal
    from entities import JobPost

    db = SessionLocal()
    try:
        query = select(JobPost)
        jobs = db.scalars(query).all()
        extracted_data = []

        for job in jobs:
            if not job.description:
                continue

            features_res = extract(job.description[:1500])
            features = {
                "id": job.id,
                "job_title": job.name,
                "hard_skills": ", ".join(features_res.get("hard_skills", [])),
                "soft_skills": ", ".join(features_res.get("soft_skills", [])),
                "nice_to_have": "",
                "salary": features_res.get("salary"),
                "contract_type": None,
            }
            extracted_data.append(features)

        df = pd.DataFrame(extracted_data)
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    finally:
        db.close()