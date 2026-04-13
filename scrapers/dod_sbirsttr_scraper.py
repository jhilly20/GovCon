"""DoD SBIR/STTR Topics scraper.

Fetches open and pre-release topics from the DoD SBIR/STTR public API
and syncs them to Monday.com with Slack notifications.

API docs (inferred from browser traffic):
  Search: GET /topics/api/public/topics/search?searchParam=...&size=...&page=...
  Detail: GET /topics/api/public/topics/{topicId}/details

The search endpoint requires the Referer header set to the topics-app origin.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import requests

from base_scraper import BaseScraper, log, clean_html

# API configuration
BASE_URL = "https://www.dodsbirsttr.mil"
SEARCH_URL = f"{BASE_URL}/topics/api/public/topics/search"
DETAIL_URL = f"{BASE_URL}/topics/api/public/topics/{{topicId}}/details"

# topicReleaseStatus codes: 591 = Open, 592 = Pre-Release
OPEN_STATUS = 591
PRE_RELEASE_STATUS = 592

# Required headers to avoid 403
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE_URL}/topics-app/",
    "Origin": BASE_URL,
}

PAGE_SIZE = 200
REQUEST_DELAY = 0.5  # seconds between detail requests


def _epoch_ms_to_date(epoch_ms: int | None) -> str | None:
    """Convert epoch milliseconds to YYYY-MM-DD string."""
    if not epoch_ms:
        return None
    try:
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        return None


class DoDSBIRSTTRScraper(BaseScraper):
    """Scraper for DoD SBIR/STTR open and pre-release topics."""

    def __init__(self):
        super().__init__("DoD SBIR/STTR")
        self.session.headers.update(API_HEADERS)

    def _build_search_params(self, page: int = 0) -> Dict[str, Any]:
        """Build URL query parameters for the search endpoint."""
        search_param = {
            "searchText": None,
            "components": None,
            "programYear": None,
            "solicitationCycleNames": ["openTopics"],
            "releaseNumbers": [],
            "topicReleaseStatus": [PRE_RELEASE_STATUS, OPEN_STATUS],
            "modernizationPriorities": [],
            "sortBy": "finalTopicCode,asc",
            "technologyAreaIds": [],
            "component": None,
            "program": None,
        }
        return {
            "searchParam": json.dumps(search_param, separators=(",", ":")),
            "size": str(PAGE_SIZE),
            "page": str(page),
        }

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch all open/pre-release topics from the DoD SBIR/STTR API."""
        all_topics = []
        page = 0

        while True:
            params = self._build_search_params(page)
            try:
                log(f"Fetching DoD SBIR/STTR page {page} ...")
                resp = self.session.get(SEARCH_URL, params=params, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:
                log(f"Error fetching search page {page}: {e}")
                break

            topics = payload.get("data", [])
            total = payload.get("total", 0)

            if not topics:
                break

            all_topics.extend(topics)
            log(f"  Got {len(topics)} topics (total reported: {total})")

            if len(all_topics) >= total:
                break

            page += 1
            time.sleep(REQUEST_DELAY)

        # Optionally fetch detail for each topic
        for i, topic in enumerate(all_topics):
            topic_id = topic.get("topicId")
            if topic_id:
                try:
                    detail = self._fetch_detail(topic_id)
                    topic["_detail"] = detail
                except Exception as e:
                    log(f"Error fetching detail for {topic_id}: {e}")
                    topic["_detail"] = {}
                if i < len(all_topics) - 1:
                    time.sleep(REQUEST_DELAY)

        return all_topics

    def _fetch_detail(self, topic_id: str) -> Dict[str, Any]:
        """Fetch full detail for a single topic."""
        url = DETAIL_URL.format(topicId=topic_id)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _build_description(self, item: Dict[str, Any], detail: Dict[str, Any]) -> str:
        """Build a comprehensive description from search + detail API data.

        Combines the topic description, objective, phase descriptions,
        keywords, technology areas, and focus areas into a single text
        block suitable for the Monday.com description column.
        """
        sections = []

        # Objective (most useful summary — show first)
        objective = clean_html(detail.get("objective", ""))
        if objective:
            sections.append(f"OBJECTIVE: {objective}")

        # Main description
        description = clean_html(detail.get("description", ""))
        if description:
            sections.append(f"DESCRIPTION: {description}")

        # Phase descriptions
        for phase_key, phase_label in [
            ("phase1Description", "PHASE I"),
            ("phase2Description", "PHASE II"),
            ("phase3Description", "PHASE III"),
        ]:
            phase_text = clean_html(detail.get(phase_key, ""))
            if phase_text:
                sections.append(f"{phase_label}: {phase_text}")

        # Keywords
        keywords = detail.get("keywords", "")
        if keywords:
            sections.append(f"KEYWORDS: {keywords}")

        # Technology areas & focus areas
        tech_areas = detail.get("technologyAreas") or []
        if tech_areas:
            sections.append(f"TECHNOLOGY AREAS: {', '.join(tech_areas)}")

        focus_areas = detail.get("focusAreas") or []
        if focus_areas:
            sections.append(f"FOCUS AREAS: {', '.join(focus_areas)}")

        # ITAR flag
        if detail.get("itar"):
            sections.append("ITAR: Yes")

        # CMMC level
        cmmc = detail.get("cmmcLevel", "")
        if cmmc:
            sections.append(f"CMMC LEVEL: {cmmc}")

        # Metadata from search result
        program = item.get("program", "")
        solicitation = item.get("solicitationNumber", "")
        component = item.get("component", "")
        status = item.get("topicStatus", "")

        if not sections:
            # Fallback when detail API returned nothing
            return f"{program} {solicitation} - {component} - {status}"

        return "\n\n".join(sections)

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a topic record."""
        detail = item.get("_detail", {})

        title = item.get("topicTitle", "")
        topic_code = item.get("topicCode", "")
        component = item.get("component", "")
        program = item.get("program", "")  # SBIR or STTR
        solicitation = item.get("solicitationNumber", "")
        status = item.get("topicStatus", "")

        # Build comprehensive description from detail API fields
        description = self._build_description(item, detail)

        # Build URL to topic detail page
        url = f"{BASE_URL}/topics-app/#!/topics/{topic_code}" if topic_code else BASE_URL

        # Dates
        open_date = _epoch_ms_to_date(item.get("topicStartDate"))
        close_date = _epoch_ms_to_date(item.get("topicEndDate"))
        pre_release_start = _epoch_ms_to_date(item.get("topicPreReleaseStartDate"))

        # Use close date as deadline; fall back to pre-release end
        deadline = close_date or _epoch_ms_to_date(item.get("topicPreReleaseEndDate"))

        # TPOC information
        tpoc_name = ""
        tpoc_email = ""
        tpoc_phone = ""
        managers = item.get("topicManagers") or []
        for mgr in managers:
            if mgr.get("assignmentType") == "TPOC":
                tpoc_name = mgr.get("name", "")
                tpoc_email = mgr.get("email", "") if mgr.get("emailDisplay") == "Y" else ""
                tpoc_phone = mgr.get("phone", "") if mgr.get("phoneDisplay") == "Y" else ""
                break

        # Agency = component (e.g. ARMY, NAVY, AIR FORCE)
        agency = f"DoD {component}" if component else "DoD"

        full_title = f"[{topic_code}] {title}" if topic_code else title

        return {
            "title": full_title,
            "description": description[:5000],
            "url": url,
            "deadline": deadline,
            "agency": agency,
            "topic_code": topic_code,
            "program": program,
            "solicitation": solicitation,
            "status": status,
            "open_date": open_date,
            "close_date": close_date,
            "pre_release_start": pre_release_start,
            "tpoc_name": tpoc_name,
            "tpoc_email": tpoc_email,
            "tpoc_phone": tpoc_phone,
        }


def main():
    scraper = DoDSBIRSTTRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
