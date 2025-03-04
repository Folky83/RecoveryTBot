"""
Test a simpler approach to extract company URLs from the HTML source code
"""
import os
import json
import logging
import re
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_company_urls_from_html():
    """Extract company URLs directly from HTML source code without JavaScript rendering"""
    logger.info("Extracting company URLs from HTML source code")
    company_urls = {}
    
    # Set up session with appropriate headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # Try different URLs to find the one with company listings
    urls_to_try = [
        "https://www.mintos.com/en/lending-companies",
        "https://www.mintos.com/en/loan-originators",
        "https://www.mintos.com/en/investing",
        "https://www.mintos.com/en/investing-in-loans",
        "https://www.mintos.com/en/loan-originators/"
    ]
    
    # Try each URL in sequence
    for url_index, url in enumerate(urls_to_try):
        # Skip URLs if we already found companies
        if company_urls:
            logger.info(f"Already found {len(company_urls)} companies, skipping remaining URLs")
            break
            
        try:
            logger.info(f"Fetching page {url_index+1}/{len(urls_to_try)}: {url}")
            response = session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch page: {url} (status: {response.status_code})")
                continue
                
            # Save HTML for inspection (use a unique filename for each URL)
            url_parts = url.split('/')
            filename = f"{url_parts[-1] or 'index'}.html"
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"Saved HTML to {filename}")
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for links that match company URL patterns
            company_link_pattern = re.compile(r'/en/lending-companies/[^/]+|/en/loan-originators/[^/]+')
            
            # Find all links
            links = soup.find_all('a', href=True)
            logger.info(f"Found {len(links)} links in total")
            
            company_count = 0
            
            for link in links:
                href = link['href']
                
                # Check if the link matches our pattern
                if company_link_pattern.match(href):
                    # Skip links to the main lending companies pages
                    if href in ['/en/lending-companies/', '/en/loan-originators/']:
                        continue
                        
                    # Extract company ID from the URL
                    url_parts = href.split('/')
                    company_id = url_parts[-1]
                    
                    # Skip the main page or anchor links
                    if not company_id or company_id in ['#details', 'details']:
                        continue
                    
                    # Get company name from the link text or from image alt
                    company_name = link.get_text().strip()
                    
                    # If link text is empty, try to find an image and get its alt text
                    if not company_name or len(company_name) < 2:
                        img = link.find('img')
                        if img and img.has_attr('alt'):
                            company_name = img['alt']
                    
                    # If still no name, use the ID
                    if not company_name or len(company_name) < 2:
                        company_name = company_id.replace('-', ' ').title()
                    
                    # Ensure URL is absolute
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = f"https://www.mintos.com{href}"
                        else:
                            href = f"https://www.mintos.com/{href}"
                    
                    # Add to our results
                    if company_id not in company_urls:
                        company_urls[company_id] = {
                            'name': company_name,
                            'url': href
                        }
                        company_count += 1
                        logger.info(f"Found company: {company_name} ({company_id}) - {href}")
            
            logger.info(f"Found {company_count} company links in total")
            
            # If no companies found in links, look for the table structure shown in the screenshot
            if company_count == 0:
                logger.info("Looking for companies in loan-originator-details-table")
                tables = soup.find_all('table', class_=lambda c: c and 'loan-originator-details-table' in c)
                
                if tables:
                    logger.info(f"Found {len(tables)} loan originator details tables")
                    
                    for table in tables:
                        # Find all rows in the table
                        rows = table.find_all('tr')
                        logger.info(f"Found {len(rows)} rows in the table")
                        
                        for row in rows:
                            # Find the logo column which should contain company link
                            logo_cell = row.find('td', class_=lambda c: c and 'logo' in c)
                            
                            if logo_cell:
                                # Find the link in the logo cell
                                link = logo_cell.find('a', href=True)
                                
                                if link:
                                    href = link['href']
                                    
                                    # Extract company ID from the URL
                                    url_parts = href.split('/')
                                    company_id = url_parts[-1] if url_parts else None
                                    
                                    if not company_id or company_id in ['lending-companies', 'loan-originators', '#details', 'details']:
                                        continue
                                    
                                    # Get company name from image alt text
                                    img = link.find('img')
                                    company_name = None
                                    
                                    if img and img.has_attr('alt'):
                                        company_name = img['alt']
                                    
                                    # If no name found, use link text or ID
                                    if not company_name:
                                        company_name = link.get_text().strip()
                                        
                                        if not company_name or len(company_name) < 2:
                                            company_name = company_id.replace('-', ' ').title()
                                    
                                    # Ensure URL is absolute
                                    if not href.startswith('http'):
                                        if href.startswith('/'):
                                            href = f"https://www.mintos.com{href}"
                                        else:
                                            href = f"https://www.mintos.com/{href}"
                                    
                                    # Add to our results
                                    if company_id not in company_urls:
                                        company_urls[company_id] = {
                                            'name': company_name,
                                            'url': href
                                        }
                                        company_count += 1
                                        logger.info(f"Found company in table: {company_name} ({company_id}) - {href}")
                    
                    logger.info(f"Found {company_count} company links in total after searching tables")
        
    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
    
    # Save results to a file
    if company_urls:
        with open("simple_html_results.json", "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to simple_html_results.json")
    else:
        logger.warning("No companies found in HTML")
    
    return company_urls

if __name__ == "__main__":
    extract_company_urls_from_html()