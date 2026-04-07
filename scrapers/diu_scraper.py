"""DIU (Defense Innovation Unit) Open Solicitations scraper.

Fetches open Commercial Solutions Openings (CSOs) and challenges from
the DIU website. The page is server-rendered via Nuxt.js, so plain
HTTP requests are sufficient.

Source: https://www.diu.mil/work-with-us/open-solicitations
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

DIU_URL = "https://www.diu.mil/work-with-us/open-solicitations"
DIU_BASE = "https://www.diu.mil"


class DIUScraper(BaseScraper):
    """Scraper for DIU open solicitations and challenges."""

    def __init__(self):
        super().__init__("DIU")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch open solicitations from the DIU page."""
        try:
            resp = self.session.get(DIU_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching DIU page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # Find h4 headings that represent solicitation titles
        h4_elements = soup.find_all("h4")
        for h4 in h4_elements:
            title = h4.get_text(strip=True)

            # Skip non-solicitation headings
            if any(
                skip in title
                for skip in [
                    "Eligibility",
                    "Connect",
                    "Sorry",
                    "Search",
                    "Defense Advanced",
                    "Find the Right",
                ]
            ):
                continue

            # Find the parent container
            parent = h4.find_parent("div")
            if not parent:
                continue

            full_text = parent.get_text(separator="|", strip=True)

            # Extract deadline from "Responses Due By" text
            deadline = None
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", full_text)
            if date_match:
                deadline = date_match.group(1)

            # Extract submission link
            url = DIU_URL
            links = parent.find_all("a", href=True)
            for link in links:
                href = link["href"]
                link_text = link.get_text(strip=True).lower()
                if "submit" in link_text or "solution" in link_text:
                    if href.startswith("/"):
                        url = DIU_BASE + href
                    elif href.startswith("http"):
                        url = href
                    break

            # Extract description from nearby paragraphs
            description = ""
            for sib in h4.find_next_siblings(["p", "div"], limit=3):
                text = sib.get_text(strip=True)
                if text and len(text) > 20 and "Responses Due" not in text:
                    description = text[:2000]
                    break

            items.append(
                {
                    "title": title,
                    "deadline": deadline,
                    "url": url,
                    "description": description,
                    "full_text": full_text,
                }
            )

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a DIU solicitation."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", DIU_URL),
            "deadline": item.get("deadline"),
            "agency": "DIU (Defense Innovation Unit)",
        }


def main():
    scraper = DIUScraper()
    scraper.run()


if __name__ == "__main__":
    main()
