# SkillPulse AI — Specification: Frontend UI & Recruiter Demo Mode
**Cloudflare Pages SPA, One-Click Demo Personas, Interactive Fit Visualizer, and Pre-Seeded Dataset**

## 1. Overview & Objectives
The user interface is designed as a standalone, responsive, glassmorphic Single Page Application (SPA) deployable to **Cloudflare Pages**. It offers visitors (recruiters, tech leads, hiring managers) an immediate, frictionless demonstration of SkillPulse AI's labor market analytics and semantic matching capabilities.

---

## 2. Key UI Views & Navigation

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  SkillPulse AI              [ Market Analytics ] [ Job Explorer ] [ Candidate Matcher ]│
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ Quick Demo Personas ]: [ 🚀 Senior Cloud Architect ] [ 🤖 AI/ML Eng ] [ 💻 Fullstack]│
│                                                                                        │
│  ┌────────────────────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │         Candidate CV Profile           │  │       Composite Fit & Gap Breakdown  │  │
│  │                                        │  │                                      │  │
│  │  - Extracted Seniority: Senior         │  │      ╭──────────╮                    │  │
│  │  - Years Experience: 6+ yrs            │  │     │   94%    │   Overall Fit Score │  │
│  │  - Canonical Hard Skills:              │  │      ╰──────────╯                    │  │
│  │    [Python] [Kubernetes] [Docker]      │  │                                      │  │
│  │    [AWS] [PostgreSQL] [FastAPI]        │  │  ✅ Matched Skills (12):             │  │
│  │                                        │  │     [Python] [AWS] [Kubernetes]...   │  │
│  │  - Soft & Domain Skills:               │  │  ⚠️ Missing Critical Skills (2):     │  │
│  │    [System Design] [Mentorship]        │  │     [Terraform] [Prometheus]         │  │
│  │                                        │  │  📈 Recommended Upskilling (Top Gap):│  │
│  │                                        │  │     + Terraform (+18% market match)  │  │
│  └────────────────────────────────────────┘  └──────────────────────────────────────┘  │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                 Ranked Job Listings (Reciprocal Rank Fusion Hybrid Search)        │  │
│  │  1. Senior Platform Engineer · Stripe (Dublin / Remote) · Fit: 96%               │  │
│  │  2. Lead Cloud Infrastructure Architect · Revolut (London / Hybrid) · Fit: 91%   │  │
│  │  3. Principal Backend Engineer · Nubank (São Paulo / Remote) · Fit: 88%          │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. One-Click Demo Personas Specification

To ensure recruiters from LinkedIn can test the engine in **under 3 seconds without uploading files**, the UI provides 3 pre-configured demo personas:

### Persona 1: Senior Cloud & Backend Architect
* **Target Title**: Lead / Senior Cloud Platform Engineer
* **Experience**: 6+ years
* **Raw Resume Profile**:
  > *"Senior Backend Engineer with 6+ years building distributed cloud systems using Python, FastAPI, and Go. Deep hands-on expertise in Kubernetes container orchestration, Docker, AWS (EKS, RDS, S3), PostgreSQL relational modeling, and Redis caching. Proven background in CI/CD pipeline automation, microservices architecture, and technical team mentorship."*
* **Expected Match Focus**: Senior Cloud, DevOps, and Platform Engineering roles across Europe & Americas.

### Persona 2: AI / ML Engineer & RAG Specialist
* **Target Title**: AI / Machine Learning Engineer
* **Experience**: 4 years
* **Raw Resume Profile**:
  > *"Machine Learning Engineer specialized in LLM applications, RAG pipelines, and semantic search. Proficient with PyTorch, Hugging Face Transformers, LangChain, pgvector, and FastAPI. Strong foundation in Python, data processing with Pandas and NumPy, Docker containerization, and vector database indexing (HNSW, Cosine similarity)."*
* **Expected Match Focus**: GenAI, MLOps, and NLP Specialist roles.

### Persona 3: Junior Fullstack Developer
* **Target Title**: Junior / Associate Software Developer
* **Experience**: 1 year
* **Raw Resume Profile**:
  > *"Junior Fullstack Developer with solid foundation in modern JavaScript/TypeScript, React, Node.js, and HTML5/CSS3. Experience with relational databases (SQL, PostgreSQL), Git version control, and building responsive web applications with TailwindCSS and RESTful APIs."*
* **Expected Match Focus**: Entry-level and Junior Frontend / Fullstack roles.

---

## 4. Visual Components & Styling System

* **Design System**: Glassmorphism with tailored dark theme (`#0f172a` slate base, cyan `#06b6d4` & violet `#8b5cf6` accent gradients).
* **Typography**: Modern geometric typography (`Outfit` / `Inter` from Google Fonts).
* **Interactive Charting**: Chart.js for real-time Technology Trends, Seniority Breakdown, and Location Distribution.
* **Fit Score Gauge**: CSS animated circular radial progress meter with color grading ($<60\%$ Amber, $60-80\%$ Cyan, $>80\%$ Emerald Green).
* **Pill Badges**:
  - Matched Skills: Emerald outline with green glow (`background: rgba(16, 185, 129, 0.15)`).
  - Missing Skills: Rose red badge (`background: rgba(244, 63, 94, 0.15)`).
  - Recommended Upskilling: Amber badge with demand frequency badge (`+N jobs`).

---

## 5. Pre-Seeded Demonstration Dataset

The production database is pre-seeded with **300+ real, structured technology job postings** across key regions:
* **Europe (Dublin, London, Berlin, Amsterdam, Remote Europe)**:
  - Currencies: `EUR`, `GBP`.
  - Roles: Python Backend, Data Engineering, AI/ML, Cloud Infrastructure, Fullstack React.
* **Latin America (São Paulo, Rio de Janeiro, Remote Brazil)**:
  - Currencies: `BRL`, `USD`.
  - Extracted attributes: Normalized CLT / PJ contract modalities, standardized seniorities.
