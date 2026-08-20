<div align="center">

# SkillPulse AI ⚡
### Labor Market Intelligence, Multi-Provider Cloud AI Cascade & Semantic Talent Matcher

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-HNSW_384d-blue?style=for-the-badge)](https://github.com/pgvector/pgvector)
[![Cloudflare](https://img.shields.io/badge/Cloudflare_Pages-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://pages.cloudflare.com/)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.3_70B-f55036?style=for-the-badge)](https://groq.com/)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Free_Models-6366f1?style=for-the-badge)](https://openrouter.ai/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

<br/>

**Live Showcase**: [https://skillpulse.pages.dev](https://skillpulse.pages.dev) · **API Documentation**: `/docs` (Interactive OpenAPI Swagger)

</div>

---

## 1. Executive Summary & Vision

**SkillPulse AI** is an open-source labor market intelligence platform and candidate semantic matching engine designed for public cloud deployment on a **100% free-tier architecture**. It ingests job postings across global regions (Europe, Latin America, North America), extracts structured entity attributes through a high-performance multi-tier AI cascade (Regex Trie $\to$ Contextual NER $\to$ Cloud LLM Router), canonicalizes skills against standardized taxonomies (**ESCO** / **O*NET**), and provides a weighted hybrid search and candidate fit analysis engine powered by **pgvector (384-dimensional dense embeddings)**.

---

## 2. Target System Architecture

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
│  - Market Analytics (Metrics, Trends, Top Tech)           │────▶│  - /api/v1/jobs        - /api/v1/match                    │
│  - Structured Job Explorer & DB Filters                   │     │  - /api/v1/analytics   - /api/v1/extract                  │
│  - 1-Click Recruiter Demo Personas                        │     │  - In-Memory SentenceTransformers (384-d MiniLM CPU)      │
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

## 3. Key Technical Highlights

### ⚡ 1. Multi-Provider Cloud AI Router
Replaces expensive proprietary models or heavy local servers with an intelligent free cloud router:
* **Primary**: **Groq API** (`llama-3.3-70b-versatile`, sub-200ms latency, 30 RPM free).
* **Secondary**: **OpenRouter Free Tier** (`meta-llama/llama-3.3-70b-instruct:free`, 20 RPM).
* **Failover Engine**: Inspects HTTP `Retry-After` headers on `429 Too Many Requests`, executes exponential backoff with jitter, and fails over gracefully to deterministic Tier 1 Aho-Corasick matching.

### 🧠 2. Hybrid Search (Reciprocal Rank Fusion)
Combines lexical precision with semantic depth in PostgreSQL 16:
* **Dense Retrieval**: 384-dimensional embeddings generated in-memory on CPU via `sentence-transformers/all-MiniLM-L6-v2` queried via pgvector HNSW indexing (`<#>` / `<=>`).
* **Sparse Lexical Search**: Full-text keyword matching (`tsvector` & BM25 ranking).
* **RRF Scoring ($k=60$)**:
  $$\text{RRF Score}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{w_m}{k + \text{rank}_m(d)}$$

### 🎯 3. Weighted Candidate Matcher & 1-Click Demo Personas
* **Composite Fit Scoring**:
  $$\text{Fit Score} = 50\% \times \text{Hard Skill Overlap} + 20\% \times \text{Soft Skill Overlap} + 30\% \times \text{Dense Vector Similarity}$$
* **Interactive 1-Click Recruiter Personas**:
  1. 🚀 **Senior Cloud & Backend Architect** (Kubernetes, Docker, AWS, Go, Python, PostgreSQL).
  2. 🤖 **AI / ML Engineer & RAG Specialist** (PyTorch, Hugging Face, LangChain, pgvector).
  3. 💻 **Junior Fullstack Developer** (React, TypeScript, Node.js, SQL, TailwindCSS).
* **Visual Breakdown**: Animated radial SVG fit gauge, matched skills in emerald green, missing critical requirements in rose red, and recommended high-ROI upskilling paths in amber.

### 🌐 4. Zero Cloud Cost Architecture
* **Frontend**: Cloudflare Pages (Free unlimited static hosting & global CDN).
* **Backend**: FastAPI container on Render / Hugging Face Spaces free tier.
* **Database**: Neon Serverless PostgreSQL with native `pgvector` extension.

---

## 4. Repository Layout

```
├── api/
│   └── v1/                   # RESTful API Endpoints (jobs, match, extract, analytics)
├── config.py                 # Pydantic Settings & Environment Loader
├── database.py               # SQLAlchemy 2.0 Engine & Session Factory
├── entities/                 # Normalized Relational Models & pgvector Columns
│   ├── job.py                # Processed vacancy record (embedding vector(384))
│   ├── candidate_profile.py  # Candidate CV record
│   ├── taxonomy_node.py      # ESCO / O*NET canonical hierarchy
│   └── associations.py       # Many-to-many junction tables
├── features_extractors/      # Multi-Tier Cascade Extractors
│   ├── regex_extractor.py    # Tier 1: Aho-Corasick Trie & 300+ regex patterns
│   ├── bert_extractor.py     # Tier 2: JobBERT Contextual NER
│   └── llm_extractor.py      # Tier 3: Free Cloud AI Router (Groq & OpenRouter)
├── frontend/                 # Responsive Single Page Application (SPA)
│   ├── index.html            # Dashboard & Candidate Matcher Views
│   ├── script.js             # Client controller, demo personas & SVG gauge
│   └── style.css             # Glassmorphic dark styling system
├── services/                 # Core Business Logic
│   ├── matcher_service.py    # Candidate fit computation & gap analysis
│   ├── hybrid_search_service.py # Reciprocal Rank Fusion search engine
│   ├── embedding_service.py  # MiniLM CPU embeddings & cosine distance
│   └── taxonomy_service.py   # ESCO canonical skill normalization
├── tests/                    # Pytest Unit & Integration Test Suite
├── docs/                     # Full Technical Architecture & Deployment Specs
├── Dockerfile                # Production Container Image
├── docker-compose.yml        # Multi-Container Local Dev Stack
├── requirements.txt          # Python Dependencies
└── README.md
```

---

## 5. Quickstart & Local Setup

### Prerequisites
* Python 3.11+ or 3.12
* (Optional) Docker & Docker Compose

### 1. Clone & Configure Environment

```bash
git clone https://github.com/NathanLCR/skillpulse-ai.git
cd skillpulse-ai

# Copy example environment configuration
cp .env.example .env
```

Edit `.env` and add your free API keys:
```env
GROQ_API_KEY="gsk_your_free_groq_api_key"
OPENROUTER_API_KEY="sk-or-v1-your_free_openrouter_api_key"
DATABASE_URL="sqlite:///jobs.db"
```

### 2. Install Dependencies & Run Locally

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Start the FastAPI server
uvicorn app:app --reload --port 8000
```

Visit the application in your browser:
* **Web UI Dashboard & Candidate Matcher**: `http://localhost:8000/dashboard`
* **Interactive OpenAPI Swagger Docs**: `http://localhost:8000/docs`

---

## 6. Docker Compose Setup

Run the full stack (PostgreSQL 16 + pgvector, Redis, Celery, and FastAPI) locally:

```bash
docker-compose up -d --build
```

Access the service at `http://localhost:8080`.

---

## 7. Cloud Deployment Guide

### Deploying Frontend to Cloudflare Pages (Free)
1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/) $\to$ **Workers & Pages** $\to$ **Create application** $\to$ **Pages**.
2. Connect your GitHub repository.
3. Configure build settings:
   * **Framework preset**: None
   * **Build command**: Leave empty
   * **Build output directory**: `frontend`
4. Click **Save and Deploy**. Your frontend is live globally on `https://skillpulse.pages.dev`.

### Deploying Backend to Render (Free)
1. Create a **New Web Service** on [render.com](https://render.com).
2. Connect your repository.
3. Set environment variables:
   * `DATABASE_URL`: `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`
   * `GROQ_API_KEY`: `${YOUR_GROQ_API_KEY}`
   * `OPENROUTER_API_KEY`: `${YOUR_OPENROUTER_API_KEY}`
   * `CORS_ORIGINS`: `["https://skillpulse.pages.dev", "http://localhost:8000"]`
4. Set **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`.

---

## 8. Running Automated Tests

Run the complete test suite:

```bash
pytest -v
```

All 84+ unit and integration tests validate the Cloud AI Router, Aho-Corasick trie matching, JobBERT NER extraction, ESCO taxonomy mapping, pgvector hybrid search, and candidate gap calculation.

---

## 9. License

This project is licensed under the [MIT License](LICENSE).
