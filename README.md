<div align="center">

# SkillPulse

### Labor market intelligence and semantic job matching for software professionals.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-384d_HNSW-blue?style=flat)](https://github.com/pgvector/pgvector)
[![Tests](https://img.shields.io/badge/Tests-108_Passing-10b981?style=flat&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-slate.svg?style=flat)](https://opensource.org/licenses/MIT)

<br/>

**[Live Demo](https://skillpulse.pages.dev)** · **[Architecture](#system-architecture)** · **[API Reference](/docs)** · **[Quickstart](#quickstart--local-setup)**

</div>

---

## What does SkillPulse do?

**SkillPulse** analyzes software job postings across European and Latin American markets, extracts and normalizes required technical competencies using canonical taxonomies (**ESCO** / **O*NET**), and combines full-text lexical ranking with 384-dimensional dense vector embeddings (**pgvector**) to measure explainable candidate-job fit and identify high-ROI skill gaps.

```text
Nathan — Backend → AI Engineer

Market Fit
████████████████░░ 88%

Strongest areas
Backend Engineering        96%
Databases & Storage        91%
Cloud / DevOps             82%
Machine Learning & AI      64%
Frontend & Web             58%

Largest gaps
○ Kubernetes
○ MLOps
○ LLM evaluation
○ AWS Bedrock
```

---

## Core Capabilities

### 1. 1-Click Candidate Matcher (Hero Feature)
* **Instant Evaluation**: Test candidate resumes or 1-click software personas (*Backend Developer*, *Junior AI Engineer*, *Full-stack Developer*, *Senior Cloud Architect*).
* **Explainable Fit Scoring**: Decomposes the composite match score into transparent, defensible components:
  $$\text{Fit Score} = 50\% \times \text{Hard Skill Overlap} + 20\% \times \text{Soft Skill Overlap} + 30\% \times \text{Dense Vector Similarity}$$
* **Point Breakdown**: Exposes granular points ($44.0 / 50$ Hard Skills + $18.0 / 20$ Soft Skills + $26.0 / 30$ Semantic Sim = $88.0 / 100$) rather than an opaque black-box number.
* **Skill Gap Analysis**: Identifies exact missing requirements (e.g. `Kubernetes`, `AWS Bedrock`) and recommends high-ROI upskilling targets ranked by market frequency.

### 2. Job Explorer & Hybrid Search
* **Natural Language Queries**: Search vacancies using semantic phrases such as `"backend AI engineer working with Python and LLMs"`.
* **Reciprocal Rank Fusion (RRF, $k=60$)**: Combines PostgreSQL full-text keyword retrieval with dense vector cosine similarity (`all-MiniLM-L6-v2` 384-d embeddings) stored in `pgvector`.
* **Explainability Rationale**: Every search result surfaces why it matched, including matched skills (✓) and missing skills (○).

### 3. Labor Market Overview & Analytics
* **Continuous Vacancy Intelligence**: Aggregates structured vacancies across Ireland, UK, Europe, and Latin America.
* **Skill Frequency Distributions**: Real-time tracking of top demanded technologies (Python 38%, AWS 29%, React 24%, Docker 22%, PostgreSQL 20%).
* **Emerging Tech & Workplace Models**: Identifies high-velocity technologies (`FastAPI`, `LLM`, `Terraform`, `pgvector`) and remote/hybrid/onsite breakdowns.

---

## System Architecture

SkillPulse is engineered with a **production-oriented architecture** that decouples multi-source data ingestion, cascade feature extraction, canonical taxonomy mapping, and hybrid vector retrieval.

```text
                JOB SOURCES
                    │
        ┌───────────┴───────────┐
      Arbeitnow   Remotive    Himalayas   RemoteOK    Gupy
                    │
                    ▼
            Extraction Cascade Pipeline
        ┌───────────┼───────────┐
    Tier 1: Trie   Tier 2: NER  Tier 3: Cloud LLM Router
  (Aho-Corasick)  (Contextual)  (Groq Llama 3.3 / OpenRouter)
                    │
                    ▼
           Skill Normalization
        ESCO / O*NET Canonical Graph
                    │
                    ▼
            PostgreSQL 16 Storage Layer
       pgvector (384-d MiniLM Embeddings)
                    │
             ┌──────┴──────┐
       PostgreSQL Lexical  Dense Vector
          (Full-Text)      (HNSW Cosine)
             └──────┬──────┘
                    ▼
      Reciprocal Rank Fusion (RRF, k=60)
                    │
                    ▼
         Explainable Matching Engine
  Fit = 50% Hard Skill + 20% Soft Skill + 30% Semantic Similarity
```

### Engineering Highlights

* **Multi-Source Ingestion**: Modular adapter architecture collecting vacancies across international job portals.
* **Multi-Stage Extraction Cascade**: High-speed deterministic Trie matching for canonical terms, contextual token classification for experience/seniority, and cloud LLM routing for unstructured descriptions.
* **ESCO / O\*NET Taxonomy Normalization**: Maps thousands of raw skill aliases (e.g. `reactjs` $\to$ `React`, `postgres` $\to$ `PostgreSQL`, `k8s` $\to$ `Kubernetes`) to a structured semantic graph.
* **PostgreSQL + pgvector Hybrid Retrieval**: Merges PostgreSQL full-text retrieval with dense vector similarity via Reciprocal Rank Fusion (RRF).
* **Automated Test Suite**: 108 unit and integration tests across data models, extraction pipelines, search algorithms, and API endpoints.

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend & API** | FastAPI, Python 3.11+, Pydantic v2, Uvicorn |
| **Database & Vectors** | PostgreSQL 16, pgvector (HNSW Indexing), SQLAlchemy 2.0, Alembic |
| **Embeddings & NLP** | `sentence-transformers/all-MiniLM-L6-v2` (384-d), ESCO / O*NET Graph |
| **Cloud AI Router** | Groq (`llama-3.3-70b-versatile`), OpenRouter API (Failover with backoff) |
| **Frontend UI** | Modern Vanilla JS/HTML5/CSS3 (Product-first design, 0 heavy frameworks) |
| **Quality & Tests** | `pytest`, `pytest-asyncio`, `httpx` (108 automated tests) |

---

## Quickstart & Local Setup

### Prerequisites
* Python 3.11+ or 3.12
* Git

### 1. Clone & Configure Environment

```bash
git clone https://github.com/NathanLCR/gupy-job-scraper.git
cd gupy-job-scraper

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` as needed:
```env
DATABASE_URL="sqlite:///jobs.db"
GROQ_API_KEY="your_groq_api_key"
OPENROUTER_API_KEY="your_openrouter_api_key"
PORT=8000
```

### 3. Run Automated Tests

```bash
pytest
```
*Expected: 108 passed tests in ~2 seconds.*

### 4. Start the Application

```bash
uvicorn app:app --reload --port 8000
```

Open your browser at:
* **Product Interface**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
* **OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/match` | Candidate CV-to-job matching, explainable scoring & skill gap analysis |
| `POST` | `/api/v1/jobs/search/hybrid` | Reciprocal Rank Fusion (RRF) hybrid search across vacancies |
| `GET` | `/api/v1/jobs` | Paginated structured vacancies with multi-region and taxonomy filters |
| `POST` | `/api/v1/jobs/ingest` | Trigger background ingestion across public feeds |
| `POST` | `/api/v1/extract` | Extract entities using multi-stage cascade |
| `GET` | `/api/v1/analytics/overview` | Real-time market analytics, skill demand & workplace mix |
| `GET` | `/api/v1/analytics/trends` | 30-day technology frequency timelines |
| `GET` | `/health` | System health check and database connectivity confirmation |

---

## Project History & Evolution

This project originally originated as an academic Python assignment (CA2) focused on scraping vacancy listings from Gupy and storing them in SQLite.

Throughout development, each component was re-architected toward production standards:
* **Scraper $\to$ Multi-Source Ingestion Engine**: Expanded from a single site scraper into a modular adapter system ingesting European and Latin American job boards.
* **Regex Keywords $\to$ Extraction Cascade**: Replaced basic substring searches with a multi-tier cascade combining Aho-Corasick Trie matching, contextual token NER, and LLM extraction routing.
* **Raw Strings $\to$ Canonical Skill Taxonomy**: Implemented normalization against international labor taxonomies (**ESCO** / **O*NET**).
* **Keyword Filtering $\to$ Hybrid Retrieval**: Added dense vector embeddings (`all-MiniLM-L6-v2`), `pgvector` indexing, and Reciprocal Rank Fusion (RRF).
* **Static Job Board $\to$ Candidate Intelligence Platform**: Evolved into **SkillPulse**, providing explainable fit scoring, domain competency breakdown, and actionable skill-gap recommendations.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
