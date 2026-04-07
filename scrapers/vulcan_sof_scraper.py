"""Vulcan SOF (Special Operations Forces) scraper.

Fetches open calls/opportunities from the Vulcan SOF portal.
This site requires login to access the search page.

Source: https://vulcan-sof.com/login/ng2/search/calls

Credentials are expected as environment variables:
  VULCAN_SOF_EMAIL
  VULCAN_SOF_PASSWORD

IMPORTANT: Vulcan SOF login requires 2FA (two-factor authentication).
The scraper opens a **visible** (non-headless) browser window so the
operator can enter the 2FA code manually.  Before starting the login
flow the scraper pauses with an input() prompt so the operator can
confirm they are ready — this prevents the 2FA code from timing out
while the browser is still initialising.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, get_selenium_driver, log

VULCAN_LOGIN_URL = "https://vulcan-sof.com/login"
VULCAN_SEARCH_URL = "https://vulcan-sof.com/login/ng2/search/calls"
VULCAN_BASE = "https://vulcan-sof.com"


class VulcanSOFScraper(BaseScraper):
    """Scraper for Vulcan SOF open calls (login-required)."""

    def __init__(self):
        super().__init__("Vulcan SOF")
        self.email = os.getenv("VULCAN_SOF_EMAIL", "")
        self.password = os.getenv("VULCAN_SOF_PASSWORD", "")

    # Maximum seconds to wait for the operator to complete 2FA
    _2FA_TIMEOUT = 120

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch open calls from Vulcan SOF via Selenium login.

        The browser opens in **visible** (non-headless) mode so the
        operator can manually enter a 2FA code.  A readiness prompt is
        shown before the login flow begins to prevent the code from
        timing out.
        """
        if not self.email or not self.password:
            log("ERROR: VULCAN_SOF_EMAIL and VULCAN_SOF_PASSWORD must be set")
            return []

        # --- Readiness gate ---------------------------------------------------
        log("Vulcan SOF requires manual 2FA entry in a visible browser window.")
        log("Have your authenticator app ready before continuing.")
        try:
            input(
                "\n>>> Press ENTER when you are ready to start the login flow "
                "(2FA will be required shortly after)... "
            )
        except EOFError:
            # Non-interactive environment — proceed immediately
            log("Non-interactive environment detected, proceeding without prompt.")

        try:
            driver = get_selenium_driver(page_load_timeout=45, headless=False)
        except Exception as e:
            log(f"Error initializing Selenium driver: {e}")
            return []

        items: List[Dict[str, Any]] = []

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            wait = WebDriverWait(driver, 15)

            # Step 1: Login
            log("Navigating to Vulcan SOF login page...")
            driver.get(VULCAN_LOGIN_URL)
            time.sleep(3)

            # Find and fill login form
            email_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='email' i]"))
            )
            email_field.clear()
            email_field.send_keys(self.email)

            password_field = driver.find_element(
                By.CSS_SELECTOR, "input[type='password']"
            )
            password_field.clear()
            password_field.send_keys(self.password)

            # Click login button
            login_btn = driver.find_element(
                By.CSS_SELECTOR, "button[type='submit'], button.login-btn, input[type='submit']"
            )
            login_btn.click()
            log("Submitted login credentials — complete 2FA in the browser window...")

            # Step 2: Wait for 2FA completion ---------------------------------
            # Poll until the URL moves into the authenticated /login/ng2/
            # section (e.g. /login/ng2/search/calls).  We cannot simply
            # check for absence of "login" because the authenticated app
            # routes also live under /login/ng2/.
            deadline = time.time() + self._2FA_TIMEOUT
            authenticated = False
            while time.time() < deadline:
                current_url = driver.current_url
                if "/ng2/" in current_url:
                    authenticated = True
                    break
                time.sleep(2)

            if not authenticated:
                log(
                    f"WARNING: 2FA was not completed within {self._2FA_TIMEOUT}s. "
                    "Attempting to continue, but results may be empty."
                )

            # Step 3: Navigate to search/calls page
            log("Navigating to calls search page...")
            driver.get(VULCAN_SEARCH_URL)
            time.sleep(5)

            # Step 4: Extract call listings
            # Wait for Angular app to render
            time.sleep(3)

            # Try to find call cards/rows
            call_elements = driver.find_elements(
                By.CSS_SELECTOR,
                ".call-card, .search-result, tr.call-row, [class*='call'], [class*='opportunity']"
            )

            if not call_elements:
                # Try broader selectors
                call_elements = driver.find_elements(
                    By.CSS_SELECTOR, ".card, .list-item, tr"
                )

            log(f"Found {len(call_elements)} potential call elements")

            for elem in call_elements:
                try:
                    text = elem.text.strip()
                    if not text or len(text) < 10:
                        continue

                    # Extract title - usually the first line or h-tag
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    title = lines[0] if lines else ""

                    # Extract any links
                    link_elems = elem.find_elements(By.TAG_NAME, "a")
                    url = VULCAN_SEARCH_URL
                    for le in link_elems:
                        href = le.get_attribute("href") or ""
                        if href and "call" in href.lower():
                            url = href
                            break

                    if title and len(title) > 5:
                        items.append(
                            {
                                "title": title,
                                "url": url,
                                "full_text": text[:3000],
                            }
                        )
                except Exception as e:
                    log(f"Error parsing call element: {e}")

            if not items:
                log("No structured call elements found on the page.")

        except Exception as e:
            log(f"Error during Vulcan SOF scraping: {e}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return items

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a Vulcan SOF call."""
        title = item.get("title", "")
        full_text = item.get("full_text", "")

        # Extract description
        description = ""
        if full_text:
            lines = [ln.strip() for ln in full_text.split("\n") if len(ln.strip()) > 20]
            description = " ".join(lines[1:5])[:2000]  # Skip title line

        return {
            "title": f"Vulcan SOF: {title}" if title else "",
            "description": description,
            "url": item.get("url", VULCAN_SEARCH_URL),
            "deadline": None,
            "agency": "SOCOM (Special Operations Command)",
        }


def main():
    scraper = VulcanSOFScraper()
    scraper.run()


if __name__ == "__main__":
    main()
