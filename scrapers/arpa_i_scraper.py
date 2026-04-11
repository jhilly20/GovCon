"""ARPA-I (Advanced Research Projects Agency — Infrastructure) scraper.

The ARPA-I page at transportation.gov returns 403 (Cloudflare).
This scraper falls back to searching Grants.gov for ARPA-I and DOT
funding opportunities.

No authentication required.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, clean_html, log

GRANTS_GOV_SEARCH = "https://api.grants.gov/v1/api/search2"
GRANTS_GOV_DETAIL = "https://www.grants.gov/search-results-detail"
ARPA_I_PAGE = "https://www.transportation.gov/arpa-i"
PAGE_SIZE = 100


class ARPAIScraper(BaseScraper):
    """Scraper for ARPA-I opportunities via Grants.gov API."""

    def __init__(self):
        super().__init__("ARPA-I")

    # Only keep results whose agency contains one of these strings
    DOT_AGENCY_KEYWORDS = [
        "DOT",
        "Transportation",
        "Highway",
        "Transit",
        "Aviation",
        "Maritime",
        "Railroad",
        "Pipeline",
        "NHTSA",
        "FHWA",
        "FTA",
        "FAA",
        "FRA",
        "PHMSA",
        "FMCSA",
    ]

    # Search terms that capture ARPA-I and DOT innovation opportunities
    SEARCH_TERMS = [
        "ARPA-I",
        "transportation infrastructure innovation",
        "DOT research innovation technology",
    ]

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Search Grants.gov for ARPA-I and DOT innovation opportunities."""
        all_items: Dict[str, Dict[str, Any]] = {}

        for term in self.SEARCH_TERMS:
            results = self._search_grants_gov(term)
            for opp in results:
                opp_id = str(opp.get("id", ""))
                if not opp_id or opp_id in all_items:
                    continue
                agency = opp.get("agency", "")
                if self._is_dot_agency(agency):
                    all_items[opp_id] = opp

        log(f"ARPA-I: {len(all_items)} unique DOT/ARPA-I opportunities")
        return list(all_items.values())

    def _is_dot_agency(self, agency: str) -> bool:
        """Check if an agency string belongs to DOT."""
        agency_lower = agency.lower()
        return any(kw.lower() in agency_lower for kw in self.DOT_AGENCY_KEYWORDS)

    def _search_grants_gov(self, keyword: str) -> list:
        """Search Grants.gov for a specific keyword."""
        try:
            payload = {
                "keyword": keyword,
                "oppStatuses": "posted|forecasted",
                "eligibilities": "22|23|25",  # small biz / for-profit / unrestricted
                "rows": PAGE_SIZE,
                "startRecordNum": 0,
            }
            resp = self.session.post(
                GRANTS_GOV_SEARCH,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("errorcode") != 0:
                log(f"Grants.gov API error for '{keyword}': {data.get('msg')}")
                return []

            opportunities = data.get("data", {}).get("oppHits", [])
            hit_count = data.get("data", {}).get("hitCount", 0)
            log(f"Grants.gov '{keyword}': {len(opportunities)} of {hit_count} results")
            return opportunities

        except Exception as e:
            log(f"Grants.gov search error for '{keyword}': {e}")
            return []

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a Grants.gov opportunity."""
        title = clean_html(item.get("title", ""))
        opp_number = item.get("number", "")
        agency = item.get("agency", "")

        opp_id = item.get("id", "")
        url = f"{GRANTS_GOV_DETAIL}/{opp_id}" if opp_id else ARPA_I_PAGE

        # Parse close date
        close_date_raw = item.get("closeDate", "")
        deadline = None
        if close_date_raw:
            m = re.match(r"(\d{2})/(\d{2})/(\d{4})", close_date_raw)
            if m:
                deadline = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

        full_title = f"[{opp_number}] {title}" if opp_number else title

        return {
            "title": full_title,
            "description": f"Status: {item.get('oppStatus', '')} | "
            f"Agency: {agency} | "
            f"Open: {item.get('openDate', '')} | "
            f"Close: {close_date_raw or 'N/A'}",
            "url": url,
            "deadline": deadline,
            "agency": agency or "DOT ARPA-I",
        }


def main():
    scraper = ARPAIScraper()
    scraper.run()


if __name__ == "__main__":
    main()
