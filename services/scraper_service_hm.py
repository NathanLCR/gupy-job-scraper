import math
from datetime import UTC, datetime
from random import randint
from threading import Thread
from time import sleep
from typing import Any, Dict, Optional
import requests
from sqlalchemy import select

from database import SessionLocal
from entities.search_term import SearchTerm
from services.error_service import log_error
from services.ingestion.ingestion_manager import ingestion_manager
from services.jobs_post_service_hm import save_new_job_post
from services.search_terms_service_hm import get_search_terms, update_last_scraped_at

BASE_URL = "https://employability-portal.gupy.io/api/v1/jobs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
}
LIMIT = 20


def get_scrape_status() -> Dict[str, Any]:
    """Returns unified status from IngestionManager."""
    mgr_status = ingestion_manager.get_status()
    return {
        "running": mgr_status.get("running", False),
        "mode": "multi_source",
        "started_at": mgr_status.get("started_at"),
        "finished_at": mgr_status.get("finished_at"),
        "error": mgr_status.get("error"),
        "total_fetched": mgr_status.get("total_fetched", 0),
        "total_inserted": mgr_status.get("total_inserted", 0),
        "total_skipped": mgr_status.get("total_skipped", 0),
        "sources_stats": mgr_status.get("sources_stats", {}),
    }


def fetch_gupy_page(term: str, page: int, limit: int = LIMIT):
    params = {
        "jobName": term,
        "limit": limit,
        "offset": str((page * limit) - limit),
        "sortBy": "publishedDate",
        "sortOrder": "desc",
    }

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        log_error(
            source="scraper_service_hm.fetch_gupy_jobs_post",
            message="Request failed",
            term=term,
            page=page,
            request_limit=limit,
            payload=str(exc),
        )
        return None


def start_scrape(source: str = "all", limit: int = 50):
    """Triggers multi-source public job ingestion via IngestionManager."""
    return ingestion_manager.ingest(source=source, limit_per_source=limit, auto_extract=True)


def start_scrape_thread(source: str = "all", limit: int = 50):
    """Triggers asynchronous ingestion thread."""
    ingestion_manager.start_ingest_thread(source=source, limit_per_source=limit, auto_extract=True)

        