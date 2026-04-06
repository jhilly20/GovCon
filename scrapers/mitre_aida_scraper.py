"""MITRE AiDA OTA Consortia Opportunities scraper.

Scrapes the MITRE AiDA "Existing OT Consortia" page to discover
consortia and their "Current Opportunities" links, then follows each
link to extract open opportunities.  Each opportunity title is prepended
with the consortium name so users know which consortium manages it.

Source: https://aida.mitre.org/ota/existing-ota-consortia/
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, clean_html, log

AIDA_URL = "https://aida.mitre.org/ota/existing-ota-consortia/"

# Known consortium -> opportunity URL mapping (extracted from AiDA page).
# The scraper will also attempt to dynamically discover these.
KNOWN_CONSORTIA: Dict[str, str] = {
    "Cornerstone Consortium": "https://cornerstone.army.mil/",
    "CWMD Consortium": "https://www.cwmdconsortium.org/business-opportunities/",
    "Defense Electronics Consortium (DEC)": "https://www.deconsortium.org/projects/",
    "Defense Industrial Base Consortium (DIBC)": "https://www.dibconsortium.org/solicitations/",
    "DoD Ordnance Technology Consortium (DOTC)": "https://nac-dotc.org/opportunities/",
    "Medical CBRN Defense Consortium (MCDC)": "https://www.medcbrn.org/solicitations/",
    "National Spectrum Consortium (NSC)": "https://www.nationalspectrumconsortium.org/solicitations/",
    "University Consortium for Applied Hypersonics (UCAH)": "https://hypersonics.tamu.edu/project-call/",
    "Vertical Lift Consortium (VLC)": "https://www.verticalliftconsortium.org/opportunities/",
    "Aviation & Missile Technology Consortium (AMTC)": "https://www.amtcenterprise.org/opportunities/",
    "Space Enterprise Consortium (SpEC)": "https://space-enterprise.org/opportunities/",
    "Consortium Management Group (CMG)": "https://cmgcorp.org/cmg-opportunities/",
    "Medical Technologies Enterprise Consortium (MTEC)": "https://www.mtec-sc.org/solicitations/",
    "National Advanced Mobility Consortium (NAMC)": "https://www.namconsortium.org/opportunities",
    "Training and Readiness Accelerator II (TReX)": "https://www.trexii.org/opportunities/",
    "Expeditionary Missions Consortium (EMC2)": "https://www.emccrane.org/solicitations/",
    "IWRP Consortium": "https://www.theiwrp.org/ota/opportunities/",
    "Marine Sustainment Technology and Innovation Consortium (MSTIC)": "https://www.mstic.org/opportunities/",
    "Naval Aviation Systems Consortium (NASC)": "https://nascsolutions.tech/opportunities/",
    "Naval Surface Technology and Innovation Consortium (NSTIC)": "https://www.nstic.org/opportunities/",
    "S2MARTS": "https://s2marts.org/opportunities/",
    "NSTXL": "https://nstxl.org/nstxl-opportunities/",
    "HSTech Consortium": "https://bstc.ati.org/opportunities/",
    "Rapid Response Partnership Vehicle (RRPV)": "https://www.rrpv.org/opportunities/",
}

REQUEST_DELAY = 1.5  # seconds between requests to be polite


class MITREAiDAScraper(BaseScraper):
    """Scraper for OTA consortia opportunities via MITRE AiDA."""

    def __init__(self):
        super().__init__("MITRE AiDA")

    def _discover_consortia(self) -> Dict[str, str]:
        """Dynamically discover consortium opportunity URLs from AiDA page."""
        consortia: Dict[str, str] = dict(KNOWN_CONSORTIA)

        try:
            resp = self.session.get(AIDA_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log(f"Error fetching AiDA page: {e}")
            return consortia

        soup = BeautifulSoup(resp.text, "html.parser")
        all_links = soup.find_all("a", href=True)

        current_name = None
        for a in all_links:
            text = a.get_text(strip=True)
            href = a["href"]

            if "mitre.org" in href and "Current Opportunities" not in text:
                continue

            # Identify consortium name links
            if (
                any(kw in text for kw in ["Consortium", "WERX", "S2MARTS", "NSTXL", "SpEC", "MTEC"])
                and href.startswith("http")
            ):
                current_name = text

            # Identify opportunity links
            if "Current Opportunities" in text and href.startswith("http") and current_name:
                # Clean up NSTXL URL (remove tracking params)
                clean_href = re.sub(r"\?.*$", "", href)
                consortia[current_name] = clean_href

        return consortia

    def _scrape_opportunities_page(
        self, consortium_name: str, url: str
    ) -> List[Dict[str, Any]]:
        """Scrape a single consortium's opportunities page."""
        items: List[Dict[str, Any]] = []

        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            if resp.status_code != 200:
                log(f"  {consortium_name}: HTTP {resp.status_code}")
                return []
        except Exception as e:
            log(f"  {consortium_name}: Error fetching {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strategy 1: Look for WordPress REST API (many consortium sites use WP)
        wp_items = self._try_wordpress_api(url, consortium_name)
        if wp_items:
            return wp_items

        # Strategy 2: Look for cards/articles/list items with opportunity data
        selectors = [
            "article",
            ".opportunity",
            ".solicitation",
            ".project-card",
            ".card",
            "table tr",
            ".entry-content li",
            ".wp-block-post",
        ]

        for sel in selectors:
            elements = soup.select(sel)
            for elem in elements:
                text = elem.get_text(separator=" ", strip=True)
                if not text or len(text) < 20:
                    continue

                # Get title
                title_el = elem.find(["h2", "h3", "h4", "a", "strong"])
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    title = lines[0] if lines else text[:100]

                # Skip generic navigation or footer text
                if any(skip in title.lower() for skip in [
                    "menu", "footer", "copyright", "privacy", "contact",
                    "home", "about", "how to join", "current members",
                ]):
                    continue

                # Get link
                link_el = elem.find("a", href=True)
                opp_url = url
                if link_el:
                    href = link_el["href"]
                    if href.startswith("http"):
                        opp_url = href
                    elif href.startswith("/"):
                        # Build absolute URL
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        opp_url = f"{parsed.scheme}://{parsed.netloc}{href}"

                # Extract deadline if present
                deadline = None
                date_match = re.search(
                    r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\w+ \d{1,2},?\s*\d{4})",
                    text,
                )
                if date_match:
                    deadline = date_match.group(1)

                items.append({
                    "consortium": consortium_name,
                    "title": title,
                    "url": opp_url,
                    "deadline": deadline,
                    "description": text[:2000],
                })

            if items:
                break

        # If still nothing, check if the page has any meaningful content at all
        if not items:
            page_text = soup.get_text(separator=" ", strip=True)
            # Check for "no opportunities" messages
            no_opp_phrases = [
                "no current", "no open", "no active", "check back",
                "no opportunities", "none at this time",
            ]
            has_no_opps = any(phrase in page_text.lower() for phrase in no_opp_phrases)
            if has_no_opps:
                log(f"  {consortium_name}: No current opportunities listed")
            else:
                log(f"  {consortium_name}: Could not parse opportunities from page")

        return items

    def _try_wordpress_api(
        self, site_url: str, consortium_name: str
    ) -> List[Dict[str, Any]]:
        """Try WordPress REST API for the consortium site."""
        from urllib.parse import urlparse

        parsed = urlparse(site_url)
        wp_api_url = f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/posts"

        try:
            resp = self.session.get(
                wp_api_url, params={"per_page": 20}, timeout=15
            )
            if resp.status_code != 200:
                return []

            posts = resp.json()
            if not isinstance(posts, list):
                return []

            items = []
            for post in posts:
                title = clean_html(post.get("title", {}).get("rendered", ""))
                if not title:
                    continue
                excerpt = clean_html(post.get("excerpt", {}).get("rendered", ""))
                link = post.get("link", site_url)
                date_str = post.get("date", "")[:10]

                items.append({
                    "consortium": consortium_name,
                    "title": title,
                    "url": link,
                    "deadline": date_str,
                    "description": excerpt[:2000],
                })

            if items:
                log(f"  {consortium_name}: Found {len(items)} items via WordPress API")
            return items

        except Exception:
            return []

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Discover consortia and scrape their opportunity pages."""
        consortia = self._discover_consortia()
        log(f"Discovered {len(consortia)} consortia with opportunity pages")

        all_items: List[Dict[str, Any]] = []

        for name, url in consortia.items():
            log(f"Scraping {name}: {url}")
            items = self._scrape_opportunities_page(name, url)
            all_items.extend(items)
            time.sleep(REQUEST_DELAY)

        log(f"Total opportunities found across all consortia: {len(all_items)}")
        return all_items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields, prepending consortium name to title."""
        consortium = item.get("consortium", "")
        title = item.get("title", "")

        # Prepend consortium name so user knows eligibility
        full_title = f"[{consortium}] {title}" if consortium else title

        return {
            "title": full_title,
            "description": item.get("description", "")[:2000],
            "url": item.get("url", AIDA_URL),
            "deadline": item.get("deadline"),
            "agency": f"OTA Consortium: {consortium}" if consortium else "OTA Consortium",
        }


def main():
    scraper = MITREAiDAScraper()
    scraper.run()


if __name__ == "__main__":
    main()
