import json
from typing import Any

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.1"

SYSTEM_PROMPT = """
Você é um especialista em Recrutamento e Seleção (Tech Recruiter).
Sua tarefa é ler descrições de vagas de emprego brasileiras e extrair dados estruturados.

Responda ESTRITAMENTE com um objeto JSON válido.
Não inclua explicações, introduções ou blocos de código markdown.

Esquema do JSON:
{
  "job_title": "Título oficial da vaga",
  "salary": "Valor ou faixa (ex: 5000) ou null",
  "nivel": "Estagiário | Júnior | Pleno | Sênior | Especialista | null",
  "contrato": "CLT | PJ | Estágio | null",
  "hard_skills": ["Lista de tecnologias, frameworks e ferramentas concretas"],
  "soft_skills": ["Lista de competências comportamentais"],
  "nice_to_have": ["Diferenciais e tecnologias desejáveis"],
  "experiencia_anos": "Somente o número de anos exigidos ou null",
  "confidence_score": "Valor de 0.0 a 1.0 indicando quão clara estava a descrição"
}

Regras:
1. Se encontrar pilhas como "MERN" ou "LAMP", desmonte-as e inclua os componentes em hard_skills.
2. Seja preciso: se a vaga pede "React", não coloque "Frontend" em hard_skills.
3. Se um campo não existir, use null ou [].
"""


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    else:
        items = [str(value)]

    cleaned: list[str] = []
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


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def call_ollama(description: str, *, model: str = DEFAULT_MODEL) -> dict[str, Any] | None:
    payload = {
        "model": model,
        "prompt": f"{SYSTEM_PROMPT}\n\nDescrição da Vaga:\n{description}",
        "format": "json",
        "stream": False,
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return json.loads(result.get("response", "{}"))
    except Exception as exc:
        print(f"Error calling Ollama: {exc}")
        return None


def extract(description: str, *, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    raw = call_ollama(description, model=model) or {}

    return {
        "job_title": raw.get("job_title"),
        "salary": raw.get("salary"),
        "seniority": raw.get("nivel"),
        "contract_type": _coerce_list(raw.get("contrato")),
        "hard_skills": _coerce_list(raw.get("hard_skills")),
        "soft_skills": _coerce_list(raw.get("soft_skills")),
        "nice_to_have": _coerce_list(raw.get("nice_to_have")),
        "years_experience": _coerce_int(raw.get("experiencia_anos")),
        "confidence_score": _coerce_float(raw.get("confidence_score")),
    }
