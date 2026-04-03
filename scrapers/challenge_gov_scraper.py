import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

# Load environment variables from .env file if it exists
try:
    from pathlib import Path
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
except Exception as e:
    pass  # Silently continue if .env file doesn't exist

import requests
from bs4 import BeautifulSoup

# Challenge.gov configuration
CHALLENGE_GOV_BASE_URL = "https://www.challenge.gov"
CHALLENGE_GOV_LIST_URL = "https://portal.challenge.gov/api/challenges"

# Monday.com configuration
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID")
MONDAY_API_URL = "https://api.monday.com/v2"

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
DEFAULT_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

# Monday.com column mappings for challenge.gov
TITLE_COLUMN = "text_mkkqwaty"  # Item name is used automatically, but we'll also store in this column
DESCRIPTION_COLUMN = "text_mkkqeet2"
URL_COLUMN = "text_mkkq2vab"
DEADLINE_COLUMN = "date_mkkqedzc"
PRIZE_COLUMN = "numbers_mkkqa431"
AGENCY_COLUMN = "text_mkvqfmz5"
SOURCE_COLUMN = "text_mktm7tsx"

# Headers for web requests
CHALLENGE_GOV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.challenge.gov/",
}

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
        # Challenge.gov dates are typically in various formats, try to parse them
        # Common formats: "2024-12-31", "12/31/2024", "December 31, 2024"
        date_obj = None
        
        # Try ISO format first
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            pass
        
        # Try MM/DD/YYYY format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
            except ValueError:
                pass
        
        # Try Month DD, YYYY format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str, "%B %d, %Y")
            except ValueError:
                pass
        
        # Try YYYY-MM-DD format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass
        
        if date_obj:
            return {"date": date_obj.strftime("%Y-%m-%d")}
        return None
    except Exception:
        return None


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def fetch_challenge_list(session: requests.Session) -> Iterable[Dict[str, Any]]:
    """Fetch the list of current challenges from challenge.gov API"""
    try:
        resp = session.get(CHALLENGE_GOV_LIST_URL, headers=CHALLENGE_GOV_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("collection", [])
    except Exception as e:
        log(f"Error fetching challenge list: {e}")
        return []


def fetch_challenge_detail(session: requests.Session, challenge_url: str) -> Dict[str, Any]:
    """Fetch detailed information for a specific challenge"""
    try:
        # Challenge.gov API provides most info, but we might need to scrape the detail page for some fields
        detail_url = f"{challenge_url}?format=json" if not challenge_url.endswith("?format=json") else challenge_url
        resp = session.get(detail_url, headers=CHALLENGE_GOV_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log(f"Error fetching challenge detail {challenge_url}: {e}")
        return {}


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
                # Check if this item has "challenge.gov" in the source column
                source_value = None
                for col in item.get("column_values", []):
                    if col.get("id") == SOURCE_COLUMN:
                        source_value = col.get("text") or col.get("value")
                        break
                
                # Only include titles from challenge.gov items
                if name and source_value and "challenge.gov" in source_value.lower():
                    titles.add(normalize_name(name))
            cursor = page.get("cursor")
            if not cursor:
                break
        return titles
    except Exception as e:
        log(f"Error fetching existing titles from Monday.com: {e}")
        return set()


def extract_challenge_fields(challenge: Dict[str, Any]) -> Dict[str, Any]:
    """Extract required fields from challenge data"""
    title = challenge.get("title", "")
    
    # Get description - might be in 'description' field or need to construct from other fields
    description = clean_html(challenge.get("description", ""))
    if not description:
        # Try to get description from other fields if available
        description = clean_html(challenge.get("overview", ""))
    
    # Get URL - might be in 'url' field or need to construct from challenge ID
    url = challenge.get("url", "")
    if not url and challenge.get("id"):
        url = f"https://www.challenge.gov/challenge/{challenge['id']}/"
    
    # Extract deadline from end_date field
    deadline = None
    end_date = challenge.get("end_date")
    if end_date:
        deadline = end_date
    
    # Extract prize amount - prize_total is in cents, convert to dollars
    prize_amount = None
    prize_total_cents = challenge.get("prize_total")
    if prize_total_cents:
        try:
            # Convert from cents to dollars
            prize_amount = float(prize_total_cents) / 100.0
        except (ValueError, TypeError):
            pass
    
    # Extract agency - might be in 'agency' field or need to construct
    agency = ""
    if challenge.get("agency"):
        agency = challenge.get("agency", "")
    elif challenge.get("organization"):
        agency = challenge.get("organization", "")
    
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
        f"✅ *challenge.gov scan completed successfully* – checked {count} {header} opportunities, "
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
    """Main function to run the challenge.gov scraper"""
    session = requests.Session()
    
    # Fetch current challenges from challenge.gov first
    challenges = list(fetch_challenge_list(session))
    log(f"Fetched {len(challenges)} challenges from challenge.gov")
    
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
            challenge_data = extract_challenge_fields(challenge)
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
                        "challenge.gov python"
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
            slack_bot_post_new_items(session, new_items, DEFAULT_SLACK_CHANNEL, "challenge.gov")
            log(f"Sent Slack notification for {len(new_items)} new challenges")
        else:
            slack_bot_notify_no_results(session, len(challenges), DEFAULT_SLACK_CHANNEL, "challenge.gov")
            log("Sent 'no new challenges' Slack notification")
    else:
        log("Warning: missing MONDAY_API_KEY env var. Skipping Monday.com integration and Slack notifications.")
        log("Challenges found:")
        for i, challenge in enumerate(challenges[:5]):  # Show first 5 challenges
            challenge_data = extract_challenge_fields(challenge)
            log(f"  Challenge {i+1}: {challenge_data.get('title', 'No title')}")


if __name__ == "__main__":
    main()