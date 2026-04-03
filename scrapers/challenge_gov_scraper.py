import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import requests
from bs4 import BeautifulSoup

# USA.gov challenges configuration
# Challenge.gov has been deprecated; active challenges are now listed on USA.gov
USAGOV_BASE_URL = "https://www.usa.gov"
USAGOV_CHALLENGES_URL = "https://www.usa.gov/find-active-challenge"

# Monday.com configuration
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID")
MONDAY_API_URL = "https://api.monday.com/v2"

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
DEFAULT_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

# Monday.com column mappings for challenges
TITLE_COLUMN = "text_mkkqwaty"  # Item name is used automatically, but we'll also store in this column
DESCRIPTION_COLUMN = "text_mkkqeet2"
URL_COLUMN = "text_mkkq2vab"
DEADLINE_COLUMN = "date_mkkqedzc"
PRIZE_COLUMN = "numbers_mkkqa431"
AGENCY_COLUMN = "text_mkvqfmz5"
SOURCE_COLUMN = "text_mktm7tsx"

# Headers for web requests
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Polite delay between detail-page requests (seconds)
REQUEST_DELAY = 1.0

MUTATION = """
mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
  create_item(board_id: $board_id, item_name: $item_name, column_values: $column_values) {
    id
  }
}
"""


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp} UTC] {message}")


def clean_html(raw: Optional[str]) -> str:
    if not raw:
        return ""
    return re.sub("<[^<]+?>", "", raw).strip()


def format_monday_date(date_str: Optional[str]) -> Optional[Dict[str, str]]:
    if not date_str:
        return None
    try:
        date_obj = None

        # Try ISO format first
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            pass

        # Try M/D/YYYY H:MM AM/PM ET format (common on usa.gov detail pages)
        if not date_obj:
            cleaned = re.sub(r"\s*(ET|EST|EDT|CT|PT)\s*$", "", date_str.strip())
            for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
                try:
                    date_obj = datetime.strptime(cleaned, fmt)
                    break
                except ValueError:
                    continue

        # Try MM/DD/YYYY format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str.strip(), "%m/%d/%Y")
            except ValueError:
                pass

        # Try Month DD, YYYY format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str.strip(), "%B %d, %Y")
            except ValueError:
                pass

        # Try YYYY-MM-DD format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            except ValueError:
                pass

        if date_obj:
            return {"date": date_obj.strftime("%Y-%m-%d")}
        return None
    except Exception:
        return None


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def fetch_challenge_list(session: requests.Session) -> List[Dict[str, Any]]:
    """Scrape the USA.gov active-challenges listing page.

    Returns a list of dicts with keys: title, description, url, detail_path.
    """
    challenges: List[Dict[str, Any]] = []
    try:
        resp = session.get(USAGOV_CHALLENGES_URL, headers=REQUEST_HEADERS, timeout=30)
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


def fetch_challenge_detail(session: requests.Session, detail_url: str) -> Dict[str, Any]:
    """Scrape a USA.gov challenge detail page for structured data.

    Parses the 'Key information' table to extract agency, dates, prize, etc.
    """
    detail: Dict[str, Any] = {}
    try:
        resp = session.get(detail_url, headers=REQUEST_HEADERS, timeout=30)
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


