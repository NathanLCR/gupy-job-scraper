# Gupy Job Scraper & Extractor

Backend application for scraping job postings from Gupy, storing the raw posts in PostgreSQL, and transforming them into a structured dataset through regex-based feature extraction.

This repository was created as a Continuous Assessment project for the MSc in Artificial Intelligence at Dublin Business School.

## Overview

The project is an ETL-style pipeline with three main stages:

1. Acquire raw job posts from Gupy based on configured search terms
2. Store those posts in a relational PostgreSQL database
3. Extract structured features such as hard skills, soft skills, contract type, salary, and location into normalized tables

The application exposes a Flask API, serves a dashboard UI from the same backend, and includes Swagger documentation for the available endpoints.

Initial exploratory work was done in Colab:
[Project notebook](https://colab.research.google.com/drive/1r7xoXbw376IM_KzP7bz2EyOBR_rpCuGz?usp=sharing)

## Features

- Background scraper for fetching job posts without blocking the API
- Regex-based feature extraction for job descriptions
- Normalized relational schema for jobs, companies, contract types, skills, cities, and states
- CSV export for raw posts and structured jobs
- Dashboard UI for monitoring scrape and extractor status
- Swagger UI for API exploration and manual testing

## Tech Stack

- Python 3.12+
- Flask
- SQLAlchemy
- Alembic
- PostgreSQL
- Flasgger
- Pandas
- NumPy

## Repository Layout

- `app.py`: Swagger-enabled Flask app entrypoint
- `app_hm.py`: Flask app entrypoint used by the Docker container
- `database.py`: SQLAlchemy engine, session, and database initialization
- `entities/`: ORM models
- `services/`: business logic for scraping, extraction, exports, errors, and stats
- `features_extractors/`: regex and model-assisted extraction utilities
- `frontend/`: static dashboard assets
- `migrations/`: Alembic migration scripts
- `tests/`: unit and integration tests

## Quick Start

There are two supported ways to run the project:

- Docker Compose: recommended for the fastest setup
- Local Python environment: useful for development and debugging

## Option 1: Run with Docker

The Docker setup includes:

- a PostgreSQL container
- the Flask app served through `gunicorn`
- automatic wait-for-database startup handling
- automatic `alembic upgrade head` on container boot
- support for Azure-style `PORT` and external database configuration

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
5. Trigger regex extraction
6. Review raw posts, structured jobs, metrics, and errors
7. Export CSVs if needed

## Main Endpoints

### App and docs

- `GET /health`: service health
- `GET /dashboard`: dashboard UI
- `GET /docs`: Swagger UI

### Database and pipeline

- `POST /database/init`: create tables directly from SQLAlchemy metadata
- `POST /scrape/start`: start a background scrape
- `GET /scrape/status`: inspect scraper status
- `POST /regex-extract`: start regex feature extraction
- `GET /regex-extract/status`: inspect extractor status

### Data

- `GET /job-posts`: list raw scraped posts
- `GET /job-posts/<id>`: get one raw post
- `GET /jobs`: list processed jobs
- `GET /jobs/<id>`: get one processed job

### Search terms

- `GET /search-terms`: list search terms
- `POST /search-terms`: create a search term
- `PUT /search-terms/<id>`: deactivate a search term

### Exports and stats

- `GET /job-posts/export`: export raw posts as CSV
- `GET /jobs/export`: export processed jobs as CSV
- `GET /stats`: summary metrics
- `GET /errors`: recent logged errors
- `GET /features/average-job-post-daily`
- `GET /features/top-5-technologies`
- `GET /features/top-5-locations`
- `GET /features/average-salary`
- `GET /features/jobs-by-contract-type`

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

If tests fail during import with a PostgreSQL driver or database configuration error, make sure:

- dependencies from `requirements.txt` are installed
- `psycopg2-binary` is available
- your database environment variables are set correctly

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

The Docker container runs `app_hm.py`, which does not include the Swagger setup. If you need Swagger locally, run `app.py` instead.

## Notes

- Files ending with `hm` were identified in the project as human-authored variants
- Other parts of the repository were developed with AI assistance and later integrated into the final project

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

Regex expressions and scraping logic were developed as part of the project work.
