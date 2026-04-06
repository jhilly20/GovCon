"""ERDCWERX scraper.

Fetches current tech challenges and events from the ERDCWERX WordPress
REST API.  Category 6 = "Current" challenges.

API: https://www.erdcwerx.org/wp-json/wp/v2/posts?categories=6
Source: https://www.erdcwerx.org/category/event-tech-challenges/current/
"""

from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, clean_html, log

ERDCWERX_API = "https://www.erdcwerx.org/wp-json/wp/v2/posts"
CATEGORY_ID = 6  # "Current" tech challenges
PER_PAGE = 50


class ERDCWERXScraper(BaseScraper):
    """Scraper for ERDCWERX current tech challenges via WordPress API."""

    def __init__(self):
        super().__init__("ERDCWERX")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch current challenges from the ERDCWERX WordPress API."""
        all_posts = []
        page = 1

        while True:
            params = {
                "categories": CATEGORY_ID,
                "per_page": PER_PAGE,
                "page": page,
                "orderby": "date",
                "order": "desc",
            }
            try:
                resp = self.session.get(ERDCWERX_API, params=params, timeout=30)
                if resp.status_code == 400:
                    # No more pages
                    break
                resp.raise_for_status()
                posts = resp.json()
            except Exception as e:
                log(f"Error fetching ERDCWERX page {page}: {e}")
                break

            if not posts:
                break

            all_posts.extend(posts)
            log(f"Fetched {len(posts)} ERDCWERX posts (page {page})")

            # Check if there are more pages
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1

        return all_posts

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an ERDCWERX WordPress post."""
        title = clean_html(item.get("title", {}).get("rendered", ""))
        content_raw = item.get("content", {}).get("rendered", "")
        excerpt_raw = item.get("excerpt", {}).get("rendered", "")

        description = clean_html(excerpt_raw) if excerpt_raw else clean_html(content_raw)

        url = item.get("link", "")
        date_published = item.get("date", "")[:10]  # YYYY-MM-DD

        return {
            "title": title,
            "description": description[:2000],
            "url": url,
            "deadline": date_published,  # Use publish date as reference
            "agency": "ERDC (Army Engineer R&D Center)",
        }


def main():
    scraper = ERDCWERXScraper()
    scraper.run()


if __name__ == "__main__":
    main()
