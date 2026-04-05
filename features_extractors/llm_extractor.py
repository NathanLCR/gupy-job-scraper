import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
from sqlalchemy import select
from database import SessionLocal
from entities import JobPost

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.1"
OUTPUT_CSV = "extracted_jobs_llm.csv"

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

def call_ollama(description: str) -> dict[str, Any] | None:
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": f"{SYSTEM_PROMPT}\n\nDescrição da Vaga:\n{description}",
        "format": "json",
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return json.loads(result.get("response", "{}"))
    except Exception as e:
        print(f"Error calling Ollama: {e}")
        return None

def run_llm_extraction(limit: int = 5):
    db = SessionLocal()
    try:
        print(f"Fetching {limit} jobs for LLM extraction...")
        jobs = db.scalars(select(JobPost).limit(limit)).all()
        
        extracted_results = []
        for job in jobs:
            if not job.description:
                continue
            
            print(f"Extracting job {job.id}: {job.name}...")
            desc = job.description[:3000]
            
            parsed_data = call_ollama(desc)
            if parsed_data:
                parsed_data["source_id"] = job.id
                parsed_data["extracted_at"] = datetime.now(timezone.utc).isoformat()
                
                if isinstance(parsed_data.get("hard_skills"), list):
                    parsed_data["hard_skills"] = ", ".join(parsed_data["hard_skills"])
                if isinstance(parsed_data.get("soft_skills"), list):
                    parsed_data["soft_skills"] = ", ".join(parsed_data["soft_skills"])
                if isinstance(parsed_data.get("nice_to_have"), list):
                    parsed_data["nice_to_have"] = ", ".join(parsed_data["nice_to_have"])
                
                extracted_results.append(parsed_data)
        
        if extracted_results:
            df = pd.DataFrame(extracted_results)
            df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
            print(f"\nExtraction complete! Saved to: {OUTPUT_CSV}")
        else:
            print("No data extracted.")

    finally:
        db.close()

if __name__ == "__main__":
    run_llm_extraction(limit=150)
