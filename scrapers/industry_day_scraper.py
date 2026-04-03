import os
import requests
import json
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
BOARD_ID = os.getenv("MONDAY_BOARD_ID", "")  # event dashboard. must be string, not int

# Replace these with your real Monday column IDs
DUEDATE_COLUMN = "date_mkkz1cgv"
LINK_COLUMN = "link_mkktmmgp"  
SOLIC_COL       = "text_mkzb3jv1"   # unique Solicitation/Notice ID


# SAM.gov config
SAM_API_KEY = os.getenv("SAM_API_KEY", "")
SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
DETAIL_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{}"

# v1 search params
params = {
    #"api_key": SAM_API_KEY,
    "random": str(int(time.time()*1000)),
    "index": "opp",     # opportunity index
    "page": 0,
    "sort": "-modifiedDate",
    "size": 200,
    "mode": "search",
    #"responseType": "json",
    # 👇 Today in UTC, formatted like 2025-09-25-05:00
    #"response_date.from": datetime.now(timezone.utc).strftime("%Y-%m-%d-05:00"),
    #"response_date.to": "2026-09-23-05:00",    # optional upper bound
    "is_active": "true",
    "q": "\"Industry Day\"",
    "qMode": "ALL",
    "notice_type":"s"    
}



# === FUNCTIONS ===
def sam_search():
    r = requests.get(SEARCH_URL, params=params, timeout=60)
    #print("SAM request URL:", r.url)
    r.raise_for_status()
    data = r.json()

    
    # try a few common total-count locations
    total = (
        data.get("page", {}).get("totalElements")
        or data.get("page", {}).get("total_elements")
        or data.get("_embedded", {}).get("total")
        or data.get("totalRecords")
    )
    print("SAM reported total:", total)

    hits = data.get("_embedded", {}).get("results", [])
    #print("Returned this page:", len(hits))
    return hits
def sam_detail(notice_id):
    """Fetch v2 detail for a specific notice"""
    r = requests.get(DETAIL_URL.format(notice_id), timeout=60)  
    r.raise_for_status()
    return r.json()

def clean_html(raw):
    """Simple cleaner to strip <p>, <br>, etc."""
    return re.sub("<[^<]+?>", "", raw).strip() if raw else ""

def parse_detail(detail):
    """Extract relevant pieces from the v2 detail JSON."""
    # Title
    title = detail.get("title", "")
    solnum = detail.get("solicitationNumber","")
    detail = detail.get("data2", detail)

    # Description body: detail["description"] is a list of objects with "body"
    long_desc = ""
    desc_list = detail.get("description")
    if isinstance(desc_list, list) and desc_list:
        long_desc = clean_html(desc_list[0].get("body", ""))
    elif isinstance(desc_list, dict):
        long_desc = clean_html(desc_list.get("body", ""))
    else:
        long_desc = str(desc_list) if desc_list else ""

    # Point of Contacts
    poc_list = detail.get("pointOfContact", [])
    contacts = []
    for poc in poc_list:
        name = poc.get("fullName")
        email = poc.get("email")
        phone = poc.get("phone")
        parts = []
        if name:
            parts.append(name)
        if email:
            parts.append(email)
        if phone:
            parts.append(phone)
        contacts.append(" / ".join(parts))
    poc_str = "; ".join(contacts)

    # Deadlines: responseDeadline in "solicitation.deadlines.response"
    due_raw = detail.get("responseDate") or None
    close_date_val = None
    if due_raw:
        try:
            # Convert to YYYY-MM-DD
            dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
            close_date_val = {"date": dt.strftime("%Y-%m-%d")}
        except Exception:
            pass


    return {
        "title": title,
        "long_desc": long_desc,
        "pocs": poc_str,
        "solnum": solnum,
        "close date" : close_date_val
    }

# === MONDAY GRAPHQL ===
API_URL = "https://api.monday.com/v2"
HEADERS_MD = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}

MUTATION = """
mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
  create_item(
    board_id: $board_id,
    item_name: $item_name,
    column_values: $column_values
  ) {
    id
  }
}
"""

# helper stays the same
def format_monday_date(due_raw):
    if not due_raw or "T" not in due_raw:
        return None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        return {"date": dt.strftime("%Y-%m-%d")}
    except Exception as e:
        print("❌ Date parse failed:", e)
        return None
    
def monday_create_item(title, close_date_val, link, topic_no):

    # ✅ Link columns must be JSON
    link_val = {"url": link, "text": "SAM.gov"} if link else None

    colvals = {
        DUEDATE_COLUMN: close_date_val,
        LINK_COLUMN: link_val,
        SOLIC_COL: topic_no,
        "text_mkkqwaty": title
    }

    colvals = {k: v for k, v in colvals.items() if v is not None}

    variables = {
        "board_id": str(BOARD_ID),
        "item_name": title,
        "column_values": json.dumps(colvals)
    }

    #print("Creating Monday item with topic_no:", topic_no, "->", SOLIC_COL)

    
    res = requests.post(API_URL, headers=HEADERS_MD, json={"query": MUTATION, "variables": variables})
    res.raise_for_status()
    data = res.json()

    # ✅ Monday GraphQL errors come back in JSON
    if "errors" in data:
        #print("❌ Monday GraphQL errors:", json.dumps(data["errors"], indent=2))
        #print("❌ Sent colvals:", json.dumps(colvals, indent=2))
        return None

    print("✅ Monday created item:", data)
    return data

