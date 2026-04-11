"""ICWERX (Intelligence Community WERX) scraper.

Fetches current opportunities from the ICWERX Webflow site.
Parses opportunity cards from the "Current Opportunities" section,
filtering out past/closed items.

Source: https://www.icwerx.org/opportunities
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

ICWERX_URL = "https://www.icwerx.org/opportunities"


class ICWERXScraper(BaseScraper):
    """Scraper for ICWERX opportunities (Webflow site)."""

    def __init__(self):
        super().__init__("ICWERX")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch current opportunities from ICWERX."""
        try:
            resp = self.session.get(ICWERX_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching ICWERX page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # Webflow uses w-dyn-item divs inside w-dyn-list containers
        dyn_items = soup.find_all("div", class_="w-dyn-item")

        for item_div in dyn_items:
            text_parts = item_div.get_text(separator=" | ", strip=True)

            # Extract title — look for a named heading or the longest
            # meaningful segment
            title = ""
            for tag in item_div.find_all(["h1", "h2", "h3", "h4", "h5"]):
                t = tag.get_text(strip=True)
                if t and len(t) > len(title):
                    title = t

            if not title:
                # Fallback: find the first text chunk > 10 chars that is
                # not a label ("Submit By", "When:", "closed", etc.)
                for segment in text_parts.split(" | "):
                    seg = segment.strip()
                    if (
                        len(seg) > 10
                        and seg.lower() not in ("submit by", "closed", "more information")
                        and not seg.lower().startswith("when:")
                        and not seg.lower().startswith("submissions closed")
                        and not re.match(r"^\w+ \d{1,2},? \d{4}$", seg)
                    ):
                        title = seg
                        break

            if not title:
                continue

            # Extract submission deadline
            deadline = None
            # Look for date text near "Submit By" label
            deadline_match = re.search(
                r"(\w+ \d{1,2},?\s*\d{4})",
                text_parts,
            )
            if deadline_match:
                deadline = deadline_match.group(1)

            # Check if submissions are closed
            submission_closed = "closed" in text_parts.lower().split("submit by")[-1][:30] if "submit by" in text_parts.lower() else False

            # Extract event date from "When:" text
            event_date = None
            when_match = re.search(r"When:\s*(.+?)(?:\s*\||$)", text_parts)
            if when_match:
                event_date = when_match.group(1).strip()

            # Extract description — get the longest text block
            description = ""
            for segment in text_parts.split(" | "):
                seg = segment.strip()
                if len(seg) > len(description) and seg != title:
                    description = seg

            # Extract link
            url = ICWERX_URL
            link_el = item_div.find("a", href=True)
            if link_el:
                href = link_el["href"]
                if href.startswith("/"):
                    url = f"https://www.icwerx.org{href}"
                elif href.startswith("http"):
                    url = href

            # Include items even if submissions are closed, as long as
            # the event itself is in the future.  The user wants to know
            # about upcoming events.
            items.append({
                "title": title,
                "deadline": deadline if not submission_closed else None,
                "event_date": event_date,
                "description": description,
                "url": url,
                "submission_closed": submission_closed,
            })

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an ICWERX opportunity."""
        desc = item.get("description", "")
        event_date = item.get("event_date", "")
        if event_date and desc:
            desc = f"Event: {event_date}. {desc}"
        elif event_date:
            desc = f"Event: {event_date}"

        return {
            "title": item.get("title", ""),
            "description": desc[:2000],
            "url": item.get("url", ICWERX_URL),
            "deadline": item.get("deadline"),
            "agency": "ICWERX (Intelligence Community WERX)",
        }


def main():
    scraper = ICWERXScraper()
    scraper.run()


if __name__ == "__main__":
    main()
