"""ARPA-E Funding Opportunity Announcements (FOA) scraper.

Scrapes open FOAs from the ARPA-E eXCHANGE portal.  The page is an
ASP.NET WebForms application that server-renders all FOA groups in
``<div class="foaGroup">`` elements.

No authentication required.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

ARPA_E_URL = "https://arpa-e-foa.energy.gov/Default.aspx"
ARPA_E_BASE = "https://arpa-e-foa.energy.gov"


class ARPAEScraper(BaseScraper):
    """Scraper for ARPA-E Funding Opportunity Announcements."""

    def __init__(self):
        super().__init__("ARPA-E")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch and parse the ARPA-E FOA listing page."""
        try:
            resp = self.session.get(ARPA_E_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching ARPA-E page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # FOA groups are in <div class="foaGroup"> elements
        foa_groups = soup.find_all("div", class_="foaGroup")
        log(f"ARPA-E: found {len(foa_groups)} FOA groups")

        items = []
        for fg in foa_groups:
            item = self._parse_foa_group(fg)
            if item:
                items.append(item)

        return items

    def _parse_foa_group(self, fg) -> Dict[str, Any] | None:
        """Parse a single foaGroup div into an item dict.

        Each ``foaGroup`` contains:
        - ``<h2 class="hp">`` with the FOA number and title
          (e.g. "DE-FOA-0003467: Seeding Critical Advances ...")
        - ``<div class="program_highlights">`` with description, Apply link,
          and document links
        """
        # Extract FOA number and title from the <h2 class="hp"> header
        h2 = fg.find("h2", class_="hp")
        if not h2:
            return None

        header_text = h2.get_text(strip=True)
        if not header_text:
            return None

        # Split "FOA-NUMBER: Title" on the first colon
        foa_number = ""
        foa_title = header_text
        if ":" in header_text:
            parts = header_text.split(":", 1)
            foa_number = parts[0].strip()
            foa_title = parts[1].strip()

        # Description from program_highlights div
        highlights = fg.find("div", class_="program_highlights")
        description = ""
        if highlights:
            # Get the foaDescription sub-div if present
            desc_el = highlights.find("div", class_="foaDescription")
            if desc_el:
                description = desc_el.get_text(strip=True)
            else:
                description = highlights.get_text(strip=True)

        # Documents section for dates
        docs_el = highlights.find("div", class_="foaDocs") if highlights else None
        docs_text = docs_el.get_text(strip=True) if docs_el else ""

        # Try to extract deadline from all available text
        all_text = description + " " + docs_text
        if highlights:
            all_text += " " + highlights.get_text(strip=True)
        deadline = self._extract_deadline(all_text)

        # Check for Apply button (indicates open FOA)
        apply_link = fg.find("a", string=re.compile(r"Apply", re.IGNORECASE))
        has_apply = apply_link is not None

        # Build URL from the h2 link or Apply link
        url = ARPA_E_URL
        h2_link = h2.find("a", href=True)
        if h2_link:
            href = h2_link["href"]
            if not href.startswith("http"):
                url = f"{ARPA_E_BASE}/{href}"
            else:
                url = href

        title = f"[{foa_number}] {foa_title}" if foa_number else foa_title

        return {
            "title": title,
            "url": url,
            "description": description,
            "foa_number": foa_number,
            "deadline_raw": deadline,
            "has_apply": has_apply,
            "docs_text": docs_text,
        }

    def _extract_deadline(self, text: str) -> str | None:
        """Try to extract a deadline date from text."""
        # Look for common date patterns
        # "Full Application Deadline: MM/DD/YYYY"
        # "Deadline: Month DD, YYYY"
        # "Due: MM/DD/YYYY HH:MM PM ET"
        patterns = [
            r"(?:Deadline|Due|Close)[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
            r"(?:Deadline|Due|Close)[:\s]*(\w+\s+\d{1,2},?\s+\d{4})",
            r"FA\s+Deadline[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an ARPA-E FOA."""
        desc = item.get("description", "")
        docs = item.get("docs_text", "")
        if docs:
            desc = f"{desc}\n\nDocuments: {docs}" if desc else docs

        return {
            "title": item.get("title", ""),
            "description": clean_html(desc)[:2000],
            "url": item.get("url", ""),
            "deadline": item.get("deadline_raw"),
            "agency": "DOE ARPA-E",
        }


def main():
    scraper = ARPAEScraper()
    scraper.run()


if __name__ == "__main__":
    main()
