"""Colosseum (ONI – One Nation Innovation) Marketplace scraper.

Fetches open challenges from the Colosseum marketplace.  The site is a
Next.js app that requires authentication, so Selenium headless is used
to log in and extract challenge data.

Source: https://marketplace.gocolosseum.org/dashboard/challenges

Credentials are expected as environment variables:
  COLOSSEUM_EMAIL
  COLOSSEUM_PASSWORD
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, log

COLOSSEUM_LOGIN_URL = "https://marketplace.gocolosseum.org/auth/login"
COLOSSEUM_CHALLENGES_URL = (
    "https://marketplace.gocolosseum.org/dashboard/challenges"
)
COLOSSEUM_BASE = "https://marketplace.gocolosseum.org"


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
    driver.set_page_load_timeout(45)
    return driver


class ColosseumScraper(BaseScraper):
    """Scraper for Colosseum marketplace challenges (login-required)."""

    def __init__(self):
        super().__init__("Colosseum")
        self.email = os.getenv("COLOSSEUM_EMAIL", "")
        self.password = os.getenv("COLOSSEUM_PASSWORD", "")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch challenges from Colosseum marketplace via Selenium login."""
        if not self.email or not self.password:
            log("ERROR: COLOSSEUM_EMAIL and COLOSSEUM_PASSWORD must be set")
            return []

        try:
            driver = _get_selenium_driver()
        except Exception as e:
            log(f"Error initializing Selenium driver: {e}")
            return []

        items: List[Dict[str, Any]] = []

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            wait = WebDriverWait(driver, 20)

            # Step 1: Login
            log("Navigating to Colosseum login page...")
            driver.get(COLOSSEUM_LOGIN_URL)
            time.sleep(3)

            # Fill email
            email_field = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='email' i]")
                )
            )
            email_field.clear()
            email_field.send_keys(self.email)

            # Fill password
            password_field = driver.find_element(
                By.CSS_SELECTOR, "input[type='password']"
            )
            password_field.clear()
            password_field.send_keys(self.password)

            # Submit
            login_btn = driver.find_element(
                By.CSS_SELECTOR, "button[type='submit'], button:not([type])"
            )
            login_btn.click()
            log("Submitted login credentials...")
            time.sleep(5)

            # Step 2: Navigate to challenges page
            log("Navigating to challenges dashboard...")
            driver.get(COLOSSEUM_CHALLENGES_URL)
            time.sleep(5)

            # Step 3: Extract challenge cards
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
                    # Filter for elements that look like challenge cards
                    for elem in elems:
                        text = elem.text.strip()
                        if text and len(text) > 20:
                            challenge_elements.append(elem)
                    if challenge_elements:
                        log(f"Found {len(challenge_elements)} challenges using selector: {sel}")
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
                    url = COLOSSEUM_CHALLENGES_URL
                    for le in link_elems:
                        href = le.get_attribute("href") or ""
                        if href and "challenge" in href.lower():
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
                # Get page body as fallback
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
            "url": item.get("url", COLOSSEUM_CHALLENGES_URL),
            "deadline": None,
            "agency": "ONI (One Nation Innovation)",
        }


def main():
    scraper = ColosseumScraper()
    scraper.run()


if __name__ == "__main__":
    main()
