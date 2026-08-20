"""
Comprehensive Unit & Integration Tests for Phase 2:
Multi-Tier Extraction Cascade & Ollama Integration.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app import app
from features_extractors.bert_extractor import JobBERTExtractor, extract as bert_extract
from features_extractors.llm_extractor import (
    OllamaExtractionSchema,
    StructuredSalary,
    _coerce_float,
    _coerce_int,
    _coerce_list,
    _parse_salary_payload,
    call_ollama,
    extract as llm_extract,
)
from features_extractors.regex_extractor import (
    TRIE_MATCHER,
    _clean,
    detect_stacks,
    extract as regex_extract,
    normalise_skill_label,
)
from services.extractor_service import (
    calculate_confidence,
    extract_cascade,
    parse_salary,
)

client = TestClient(app)


# ==============================================================================
# TIER 1 TESTS (Aho-Corasick Trie & 300+ Skills)
# ==============================================================================

class TestTier1Extractor:

    def test_trie_matcher_exact_and_multiterm(self):
        text = "Experience with Python, Kubernetes, AWS Certified Solutions Architect, and FastAPI."
        matches = TRIE_MATCHER.find_matches(text)
        canonical_ids = {m[1] for m in matches}

        assert "python" in canonical_ids
        assert "kubernetes" in canonical_ids
        assert "cert-aws-solutions-architect" in canonical_ids
        assert "fastapi" in canonical_ids

    def test_trie_word_boundary_isolation(self):
        # 'R' or 'Go' shouldn't match within random words
        text = "Great opportunity for a Good Engineer in Rome with React skills."
        matches = TRIE_MATCHER.find_matches(text)
        canonical_ids = {m[1] for m in matches}

        assert "r" not in canonical_ids
        assert "go" not in canonical_ids
        assert "react" in canonical_ids

    def test_certifications_and_emerging_tools(self):
        text = """
        Mandatory: CKA (Certified Kubernetes Administrator), Terraform Associate, and CISSP.
        Experience with pgvector, ChromaDB, and LangChain.
        """
        features = regex_extract(text)
        assert "CKA (Certified Kubernetes Administrator)" in features["hard_skills"]
        assert "CISSP" in features["hard_skills"]
        assert "pgvector" in features["hard_skills"]
        assert "ChromaDB" in features["hard_skills"]
        assert "LangChain" in features["hard_skills"]

    def test_tech_stack_detection_expanded(self):
        text = "Building modern pipelines using Python, Airflow, dbt, and Snowflake."
        features = regex_extract(text)
        assert "DataOps" in features["tech_stack"]
        assert "Airflow" in features["hard_skills"]
        assert "Snowflake" in features["hard_skills"]

    def test_seniority_and_experience_extraction(self):
        text = "Vaga para Tech Lead. Mínimo de 7 anos de experiência com Java e Spring Boot."
        features = regex_extract(text)
        assert features["seniority"] == "Tech Lead"
        assert features["years_experience"] == 7


# ==============================================================================
# TIER 2 TESTS (Contextual NER / JobBERT)
# ==============================================================================

class TestTier2Extractor:

    def test_bert_extractor_fallback_contextual(self):
        extractor = JobBERTExtractor()
        text = "Buscamos profissional com sólida experiência com Rust, Axum e WebAssembly."
        result = extractor.extract(text)

        assert "hard_skills" in result
        assert "confidence_score" in result
        assert any("Rust" in s or "Axum" in s for s in result["hard_skills"])

    def test_bert_extract_empty_string(self):
        result = bert_extract("")
        assert result["hard_skills"] == []
        assert result["confidence_score"] == 0.0

    def test_bert_extractor_model_pipeline_mock(self):
        extractor = JobBERTExtractor()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"entity_group": "SKILL", "word": "LangGraph", "score": 0.95},
            {"entity_group": "SOFT", "word": "comunicação assertiva", "score": 0.92},
            {"entity_group": "SALARY", "word": "R$ 15.000", "score": 0.88},
        ]
        extractor._pipeline = mock_pipe
        extractor._initialized = True

        result = extractor.extract("Job text here")
        assert "LangGraph" in result["hard_skills"]
        assert "comunicação assertiva" in result["soft_skills"]
        assert result["salary"] == "R$ 15.000"
        assert result["confidence_score"] >= 0.90


# ==============================================================================
# TIER 3 TESTS (Structured Ollama LLM)
# ==============================================================================

class TestTier3Extractor:

    def test_salary_payload_parser(self):
        # Range string
        res = _parse_salary_payload("R$ 10.000 - R$ 15.000")
        assert res["min"] == 10000
        assert res["max"] == 15000
        assert res["currency"] == "BRL"

        # Structured dict
        res_dict = _parse_salary_payload({"min": 80000, "max": 95000, "currency": "EUR"})
        assert res_dict["min"] == 80000
        assert res_dict["max"] == 95000
        assert res_dict["currency"] == "EUR"

    def test_ollama_pydantic_schema_validation(self):
        schema = OllamaExtractionSchema(
            job_title="Senior AI Engineer",
            seniority="Sênior",
            years_experience=5,
            contract_type=["PJ"],
            salary=StructuredSalary(min=18000, max=22000, currency="BRL"),
            hard_skills=["Python", "PyTorch", "vLLM", "pgvector"],
            soft_skills=["Leadership", "Problem Solving"],
            nice_to_have=["Kubernetes"],
            tech_stack=["MLOps"],
            confidence_score=0.95,
        )
        data = schema.model_dump()
        assert data["job_title"] == "Senior AI Engineer"
        assert data["salary"]["min"] == 18000
        assert data["confidence_score"] == 0.95

    @patch("features_extractors.llm_extractor.requests.post")
    def test_call_groq_success(self, mock_post):
        from features_extractors.llm_extractor import call_groq
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"job_title": "Lead Cloud Architect", "seniority": "Lead", "hard_skills": ["Kubernetes", "AWS", "Terraform"], "soft_skills": ["Mentorship"], "years_experience": 6, "confidence_score": 0.96}'
                }
            }]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        res = call_groq("Senior Cloud Architect description", api_key="gsk_test_key")
        assert res["job_title"] == "Lead Cloud Architect"
        assert "Kubernetes" in res["hard_skills"]
        assert res["confidence_score"] == 0.96

    @patch("features_extractors.llm_extractor.requests.post")
    def test_call_openrouter_success(self, mock_post):
        from features_extractors.llm_extractor import call_openrouter
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"job_title": "AI Research Engineer", "seniority": "Sênior", "hard_skills": ["PyTorch", "Transformers", "pgvector"], "soft_skills": ["Research"], "years_experience": 4, "confidence_score": 0.94}'
                }
            }]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        res = call_openrouter("AI Engineer description", api_key="sk-or-test_key")
        assert res["job_title"] == "AI Research Engineer"
        assert "PyTorch" in res["hard_skills"]
        assert res["confidence_score"] == 0.94

    @patch("features_extractors.llm_extractor.call_groq")
    @patch("features_extractors.llm_extractor.call_openrouter")
    def test_cloud_router_failover_from_groq_to_openrouter(self, mock_openrouter, mock_groq):
        from features_extractors.llm_extractor import route_cloud_llm
        from config import settings

        # Groq throws 429 or returns None
        mock_groq.return_value = None
        mock_openrouter.return_value = {
            "job_title": "DevOps Engineer",
            "seniority": "Pleno",
            "hard_skills": ["Docker", "CI/CD"],
            "soft_skills": [],
            "years_experience": 3,
            "confidence_score": 0.90,
        }

        with patch.object(settings, "GROQ_API_KEY", "gsk_dummy"), patch.object(settings, "OPENROUTER_API_KEY", "sk-or-dummy"):
            result, provider = route_cloud_llm("DevOps posting")
            assert provider == "tier3_cloud_llm_openrouter"
            assert result["job_title"] == "DevOps Engineer"


# ==============================================================================
# CONFIDENCE ROUTER & CASCADE ORCHESTRATOR TESTS
# ==============================================================================

class TestConfidenceRouterCascade:

    def test_calculate_confidence_scoring(self):
        # Rich extraction
        t1_rich = {
            "hard_skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
            "seniority": "Sênior",
            "years_experience": 5,
            "soft_skills": ["comunicação"],
            "tech_stack": ["FastAPI"],
        }
        conf_high = calculate_confidence(t1_rich)
        assert conf_high >= 0.85

        # Poor extraction
        t1_poor = {
            "hard_skills": [],
            "seniority": None,
            "years_experience": None,
            "soft_skills": [],
            "tech_stack": [],
        }
        conf_low = calculate_confidence(t1_poor)
        assert conf_low <= 0.30

    def test_cascade_bypasses_tier3_when_confidence_high(self):
        text = """
        Vaga para Desenvolvedor Python Sênior.
        Requisitos: 5 anos de experiência com Python, FastAPI, Docker e PostgreSQL.
        Soft skills: liderança e comunicação.
        """
        result = extract_cascade(text, tier_threshold=0.85)
        # High confidence should resolve via Tier 1
        assert result["tier_used"] == "tier1_regex"
        assert result["confidence"] >= 0.85
        assert "Python" in result["hard_skills"]
        assert result["seniority"] == "Sênior"

    @patch("services.extractor_service.llm_extract")
    def test_cascade_routes_to_tier3_when_confidence_low(self, mock_llm):
        mock_llm.return_value = {
            "job_title": "AI Cloud Specialist",
            "seniority": "Especialista",
            "years_experience": 4,
            "contract_type": ["CLT"],
            "salary": {"min": 14000, "max": 18000, "currency": "BRL"},
            "hard_skills": ["CustomLLM", "Prompting"],
            "soft_skills": ["critical thinking"],
            "nice_to_have": [],
            "tech_stack": [],
            "confidence_score": 0.88,
        }

        # Ambiguous short description with no clear standard skills
        ambiguous_text = "Profissional para liderar projetos inovadores de IA aplicada na empresa."
        result = extract_cascade(ambiguous_text, tier_threshold=0.85)

        assert mock_llm.called
        assert result["tier_used"] in ("tier3_cloud_llm", "tier3_cloud_llm_groq", "tier3_cloud_llm_openrouter", "tier3_ollama_llm")
        assert result["seniority"] == "Especialista"
        assert "CustomLLM" in result["hard_skills"]

    def test_cascade_force_tier_overrides(self):
        text = "Vaga Python Sênior com Docker."
        res_regex = extract_cascade(text, force_tier="regex")
        assert res_regex["tier_used"] == "tier1_regex"


# ==============================================================================
# API ENDPOINT INTEGRATION TESTS
# ==============================================================================

class TestExtractAPIEndpoints:

    def test_extract_endpoint_cascade_mode(self):
        payload = {
            "text": "Desenvolvedor React Sênior. Requisitos: 6 anos de experiência com React, TypeScript, Redux e Tailwind CSS.",
            "extractor_type": "cascade",
            "tier_threshold": 0.85,
        }
        res = client.post("/api/v1/extract", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "React" in data["hard_skills"]
        assert "TypeScript" in data["hard_skills"]
        assert data["seniority"] == "Sênior"
        assert data["years_experience"] == 6
        assert data["tier_used"] in ("tier1_regex", "tier1_tier2_cascade")

    def test_batch_extraction_cascade_trigger(self):
        # 1. Unauthenticated should fail
        unauth_res = client.post("/api/v1/extract/batch?engine=cascade&limit=5")
        assert unauth_res.status_code == 401

        # 2. Authenticated with admin key should succeed
        headers = {"X-Admin-Key": "skillpulse-admin-secret"}
        res = client.post("/api/v1/extract/batch?engine=cascade&limit=5", headers=headers)
        assert res.status_code == 202
        assert res.json()["engine"] == "cascade"

        status_res = client.get("/api/v1/extract/status?engine=cascade", headers=headers)
        assert status_res.status_code == 200
        assert "running" in status_res.json()
