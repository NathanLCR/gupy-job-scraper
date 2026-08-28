"""
SkillPulse AI - Remotive Ingestion Adapter (Global Remote Tech / Software Dev / Data).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import requests

from services.ingestion.base_adapter import BaseIngestionAdapter
from utils import parse_datetime


class RemotiveAdapter(BaseIngestionAdapter):
    """Adapter for Remotive API (Global remote developer, data, devops, and tech roles)."""

    source_name: str = "remotive"
    display_name: str = "Remotive (Global Remote)"
    description: str = "Curated global remote software engineering, data science, and DevOps jobs"
    default_region: str = "Global"
    default_country: str = "US"
    default_currency: str = "USD"
    endpoint_url: str = "https://remotive.com/api/remote-jobs"
    supports_search_terms: bool = True

    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        if term:
            params["search"] = term

        try:
            resp = requests.get(
                self.endpoint_url,
                params=params,
                headers=self.DEFAULT_HEADERS,
                timeout=self.FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            jobs = payload.get("jobs", [])
            if isinstance(jobs, list):
                return jobs[:limit]
            return []
        except Exception:
            return []

    def normalize_job(
        self,
        raw_item: Dict[str, Any],
        term: Optional[str] = None,
    ) -> Dict[str, Any]:
        company_name = (raw_item.get("company_name") or "Remotive Partner").strip()
        title = (raw_item.get("title") or "").strip()
        cand_loc = (raw_item.get("candidate_required_location") or "Worldwide").strip()

        fingerprint = self.generate_fingerprint(company_name, title, cand_loc)
        job_id = self.generate_job_id(self.source_name, raw_item.get("id"), fingerprint)

        description = self.clean_html(raw_item.get("description"))

        # Map region / country from candidate location
        loc_lower = cand_loc.lower()
        region = self.default_region
        country_code = self.default_country
        currency = self.default_currency

        if any(k in loc_lower for k in ("usa", "us only", "north america", "united states", "canada")):
            region = "North America"
            country_code = "US"
            currency = "USD"
        elif any(k in loc_lower for k in ("uk", "united kingdom", "london")):
            region = "Europe"
            country_code = "GB"
            currency = "GBP"
        elif any(k in loc_lower for k in ("europe", "eu", "germany", "ireland", "france", "netherlands")):
            region = "Europe"
            country_code = "EU"
            currency = "EUR"
        elif any(k in loc_lower for k in ("latam", "latin america", "brazil", "brasil")):
            region = "Latin America"
            country_code = "BR"
            currency = "USD"
        elif "worldwide" in loc_lower or "anywhere" in loc_lower:
            region = "Global"
            country_code = "WW"

        # Tags & category to skills
        tags = list(raw_item.get("tags") or [])
        category = raw_item.get("category")
        if category and category not in tags:
            tags.append(category)

        skills_json = json.dumps(tags, ensure_ascii=False) if tags else None

        salary_text = raw_item.get("salary")
        badges = [f"Salary: {salary_text}"] if salary_text else []
        badges_json = json.dumps(badges, ensure_ascii=False) if badges else None

        return {
            "id": job_id,
            "source": self.source_name,
            "company_id": None,
            "name": title,
            "description": description,
            "career_page_id": None,
            "career_page_name": company_name,
            "career_page_logo": raw_item.get("company_logo"),
            "career_page_url": None,
            "job_type": raw_item.get("job_type", "Full-time"),
            "published_date": parse_datetime(raw_item.get("publication_date")),
            "application_deadline": None,
            "is_remote_work": True,
            "city": None,
            "state": None,
            "country": cand_loc,
            "job_url": raw_item.get("url"),
            "workplace_type": "REMOTE",
            "disabilities": None,
            "skills": skills_json,
            "badges": badges_json,
            "region": region,
            "country_code": country_code,
            "currency": currency,
            "fingerprint": fingerprint,
        }
