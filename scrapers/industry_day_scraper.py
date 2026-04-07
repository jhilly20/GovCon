"""SAM.gov Industry Day scraper.

Searches SAM.gov for active "Industry Day" special notices and posts
them to the Monday.com **Event Dashboard** board.  Deduplicates by
solicitation number so existing items are never recreated.

This scraper targets a separate Monday.com board from the opportunity
scrapers (MONDAY_EVENT_BOARD_ID instead of MONDAY_BOARD_ID) and uses
event-specific columns (due date, link, topic number).  Because of
this, it does NOT inherit from BaseScraper -- it imports shared
utilities (log, clean_html) but manages its own Monday.com integration.

Environment variables:
    MONDAY_API_KEY          Monday.com API token (shared with other scrapers)
    MONDAY_EVENT_BOARD_ID   Board ID for the Event Dashboard
    SAM_API_KEY             SAM.gov API key (optional; search works without it)
    SLACK_BOT_TOKEN         Slack bot token (shared with other scrapers)
    SLACK_CHANNEL           Default Slack channel for notifications
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import requests

from base_scraper import log

# ---------------------------------------------------------------------------
# SAM.gov configuration
# ---------------------------------------------------------------------------
SAM_API_KEY = os.getenv("SAM_API_KEY", "")
SAM_SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
SAM_DETAIL_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{}"

# ---------------------------------------------------------------------------
# Monday.com configuration -- Event Dashboard board
# ---------------------------------------------------------------------------
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
MONDAY_EVENT_BOARD_ID = os.getenv("MONDAY_EVENT_BOARD_ID", "")
MONDAY_API_URL = "https://api.monday.com/v2"

# Column IDs on the Event Dashboard board
TITLE_COLUMN = "text_mkkqwaty"
DUEDATE_COLUMN = "date_mkkz1cgv"
LINK_COLUMN = "link_mkktmmgp"
SOLIC_COLUMN = "text_mkzb3jv1"  # Solicitation / topic number

MUTATION = """
mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
  create_item(board_id: $board_id, item_name: $item_name, column_values: $column_values) {
    id
  }
}
"""

# ---------------------------------------------------------------------------
# Slack configuration
# ---------------------------------------------------------------------------
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")


# ===== SAM.gov helpers =====================================================

def sam_search(session: requests.Session) -> List[Dict[str, Any]]:
    """Search SAM.gov for active Industry Day special notices."""
    params = {
        "random": str(int(time.time() * 1000)),
        "index": "opp",
        "page": 0,
        "sort": "-modifiedDate",
        "size": 200,
        "mode": "search",
        "is_active": "true",
        "q": '"Industry Day"',
        "qMode": "ALL",
        "notice_type": "s",
    }

    try:
        resp = session.get(SAM_SEARCH_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log(f"Error searching SAM.gov: {exc}")
        return []

    total = (
        data.get("page", {}).get("totalElements")
        or data.get("page", {}).get("total_elements")
        or data.get("_embedded", {}).get("total")
        or data.get("totalRecords")
    )
    log(f"SAM.gov reported {total} total Industry Day results")

    hits = data.get("_embedded", {}).get("results", [])
    log(f"Returned {len(hits)} results on this page")
    return hits


def sam_detail(session: requests.Session, notice_id: str) -> Dict[str, Any]:
    """Fetch the v2 detail JSON for a specific SAM.gov notice."""
    url = SAM_DETAIL_URL.format(notice_id)
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _parse_response_date(raw: Optional[str]) -> Optional[Dict[str, str]]:
    """Parse a SAM.gov ISO date string into Monday.com date format."""
    if not raw or "T" not in raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return {"date": dt.strftime("%Y-%m-%d")}
    except Exception:
        return None


# ===== Monday.com helpers ==================================================

def _monday_headers() -> Dict[str, str]:
    return {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}


def monday_find_item_by_topic(session: requests.Session, topic_no: str) -> List[Dict]:
    """Check if an item with the given solicitation number already exists."""
    if not MONDAY_API_KEY or not topic_no:
        return []

    query = """
    query ($board_id: ID!, $column_id: String!, $values: [String!]!) {
      items_page_by_column_values(
        board_id: $board_id,
        columns: [{column_id: $column_id, column_values: $values}],
        limit: 10
      ) {
        items { id name }
      }
    }
    """
    variables = {
        "board_id": str(MONDAY_EVENT_BOARD_ID),
        "column_id": SOLIC_COLUMN,
        "values": [str(topic_no)],
    }
    try:
        res = session.post(
            MONDAY_API_URL,
            headers=_monday_headers(),
            json={"query": query, "variables": variables},
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
        if "errors" in data:
            log(f"Monday API error (find): {json.dumps(data['errors'], indent=2)}")
            return []
        return (
            data.get("data", {})
            .get("items_page_by_column_values", {})
            .get("items", [])
        )
    except Exception as exc:
        log(f"Error querying Monday.com for topic {topic_no}: {exc}")
        return []


def monday_create_event_item(
    session: requests.Session,
    title: str,
    close_date_val: Optional[Dict[str, str]],
    link: str,
    topic_no: str,
) -> Optional[Dict]:
    """Create a new item on the Event Dashboard board."""
    if not MONDAY_API_KEY:
        log("MONDAY_API_KEY not set -- skipping item creation")
        return None

    link_val = {"url": link, "text": "SAM.gov"} if link else None

    colvals: Dict[str, Any] = {
        TITLE_COLUMN: title,
        DUEDATE_COLUMN: close_date_val,
        LINK_COLUMN: link_val,
        SOLIC_COLUMN: topic_no,
    }
    colvals = {k: v for k, v in colvals.items() if v is not None}

    variables = {
        "board_id": str(MONDAY_EVENT_BOARD_ID),
        "item_name": title,
        "column_values": json.dumps(colvals),
    }

    try:
        res = session.post(
            MONDAY_API_URL,
            headers=_monday_headers(),
            json={"query": MUTATION, "variables": variables},
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
        if "errors" in data:
            log(f"Monday GraphQL errors: {json.dumps(data['errors'], indent=2)}")
            return None
        log(f"Created Monday.com event item: {title}")
        return data
    except Exception as exc:
        log(f"Error creating Monday.com item for '{title}': {exc}")
        return None


# ===== Slack helpers =======================================================

def slack_post_new_items(session: requests.Session, new_items: List[Dict]) -> None:
    """Post a summary of new Industry Day items to Slack."""
    if not SLACK_BOT_TOKEN or not new_items:
        return

    lines = [f"*{len(new_items)} new SAM.gov Industry Days*"]
    for it in new_items[:30]:
        title = it.get("title", "(no title)")
        topic = it.get("topic", "")
        link = it.get("link", "")
        due_text = it.get("due_text", "")
        due_fmt = f" | Due {due_text}" if due_text else ""
        lines.append(f"  *{title}* ({topic}){due_fmt}\n<{link}>")

    text = "\n".join(lines)
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}
    try:
        r = session.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
    except Exception as exc:
        log(f"Slack API error: {exc}")


def slack_notify_no_results(session: requests.Session, count: int) -> None:
    """Notify Slack when no new Industry Days are found."""
    if not SLACK_BOT_TOKEN:
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = (
        f"*SAM.gov Industry Day scan completed* - checked {count} events, "
        f"no new ones found.\n"
        f"_(Checked {now_str})_"
    )
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}
    try:
        r = session.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
    except Exception as exc:
        log(f"Slack API error (no results): {exc}")


# ===== Main ================================================================

def main() -> None:
    log("Starting SAM.gov Industry Day scraper")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })

    hits = sam_search(session)
    if not hits:
        log("No results from SAM.gov search")
        return

    new_items: List[Dict[str, str]] = []

    for opp in hits:
        notice_id = opp.get("_id", "")
        title = opp.get("title", "Untitled")
        solnum = opp.get("solicitationNumber", "")
        due_raw = opp.get("responseDate")

        # ---- Try to enrich from v2 detail endpoint ----
        link = ""
        topic_no = solnum

        if notice_id:
            try:
                detail_raw = sam_detail(session, notice_id)
                detail_data2 = detail_raw.get("data2", {})

                # Prefer uiLink from detail; fall back to public opp URL
                link = (
                    detail_data2.get("uiLink")
                    or f"https://sam.gov/opp/{notice_id}/view"
                )

                # Authoritative solicitation number from detail
                topic_no = detail_data2.get("solicitationNumber") or solnum

            except Exception as exc:
                log(f"Failed to fetch detail for {notice_id}: {exc}")
                link = f"https://sam.gov/opp/{notice_id}/view"
        else:
            link = f"https://sam.gov/opp/{solnum or ''}".rstrip("/")

        # ---- Dedup by solicitation number ----
        if topic_no and monday_find_item_by_topic(session, topic_no):
            continue

        # ---- Create Monday.com item ----
        close_date_val = _parse_response_date(due_raw)

        monday_create_event_item(session, title, close_date_val, link, topic_no)

        new_items.append({
            "title": title,
            "topic": topic_no,
            "link": link,
            "due_text": (close_date_val or {}).get("date", ""),
        })

    # ---- Slack summary ----
    if new_items:
        slack_post_new_items(session, new_items)
        log(f"Posted {len(new_items)} new Industry Day items to Slack")
    else:
        slack_notify_no_results(session, len(hits))
        log(f"No new Industry Days (checked {len(hits)} results)")

    log("Industry Day scraper complete")


if __name__ == "__main__":
    main()
