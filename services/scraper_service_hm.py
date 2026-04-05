import requests
import math
from time import sleep
from random import randint
from datetime import datetime, UTC
from threading import Thread
from sqlalchemy import select
from database import SessionLocal
from entities.search_term import SearchTerm
from services.error_service import log_error
from services.jobs_post_service_hm import save_new_job_post
from services.search_terms_service_hm import get_search_terms

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

scrape_status = {
    "running": False,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}

def get_scrape_status():
    return scrape_status


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
            source = "scraper_service_hm.fetch_gupy_jobs_post",
            message = 'Request failed',
            term = term,
            page = page,
            request_limit = limit,
            payload = str(exc)
        )
        return None
def start_scrape():
    if (scrape_status['running']) :
        return
    search_terms = get_search_terms()
    scrape_status["running"] = True
    scrape_status["mode"] = "incremental"
    scrape_status["started_at"] = datetime.now(UTC).isoformat()
    for term in search_terms:
        print(f"Scraping for term: {term}")
        inserted = 0
        try: 
            response = fetch_gupy_page(term, 1)
            if response is None:
                break
            inserted += save_new_job_post(response['data'])
            if check_if_all_save(inserted):
                print(f"Inserted: {inserted} for {term}")
                continue
            max_pages = math.ceil(response['pagination']['total']/LIMIT)
            for page in range (2, max_pages + 1):
                response = fetch_gupy_page(term, page)
                if response is None:
                    break
                saved = save_new_job_post(response['data'])
                inserted += saved
                if check_if_all_save(saved):
                    print(f"Inserted: {inserted} for {term}")
                    break
                sleep(randint(5,20))  
        except Exception as exc:
            log_error(
                source = "scraper_service_hm.start_scrape",
                message = 'Error scraping jobs',
                term = term,
                page = page,
                request_limit = LIMIT,
                payload = str(exc)
            )
            print(exc)
            continue
    scrape_status["running"] = False
    scrape_status["finished_at"] = datetime.now(UTC).isoformat()

def start_scrape_thread():
    thread = Thread(target=start_scrape)
    thread.setDaemon(True)
    thread.start()

def check_if_all_save(inserted, limit=LIMIT):
    return inserted < limit

if __name__ == "__main__":
    start_scrape()