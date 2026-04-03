import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper, log, clean_html, format_monday_date


class SDAImprovedScraper(BaseScraper):
    """Improved scraper for Space Development Agency (SDA) opportunities"""
    
    def __init__(self):
        super().__init__("SDA Improved")
        self.base_url = "https://www.sda.mil/opportunities/"
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
            
            # Method 1: Look for h3 elements with links
            h3_elements = soup.find_all('h3')
            for h3 in h3_elements:
                link = h3.find('a', href=True)
                if link:
                    title = link.get_text(strip=True)
                    if title and len(title) > 5:
                        description = ""
                        next_elem = h3.find_next_sibling()
                        if next_elem:
                            description = next_elem.get_text(strip=True)[:500]
                        
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
            containers = soup.find_all(['div', 'section', 'article'])
            for container in containers:
                container_text = container.get_text().lower()
                if any(keyword in container_text for keyword in 
                      ['opportunity', 'solicitation', 'call', 'rfi', 'rfei', 'broad agency']):
                    
                    title_elem = container.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        if title and len(title) > 5:
                            description = ""
                            p_elem = container.find('p')
                            if p_elem:
                                description = p_elem.get_text(strip=True)[:500]
                            
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
                    json_matches = re.findall(r'(\[.*?\])', script.string)
                    for match in json_matches:
                        try:
                            data = json.loads(match)
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and 'title' in item:
                                        opportunities.append(item)
                        except (json.JSONDecodeError, ValueError):
                            pass
            
            log(f"Found {len(opportunities)} opportunities in SDA script tags")
            return opportunities
            
        except Exception as e:
            log(f"Error fetching SDA data: {e}")
            return []
    
    def extract_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract required fields from SDA opportunity"""
        title = item.get("title", item.get("opportunityTitle", item.get("name", "")))
        
        description = item.get("description", item.get("summary", item.get("overview", "")))
        if description:
            description = clean_html(description)
        
        url = item.get("url", item.get("link", ""))
        if url and not url.startswith(('http://', 'https://')):
            if url.startswith('/'):
                url = f"https://www.sda.mil{url}"
            else:
                url = f"https://www.sda.mil/{url}"
        
        deadline = None
        deadline_fields = [
            "deadline", "dueDate", "submissionDeadline", "closeDate", 
            "responseDate", "finalDate", "registrationDeadline"
        ]
        
        for field in deadline_fields:
            if field in item and item[field]:
                deadline = item[field]
                break
        
        agency = item.get("agency", item.get("organization", item.get("sponsoringAgency", "SDA")))
        
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


def main():
    """Main function to run the SDA improved scraper"""
    scraper = SDAImprovedScraper()
    scraper.run()


if __name__ == "__main__":
    main()
