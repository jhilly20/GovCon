"""EERE Exchange (DOE) Funding Opportunity scraper.

Scrapes open funding opportunities from the DOE Office of Energy
Efficiency & Renewable Energy (EERE) eXCHANGE portal.  The page is an
ASP.NET WebForms application that server-renders FOA groups in
``<div class="foaGroup">`` elements — the same platform as ARPA-E.

No authentication required.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

EERE_URL = "https://eere-exchange.energy.gov/Default.aspx"
EERE_BASE = "https://eere-exchange.energy.gov"


class EEREExchangeScraper(BaseScraper):
    """Scraper for EERE Exchange funding opportunities."""

    def __init__(self):
        super().__init__("EERE Exchange")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch and parse the EERE Exchange FOA listing page."""
        try:
            resp = self.session.get(EERE_URL, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching EERE Exchange page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # FOA groups are in <div class="foaGroup"> elements
        foa_groups = soup.find_all("div", class_="foaGroup")
        log(f"EERE Exchange: found {len(foa_groups)} FOA groups")

        # Also parse the jump-to listing for FOA numbers and titles
        foa_index = self._parse_jump_to_listing(soup)

        items = []
        for fg in foa_groups:
            item = self._parse_foa_group(fg, foa_index)
            if item:
                items.append(item)

        return items

    def _parse_jump_to_listing(self, soup) -> Dict[str, str]:
        """Parse the 'Jump to an Announcement' dropdown for FOA number→title mapping."""
        index = {}
        toggle = soup.find("div", class_="divToggleContent")
        if not toggle:
            return index

        links = toggle.find_all("a", href=True)
        # Links come in pairs: FOA number, then FOA title
        i = 0
        while i < len(links) - 1:
            href = links[i].get("href", "")
            if "#FoaId" in href:
                foa_num = links[i].get_text(strip=True)
                foa_title = links[i + 1].get_text(strip=True)
                foa_id = href.lstrip("#")
                index[foa_id] = {"number": foa_num, "title": foa_title}
                i += 2
            else:
                i += 1

        return index

    def _parse_foa_group(self, fg, foa_index: Dict) -> Dict[str, Any] | None:
        """Parse a single foaGroup div into an item dict.

        Each ``foaGroup`` contains:
        - ``<h2 class="hp">`` with the FOA number and title
          (e.g. "DE-FOA-0003589: Critical Minerals & Materials ...")
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

        # Check for Apply button
        apply_link = fg.find("a", string=re.compile(r"Apply", re.IGNORECASE))
        has_apply = apply_link is not None

        # Build URL from the h2 link or default
        url = EERE_URL
        h2_link = h2.find("a", href=True)
        if h2_link:
            href = h2_link["href"]
            if not href.startswith("http"):
                url = f"{EERE_BASE}/{href}"
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
        patterns = [
            r"(?:Deadline|Due|Close)[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
            r"(?:Deadline|Due|Close)[:\s]*(\w+\s+\d{1,2},?\s+\d{4})",
            r"FA\s+Deadline[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
            r"Full\s+Application[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an EERE Exchange FOA."""
        desc = item.get("description", "")
        docs = item.get("docs_text", "")
        if docs:
            desc = f"{desc}\n\nDocuments: {docs}" if desc else docs

        return {
            "title": item.get("title", ""),
            "description": clean_html(desc)[:2000],
            "url": item.get("url", ""),
            "deadline": item.get("deadline_raw"),
            "agency": "DOE EERE",
        }


def main():
    scraper = EEREExchangeScraper()
    scraper.run()


if __name__ == "__main__":
    main()
