"""
Simplified test for extracting company URLs from the Mintos lending companies details page
This version avoids JavaScript rendering to be faster
"""
import os
import json
import logging
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_company_details_extraction_simple():
    """Test extracting company URLs from the details page without JS rendering"""
    logger.info("Testing extraction from lending companies details page (simple version)")
    details_url = "https://www.mintos.com/en/lending-companies/#details"
    company_urls = {}
    
    # Set up session with appropriate headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    try:
        logger.info(f"Fetching details page: {details_url}")
        response = session.get(details_url, timeout=10)
        
        if response.status_code == 200:
            html_content = response.text
            
            # Save the HTML for inspection
            with open("details_page_simple.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("Saved HTML to details_page_simple.html")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # First look for tables that might contain company information
            tables = soup.select('table')
            if tables:
                logger.info(f"Found {len(tables)} tables on the page")
                
                # Process each table to find company information
                for table_index, table in enumerate(tables):
                    logger.info(f"Processing table {table_index+1}")
                    
                    # Look for table rows with company information
                    rows = table.select('tbody tr')
                    logger.info(f"Table {table_index+1} has {len(rows)} rows")
                    
                    for row_index, row in enumerate(rows):
                        try:
                            # Each row should have cells with company info
                            cells = row.select('td')
                            if len(cells) >= 2:  # Need at least name and possibly a link
                                # First cell usually contains the company name and link
                                name_cell = cells[0]
                                company_link = name_cell.select_one('a')
                                
                                if company_link and company_link.has_attr('href'):
                                    company_url = company_link['href']
                                    company_name = company_link.text.strip()
                                    
                                    # Extract company ID from URL
                                    parts = company_url.split('/')
                                    if parts:
                                        company_id = parts[-1].rstrip('/') if parts[-1] else parts[-2].rstrip('/') if len(parts) > 1 else None
                                    else:
                                        company_id = None
                                    
                                    # Skip if not a valid company page
                                    if (not company_id or
                                        company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                                        '?' in company_id or
                                        '#' in company_id or
                                        company_id.isdigit()):
                                        continue
                                    
                                    # Ensure URL is absolute
                                    if not company_url.startswith('http'):
                                        if company_url.startswith('/'):
                                            company_url = f"https://www.mintos.com{company_url}"
                                        else:
                                            company_url = f"https://www.mintos.com/{company_url}"
                                    
                                    # Add to our results if not already present
                                    if company_id not in company_urls:
                                        company_urls[company_id] = {
                                            'name': company_name,
                                            'url': company_url
                                        }
                                        logger.info(f"Found company: {company_name} ({company_id}) - {company_url}")
                        except Exception as e:
                            logger.warning(f"Error processing row {row_index+1} in table {table_index+1}: {e}")
                            continue
            else:
                logger.warning("No tables found on the page")
            
            # Also look for links that might be company pages
            company_link_count = 0
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/loan-originators/' in href or '/lending-companies/' in href:
                    company_link_count += 1
                    
                    # Extract company ID from URL
                    parts = href.split('/')
                    if parts:
                        company_id = parts[-1].rstrip('/') if parts[-1] else parts[-2].rstrip('/') if len(parts) > 1 else None
                    else:
                        company_id = None
                    
                    # Skip main category pages and invalid IDs
                    if (not company_id or
                        company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                        '?' in company_id or
                        '#' in company_id or
                        company_id.isdigit()):
                        continue
                    
                    # Get company name from link text
                    company_name = link.get_text().strip()
                    if not company_name or len(company_name) < 2:
                        company_name = company_id.replace('-', ' ').title()
                    
                    # Ensure URL is absolute
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = f"https://www.mintos.com{href}"
                        else:
                            href = f"https://www.mintos.com/{href}"
                    
                    # Add to our results if not already present
                    if company_id not in company_urls:
                        company_urls[company_id] = {
                            'name': company_name,
                            'url': href
                        }
                        logger.info(f"Found company from link: {company_name} ({company_id}) - {href}")
            
            logger.info(f"Processed {company_link_count} company-related links")
            
            if company_urls:
                logger.info(f"Successfully found {len(company_urls)} companies")
                
                # Save the results to a file
                with open("company_urls_simple.json", "w", encoding="utf-8") as f:
                    json.dump(company_urls, f, indent=2)
                logger.info("Saved company URLs to company_urls_simple.json")
            else:
                logger.warning("No company URLs found")
                
                # Check if we need to look at specific API endpoints instead
                logger.info("Checking if data might be loaded via API")
                
                # Inspect page source for potential API endpoints
                scripts = soup.find_all('script')
                logger.info(f"Found {len(scripts)} script tags on page")
                
                api_endpoints = []
                for script in scripts:
                    script_text = script.string
                    if script_text:
                        # Look for possible API endpoints
                        if 'api' in script_text.lower() and ('lend' in script_text.lower() or 'loan' in script_text.lower()):
                            lines = script_text.split('\n')
                            for line in lines:
                                if 'api' in line.lower() and ('lend' in line.lower() or 'loan' in line.lower()):
                                    logger.info(f"Potential API reference: {line.strip()}")
                                    
                                    # Try to extract URL
                                    if 'http' in line:
                                        start = line.find('http')
                                        end = line.find('"', start) if '"' in line[start:] else line.find("'", start) if "'" in line[start:] else len(line)
                                        if start >= 0 and end > start:
                                            api_url = line[start:end]
                                            api_endpoints.append(api_url)
                                            logger.info(f"Extracted API URL: {api_url}")
                
                if api_endpoints:
                    logger.info(f"Found {len(api_endpoints)} potential API endpoints to try")
                    
                    for api_url in api_endpoints:
                        try:
                            logger.info(f"Trying API endpoint: {api_url}")
                            api_response = session.get(api_url, timeout=10)
                            
                            if api_response.status_code == 200:
                                try:
                                    data = api_response.json()
                                    logger.info(f"Successfully got JSON response from {api_url}")
                                    
                                    # Save API response for inspection
                                    with open(f"api_response_{api_endpoints.index(api_url)}.json", "w", encoding="utf-8") as f:
                                        json.dump(data, f, indent=2)
                                    logger.info(f"Saved API response to api_response_{api_endpoints.index(api_url)}.json")
                                    
                                except Exception as e:
                                    logger.warning(f"Error parsing JSON from API: {e}")
                            else:
                                logger.warning(f"API request failed with status code {api_response.status_code}")
                                
                        except Exception as e:
                            logger.error(f"Error accessing API endpoint {api_url}: {e}")
                
        else:
            logger.error(f"Failed to fetch details page: {response.status_code}")
            return None
        
    except Exception as e:
        logger.error(f"Error in extraction process: {e}")
        return None
    
    return company_urls

if __name__ == "__main__":
    test_company_details_extraction_simple()