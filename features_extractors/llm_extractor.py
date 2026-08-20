"""
SkillPulse AI — Free Cloud AI Router & Structured Entity Extractor.
Multi-provider free LLM orchestration (Groq Llama 3.3 70B & OpenRouter Free Tier)
with JSON schema enforcement, dynamic 429 exponential backoff, and zero-fail fallback.
"""

import json
import logging
import random
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import requests
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)

# Default endpoints and models from settings
DEFAULT_GROQ_MODEL = settings.GROQ_MODEL
DEFAULT_GROQ_BASE_URL = settings.GROQ_BASE_URL
DEFAULT_OPENROUTER_MODEL = settings.OPENROUTER_MODEL
DEFAULT_OPENROUTER_BASE_URL = settings.OPENROUTER_BASE_URL
DEFAULT_OLLAMA_MODEL = settings.OLLAMA_MODEL
DEFAULT_OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL


class StructuredSalary(BaseModel):
    raw: Optional[str] = Field(None, description="Raw salary text as appeared in description")
    min: Optional[int] = Field(None, description="Minimum numeric salary")
    max: Optional[int] = Field(None, description="Maximum numeric salary")
    currency: Optional[str] = Field("BRL", description="ISO currency code (BRL, USD, EUR, GBP)")


class StructuredExtractionSchema(BaseModel):
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


# Backward compatibility alias
OllamaExtractionSchema = StructuredExtractionSchema


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
        digits = re.findall(r"\d+(?:\.\d+)*", raw)
        min_v = int(digits[0].replace(".", "")) if digits else None
        max_v = int(digits[1].replace(".", "")) if len(digits) > 1 else min_v
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


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Helper to extract JSON object from raw response string."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip markdown fences if present
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: search for first { and last }
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


# ==============================================================================
# CLOUD AI ROUTER PROVIDERS & RATE-LIMIT BACKOFF
# ==============================================================================

def call_groq(
    description: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 25,
) -> Optional[Dict[str, Any]]:
    """
    Invoke Groq Free Tier API (Llama 3.3 70B Versatile) with JSON mode.
    Endpoint: https://api.groq.com/openai/v1/chat/completions
    Rate Limit: 30 RPM / 14,400 RPD
    """
    key = api_key or settings.GROQ_API_KEY
    if not key:
        logger.debug("GROQ_API_KEY is not configured.")
        return None

    model_name = model or settings.GROQ_MODEL
    url = f"{(base_url or settings.GROQ_BASE_URL).rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Job Posting Description:\n{description}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if response.status_code == 429:
        raise requests.exceptions.HTTPError("429 Too Many Requests", response=response)

    response.raise_for_status()
    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    return _extract_json_from_text(content)


def call_openrouter(
    description: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Invoke OpenRouter Free Tier API with JSON Schema adherence and failover headers.
    Endpoint: https://openrouter.ai/api/v1/chat/completions
    Rate Limit: 20 RPM
    """
    key = api_key or settings.OPENROUTER_API_KEY
    if not key:
        logger.debug("OPENROUTER_API_KEY is not configured.")
        return None

    model_name = model or settings.OPENROUTER_MODEL
    url = f"{(base_url or settings.OPENROUTER_BASE_URL).rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://skillpulse.pages.dev",
        "X-Title": "SkillPulse AI",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Job Posting Description:\n{description}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if response.status_code == 429:
        raise requests.exceptions.HTTPError("429 Too Many Requests", response=response)

    response.raise_for_status()
    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    return _extract_json_from_text(content)


def call_ollama(
    description: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Local Ollama endpoint fallback (when self-hosted instance is present).
    """
    model_name = model or DEFAULT_OLLAMA_MODEL
    api_url = f"{(base_url or DEFAULT_OLLAMA_BASE_URL).rstrip('/')}/api/generate"

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
        return _extract_json_from_text(raw_text)
    except Exception as exc:
        logger.debug(f"Ollama local API call failed ({api_url}, {model_name}): {exc}")
        return None


def execute_with_backoff(
    fn: Callable[..., Optional[Dict[str, Any]]],
    *args,
    max_retries: int = 2,
    base_backoff: float = 2.0,
    **kwargs,
) -> Optional[Dict[str, Any]]:
    """
    Executes an LLM API call with HTTP 429 Retry-After inspection and exponential backoff.
    """
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except requests.exceptions.HTTPError as http_err:
            response = getattr(http_err, "response", None)
            if response is not None and response.status_code == 429:
                if attempt == max_retries:
                    logger.warning(f"Rate limit 429 persisted after {max_retries} retries for {fn.__name__}.")
                    return None

                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        wait_seconds = float(retry_after) + 1.0
                    except (ValueError, TypeError):
                        wait_seconds = min(base_backoff * (2 ** attempt) + random.uniform(0.2, 0.8), 60.0)
                else:
                    wait_seconds = min(base_backoff * (2 ** attempt) + random.uniform(0.2, 0.8), 60.0)

                logger.info(f"Received HTTP 429 from {fn.__name__}. Backing off for {wait_seconds:.2f}s (Attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_seconds)
            else:
                logger.debug(f"HTTP error in {fn.__name__}: {http_err}")
                return None
        except Exception as exc:
            logger.debug(f"Provider invocation error in {fn.__name__}: {exc}")
            return None
    return None


def route_cloud_llm(
    description: str,
    *,
    force_provider: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Multi-Provider Cloud AI Router:
    1. Primary: Groq API (Llama 3.3 70B, ~200ms) with 429 backoff
    2. Secondary: OpenRouter API (Free Tier Models) with 429 backoff
    3. Fallback: Local Ollama (if configured/available)
    Returns: (extracted_json_or_none, provider_tag)
    """
    if force_provider == "groq":
        res = execute_with_backoff(call_groq, description, max_retries=2)
        return (res, "tier3_cloud_llm_groq") if res else (None, "tier3_failed")

    if force_provider == "openrouter":
        res = execute_with_backoff(call_openrouter, description, max_retries=2)
        return (res, "tier3_cloud_llm_openrouter") if res else (None, "tier3_failed")

    if force_provider == "ollama":
        res = call_ollama(description)
        return (res, "tier3_ollama_llm") if res else (None, "tier3_failed")

    # 1. Try Primary: Groq Free Tier
    if settings.GROQ_API_KEY:
        res = execute_with_backoff(call_groq, description, max_retries=2)
        if res:
            return res, "tier3_cloud_llm_groq"
        logger.info("Groq provider unavailable or rate-limited. Failing over to OpenRouter...")

    # 2. Try Secondary: OpenRouter Free Tier
    if settings.OPENROUTER_API_KEY:
        res = execute_with_backoff(call_openrouter, description, max_retries=2)
        if res:
            return res, "tier3_cloud_llm_openrouter"
        logger.info("OpenRouter provider unavailable or rate-limited. Failing over to Ollama/Regex...")

    # 3. Try Local Ollama if available
    res = call_ollama(description)
    if res:
        return res, "tier3_ollama_llm"

    return None, "tier1_regex_fallback"


def extract(
    description: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    force_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tier 3 Cloud AI Extraction entry point.
    Dispatches to Cloud AI Router and normalizes output into schema.
    """
    raw, provider_tag = route_cloud_llm(description, force_provider=force_provider)
    raw = raw or {}

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
        "tier_used": provider_tag if raw else "tier1_regex_fallback",
    }
