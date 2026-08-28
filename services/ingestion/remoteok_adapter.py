"""
SkillPulse AI - RemoteOK Ingestion Adapter (Global Remote Tech / Developer Roles).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
import requests

from services.ingestion.base_adapter import BaseIngestionAdapter
from utils import parse_datetime


class RemoteOKAdapter(BaseIngestionAdapter):
    """Adapter for RemoteOK Public API."""

    source_name: str = "remoteok"
    display_name: str = "RemoteOK (Developer & Tech)"
    description: str = "Global remote software engineer, developer, DevOps, and cloud jobs"
    default_region: str = "Global"
    default_country: str = "US"
    default_currency: str = "USD"
    endpoint_url: str = "https://remoteok.com/api"
    supports_search_terms: bool = True

    def fetch_jobs(
        self,
        term: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        # RemoteOK returns a full list; first element is legal notice
        try:
            resp = requests.get(
                self.endpoint_url,
                headers=self.DEFAULT_HEADERS,
                timeout=self.FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return []

            # Filter out legal/header elements
            items = [item for item in data if isinstance(item, dict) and "position" in item]

            if term:
                term_lower = term.lower()
                filtered = []
                for j in items:
                    pos_match = term_lower in (j.get("position") or "").lower()
                    desc_match = term_lower in (j.get("description") or "").lower()
                    tags_match = any(term_lower in str(t).lower() for t in (j.get("tags") or []))
                    if pos_match or desc_match or tags_match:
                        filtered.append(j)
                return filtered[:limit]

            # Paginate in memory
            start = (page - 1) * limit
            return items[start : start + limit]
        except Exception:
            return []

    def normalize_job(
        self,
        raw_item: Dict[str, Any],
        term: Optional[str] = None,
    ) -> Dict[str, Any]:
        company_name = (raw_item.get("company") or "RemoteOK Partner").strip()
        title = (raw_item.get("position") or "").strip()
        loc_str = (raw_item.get("location") or "Worldwide").strip()
        slug = raw_item.get("slug") or str(raw_item.get("id"))

        fingerprint = self.generate_fingerprint(company_name, title, loc_str)
        job_id = self.generate_job_id(self.source_name, slug, fingerprint)

        description = self.clean_html(raw_item.get("description"))

        # Map region / country
        region = self.default_region
        country_code = self.default_country
        currency = self.default_currency
        loc_lower = loc_str.lower()

        if any(k in loc_lower for k in ("usa", "united states", "us only", "north america")):
            region = "North America"
            country_code = "US"
        elif any(k in loc_lower for k in ("uk", "united kingdom")):
            region = "Europe"
            country_code = "GB"
            currency = "GBP"
        elif any(k in loc_lower for k in ("europe", "eu", "germany", "ireland")):
            region = "Europe"
            country_code = "EU"
            currency = "EUR"
        elif "worldwide" in loc_lower or "anywhere" in loc_lower:
            region = "Global"
            country_code = "WW"

        tags = raw_item.get("tags") or []
        skills_json = json.dumps(tags, ensure_ascii=False) if tags else None

        badges = []
        min_sal = raw_item.get("salary_min")
        max_sal = raw_item.get("salary_max")
        if min_sal and max_sal:
            badges.append(f"Salary: ${min_sal:,.0f} - ${max_sal:,.0f}")
        elif min_sal:
            badges.append(f"Salary: from ${min_sal:,.0f}")

        badges_json = json.dumps(badges, ensure_ascii=False) if badges else None

        # Parse date (iso or epoch)
        pub_val = raw_item.get("date") or raw_item.get("epoch")
        pub_dt = None
        if isinstance(pub_val, (int, float)):
            pub_dt = datetime.fromtimestamp(pub_val, tz=UTC).replace(tzinfo=None)
        elif isinstance(pub_val, str):
            pub_dt = parse_datetime(pub_val)

        return {
            "id": job_id,
            "source": self.source_name,
            "company_id": None,
            "name": title,
            "description": description,
            "career_page_id": None,
            "career_page_name": company_name,
            "career_page_logo": raw_item.get("company_logo") or raw_item.get("logo"),
            "career_page_url": None,
            "job_type": "Full-time",
            "published_date": pub_dt,
            "application_deadline": None,
            "is_remote_work": True,
            "city": None,
            "state": None,
            "country": loc_str,
            "job_url": raw_item.get("url") or raw_item.get("apply_url"),
            "workplace_type": "REMOTE",
            "disabilities": None,
            "skills": skills_json,
            "badges": badges_json,
            "region": region,
            "country_code": country_code,
            "currency": currency,
            "fingerprint": fingerprint,
        }
