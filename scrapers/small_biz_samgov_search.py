import os
import requests
import json
from urllib.parse import urlencode
import time
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")



# === CONFIG ===
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
BOARD_ID = os.getenv("MONDAY_BOARD_ID", "")  # must be string, not int

# Replace these with your real Monday column IDs
AGENCY_COLUMN = "text_mkvqfmz5"
DUEDATE_COLUMN = "date_mkkqedzc"
LINK_COLUMN = "text_mkkq2vab"  
SOLIC_COL       = "text_mkm0rbb8"   # unique Solicitation/Notice ID


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
    "size": 100,
     "mode": "search",
    "responseType": "json",
    # 👇 Today in UTC, formatted like 2025-09-25-05:00
    "response_date.from": datetime.now(timezone.utc).strftime("%Y-%m-%d-05:00"),
    #"response_date.to": "2026-09-23-05:00",    # optional upper bound
    "is_active": "true",
    "q": "",
    "qMode": "ALL",
    "naics": "541715",
    "notice_type": "r,p,o,k",                # Sources Sought, Presolicitation, Solicitation, Combined
    "set_aside": "SBP,SBA"
}

API_URL = "https://api.monday.com/v2"
HEADERS_MD = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("CUAS_SLACK_CHANNEL", "") # CUAS-specific channel

# ===SAM.gov FUNCTIONS ===
def sam_search():
    # Manually build query string to avoid urlencode escaping the colon
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{SEARCH_URL}?{query}"
    #print("DEBUG URL:", url)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    # v1 nests results under "_embedded.results"
    hits = data.get("_embedded", {}).get("results", [])
    
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
        "close_date": close_date_val
    }



# === MONDAY HELPERS ===
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
    #print("🔍 monday_find_item_by_topic response:", json.dumps(data, indent=2))

    if "errors" in data:
        #print("❌ Monday API error:", data["errors"])
        return []

    return data.get("data", {}).get("items_page_by_column_values", {}).get("items", [])
    
def monday_create_item(title, agency, close_date_val, link, open_date_val,
                       tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command):
    colvals = {
        AGENCY_COLUMN: agency or "Unknown",
        DUEDATE_COLUMN: close_date_val,
        LINK_COLUMN: link,
        "text_mktm7tsx": "C-UXS sam.gov",   # Source
        "date4": open_date_val,              # Open Date
        "text_mkkqftmh": tpoc_name,          # TPOC
        "tpoc_email_mkkqgfsv": {"email": tpoc_email, "text": tpoc_name or tpoc_email} if tpoc_email else None,   # TPOC email
        "tpoc_phone_mkmfav28": tpoc_phone,   # TPOC phone
        "text_mkktdh29": topic_no,           # Topic No
        "text_mkkqeet2": description,        # Description
        "text_mkvqs88k": command,             # Command
        "text_mkkqwaty": title               # 🔹 Duplicate Title column
    }
    if close_date_val:
        colvals[DUEDATE_COLUMN] = close_date_val

    # Remove None values
    colvals = {k:v for k,v in colvals.items() if v}
    # === MONDAY GRAPHQL ===
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

    variables = {
        "board_id": str(BOARD_ID),
        "item_name": title,
        "column_values": json.dumps(colvals)
    }
    res = requests.post(API_URL, headers=HEADERS_MD, json={"query": MUTATION, "variables": variables})
    res.raise_for_status()
    data = res.json()
    #print("Monday response:", data)
    return data


def monday_upsert_item(title, agency, close_date_val, link, open_date_val,
                       tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command):
    """Check if item exists by Topic No; update if changed, else create."""
    existing = monday_find_item_by_topic(topic_no)

    # Build base payload
    colvals = {
        AGENCY_COLUMN: agency or "Unknown",
        DUEDATE_COLUMN: close_date_val,
        LINK_COLUMN: link,
        "text_mktm7tsx": "small biz setaside 541715 sam.gov",  # Source (default)
        "date4": open_date_val,
        "text_mkkqftmh": tpoc_name,
        "tpoc_email_mkkqgfsv": {"email": tpoc_email, "text": tpoc_name or tpoc_email} if tpoc_email else None,
        "tpoc_phone_mkmfav28": tpoc_phone,
        "text_mkktdh29": topic_no,
        "text_mkkqeet2": description,
        "text_mkvqs88k": command,
        "text_mkkqwaty": title
    }
    colvals = {k: v for k, v in colvals.items() if v}

    if existing:
        item = existing[0]
        item_id = item["id"]
        #print(f"⚡ Found existing item for Topic {topic_no} (ID {item_id}). Skipping (no updates).")
    else:
        #print(f"➕ Creating new item for Topic {topic_no}")
        monday_create_item(
            title, agency, close_date_val, link, open_date_val,
            tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command
        )
