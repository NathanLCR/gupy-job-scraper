# SkillPulse — LinkedIn Launch Package & Video Demo Script

This document contains the ready-to-publish **LinkedIn Launch Post** and the **40–60 Second Video Recording Script** for showcasing SkillPulse as a portfolio-grade product.

---

## 1. LinkedIn Launch Post

```markdown
I started this as a university Python scraping assignment.

It ended up becoming something much larger.

I've been building SkillPulse — a labor market intelligence and semantic job-matching platform for software roles.

Instead of simply collecting job listings, SkillPulse tries to understand them.

What it does under the hood:
→ Multi-source job ingestion across European and Latin American markets
→ Structured extraction of technical skills, seniority, experience, and domain requirements
→ Skill normalization using ESCO / O*NET canonical taxonomies
→ PostgreSQL + pgvector dense semantic search (384-dimensional embeddings)
→ Hybrid lexical + dense retrieval using Reciprocal Rank Fusion (RRF, k=60)
→ Explainable candidate-to-job matching and actionable skill-gap analysis
→ A FastAPI backend backed by 108 automated tests

The part I found most interesting was building the explainable matching pipeline.

Rather than asking an LLM, "Is this candidate a good fit?", the system combines explicit hard/soft skill overlap with dense vector cosine similarity and decomposes the final score into transparent components:

Example: Candidate → AI Backend Engineer: 88%
• Hard Skills: 44.0 / 50
• Soft Skills: 18.0 / 20
• Semantic Similarity: 26.0 / 30
---------------------------------
Total: 88.0 / 100

✓ Matched: Python, FastAPI, Docker, PostgreSQL
○ Missing Gaps: Kubernetes, AWS Bedrock

The project originally started as my CA2 college assignment: scrape jobs from Gupy and store them in SQLite. I kept asking myself what the next production version of each component would look like:

Scraper → Multi-source ingestion adapters
Regex search → Multi-stage extraction cascade
Raw keywords → Canonical skill taxonomy (ESCO/O*NET)
Keyword filter → Hybrid retrieval (pgvector + RRF)
Job listing → Candidate intelligence platform

That evolution became SkillPulse.

Live interactive demo: https://skillpulse.pages.dev
GitHub repository: https://github.com/NathanLCR/gupy-job-scraper

#SoftwareEngineering #AIEngineering #InformationRetrieval #NLP #Python #FastAPI #PostgreSQL #pgvector
```

---

## 2. 40–60 Second Product Screen Recording Script

Record a clean screen capture at 1080p (60fps) with your browser at 100% zoom.

| Timestamp | Screen / View | Action on Screen | Voiceover / Text Overlay |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:08** | **Market Overview** (`Market Analytics`) | Open on the overview banner showing `"395 Software Jobs Analyzed across Europe, UK, and Latin America"`. Scroll gently across the Top Skills table (Python 38%, AWS 29%, React 24%) and remote workplace ratio. | *"SkillPulse analyzes live software job postings across international markets to understand tech demand."* |
| **0:08 – 0:18** | **Job Explorer** (`Job Explorer`) | Switch to Job Explorer. Click the preset chip `"backend AI engineer working with Python and LLMs"` and press enter. Show ranked results with Match %, Matched skills (✓), and *"Why this matched"*. | *"Hybrid retrieval combines PostgreSQL full-text search with dense pgvector embeddings via Reciprocal Rank Fusion."* |
| **0:18 – 0:42** | **Candidate Matcher** (`Candidate Matcher` — **Hero Demo**) | Switch to Candidate Matcher. Click `[ Backend Developer ]` 1-click persona. The screen smoothly computes and scrolls to the results: point breakdown (`44/50`, `18/20`, `26/30` = `88/100`), Strongest areas bars (Backend 96%, Databases 91%), and Largest gaps (`Kubernetes`, `MLOps`). Scroll to the #1 ranked job card showing matched skills and match reason. | *"Click any persona to test candidate fit. The matcher doesn't just output a percentage—it explains exactly how hard skills, soft skills, and semantic vectors contributed, and highlights your largest skill gaps."* |
| **0:42 – 0:55** | **Architecture View** (`How It Works`) | Switch to How It Works. Briefly pan over the visual pipeline diagram: *Ingestion $\to$ Extraction Cascade $\to$ ESCO Normalization $\to$ pgvector $\to$ RRF $\to$ Matcher*. | *"Built with FastAPI, PostgreSQL 16, pgvector, and ESCO taxonomy normalization. 108 automated tests."* |
| **0:55 – 1:00** | **Outro** | Finish on the SkillPulse header with the live demo link. | *"SkillPulse — Understand the market. Measure your fit. Find your gaps."* |

---

## 3. Publication Checklist

- [x] **No Authentication Required**: Anyone can test the demo immediately with zero signup friction.
- [x] **1-Click Software Personas**: 4 distinct personas (`Backend Developer`, `Junior AI Engineer`, `Full-stack Developer`, `Senior Cloud Architect`) ready in 1 click.
- [x] **Explainable Fit Scoring**: Transparent point breakdown ($X/50 + Y/20 + Z/30 = \text{Total}/100$) + domain strength bars + skill inspection chips.
- [x] **Realistic Seeded Dataset**: 395 structured software positions with canonical ESCO/O*NET taxonomy normalization.
- [x] **Job Explorer (Hybrid Search)**: Natural language query box with explainability badges.
- [x] **How It Works**: Architecture pipeline diagram and clear technical descriptions without exaggerated claims.
