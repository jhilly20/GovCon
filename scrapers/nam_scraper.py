"""NAM Consortium (National Advanced Mobility Consortium) scraper.

Fetches open and pending opportunities from the NAMC portal.
The site is a custom CMS with server-rendered HTML containing
opportunity cards with status filters.

Source: https://www.namconsortium.org/opportunities
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

NAM_URL = "https://www.namconsortium.org/opportunities"
NAM_BASE = "https://www.namconsortium.org"


class NAMScraper(BaseScraper):
    """Scraper for NAM Consortium opportunities."""

    def __init__(self):
        super().__init__("NAM Consortium")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch open and pending opportunities from NAMC."""
        try:
            # The site supports query params for filtering
            # status_op=or&status[]=Open&status[]=Pending
            params = {
                "status_op": "or",
                "status[]": ["Open", "Pending"],
            }
            resp = self.session.get(NAM_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching NAM Consortium page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # Look for opportunity entries — typically in a list or table
        # The site has a main content area with opportunity cards
        main_content = soup.find("main") or soup.find("div", class_="main-content")
        if not main_content:
            main_content = soup

        # Look for links to individual opportunity pages
        all_links = main_content.find_all("a", href=True)
        seen_urls = set()

        for link in all_links:
            href = link["href"]
            text = link.get_text(strip=True)

            # NAM opportunity detail pages typically follow /opportunities/ID pattern
            if "/opportunities/" not in href or href == "/opportunities":
                continue
            if not text or len(text) < 5:
                continue

            if href.startswith("/"):
                full_url = NAM_BASE + href
            elif href.startswith("http"):
                full_url = href
            else:
                continue

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Get parent row/container for additional context
            parent = link.find_parent("tr") or link.find_parent("div")
            context_text = parent.get_text(separator=" | ", strip=True) if parent else text

            # Extract status from context
            status = ""
            status_match = re.search(r"\b(Open|Pending|Closed|Draft)\b", context_text, re.IGNORECASE)
            if status_match:
                status = status_match.group(1)
                # Skip closed/draft
                if status.lower() in ("closed", "draft"):
                    continue

            # Extract deadline if present
            deadline = None
            date_match = re.search(
                r"(\d{1,2}/\d{1,2}/\d{4}|\w+ \d{1,2},?\s*\d{4}|\d{4}-\d{2}-\d{2})",
                context_text,
            )
            if date_match:
                deadline = date_match.group(1)

            items.append({
                "title": text,
                "status": status,
                "deadline": deadline,
                "url": full_url,
                "description": f"Status: {status}" if status else "",
            })

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a NAM Consortium opportunity."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", NAM_URL),
            "deadline": item.get("deadline"),
            "agency": "NAM Consortium (Army)",
        }


def main():
    scraper = NAMScraper()
    scraper.run()


if __name__ == "__main__":
    main()
