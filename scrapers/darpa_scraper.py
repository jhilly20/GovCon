"""DARPA Opportunities scraper.

Fetches R&D opportunities from the DARPA RSS feed.  The main
opportunities page is JS-rendered, but DARPA publishes an RSS feed at
https://www.darpa.mil/rss/opportunities.xml that contains recent
postings with descriptions and links.

Source: https://www.darpa.mil/work-with-us/opportunities
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

DARPA_RSS_URL = "https://www.darpa.mil/rss/opportunities.xml"
DARPA_PAGE_URL = "https://www.darpa.mil/work-with-us/opportunities"


class DARPAScraper(BaseScraper):
    """Scraper for DARPA R&D opportunities via RSS feed."""

    def __init__(self):
        super().__init__("DARPA")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch opportunities from the DARPA RSS feed."""
        try:
            resp = self.session.get(DARPA_RSS_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching DARPA RSS feed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")
        log(f"Found {len(items)} items in DARPA RSS feed")

        results = []
        for item in items:
            results.append(
                {
                    "title": item.title.get_text(strip=True) if item.title else "",
                    "link": item.link.get_text(strip=True) if item.link else "",
                    "description_raw": (
                        item.description.get_text() if item.description else ""
                    ),
                    "pub_date": (
                        item.pubDate.get_text(strip=True) if item.pubDate else ""
                    ),
                    "guid": item.guid.get_text(strip=True) if item.guid else "",
                }
            )

        return results

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a DARPA RSS item."""
        title = item.get("title", "")
        description_raw = item.get("description_raw", "")

        # Parse HTML description to extract text and any embedded links
        desc_soup = BeautifulSoup(description_raw, "html.parser")
        description = desc_soup.get_text(separator=" ", strip=True)

        # Try to extract a direct link from description (often links to SAM.gov or grants.gov)
        url = item.get("link") or DARPA_PAGE_URL
        desc_links = desc_soup.find_all("a", href=True)
        for link in desc_links:
            href = link["href"]
            if "sam.gov" in href or "grants.gov" in href:
                url = href
                break

        # Extract deadline from description text if present
        deadline = None
        deadline_patterns = [
            r"(?:due|closes?|deadline|response)\s*(?:date)?[:\s]*(\w+ \d{1,2},?\s*\d{4})",
            r"(\d{1,2}/\d{1,2}/\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
        ]
        for pattern in deadline_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                deadline = match.group(1)
                break

        # Determine opportunity type from title
        opp_type = ""
        for prefix in ["BAA", "RFI", "CSO", "HR", "PA"]:
            if re.search(r'\b' + prefix + r'\b', title.upper()):
                opp_type = prefix
                break

        full_title = f"DARPA {opp_type}: {title}" if opp_type else f"DARPA: {title}"

        return {
            "title": full_title,
            "description": description[:2000],
            "url": url,
            "deadline": deadline,
            "agency": "DARPA",
        }


def main():
    scraper = DARPAScraper()
    scraper.run()


if __name__ == "__main__":
    main()
