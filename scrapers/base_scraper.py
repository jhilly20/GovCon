import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Missing required dependencies: {e}")
    print("Please install with: pip install requests beautifulsoup4")
    raise

# Monday.com configuration
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID", "")
MONDAY_API_URL = "https://api.monday.com/v2"

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
DEFAULT_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")

# Monday.com column mappings
TITLE_COLUMN = "text_mkkqwaty"
DESCRIPTION_COLUMN = "text_mkkqeet2"
URL_COLUMN = "text_mkkq2vab"
DEADLINE_COLUMN = "date_mkkqedzc"
AGENCY_COLUMN = "text_mkvqfmz5"
SOURCE_COLUMN = "text_mktm7tsx"

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
        # Try various date formats commonly used
        date_obj = None
        
        # Try ISO format first: "2024-12-31T23:59:59"
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            pass
        
        # Try YYYY-MM-DD format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass
        
        # Try MM/DD/YYYY HH:MM AM/PM format (common on usa.gov detail pages)
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
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
        
        # Try DD Month YYYY format
        if not date_obj:
            try:
                date_obj = datetime.strptime(date_str, "%d %B %Y")
            except ValueError:
                pass
        
        if date_obj:
            return {"date": date_obj.strftime("%Y-%m-%d")}
        return None
    except Exception:
        return None


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def fetch_existing_titles_by_source(session: requests.Session, source_name: str, limit: int = 200) -> set:
    """Fetch existing titles from Monday.com for a specific source to avoid duplicates"""
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
                # Check if this item has the source name in the source column
                source_value = None
                for col in item.get("column_values", []):
                    if col.get("id") == SOURCE_COLUMN:
                        source_value = col.get("text") or col.get("value")
                        break
                
                # Only include titles from matching source items
                if name and source_value and source_name.lower() in source_value.lower():
                    titles.add(normalize_name(name))
            cursor = page.get("cursor")
            if not cursor:
                break
        return titles
    except Exception as e:
        log(f"Error fetching existing titles from Monday.com: {e}")
        return set()


def monday_create_item(session, title, description, url, deadline_val, agency, source_label):
    """Create a new item in Monday.com"""
    if not MONDAY_API_KEY:
        raise Exception("MONDAY_API_KEY not available")
    
    colvals = {
        TITLE_COLUMN: title,
        DESCRIPTION_COLUMN: description,
        URL_COLUMN: url,
        DEADLINE_COLUMN: deadline_val,
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
    """Send Slack notification for new opportunities"""
    if not SLACK_BOT_TOKEN or not new_items:
        return
    
    lines = [f"*🆕 {len(new_items)} new {header} opportunities*"]
    for it in new_items[:30]:
        title = it.get("title", "(no title)")
        agency = it.get("agency", "")
        deadline = it.get("deadline_text", "")
        url = it.get("url", "")
        
        deadline_text = f" • Due {deadline}" if deadline else ""
        agency_text = f" • {agency}" if agency else ""
        
        lines.append(f"• *{title}* {agency_text}{deadline_text}\n<{url}>")

    text = "\n".join(lines)
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": slack_channel or DEFAULT_SLACK_CHANNEL, "text": text}
    r = session.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=20)
    r.raise_for_status()


def slack_bot_notify_no_results(session, count, slack_channel, header):
    """Send Slack notification when no new opportunities are found"""
    if not SLACK_BOT_TOKEN:
        return
    
    text = (
        f"✅ *{header} scan completed successfully* – checked {count} {header} opportunities, "
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


class BaseScraper:
    """Base class for all scrapers"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
    
    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract required fields from item data - to be implemented by subclasses"""
        raise NotImplementedError
    
    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch data from the source - to be implemented by subclasses"""
        raise NotImplementedError
    
    def run(self):
        """Main execution method"""
        log(f"Starting {self.source_name} scraper")
        
        try:
            # Fetch data from source
            items = list(self.fetch_data())
            log(f"Fetched {len(items)} items from {self.source_name}")
            
            # Only proceed if we have Monday.com integration
            if os.getenv("MONDAY_API_KEY"):
                try:
                    # Fetch existing titles to avoid duplicates for this specific source
                    existing_titles = fetch_existing_titles_by_source(self.session, self.source_name)
                    log(f"Fetched {len(existing_titles)} existing {self.source_name} titles from Monday.com")
                except Exception as e:
                    log(f"Error fetching existing titles from Monday.com: {e}")
                    existing_titles = set()
                
                new_items = []
                
                for item in items:
                    item_data = self.extract_fields(item)
                    title = item_data.get("title", "")
                    
                    if not title:
                        continue
                        
                    title_key = normalize_name(title)
                    if title_key in existing_titles:
                        continue
                    
                    # Format deadline for Monday.com
                    deadline_val = format_monday_date(item_data.get("deadline"))
                    deadline_text = (deadline_val or {}).get("date", "")
                    
                    if os.getenv("MONDAY_API_KEY"):
                        try:
                            # Create Monday.com item
                            monday_create_item(
                                self.session,
                                title,
                                item_data.get("description", ""),
                                item_data.get("url", ""),
                                deadline_val,
                                item_data.get("agency", ""),
                                f"{self.source_name} python"
                            )
                            
                            existing_titles.add(title_key)
                            new_items.append({
                                "title": title,
                                "agency": item_data.get("agency", ""),
                                "deadline_text": deadline_text,
                                "url": item_data.get("url", ""),
                            })
                            
                            log(f"Created Monday.com item for {self.source_name}: {title}")
                            
                        except Exception as e:
                            log(f"Error creating Monday.com item for {title}: {e}")
                    else:
                        log(f"Skipping Monday.com creation for {title} (no API key)")
                
                # Send notifications
                if new_items:
                    slack_bot_post_new_items(self.session, new_items, DEFAULT_SLACK_CHANNEL, self.source_name)
                    log(f"Sent Slack notification for {len(new_items)} new {self.source_name} items")
                else:
                    slack_bot_notify_no_results(self.session, len(items), DEFAULT_SLACK_CHANNEL, self.source_name)
                    log(f"Sent 'no new {self.source_name} items' Slack notification")
            else:
                log("Warning: missing MONDAY_API_KEY env var. Skipping Monday.com integration and Slack notifications.")
                log(f"{self.source_name} items found:")
                for i, item in enumerate(items[:5]):  # Show first 5 items
                    item_data = self.extract_fields(item)
                    log(f"  Item {i+1}: {item_data.get('title', 'No title')}")
                    
        except Exception as e:
            log(f"Error in {self.source_name} scraper: {e}")
