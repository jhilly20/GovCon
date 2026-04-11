"""NIST SBIR scraper.

Fetches current SBIR solicitation information from the NIST Technology
Partnerships Office page.  NIST typically has 1-2 active solicitation
cycles per year.

Source: https://www.nist.gov/tpo/small-business-innovation-research-program-sbir
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

NIST_SBIR_URL = "https://www.nist.gov/tpo/small-business-innovation-research-program-sbir"
NIST_BASE = "https://www.nist.gov"


class NISTSBIRScraper(BaseScraper):
    """Scraper for NIST SBIR solicitations."""

    def __init__(self):
        super().__init__("NIST SBIR")

    def _scrape_main_page(self) -> list:
        """Scrape the main NIST SBIR page for solicitation info."""
        items = []
        try:
            resp = self.session.get(NIST_SBIR_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching NIST SBIR page: {e}")
            return items

        soup = BeautifulSoup(resp.text, "html.parser")

        main_content = (
            soup.find("div", class_="field--name-body")
            or soup.find("article")
            or soup.find("main")
            or soup
        )

        # Look for links pointing to Grants.gov, NIST solicitation pages,
        # or the SBIR schedule page
        for a in main_content.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]

            if not any(
                kw in text.lower()
                for kw in [
                    "solicitation", "grants.gov", "funding",
                    "notice", "nofo", "proposal", "apply",
                ]
            ):
                continue

            if len(text) < 10:
                continue

            if href.startswith("/"):
                url = NIST_BASE + href
            elif href.startswith("http"):
                url = href
            else:
                continue

            parent = a.find_parent(["p", "li", "div"])
            context = parent.get_text(strip=True) if parent else text

            deadline = None
            date_match = re.search(
                r"(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})",
                context,
            )
            if date_match:
                deadline = date_match.group(1)

            items.append({
                "title": f"NIST SBIR: {text}",
                "url": url,
                "description": context[:500],
                "deadline": deadline,
            })

        return items

    def _scrape_schedule_page(self) -> list:
        """Scrape the NIST SBIR schedule page for timeline info."""
        items = []
        schedule_url = (
            NIST_BASE
            + "/tpo/small-business-innovation-research-program-sbir"
            + "/resources/sbir-schedule"
        )
        try:
            resp = self.session.get(schedule_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching NIST SBIR schedule: {e}")
            return items

        soup = BeautifulSoup(resp.text, "html.parser")
        main_content = (
            soup.find("div", class_="field--name-body")
            or soup.find("article")
            or soup
        )
        text = main_content.get_text(separator="\n", strip=True)

        # Extract schedule milestones with dates
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            date_match = re.search(
                r"((?:January|February|March|April|May|June|July|August"
                r"|September|October|November|December)\s+\d{1,2},?\s*\d{4})",
                line,
            )
            if date_match and any(
                kw in line.lower()
                for kw in [
                    "open", "close", "due", "release", "issue",
                    "phase", "solicitation", "nofo", "proposal",
                ]
            ):
                items.append({
                    "title": f"NIST SBIR Schedule: {line[:120]}",
                    "url": schedule_url,
                    "description": line,
                    "deadline": date_match.group(1),
                })

        return items

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch NIST SBIR solicitations from main and schedule pages."""
        items = self._scrape_main_page()
        schedule_items = self._scrape_schedule_page()
        items.extend(schedule_items)

        # Deduplicate by URL
        seen_urls = set()
        unique_items = []
        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                unique_items.append(item)

        return unique_items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a NIST SBIR item."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", NIST_SBIR_URL),
            "deadline": item.get("deadline"),
            "agency": "NIST",
        }


def main():
    scraper = NISTSBIRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