# === MONDAY HELPERS ===

def monday_find_item_by_topic(topic_no):
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
        "board_id": str(BOARD_ID),
        "column_id": SOLIC_COL,     # ✅ use your board’s real column id
        "values": [str(topic_no)]
    }
    res = requests.post(API_URL, headers=HEADERS_MD, json={"query": query, "variables": variables})
    res.raise_for_status()
    data = res.json()
    if "errors" in data:
        #print("❌ Monday API error:", data["errors"])
        return []
    return data.get("data", {}).get("items_page_by_column_values", {}).get("items", [])


#send to slack
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")




def slack_bot_post_new_items(new_items):
    """Post a compact list of new items to Slack using chat.postMessage."""
    if not SLACK_BOT_TOKEN or not new_items:
        return

    lines = [f"*🆕 {len(new_items)} new SAM.gov Industry Days*"]
    for it in new_items[:30]:
        title = it.get("title", "(no title)")
        topic = it.get("topic", "")
        link = it.get("link", "")
        due_text = it.get("due_text", "")
        due_text_fmt = f" • Due {due_text}" if due_text else ""
        lines.append(f"• *{title}* ({topic}) – {due_text_fmt}\n<{link}>")

    text = "\n".join(lines)
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}

    try:
        r = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=20)
        #print("Slack status:", r.status_code)
        #print("Slack response:", r.text)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Slack API call failed: {e}")

def slack_bot_notify_no_results(count=0):
    """Notify Slack when the script runs successfully but finds no new opportunities."""
    if not SLACK_BOT_TOKEN:
        return

    text = (
        f"✅ *SAM.gov scan completed successfully* – checked {count} Industry Days, "
        f"no new ones found today.\n"
        f"_(Checked {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})_"
    )

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}

    try:
        r = requests.post("https://slack.com/api/chat.postMessage",
                          headers=headers, json=payload, timeout=15)
        #print("Slack (no results) status:", r.status_code)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Slack API call failed (no results): {e}")
        
def main():
    new_items=[]
    
    hits = sam_search()
    if not hits:
        print("No results from v1 search.")
        return
    

    for opp in hits:
        notice_id = opp.get("_id")
        title = opp.get("title", "Untitled")
        solnum = opp.get("solicitationNumber", "N/A")
        due = opp.get("responseDate", "No deadline")
        desc_short = ""
        if opp.get("descriptions"):
            desc_short = clean_html(opp["descriptions"][0].get("content", ""))   
        
        # Step 2: pull detail
        if not notice_id:
            # No detail possible; still create with what we have
            close_date_val = format_monday_date(due)
            if not monday_find_item_by_topic(solnum):
                monday_create_item(
                    title,
                    close_date_val,
                    f"https://sam.gov/opp/{solnum or ''}".strip("/"),
                    None,           # open_date_val
                    solnum         # topic_no                  
                )
            continue
          
          
        try:
            # ---- V2 detail fetch
            detail_raw = sam_detail(notice_id)
            # CHANGED: unwrap, but keep both layers
            detail_data2 = detail_raw.get("data2", {})

            # CHANGED: UI link -> try data2.uiLink, else build public opp link
            link = detail_data2.get("uiLink") or f"https://sam.gov/opp/{notice_id}/view"

            # CHANGED: Description must come from ROOT (detail_raw['description'][0].body)
            description = ""
            root_desc_list = detail_raw.get("description", [])
            if isinstance(root_desc_list, list) and root_desc_list:
                description = clean_html(root_desc_list[0].get("body", ""))

            # CHANGED: Open Date — prefer v1 publishDate; else detail_raw.postedDate
            posted_raw = opp.get("publishDate") or detail_raw.get("postedDate")
            open_date_val = format_monday_date(posted_raw)

            
            # Topic No (solicitationNumber) — data2 usually has the authoritative value
            topic_no = detail_data2.get("solicitationNumber") or solnum

            
        except Exception as e:
            #print(f"❌ Failed to fetch/parse detail for {notice_id}: {e}")
            # Fallback to minimal fields
            link = f"https://sam.gov/opp/{notice_id}/view"
            open_date_val = None
            topic_no = solnum

        # Close date for Monday date column
        close_date_val = format_monday_date(due)

        
        # Upsert (create-or-skip-only)
        existing = monday_find_item_by_topic(topic_no)
        if existing:
            #already there; skip
            pass
        else:
            monday_create_item(
                title, close_date_val, link,  topic_no
            )
            #Track for Slack
            new_items.append({
                "title": title,
                "topic": topic_no,
                "link": link,
                "due_text": (close_date_val or {}).get("date", "")
            })
    #Slack Summary (new only)
    if new_items:
        slack_bot_post_new_items(new_items)
    else:
        slack_bot_notify_no_results(len(hits))

if __name__ == "__main__":
    main()
