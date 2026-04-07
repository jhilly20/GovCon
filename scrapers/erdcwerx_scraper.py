"""ERDCWERX scraper.

Fetches current tech challenges and events from the ERDCWERX WordPress
REST API.  Category 6 = "Current" challenges.  Deadline text is scraped
from the listing page HTML ("Deadline \u2014 {date}") and matched to posts
by title.

API: https://www.erdcwerx.org/wp-json/wp/v2/posts?categories=6
Source: https://www.erdcwerx.org/category/event-tech-challenges/current/
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

ERDCWERX_API = "https://www.erdcwerx.org/wp-json/wp/v2/posts"
ERDCWERX_LISTING_URL = "https://www.erdcwerx.org/category/event-tech-challenges/current/"
CATEGORY_ID = 6  # "Current" tech challenges
PER_PAGE = 50


class ERDCWERXScraper(BaseScraper):
    """Scraper for ERDCWERX current tech challenges via WordPress API."""

    def __init__(self):
        super().__init__("ERDCWERX")

    def _scrape_deadlines_from_listing(self) -> Dict[str, str]:
        """Scrape the ERDCWERX listing page for deadline text.

        The listing page contains structured deadline data inside
        ``<div class="ct-dynamic-data-layer" data-field="Deadline:...">``
        elements, immediately following an ``<h2>`` with the post title.

        Returns a dict mapping normalised title -> deadline text, e.g.
        ``{"civil works cso": "Open through December 31, 2026"}``.
        """
        deadlines: Dict[str, str] = {}
        try:
            resp = self.session.get(ERDCWERX_LISTING_URL, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for div in soup.select('div.ct-dynamic-data-layer[data-field^="Deadline"]'):
                # The deadline div text looks like "Deadline— October 30, 2026"
                raw = div.get_text(" ", strip=True)
                # Strip the leading "Deadline" + dash/em-dash
                deadline_text = re.sub(r"^[Dd]eadline\s*[\u2014\-\u2013]+\s*", "", raw).strip()

                # Find the associated title from the preceding <h2>
                heading = div.find_previous_sibling("h2")
                if not heading:
                    # Try parent context
                    parent = div.parent
                    heading = parent.find("h2") if parent else None
                if heading:
                    title_key = re.sub(r"\s+", " ", heading.get_text(strip=True).lower())
                    if deadline_text:
                        deadlines[title_key] = deadline_text
        except Exception as e:
            log(f"Error scraping ERDCWERX listing page for deadlines: {e}")

        return deadlines

    @staticmethod
    def _parse_deadline_text(text: str) -> Optional[str]:
        """Parse deadline text into a YYYY-MM-DD date string, or return the
        raw text for non-date deadlines (e.g. 'Continuously Open').

        Handles:
        - "October 30, 2026" -> "2026-10-30"
        - "Open through December 31, 2026" -> "2026-12-31"
        - "Continuously Open" -> "Continuously Open" (returned as-is)
        """
        if not text:
            return None

        # Strip leading "Open through" / "Open until" prefix to get the date
        cleaned = re.sub(r"^[Oo]pen\s+(?:through|until)\s+", "", text).strip()

        # Try common date formats
        from datetime import datetime
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Return the raw text so it can still be shown (e.g. "Continuously Open")
        return text

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch current challenges from the ERDCWERX WordPress API.

        Also scrapes the listing page to obtain real deadline text and
        attaches it to each post dict under the ``_deadline_text`` key.
        """
        # First, scrape deadlines from the listing page
        deadline_map = self._scrape_deadlines_from_listing()
        if deadline_map:
            log(f"Scraped {len(deadline_map)} deadlines from ERDCWERX listing page")

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

            # Attach deadline text from the listing page to each post
            for post in posts:
                title_key = re.sub(
                    r"\s+", " ",
                    clean_html(post.get("title", {}).get("rendered", "")).lower(),
                )
                post["_deadline_text"] = deadline_map.get(title_key, "")

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

        # Use the real deadline scraped from the listing page
        deadline_text = item.get("_deadline_text", "")
        deadline = self._parse_deadline_text(deadline_text)

        return {
            "title": title,
            "description": description[:2000],
            "url": url,
            "deadline": deadline,
            "agency": "ERDC (Army Engineer R&D Center)",
        }


def main():
    scraper = ERDCWERXScraper()
    scraper.run()


if __name__ == "__main__":
    main()
