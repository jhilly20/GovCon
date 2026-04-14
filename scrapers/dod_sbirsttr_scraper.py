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

from base_scraper import BaseScraper, log, clean_html, format_monday_date

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

    # Monday.com column IDs for DoD SBIR/STTR detail fields
    COL_TPOC = "text_mkkqftmh"
    COL_TPOC_EMAIL = "tpoc_email_mkmfdxba"  # text column
    COL_TPOC_PHONE = "tpoc_phone_mkmfav28"
    COL_COMMAND = "text_mkvqs88k"
    COL_TECH_AREAS = "text_mkvqe9f9"
    COL_FOCUS_AREAS = "text_mkvq51gy"
    COL_KEYWORDS = "text_mkkqnmtk"
    COL_OBJECTIVE = "text_mkkq8dna"
    COL_TOPIC_NO = "text_mkktdh29"
    COL_PHASE1 = "long_text_mkm07mzy"  # long_text type
    COL_PHASE2 = "long_text_1_mkm0n8s1"  # long_text type
    COL_PHASE3 = "long_text_2_mkm0612c"  # long_text type
    COL_PROGRAM = "text_mkm0c9f8"
    COL_TOPIC_ID = "text_mkm0rbb8"
    COL_CMMC = "text_mm01k3mw"
    COL_ITAR = "text_mm01sqgr"
    COL_OPEN_DATE = "date4"  # date type

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a topic record."""
        detail = item.get("_detail", {})

        title = item.get("topicTitle", "")
        topic_code = item.get("topicCode", "")
        component = item.get("component", "")
        program = item.get("program", "")  # SBIR or STTR
        solicitation = item.get("solicitationNumber", "")
        status = item.get("topicStatus", "")
        topic_id = str(item.get("topicId", ""))

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

        # Detail API fields
        objective = clean_html(detail.get("objective", ""))
        phase1 = clean_html(detail.get("phase1Description", ""))
        phase2 = clean_html(detail.get("phase2Description", ""))
        phase3 = clean_html(detail.get("phase3Description", ""))
        keywords = detail.get("keywords", "")
        tech_areas = ", ".join(detail.get("technologyAreas") or [])
        focus_areas = ", ".join(detail.get("focusAreas") or [])
        itar = "Yes" if detail.get("itar") else "No"
        cmmc = detail.get("cmmcLevel", "") or ""

        # Agency = component (e.g. ARMY, NAVY, AIR FORCE)
        agency = f"DoD {component}" if component else "DoD"

        full_title = f"[{topic_code}] {title}" if topic_code else title

        return {
            "title": full_title,
            "description": description[:2000],
            "url": url,
            "deadline": deadline,
            "agency": agency,
            "topic_code": topic_code,
            "topic_id": topic_id,
            "program": program,
            "solicitation": solicitation,
            "status": status,
            "open_date": open_date,
            "close_date": close_date,
            "pre_release_start": pre_release_start,
            "tpoc_name": tpoc_name,
            "tpoc_email": tpoc_email,
            "tpoc_phone": tpoc_phone,
            "objective": objective,
            "phase1": phase1,
            "phase2": phase2,
            "phase3": phase3,
            "keywords": keywords,
            "tech_areas": tech_areas,
            "focus_areas": focus_areas,
            "itar": itar,
            "cmmc": cmmc,
            "component": component,
        }

    def get_extra_column_values(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map detail fields to their dedicated Monday.com columns."""
        cols: Dict[str, Any] = {}

        # Simple text columns
        _text_map = {
            self.COL_TPOC: "tpoc_name",
            self.COL_TPOC_EMAIL: "tpoc_email",
            self.COL_TPOC_PHONE: "tpoc_phone",
            self.COL_COMMAND: "component",
            self.COL_TECH_AREAS: "tech_areas",
            self.COL_FOCUS_AREAS: "focus_areas",
            self.COL_KEYWORDS: "keywords",
            self.COL_OBJECTIVE: "objective",
            self.COL_TOPIC_NO: "topic_code",
            self.COL_PROGRAM: "program",
            self.COL_TOPIC_ID: "topic_id",
            self.COL_CMMC: "cmmc",
            self.COL_ITAR: "itar",
        }
        for col_id, field_key in _text_map.items():
            value = item_data.get(field_key, "")
            if value:
                cols[col_id] = value

        # Long-text columns require {"text": "..."} format
        for col_id, field_key in [
            (self.COL_PHASE1, "phase1"),
            (self.COL_PHASE2, "phase2"),
            (self.COL_PHASE3, "phase3"),
        ]:
            value = item_data.get(field_key, "")
            if value:
                cols[col_id] = {"text": value}

        # Open Date column (date type)
        open_date = item_data.get("open_date")
        if open_date:
            cols[self.COL_OPEN_DATE] = format_monday_date(open_date)

        return cols


def main():
    scraper = DoDSBIRSTTRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
