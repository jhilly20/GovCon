import os
import requests
import json
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
SOLIC_COL       = "text_mkktdh29"   # unique Solicitation/Notice ID


# SAM.gov config
SAM_API_KEY = os.getenv("SAM_API_KEY", "")
SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
DETAIL_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{}"

# v1 search params
params = {
    # "api_key": SAM_API_KEY,
    "random": str(int(time.time()*1000)),
    "index": "opp",     # opportunity index
    "page": 0,
    "sort": "-relevance",
    "size": 100,
     "mode": "search",
    #"responseType": "json",
    "is_active": "true",
    "q": "C-sUAS OR C-UAS OR C-UXS OR CUAS",
    "qMode": "ANY",

    
}



# === FUNCTIONS ===
def sam_search(session: requests.Session):
    # Use requests params to properly encode the query
    r = session.get(SEARCH_URL, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    # v1 nests results under "_embedded.results"
    hits = data.get("_embedded", {}).get("results", [])
    
    return hits

def sam_detail(session: requests.Session, notice_id):
    """Fetch v2 detail for a specific notice"""
    r = session.get(DETAIL_URL.format(notice_id), timeout=60)
    r.raise_for_status()
    return r.json()

def clean_html(raw):
    """Simple cleaner to strip <p>, <br>, etc."""
    return re.sub("<[^<]+?>", "", raw).strip() if raw else ""

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] {msg}")

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
        dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        return {"date": dt.strftime("%Y-%m-%d")}
    except Exception as e:
        #print("Date parse failed:", e)
        return None
    
def monday_create_item(session: requests.Session, title, agency, close_date_val, link, open_date_val,
                       tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command, rscore):
    """Create a new Monday item with all columns populated, including rScore."""
    colvals = {
        AGENCY_COLUMN: agency or "Unknown",
        DUEDATE_COLUMN: close_date_val,
        LINK_COLUMN: link,
        "text_mktm7tsx": "CUAS python sam.gov",   # Source
        "date4": open_date_val,                     # Open Date
        "text_mkkqftmh": tpoc_name,                 # TPOC
        "tpoc_email_mkkqgfsv": {"email": tpoc_email, "text": tpoc_name or tpoc_email} if tpoc_email else None,
        "tpoc_phone_mkmfav28": tpoc_phone,
        SOLIC_COL: topic_no,
        "text_mkkqeet2": description,
        "text_mkvqs88k": command,
        "text_mkkqwaty": title,
        "text_mkx77jn0": f"{float(rscore):.1f}%" if rscore else None  # formatted rScore
    }

    # Clean out Nones
    colvals = {k: v for k, v in colvals.items() if v}

    variables = {
        "board_id": str(BOARD_ID),
        "item_name": title,
        "column_values": json.dumps(colvals)
    }

    res = session.post(API_URL, headers=HEADERS_MD, json={"query": MUTATION, "variables": variables})
    try:
        res.raise_for_status()
        data = res.json()
        return data
    except Exception as e:
        print(f"Monday create_item failed: {e} — {res.text}")
        return None
# === MONDAY HELPERS ===

 # send to slack
#send to slack
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("CUAS_SLACK_CHANNEL", "")  # cUAS channel




def slack_bot_post_new_items(session: requests.Session, new_items):
    """Post a compact list of new items to Slack using chat.postMessage."""
    if not SLACK_BOT_TOKEN or not new_items:
        return

    lines = [f"*\U0001f195 {len(new_items)} new SAM.gov C-UXS opportunities*"]
    for it in new_items[:30]:
        title = it.get("title", "(no title)")
        rscore = it.get("rscore")
        topic = it.get("topic", "")
        link = it.get("link", "")
        agency = it.get("agency", "")
        due_text = it.get("due_text", "")
        score_text = f" \u2022 Relevance: {float(rscore):.1f}%" if rscore else ""
        due_text_fmt = f" \u2022 Due {due_text}" if due_text else ""
        lines.append(f"\u2022 *{title}* ({topic}) \u2013 {agency}{score_text}{due_text_fmt}\n<{link}>")

    text = "\n".join(lines)
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}

    try:
        r = session.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Slack API call failed: {e}")

def slack_bot_notify_no_results(session: requests.Session, count=0):
    """Notify Slack when the script runs successfully but finds no new opportunities."""
    if not SLACK_BOT_TOKEN:
        return

    text = (
        f"\u2705 SAM.gov scan completed successfully \u2013 checked {count} C-UXS opportunities, "
        f"no new ones found today.\n"
        f"_(Checked {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})_"
    )

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": SLACK_CHANNEL, "text": text}

    try:
        r = session.post("https://slack.com/api/chat.postMessage",
                          headers=headers, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"Slack API call failed (no results): {e}")
        
