"""Grants.gov opportunity scraper.

Fetches posted and forecasted opportunities from the Grants.gov public
REST API (search2 endpoint).  No API key or authentication is required.

API docs: https://grants.gov/api/applicant/
Endpoint: https://api.grants.gov/v1/api/search2

Filters to eligibilities relevant to small / for-profit businesses and
returns only posted or forecasted opportunities.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, clean_html, log

SEARCH_URL = "https://api.grants.gov/v1/api/search2"
GRANTS_GOV_BASE = "https://www.grants.gov/search-results-detail"
PAGE_SIZE = 250

# Eligibility codes that match the user's Simpler Grants search filter:
#   for_profit_organizations_other_than_small_businesses → 22
#   small_businesses → 23
#   unrestricted → 25
ELIGIBLE_CODES = "22|23|25"


class GrantsGovScraper(BaseScraper):
    """Scraper for Grants.gov opportunities via the public search2 API."""

    def __init__(self):
        super().__init__("Grants.gov")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch posted/forecasted opportunities eligible for small/for-profit businesses."""
        all_items: Dict[str, Dict[str, Any]] = {}  # dedup by opportunity id
        page = 0

        while True:
            try:
                payload = {
                    "oppStatuses": "posted|forecasted",
                    "eligibilities": ELIGIBLE_CODES,
                    "rows": PAGE_SIZE,
                    "startRecordNum": page * PAGE_SIZE,
                }
                resp = self.session.post(
                    SEARCH_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("errorcode") != 0:
                    log(f"Grants.gov API error: {data.get('msg')}")
                    break

                opportunities = data.get("data", {}).get("oppHits", [])
                hit_count = data.get("data", {}).get("hitCount", 0)

                if not opportunities:
                    break

                for opp in opportunities:
                    opp_id = str(opp.get("id", ""))
                    if opp_id and opp_id not in all_items:
                        all_items[opp_id] = opp

                log(
                    f"Grants.gov: fetched {len(all_items)} of {hit_count} "
                    f"total results (page {page})"
                )

                if len(all_items) >= hit_count:
                    break

                page += 1

            except Exception as e:
                log(f"Error querying Grants.gov API (page {page}): {e}")
                break

        log(f"Grants.gov: {len(all_items)} unique opportunities total")
        return list(all_items.values())

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a Grants.gov opportunity."""
        title = clean_html(item.get("title", ""))
        opp_number = item.get("number", "")
        agency = item.get("agency", "")

        # Build URL to the opportunity detail page
        opp_id = item.get("id", "")
        url = f"{GRANTS_GOV_BASE}/{opp_id}" if opp_id else ""

        # Parse close date from MM/DD/YYYY to YYYY-MM-DD
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
            f"Doc Type: {item.get('docType', '')} | "
            f"Agency: {agency} | "
            f"Open Date: {item.get('openDate', '')} | "
            f"Close Date: {close_date_raw or 'N/A'}",
            "url": url,
            "deadline": deadline,
            "agency": agency,
        }


def main():
    scraper = GrantsGovScraper()
    scraper.run()


if __name__ == "__main__":
    main()
