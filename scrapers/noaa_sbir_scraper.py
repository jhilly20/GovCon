"""NOAA SBIR scraper.

Fetches funding opportunities from the NOAA Technology Partnerships
Office SBIR page.  The site is WordPress-based.

Source: https://techpartnerships.noaa.gov/sbir/fundingopportunities/
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

NOAA_SBIR_URL = "https://techpartnerships.noaa.gov/sbir/fundingopportunities/"
NOAA_BASE = "https://techpartnerships.noaa.gov"
# Try WordPress REST API first
NOAA_WP_API = "https://techpartnerships.noaa.gov/wp-json/wp/v2/posts"


class NOAASBIRScraper(BaseScraper):
    """Scraper for NOAA SBIR funding opportunities."""

    def __init__(self):
        super().__init__("NOAA SBIR")

    def _fetch_from_wp_api(self) -> list:
        """Try fetching from WordPress REST API."""
        items = []
        try:
            # Search for SBIR-related posts
            params = {
                "per_page": 20,
                "search": "SBIR",
                "orderby": "date",
                "order": "desc",
            }
            resp = self.session.get(NOAA_WP_API, params=params, timeout=30)
            if resp.status_code == 200:
                posts = resp.json()
                for post in posts:
                    title = post.get("title", {}).get("rendered", "")
                    if not title:
                        continue
                    # Clean HTML from title
                    title = re.sub(r"<[^>]+>", "", title).strip()

                    content = post.get("content", {}).get("rendered", "")
                    excerpt = post.get("excerpt", {}).get("rendered", "")
                    description = re.sub(r"<[^>]+>", "", excerpt or content).strip()

                    url = post.get("link", NOAA_SBIR_URL)
                    date_published = post.get("date", "")[:10]

                    items.append({
                        "title": title,
                        "url": url,
                        "description": description[:2000],
                        "deadline": None,
                        "date_published": date_published,
                    })
                log(f"Fetched {len(items)} posts from NOAA WP API")
        except Exception as e:
            log(f"NOAA WP API failed: {e}")

        return items

    def _fetch_from_html(self) -> list:
        """Scrape the NOAA funding opportunities page for status info."""
        items = []
        try:
            resp = self.session.get(NOAA_SBIR_URL, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            main_content = (
                soup.find("div", class_="entry-content")
                or soup.find("main")
                or soup
            )

            page_text = main_content.get_text(separator="\n", strip=True)

            # The page typically has a status banner like
            # "The FY 2025 Notice of Funding Opportunity is now closed"
            # or links to the current NOFO
            for h in main_content.find_all(["h2", "h3", "h4"]):
                heading_text = h.get_text(strip=True)
                if not heading_text:
                    continue

                # Get content after this heading
                content_parts = []
                for sib in h.find_next_siblings():
                    if sib.name in ("h2", "h3", "h4"):
                        break
                    content_parts.append(sib.get_text(strip=True))
                content = " ".join(content_parts)[:500]

                # Determine status
                combined = f"{heading_text} {content}".lower()
                is_closed = "closed" in combined
                is_open = any(
                    kw in combined
                    for kw in ["open", "accepting", "available", "submit"]
                )

                # Extract any deadline dates
                deadline = None
                date_match = re.search(
                    r"(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})",
                    content,
                )
                if date_match:
                    deadline = date_match.group(1)

                status = "closed" if is_closed else "open" if is_open else "unknown"

                items.append({
                    "title": f"NOAA SBIR: {heading_text}",
                    "url": NOAA_SBIR_URL,
                    "description": f"Status: {status}. {content}"[:2000],
                    "deadline": deadline,
                    "status": status,
                })

            # Also find links to external solicitation pages (Grants.gov etc.)
            for a in main_content.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]

                if not any(
                    kw in href.lower()
                    for kw in ["grants.gov", "nofo", "solicitation"]
                ):
                    continue

                if len(text) < 10:
                    continue

                url = href if href.startswith("http") else NOAA_BASE + href

                parent = a.find_parent(["p", "li"])
                context = parent.get_text(strip=True) if parent else text

                items.append({
                    "title": f"NOAA: {text}",
                    "url": url,
                    "description": context[:500],
                    "deadline": None,
                })

        except Exception as e:
            log(f"Error fetching NOAA SBIR HTML: {e}")

        return items

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch NOAA SBIR opportunities from WP API or HTML fallback."""
        items = self._fetch_from_wp_api()
        if not items:
            items = self._fetch_from_html()

        # Deduplicate by URL
        seen_urls = set()
        unique_items = []
        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                unique_items.append(item)

        return unique_items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a NOAA SBIR item."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", NOAA_SBIR_URL),
            "deadline": item.get("deadline"),
            "agency": "NOAA",
        }


def main():
    scraper = NOAASBIRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
