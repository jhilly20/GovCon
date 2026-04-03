import json
import os
import requests
from urllib.parse import urlencode
import time
import re
from datetime import datetime, timezone

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

# === CONFIG ===
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
BOARD_ID = os.getenv("MONDAY_BOARD_ID", "")  # must be string, not int

# Replace these with your real Monday column IDs
AGENCY_COLUMN = "text_mkvqfmz5"
DUEDATE_COLUMN = "date_mkkqedzc"
LINK_COLUMN = "text_mkkq2vab"  
SOLIC_COL       = "text_mkm0rbb8"   # unique Solicitation/Notice ID

# === MONDAY.COM API ===
API_URL = "https://api.monday.com/v2"
HEADERS_MD = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}

# === SLACK CONFIG ===
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")

# === SAM.GOV API ===
SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"

# v1 search params
params = {
    "random": str(int(time.time()*1000)),
    "index": "opp",     # opportunity index
    "page": 0,
    "sort": "-modifiedDate",
    "size": 100,
    "mode": "search",
    "responseType": "json",
    "response_date.from": datetime.now(timezone.utc).strftime("%Y-%m-%d-05:00"),
    "is_active": "true",
    "q": "COBOL OR FORTRAN OR refactor OR replatform OR DevSecOps",
    "qMode": "ANY",
    "notice_type": "r,p,o,k",                # Sources Sought, Presolicitation, Solicitation, Combined
    "postedDate_to": datetime.now(timezone.utc).strftime("%Y-%m-%d-05:00")
}

# === MONDAY.COM MUTATION ===
MUTATION = """
mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
  create_item (
    board_id: $board_id,
    item_name: $item_name,
    column_values: $column_values
  ) {
    id
  }
}
"""

def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp} UTC] {message}")

def clean_html(raw: str) -> str:
    if not raw:
        return ""
    return re.sub("<[^<]+?>", "", raw).strip()

def format_monday_date(date_str: str) -> dict:
    """Convert SAM.gov date string to Monday.com format."""
    if not date_str:
        return {}
    try:
        # Handle SAM.gov format: 2024-12-16T23:59:59Z
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return {"date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M:%S")}
        else:
            # Handle other formats
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return {"date": dt.strftime("%Y-%m-%d")}
    except Exception as e:
        log(f"Date format error: {e} for '{date_str}'")
        return {}

