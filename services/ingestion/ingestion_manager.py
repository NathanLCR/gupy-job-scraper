"""
SkillPulse AI - Multi-Source Ingestion Manager & Orchestrator.
Coordinates job scraping across public and multi-region job feeds (Arbeitnow, Remotive, Jobicy, Himalayas, RemoteOK, Gupy),
handles deduplication by ID and SHA-256 fingerprint, tracks real-time progress metrics,
and triggers the downstream multi-tier AI extraction cascade.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from threading import Lock, Thread
from typing import Any, Dict, List, Optional
from sqlalchemy import select

from database import SessionLocal, init_db
from entities import JobPost, SearchTerm
from services.error_service import log_error
from services.ingestion.arbeitnow_adapter import ArbeitnowAdapter
from services.ingestion.base_adapter import BaseIngestionAdapter
from services.ingestion.gupy_adapter import GupyAdapter
from services.ingestion.himalayas_adapter import HimalayasAdapter
from services.ingestion.jobicy_adapter import JobicyAdapter
from services.ingestion.remoteok_adapter import RemoteOKAdapter
from services.ingestion.remotive_adapter import RemotiveAdapter

logger = logging.getLogger(__name__)


class IngestionManager:
    """Central orchestrator for multi-source public job ingestion."""

    def __init__(self):
        self._lock = Lock()
        self._adapters: Dict[str, BaseIngestionAdapter] = {}
        self._register_default_adapters()
        self._status: Dict[str, Any] = {
            "running": False,
            "source": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "total_fetched": 0,
            "total_inserted": 0,
            "total_skipped": 0,
            "sources_stats": {},
        }

    def _register_default_adapters(self) -> None:
        """Register built-in public job feed adapters."""
        self.register_adapter(ArbeitnowAdapter())
        self.register_adapter(RemotiveAdapter())
        self.register_adapter(JobicyAdapter())
        self.register_adapter(HimalayasAdapter())
        self.register_adapter(RemoteOKAdapter())
        self.register_adapter(GupyAdapter())

    def register_adapter(self, adapter: BaseIngestionAdapter) -> None:
        self._adapters[adapter.source_name] = adapter

    def get_adapter(self, name: str) -> Optional[BaseIngestionAdapter]:
        return self._adapters.get(name)

    def get_available_sources(self) -> List[Dict[str, Any]]:
        """Returns metadata for all available ingestion adapters."""
        return [
            {
                "id": name,
                "name": adapter.display_name,
                "description": adapter.description,
                "region": adapter.default_region,
                "country_code": adapter.default_country,
                "currency": adapter.default_currency,
                "endpoint": adapter.endpoint_url,
                "is_active": True,
                "supports_terms": adapter.supports_search_terms,
            }
            for name, adapter in self._adapters.items()
        ]

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def _get_active_terms(self, db) -> List[str]:
        terms = db.scalars(
            select(SearchTerm.term)
            .where(SearchTerm.is_active.is_(True))
            .order_by(SearchTerm.id.asc())
        ).all()
        if terms:
            return list(terms)
        return [
            "Software Engineer",
            "Python",
            "Data Engineer",
            "React",
            "DevOps",
            "Backend",
            "Machine Learning",
            "Full Stack",
        ]

    def ingest(
        self,
        source: str = "all",
        terms: Optional[List[str]] = None,
        max_pages_per_source: int = 1,
        limit_per_source: int = 50,
        auto_extract: bool = True,
    ) -> Dict[str, Any]:
        """
        Synchronous ingestion execution across specified or all sources.
        Saves new records to jobs_posts and deduplicates against DB.
        """
        with self._lock:
            if self._status["running"]:
                return {"status": "already_running", "message": "Ingestion is already running"}

            init_db()
            self._status["running"] = True
            self._status["source"] = source
            self._status["started_at"] = datetime.now(UTC).isoformat()
            self._status["finished_at"] = None
            self._status["error"] = None
            self._status["total_fetched"] = 0
            self._status["total_inserted"] = 0
            self._status["total_skipped"] = 0
            self._status["sources_stats"] = {}

        db = SessionLocal()
        total_inserted = 0
        total_fetched = 0
        total_skipped = 0

        try:
            # Query existing IDs and fingerprints for deduplication
            existing_ids = set(db.scalars(select(JobPost.id)).all())
            existing_fingerprints = set(
                fp for fp in db.scalars(select(JobPost.fingerprint)).all() if fp
            )

            # Determine target adapters
            if source == "all":
                target_adapters = list(self._adapters.values())
            elif source in self._adapters:
                target_adapters = [self._adapters[source]]
            else:
                target_adapters = list(self._adapters.values())

            # Determine search terms
            active_terms = terms if terms else self._get_active_terms(db)

            for adapter in target_adapters:
                src_name = adapter.source_name
                self._status["sources_stats"][src_name] = {
                    "fetched": 0,
                    "inserted": 0,
                    "skipped": 0,
                    "status": "running",
                }

                try:
                    logger.info(f"Ingesting from source: {adapter.display_name}")
                    normalized_jobs = adapter.scrape(
                        terms=active_terms,
                        max_pages=max_pages_per_source,
                        limit_per_page=limit_per_source,
                    )

                    src_fetched = len(normalized_jobs)
                    src_inserted = 0
                    src_skipped = 0

                    for job_dict in normalized_jobs:
                        job_id = job_dict.get("id")
                        fp = job_dict.get("fingerprint")

                        if job_id is None or job_id in existing_ids:
                            src_skipped += 1
                            continue
                        if fp and fp in existing_fingerprints:
                            src_skipped += 1
                            continue

                        # Instantiate JobPost entity
                        post = JobPost(
                            id=job_id,
                            source=job_dict.get("source", src_name),
                            company_id=job_dict.get("company_id"),
                            name=job_dict.get("name", "")[:255],
                            description=job_dict.get("description"),
                            career_page_id=job_dict.get("career_page_id"),
                            career_page_name=(job_dict.get("career_page_name") or "")[:255],
                            career_page_logo=job_dict.get("career_page_logo"),
                            career_page_url=job_dict.get("career_page_url"),
                            job_type=job_dict.get("job_type"),
                            published_date=job_dict.get("published_date"),
                            application_deadline=job_dict.get("application_deadline"),
                            is_remote_work=job_dict.get("is_remote_work"),
                            city=job_dict.get("city"),
                            state=job_dict.get("state"),
                            country=job_dict.get("country"),
                            job_url=job_dict.get("job_url"),
                            workplace_type=job_dict.get("workplace_type"),
                            disabilities=job_dict.get("disabilities"),
                            skills=job_dict.get("skills"),
                            badges=job_dict.get("badges"),
                            region=job_dict.get("region") or adapter.default_region,
                            country_code=job_dict.get("country_code") or adapter.default_country,
                            currency=job_dict.get("currency") or adapter.default_currency,
                            fingerprint=fp,
                        )

                        try:
                            with db.begin_nested():
                                db.add(post)
                                db.flush()
                            existing_ids.add(job_id)
                            if fp:
                                existing_fingerprints.add(fp)
                            src_inserted += 1
                        except Exception:
                            src_skipped += 1

                    db.commit()

                    self._status["sources_stats"][src_name] = {
                        "fetched": src_fetched,
                        "inserted": src_inserted,
                        "skipped": src_skipped,
                        "status": "completed",
                    }
                    total_fetched += src_fetched
                    total_inserted += src_inserted
                    total_skipped += src_skipped

                except Exception as src_err:
                    logger.error(f"Error scraping source {src_name}: {src_err}")
                    log_error(
                        f"Error in adapter {src_name}: {src_err}",
                        source=f"ingestion.{src_name}",
                        payload=str(src_err),
                    )
                    self._status["sources_stats"][src_name] = {
                        "fetched": 0,
                        "inserted": 0,
                        "skipped": 0,
                        "status": f"failed: {src_err}",
                    }

            self._status["total_fetched"] = total_fetched
            self._status["total_inserted"] = total_inserted
            self._status["total_skipped"] = total_skipped

            # Update search terms last_scraped_at timestamp
            try:
                now_dt = datetime.now(UTC)
                query_st = db.query(SearchTerm).filter(SearchTerm.is_active.is_(True))
                if active_terms:
                    query_st = query_st.filter(SearchTerm.term.in_(active_terms))
                for st in query_st.all():
                    st.last_scraped_at = now_dt
                db.commit()
            except Exception:
                pass

            # Trigger AI extraction cascade if requested and new jobs were inserted
            if auto_extract and total_inserted > 0:
                try:
                    from services.extractor_service import start_extractor_thread
                    start_extractor_thread("cascade", limit=total_inserted + 50)
                except Exception as ext_err:
                    logger.warning(f"Could not auto-trigger extraction cascade: {ext_err}")

            return {
                "status": "completed",
                "total_fetched": total_fetched,
                "total_inserted": total_inserted,
                "total_skipped": total_skipped,
                "sources_stats": self._status["sources_stats"],
            }

        except Exception as exc:
            with self._lock:
                self._status["error"] = str(exc)
            log_error(f"Ingestion crashed: {exc}", source="ingestion_manager", payload=str(exc))
            return {"status": "error", "error": str(exc)}
        finally:
            with self._lock:
                self._status["running"] = False
                self._status["finished_at"] = datetime.now(UTC).isoformat()
            db.close()

    def start_ingest_thread(
        self,
        source: str = "all",
        terms: Optional[List[str]] = None,
        max_pages_per_source: int = 1,
        limit_per_source: int = 50,
        auto_extract: bool = True,
    ) -> None:
        """Launches ingestion asynchronously in a background daemon thread."""
        thread = Thread(
            target=self.ingest,
            kwargs={
                "source": source,
                "terms": terms,
                "max_pages_per_source": max_pages_per_source,
                "limit_per_source": limit_per_source,
                "auto_extract": auto_extract,
            },
            daemon=True,
        )
        thread.start()


# Global singleton instance
ingestion_manager = IngestionManager()
