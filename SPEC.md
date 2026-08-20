# SkillPulse AI — Technical Specification & Architecture
**Labor Market Intelligence, Multi-Tier AI Skill Extraction & Semantic Candidate Matcher**

## 1. Overview & Vision
**SkillPulse AI** (formerly Gupy Job Scraper & AI Extractor) is an enterprise-ready labor market intelligence platform. It ingests job postings across global regions, extracts structured entity attributes using a multi-tier cascade (Regex $\to$ Local NER $\to$ Structured Ollama LLM), canonicalizes skills into standardized taxonomies (ESCO / O*NET), stores dense semantic embeddings in PostgreSQL (`pgvector`), and powers an interactive **Candidate-to-Job Matching & Skill Gap Analysis** engine.

---

## 2. Target Architecture

```
                                      ┌─────────────────────────────────────────────────────────┐
                                      │             Multi-Region Ingestion Layer                │
                                      │   (Gupy [BR] · European/Adzuna [IE/UK] · JSON Feeds)    │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │
                                                                   ▼
                                      ┌─────────────────────────────────────────────────────────┐
                                      │            FastAPI Gateway & Celery Workers             │
                                      │              (Async Task Queue via Redis)               │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │
                                      ┌────────────────────────────┴────────────────────────────┐
                                      │                                                         │
                                      ▼                                                         ▼
                ┌───────────────────────────────────────────┐             ┌───────────────────────────────────────────┐
                │       Multi-Tier Extraction Cascade       │             │       Candidate Resume Matcher Engine     │
                │                                           │             │                                           │
                │  Tier 1: Fast Regex / Trie (<5ms)         │             │  1. Parse Resume (PDF/Text)               │
                │  Tier 2: Token Classifier NER (~30ms)     │             │  2. Extract Candidate Skills Profile      │
                │  Tier 3: Local Ollama LLM (Structured)    │             │  3. Compute Skill Fit & Missing Overlap   │
                └─────────────────────┬─────────────────────┘             └─────────────────────┬─────────────────────┘
                                      │                                                         │
                                      ▼                                                         ▼
                ┌───────────────────────────────────────────┐             ┌───────────────────────────────────────────┐
                │     Canonical Taxonomy & Graph Layer      │             │        pgvector Hybrid Search (RRF)       │
                │     (ESCO / O*NET Aliases + Co-occur)     │             │    Dense Cosine Dist + Sparse BM25 / Text │
                └─────────────────────┬─────────────────────┘             └─────────────────────┬─────────────────────┘
                                      │                                                         │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │
                                                                   ▼
                                      ┌─────────────────────────────────────────────────────────┐
                                      │            PostgreSQL 16 Storage Layer                  │
                                      │     (Relational Entities + HNSW Vector Indexing)        │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │
                                                                   ▼
                                      ┌─────────────────────────────────────────────────────────┐
                                      │               Unified Web UI Dashboard                  │
                                      │  [Market Analytics] [Job Explorer] [Candidate Matcher]  │
                                      └─────────────────────────────────────────────────────────┘
```

---

## 3. Core Functional Pillars

### 3.1. Multi-Region Ingestion Adapter
* Abstract base class: `BaseIngestionAdapter`.
* Properties per job: `region` (`Europe`, `Latin America`, `North America`, `Global`), `country_code` (ISO 2-letter e.g. `IE`, `GB`, `BR`, `US`), `currency` (`EUR`, `GBP`, `BRL`, `USD`), `workplace_type` (`REMOTE`, `HYBRID`, `ONSITE`).
* Concrete implementations:
  1. `GupyAdapter` (Brazil / LatAm).
  2. `AdzunaAdapter` / `PublicJobFeedAdapter` (Ireland, UK, Europe).
  3. `DirectIngestAdapter` (Custom JSON / text ingestion).
* Deduplication by SHA-256 fingerprint of normalized `company + title + location`.

### 3.2. Multi-Tier Hybrid Extraction Pipeline
* **Tier 1 (High-Speed Exact Matching - <5ms)**: Aho-Corasick trie & regex matching 300+ standard tech terms, cloud providers, databases, and frameworks.
* **Tier 2 (Contextual NER - ~30ms)**: Token classification using `JobBERT` to extract emerging skills and domain-specific terminology.
* **Tier 3 (Structured Local LLM via Ollama - ~1.5s)**: Local `Llama 3.1` / `Qwen 2.5` invoked with JSON Schema format to extract:
  * Normalized job title & seniority (`Intern`, `Junior`, `Mid`, `Senior`, `Lead`, `Principal`).
  * Structured salary bounds (`min`, `max`, `currency`).
  * Minimum years of experience requirement.
  * Implicit soft skills and nice-to-have requirements.
