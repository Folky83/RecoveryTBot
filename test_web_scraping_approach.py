"""
Test the improved web scraping approach for finding company URLs
This script tests the direct web scraping approach without using API calls.
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

def test_web_scraping():
    """Test the web scraping approach for finding company URLs"""
    logger.info("Testing web scraping approach for company URLs")
    company_urls = {}
    
    # Set up session with appropriate headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # Pages to check for company links
    pages_to_check = [
        "https://www.mintos.com/en/loan-originators/",
        "https://www.mintos.com/en/lending-companies/",
        "https://www.mintos.com/en/investing/"
    ]
    
    # Try each page
    for page_url in pages_to_check:
        try:
            logger.info(f"Fetching page: {page_url}")
            response = session.get(page_url, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Save HTML for inspection
                url_parts = page_url.split('/')
                filename = url_parts[-2] if page_url.endswith('/') and url_parts[-1] == '' else url_parts[-1]
                filename = filename if filename else 'home'
                
                with open(f"{filename}_test_page.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"Saved HTML to {filename}_test_page.html")
                
                # Parse HTML with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Look for links that might be company pages
                found_company_links = 0
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if '/loan-originators/' in href or '/lending-companies/' in href:
                        # Extract company ID from URL
                        url_str = href
                        if url_str.endswith('/'):
                            url_str = url_str[:-1]  # Remove trailing slash
                        path_parts = url_str.split('/')
                        company_id = path_parts[-1] if path_parts else None
                        
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
                            found_company_links += 1
                            logger.info(f"Found company: {company_name} ({company_id}) - {href}")
                
                logger.info(f"Found {found_company_links} company links on {page_url}")
                
            else:
                logger.warning(f"Failed to fetch page: {page_url} (status: {response.status_code})")
                
        except Exception as e:
            logger.error(f"Error processing URL {page_url}: {e}")
    
    # Save results to a file
    if company_urls:
        with open("web_scraping_results.json", "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to web_scraping_results.json")
    else:
        logger.warning("No companies found via web scraping")
    
    return company_urls

if __name__ == "__main__":
    test_web_scraping()