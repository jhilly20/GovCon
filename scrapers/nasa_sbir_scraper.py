"""NASA SBIR/STTR scraper.

Fetches current open solicitations from the NASA SBIR/STTR page.
NASA's SBIR page links to their solicitation portal with Phase I and
Phase II opportunities.

Source: https://www.nasa.gov/sbir_sttr/
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

NASA_SBIR_URL = "https://www.nasa.gov/sbir_sttr/"
NASA_BASE = "https://www.nasa.gov"
# sbir.gov API as supplementary data source
SBIR_GOV_API = "https://www.sbir.gov/api/solicitations.json"


class NASASBIRScraper(BaseScraper):
    """Scraper for NASA SBIR/STTR opportunities."""

    def __init__(self):
        super().__init__("NASA SBIR")

    def _fetch_from_nasa_page(self) -> list:
        """Scrape the NASA SBIR page for solicitation links and details."""
        items = []
        try:
            resp = self.session.get(NASA_SBIR_URL, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Collect phase/program links with context
            seen_urls = set()
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]

                if not any(
                    kw in text.lower()
                    for kw in [
                        "solicitation", "phase i", "phase ii",
                        "ignite", "sbir", "sttr", "subtopic",
                    ]
                ):
                    continue

                if href.startswith("/"):
                    url = NASA_BASE + href
                elif href.startswith("http"):
                    url = href
                else:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Get context from parent element
                parent = a.find_parent(["p", "li", "div"])
                context = parent.get_text(strip=True) if parent else text

                # Try to extract deadline from context
                deadline = None
                date_match = re.search(
                    r"(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})",
                    context,
                )
                if date_match:
                    deadline = date_match.group(1)

                items.append({
                    "title": f"NASA {text}",
                    "url": url,
                    "description": context[:500] if context != text else "",
                    "deadline": deadline,
                })

            # Follow phase-specific pages to find actual solicitations
            for item in list(items):
                if "/sbir_sttr/phase" in item["url"] or "/sbir_sttr/sbir-ignite" in item["url"]:
                    sub_items = self._scrape_subpage(item["url"], item["title"])
                    if sub_items:
                        items.extend(sub_items)

        except Exception as e:
            log(f"Error fetching NASA SBIR page: {e}")

        return items

    def _scrape_subpage(self, url: str, parent_title: str) -> list:
        """Follow a phase page to find specific solicitation links."""
        sub_items = []
        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                return sub_items
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]

                if not any(
                    kw in text.lower()
                    for kw in ["solicitation", "topic", "subtopic", "submit", "apply"]
                ):
                    continue

                if len(text) < 10:
                    continue

                if href.startswith("/"):
                    full_url = NASA_BASE + href
                elif href.startswith("http"):
                    full_url = href
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

                sub_items.append({
                    "title": f"{parent_title}: {text}",
                    "url": full_url,
                    "description": context[:500] if context != text else "",
                    "deadline": deadline,
                })

        except Exception as e:
            log(f"Error scraping NASA subpage {url}: {e}")

        return sub_items

    def _fetch_from_sbir_gov(self) -> list:
        """Fetch NASA solicitations from sbir.gov API."""
        items = []
        try:
            params = {
                "keyword": "",
                "agency": "National Aeronautics and Space Administration",
                "open": "1",  # Only open solicitations
            }
            resp = self.session.get(SBIR_GOV_API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for sol in data if isinstance(data, list) else []:
                title = sol.get("solicitation_title", "")
                if not title:
                    continue

                # Extract dates
                close_date = sol.get("close_date", "")
                open_date = sol.get("open_date", "")

                url = sol.get("solicitation_url", "")
                if not url:
                    url = sol.get("sb_url", NASA_SBIR_URL)

                description = sol.get("solicitation_agency", "NASA")
                phase = sol.get("solicitation_type", "")
                if phase:
                    description = f"{phase}. {description}"

                items.append({
                    "title": title,
                    "url": url,
                    "description": description,
                    "deadline": close_date,
                })

        except Exception as e:
            log(f"Error fetching from sbir.gov API: {e}")

        return items

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch NASA SBIR opportunities from multiple sources."""
        items = []

        # Try sbir.gov API first (structured data)
        sbir_items = self._fetch_from_sbir_gov()
        if sbir_items:
            log(f"Fetched {len(sbir_items)} items from sbir.gov API")
            items.extend(sbir_items)

        # Also scrape the NASA page for any items not on sbir.gov
        nasa_items = self._fetch_from_nasa_page()
        if nasa_items:
            log(f"Fetched {len(nasa_items)} items from NASA SBIR page")
            # Deduplicate by title
            existing_titles = {i["title"].lower() for i in items}
            for item in nasa_items:
                if item["title"].lower() not in existing_titles:
                    items.append(item)

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a NASA SBIR opportunity."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", NASA_SBIR_URL),
            "deadline": item.get("deadline"),
            "agency": "NASA",
        }


def main():
    scraper = NASASBIRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
