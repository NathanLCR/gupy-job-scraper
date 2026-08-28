# SkillPulse AI — Deployment Guide: 100% Free Cloud & Cloudflare
**Step-by-Step Production Setup for Cloudflare Pages, FastAPI Backend, and Neon Serverless pgvector**

## 1. Architecture & Free Tier Stack

```
                          ┌──────────────────────────────────────────────┐
                          │   Cloudflare Pages (Frontend Dashboard)     │
                          │   https://skillpulse.pages.dev               │
                          └──────────────────────┬───────────────────────┘
                                                 │ HTTPS REST (CORS)
                                                 ▼
                          ┌──────────────────────────────────────────────┐
                          │   Render / Hugging Face Spaces (FastAPI)     │
                          │   https://skillpulse-api.onrender.com        │
                          └──────────────────────┬───────────────────────┘
                                                 │ PostgreSQL + pgvector (SSL)
                                                 ▼
                          ┌──────────────────────────────────────────────┐
                          │   Neon Serverless PostgreSQL (`pgvector`)    │
                          │   ep-xyz.region.aws.neon.tech                │
                          └──────────────────────────────────────────────┘
```

---

## 2. Step 1: Database Setup on Neon (Free Tier)

1. Sign up at [neon.tech](https://neon.tech) (Free tier, no credit card required).
2. Create a new project: `skillpulse-db`.
3. In the Neon SQL Editor, enable the `vector` extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
4. Copy the connection string (with pooled connection):
   `postgresql://username:password@ep-xyz.region.aws.neon.tech/neondb?sslmode=require`

---

## 3. Step 2: Backend Deployment on Render (Free Web Service)

1. Fork or push the cleaned repository to your GitHub account (`github.com/NathanLCR/skillpulse-ai`).
2. Log in to [render.com](https://render.com) and create a **New Web Service**:
   - **Repository**: Connect your GitHub repository.
   - **Environment**: Python 3.12 (or Docker).
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free (0.1 CPU, 512 MB RAM).
3. Set the Environment Variables in the Render Dashboard:
   | Variable | Value |
   | :--- | :--- |
   | `DATABASE_URL` | `postgresql://username:password@ep-xyz.neon.tech/neondb?sslmode=require` |
   | `GROQ_API_KEY` | `${YOUR_GROQ_API_KEY}` |
   | `GROQ_MODEL` | `llama-3.3-70b-versatile` |
   | `OPENROUTER_API_KEY` | `${YOUR_OPENROUTER_API_KEY}` |
   | `OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` |
   | `CORS_ORIGINS` | `["https://skillpulse.pages.dev", "http://localhost:8000"]` |
   | `ENVIRONMENT` | `production` |
4. Deploy service and note down your backend URL (e.g. `https://skillpulse-api.onrender.com`).

---

## 4. Step 3: Frontend Deployment on Cloudflare Pages

1. Log in to your [Cloudflare Dashboard](https://dash.cloudflare.com/) and navigate to **Workers & Pages** $\to$ **Create Application** $\to$ **Pages**.
2. Connect your GitHub repository.
3. Configure the build settings:
   - **Framework preset**: None (Static HTML/JS).
   - **Build command**: Leave empty.
   - **Build output directory**: `frontend`
4. Set Environment Variables (optional, for custom API URLs):
   - `VITE_API_BASE_URL` or set `window.API_BASE_URL = "https://skillpulse-api.onrender.com"` in `frontend/script.js`.
5. Click **Save and Deploy**. Cloudflare will provide a global live URL: `https://skillpulse.pages.dev`.

---

## 5. Step 4: Verification & Smoke Testing
- Visit `https://skillpulse.pages.dev`.
- Verify the **Top 10 Technologies** and **Seniority Distribution** charts load from the backend.
- Navigate to the **Candidate Matcher** tab and click **"Try Senior Cloud Architect"**.
- Confirm that the composite fit score, green matched badges, red gap badges, and ranked jobs render in $< 500\text{ms}$.
