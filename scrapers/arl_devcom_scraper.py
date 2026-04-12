"""ARL DEVCOM funded research opportunities scraper.

Scrapes funded research opportunities from the Army Research Laboratory
DEVCOM website.  Each opportunity is an ``<a class="permalink">`` element
containing an ``<h4>`` title and a ``<div class="opportunity-description">``
sibling with the summary.

No authentication required.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

ARL_URL = "https://arl.devcom.army.mil/collaborate-with-us/avenue/funded-research/"
ARL_BASE = "https://arl.devcom.army.mil"


class ARLDevcomScraper(BaseScraper):
    """Scraper for ARL DEVCOM funded research opportunities."""

    def __init__(self):
        super().__init__("ARL DEVCOM")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch and parse the funded research page."""
        try:
            resp = self.session.get(ARL_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching ARL DEVCOM page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Each opportunity is wrapped in <a class="permalink">
        permalink_links = soup.find_all("a", class_="permalink")
        log(f"ARL DEVCOM: found {len(permalink_links)} permalink entries")

        items = []
        for link in permalink_links:
            title_el = link.find("h4")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = ARL_BASE + href

            # Description is the sibling div after the h4
            desc_el = link.find("div", class_="opportunity-description")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Extract metadata from the parent container
            parent = link.parent
            metadata = {}
            if parent:
                # Target Audience
                audience_label = parent.find(
                    string=re.compile(r"Target Audience", re.IGNORECASE)
                )
                if audience_label:
                    audience_container = audience_label.find_parent("div")
                    if audience_container:
                        metadata["audience"] = audience_container.get_text(
                            strip=True
                        ).replace("Target Audience(s):", "").strip()

                # Research Type
                rtype_label = parent.find(
                    string=re.compile(r"Research Type", re.IGNORECASE)
                )
                if rtype_label:
                    rtype_container = rtype_label.find_parent("div")
                    if rtype_container:
                        metadata["research_type"] = rtype_container.get_text(
                            strip=True
                        ).replace("Research Type(s):", "").strip()

            items.append(
                {
                    "title": title,
                    "url": href,
                    "description": description,
                    "metadata": metadata,
                }
            )

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an ARL DEVCOM opportunity."""
        metadata = item.get("metadata", {})
        desc = item.get("description", "")
        audience = metadata.get("audience", "")
        rtype = metadata.get("research_type", "")
        if audience or rtype:
            extra = []
            if audience:
                extra.append(f"Audience: {audience}")
            if rtype:
                extra.append(f"Research Type: {rtype}")
            desc = f"{desc}\n{' | '.join(extra)}" if desc else " | ".join(extra)

        return {
            "title": item.get("title", ""),
            "description": clean_html(desc)[:2000],
            "url": item.get("url", ""),
            "deadline": None,  # ARL DEVCOM doesn't list explicit deadlines
            "agency": "Army DEVCOM ARL",
        }


def main():
    scraper = ARLDevcomScraper()
    scraper.run()


if __name__ == "__main__":
    main()