def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def fetch_existing_topics(session: requests.Session, limit=200, debug=False):
    """Fetch existing Topic No values and item names from Monday to avoid per-item lookups."""
    query = """
    query ($board_id: [ID!]!, $limit: Int!, $cursor: String, $col_id: String!) {
      boards(ids: $board_id) {
        items_page(limit: $limit, cursor: $cursor) {
          cursor
          items {
          id
          name
          column_values(ids: [$col_id]) {
              id
              text
              value
            }
          }
        }
      }
    }
    """
    topics = set()
    names = set()
    cursor = None
    while True:
        variables = {
            "board_id": [str(BOARD_ID)],
            "limit": limit,
            "cursor": cursor,
            "col_id": SOLIC_COL,
        }
        res = session.post(API_URL, headers=HEADERS_MD, json={"query": query, "variables": variables})
        res.raise_for_status()
        data = res.json()
        if "errors" in data:
            log(f"Monday API errors: {json.dumps(data['errors'], indent=2)}")
            return set()
        boards = data.get("data", {}).get("boards", [])
        if not boards:
            log("Monday API returned no boards for the given board_id.")
            return set()
        page = boards[0].get("items_page", {})
        items = page.get("items", [])
        log(f"Monday items_page fetched {len(items)} items")
        for item in items:
            name = item.get("name")
            if name:
                names.add(normalize_name(name))
            cols = item.get("column_values", [])
            if debug and cols:
                log(f"Sample column_values: {json.dumps(cols, indent=2)}")
                debug = False
            for col in cols:
                text_val = (col.get("text") or "").strip()
                if text_val:
                    topics.add(text_val)
                    continue
                raw_val = col.get("value")
                if raw_val:
                    try:
                        parsed = json.loads(raw_val)
                        if isinstance(parsed, str) and parsed.strip():
                            topics.add(parsed.strip())
                        elif isinstance(parsed, dict):
                            value = (parsed.get("text") or parsed.get("value") or "").strip()
                            if value:
                                topics.add(value)
                    except json.JSONDecodeError:
                        pass
        cursor = page.get("cursor")
        if not cursor:
            break
    return topics, names


def main():
    new_items = []

    if not SAM_API_KEY:
        log("Warning: missing SAM_API_KEY env var.")
    if not MONDAY_API_KEY:
        log("Warning: missing MONDAY_API_KEY env var; Monday updates will be skipped.")

    session = requests.Session()

    start = time.time()
    hits = sam_search(session)
    log(f"Search returned {len(hits)} hits in {time.time() - start:.2f}s")
    if not hits:
        log("No results from v1 search.")
        return

    existing_topics = set()
    existing_names = set()
    if MONDAY_API_KEY:
        start = time.time()
        existing_topics, existing_names = fetch_existing_topics(
            session, debug=os.getenv("MONDAY_DEBUG") == "1"
        )
        log(
            f"Fetched {len(existing_topics)} existing topics and {len(existing_names)} names "
            f"in {time.time() - start:.2f}s"
        )

    for opp in hits:
        notice_id = opp.get("_id")
        title = opp.get("title", "Untitled")
        solnum = opp.get("solicitationNumber", "N/A")
        due = opp.get("responseDate", "No deadline")
        rscore = opp.get("_rScore")  # get relevance score

        desc_short = ""
        if opp.get("descriptions"):
            desc_short = clean_html(opp["descriptions"][0].get("content", ""))

        # Build agency/command string from organizationHierarchy
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
            name_key = normalize_name(title)
            if MONDAY_API_KEY and solnum not in existing_topics and name_key not in existing_names:
                monday_create_item(
                    session,
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
                    command,        # you computed this above from orgs
                    rscore
                )
            continue
          
          
        try:
            # ---- V2 detail fetch
            detail_raw = sam_detail(session, notice_id)
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

            # TPOC broken out
            tpoc_name, tpoc_email, tpoc_phone = "", "", ""
            poc_list = detail_data2.get("pointOfContact", [])
            if poc_list:
                tpoc_name = poc_list[0].get("fullName", "")
                tpoc_email = poc_list[0].get("email", "")
                tpoc_phone = poc_list[0].get("phone", "")


            # Topic No (solicitationNumber) — data2 usually has the authoritative value
            topic_no = detail_data2.get("solicitationNumber") or solnum

            
        except Exception as e:
            # Fallback to minimal fields
            link = f"https://sam.gov/opp/{notice_id}/view"
            open_date_val = None
            tpoc_name, tpoc_email, tpoc_phone = "", "", ""
            topic_no = solnum
            description = desc_short

        # Close date for Monday date column
        close_date_val = format_monday_date(due)

        # Upsert (create-or-skip-only)
        name_key = normalize_name(title)
        if MONDAY_API_KEY and (topic_no in existing_topics or (not topic_no and name_key in existing_names)):
            continue

        if MONDAY_API_KEY:
            monday_create_item(
                session,
                title, agency, close_date_val, link, open_date_val, tpoc_name, tpoc_email, tpoc_phone, topic_no, description, command, rscore
            )
            existing_topics.add(topic_no)
            if name_key:
                existing_names.add(name_key)
        # Track for Slack
        new_items.append({
            "title": title,
            "topic": topic_no,
            "link": link,
            "agency": agency,
            "due_text": (close_date_val or {}).get("date", ""),
            "rscore": rscore
        })
    
    #Slack Summary (new only)
    if SLACK_BOT_TOKEN:
        if new_items:
            slack_bot_post_new_items(session, new_items)
        else:
            slack_bot_notify_no_results(session, len(hits))

if __name__ == "__main__":
    main()
