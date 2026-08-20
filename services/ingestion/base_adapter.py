"""
SkillPulse AI - Base Ingestion Adapter.
Abstract base class for all public and multi-region job feed adapters.
Provides standardized normalization, HTML cleaning, fingerprinting, and deterministic ID generation.
"""

from __future__ import annotations

import abc
import hashlib
import html
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
import requests
from utils import parse_datetime, parse_date


class BaseIngestionAdapter(abc.ABC):
    """Abstract base class for job ingestion adapters."""

    source_name: str = "base"
    display_name: str = "Base Adapter"
    description: str = "Base Ingestion Adapter"
    default_region: str = "Global"
    default_country: str = "WW"
    default_currency: str = "USD"
    endpoint_url: str = ""
    supports_search_terms: bool = True

    DEFAULT_HEADERS: Dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 SkillPulseAI/1.0"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
    }

    FETCH_TIMEOUT: int = 25

    @abc.abstractmethod
    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch raw job items from the public endpoint.
        Returns a list of raw job dicts from the provider.
        """
        pass

    @abc.abstractmethod
    def normalize_job(
        self,
        raw_item: Dict[str, Any],
        term: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Normalize a raw provider job item into standard JobPost dictionary schema:
        {
            "id": int,
            "source": str,
            "company_id": Optional[int],
            "name": str,
            "description": Optional[str],
            "career_page_id": Optional[int],
            "career_page_name": Optional[str],
            "career_page_logo": Optional[str],
            "career_page_url": Optional[str],
            "job_type": Optional[str],
            "published_date": Optional[datetime],
            "application_deadline": Optional[date],
            "is_remote_work": Optional[bool],
            "city": Optional[str],
            "state": Optional[str],
            "country": Optional[str],
            "job_url": Optional[str],
            "workplace_type": Optional[str],
            "disabilities": Optional[bool],
            "skills": Optional[str],
            "badges": Optional[str],
            "region": str,
            "country_code": str,
            "currency": str,
            "fingerprint": str,
        }
        """
        pass

    def scrape(
        self,
        terms: Optional[List[str]] = None,
        max_pages: int = 1,
        limit_per_page: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Scrapes jobs across given search terms (or a single run if terms are not supported).
        Returns a list of normalized job dictionaries.
        """
        normalized_jobs: List[Dict[str, Any]] = []
        seen_fingerprints: set[str] = set()

        if self.supports_search_terms and terms:
            active_terms = terms
        else:
            active_terms = [None]

        for term in active_terms:
            for page in range(1, max_pages + 1):
                try:
                    raw_items = self.fetch_jobs(term=term, page=page, limit=limit_per_page)
                    if not raw_items:
                        break

                    for item in raw_items:
                        try:
                            norm = self.normalize_job(item, term=term)
                            if not norm or not norm.get("name"):
                                continue

                            fp = norm.get("fingerprint")
                            if fp and fp in seen_fingerprints:
                                continue
                            if fp:
                                seen_fingerprints.add(fp)

                            normalized_jobs.append(norm)
                        except Exception as item_err:
                            continue
                except Exception as page_err:
                    break

        return normalized_jobs

    @staticmethod
    def clean_html(raw_html: Optional[str]) -> str:
        """Strips HTML tags, decodes HTML entities, and removes excess whitespace."""
        if not raw_html:
            return ""
        # Unescape HTML entities
        text = html.unescape(raw_html)
        # Normalize non-breaking spaces
        text = text.replace("\xa0", " ")
        # Replace line breaks and block elements with newlines
        text = re.sub(r"<(?:br|p|div|li|h\d)[^>]*>", "\n", text, flags=re.I)
        # Strip all other HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Normalize multiple spaces and multiple newlines
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()

    @staticmethod
    def generate_fingerprint(
        company: Optional[str],
        title: Optional[str],
        location: Optional[str] = None,
    ) -> str:
        """
        Generates a SHA-256 fingerprint for deduplication based on
        normalized company name, job title, and location.
        """
        norm_company = re.sub(r"[^\w\s]", "", (company or "").lower().strip())
        norm_title = re.sub(r"[^\w\s]", "", (title or "").lower().strip())
        norm_loc = re.sub(r"[^\w\s]", "", (location or "").lower().strip())
        raw_key = f"{norm_company}|{norm_title}|{norm_loc}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_job_id(
        source: str,
        external_id: Any,
        fingerprint: Optional[str] = None,
    ) -> int:
        """
        Generates a unique, deterministic 63-bit positive integer ID.
        Preserves original Gupy integer IDs when valid to ensure backward compatibility.
        """
        if source == "gupy" and external_id is not None:
            try:
                val = int(external_id)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass

        raw_id_str = f"{source}:{str(external_id or fingerprint or '')}"
        digest = hashlib.sha256(raw_id_str.encode("utf-8")).digest()
        # Big-endian 8 bytes masked with 0x7FFFFFFFFFFFFFFF to ensure positive 63-bit integer
        return int.from_bytes(digest[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF
