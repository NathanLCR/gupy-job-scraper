# SkillPulse AI — Master Technical Architecture & Specification
**Labor Market Intelligence, Multi-Provider Cloud AI Cascade & Semantic Talent Matcher**

## 1. Executive Summary & Vision
**SkillPulse AI** is an open-source labor market intelligence platform and candidate semantic matching engine designed for public cloud deployment. It aggregates job postings across global regions (Europe, Latin America, North America), extracts structured entity attributes through a high-performance AI cascade (Regex Trie $\to$ Contextual NER $\to$ Cloud LLM Router), normalizes competencies against standardized taxonomies (**ESCO** / **O*NET**), and provides a weighted hybrid search and candidate fit analysis engine powered by **pgvector (384-d embeddings)**.

The platform is designed to run **100% on free-tier cloud infrastructure**:
- **Frontend & Edge CDN**: Cloudflare Pages (Static SPA, unlimited global bandwidth, SSL, edge caching).
- **Backend API Engine**: FastAPI on Render / Hugging Face Spaces (Python 3.12, async endpoints, CORS-enabled).
- **Database Layer**: Neon Serverless PostgreSQL with native `pgvector` HNSW indexing (with local SQLite fallback).
- **Cloud AI Router**: Multi-provider free tier router (Groq Llama-3.3 70B & OpenRouter Free Models) with dynamic chunked batching and rate-limit backoff.

---

## 2. Target System Architecture Diagram

```
                                  ┌─────────────────────────────────────────────────────────┐
                                  │             Cloudflare Global Edge Network              │
                                  │         (DNS Proxy · Free SSL · DDoS Shield)            │
                                  └────────────────────────────┬────────────────────────────┘
                                                               │
                              ┌────────────────────────────────┴────────────────────────────────┐
                              ▼                                                                 ▼
┌───────────────────────────────────────────────────────────┐     ┌───────────────────────────────────────────────────────────┐
│              Cloudflare Pages (Frontend SPA)              │     │              FastAPI Backend Gateway                      │
│                                                           │     │                                                           │
│  - Dashboard Overview (Metrics, Trends, Top Tech)         │────▶│  - /api/v1/jobs        - /api/v1/match                    │
│  - Job Explorer & Structured Database Filter              │     │  - /api/v1/analytics   - /api/v1/extract                  │
│  - One-Click Candidate Matcher (Demo Personas)            │     │  - In-Memory SentenceTransformers (384-d MiniLM CPU)      │
└───────────────────────────────────────────────────────────┘     └─────────────────────────────┬─────────────────────────────┘
                                                                                                │
                                                    ┌───────────────────────────────────────────┴───────────────────────────┐
                                                    ▼                                                                       ▼
┌───────────────────────────────────────────────────────────┐                             ┌─────────────────────────────────────────────────────────┐
│           Multi-Provider Free Cloud AI Router             │                             │          PostgreSQL 16 Storage Layer (`pgvector`)       │
│                                                           │                             │                                                         │
│  Tier 1: High-Speed Aho-Corasick / Regex (<5ms)           │                             │  - Relational Schema: Jobs, Skills, Taxonomies          │
│  Tier 2: Token Classifier Contextual NER (~30ms)          │                             │  - Vector Column: embedding vector(384)                 │
│  Tier 3: Free Cloud LLM (Groq 30 RPM / OpenRouter 20 RPM) │                             │  - Indexing: HNSW (m=16, ef_construction=64)            │
│  Engine: Chunked Batch Slicer + 429 Exponential Backoff   │                             │  - Hybrid Search: Reciprocal Rank Fusion (RRF)          │
└───────────────────────────────────────────────────────────┘                             └─────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Breakdown

| Subsystem | Document Reference | Key Responsibilities |
| :--- | :--- | :--- |
| **Cloud AI Router & Batching** | [`01_cloud_ai_router_and_batching.md`](01_cloud_ai_router_and_batching.md) | Multi-provider free LLM orchestration (Groq, OpenRouter), JSON Schema validation, chunked batching, and 429 rate-limit backoff. |
| **Frontend & Demo Mode** | [`02_frontend_and_demo_mode.md`](02_frontend_and_demo_mode.md) | Modern UI dashboard, one-click demo personas, circular fit gauge, skill gap visualization, Chart.js trends, pre-seeded dataset. |
| **Cloudflare Deployment** | [`03_cloudflare_deployment_guide.md`](03_cloudflare_deployment_guide.md) | Step-by-step setup for Cloudflare Pages, backend container hosting (Render/HF), Neon PostgreSQL, and environment configs. |
| **LinkedIn Launch Kit** | [`04_linkedin_launch_and_portfolio_kit.md`](04_linkedin_launch_and_portfolio_kit.md) | Viral LinkedIn post copy, technical talking points, benchmark badges, and GitHub showcase README. |

---

## 4. End-to-End Data Flow

```
1. Ingestion / Scrape ──▶ 2. AI Extraction Cascade ──▶ 3. Canonical Taxonomy Normalization
                                (Regex ➔ NER ➔ Groq/OpenRouter)     (ESCO / O*NET Standard)
                                            │
                                            ▼
4. Dense Vector Generation ◀── 5. PostgreSQL + pgvector Storage
    (384-d all-MiniLM CPU)        (Relational Tables + HNSW Index)
            │
            ▼
6. Candidate CV Submission ──▶ 7. Hybrid Search (RRF) ──▶ 8. Fit Score & Gap Breakdown
 (1-Click Persona / Custom)    (Sparse BM25 + Dense Cosine)   (50% Hard + 20% Soft + 30% Vector)
```

---

## 5. Security, Secrets & Environment Isolation
- All API keys (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `DATABASE_URL`) are read exclusively from environment variables via `config.py`.
- The repository `.gitignore` strictly protects `.env`, `docs/`, `jobs.db`, and build caches.
- A public `.env.example` provides a clear configuration blueprint for external contributors.
