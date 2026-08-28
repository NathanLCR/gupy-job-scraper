# SkillPulse AI — Specification: Cloud AI Router & Batching Engine
**Multi-Provider Free LLM Cascade, JSON Schema Enforcement, and Resilient Batching**

## 1. Overview & Objective
This subsystem replaces all requirements for local LLMs (such as local Ollama instances) with a cloud-ready, multi-provider free AI routing layer. It delivers sub-second structured entity extraction, respects free-tier rate limits via intelligent chunked batching and backoff, and ensures zero runtime cost.

---

## 2. Multi-Provider Cloud AI Router Topology

```
                                  ┌─────────────────────────────┐
                                  │   Raw Job / Resume Text     │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │ Tier 1: Aho-Corasick / Regex│ ── If confidence >= 0.85 ──▶ [ Return Normalized Skills ]
                                  │      (300+ Patterns, <5ms)  │
                                  └──────────────┬──────────────┘
                                                 │ (Confidence < 0.85)
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │ Tier 2: JobBERT Context NER │ ── Extract Emerging Skills (~30ms)
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │  Tier 3: Free Cloud Router  │
                                  └──────────────┬──────────────┘
                                                 │
                      ┌──────────────────────────┴──────────────────────────┐
                      ▼                                                     ▼
        ┌───────────────────────────┐                         ┌───────────────────────────┐
        │  Primary: Groq Free Tier  │                         │ Secondary: OpenRouter Free│
        │ - 30 Requests / Minute    │                         │ - 20 Requests / Minute    │
        │ - Model: Llama 3.3 70B    │                         │ - Model: Llama 3.3 70B    │
        │ - Ultra-fast (~200ms)     │                         │ - Free fallback endpoint  │
        └─────────────┬─────────────┘                         └─────────────┬─────────────┘
                      │ (429 Rate Limited)                                  │ (429 Rate Limited)
                      └──────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │ Failover: Tier 1 Trie/Regex │ ── Zero-fail fallback ensures system never crashes
                                  └─────────────────────────────┘
```

---

## 3. Provider Configuration & Endpoints

### 3.1. Primary Provider: Groq API
* **Base URL**: `https://api.groq.com/openai/v1`
* **Default Model**: `llama-3.3-70b-versatile` (or `llama-3.1-8b-instant`)
* **Authentication**: `Bearer ${GROQ_API_KEY}`
* **Rate Limits**: 30 Requests/Min (RPM), 14,400 Requests/Day (RPD), 30,000 Tokens/Min (TPM).
* **Format**: Standard OpenAI Chat Completion with `response_format={"type": "json_object"}`.

### 3.2. Secondary Provider: OpenRouter API
* **Base URL**: `https://openrouter.ai/api/v1`
* **Default Model**: `meta-llama/llama-3.3-70b-instruct:free` (or `google/gemini-2.0-flash-exp:free`, `qwen/qwen-2.5-72b-instruct:free`)
* **Authentication**: `Bearer ${OPENROUTER_API_KEY}`
* **Headers**: `HTTP-Referer: https://skillpulse.pages.dev`, `X-Title: SkillPulse AI`
* **Rate Limits**: 20 Requests/Min (RPM).

---

## 4. Structured JSON Extraction Schema
All LLM prompts enforce strict Pydantic schema adherence:

```json
{
  "job_title": "Senior Cloud Platform Engineer",
  "seniority": "Sênior",
  "years_experience": 5,
  "contract_type": ["CLT", "Remoto"],
  "salary": {
    "raw": "R$ 15.000 - R$ 18.000",
    "min": 15000,
    "max": 18000,
    "currency": "BRL"
  },
  "hard_skills": ["Python", "Kubernetes", "Docker", "AWS", "Terraform", "PostgreSQL"],
  "soft_skills": ["Leadership", "Communication", "Agile Methodologies"],
  "nice_to_have": ["Go", "Kafka", "Prometheus"],
  "tech_stack": ["Cloud Infrastructure", "Distributed Systems"],
  "confidence_score": 0.95
}
```

---

## 5. Intelligent Batching & Rate-Limit Backoff Engine

To process large backlogs of scraped posts without triggering `429 Too Many Requests` or exceeding quotas:

### 5.1. Algorithm & Queue Lifecycle
1. **Chunking**: Slice unextracted posts into batches of $N = 15$ items (`EXTRACTION_BATCH_SIZE`).
2. **Inter-Request Throttle**: Inject a baseline pause of $2.0\text{s}$ (`EXTRACTION_RATE_LIMIT_DELAY`) between individual items to stay safely below the 30 RPM limit.
3. **429 Detection & Dynamic Backoff**:
   - Inspect the HTTP response headers (`retry-after`).
   - If present, sleep for the specified duration plus a $1.0\text{s}$ jitter buffer.
   - If absent, trigger exponential backoff:
     $$\text{Wait Time} = \min(\text{EXTRACTION\_BACKOFF\_SECONDS} \times 2^{\text{retry\_count}}, 60.0)$$
4. **Provider Failover**:
   - If Groq returns 429 after 2 retries, automatically route subsequent items in the batch to OpenRouter.
   - If OpenRouter is also throttled, fallback to deterministic Tier 1 Trie/Regex extraction to maintain pipeline throughput.
5. **State & Progress Reporting**:
   - Update job extraction status atomically in PostgreSQL (`jobs.db`).
   - Expose progress percentage via `/api/v1/extract/status` for the dashboard progress bar.

---

## 6. Dense Embeddings (In-Memory CPU SentenceTransformers)

* **Model**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).
* **Execution Environment**: Runs directly on the backend CPU inside the FastAPI container.
* **Latency**: ~10ms per text.
* **Cost & Limits**: **100% Free, Unlimited, Zero API keys required**.
* **Vector Normalization**: $L_2$ normalized before insertion into `pgvector` for fast cosine similarity via dot product (`<#>` / `<=>`).
