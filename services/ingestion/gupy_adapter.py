"""
SkillPulse AI - Gupy Ingestion Adapter (Latin America / Brazil).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import requests

from services.ingestion.base_adapter import BaseIngestionAdapter
from utils import parse_datetime, parse_date


class GupyAdapter(BaseIngestionAdapter):
    """Adapter for Gupy (employability-portal.gupy.io)."""

    source_name: str = "gupy"
    display_name: str = "Gupy (Latin America)"
    description: str = "Leading Brazilian & Latin American enterprise tech job board"
    default_region: str = "Latin America"
    default_country: str = "BR"
    default_currency: str = "BRL"
    endpoint_url: str = "https://employability-portal.gupy.io/api/v1/jobs"
    supports_search_terms: bool = True

    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        params = {
            "limit": limit,
            "offset": str((page * limit) - limit),
            "sortBy": "publishedDate",
            "sortOrder": "desc",
        }
        if term:
            params["jobName"] = term

        try:
            resp = requests.get(
                self.endpoint_url,
                params=params,
                headers=self.DEFAULT_HEADERS,
                timeout=self.FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
                return payload["data"]
            return []
        except Exception:
            return []

    def normalize_job(
        self,
        raw_item: Dict[str, Any],
        term: Optional[str] = None,
    ) -> Dict[str, Any]:
        company_name = raw_item.get("careerPageName") or f"Empresa {raw_item.get('companyId', '')}"
        title = raw_item.get("name", "").strip()
        location_str = f"{raw_item.get('city', '')} {raw_item.get('state', '')} {raw_item.get('country', '')}"
        fingerprint = self.generate_fingerprint(company_name, title, location_str)
        job_id = self.generate_job_id(self.source_name, raw_item.get("id"), fingerprint)

        description = self.clean_html(raw_item.get("description"))

        # Remote / workplace mapping
        is_remote = bool(raw_item.get("isRemoteWork"))
        wp_type = raw_item.get("workplaceType")
        if not wp_type:
            wp_type = "REMOTE" if is_remote else "ONSITE"

        # Skills & badges serialization
        skills_raw = raw_item.get("skills")
        skills_json = json.dumps(skills_raw, ensure_ascii=False) if skills_raw else None

        badges_raw = raw_item.get("badges")
        badges_json = json.dumps(badges_raw, ensure_ascii=False) if badges_raw else None

        return {
            "id": job_id,
            "source": self.source_name,
            "company_id": raw_item.get("companyId"),
            "name": title,
            "description": description,
            "career_page_id": raw_item.get("careerPageId"),
            "career_page_name": company_name,
            "career_page_logo": raw_item.get("careerPageLogo"),
            "career_page_url": raw_item.get("careerPageUrl"),
            "job_type": raw_item.get("type"),
            "published_date": parse_datetime(raw_item.get("publishedDate")),
            "application_deadline": parse_date(raw_item.get("applicationDeadline")),
            "is_remote_work": is_remote,
            "city": raw_item.get("city"),
            "state": raw_item.get("state"),
            "country": raw_item.get("country") or "Brasil",
            "job_url": raw_item.get("jobUrl"),
            "workplace_type": wp_type,
            "disabilities": raw_item.get("disabilities"),
            "skills": skills_json,
            "badges": badges_json,
            "region": self.default_region,
            "country_code": self.default_country,
            "currency": self.default_currency,
            "fingerprint": fingerprint,
        }
