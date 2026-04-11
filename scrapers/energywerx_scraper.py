"""EnergyWERX scraper.

Fetches current and upcoming opportunities from the EnergyWERX Webflow
site.  Parses the "Current Opportunities" and "Upcoming Opportunities"
sections, skipping past/closed items.

Source: https://www.energywerx.org/opportunities
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

ENERGYWERX_URL = "https://www.energywerx.org/opportunities"
ENERGYWERX_BASE = "https://www.energywerx.org"


class EnergyWERXScraper(BaseScraper):
    """Scraper for EnergyWERX opportunities (Webflow site)."""

    def __init__(self):
        super().__init__("EnergyWERX")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch current and upcoming opportunities from EnergyWERX."""
        try:
            resp = self.session.get(ENERGYWERX_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching EnergyWERX page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # The page structure has sections: Current, Upcoming, Past
        # Each opportunity has a "More Info" link and deadline info
        # We look for links to /opportunities/* detail pages
        all_links = soup.find_all("a", href=True)

        seen_urls = set()
        for link in all_links:
            href = link["href"]
            link_text = link.get_text(strip=True).lower()

            # Only follow "More Info" links to opportunity detail pages
            if "more info" not in link_text:
                continue
            if not href.startswith("/opportunities/"):
                continue

            full_url = ENERGYWERX_BASE + href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Get the parent container to extract opportunity details
            parent = link.find_parent("div")
            if not parent:
                continue

            # Walk up to find the full opportunity block
            # Look for the outermost div that contains title + deadline + link
            block = parent
            for _ in range(5):
                p = block.find_parent("div")
                if p and len(p.get_text(strip=True)) < 500:
                    block = p
                else:
                    break

            block_text = block.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in block_text.split("\n") if l.strip()]

            # Check if this is a closed/past opportunity
            is_closed = False
            for line in lines:
                if line.lower().startswith("closed"):
                    is_closed = True
                    break

            if is_closed:
                continue

            # Extract title from the nearest preceding section heading
            section_heading = link.find_previous(["h1", "h2", "h3", "h4", "h5"])
            title = section_heading.get_text(strip=True) if section_heading else ""

            if not title or len(title) < 5:
                # Fallback: use the URL slug
                slug = href.rstrip("/").split("/")[-1]
                title = slug.replace("-", " ").title()

            # Extract deadline from text like "Deadline 23 Apr 3:00 pm ET 2026"
            deadline = None
            for line in lines:
                if re.match(r"^Deadline", line, re.IGNORECASE):
                    continue
                # Look for date patterns
                m = re.search(
                    r"(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s*(\d{4})",
                    " ".join(lines),
                    re.IGNORECASE,
                )
                if m:
                    day, month, year = m.group(1), m.group(2), m.group(3)
                    deadline = f"{month} {day}, {year}"
                    break

            # Check for "Coming Soon" / "TBD" deadlines
            if not deadline:
                for line in lines:
                    if "coming soon" in line.lower() or "tbd" in line.lower():
                        deadline = None
                        break

            items.append({
                "title": title,
                "deadline": deadline,
                "url": full_url,
                "description": "",
            })

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an EnergyWERX opportunity."""
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", ENERGYWERX_URL),
            "deadline": item.get("deadline"),
            "agency": "EnergyWERX (DOE)",
        }


def main():
    scraper = EnergyWERXScraper()
    scraper.run()


if __name__ == "__main__":
    main()