def sam_search():
    """Search SAM.gov using v1 API with our parameters."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{SEARCH_URL}?{query}"
    log(f"Searching SAM.gov for COBOL, FORTRAN, refactor, replatform, DevSecOps, or code migration opportunities...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    # v1 nests results under "_embedded.results"
    hits = data.get("_embedded", {}).get("results", [])
    log(f"Fetched {len(hits)} hits from SAM.gov")
    return hits

def sam_detail(notice_id: str):
    """Fetch full detail for a single opportunity using v2 API."""
    detail_url = f"https://api.sam.gov/prod/opportunities/v2/{notice_id}"
    headers = {"User-Agent": "Cognition Scraper/1.0"}
    r = requests.get(detail_url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def monday_find_item_by_topic(topic_no):
    """Find an item by Topic No (solicitationNumber) using items_page_by_column_values."""
    query = """
    query ($board_id: ID!, $column_id: String!, $values: [String!]!) {
      items_page_by_column_values(
        board_id: $board_id,
        columns: [{column_id: $column_id, column_values: $values}],
        limit: 10
      ) {
        items {
          id
          name
          column_values {
            id
            text
            value
          }
        }
      }
    }
    """
    variables = {
        "board_id": str(BOARD_ID),
        "column_id": "text_mkktdh29",    # 👈 Topic No column ID
        "values": [topic_no]             # 👈 Must be a list of strings
    }
    res = requests.post(API_URL, headers=HEADERS_MD,
                        json={"query": query, "variables": variables})
    res.raise_for_status()
    data = res.json()
    items = data.get("data", {}).get("items_page_by_column_values", {}).get("items", [])
    return items

def monday_create_item(title, agency, close_date_val, link, open_date_val,
                       tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command, client, rscore):
    """Create a new Monday item with all columns populated, including rScore."""
    colvals = {
        AGENCY_COLUMN: agency or "Unknown",
        DUEDATE_COLUMN: close_date_val,
        LINK_COLUMN: link,
        "text_mktm7tsx": "Cognition sam.gov",   # Source
        "date4": open_date_val,                     # Open Date
        "text_mkkqftmh": tpoc_name,                 # TPOC
        "tpoc_email_mkkqgfsv": {"email": tpoc_email, "text": tpoc_name or tpoc_email} if tpoc_email else None,
        "tpoc_phone_mkmfav28": tpoc_phone,
        "text_mkktdh29": topic_no,
        "text_mkkqeet2": description,
        "text_mkvqs88k": command,
        "text_mkkqwaty": client,
        "text_mkx77jn0": f"{float(rscore):.1f}%" if rscore else None  # ✅ formatted rScore
    }

    # Clean out Nones
    colvals = {k: v for k, v in colvals.items() if v}

    variables = {
        "board_id": str(BOARD_ID),
        "item_name": title,
        "column_values": json.dumps(colvals)
    }

    res = requests.post(API_URL, headers=HEADERS_MD, json={"query": MUTATION, "variables": variables})
    try:
        res.raise_for_status()
        data = res.json()
        log(f"✅ Created Monday item for {topic_no} ({title}) with rScore {rscore}")
        return data
    except Exception as e:
        log(f"❌ Monday.com API error: {e}")
        return None

def slack_bot_post_new_items(new_items):
    """Post new items to Slack using bot token."""
    if not SLACK_BOT_TOKEN:
        return

    lines = []
    for item in new_items:
        title = item.get("title", "Untitled")
        topic = item.get("topic", "N/A")
        agency = item.get("agency", "Unknown")
        due = item.get("due_text", "")
        link = item.get("link", "")
        rscore = item.get("rscore", 0)
        score_text = f" • Relevance: {float(rscore):.1f}%" if rscore else ""
        due_text_fmt = f" • Due {due}" if due else ""
        lines.append(f"• *{title}* ({topic}) – {agency}{score_text}{due_text_fmt}\n<{link}>")
        client = "Windsurf | Cognition AI"

    text = "\n".join(lines)
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}

    try:
        r = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=20)
        log(f"Slack notification sent for {len(new_items)} new items")
        r.raise_for_status()
    except Exception as e:
        log(f"❌ Slack API call failed: {e}")

def slack_bot_notify_no_results(count=0):
    """Notify Slack when script runs successfully but finds no new opportunities."""
    if not SLACK_BOT_TOKEN:
        return

    text = (
        f"✅ SAM.gov scan completed successfully – checked {count} opportunities for Cognition, "
        f"no new ones found today.\n"
        f"_(Checked {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})_"
    )
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}

    try:
        r = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log(f"❌ Slack API call failed (no results): {e}")

def main():
    new_items=[]
    
    hits = sam_search()
    
    if not hits:
        print("No results from SAM.gov search.")
        return
    
    for opp in hits:
        notice_id = opp.get("_id")
        title = opp.get("title", "Untitled")
        solnum = opp.get("solicitationNumber", "N/A")
        due = opp.get("responseDate", "No deadline")
        rscore = opp.get("_rScore")

        desc_short = ""
        if opp.get("descriptions"):
            desc_short = clean_html(opp["descriptions"][0].get("content", ""))

        # Build agency/command string from organizationHierarchy
        orgs = opp.get("organizationHierarchy", [])
        agency = "Unknown Agency"
        client = "Windsurf | Cognition AI"
        command = ""
        if orgs:
            dept = orgs[0].get("name", "")
            if "DEFENSE" in dept.upper() or dept.upper() == "DOD":
                if len(orgs) > 1:
                    command = orgs[1].get("name", "")
                agency = "Department of Defense"
            else:
                agency = orgs[0].get("name", "")

        # Check for duplicates
        existing = monday_find_item_by_topic(solnum)
        
        if existing:
            continue
        
        # Create item with available data
        close_date_val = format_monday_date(due)
        link = f"https://sam.gov/opp/{notice_id}/view"
        
        result = monday_create_item(
            title, agency, close_date_val, link, None,  # open_date_val
            "",             # tpoc_name
            "",             # tpoc_email
            "",             # tpoc_phone
            solnum,         # topic_no
            desc_short,     # description
            command,         # you computed this above from orgs
            client,
            rscore
        )
        
        if result and result.get('data', {}).get('create_item'):
            new_items.append({
                "title": title,
                "topic": solnum,
                "link": link,
                "agency": agency,
                "due_text": (close_date_val or {}).get("date", ""),
                "client": client,
                "rscore": rscore                
            })
    
    # Send summary statistics (concise version)
    total_found = len(hits)
    total_new = len(new_items)
    total_existing = total_found - total_new
    
    if total_new > 0:
        # Send new items notification
        slack_bot_post_new_items(new_items)
    else:
        # Send no results notification
        slack_bot_notify_no_results(total_found)

if __name__ == "__main__":
    main()
