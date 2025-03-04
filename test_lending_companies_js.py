"""
Test extracting company information from the lending companies page using JavaScript rendering
"""
import json
import logging
import sys
from requests_html import HTMLSession
import time
import re

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def extract_companies_with_js_rendering():
    """Extract company information from the lending companies page using JavaScript rendering"""
    url = "https://www.mintos.com/en/lending-companies/#details"
    
    logger.info(f"Fetching data from {url} with JS rendering")
    try:
        session = HTMLSession()
        response = session.get(url)
        
        # Render the JavaScript
        logger.info("Rendering JavaScript (this may take a while)...")
        response.html.render(timeout=60, sleep=5)
        
        logger.info("JavaScript rendered, extracting data...")
        html_content = response.html.html
        
        # Save the rendered HTML for inspection
        with open("lending_companies_rendered.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # Extract company data
        companies = {}
        
        # Look for company cards or items in the rendered HTML
        logger.info("Looking for company elements in the rendered HTML")
        
        # Find company cards
        company_elements = response.html.find('.company-card, .lending-company-card, .lender-card, [data-company-id]')
        
        logger.info(f"Found {len(company_elements)} company elements")
        
        for element in company_elements:
            try:
                # Get company ID
                company_id = element.attrs.get('data-company-id') or element.attrs.get('id')
                
                # Get company name from various possible elements
                name_elem = element.find('h3, h4, .company-name, .lender-name, .name', first=True)
                company_name = name_elem.text if name_elem else None
                
                # Get company URL
                company_url = None
                link_elem = element.find('a', first=True)
                if link_elem:
                    company_url = link_elem.attrs.get('href')
                    
                # If we found enough information, add to our results
                if company_id and company_name:
                    companies[company_id] = {
                        'name': company_name,
                        'url': company_url or f"https://www.mintos.com/en/lending-companies/{company_id}"
                    }
                    logger.info(f"Added company: {company_name} (ID: {company_id})")
            except Exception as e:
                logger.error(f"Error processing company element: {e}")
        
        # If previous approach didn't work, try looking for JavaScript data
        if not companies:
            logger.info("Looking for company data in JavaScript variables...")
            
            # Try to extract from JavaScript variables
            script_pattern = re.compile(r'(window\.lendingCompanies|var lendingCompanies)\s*=\s*(\[.*?\]|\{.*?\});', re.DOTALL)
            match = script_pattern.search(html_content)
            
            if match:
                logger.info("Found company data in JavaScript")
                json_str = match.group(2)
                try:
                    company_data = json.loads(json_str)
                    
                    if isinstance(company_data, list):
                        for company in company_data:
                            if 'id' in company and 'name' in company:
                                company_id = str(company['id'])
                                companies[company_id] = {
                                    'name': company['name'],
                                    'url': company.get('url', f"https://www.mintos.com/en/lending-companies/{company_id}")
                                }
                    elif isinstance(company_data, dict):
                        for company_id, company in company_data.items():
                            if 'name' in company:
                                companies[company_id] = {
                                    'name': company['name'],
                                    'url': company.get('url', f"https://www.mintos.com/en/lending-companies/{company_id}")
                                }
                except Exception as e:
                    logger.error(f"Error parsing company JSON: {e}")
        
        # If all else fails, look for a table with company information
        if not companies:
            logger.info("Looking for company table...")
            tables = response.html.find('table')
            
            for table in tables:
                rows = table.find('tr')
                for row in rows:
                    cells = row.find('td')
                    if len(cells) >= 2:
                        name_cell = cells[0]
                        company_name = name_cell.text
                        
                        # Check for link
                        link_elem = name_cell.find('a', first=True)
                        company_url = None
                        if link_elem:
                            company_url = link_elem.attrs.get('href')
                            
                        if company_name:
                            # Create an ID from the name
                            company_id = company_name.lower().replace(' ', '-')
                            companies[company_id] = {
                                'name': company_name,
                                'url': company_url or f"https://www.mintos.com/en/lending-companies/{company_id}"
                            }
        
        # Save to file
        with open("mintos_companies_js.json", "w", encoding="utf-8") as f:
            json.dump(companies, f, indent=2)
            
        logger.info(f"Found {len(companies)} companies")
        
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
                
        # Close the session
        session.close()
        
        return companies
        
    except Exception as e:
        logger.error(f"Error fetching or parsing the page: {e}")
        return {}
        
if __name__ == "__main__":
    extract_companies_with_js_rendering()