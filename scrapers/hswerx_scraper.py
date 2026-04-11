"""HSWERX (Homeland Security WERX) scraper.

Fetches upcoming events and opportunities from the HSWERX Webflow site.
Parses event cards from the main events page.

Source: https://www.hswerx.org/events
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

HSWERX_URL = "https://www.hswerx.org/events"
HSWERX_BASE = "https://www.hswerx.org"


class HSWERXScraper(BaseScraper):
    """Scraper for HSWERX events and opportunities (Webflow site)."""

    def __init__(self):
        super().__init__("HSWERX")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch upcoming events from HSWERX."""
        try:
            resp = self.session.get(HSWERX_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching HSWERX page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # HSWERX uses Webflow with event cards
        # Look for links to event detail pages
        all_links = soup.find_all("a", href=True)
        seen_urls = set()

        for link in all_links:
            href = link["href"]
            link_text = link.get_text(strip=True).lower()

            if "more info" not in link_text:
                continue

            if href.startswith("/"):
                full_url = HSWERX_BASE + href
            elif href.startswith("http"):
                full_url = href
            else:
                continue

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Walk up to find the event block
            block = link
            for _ in range(8):
                parent = block.find_parent("div")
                if parent:
                    block = parent
                    # Stop when we have enough context
                    text_len = len(block.get_text(strip=True))
                    if text_len > 100:
                        break

            block_text = block.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in block_text.split("\n") if l.strip()]

            # Extract title — look for the main heading
            title = ""
            for line in lines:
                if (
                    len(line) > 15
                    and line.lower() not in ("more info",)
                    and "submission" not in line.lower()
                    and not re.match(r"^Event Date:", line, re.IGNORECASE)
                ):
                    title = line
                    break

            if not title:
                continue

            # Extract event date
            event_date = None
            for line in lines:
                m = re.match(r"Event Date:\s*(.+)", line, re.IGNORECASE)
                if m:
                    event_date = m.group(1).strip()
                    break

            # Extract deadline from "Submissions closed" text
            deadline = None
            for line in lines:
                m = re.search(
                    r"[Ss]ubmissions?\s+(?:closed?|due)\s+(.+)",
                    line,
                )
                if m:
                    deadline = m.group(1).strip().rstrip(".")
                    break

            # Extract description
            description = ""
            for line in lines:
                if len(line) > 50 and line != title:
                    description = line
                    break

            items.append({
                "title": title,
                "deadline": deadline,
                "event_date": event_date,
                "description": description,
                "url": full_url,
            })

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an HSWERX event."""
        desc = item.get("description", "")
        event_date = item.get("event_date", "")
        if event_date and desc:
            desc = f"Event: {event_date}. {desc}"
        elif event_date:
            desc = f"Event: {event_date}"

        return {
            "title": item.get("title", ""),
            "description": desc[:2000],
            "url": item.get("url", HSWERX_URL),
            "deadline": item.get("deadline"),
            "agency": "HSWERX (DHS)",
        }


def main():
    scraper = HSWERXScraper()
    scraper.run()


if __name__ == "__main__":
    main()
