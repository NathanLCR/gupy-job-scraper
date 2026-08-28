"""
SkillPulse AI - Arbeitnow Ingestion Adapter (Europe / UK / Worldwide Remote).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
import requests

from services.ingestion.base_adapter import BaseIngestionAdapter
from utils import parse_datetime


class ArbeitnowAdapter(BaseIngestionAdapter):
    """Adapter for Arbeitnow Job Board API (Europe, UK, and Worldwide remote tech)."""

    source_name: str = "arbeitnow"
    display_name: str = "Arbeitnow (Europe & Remote)"
    description: str = "European tech jobs (Germany, UK, Ireland, EU) and global remote roles"
    default_region: str = "Europe"
    default_country: str = "DE"
    default_currency: str = "EUR"
    endpoint_url: str = "https://www.arbeitnow.com/api/job-board-api"
    supports_search_terms: bool = True

    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params = {"page": page}
        try:
            resp = requests.get(
                self.endpoint_url,
                params=params,
                headers=self.DEFAULT_HEADERS,
                timeout=self.FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            items = payload.get("data", [])
            if not isinstance(items, list):
                return []

            # If a search term is specified, perform client-side keyword filtering
            if term:
                term_lower = term.lower()
                filtered = []
                for j in items:
                    title_match = term_lower in (j.get("title") or "").lower()
                    desc_match = term_lower in (j.get("description") or "").lower()
                    tag_match = any(term_lower in str(t).lower() for t in (j.get("tags") or []))
                    if title_match or desc_match or tag_match:
                        filtered.append(j)
                return filtered[:limit]

            return items[:limit]
        except Exception:
            return []

    def normalize_job(
        self,
        raw_item: Dict[str, Any],
        term: Optional[str] = None,
    ) -> Dict[str, Any]:
        company_name = (raw_item.get("company_name") or "Arbeitnow Partner").strip()
        title = (raw_item.get("title") or "").strip()
        location_raw = (raw_item.get("location") or "").strip()
        slug = raw_item.get("slug") or raw_item.get("url")

        fingerprint = self.generate_fingerprint(company_name, title, location_raw)
        job_id = self.generate_job_id(self.source_name, slug, fingerprint)

        description = self.clean_html(raw_item.get("description"))

        # Parse location details
        city = None
        state = None
        country = None
        country_code = self.default_country
        region = self.default_region
        currency = self.default_currency

        if location_raw:
            loc_lower = location_raw.lower()
            if "," in location_raw:
                parts = [p.strip() for p in location_raw.split(",")]
                city = parts[0]
                country = parts[-1]
            else:
                city = location_raw

            if any(k in loc_lower for k in ("uk", "united kingdom", "london", "manchester", "scotland", "england")):
                country = "United Kingdom"
                country_code = "GB"
                currency = "GBP"
                region = "Europe"
            elif any(k in loc_lower for k in ("germany", "deutschland", "berlin", "munich", "hamburg", "frankfurt", "cologne")):
                country = "Germany"
                country_code = "DE"
                currency = "EUR"
                region = "Europe"
            elif any(k in loc_lower for k in ("ireland", "dublin", "cork", "galway")):
                country = "Ireland"
                country_code = "IE"
                currency = "EUR"
                region = "Europe"
            elif any(k in loc_lower for k in ("netherlands", "amsterdam", "rotterdam")):
                country = "Netherlands"
                country_code = "NL"
                currency = "EUR"
                region = "Europe"
            elif any(k in loc_lower for k in ("usa", "united states", "san francisco", "new york", "austin")):
                country = "United States"
                country_code = "US"
                currency = "USD"
                region = "North America"
            elif "remote" in loc_lower or "worldwide" in loc_lower or "anywhere" in loc_lower:
                region = "Global"
                country_code = "WW"

        is_remote = bool(raw_item.get("remote"))
        wp_type = "REMOTE" if is_remote else "ONSITE"

        # Published date parsing (epoch or iso string)
        pub_val = raw_item.get("created_at")
        published_dt = None
        if isinstance(pub_val, (int, float)):
            published_dt = datetime.fromtimestamp(pub_val, tz=UTC).replace(tzinfo=None)
        elif isinstance(pub_val, str):
            published_dt = parse_datetime(pub_val)

        # Tags to skills JSON
        tags = raw_item.get("tags") or []
        skills_json = json.dumps(tags, ensure_ascii=False) if tags else None

        job_types = raw_item.get("job_types") or []
        job_type_str = job_types[0] if isinstance(job_types, list) and job_types else str(job_types or "Full Time")

        return {
            "id": job_id,
            "source": self.source_name,
            "company_id": None,
            "name": title,
            "description": description,
            "career_page_id": None,
            "career_page_name": company_name,
            "career_page_logo": None,
            "career_page_url": None,
            "job_type": job_type_str,
            "published_date": published_dt,
            "application_deadline": None,
            "is_remote_work": is_remote,
            "city": city,
            "state": state,
            "country": country,
            "job_url": raw_item.get("url"),
            "workplace_type": wp_type,
            "disabilities": None,
            "skills": skills_json,
            "badges": None,
            "region": region,
            "country_code": country_code,
            "currency": currency,
            "fingerprint": fingerprint,
        }
