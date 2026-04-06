"""Grants.gov Simpler Search scraper.

Fetches posted and forecasted opportunities from the Grants.gov Simpler
Grants API for small business / for-profit eligibility.

API: https://api.simpler.grants.gov/v1/opportunities/search
Source: https://simpler.grants.gov/search

Note: The v1 API requires an API key.  Set the GRANTS_GOV_API_KEY
environment variable.  If no key is available, falls back to scraping
the HTML search results page.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

API_URL = "https://api.simpler.grants.gov/v1/opportunities/search"
SEARCH_URL = (
    "https://simpler.grants.gov/search"
    "?eligibility=for_profit_organizations_other_than_small_businesses"
    ",small_businesses,unrestricted"
)
PAGE_SIZE = 25

# Defense / dual-use search terms
SEARCH_QUERIES = [
    "defense",
    "SBIR",
    "STTR",
    "dual-use",
    "national security",
    "cybersecurity",
    "artificial intelligence",
]


class GrantsGovScraper(BaseScraper):
    """Scraper for Grants.gov opportunities via API or HTML fallback."""

    def __init__(self):
        super().__init__("Grants.gov")
        self.api_key = os.getenv("GRANTS_GOV_API_KEY", "")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch opportunities from Grants.gov."""
        if self.api_key:
            return self._fetch_api()
        return self._fetch_html()

    def _fetch_api(self) -> List[Dict[str, Any]]:
        """Fetch via the Simpler Grants API (requires API key)."""
        all_items: Dict[str, Dict[str, Any]] = {}  # dedup by opportunity_id

        for query in SEARCH_QUERIES:
            try:
                payload = {
                    "pagination": {"page_offset": 1, "page_size": PAGE_SIZE},
                    "query": query,
                    "filters": {
                        "opportunity_status": {
                            "one_of": ["posted", "forecasted"]
                        },
                    },
                }
                headers = {
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key,
                }
                resp = self.session.post(
                    API_URL, json=payload, headers=headers, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()

                opportunities = data.get("data", {}).get("opportunities", [])
                log(f"Grants.gov API: {len(opportunities)} results for '{query}'")

                for opp in opportunities:
                    opp_id = str(opp.get("opportunity_id", ""))
                    if opp_id and opp_id not in all_items:
                        all_items[opp_id] = opp

            except Exception as e:
                log(f"Error querying Grants.gov API for '{query}': {e}")

        return list(all_items.values())

    def _fetch_html(self) -> List[Dict[str, Any]]:
        """Fallback: scrape the Grants.gov HTML search page."""
        log("No Grants.gov API key, using HTML fallback")
        try:
            resp = self.session.get(SEARCH_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching Grants.gov HTML page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # Look for opportunity cards/listings
        cards = soup.find_all(
            ["article", "div"],
            class_=lambda c: c and ("opportunity" in str(c).lower() or "result" in str(c).lower()) if c else False,
        )

        for card in cards:
            title_el = card.find(["h2", "h3", "h4", "a"])
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = ""
            link = card.find("a", href=True)
            if link:
                href = link["href"]
                if href.startswith("/"):
                    url = "https://simpler.grants.gov" + href
                elif href.startswith("http"):
                    url = href

            desc = card.get_text(separator=" ", strip=True)[:2000]

            items.append({
                "title": title,
                "url": url,
                "description": desc,
                "_html": True,
            })

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a Grants.gov opportunity."""
        if item.get("_html"):
            return {
                "title": item.get("title", ""),
                "description": item.get("description", "")[:2000],
                "url": item.get("url", SEARCH_URL),
                "deadline": None,
                "agency": item.get("agency_name", "Federal"),
            }

        # API response fields
        title = item.get("opportunity_title", "")
        opp_number = item.get("opportunity_number", "")
        agency = item.get("agency_name", "")
        summary = item.get("summary", {})
        description = summary.get("summary_description", "") if isinstance(summary, dict) else ""
        description = clean_html(description)

        close_date = item.get("close_date")
        post_date = item.get("post_date")

        opp_id = item.get("opportunity_id", "")
        url = f"https://simpler.grants.gov/opportunity/{opp_id}" if opp_id else SEARCH_URL

        full_title = f"[{opp_number}] {title}" if opp_number else title

        return {
            "title": full_title,
            "description": description[:2000],
            "url": url,
            "deadline": close_date,
            "agency": agency,
        }


def main():
    scraper = GrantsGovScraper()
    scraper.run()


if __name__ == "__main__":
    main()
