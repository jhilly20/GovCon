"""TechConnect opportunities scraper.

Fetches active opportunities from the TechConnect WordPress site via
its REST API (page 843 contains the rendered opportunities listing).

No authentication required.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

WP_API_URL = "https://techconnect.org/wp-json/wp/v2/pages/843"
TECHCONNECT_BASE = "https://techconnect.org"


class TechConnectScraper(BaseScraper):
    """Scraper for TechConnect opportunities via WordPress REST API."""

    def __init__(self):
        super().__init__("TechConnect")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch the opportunities page and parse opportunity cards."""
        try:
            resp = self.session.get(WP_API_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(f"Error fetching TechConnect API: {e}")
            return []

        content_html = data.get("content", {}).get("rendered", "")
        if not content_html:
            log("TechConnect: no rendered content found")
            return []

        soup = BeautifulSoup(content_html, "html.parser")
        cards = soup.find_all("div", class_="pt-cv-content-item")
        log(f"TechConnect: found {len(cards)} opportunity cards")

        items = []
        for card in cards:
            title_el = card.find("h4", class_="pt-cv-title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link_el = title_el.find("a", href=True)
            url = link_el["href"] if link_el else ""

            # Category tag (e.g. "OPPORTUNITY")
            tax_el = card.find("div", class_="pt-cv-taxoterm")
            category = tax_el.get_text(strip=True) if tax_el else ""

            # Description / due date from content div
            content_div = card.find("div", class_="pt-cv-content")
            desc_text = content_div.get_text(strip=True) if content_div else ""

            # Extract due date from description text like "Due: April 21, 2026"
            deadline = None
            m = re.search(
                r"Due:\s*(\w+\s+\d{1,2},?\s+\d{4})", desc_text, re.IGNORECASE
            )
            if m:
                deadline = m.group(1).strip()

            items.append(
                {
                    "title": title,
                    "url": url,
                    "category": category,
                    "description": desc_text,
                    "deadline_raw": deadline,
                }
            )

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a TechConnect opportunity card."""
        return {
            "title": item.get("title", ""),
            "description": clean_html(item.get("description", ""))[:2000],
            "url": item.get("url", ""),
            "deadline": item.get("deadline_raw"),
            "agency": "TechConnect",
        }


def main():
    scraper = TechConnectScraper()
    scraper.run()


if __name__ == "__main__":
    main()
