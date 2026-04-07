import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log

# USA.gov challenges configuration
# Challenge.gov has been deprecated; active challenges are now listed on USA.gov
USAGOV_BASE_URL = "https://www.usa.gov"
USAGOV_CHALLENGES_URL = "https://www.usa.gov/find-active-challenge"

# Polite delay between detail-page requests (seconds)
REQUEST_DELAY = 1.0


def parse_prize_amount(prize_text: Optional[str]) -> Optional[float]:
    """Extract a numeric dollar amount from prize text like 'Total cash prizes: $2,500,000'."""
    if not prize_text:
        return None
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", prize_text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def strip_timezone_suffix(date_str: str) -> str:
    """Remove trailing timezone abbreviations (ET, EST, EDT, CT, PT) from date strings."""
    return re.sub(r"\s*(ET|EST|EDT|CT|PT)\s*$", "", date_str.strip())


class ChallengeGovScraper(BaseScraper):
    """Scraper for USA.gov active federal challenges.

    Challenge.gov has been deprecated. Active challenges are now listed at
    https://www.usa.gov/find-active-challenge with detail pages under
    https://www.usa.gov/challenges/<slug>.
    """

    def __init__(self):
        super().__init__("usa.gov challenges")
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    @property
    def dedup_source_keywords(self):
        """Match legacy items tagged with 'challenge' or 'usa.gov'."""
        return ["usa.gov", "challenge"]

    def _fetch_challenge_list(self) -> List[Dict[str, Any]]:
        """Scrape the USA.gov active-challenges listing page.

        Returns a list of dicts with keys: title, description, url, detail_path.
        """
        challenges: List[Dict[str, Any]] = []
        try:
            resp = self.session.get(USAGOV_CHALLENGES_URL, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("div.usagov-cards li.usa-card")
            for card in cards:
                link = card.find("a", class_="usa-card__container")
                if not link:
                    continue

                heading = link.find("h2")
                title = heading.get_text(strip=True) if heading else ""

                body = link.find("div", class_="usa-card__body")
                description = body.get_text(strip=True) if body else ""

                href = link.get("href", "")
                full_url = href if href.startswith("http") else f"{USAGOV_BASE_URL}{href}"

                challenges.append({
                    "title": title,
                    "description": description,
                    "url": full_url,
                    "detail_path": href,
                })
        except Exception as e:
            log(f"Error fetching challenge list from USA.gov: {e}")

        return challenges

    def _fetch_challenge_detail(self, detail_url: str) -> Dict[str, Any]:
        """Scrape a USA.gov challenge detail page for structured data.

        Parses the 'Key information' table to extract agency, dates, prize, etc.
        """
        detail: Dict[str, Any] = {}
        try:
            resp = self.session.get(detail_url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Parse the "Key information" table
            table = soup.find("table", class_="usa-table")
            if table:
                rows = table.find_all("tr")
                for row in rows:
                    th = row.find("th")
                    td = row.find("td")
                    if not th or not td:
                        continue
                    label = th.get_text(strip=True).lower()
                    value = td.get_text(" ", strip=True)

                    if "sponsoring agency" in label or "agency" in label:
                        detail["agency"] = value
                    elif "end date" in label:
                        detail["end_date"] = value
                    elif "start date" in label:
                        detail["start_date"] = value
                    elif "prize" in label:
                        detail["prize_text"] = value
                    elif "challenge type" in label:
                        detail["challenge_type"] = value
                    elif "contact" in label:
                        detail["contact"] = value

            # Get the longer description from the page body
            content_div = soup.find("div", class_="body-copy")
            if content_div:
                paragraphs = []
                for elem in content_div.children:
                    if getattr(elem, "name", None) == "table":
                        break
                    text = elem.get_text(strip=True) if hasattr(elem, "get_text") else str(elem).strip()
                    if text:
                        paragraphs.append(text)
                if paragraphs:
                    detail["long_description"] = " ".join(paragraphs)

            # Get the apply/action link if present
            apply_link = soup.find("a", class_="usa-button")
            if apply_link:
                detail["apply_url"] = apply_link.get("href", "")

        except Exception as e:
            log(f"Error fetching challenge detail {detail_url}: {e}")

        return detail

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch challenges from USA.gov listing page and enrich with detail pages."""
        challenges = self._fetch_challenge_list()
        log(f"Fetched {len(challenges)} challenges from USA.gov listing page")

        for i, challenge in enumerate(challenges):
            detail_url = challenge.get("url", "")
            if detail_url:
                detail = self._fetch_challenge_detail(detail_url)
                challenge["detail"] = detail
                log(f"  Fetched detail for: {challenge.get('title', '(unknown)')}")
                # Be polite to the server
                if i < len(challenges) - 1:
                    time.sleep(REQUEST_DELAY)
            else:
                challenge["detail"] = {}

        return challenges

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardized fields from a challenge item (listing + detail data)."""
        detail = item.get("detail", {})

        title = item.get("title", "")

        # Prefer longer description from the detail page
        description = detail.get("long_description", "") or item.get("description", "")

        # Append prize info to description so it's visible in Monday.com
        prize_amount = parse_prize_amount(detail.get("prize_text"))
        if prize_amount:
            description = f"{description}\n\nPrize: ${prize_amount:,.0f}".strip()

        url = item.get("url", "")

        # Deadline = end_date from detail page; strip timezone suffix before parsing
        raw_deadline = detail.get("end_date")
        deadline = strip_timezone_suffix(raw_deadline) if raw_deadline else None

        # Agency from detail page
        agency = detail.get("agency", "")

        return {
            "title": title,
            "description": description,
            "url": url,
            "deadline": deadline,
            "agency": agency,
        }


def main():
    """Main function to run the USA.gov challenges scraper"""
    scraper = ChallengeGovScraper()
    scraper.run()


if __name__ == "__main__":
    main()
