# Gupy Job Scraper & AI Extractor

Backend application for scraping job postings from [Gupy](https://www.gupy.io/), storing the raw posts in PostgreSQL, and transforming them into a structured dataset through regex-based and LLM-assisted feature extraction.

This repository was created as a Continuous Assessment project for the **MSc in Artificial Intelligence** at **Dublin Business School**.

> 📄 **Project Report**: [`Rocha-20082900.pdf`](Rocha-20082900.pdf)
>
> Rocha, N.L. (2026). _Gupy Job Scraper & AI Extractor: A Data Acquisition and Preprocessing Pipeline_. MSc Artificial Intelligence, Dublin Business School. Student ID 20082900.

---

## Overview

The project is an ETL-style pipeline with three main stages:

1. **Acquire** — Scrape raw job posts from Gupy based on configurable search terms
2. **Store** — Persist raw posts in a relational PostgreSQL database
3. **Extract** — Transform descriptions into structured features (hard skills, soft skills, contract type, salary, seniority, location) using a regex engine or a local LLM via Ollama

The application exposes a Flask REST API, serves a dashboard UI from the same backend, and includes Swagger documentation for all available endpoints.

Initial exploratory work was done in Google Colab:
[Project notebook](https://colab.research.google.com/drive/1r7xoXbw376IM_KzP7bz2EyOBR_rpCuGz?usp=sharing)

## Features

- Background scraper with incremental mode to avoid re-fetching old posts
- Regex-based feature extraction for job descriptions (80+ technology patterns)
- LLM-based feature extraction using Ollama and Llama 3.1
- Normalized relational schema for jobs, companies, contract types, skills, cities, and states
- Paginated, filterable, and sortable API endpoints
- CSV export for raw posts and structured jobs
- Dashboard UI with analytics: top technologies, top locations, salary averages, seniority distribution, contract type breakdown, and technology trends over time
- Swagger UI for API exploration and manual testing
- Docker Compose setup with health checks and automatic migrations

## Tech Stack

| Layer           | Technologies          |
| --------------- | --------------------- |
| Language        | Python 3.12+          |
| Web framework   | Flask                 |
| ORM             | SQLAlchemy 2.0        |
| Migrations      | Alembic               |
| Database        | PostgreSQL 16         |
| API docs        | Flasgger (Swagger UI) |
| Data processing | Pandas, NumPy         |
| HTTP client     | Requests              |
| LLM integration | Ollama (Llama 3.1)    |
| Deployment      | Docker, Gunicorn      |
| Env management  | python-dotenv         |

## Repository Layout

```
├── app.py                    # Flask app with full Swagger annotations
├── app_hm.py                 # Flask app used by Docker (paginated endpoints)
├── database.py               # SQLAlchemy engine, session, and DB init
├── utils.py                  # Date parsing helpers and CSV header constants
├── swagger_config.py         # Flasgger / Swagger UI configuration
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Rocha-20082900.pdf        # Project report
│
├── entities/                 # ORM models
│   ├── base.py               # Declarative base
│   ├── job_post.py           # Raw scraped post
│   ├── job.py                # Processed/extracted job
│   ├── company.py
│   ├── city.py / state.py
│   ├── contract_type.py
│   ├── hard_skill.py / soft_skill.py / nice_to_have_skill.py
│   ├── search_term.py
│   ├── error_log.py
│   └── associations.py       # Many-to-many join tables
│
├── services/                 # Business logic
│   ├── scraper_service_hm.py # Gupy scraping with incremental pagination
│   ├── extractor_service.py  # Regex and LLM extraction orchestrator
│   ├── jobs_post_service_hm.py
│   ├── job_service_hm.py
│   ├── search_terms_service_hm.py
│   ├── features_service_hm.py  # Analytics queries
│   ├── stats_service.py
│   ├── error_service.py
│   └── csv_service.py
│
├── features_extractors/      # Extraction engines
│   ├── regex_extractor.py    # Regex patterns + skill normalization
│   ├── llm_extractor.py      # Ollama / Llama 3.1 integration
│   ├── bert_extractor.py     # BERT/NER experimental extractor
│   ├── fine_tune_prep.py     # NER fine-tuning data preparation
│   └── train_jobbert.py      # JobBERT fine-tuning script
│
├── frontend/                 # Static dashboard assets
│   ├── index.html
│   ├── script.js
│   ├── style.css
│   └── favicon.png
│
├── migrations/               # Alembic migration scripts
├── tests/                    # Unit and integration tests
└── ai-assistance/            # AI-assisted development logs
```

## Quick Start

There are two supported ways to run the project:

- **Docker Compose** — recommended for the fastest setup
- **Local Python environment** — useful for development and debugging

## Option 1: Run with Docker

The Docker setup includes:

- A PostgreSQL 16 container
- The Flask app served through Gunicorn
- Automatic wait-for-database startup handling
- Automatic `alembic upgrade head` on container boot
- Support for Azure-style `PORT` and external database configuration

### Start the stack

```bash
docker compose up --build
```

### Access the app

- Dashboard: [http://127.0.0.1:8080/dashboard](http://127.0.0.1:8080/dashboard)
- Swagger docs: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)
- Health check: [http://127.0.0.1:8080/health](http://127.0.0.1:8080/health)

### Stop the stack

```bash
docker compose down
```

To also remove the PostgreSQL volume and start fresh:

```bash
docker compose down -v
```

### Docker environment

The app container is started with these database settings:

```env
DB_HOST=db
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
```

For local Compose, `DB_HOST=db` works because `db` is the Postgres service name inside Docker networking.
That hostname will not work in Azure unless you actually deploy a database service with that exact name.

## Option 2: Run locally

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
DB_PORT=5432
DB_USER=your_postgres_user
DB_PASSWORD=your_password
DB_NAME=postgres
DB_HOST=your_database_host
```

You can also use a single `DATABASE_URL` instead of separate `DB_*` variables:

```env
DATABASE_URL=postgresql://username:password@hostname:5432/postgres
```

### 4. Apply migrations

```bash
alembic upgrade head
```

### 5. Start the application

```bash
python3 app_hm.py
```

The app will be available at [http://127.0.0.1:8080](http://127.0.0.1:8080).

## Typical Workflow

Once the app is running, a common end-to-end flow looks like this:

1. Open the dashboard or Swagger UI
2. Add one or more search terms
3. Start a scrape
4. Wait for the scraper status to return to idle
5. Trigger regex extraction (or LLM extraction if Ollama is running)
6. Review raw posts, structured jobs, metrics, and errors
7. Export CSVs if needed

## API Endpoints

### App and docs

| Method | Endpoint     | Description          |
| ------ | ------------ | -------------------- |
| `GET`  | `/health`    | Service health check |
| `GET`  | `/dashboard` | Dashboard UI         |
| `GET`  | `/docs`      | Swagger UI redirect  |

### Database and pipeline

| Method | Endpoint                | Description                            |
| ------ | ----------------------- | -------------------------------------- |
| `POST` | `/database/init`        | Create tables from SQLAlchemy metadata |
| `POST` | `/scrape/start`         | Start a background scrape              |
| `GET`  | `/scrape/status`        | Inspect scraper status                 |
| `POST` | `/regex-extract`        | Start regex feature extraction         |
| `GET`  | `/regex-extract/status` | Inspect regex extractor status         |
| `POST` | `/llm-extract`          | Start LLM feature extraction           |
| `GET`  | `/llm-extract/status`   | Inspect LLM extractor status           |

### Data

| Method | Endpoint          | Description                        |
| ------ | ----------------- | ---------------------------------- |
| `GET`  | `/job-posts`      | List raw scraped posts (paginated) |
| `GET`  | `/job-posts/<id>` | Get one raw post                   |
| `GET`  | `/jobs`           | List processed jobs (paginated)    |
| `GET`  | `/jobs/<id>`      | Get one processed job              |

### Search terms

| Method   | Endpoint             | Description                                |
| -------- | -------------------- | ------------------------------------------ |
| `GET`    | `/search-terms`      | List search terms (paginated)              |
| `POST`   | `/search-terms`      | Create a search term                       |
| `PUT`    | `/search-terms/<id>` | Update a search term (activate/deactivate) |
| `DELETE` | `/search-terms/<id>` | Delete a search term                       |

### Exports and analytics

| Method | Endpoint                           | Description                          |
| ------ | ---------------------------------- | ------------------------------------ |
| `GET`  | `/job-posts/export`                | Export raw posts as CSV              |
| `GET`  | `/jobs/export`                     | Export processed jobs as CSV         |
| `GET`  | `/stats`                           | Summary metric counts                |
| `GET`  | `/errors`                          | Recent logged errors (paginated)     |
| `GET`  | `/features/average-job-post-daily` | Average daily job post count         |
| `GET`  | `/features/top-technologies`       | Top technologies by job count        |
| `GET`  | `/features/top-locations`          | Top locations by job count           |
| `GET`  | `/features/average-salary`         | Average salary across processed jobs |
| `GET`  | `/features/jobs-by-contract-type`  | Jobs grouped by contract type        |
| `GET`  | `/features/jobs-by-seniority`      | Jobs grouped by seniority level      |
| `GET`  | `/features/technology-trends`      | Technology trend time-series         |

## Migrations

Alembic migration files live in `migrations/`.

Useful commands:

```bash
alembic upgrade head
alembic downgrade -1
alembic history
```

Note: the project still contains a `/database/init` endpoint that uses `Base.metadata.create_all(...)`. For consistent environments, prefer Alembic migrations where possible.

## Testing

Run the test suite with:

```bash
pytest -q
```

Tests use an **in-memory SQLite database** configured automatically via `conftest.py`, so no running PostgreSQL instance is required.

The test suite includes:

- **Unit tests** for the regex extractor (skill extraction, salary parsing, cleaning)
- **Unit tests** for utility functions (date/datetime parsing)
- **Integration tests** for Flask endpoints (health, search terms, job posts, scrape status)

If tests fail during import with a driver error, make sure all dependencies from `requirements.txt` are installed.

## Troubleshooting

### Docker container starts but app is unavailable

Check container logs:

```bash
docker compose logs app
docker compose logs db
```

### Azure deployment cannot resolve `db`

If Azure shows an error like `could not translate host name "db"`, the app is still pointing at the local Docker Compose hostname.

In Azure, set either:

```env
DATABASE_URL=postgresql://username:password@your-server.postgres.database.azure.com:5432/postgres
```

or:

```env
DB_HOST=your-server.postgres.database.azure.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=your_user
DB_PASSWORD=your_password
DB_SSLMODE=require
```

Azure often expects the app to bind using the `PORT` environment variable. The container now supports that automatically.

### Need a clean database reset

With Docker:

```bash
docker compose down -v
docker compose up --build
```

Locally, reset your target database manually and re-run:

```bash
alembic upgrade head
```

### Swagger UI does not load

The Docker container runs `app_hm.py`, which includes Swagger via an optional import. If Flasgger is not installed, Swagger UI will be silently disabled. Run `app.py` directly for guaranteed Swagger support.

## File Naming Convention

Files ending with `_hm` (e.g. `app_hm.py`, `scraper_service_hm.py`) were identified in the project as **human-authored** variants. Other parts of the codebase were developed with AI assistance and then reviewed and integrated into the final project. The `ai-assistance/` directory contains logs documenting the AI-assisted development process.

## Attribution

This project uses the following libraries and frameworks:

- [Python](https://docs.python.org/3/)
- [Flask](https://flask.palletsprojects.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Alembic](https://alembic.sqlalchemy.org/)
- [Flasgger](https://github.com/flasgger/flasgger)
- [Pandas](https://pandas.pydata.org/)
- [NumPy](https://numpy.org/)
- [Requests](https://requests.readthedocs.io/)
- [Gunicorn](https://gunicorn.org/)
- [Ollama](https://ollama.com/)

Regex expressions and scraping logic were developed as part of the project work.

## AI-Generated README & Code Audit

> **This README was generated by an AI assistant (Antigravity / Claude Opus 4.6)** based on a full audit of the codebase.
