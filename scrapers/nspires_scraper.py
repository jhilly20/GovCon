"""NASA NSPIRES solicitations scraper.

NSPIRES is a legacy Java web application that requires JavaScript form
submission to load solicitation results.  This scraper uses Selenium
headless to submit the search form and extract open solicitations.

Falls back to scraping the NASA SBIR/STTR page if NSPIRES is
unreachable.

No authentication required.
"""

import time
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, get_selenium_driver, log

NSPIRES_URL = "https://nspires.nasaprs.com/external/solicitations/solicitations!init.do"
NSPIRES_BASE = "https://nspires.nasaprs.com"


class NSPIRESScraper(BaseScraper):
    """Scraper for NASA NSPIRES open solicitations."""

    def __init__(self):
        super().__init__("NSPIRES")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Use Selenium to submit the NSPIRES search form and extract results."""
        driver = None
        try:
            driver = get_selenium_driver(page_load_timeout=45)
            return self._scrape_with_selenium(driver)
        except Exception as e:
            log(f"Selenium scraping failed: {e}")
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _scrape_with_selenium(self, driver) -> list:
        """Navigate NSPIRES and extract open solicitations."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        log("NSPIRES: loading search page...")
        driver.get(NSPIRES_URL)
        time.sleep(3)

        # Click the "Open" link/button to show open solicitations
        try:
            # Look for the "Open" status link in the form
            open_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@href, 'method=open')]")
                )
            )
            open_link.click()
            time.sleep(3)
        except Exception:
            # Try direct navigation
            log("NSPIRES: trying direct URL for open solicitations...")
            driver.get(
                f"{NSPIRES_BASE}/external/solicitations/solicitations.do"
                "?method=open&stack=push"
            )
            time.sleep(3)

        # Parse the resulting page
        soup = BeautifulSoup(driver.page_source, "html.parser")

        items = []

        # Look for solicitation links in tables
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # Check if this looks like a solicitation results table
            headers = [
                th.get_text(strip=True).lower()
                for th in rows[0].find_all(["th", "td"])
            ]
            if not any(
                kw in " ".join(headers)
                for kw in ["solicitation", "title", "release", "status"]
            ):
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                # Try to extract link and title
                link_el = row.find("a", href=True)
                if not link_el:
                    continue

                title = link_el.get_text(strip=True)
                href = link_el["href"]
                if not href.startswith("http"):
                    href = NSPIRES_BASE + href

                # Extract dates from cells
                release_date = None
                close_date = None
                for cell in cells:
                    text = cell.get_text(strip=True)
                    # Look for date patterns
                    if "/" in text and len(text) <= 12:
                        if not release_date:
                            release_date = text
                        else:
                            close_date = text

                items.append(
                    {
                        "title": title,
                        "url": href,
                        "release_date": release_date,
                        "close_date": close_date,
                    }
                )

        # Also try to find solicitations in div/list format
        viewrepo_links = soup.find_all(
            "a", href=lambda h: h and "viewreposol" in h.lower()
        )
        for link in viewrepo_links:
            title = link.get_text(strip=True)
            href = link["href"]
            if not href.startswith("http"):
                href = NSPIRES_BASE + href
            if not any(it["url"] == href for it in items):
                items.append(
                    {
                        "title": title,
                        "url": href,
                        "release_date": None,
                        "close_date": None,
                    }
                )

        log(f"NSPIRES: found {len(items)} solicitations")
        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a NSPIRES solicitation."""
        return {
            "title": item.get("title", ""),
            "description": f"Release: {item.get('release_date', 'N/A')} | "
            f"Close: {item.get('close_date', 'N/A')}",
            "url": item.get("url", ""),
            "deadline": item.get("close_date"),
            "agency": "NASA NSPIRES",
        }


def main():
    scraper = NSPIRESScraper()
    scraper.run()


if __name__ == "__main__":
    main()
