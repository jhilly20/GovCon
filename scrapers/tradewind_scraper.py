"""Tradewind AI Opportunities scraper.

Fetches open opportunities from the Tradewind AI website.  The site is
built on Wix and renders most content client-side, so Selenium headless
is required to extract opportunity data.

Source: https://www.tradewindai.com/opportunities
"""

import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, get_selenium_driver, log

TRADEWIND_URL = "https://www.tradewindai.com/opportunities"
TRADEWIND_BASE = "https://www.tradewindai.com"

# Known Tradewind sub-pages with active opportunities
TRADEWIND_OPP_PAGES = [
    "https://www.tradewindai.com/tradewinds-opportunity",
    "https://www.tradewindai.com/swarm-forge",
]


class TradewindScraper(BaseScraper):
    """Scraper for Tradewind AI opportunities using Selenium."""

    def __init__(self):
        super().__init__("Tradewind AI")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch opportunities from Tradewind AI using Selenium."""
        items: List[Dict[str, Any]] = []

        try:
            driver = get_selenium_driver()
        except Exception as e:
            log(f"Error initializing Selenium driver: {e}")
            return self._fetch_fallback()

        try:
            # First get the main opportunities page to find current links
            log("Loading Tradewind AI opportunities page...")
            driver.get(TRADEWIND_URL)
            time.sleep(5)  # Wait for Wix to render

            from selenium.webdriver.common.by import By

            # Find all links on the page that point to opportunity detail pages
            links = driver.find_elements(By.TAG_NAME, "a")
            opp_urls = set()
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.text.strip().lower()
                if (
                    href.startswith(TRADEWIND_BASE)
                    and href != TRADEWIND_URL
                    and ("opportunity" in href or "forge" in href or "marketplace" in href)
                ):
                    opp_urls.add(href)
                elif "learn more" in text and href.startswith(TRADEWIND_BASE):
                    opp_urls.add(href)

            # Add known sub-pages
            for url in TRADEWIND_OPP_PAGES:
                opp_urls.add(url)

            log(f"Found {len(opp_urls)} Tradewind opportunity pages to check")

            # Visit each opportunity page
            for url in opp_urls:
                try:
                    driver.get(url)
                    time.sleep(3)

                    title = driver.title.replace(" | Tradewind", "").strip()
                    if not title or title == "Opportunities":
                        continue

                    # Get page text content
                    body = driver.find_element(By.TAG_NAME, "body")
                    page_text = body.text[:5000]

                    items.append(
                        {
                            "title": title,
                            "url": url,
                            "page_text": page_text,
                        }
                    )
                    log(f"  Extracted: {title}")
                except Exception as e:
                    log(f"  Error loading {url}: {e}")

        except Exception as e:
            log(f"Error during Tradewind scraping: {e}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return items if items else self._fetch_fallback()

    def _fetch_fallback(self) -> List[Dict[str, Any]]:
        """Fallback: scrape what we can without Selenium from known pages."""
        items = []
        for url in TRADEWIND_OPP_PAGES:
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(resp.text, "html.parser")
                    title = soup.title.get_text(strip=True) if soup.title else ""
                    title = title.replace(" | Tradewind", "").strip()
                    if title:
                        items.append(
                            {
                                "title": title,
                                "url": url,
                                "page_text": soup.get_text(separator=" ", strip=True)[
                                    :3000
                                ],
                            }
                        )
            except Exception as e:
                log(f"Fallback error for {url}: {e}")
        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a Tradewind opportunity."""
        title = item.get("title", "")
        page_text = item.get("page_text", "")

        # Try to extract description from page text
        description = ""
        if page_text:
            # Take the first meaningful paragraph
            lines = [ln.strip() for ln in page_text.split("\n") if len(ln.strip()) > 40]
            description = " ".join(lines[:5])[:2000]

        return {
            "title": f"Tradewind: {title}" if title else "Tradewind AI Opportunity",
            "description": description,
            "url": item.get("url", TRADEWIND_URL),
            "deadline": None,
            "agency": "Tradewind AI (DoD)",
        }


def main():
    scraper = TradewindScraper()
    scraper.run()


if __name__ == "__main__":
    main()
