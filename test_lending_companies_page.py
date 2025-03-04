"""
Test extracting company information from the lending companies page
"""
import requests
from bs4 import BeautifulSoup
import json
import logging
import sys
from typing import Dict, List, Any

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def extract_companies_from_page():
    """Extract company information from the lending companies page"""
    url = "https://www.mintos.com/en/lending-companies/#details"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    logger.info(f"Fetching data from {url}")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.error(f"Failed to retrieve the page: status code {response.status_code}")
            return {}
            
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for company cards or sections
        logger.info("Parsing HTML content for company information")
        companies = {}
        
        # Strategy 1: Look for JSON data embedded in the page
        # Sometimes company data is embedded as a JSON object in a script tag
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.string
            if script_text and ('companies' in script_text or 'lenders' in script_text or 'originators' in script_text):
                logger.info("Found potential company data in script tag")
                try:
                    # Extract JSON from the script content
                    start_marker = None
                    for marker in ['var companies =', 'var lenders =', 'var originators =', 'const companies =']:
                        if script_text and marker in script_text:
                            start_marker = marker
                            break
                            
                    if start_marker:
                        json_start = script_text.find(start_marker) + len(start_marker)
                        # Find the end of the JSON object (usually a semicolon or closing script tag)
                        json_end = script_text.find(';', json_start)
                        if json_end == -1:
                            json_end = len(script_text)
                            
                        json_data = script_text[json_start:json_end].strip()
                        company_data = json.loads(json_data)
                        
                        if isinstance(company_data, list):
                            for company in company_data:
                                if isinstance(company, dict) and 'id' in company and 'name' in company:
                                    company_id = company.get('id').lower() if isinstance(company.get('id'), str) else str(company.get('id'))
                                    companies[company_id] = {
                                        'name': company.get('name'),
                                        'url': company.get('url', f"https://www.mintos.com/en/lending-companies/{company_id}")
                                    }
                        elif isinstance(company_data, dict):
                            for company_id, company in company_data.items():
                                if isinstance(company, dict) and 'name' in company:
                                    company_id = company_id.lower()
                                    companies[company_id] = {
                                        'name': company.get('name'),
                                        'url': company.get('url', f"https://www.mintos.com/en/lending-companies/{company_id}")
                                    }
                except Exception as e:
                    logger.error(f"Error parsing JSON from script: {e}")
                    
        # Strategy 2: Look for company cards or sections in the HTML
        if not companies:
            logger.info("Looking for company cards in HTML")
            company_cards = soup.find_all(['div', 'a'], class_=lambda c: c and any(term in c for term in ['company-card', 'lender-card', 'originator-card']))
            
            for card in company_cards:
                try:
                    # Extract company name
                    name_elem = card.find(['h2', 'h3', 'h4', 'div', 'span'], class_=lambda c: c and any(term in c for term in ['name', 'title']))
                    company_name = name_elem.get_text(strip=True) if name_elem else None
                    
                    # Extract company URL
                    company_url = None
                    if card.name == 'a':
                        company_url = card.get('href')
                    else:
                        link_elem = card.find('a')
                        if link_elem:
                            company_url = link_elem.get('href')
                            
                    # Extract company ID from URL
                    company_id = None
                    if company_url:
                        parts = company_url.rstrip('/').split('/')
                        company_id = parts[-1].lower()
                    elif company_name:
                        # Create slug from name
                        company_id = company_name.lower().replace(' ', '-')
                        
                    if company_id and company_name:
                        companies[company_id] = {
                            'name': company_name,
                            'url': company_url or f"https://www.mintos.com/en/lending-companies/{company_id}"
                        }
                except Exception as e:
                    logger.error(f"Error parsing company card: {e}")
                    
        # Strategy 3: Look for a table of companies
        if not companies:
            logger.info("Looking for company table")
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    try:
                        cells = row.find_all(['td', 'th'])
                        if cells and len(cells) >= 2:
                            name_cell = cells[0]
                            company_name = name_cell.get_text(strip=True)
                            
                            # Check for a link in the name cell
                            link = name_cell.find('a')
                            company_url = link.get('href') if link else None
                            
                            # Extract company ID from URL or name
                            company_id = None
                            if company_url:
                                parts = company_url.rstrip('/').split('/')
                                company_id = parts[-1].lower()
                            elif company_name:
                                company_id = company_name.lower().replace(' ', '-')
                                
                            if company_id and company_name:
                                companies[company_id] = {
                                    'name': company_name,
                                    'url': company_url or f"https://www.mintos.com/en/lending-companies/{company_id}"
                                }
                    except Exception as e:
                        logger.error(f"Error parsing table row: {e}")
        
        logger.info(f"Found {len(companies)} companies")
        
        # Save to file for reference
        with open("mintos_companies_direct.json", "w", encoding="utf-8") as f:
            json.dump(companies, f, indent=2)
            
        # Check for our problem companies
        problem_companies = ["iuvo", "iuvo group", "eleving", "eleving group", "mogo", "finko"]
        logger.info("Checking for problem companies:")
        for problem in problem_companies:
            found = False
            for company_id, data in companies.items():
                if problem.lower() in company_id.lower() or problem.lower() in data['name'].lower():
                    logger.info(f"- Found {problem} as '{data['name']}' (ID: {company_id})")
                    logger.info(f"  URL: {data['url']}")
                    found = True
            if not found:
                logger.info(f"- {problem.title()}: Not found")
                
        return companies
        
    except Exception as e:
        logger.error(f"Error fetching or parsing the page: {e}")
        return {}

if __name__ == "__main__":
    extract_companies_from_page()