#send to slack
def slack_bot_post_new_items(new_items):
    """Post a compact list of new items to Slack using chat.postMessage."""
    if not SLACK_BOT_TOKEN or not new_items:
        return

    # Build a clean message with links
    lines = [f"*🆕 {len(new_items)} new C-UXS SAM.gov opportunities for NAICS 541715 small biz or partial set aside*"]
    for it in new_items[:30]:  # avoid super long posts; send top 30
        title = it.get("title", "(no title)")
        topic = it.get("topic", "")
        link  = it.get("link", "")
        agency = it.get("agency", "")
        due_text = it.get("due_text", "")
        lines.append(f"• *{title}* ({topic}) – {agency}  {f'• Due {due_text}' if due_text else ''}\n<{link}>")

    text = "\n".join(lines)

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}
    try:
        r = requests.post("https://slack.com/api/chat.postMessage",
                          headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        resp = r.json()
        if not resp.get("ok"):
            print(f"❌ Slack API error: {resp}")
    except Exception as e:
        print(f"❌ Slack API call failed: {e}")

def slack_bot_notify_no_results(count=0):
    """Notify Slack when the script runs successfully but finds no new opportunities."""
    if not SLACK_BOT_TOKEN:
        return

    text = (
        f"✅ *C-UXS SAM.gov scan completed successfully* – checked {count} C-UXS opportunities, "
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
        print("Slack (no results) status:", r.status_code)
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

        # 🔹 Build agency/command string from organizationHierarchy
        # === AGENCY / COMMAND LOGIC ===
        orgs = opp.get("organizationHierarchy", [])
        agency = "Unknown Agency"
        command = ""
        if orgs:
            dept = orgs[0].get("name", "")
            if "DEFENSE" in dept.upper() or dept.upper() == "DOD":
                if len(orgs) > 1:
                    agency = orgs[1].get("name", "")
                if len(orgs) > 2:
                    command = orgs[2].get("name", "")
            else:
                agency = dept
                if len(orgs) > 1:
                    command = orgs[1].get("name", "")
        
        # Step 2: pull detail
        if not notice_id:
            # No detail possible; still create with what we have
            close_date_val = format_monday_date(due)
            if not monday_find_item_by_topic(solnum):
                monday_create_item(
                    title,
                    agency,
                    close_date_val,
                    f"https://sam.gov/opp/{solnum or ''}".strip("/"),
                    None,           # open_date_val
                    "",             # tpoc_name
                    "",             # tpoc_email
                    "",             # tpoc_phone
                    solnum,         # topic_no
                    desc_short,     # description
                    command         # you computed this above from orgs
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

            # ✅ TPOC broken out
            tpoc_name, tpoc_email, tpoc_phone = "", "", ""
            poc_list = detail_data2.get("pointOfContact", [])
            if poc_list:
                tpoc_name = poc_list[0].get("fullName", "")
                tpoc_email = poc_list[0].get("email", "")
                tpoc_phone = poc_list[0].get("phone", "")


            # Topic No (solicitationNumber) — data2 usually has the authoritative value
            topic_no = detail_data2.get("solicitationNumber") or solnum

            
        except Exception as e:
            #print(f"❌ Failed to fetch/parse detail for {notice_id}: {e}")
            # Fallback to minimal fields
            link = f"https://sam.gov/opp/{notice_id}/view"
            open_date_val = None
            tpoc_name, tpoc_email, tpoc_phone = "", "", ""
            topic_no = solnum
            description = desc_short

        # Close date for Monday date column
        close_date_val = format_monday_date(due)

        # Create item with all fields


        # Upsert (create-or-skip-only)
        existing = monday_find_item_by_topic(topic_no)
        if existing:
            #already there; skip
            pass
        else:
            monday_create_item(
                title, agency, close_date_val, link, open_date_val, tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command
            )
            #Track for Slack
            new_items.append({
                "title": title,
                "topic": topic_no,
                "link": link,
                "agency":agency,
                "due_text": (close_date_val or {}).get("date", "")
            })
    #Slack Summary (new only)
    if new_items:
        slack_bot_post_new_items(new_items)
    else:
        slack_bot_notify_no_results(len(hits))

if __name__ == "__main__":
    main()

