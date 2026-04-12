"""DHS Acquisition Planning Forecast System (APFS) scraper.

Fetches the DHS acquisition forecast from the public JSON API at
``/api/forecast/``.  The API returns structured data for all published
forecast entries including NAICS, set-aside, contract status, dollar
range, and contact information.

No authentication required.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from base_scraper import BaseScraper, clean_html, log

DHS_FORECAST_API = "https://apfs-cloud.dhs.gov/api/forecast/"
DHS_FORECAST_PAGE = "https://apfs-cloud.dhs.gov/forecast/"


class DHSForecastScraper(BaseScraper):
    """Scraper for DHS Acquisition Planning Forecast entries."""

    def __init__(self):
        super().__init__("DHS Forecast")

    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch all forecast entries from the DHS APFS API."""
        try:
            resp = self.session.get(DHS_FORECAST_API, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(f"Error fetching DHS Forecast API: {e}")
            return []

        if not isinstance(data, list):
            log(f"DHS Forecast: unexpected response type: {type(data)}")
            return []

        log(f"DHS Forecast: fetched {len(data)} forecast entries")
        return data

    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardised fields from a DHS forecast entry."""
        apfs_number = item.get("apfs_number", "")
        title = item.get("requirements_title", "")
        requirement = item.get("requirement", "")
        organization = item.get("organization", "")
        mission = _safe_str(item.get("mission"))
        naics = _safe_str(item.get("naics"))
        dollar_range = _parse_display_name(item.get("dollar_range"))
        set_aside = _safe_str(item.get("small_business_set_aside"))
        contract_vehicle = _safe_str(item.get("contract_vehicle"))
        contract_type = _safe_str(item.get("contract_type"))
        contract_status = _safe_str(item.get("contract_status"))

        # Dates
        solicitation_date = _safe_str(
            item.get("estimated_solicitation_release_date")
        )
        award_date = _safe_str(item.get("anticipated_award_date"))

        # Use estimated solicitation release date as deadline
        deadline = solicitation_date if solicitation_date else award_date

        # Contact info
        contact_first = _safe_str(item.get("requirements_contact_first_name"))
        contact_last = _safe_str(item.get("requirements_contact_last_name"))
        contact_email = _safe_str(item.get("requirements_contact_email"))
        contact = f"{contact_first} {contact_last}".strip()
        if contact_email:
            contact = f"{contact} ({contact_email})" if contact else contact_email

        # Build description
        desc_parts = []
        if requirement:
            desc_parts.append(requirement)
        if naics:
            desc_parts.append(f"NAICS: {naics}")
        if dollar_range:
            desc_parts.append(f"Dollar Range: {dollar_range}")
        if set_aside:
            desc_parts.append(f"Set-Aside: {set_aside}")
        if contract_vehicle:
            desc_parts.append(f"Vehicle: {contract_vehicle}")
        if contract_type:
            desc_parts.append(f"Type: {contract_type}")
        if contract_status:
            desc_parts.append(f"Status: {contract_status}")
        if contact:
            desc_parts.append(f"Contact: {contact}")

        description = " | ".join(desc_parts)

        # Build agency label
        agency = f"DHS {organization}" if organization else "DHS"

        full_title = f"[{apfs_number}] {title}" if apfs_number else title

        return {
            "title": full_title,
            "description": description[:2000],
            "url": DHS_FORECAST_PAGE,
            "deadline": deadline,
            "agency": agency,
        }


def _safe_str(value) -> str:
    """Convert a value to string, returning empty string for None/'None'."""
    if value is None:
        return ""
    s = str(value).strip()
    if s == "None":
        return ""
    return s


def _parse_display_name(value) -> str:
    """Extract display_name from a dict-like string or return the value."""
    if not value:
        return ""
    s = str(value)
    # The API returns strings like "{'display_name': 'Over $100M', ...}"
    m = re.search(r"'display_name':\s*'([^']*)'", s)
    if m:
        return m.group(1)
    if s == "None":
        return ""
    return s


def main():
    scraper = DHSForecastScraper()
    scraper.run()


if __name__ == "__main__":
    main()
