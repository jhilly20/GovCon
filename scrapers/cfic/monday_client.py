"""Monday.com API client for the CFIC scraper.

Handles checking for existing events and creating new items
on the Monday.com board.
"""

import json
import logging
from typing import Any

import requests

from .config import (
    MONDAY_API_TOKEN,
    MONDAY_API_URL,
    MONDAY_BOARD_ID,
    MONDAY_COLUMNS,
    SCRAPER_SOURCE,
)
from .scraper import CficEvent

logger = logging.getLogger(__name__)


def _run_query(query: str, variables: dict[str, Any] | None = None) -> dict:
    """Execute a Monday.com GraphQL query."""
    headers = {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(MONDAY_API_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        logger.error("Monday.com API errors: %s", data["errors"])
        raise RuntimeError(f"Monday.com API error: {data['errors']}")

    return data


def get_existing_event_names() -> set[str]:
    """Fetch all item names currently on the board.

    Returns a set of item names (lowercased) for deduplication.
    """
    query = """
    query ($boardId: [ID!]!) {
        boards(ids: $boardId) {
            items_page(limit: 500) {
                items {
                    name
                    column_values {
                        id
                        text
                    }
                }
            }
        }
    }
    """
    variables = {"boardId": [str(MONDAY_BOARD_ID)]}
    data = _run_query(query, variables)

    names = set()
    boards = data.get("data", {}).get("boards", [])
    if boards:
        items = boards[0].get("items_page", {}).get("items", [])
        for item in items:
            names.add(item["name"].strip().lower())

    logger.info("Found %d existing items on board", len(names))
    return names


def _format_date_for_monday(date_str: str) -> str:
    """Convert a date like '05 May 2026' to Monday.com format 'YYYY-MM-DD'.

    Returns empty string if parsing fails.
    """
    import re
    from datetime import datetime

    date_str = date_str.strip()

    # Try parsing "DD Month YYYY"
    try:
        dt = datetime.strptime(date_str, "%d %B %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try parsing "DD Mon YYYY"
    try:
        dt = datetime.strptime(date_str, "%d %b %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try to extract a date from longer text
    match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str)
    if match:
        try:
            dt = datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}",
                "%d %B %Y",
            )
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    logger.warning("Could not parse date: %s", date_str)
    return ""


def _build_description(event: CficEvent) -> str:
    """Build a combined description string from event fields."""
    parts = []

    if event.purpose:
        parts.append(f"Purpose: {event.purpose}")

    if event.background:
        parts.append(f"Background: {event.background}")

    if event.rsvp_deadline:
        parts.append(f"RSVP Deadline: {event.rsvp_deadline}")

    if event.eligibility:
        parts.append(f"Eligibility: {event.eligibility}")

    if event.key_takeaways:
        takeaways = "; ".join(event.key_takeaways)
        parts.append(f"Key Takeaways: {takeaways}")

    if event.speaker_name:
        parts.append(f"Speaker: {event.speaker_name}")

    if event.location:
        parts.append(f"Location: {event.location}")

    if event.event_type:
        parts.append(f"Event Type: {event.event_type}")

    return "\n\n".join(parts)


def create_event_item(event: CficEvent) -> dict:
    """Create a new item on the Monday.com board for the given event.

    Returns the API response data for the created item.
    """
    column_values: dict[str, Any] = {}

    # Close date (date column)
    date_formatted = _format_date_for_monday(event.date)
    if date_formatted:
        column_values[MONDAY_COLUMNS["close_date"]] = {"date": date_formatted}

    # Link
    column_values[MONDAY_COLUMNS["link"]] = event.detail_url

    # Description
    description = _build_description(event)
    if description:
        column_values[MONDAY_COLUMNS["description"]] = description

    # TPOC
    if event.tpoc_name:
        column_values[MONDAY_COLUMNS["tpoc"]] = event.tpoc_name

    # TPOC Email
    if event.tpoc_email:
        column_values[MONDAY_COLUMNS["tpoc_email"]] = event.tpoc_email

    # Agency
    column_values[MONDAY_COLUMNS["agency"]] = "CFIC / ARCYBER"

    # Source
    column_values[MONDAY_COLUMNS["source"]] = SCRAPER_SOURCE

    query = """
    mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
        create_item(
            board_id: $boardId,
            item_name: $itemName,
            column_values: $columnValues
        ) {
            id
            name
        }
    }
    """
    variables = {
        "boardId": str(MONDAY_BOARD_ID),
        "itemName": event.title,
        "columnValues": json.dumps(column_values),
    }

    data = _run_query(query, variables)
    created = data.get("data", {}).get("create_item", {})
    logger.info(
        "Created Monday.com item: %s (id=%s)",
        created.get("name"),
        created.get("id"),
    )
    return created


def sync_events(events: list[CficEvent]) -> list[CficEvent]:
    """Sync scraped events to Monday.com board.

    Checks for existing items and only creates new ones.
    Returns the list of newly created events.
    """
    existing_names = get_existing_event_names()
    new_events = []

    for event in events:
        if event.title.strip().lower() in existing_names:
            logger.info("Event already exists, skipping: %s", event.title)
            continue

        try:
            create_event_item(event)
            new_events.append(event)
        except Exception:
            logger.exception("Failed to create item for: %s", event.title)

    logger.info(
        "Synced %d new events to Monday.com (%d already existed)",
        len(new_events),
        len(events) - len(new_events),
    )
    return new_events
