"""CyberFIC event scraper.

Scrapes upcoming events from https://www.cyberfic.org/events
and follows detail page links to collect full event information.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .config import CFIC_BASE_URL, CFIC_EVENTS_URL

logger = logging.getLogger(__name__)


@dataclass
class CficEvent:
    """Represents a scraped CFIC event."""

    title: str
    date: str
    detail_url: str
    event_type: str = ""
    location: str = ""
    purpose: str = ""
    background: str = ""
    rsvp_deadline: str = ""
    eligibility: str = ""
    rsvp_url: str = ""
    tpoc_name: str = ""
    tpoc_email: str = ""
    pdf_download_url: str = ""
    speaker_name: str = ""
    speaker_bio: str = ""
    key_takeaways: list[str] = field(default_factory=list)


def _fetch_page(url: str) -> BeautifulSoup:
    """Fetch a page and return parsed BeautifulSoup."""
    logger.info("Fetching %s", url)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _normalize_url(href: str) -> str:
    """Ensure a URL is absolute."""
    if href.startswith("/"):
        return CFIC_BASE_URL + href
    return href


def _extract_text(element: Optional[Tag]) -> str:
    """Extract cleaned text from a BeautifulSoup element."""
    if element is None:
        return ""
    return element.get_text(separator=" ", strip=True)


def _find_section_text(soup: BeautifulSoup, heading: str) -> str:
    """Find a bold heading in the page body and return the text that follows it.

    Looks for patterns like <span style="font-weight:bold;">Purpose</span>
    then collects subsequent paragraph text until the next bold heading.
    """
    text_elements = soup.find_all("div", attrs={"data-testid": "richTextElement"})

    found_heading = False
    collected_parts: list[str] = []

    for elem in text_elements:
        elem_text = _extract_text(elem)

        if not found_heading:
            # Check if this element contains our heading as bold text
            bold_tags = elem.find_all("span", style=lambda s: s and "font-weight:bold" in s)
            for bold in bold_tags:
                bold_text = bold.get_text(strip=True)
                if bold_text.lower().startswith(heading.lower()):
                    found_heading = True
                    # Get text after the heading within this element
                    remaining = elem_text.split(bold_text, 1)
                    if len(remaining) > 1 and remaining[1].strip():
                        collected_parts.append(remaining[1].strip())
                    break
        else:
            # Check if we hit the next bold heading
            bold_tags = elem.find_all("span", style=lambda s: s and "font-weight:bold" in s)
            if bold_tags:
                bold_text = bold_tags[0].get_text(strip=True)
                # If the entire element is a new heading, stop collecting
                if bold_text and elem_text.startswith(bold_text):
                    break

            if elem_text:
                collected_parts.append(elem_text)

    return " ".join(collected_parts).strip()


def _parse_event_type(title: str) -> str:
    """Infer event type from the title."""
    title_upper = title.upper()
    if "COLLABORATION EVENT" in title_upper or re.search(r"\bCE\b", title_upper):
        return "Collaboration Event (CE)"
    if "ASSESSMENT EVENT" in title_upper or re.search(r"\bAE\b", title_upper):
        return "Assessment Event (AE)"
    if "WEBINAR" in title_upper or "CONNECTOR SERIES" in title_upper:
        return "Connector Series Webinar"
    if "Q & A" in title_upper or "Q&A" in title_upper:
        return "Q & A Session"
    return "Event"


def scrape_upcoming_events_list() -> list[dict[str, str]]:
    """Scrape the main events page and return basic info for upcoming events.

    Returns a list of dicts with keys: title, date, detail_url
    """
    soup = _fetch_page(CFIC_EVENTS_URL)

    # Find the "Upcoming Events" heading
    upcoming_heading = None
    previous_heading = None
    rich_texts = soup.find_all("div", attrs={"data-testid": "richTextElement"})

    for rt in rich_texts:
        text = _extract_text(rt)
        if "Upcoming Events" in text:
            upcoming_heading = rt
        elif "Previous Events" in text:
            previous_heading = rt

    if upcoming_heading is None:
        logger.warning("Could not find 'Upcoming Events' section on the page")
        return []

    # Find the parent section containing the upcoming events
    # Walk up to find the section container
    upcoming_section = upcoming_heading.find_parent("section")
    if upcoming_section is None:
        logger.warning("Could not find upcoming events section container")
        return []

    events = []

    # Find all "Learn More" buttons/links in this section
    learn_more_links = upcoming_section.find_all(
        "a",
        attrs={"aria-label": "Learn More"},
    )

    for link in learn_more_links:
        href = link.get("href", "")
        if not href or "/events/" not in href:
            continue

        detail_url = _normalize_url(href)

        # Find the parent card container to extract title and date
        # Walk up to find the box container
        card = link.find_parent("div", class_=lambda c: c and "container" in c)
        if card is None:
            card = link.parent

        # Find the title - look for h4 or a linked title within the card area
        title = ""
        date_str = ""

        # Search in the same section for elements associated with this link
        # Look for rich text elements in the parent containers
        parent_box = link.find_parent("div", attrs={"dir": "ltr"})
        if parent_box is None:
            parent_box = card

        # Search the section for title links pointing to the same URL
        slug = href.rstrip("/").split("/")[-1]
        title_links = upcoming_section.find_all(
            "a", href=lambda h: h and slug in h
        )
        for tl in title_links:
            # Check if this is a text link (not a button or image)
            parent_rich_text = tl.find_parent(
                "div", attrs={"data-testid": "richTextElement"}
            )
            if parent_rich_text:
                title = _extract_text(tl)
                if title:
                    break

        if not title:
            # Fallback: use the slug as title
            title = slug.replace("-", " ").title()

        # Find the date - look for date-like text near this card
        # The date is typically in the same parent container
        # Dates look like "05 May 2026" or "06 May 2026"
        all_texts_in_section = upcoming_section.find_all(
            "div", attrs={"data-testid": "richTextElement"}
        )
        for text_elem in all_texts_in_section:
            t = _extract_text(text_elem)
            date_match = re.match(r"^\d{2}\s+\w+\s+\d{4}$", t.strip())
            if date_match:
                # Check if this date element is near the same card
                # by checking if the link's slug appears in nearby elements
                # Simple heuristic: associate dates by order
                if not date_str:
                    # We'll refine this association below
                    pass

        # Better approach: collect all cards with their titles and dates in order
        events.append(
            {
                "title": title,
                "detail_url": detail_url,
            }
        )

    # Now collect dates in order from the section
    date_pattern = re.compile(r"^\d{2}\s+\w+\s+\d{4}$")
    date_elements = []
    for text_elem in upcoming_section.find_all(
        "div", attrs={"data-testid": "richTextElement"}
    ):
        t = _extract_text(text_elem).strip()
        if date_pattern.match(t):
            date_elements.append(t)

    # Associate dates with events by position order
    for i, event in enumerate(events):
        if i < len(date_elements):
            event["date"] = date_elements[i]
        else:
            event["date"] = ""

    logger.info("Found %d upcoming events on listing page", len(events))
    return events


def scrape_event_detail(event_info: dict[str, str]) -> CficEvent:
    """Scrape a detail page for full event information.

    Args:
        event_info: dict with keys title, date, detail_url from the listing page
    """
    soup = _fetch_page(event_info["detail_url"])

    event = CficEvent(
        title=event_info.get("title", ""),
        date=event_info.get("date", ""),
        detail_url=event_info["detail_url"],
    )

    event.event_type = _parse_event_type(event.title)

    # Extract date and location from h6 element
    # The h6 contains date, location, and "Share on Social Media" on separate lines
    # When extracted with get_text(separator=" "), it becomes one string like:
    # "06 May 2026 Location: In-Person at CFIC Share on Social Media"
    h6_elements = soup.find_all("h6")
    for h6 in h6_elements:
        text = _extract_text(h6)
        if re.search(r"\d{2}\s+\w+\s+\d{4}", text):
            # Extract date
            date_match = re.search(r"(\d{2}\s+\w+\s+\d{4})", text)
            if date_match and not event.date:
                event.date = date_match.group(1)

            # Extract location
            loc_match = re.search(
                r"Location:\s*(.+?)(?:\s*Share on Social Media|$)",
                text,
                re.IGNORECASE,
            )
            if loc_match:
                event.location = loc_match.group(1).strip()
            break

    # Extract RSVP URL
    rsvp_buttons = soup.find_all(
        "a",
        attrs={
            "aria-label": lambda v: v and "RSVP" in v.upper() if v else False,
        },
    )
    if not rsvp_buttons:
        # Also look for buttons with RSVP text in labels
        for a_tag in soup.find_all("a"):
            label = a_tag.find("span", attrs={"data-testid": "stylablebutton-label"})
            if label and "RSVP" in _extract_text(label).upper():
                rsvp_buttons.append(a_tag)
                break

    if rsvp_buttons:
        event.rsvp_url = rsvp_buttons[0].get("href", "")

    # Extract RSVP deadline and eligibility
    # These appear as separate styled paragraphs within one rich text block.
    # We look for the block and extract just the deadline/eligibility lines.
    for rt in soup.find_all("div", attrs={"data-testid": "richTextElement"}):
        text = _extract_text(rt)
        if "Request to Attend" in text:
            # Extract only the deadline portion (before "Purpose" or other sections)
            deadline_match = re.search(
                r"(Request to Attend.*?(?:ET|Eastern|PM|AM))",
                text,
                re.IGNORECASE,
            )
            if deadline_match:
                event.rsvp_deadline = deadline_match.group(1).strip()
            elif "NLT" in text:
                # Fallback: grab up to the first sentence with a year
                nlt_match = re.search(
                    r"(.*?NLT.*?\d{4}.*?(?:ET|Eastern|PM|AM|$))",
                    text,
                    re.IGNORECASE,
                )
                if nlt_match:
                    event.rsvp_deadline = nlt_match.group(1).strip()
        if "U.S. Citizens Only" in text and not event.eligibility:
            event.eligibility = "U.S. Citizens Only"

    # Extract purpose
    purpose = _find_section_text(soup, "Purpose")
    if purpose:
        event.purpose = purpose

    # Extract background/synopsis
    background = _find_section_text(soup, "Background/Synopsis")
    if not background:
        background = _find_section_text(soup, "Background")
    if background:
        event.background = background

    # Extract contact info (TPOC)
    questions_text = _find_section_text(soup, "Questions")
    if questions_text:
        # Parse contact names and emails
        email_matches = re.findall(
            r"([\w.-]+@[\w.-]+\.\w+)", questions_text
        )
        # Find names before "at email" patterns
        name_pattern = re.search(
            r"contact\s+([\w\s]+?)\s+at\s+", questions_text, re.IGNORECASE
        )
        if name_pattern:
            event.tpoc_name = name_pattern.group(1).strip()
        if email_matches:
            event.tpoc_email = ", ".join(email_matches)

    # Extract PDF download link
    download_links = soup.find_all("a", attrs={"aria-label": "Download Release"})
    if not download_links:
        for a_tag in soup.find_all("a"):
            label_span = a_tag.find(
                "span", class_=lambda c: c and "button__label" in c
            )
            if label_span and "Download Release" in _extract_text(label_span):
                download_links.append(a_tag)
                break

    if download_links:
        event.pdf_download_url = download_links[0].get("href", "")

    # Extract speaker info (for webinars)
    for rt in soup.find_all("div", attrs={"data-testid": "richTextElement"}):
        text = _extract_text(rt)
        if "Meet Our Speaker" in text:
            # The next rich text element typically has the speaker name
            next_sibling = rt.find_next(
                "div", attrs={"data-testid": "richTextElement"}
            )
            if next_sibling:
                event.speaker_name = _extract_text(next_sibling)
            break

    # Extract speaker bio
    speaker_bio = _find_section_text(soup, "More About")
    if speaker_bio:
        event.speaker_bio = speaker_bio

    # Extract key takeaways
    for rt in soup.find_all("div", attrs={"data-testid": "richTextElement"}):
        text = _extract_text(rt)
        if "Key Takeaways" in text:
            # Find the next element containing the bullet list
            takeaways_container = rt.find_next(
                "div", attrs={"data-testid": "richTextElement"}
            )
            if takeaways_container:
                items = takeaways_container.find_all("li")
                if items:
                    event.key_takeaways = [
                        _extract_text(li) for li in items
                    ]
                else:
                    # Fallback: split by bullet characters
                    raw = _extract_text(takeaways_container)
                    if raw:
                        event.key_takeaways = [
                            s.strip()
                            for s in re.split(r"[•\n]", raw)
                            if s.strip()
                        ]
            break

    logger.info("Scraped detail for: %s", event.title)
    return event


def scrape_all_upcoming() -> list[CficEvent]:
    """Scrape all upcoming CFIC events with full details.

    Returns a list of CficEvent objects with all available fields populated.
    """
    event_list = scrape_upcoming_events_list()
    events = []

    for event_info in event_list:
        try:
            event = scrape_event_detail(event_info)
            events.append(event)
        except Exception:
            logger.exception("Failed to scrape detail for: %s", event_info.get("title"))

    return events