* **Confidence Routing**: If Tier 1 + 2 confidence score $\ge 0.85$, bypass Tier 3 to save computation.

### 3.3. Canonical Taxonomy & Graph Normalization
* Standardized skill dictionary mapping raw variations (e.g. `["k8s", "kubernetes", "k8s cluster"]` $\to$ `Kubernetes`).
* Alignment with **ESCO** and **O*NET** skill identifiers.
* Pairwise skill co-occurrence computation to power tech cluster analysis and graph visualization.

### 3.4. Semantic Search & Storage (`pgvector`)
* PostgreSQL 16 relational tables (`jobs`, `companies`, `skills`, `locations`, `regions`, `taxonomy_nodes`).
* Sentence transformer embedding (384-dimensional `vector(384)`) with **HNSW** index (`m=16, ef_construction=64`).
* Hybrid Search: Reciprocal Rank Fusion (RRF) combining full-text search (`tsvector` with BM25 ranking) and vector cosine distance.

### 3.5. Candidate Matcher & Skill Gap Analysis Engine
* Input: User uploads CV (PDF/TXT) or inputs structured profile.
* Skill extraction on candidate text.
* Hybrid search identifies relevant job listings in chosen region.
* Fit score computation:
  $$\text{Fit Score} = 0.50 \times \text{HardSkillOverlap} + 0.20 \times \text{SoftSkillOverlap} + 0.30 \times \text{VectorSimilarity}$$
* Outputs:
  * **Fit Percentage** (0–100%).
  * **Matched Skills** (green badges).
  * **Missing Critical Skills** (red badges).
  * **Recommended Next Skills** to maximize match across target roles.

### 3.6. Modernized UI Dashboard with Dedicated Matcher Tab
1. **📊 Market Analytics**: Regional salary curves, top required technologies, skill growth trends, and interactive co-occurrence network graph.
2. **🔍 Job Explorer**: Multi-region faceted search, hybrid keyword/vector search bar, remote filters, detailed job drawer.
3. **🎯 Candidate Matcher (Dedicated Tab)**:
   * Resume dropzone / text editor.
   * Target region & seniority filter pills.
   * Match gauge & visual skill gap breakdown.
4. **⚙️ Ingestion & Worker Ops**: Trigger scrapers, monitor Celery tasks, inspect queue status.

---

## 4. API Endpoints Specification (FastAPI v1)

```
GET  /api/v1/jobs                 # Paginated multi-region search with filters
GET  /api/v1/jobs/{id}            # Job details with skill graph links
POST /api/v1/jobs/ingest          # Enqueue background scraping/ingestion task
POST /api/v1/extract              # Synchronous on-demand text extraction
POST /api/v1/match                # Candidate CV matching & skill gap analysis
GET  /api/v1/analytics/skills     # Regional skill demand & salary correlation
GET  /api/v1/analytics/graph      # Skill co-occurrence network data
GET  /api/v1/tasks/{task_id}      # Celery task status and progress
```

---

## 5. Docker Topology

* `api`: FastAPI application (Uvicorn).
* `worker`: Celery worker for async scraping and batch extraction.
* `redis`: Task message broker & caching.
* `db`: PostgreSQL 16 + `pgvector`.
* `ollama`: Local LLM server (Llama 3.1 / Qwen 2.5).

---

## 6. Phased Implementation Roadmap
1. **Phase 1**: Core FastAPI Async App, PostgreSQL 16 + `pgvector`, Alembic migrations, Docker Compose.
2. **Phase 2**: Multi-Tier Extraction Cascade (Trie + JobBERT + Ollama Structured JSON).
3. **Phase 3**: Canonical Taxonomy (ESCO/O*NET) & Co-occurrence Graph Engine.
4. **Phase 4**: Hybrid Search (RRF) & Candidate Matcher with Gap Analysis.
5. **Phase 5**: Multi-Region Ingestion Adapters & Celery Worker Queue.
6. **Phase 6**: UI Redesign (Dashboard, Job Explorer, Dedicated Matcher Tab).