def fetch_existing_challenge_titles(session: requests.Session, limit: int = 200) -> set:
    """Fetch existing challenge titles from Monday.com to avoid duplicates"""
    if not MONDAY_API_KEY:
        return set()

    try:
        query = """
        query ($board_id: [ID!]!, $limit: Int!, $cursor: String, $title_col_id: String!, $source_col_id: String!) {
          boards(ids: $board_id) {
            items_page(limit: $limit, cursor: $cursor) {
              cursor
              items {
                id
                name
                column_values(ids: [$title_col_id, $source_col_id]) {
                  id
                  text
                  value
                }
              }
            }
          }
        }
        """

        headers = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}
        cursor = None
        titles = set()
        while True:
            variables = {
                "board_id": [str(MONDAY_BOARD_ID)],
                "limit": limit,
                "cursor": cursor,
                "title_col_id": TITLE_COLUMN,
                "source_col_id": SOURCE_COLUMN,
            }
            res = session.post(
                MONDAY_API_URL,
                headers=headers,
                json={"query": query, "variables": variables},
                timeout=30,
            )
            res.raise_for_status()
            payload = res.json()
            if "errors" in payload:
                log(f"Monday API errors: {json.dumps(payload['errors'], indent=2)}")
                break
            boards = payload.get("data", {}).get("boards", [])
            if not boards:
                break
            page = boards[0].get("items_page", {})
            for item in page.get("items", []):
                name = item.get("name")
                # Check if this item has a challenge source tag
                source_value = None
                for col in item.get("column_values", []):
                    if col.get("id") == SOURCE_COLUMN:
                        source_value = col.get("text") or col.get("value")
                        break

                # Include titles from challenge.gov or usa.gov challenge items
                if name and source_value:
                    src = source_value.lower()
                    if "challenge" in src or "usa.gov" in src:
                        titles.add(normalize_name(name))
            cursor = page.get("cursor")
            if not cursor:
                break
        return titles
    except Exception as e:
        log(f"Error fetching existing titles from Monday.com: {e}")
        return set()


def extract_challenge_fields(challenge: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    """Merge listing-page data with detail-page data into a unified record."""
    title = challenge.get("title", "")

    # Prefer longer description from the detail page
    description = detail.get("long_description", "") or challenge.get("description", "")

    url = challenge.get("url", "")

    # Deadline = end_date from detail page
    deadline = detail.get("end_date")

    # Prize amount
    prize_amount = parse_prize_amount(detail.get("prize_text"))

    # Agency from detail page
    agency = detail.get("agency", "")

    return {
        "title": title,
        "description": description,
        "url": url,
        "deadline": deadline,
        "prize_amount": prize_amount,
        "agency": agency,
    }


def monday_create_item(session, title, description, url, deadline_val, prize_amount, agency, source_label):
    """Create a new item in Monday.com"""
    if not MONDAY_API_KEY:
        raise Exception("MONDAY_API_KEY not available")
    
    colvals = {
        TITLE_COLUMN: title,
        DESCRIPTION_COLUMN: description,
        URL_COLUMN: url,
        DEADLINE_COLUMN: deadline_val,
        PRIZE_COLUMN: prize_amount,
        AGENCY_COLUMN: agency,
        SOURCE_COLUMN: source_label,
    }
    # Remove None values
    colvals = {k: v for k, v in colvals.items() if v is not None}
    
    variables = {
        "board_id": str(MONDAY_BOARD_ID),
        "item_name": title,
        "column_values": json.dumps(colvals),
    }
    res = session.post(MONDAY_API_URL, headers={"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"},
                      json={"query": MUTATION, "variables": variables})
    res.raise_for_status()
    return res.json()


def slack_bot_post_new_items(session, new_items, slack_channel, header):
    """Send Slack notification for new challenges"""
    if not SLACK_BOT_TOKEN or not new_items:
        return
    
    lines = [f"*🆕 {len(new_items)} new {header} opportunities*"]
    for it in new_items[:30]:
        title = it.get("title", "(no title)")
        prize = it.get("prize_amount")
        agency = it.get("agency", "")
        deadline = it.get("deadline_text", "")
        url = it.get("url", "")
        
        prize_text = f" • Prize: ${prize:,.0f}" if prize else ""
        deadline_text = f" • Due {deadline}" if deadline else ""
        agency_text = f" • {agency}" if agency else ""
        
        lines.append(f"• *{title}* {agency_text}{prize_text}{deadline_text}\n<{url}>")

    text = "\n".join(lines)
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": slack_channel or DEFAULT_SLACK_CHANNEL, "text": text}
    r = session.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=20)
    r.raise_for_status()


def slack_bot_notify_no_results(session, count, slack_channel, header):
    """Send Slack notification when no new challenges are found"""
    if not SLACK_BOT_TOKEN:
        return
    
    text = (
        f"\u2705 *USA.gov challenge scan completed successfully* \u2013 checked {count} {header} opportunities, "
        f"no new ones found today.\n"
        f"_(Checked {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})_"
    )
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": slack_channel or DEFAULT_SLACK_CHANNEL, "text": text}
    r = session.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=15)
    r.raise_for_status()


