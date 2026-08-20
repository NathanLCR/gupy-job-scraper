"""
Tier 3 Structured Local LLM Extractor via Ollama (~1.5s).
Enforces structured Pydantic JSON Schema outputs for job attributes,
seniority normalization, salary boundaries (min, max, currency), and soft skills.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

import requests
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = settings.OLLAMA_MODEL
DEFAULT_BASE_URL = settings.OLLAMA_BASE_URL


class StructuredSalary(BaseModel):
    raw: Optional[str] = Field(None, description="Raw salary text as appeared in description")
    min: Optional[int] = Field(None, description="Minimum numeric salary")
    max: Optional[int] = Field(None, description="Maximum numeric salary")
    currency: Optional[str] = Field("BRL", description="ISO currency code (BRL, USD, EUR, GBP)")


class OllamaExtractionSchema(BaseModel):
    job_title: Optional[str] = Field(None, description="Official or inferred job title")
    seniority: Optional[str] = Field(
        None,
        description="Seniority level: Estagiário | Júnior | Pleno | Sênior | Especialista | Lead | Principal | Gerente | Diretor",
    )
    years_experience: Optional[int] = Field(None, description="Minimum required years of experience")
    contract_type: List[str] = Field(default_factory=list, description="Contract modalities: CLT, PJ, Estágio")
    salary: Optional[StructuredSalary] = Field(None, description="Structured salary boundaries")
    hard_skills: List[str] = Field(default_factory=list, description="List of technical skills and tools")
    soft_skills: List[str] = Field(default_factory=list, description="List of behavioral and interpersonal skills")
    nice_to_have: List[str] = Field(default_factory=list, description="Desirable or bonus skills")
    tech_stack: List[str] = Field(default_factory=list, description="Identified architectures and tech stacks")
    confidence_score: float = Field(1.0, ge=0.0, le=1.0, description="Extraction confidence score from 0.0 to 1.0")


SYSTEM_PROMPT = """
You are a senior Tech Recruiter and Labor Market Intelligence AI.
Your task is to parse job postings and extract structured attributes strictly conforming to the requested schema.

Guidelines:
1. "hard_skills": Concrete programming languages, libraries, databases, cloud services, and tools.
2. "soft_skills": Interpersonal, leadership, and behavioral traits (e.g. communication, problem-solving, teamwork).
3. "nice_to_have": Desirable/bonus skills explicitly listed under 'nice to have' or 'diferenciais'.
4. "seniority": Normalize to one of: "Estagiário", "Júnior", "Pleno", "Sênior", "Especialista", "Lead", "Principal", "Gerente".
5. "salary": Extract min, max, and currency (BRL, EUR, USD, GBP) if mentioned.
6. "years_experience": Extract the minimum number of years required (integer only).
7. If any field is not present in the text, use null or empty list.

Return ONLY a valid JSON object matching the schema. No explanations, no markdown formatting.
"""


def _coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    else:
        items = [str(value)]

    cleaned: List[str] = []
    seen: set[str] = set()
    for item in items:
        label = str(item).strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(label)
    return cleaned


def _coerce_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _coerce_float(value: Any, default: float = 1.0) -> float:
    if value in (None, ""):
        return default
    try:
        val = float(value)
        return max(0.0, min(1.0, val))
    except (TypeError, ValueError):
        return default


def _parse_salary_payload(val: Any) -> Optional[Dict[str, Any]]:
    if val is None:
        return None
    if isinstance(val, dict):
        return {
            "raw": str(val.get("raw")) if val.get("raw") else None,
            "min": _coerce_int(val.get("min")),
            "max": _coerce_int(val.get("max")),
            "currency": str(val.get("currency") or "BRL"),
        }
    if isinstance(val, (int, float)):
        return {"raw": str(val), "min": int(val), "max": int(val), "currency": "BRL"}
    if isinstance(val, str):
        raw = val.strip()
        digits = re.findall(r'\d+(?:\.\d+)*', raw)
        min_v = int(digits[0].replace('.', '')) if digits else None
        max_v = int(digits[1].replace('.', '')) if len(digits) > 1 else min_v
        curr = "BRL"
        if "r$" in raw.lower() or "brl" in raw.lower():
            curr = "BRL"
        elif "$" in raw or "usd" in raw.lower():
            curr = "USD"
        elif "€" in raw or "eur" in raw.lower():
            curr = "EUR"
        elif "£" in raw or "gbp" in raw.lower():
            curr = "GBP"
        return {"raw": raw, "min": min_v, "max": max_v, "currency": curr}
    return None


def call_ollama(
    description: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Invokes local Ollama endpoint with structured JSON mode.
    """
    model_name = model or DEFAULT_MODEL
    api_url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/api/generate"

    payload = {
        "model": model_name,
        "prompt": f"{SYSTEM_PROMPT}\n\nJob Description:\n{description}",
        "format": "json",
        "stream": False,
    }

    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        raw_text = result.get("response", "{}")
        return json.loads(raw_text)
    except Exception as exc:
        logger.debug(f"Ollama API call failed ({api_url}, {model_name}): {exc}")
        return None


def extract(
    description: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tier 3 Structured LLM Extraction function.
    Returns normalized dictionary adhering to OllamaExtractionSchema.
    """
    raw = call_ollama(description, model=model, base_url=base_url) or {}

    salary_data = _parse_salary_payload(raw.get("salary"))

    return {
        "job_title": raw.get("job_title"),
        "salary": salary_data,
        "seniority": raw.get("seniority") or raw.get("nivel"),
        "contract_type": _coerce_list(raw.get("contract_type") or raw.get("contrato")),
        "hard_skills": _coerce_list(raw.get("hard_skills")),
        "soft_skills": _coerce_list(raw.get("soft_skills")),
        "nice_to_have": _coerce_list(raw.get("nice_to_have")),
        "tech_stack": _coerce_list(raw.get("tech_stack")),
        "years_experience": _coerce_int(raw.get("years_experience") or raw.get("experiencia_anos")),
        "confidence_score": _coerce_float(raw.get("confidence_score"), default=0.9),
    }
