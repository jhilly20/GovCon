"""DHS SBIR (Small Business Innovation Research) scraper.

Fetches open SBIR topics from the DHS Office of Innovation & Partnerships.
The site is Cloudflare-protected, so Selenium headless is used.

Source: https://oip.dhs.gov/sbir/public

Fallback: If Cloudflare blocks headless access, the scraper attempts to
scrape DHS SBIR topics from sbir.gov instead.
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, clean_html, log

DHS_SBIR_URL = "https://oip.dhs.gov/sbir/public"
DHS_SBIR_FALLBACK_URL = "https://www.sbir.gov/sbirsearch/topic/current/?agency=DHS"


def _get_selenium_driver():
    """Create a headless Selenium Chrome driver."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


class DHSSBIRScraper(BaseScraper):
    """Scraper for DHS SBIR open topics."""

    def __init__(self):
        super().__init__("DHS SBIR")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch DHS SBIR topics, trying primary site first then fallback."""
        items = self._fetch_primary()
        if not items:
            log("Primary DHS SBIR site blocked or empty, trying fallback...")
            items = self._fetch_fallback()
        return items

    def _fetch_primary(self) -> List[Dict[str, Any]]:
        """Try to scrape DHS SBIR from oip.dhs.gov using Selenium."""
        try:
            driver = _get_selenium_driver()
        except Exception as e:
            log(f"Error initializing Selenium driver: {e}")
            return []

        items: List[Dict[str, Any]] = []

        try:
            from selenium.webdriver.common.by import By

            log("Loading DHS SBIR page...")
            driver.get(DHS_SBIR_URL)
            time.sleep(5)

            page_text = driver.find_element(By.TAG_NAME, "body").text
            page_title = driver.title

            # Check if Cloudflare blocked us
            if "just a moment" in page_title.lower() or "cloudflare" in page_text.lower():
                log("Cloudflare challenge detected, falling back")
                return []

            # Look for topic cards or table rows
            selectors = [
                "[class*='topic']",
                "[class*='solicitation']",
                "table tr",
                ".card",
                "article",
            ]

            for sel in selectors:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                for elem in elems:
                    text = elem.text.strip()
                    if text and len(text) > 30:
                        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                        if lines:
                            # Get link
                            link_elems = elem.find_elements(By.TAG_NAME, "a")
                            url = DHS_SBIR_URL
                            for le in link_elems:
                                href = le.get_attribute("href") or ""
                                if href.startswith("http"):
                                    url = href
                                    break

                            items.append({
                                "title": lines[0],
                                "url": url,
                                "full_text": text[:3000],
                            })
                if items:
                    break

        except Exception as e:
            log(f"Error scraping primary DHS SBIR: {e}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return items

    def _fetch_fallback(self) -> List[Dict[str, Any]]:
        """Fallback: try to get DHS topics from sbir.gov."""
        try:
            resp = self.session.get(DHS_SBIR_FALLBACK_URL, timeout=30)
            if resp.status_code != 200:
                log(f"Fallback sbir.gov returned status {resp.status_code}")
                return []

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "html.parser")
            items = []

            # Look for topic listings
            topic_rows = soup.find_all("tr")
            for row in topic_rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    title = cells[0].get_text(strip=True)
                    link = cells[0].find("a", href=True)
                    url = link["href"] if link else DHS_SBIR_FALLBACK_URL
                    if not url.startswith("http"):
                        url = "https://www.sbir.gov" + url

                    items.append({
                        "title": title,
                        "url": url,
                        "full_text": " ".join(c.get_text(strip=True) for c in cells),
                    })

            return items

        except Exception as e:
            log(f"Error fetching DHS SBIR fallback: {e}")
            return []

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a DHS SBIR topic."""
        title = item.get("title", "")
        full_text = item.get("full_text", "")

        description = ""
        if full_text:
            lines = [ln.strip() for ln in full_text.split("\n") if len(ln.strip()) > 20]
            description = " ".join(lines[1:5])[:2000]

        # Try to extract deadline from text
        deadline = None
        date_patterns = [
            r"(?:close|due|deadline)[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
            r"(?:close|due|deadline)[:\s]*(\w+ \d{1,2},?\s*\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                deadline = match.group(1)
                break

        return {
            "title": f"DHS SBIR: {title}" if title else "",
            "description": description,
            "url": item.get("url", DHS_SBIR_URL),
            "deadline": deadline,
            "agency": "DHS (Dept. of Homeland Security)",
        }


def main():
    scraper = DHSSBIRScraper()
    scraper.run()


if __name__ == "__main__":
    main()
