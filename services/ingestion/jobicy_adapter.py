"""
SkillPulse AI - Jobicy Ingestion Adapter (Global Remote Engineering / Data / Tech).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import requests

from services.ingestion.base_adapter import BaseIngestionAdapter
from utils import parse_datetime


class JobicyAdapter(BaseIngestionAdapter):
    """Adapter for Jobicy Public Remote Jobs API."""

    source_name: str = "jobicy"
    display_name: str = "Jobicy (Tech & Data)"
    description: str = "Remote engineering and tech roles with structured salary ranges and seniority levels"
    default_region: str = "Global"
    default_country: str = "US"
    default_currency: str = "USD"
    endpoint_url: str = "https://jobicy.com/api/v2/remote-jobs"
    supports_search_terms: bool = True

    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"count": min(limit, 50)}
        if term:
            params["tag"] = term.lower().replace(" ", "-")

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
        company_name = (raw_item.get("companyName") or "Jobicy Partner").strip()
        title = (raw_item.get("jobTitle") or "").strip()
        geo = (raw_item.get("jobGeo") or "Worldwide").strip()

        fingerprint = self.generate_fingerprint(company_name, title, geo)
        job_id = self.generate_job_id(self.source_name, raw_item.get("id"), fingerprint)

        description = self.clean_html(raw_item.get("jobDescription"))

        # Map geo to region / country
        geo_lower = geo.lower()
        region = self.default_region
        country_code = self.default_country
        currency = raw_item.get("salaryCurrency") or self.default_currency

        if any(k in geo_lower for k in ("usa", "united states", "north america", "canada")):
            region = "North America"
            country_code = "US"
        elif any(k in geo_lower for k in ("uk", "united kingdom")):
            region = "Europe"
            country_code = "GB"
        elif any(k in geo_lower for k in ("europe", "eu", "germany", "ireland")):
            region = "Europe"
            country_code = "EU"
        elif any(k in geo_lower for k in ("latam", "latin america", "brazil")):
            region = "Latin America"
            country_code = "BR"
        elif "worldwide" in geo_lower or "anywhere" in geo_lower:
            region = "Global"
            country_code = "WW"

        # Industry + job level as skills/badges
        skills_list = []
        industries = raw_item.get("jobIndustry")
        if isinstance(industries, list):
            skills_list.extend(industries)
        elif isinstance(industries, str):
            skills_list.append(industries)

        level = raw_item.get("jobLevel")
        if level:
            skills_list.append(level)

        skills_json = json.dumps(skills_list, ensure_ascii=False) if skills_list else None

        badges = []
        min_sal = raw_item.get("salaryMin")
        max_sal = raw_item.get("salaryMax")
        if min_sal and max_sal:
            badges.append(f"Salary: {min_sal:,.0f} - {max_sal:,.0f} {currency}")
        elif min_sal:
            badges.append(f"Salary: from {min_sal:,.0f} {currency}")

        if level:
            badges.append(f"Level: {level}")

        badges_json = json.dumps(badges, ensure_ascii=False) if badges else None

        job_types = raw_item.get("jobType")
        job_type_str = job_types[0] if isinstance(job_types, list) and job_types else str(job_types or "Full-Time")

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
            "job_type": job_type_str,
            "published_date": parse_datetime(raw_item.get("pubDate")),
            "application_deadline": None,
            "is_remote_work": True,
            "city": None,
            "state": None,
            "country": geo,
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
