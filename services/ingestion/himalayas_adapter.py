"""
SkillPulse AI - Himalayas Ingestion Adapter (Global Remote Engineering & Data).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import requests

from services.ingestion.base_adapter import BaseIngestionAdapter
from utils import parse_datetime, parse_date


class HimalayasAdapter(BaseIngestionAdapter):
    """Adapter for Himalayas Remote Jobs Public API."""

    source_name: str = "himalayas"
    display_name: str = "Himalayas (Remote Tech)"
    description: str = "Global remote engineering, devops, and data science positions"
    default_region: str = "Global"
    default_country: str = "US"
    default_currency: str = "USD"
    endpoint_url: str = "https://himalayas.app/jobs/api"
    supports_search_terms: bool = True

    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        offset = (page - 1) * limit
        params = {"limit": min(limit, 50), "offset": offset}

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
            if not isinstance(jobs, list):
                return []

            if term:
                term_lower = term.lower()
                filtered = []
                for j in jobs:
                    title_match = term_lower in (j.get("title") or "").lower()
                    desc_match = term_lower in (j.get("description") or "").lower()
                    cat_match = any(term_lower in str(c).lower() for c in (j.get("categories") or []))
                    if title_match or desc_match or cat_match:
                        filtered.append(j)
                return filtered[:limit]

            return jobs[:limit]
        except Exception:
            return []

    def normalize_job(
        self,
        raw_item: Dict[str, Any],
        term: Optional[str] = None,
    ) -> Dict[str, Any]:
        company_name = (raw_item.get("companyName") or "Himalayas Partner").strip()
        title = (raw_item.get("title") or "").strip()
        guid = raw_item.get("guid") or raw_item.get("applicationLink")

        location_restrictions = raw_item.get("locationRestrictions") or ["Worldwide"]
        loc_str = ", ".join(location_restrictions) if isinstance(location_restrictions, list) else str(location_restrictions)

        fingerprint = self.generate_fingerprint(company_name, title, loc_str)
        job_id = self.generate_job_id(self.source_name, guid, fingerprint)

        description = self.clean_html(raw_item.get("description"))

        # Map region / country
        region = self.default_region
        country_code = self.default_country
        currency = raw_item.get("currency") or self.default_currency
        loc_lower = loc_str.lower()

        if any(k in loc_lower for k in ("usa", "united states", "north america")):
            region = "North America"
            country_code = "US"
        elif any(k in loc_lower for k in ("uk", "united kingdom")):
            region = "Europe"
            country_code = "GB"
        elif any(k in loc_lower for k in ("europe", "eu", "germany", "ireland")):
            region = "Europe"
            country_code = "EU"
        elif "worldwide" in loc_lower or "anywhere" in loc_lower:
            region = "Global"
            country_code = "WW"

        categories = list(raw_item.get("categories") or [])
        seniorities = raw_item.get("seniority") or []
        if isinstance(seniorities, list):
            categories.extend(seniorities)
        elif isinstance(seniorities, str):
            categories.append(seniorities)

        skills_json = json.dumps(categories, ensure_ascii=False) if categories else None

        badges = []
        min_sal = raw_item.get("minSalary")
        max_sal = raw_item.get("maxSalary")
        if min_sal and max_sal:
            badges.append(f"Salary: {min_sal:,.0f} - {max_sal:,.0f} {currency}")
        elif min_sal:
            badges.append(f"Salary: from {min_sal:,.0f} {currency}")

        badges_json = json.dumps(badges, ensure_ascii=False) if badges else None

        return {
            "id": job_id,
            "source": self.source_name,
            "company_id": None,
            "name": title,
            "description": description,
            "career_page_id": None,
            "career_page_name": company_name,
            "career_page_logo": raw_item.get("companyLogo"),
            "career_page_url": None,
            "job_type": raw_item.get("employmentType", "Full-time"),
            "published_date": parse_datetime(raw_item.get("pubDate")),
            "application_deadline": parse_date(raw_item.get("expiryDate")),
            "is_remote_work": True,
            "city": None,
            "state": None,
            "country": loc_str,
            "job_url": raw_item.get("applicationLink"),
            "workplace_type": "REMOTE",
            "disabilities": None,
            "skills": skills_json,
            "badges": badges_json,
            "region": region,
            "country_code": country_code,
            "currency": currency,
            "fingerprint": fingerprint,
        }
