"""ConnectWERX scraper.

Fetches active and upcoming opportunities from the ConnectWERX WordPress
site.  The WP REST API returns 404 for custom post types, so we parse
the HTML listing page directly.  Opportunities are categorised as
Active, Upcoming, or Closed — we only collect Active and Upcoming.

Source: https://www.connectwerx.org/opportunities/
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

CONNECTWERX_URL = "https://www.connectwerx.org/opportunities/"


class ConnectWERXScraper(BaseScraper):
    """Scraper for ConnectWERX opportunities (WordPress HTML)."""

    def __init__(self):
        super().__init__("ConnectWERX")

    def _parse_opportunity_card(self, card_div) -> Dict[str, Any]:
        """Parse a single opportunity card div."""
        text = card_div.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        title = ""
        deadline = None
        funding = ""
        url = CONNECTWERX_URL
        category = ""

        # First line is typically the title (e.g. "CWX-002-IEDO: ...")
        if lines:
            title = lines[0]

        # Look for category, deadline, funding in remaining lines
        for line in lines[1:]:
            if line.startswith("Categories:"):
                category = line.replace("Categories:", "").strip()
            elif "Submission Deadline" in line:
                # Extract date from "Submission Deadline: Nov. 1, 2024"
                m = re.search(r"Submission Deadlines?:\s*(.+)", line)
                if m:
                    deadline = m.group(1).strip()
            elif "Concept Papers:" in line:
                m = re.search(r"Concept Papers:\s*(.+)", line)
                if m:
                    deadline = m.group(1).strip()
            elif "Available Funding:" in line:
                funding = line.replace("Available Funding:", "").strip()

        # Extract link
        link_el = card_div.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("http"):
                url = href

        return {
            "title": title,
            "deadline": deadline,
            "funding": funding,
            "category": category,
            "url": url,
        }

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch active and upcoming opportunities from ConnectWERX."""
        try:
            resp = self.session.get(CONNECTWERX_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching ConnectWERX page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # The Avada theme puts each CWX-### opportunity in its own
        # fusion_builder_column.  The column's text contains a
        # "Categories: <status>" line that tells us whether the item is
        # Active, Upcoming, or Closed.  The three section headers
        # ("Active Opportunities" / "Upcoming" / "Closed") are separate
        # columns used for JS-toggle navigation and do NOT nest the
        # opportunity columns.

        for h1 in soup.find_all("h1"):
            text = h1.get_text(strip=True)

            # Only process CWX-### headings
            if not re.match(r"^CWX-\d", text):
                continue

            # Get the surrounding column container for details
            col = h1.find_parent(
                "div",
                class_=lambda c: c and "fusion_builder_column" in c,
            )
            if not col:
                continue

            col_text = col.get_text(separator="\n", strip=True)

            # Determine status from the "Categories:" line inside the
            # column (e.g. "Categories:\nClosed Opportunities")
            category = ""
            if "active opportunities" in col_text.lower():
                category = "active"
            elif "upcoming opportunities" in col_text.lower():
                category = "upcoming"
            elif "closed opportunities" in col_text.lower():
                category = "closed"

            # Skip closed opportunities
            if category == "closed":
                continue

            data = self._parse_opportunity_card(col)
            data["title"] = text
            data["category"] = category

            if not data.get("url") or data["url"] == CONNECTWERX_URL:
                link = h1.find_next("a", href=True)
                if link and link["href"].startswith("http"):
                    data["url"] = link["href"]

            items.append(data)

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a ConnectWERX opportunity."""
        desc = ""
        if item.get("funding"):
            desc = f"Available Funding: {item['funding']}"

        return {
            "title": item.get("title", ""),
            "description": desc[:2000],
            "url": item.get("url", CONNECTWERX_URL),
            "deadline": item.get("deadline"),
            "agency": "ConnectWERX (DOE)",
        }


def main():
    scraper = ConnectWERXScraper()
    scraper.run()


if __name__ == "__main__":
    main()
