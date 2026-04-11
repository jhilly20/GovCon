"""DOE Office of Science SBIR/STTR scraper.

Fetches funding opportunity schedule from the DOE Office of Science
SBIR program page.  The page contains Phase I and Phase II schedule
tables with dates for topics, FOAs, and deadlines.

Source: https://science.osti.gov/sbir/Funding-Opportunities
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

DOE_SBIR_BASE = "https://science.osti.gov/sbir/Funding-Opportunities"
DOE_SBIR_URLS = [
    "https://science.osti.gov/sbir/Funding-Opportunities/FY-2026",
    "https://science.osti.gov/sbir/Funding-Opportunities/FY-2025",
]


class DOESBIRScraper(BaseScraper):
    """Scraper for DOE Office of Science SBIR/STTR funding opportunities."""

    def __init__(self):
        super().__init__("DOE SBIR")

    def _parse_schedule_table(self, table, fiscal_year: str) -> list:
        """Parse a schedule table into opportunity items."""
        items = []
        rows = table.find_all("tr")
        if not rows:
            return items

        # First row is header — get column names
        headers = []
        header_row = rows[0]
        for cell in header_row.find_all(["th", "td"]):
            headers.append(cell.get_text(strip=True))

        # Determine phase from first header cell
        phase = headers[0] if headers else "Unknown"

        # Process data rows
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label = cells[0].get_text(strip=True)

            # We're interested in rows with dates — FOA Issued, Topics Issued,
            # LOI Due, Application Due, etc.
            if not any(
                kw in label.lower()
                for kw in ["issued", "due", "webinar", "topic"]
            ):
                continue

            # Each subsequent cell represents a release (Release 1, Release 2, etc.)
            for i, cell in enumerate(cells[1:], start=1):
                cell_text = cell.get_text(strip=True)
                if not cell_text:
                    continue

                release = headers[i] if i < len(headers) else f"Release {i}"

                # Check if this is a date with a status
                is_delayed = "(Delayed)" in cell_text
                cell_text = cell_text.replace("(Delayed)", "").strip()

                # Try to extract a date
                date_match = re.search(
                    r"(\w+day,\s+)?(\w+ \d{1,2},\s*\d{4})", cell_text
                )
                date_str = date_match.group(2) if date_match else None

                title = f"DOE SC SBIR {fiscal_year} — {phase} {release}: {label}"
                if is_delayed:
                    title += " (Delayed)"

                items.append({
                    "title": title,
                    "deadline": date_str,
                    "url": DOE_SBIR_BASE,
                    "description": f"{phase} {release} — {label}: {cell_text}",
                    "phase": phase,
                    "release": release,
                })

        return items

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch DOE SBIR schedule from funding opportunity pages."""
        all_items = []

        for url in DOE_SBIR_URLS:
            # Extract fiscal year from URL
            fy_match = re.search(r"FY-(\d{4})", url)
            fiscal_year = f"FY{fy_match.group(1)}" if fy_match else "FY????"

            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                log(f"Error fetching DOE SBIR {fiscal_year} page: {e}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")

            for table in tables:
                items = self._parse_schedule_table(table, fiscal_year)
                all_items.extend(items)

            log(f"Parsed {len(tables)} tables from DOE SBIR {fiscal_year}")

        # Filter to only items with upcoming dates (FOA Due, Application Due)
        # that haven't passed yet
        relevant_items = []
        for item in all_items:
            label_lower = item.get("description", "").lower()
            # Prioritise actionable items: due dates and FOA releases
            if any(kw in label_lower for kw in ["due", "foa issued", "topics issued"]):
                relevant_items.append(item)

        return relevant_items if relevant_items else all_items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a DOE SBIR schedule item."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", DOE_SBIR_BASE),
            "deadline": item.get("deadline"),
            "agency": "DOE Office of Science",
        }


def main():
    scraper = DOESBIRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
