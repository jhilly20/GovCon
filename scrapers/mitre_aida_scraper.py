"""MITRE AiDA OTA Consortia scraper.

Scrapes the MITRE AiDA "Existing OT Consortia" page to discover all
known OTA consortia, then follows each consortium's website link to
find current opportunities.  Opportunity titles are prepended with
the consortium name so downstream consumers know which consortium
the opportunity belongs to.

Source: https://aida.mitre.org/ota/existing-ota-consortia/
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

AIDA_URL = "https://aida.mitre.org/ota/existing-ota-consortia/"

# Known consortium opportunity page patterns
# Maps consortium name fragments to their known opportunity page URLs
KNOWN_OPPORTUNITY_PAGES = {
    "cornerstone": "https://cornerstone.army.mil/",
    "nstxl": "https://nstxl.org/opportunities/",
    "s2marts": "https://s2marts.org/opportunities/",
    "mtec": "https://mtec-sc.org/how-to-work-with-us/",
    "cwmd": "https://cwmdconsortium.org/opportunities/",
    "tradewind": "https://www.tradewindai.com/opportunities",
    "space enterprise": "https://space-enterprise.org/",
    "defensewerx": "https://www.defensewerx.org/opportunities",
}


class MITREAiDAScraper(BaseScraper):
    """Scraper for OTA consortia opportunities via MITRE AiDA."""

    def __init__(self):
        super().__init__("MITRE AiDA")

    def _parse_consortia(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Parse the AiDA page to extract consortium names and URLs."""
        consortia = []
        seen_names = set()

        # The page uses Divi theme with et_pb_text modules
        # Each consortium has an h5 with a link, followed by description
        for h5 in soup.find_all("h5"):
            link = h5.find("a", href=True)
            if not link:
                continue

            name = link.get_text(strip=True)
            url = link["href"]

            if not name or len(name) < 3:
                continue
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            # Get the sponsor info from following paragraphs
            sponsor = ""
            parent = h5.find_parent("div", class_="et_pb_text_inner")
            if parent:
                for p in parent.find_all("p"):
                    text = p.get_text(strip=True)
                    if "Government Sponsor:" in text:
                        sponsor = text.replace("Government Sponsor:", "").strip()
                        break

            # Get focus/mission from toggle content
            focus = ""
            toggle = h5.find_parent("div", class_="et_pb_text")
            if toggle:
                next_toggle = toggle.find_next_sibling(
                    "div", class_="et_pb_toggle"
                )
                if next_toggle:
                    focus_text = next_toggle.get_text(strip=True)
                    if len(focus_text) > 20:
                        focus = focus_text[:500]

            consortia.append({
                "name": name,
                "url": url,
                "sponsor": sponsor,
                "focus": focus,
            })

        return consortia

    def _scrape_consortium_opportunities(
        self, name: str, url: str
    ) -> List[Dict[str, Any]]:
        """Try to scrape opportunities from a consortium website."""
        items = []
        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                return items

            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True).lower()

            # Skip sites that are clearly not opportunity listings
            if len(resp.text) < 1000:
                return items

            # Look for opportunity/solicitation links
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]

                if not text or len(text) < 10 or len(text) > 200:
                    continue

                # Filter for opportunity-related links
                text_lower = text.lower()
                if not any(
                    kw in text_lower
                    for kw in [
                        "opportunity",
                        "solicitation",
                        "rpp",
                        "call",
                        "challenge",
                        "prototype",
                        "project",
                        "open",
                        "submit",
                        "apply",
                        "rfp",
                        "rfi",
                        "baa",
                    ]
                ):
                    continue

                # Skip navigation/footer links
                if any(
                    skip in text_lower
                    for skip in [
                        "learn more about",
                        "contact",
                        "about us",
                        "privacy",
                        "login",
                        "sign",
                        "menu",
                        "home",
                    ]
                ):
                    continue

                if href.startswith("/"):
                    # Make relative URL absolute
                    from urllib.parse import urljoin
                    full_url = urljoin(url, href)
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue

                items.append({
                    "title": f"[{name}] {text}",
                    "url": full_url,
                    "consortium": name,
                    "description": "",
                    "deadline": None,
                })

        except Exception as e:
            log(f"Error scraping {name} ({url}): {e}")

        return items

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch consortia from AiDA and scrape each for opportunities."""
        try:
            resp = self.session.get(AIDA_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching MITRE AiDA page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        consortia = self._parse_consortia(soup)
        log(f"Discovered {len(consortia)} OTA consortia from AiDA")

        all_items = []

        # Also add the consortia themselves as items (so we track them)
        for c in consortia:
            all_items.append({
                "title": f"[{c['name']}] OTA Consortium",
                "url": c["url"],
                "consortium": c["name"],
                "description": f"Sponsor: {c['sponsor']}. {c['focus']}"[:2000],
                "deadline": None,
                "is_consortium_entry": True,
            })

        # Scrape a subset of consortia for live opportunities
        # Prioritise known opportunity pages and limit to avoid timeouts
        scraped_count = 0
        max_scrape = 15  # Limit to avoid long runtime

        for c in consortia:
            if scraped_count >= max_scrape:
                break

            url = c["url"]
            name = c["name"]

            # Check if we have a known opportunity page
            for key, opp_url in KNOWN_OPPORTUNITY_PAGES.items():
                if key in name.lower():
                    url = opp_url
                    break

            opps = self._scrape_consortium_opportunities(name, url)
            if opps:
                log(f"  {name}: {len(opps)} potential opportunities")
                all_items.extend(opps)

            scraped_count += 1
            time.sleep(0.5)  # Rate limit

        return all_items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from an AiDA/consortium item."""
        consortium = item.get("consortium", "OTA")
        return {
            "title": item.get("title", ""),
            "description": item.get("description", "")[:2000],
            "url": item.get("url", AIDA_URL),
            "deadline": item.get("deadline"),
            "agency": f"OTA — {consortium}",
        }


def main():
    scraper = MITREAiDAScraper()
    scraper.run()


if __name__ == "__main__":
    main()