def main():
    """Main function to scrape active federal challenges from USA.gov

    Challenge.gov has been deprecated. Active challenges are now listed at
    https://www.usa.gov/find-active-challenge with detail pages under
    https://www.usa.gov/challenges/<slug>.
    """
    session = requests.Session()

    # Fetch current challenges from USA.gov listing page
    challenges = fetch_challenge_list(session)
    log(f"Fetched {len(challenges)} challenges from USA.gov")

    # Fetch detail pages for each challenge
    for i, challenge in enumerate(challenges):
        detail_url = challenge.get("url", "")
        if detail_url:
            detail = fetch_challenge_detail(session, detail_url)
            challenge["detail"] = detail
            log(f"  Fetched detail for: {challenge.get('title', '(unknown)')}")
            # Be polite to the server
            if i < len(challenges) - 1:
                time.sleep(REQUEST_DELAY)
        else:
            challenge["detail"] = {}

    # Only try to fetch existing titles and create Monday.com items if API key is available
    if MONDAY_API_KEY:
        try:
            # Fetch existing challenge titles to avoid duplicates
            existing_titles = fetch_existing_challenge_titles(session)
            log(f"Fetched {len(existing_titles)} existing challenge titles from Monday.com")
        except Exception as e:
            log(f"Error fetching existing titles from Monday.com: {e}")
            existing_titles = set()
        
        new_items = []
        
        for challenge in challenges:
            challenge_data = extract_challenge_fields(challenge, challenge.get("detail", {}))
            title = challenge_data.get("title", "")

            if not title:
                continue

            title_key = normalize_name(title)
            if title_key in existing_titles:
                continue

            # Format deadline for Monday.com
            deadline_val = format_monday_date(challenge_data.get("deadline"))
            deadline_text = (deadline_val or {}).get("date", "")

            if MONDAY_API_KEY:
                try:
                    # Create Monday.com item
                    monday_create_item(
                        session,
                        title,
                        challenge_data.get("description", ""),
                        challenge_data.get("url", ""),
                        deadline_val,
                        challenge_data.get("prize_amount"),
                        challenge_data.get("agency", ""),
                        "usa.gov challenges python"
                    )
                    
                    existing_titles.add(title_key)
                    new_items.append({
                        "title": title,
                        "prize_amount": challenge_data.get("prize_amount"),
                        "agency": challenge_data.get("agency", ""),
                        "deadline_text": deadline_text,
                        "url": challenge_data.get("url", ""),
                    })
                    
                    log(f"Created Monday.com item for challenge: {title}")
                    
                except Exception as e:
                    log(f"Error creating Monday.com item for {title}: {e}")
            else:
                log(f"Skipping Monday.com creation for {title} (no API key)")
        
        # Send notifications
        if new_items:
            slack_bot_post_new_items(session, new_items, DEFAULT_SLACK_CHANNEL, "USA.gov challenge")
            log(f"Sent Slack notification for {len(new_items)} new challenges")
        else:
            slack_bot_notify_no_results(session, len(challenges), DEFAULT_SLACK_CHANNEL, "USA.gov challenge")
            log("Sent 'no new challenges' Slack notification")
    else:
        log("Warning: missing MONDAY_API_KEY env var. Skipping Monday.com integration and Slack notifications.")
        log("Challenges found:")
        for i, challenge in enumerate(challenges):
            challenge_data = extract_challenge_fields(challenge, challenge.get("detail", {}))
            title = challenge_data.get("title", "No title")
            agency = challenge_data.get("agency", "")
            prize = challenge_data.get("prize_amount")
            deadline = challenge_data.get("deadline", "")
            prize_text = f"  Prize: ${prize:,.0f}" if prize else ""
            agency_text = f"  Agency: {agency}" if agency else ""
            deadline_text = f"  Deadline: {deadline}" if deadline else ""
            log(f"  {i+1}. {title}{agency_text}{prize_text}{deadline_text}")
            log(f"     {challenge_data.get('url', '')}")


if __name__ == "__main__":
    main()
