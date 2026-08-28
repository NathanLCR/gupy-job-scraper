# SkillPulse AI — LinkedIn Launch & Portfolio Showcase Kit
**Storytelling Copy, Architecture Badges, Technical Talking Points, and GitHub README Blueprint**

## 1. LinkedIn Post Copy (Ready-to-Post)

### 🚀 Option A: Deep Technical & Engineering Focus (Recommended)

```markdown
🚀 Excited to launch SkillPulse AI — an open-source labor market intelligence platform and semantic talent matching engine built with FastAPI, pgvector, and multi-provider AI cascades.

🔍 The Problem:
Traditional keyword-based job search engines fail when vocabulary diverges. A query for "Cloud Platform Engineer" often misses top candidates proficient in "Kubernetes, Terraform, and AWS Infrastructure" due to rigid lexical matching.

⚙️ How I Engineered the Solution:
1. 🌐 Multi-Region Ingestion: Ingests and standardizes job postings across European and LatAm markets (Dublin, London, São Paulo).
2. ⚡ Multi-Tier AI Cascade: Combines high-speed Trie/Regex matching (<5ms) with Contextual NER and Cloud LLM routers (Groq Llama 3.3 70B & OpenRouter) with dynamic 429 rate-limit backoff.
3. 📚 Canonical Taxonomy Normalization: Standardizes raw competency variations against European ESCO and O*NET frameworks.
4. 🧠 Hybrid Search (RRF): Blends sparse lexical retrieval with dense 384-dimensional sentence embeddings in PostgreSQL (pgvector + HNSW indexing).
5. 🎯 Weighted Candidate-to-Job Matcher: Computes composite fit scores (50% Hard Skills + 20% Soft Skills + 30% Semantic Vector Similarity) and provides personalized upskilling pathways.

🛠️ The Tech Stack:
• Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2
• Database: PostgreSQL 16 with pgvector & HNSW indexing
• AI & NLP: Groq, OpenRouter, SentenceTransformers (all-MiniLM-L6-v2)
• Infrastructure: Cloudflare Pages (Edge CDN), Docker, Render
• Frontend: Responsive Glassmorphic SPA, Chart.js

🌐 Live Demo: https://skillpulse.pages.dev (Test with 1-click demo personas!)
💻 GitHub (Code & Architecture): https://github.com/NathanLCR/skillpulse-ai

I’d love to hear your thoughts and feedback! What tech skills are seeing the highest demand in your region right now?

#ArtificialIntelligence #Python #FastAPI #MachineLearning #VectorSearch #PostgreSQL #Cloudflare #OpenSource #DataEngineering
```

---

## 2. Technical Talking Points for Recruiter & Tech Lead Interviews

When recruiters or engineering managers ask about this project during interviews, highlight these architectural decisions:

1. **Why Hybrid Search (Reciprocal Rank Fusion) instead of pure vector search?**
   * *Answer*: "Pure dense vector search can sometimes hallucinate semantic closeness on very specific technical acronyms (e.g. `K8s` vs `CKA`). By using Reciprocal Rank Fusion to combine sparse BM25 keyword matching with dense HNSW vector distances in `pgvector`, SkillPulse delivers the highest precision on specific tooling while preserving semantic understanding."
2. **How did you manage free-tier rate limits with LLM extraction?**
   * *Answer*: "I designed a multi-tier cascade. 70% of standard tech jobs are resolved in $<5\text{ms}$ by the Aho-Corasick trie layer. For ambiguous descriptions, we invoke the Groq/OpenRouter cloud router in chunked batches with dynamic exponential backoff and automatic provider failover on HTTP 429."
3. **How does the system achieve zero cloud hosting cost?**
   * *Answer*: "We decoupled the architecture: Cloudflare Pages delivers the static frontend globally on edge CDN with zero bandwidth fees, Neon provides serverless PostgreSQL with `pgvector`, and in-memory MiniLM embeddings run directly on CPU without third-party embedding API costs."

---

## 3. GitHub Badges & Header Assets

Add these markdown badges to the top of your GitHub `README.md`:

```markdown
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-HNSW_384d-blue?style=for-the-badge)](https://github.com/pgvector/pgvector)
[![Cloudflare](https://img.shields.io/badge/Cloudflare_Pages-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://pages.cloudflare.com/)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.3_70B-f55036?style=for-the-badge)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
```
