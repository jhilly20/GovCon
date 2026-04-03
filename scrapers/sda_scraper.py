import json
import os
import re
import time
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




# Inline utility functions (previously from base_scraper)
def log(message):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp} UTC] {message}")

def clean_html(raw):
    if not raw:
        return ""
    return re.sub("<[^<]+?>", "", raw).strip()

def format_monday_date(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return {"date": dt.strftime("%Y-%m-%d")}
    except Exception:
        return None


# Monday.com configuration
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID", "")
MONDAY_API_URL = "https://api.monday.com/v2"
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")

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


class SDAImprovedScraper:
    """Improved scraper for Space Development Agency (SDA) opportunities"""
    
    def __init__(self):
        self.name = "SDA Improved"
        self.base_url = "https://www.sda.mil/opportunities/"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        })
    
    def fetch_data(self) -> Iterable[Dict[str, Any]]:
        """Fetch data from SDA opportunities page using improved methods"""
        try:
            log(f"Fetching SDA data from: {self.base_url}")
            
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            
            # Parse HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            opportunities = []
            
            # Method 1: Look for h3 elements with links (based on the XPath provided)
            # XPath: //*[@id="fl-post-290"]/div/div/div[4]/div[1]/div/div[1]/div/div/div[3]/div/div/div[1]/h3/a
            h3_elements = soup.find_all('h3')
            for h3 in h3_elements:
                link = h3.find('a', href=True)
                if link:
                    title = link.get_text(strip=True)
                    if title and len(title) > 5:
                        # Find associated description
                        description = ""
                        # Look for sibling elements that might contain description
                        next_elem = h3.find_next_sibling()
                        if next_elem:
                            description = next_elem.get_text(strip=True)[:500]
                        
                        # Get the full URL
                        href = link.get('href', '')
                        if href.startswith('/'):
                            url = f"https://www.sda.mil{href}"
                        else:
                            url = href
                        
                        opportunities.append({
                            'title': title,
                            'description': description,
                            'url': url
                        })
            
            if opportunities:
                log(f"Found {len(opportunities)} opportunities in SDA h3 elements")
                return opportunities
            
            # Method 2: Look for all links that might be opportunities
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Filter for likely opportunity links
                if (text and len(text) > 10 and 
                    ('opportunity' in text.lower() or 'solicitation' in text.lower() or 
                     'call' in text.lower() or 'rfi' in text.lower() or 
                     'rfei' in text.lower() or 'broad agency' in text.lower())):
                    
                    if href.startswith('/'):
                        url = f"https://www.sda.mil{href}"
                    else:
                        url = href
                    
                    opportunities.append({
                        'title': text,
                        'description': 'SDA Opportunity',
                        'url': url
                    })
            
            if opportunities:
                log(f"Found {len(opportunities)} opportunities in SDA filtered links")
                return opportunities
            
            # Method 3: Look for specific patterns in the page structure
            # Look for containers that might hold opportunity information
            containers = soup.find_all(['div', 'section', 'article'])
            for container in containers:
                # Check if container has text that suggests it's an opportunity
                container_text = container.get_text().lower()
                if any(keyword in container_text for keyword in 
                      ['opportunity', 'solicitation', 'call', 'rfi', 'rfei', 'broad agency']):
                    
                    # Extract title from h1-h6 elements
                    title_elem = container.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        if title and len(title) > 5:
                            # Extract description
                            description = ""
                            p_elem = container.find('p')
                            if p_elem:
                                description = p_elem.get_text(strip=True)[:500]
                            
                            # Find links
                            link = container.find('a', href=True)
                            url = ""
                            if link:
                                href = link.get('href', '')
                                if href.startswith('/'):
                                    url = f"https://www.sda.mil{href}"
                                else:
                                    url = href
                            
                            opportunities.append({
                                'title': title,
                                'description': description,
                                'url': url
                            })
            
            if opportunities:
                log(f"Found {len(opportunities)} opportunities in SDA containers")
                return opportunities
            
            # Method 4: Look for data in script tags
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # Look for JSON data
                    json_matches = re.findall(r'(\[.*?\])', script.string)
                    for match in json_matches:
                        try:
                            data = json.loads(match)
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and 'title' in item:
                                        opportunities.append(item)
                        except Exception:
                            pass
            
            log(f"Found {len(opportunities)} opportunities in SDA script tags")
            return opportunities
            
        except Exception as e:
            log(f"Error fetching SDA data: {e}")
            return []
    
    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract required fields from SDA opportunity"""
        # Extract title
        title = item.get("title", item.get("opportunityTitle", item.get("name", "")))
        
        # Extract description
        description = item.get("description", item.get("summary", item.get("overview", "")))
        if description:
            description = clean_html(description)
        
        # Extract URL
        url = item.get("url", item.get("link", ""))
        if url and not url.startswith(('http://', 'https://')):
            if url.startswith('/'):
                url = f"https://www.sda.mil{url}"
            else:
                url = f"https://www.sda.mil/{url}"
        
        # Extract deadline
        deadline = None
        deadline_fields = [
            "deadline", "dueDate", "submissionDeadline", "closeDate", 
            "responseDate", "finalDate", "registrationDeadline"
        ]
        
        for field in deadline_fields:
            if field in item and item[field]:
                deadline = item[field]
                break
        
        # Extract agency
        agency = item.get("agency", item.get("organization", item.get("sponsoringAgency", "SDA")))
        
        # Additional fields for SDA
        opportunity_type = item.get("opportunityType", item.get("solicitationType", ""))
        opportunity_number = item.get("opportunityNumber", item.get("solicitationNumber", ""))
        
        return {
            "title": title,
            "description": description,
            "url": url,
            "deadline": deadline,
            "agency": agency,
            "opportunity_type": opportunity_type,
            "opportunity_number": opportunity_number
        }


    def run(self):
        """Run the scraper: fetch data, deduplicate, create Monday items, notify Slack."""
        items = list(self.fetch_data())
        log(f"Fetched {len(items)} items from {self.name}")

        if not MONDAY_API_KEY:
            log("Warning: MONDAY_API_KEY not set. Skipping Monday.com integration.")
            for item in items[:5]:
                fields = self.extract_fields(item)
                log(f"  {fields.get('title', 'No title')}")
            return

        headers = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}
        new_items = []

        for item in items:
            fields = self.extract_fields(item)
            title = fields.get("title", "")
            if not title:
                continue

            deadline_val = format_monday_date(fields.get("deadline"))
            colvals = {
                TITLE_COLUMN: title,
                DESCRIPTION_COLUMN: fields.get("description", ""),
                URL_COLUMN: fields.get("url", ""),
                DEADLINE_COLUMN: deadline_val,
                AGENCY_COLUMN: fields.get("agency", "SDA"),
                SOURCE_COLUMN: "SDA scraper",
            }
            colvals = {k: v for k, v in colvals.items() if v is not None}

            variables = {
                "board_id": str(MONDAY_BOARD_ID),
                "item_name": title,
                "column_values": json.dumps(colvals),
            }
            try:
                res = self.session.post(
                    MONDAY_API_URL,
                    headers=headers,
                    json={"query": MUTATION, "variables": variables},
                    timeout=30,
                )
                res.raise_for_status()
                data = res.json()
                if "errors" not in data:
                    log(f"Created Monday item: {title}")
                    new_items.append(fields)
            except Exception as e:
                log(f"Error creating Monday item for {title}: {e}")

        # Slack notification
        if SLACK_BOT_TOKEN and new_items:
            lines = [f"*{len(new_items)} new SDA opportunities*"]
            for it in new_items[:30]:
                lines.append(f"* *{it.get('title', '')}*\n<{it.get('url', '')}>")
            text = "\n".join(lines)
            slack_headers = {
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            }
            payload = {"channel": SLACK_CHANNEL, "text": text}
            try:
                r = self.session.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=slack_headers,
                    json=payload,
                    timeout=20,
                )
                r.raise_for_status()
            except Exception as e:
                log(f"Slack notification failed: {e}")

        log(f"SDA scraper complete: {len(new_items)} new items")


def main():
    """Main function to run the SDA improved scraper"""
    scraper = SDAImprovedScraper()
    scraper.run()


if __name__ == "__main__":
    main()