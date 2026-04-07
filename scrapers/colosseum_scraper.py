"""Colosseum (ONI – One Nation Innovation) Marketplace scraper.

Fetches open challenges from the Colosseum marketplace public page.
The site is a Next.js app that renders challenge cards via client-side
JavaScript, so Selenium headless is used to render the page.

No login is required — challenges are visible on the public homepage.

Source: https://marketplace.gocolosseum.org/
"""

import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, get_selenium_driver, log

COLOSSEUM_URL = "https://marketplace.gocolosseum.org/"
COLOSSEUM_BASE = "https://marketplace.gocolosseum.org"


class ColosseumScraper(BaseScraper):
    """Scraper for Colosseum marketplace challenges (public, no login)."""

    def __init__(self):
        super().__init__("Colosseum")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch challenges from the Colosseum public homepage via Selenium."""
        try:
            driver = get_selenium_driver(page_load_timeout=45)
        except Exception as e:
            log(f"Error initializing Selenium driver: {e}")
            return []

        items: List[Dict[str, Any]] = []

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            wait = WebDriverWait(driver, 20)

            # Navigate to the public homepage which lists challenges
            log("Navigating to Colosseum public marketplace...")
            driver.get(COLOSSEUM_URL)
            time.sleep(5)

            # Scroll to the #explore-challenges section to trigger lazy loading
            driver.execute_script(
                "document.getElementById('explore-challenges')?.scrollIntoView()"
            )
            time.sleep(3)

            # Try multiple selectors for challenge cards
            selectors = [
                "[class*='challenge']",
                "[class*='card']",
                "[class*='Challenge']",
                "article",
                ".grid > div",
                "[data-testid*='challenge']",
            ]

            challenge_elements = []
            for sel in selectors:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems and len(elems) > 0:
                    for elem in elems:
                        text = elem.text.strip()
                        if text and len(text) > 20:
                            challenge_elements.append(elem)
                    if challenge_elements:
                        log(
                            f"Found {len(challenge_elements)} challenges "
                            f"using selector: {sel}"
                        )
                        break

            for elem in challenge_elements:
                try:
                    text = elem.text.strip()
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    if not lines:
                        continue

                    title = lines[0]

                    # Get link if available
                    link_elems = elem.find_elements(By.TAG_NAME, "a")
                    url = COLOSSEUM_URL
                    for le in link_elems:
                        href = le.get_attribute("href") or ""
                        if href and (
                            "challenge" in href.lower()
                            or href.startswith(COLOSSEUM_BASE)
                        ):
                            url = href
                            break

                    items.append(
                        {
                            "title": title,
                            "url": url,
                            "full_text": text[:3000],
                        }
                    )
                except Exception as e:
                    log(f"Error parsing challenge element: {e}")

            if not items:
                log("No structured challenge elements found")
                body = driver.find_element(By.TAG_NAME, "body").text
                log(f"Page body (first 500 chars): {body[:500]}")

        except Exception as e:
            log(f"Error during Colosseum scraping: {e}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a Colosseum challenge."""
        title = item.get("title", "")
        full_text = item.get("full_text", "")

        description = ""
        if full_text:
            lines = [ln.strip() for ln in full_text.split("\n") if len(ln.strip()) > 20]
            description = " ".join(lines[1:5])[:2000]

        return {
            "title": f"ONI Colosseum: {title}" if title else "",
            "description": description,
            "url": item.get("url", COLOSSEUM_URL),
            "deadline": None,
            "agency": "ONI (One Nation Innovation)",
        }


def main():
    scraper = ColosseumScraper()
    scraper.run()


if __name__ == "__main__":
    main()
