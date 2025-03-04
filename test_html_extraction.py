"""
Simplified HTML extraction for finding company URLs on Mintos
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

def extract_company_urls():
    """Extract company URLs from Mintos lending companies page"""
    company_urls = {}
    
    # Create session with browser-like headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # URLs to try
    urls_to_try = [
        "https://www.mintos.com/en/lending-companies/#details",
        "https://www.mintos.com/en/loan-originators/#details",
        "https://www.mintos.com/en/investing/",
        "https://www.mintos.com/en/investing-in-loans/"
    ]
    
    # Try each URL
    for url in urls_to_try:
        try:
            logger.info(f"Fetching page: {url}")
            response = session.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {url}: {response.status_code}")
                continue
                
            # Save HTML content
            file_name = url.split('/')[-1].strip('#') or 'index'
            with open(f"{file_name}.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"Saved HTML to {file_name}.html")
            
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for table structure based on the screenshot
            tables = soup.find_all('table')
            logger.info(f"Found {len(tables)} tables on the page")
            
            # Process each table
            for table in tables:
                # Check if it has the right class or attributes
                table_class = table.get('class', [])
                table_attrs = str(table.attrs)
                
                if ('loan-table' in table_class or 
                    'loan-originator-details-table' in table_attrs or
                    'lender-table' in table_attrs):
                    
                    logger.info(f"Found potential company table: {table_class}")
                    
                    # Check for rows
                    rows = table.find_all('tr')
                    logger.info(f"Found {len(rows)} rows in the table")
                    
                    for row in rows:
                        # Look for logo cells or cells with links
                        logo_cells = row.find_all('td', class_=lambda c: c and ('logo' in c.lower() if c else False))
                        
                        if not logo_cells:
                            # Try to find any cell with a link
                            all_cells = row.find_all('td')
                            for cell in all_cells:
                                links = cell.find_all('a', href=True)
                                if links:
                                    logo_cells = [cell]
                                    break
                        
                        for cell in logo_cells:
                            links = cell.find_all('a', href=True)
                            
                            for link in links:
                                href = link.get('href')
                                
                                # Skip empty links or non-company links
                                if (not href or 
                                    not ('/lending-companies/' in href or '/loan-originators/' in href) or
                                    href.endswith('/lending-companies/') or 
                                    href.endswith('/loan-originators/')):
                                    continue
                                
                                # Extract company ID from URL
                                parts = href.split('/')
                                company_id = parts[-1] if parts else ''
                                
                                if not company_id or company_id in ['#details', 'details']:
                                    continue
                                
                                # Get company name
                                company_name = link.get_text().strip()
                                
                                # If company name is empty, try to find an image alt text
                                if not company_name or len(company_name) < 2:
                                    img = link.find('img')
                                    if img and 'alt' in img.attrs:
                                        company_name = img['alt']
                                
                                # If still no name, use the ID
                                if not company_name or len(company_name) < 2:
                                    company_name = company_id.replace('-', ' ').title()
                                
                                # Ensure URL is absolute
                                if not href.startswith('http'):
                                    href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                                
                                # Add to our results
                                if company_id not in company_urls:
                                    company_urls[company_id] = {
                                        'name': company_name,
                                        'url': href
                                    }
                                    logger.info(f"Found company: {company_name} ({company_id})")
            
            # If we already found companies, no need to check other URLs
            if company_urls:
                logger.info(f"Found {len(company_urls)} companies from {url}")
                break
                
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
    
    # If we still haven't found any companies, look for links that look like company links
    if not company_urls:
        logger.info("No companies found in tables, trying to find direct links")
        
        for url in urls_to_try:
            try:
                logger.info(f"Searching for company links in: {url}")
                
                response = session.get(url, timeout=15)
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for links that match company URL patterns
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    # Check if link looks like a company URL
                    if (('/lending-companies/' in href or '/loan-originators/' in href) and
                        not href.endswith('/lending-companies/') and 
                        not href.endswith('/loan-originators/')):
                        
                        # Extract company ID
                        parts = href.split('/')
                        company_id = parts[-1] if parts else ''
                        
                        if not company_id or company_id in ['#details', 'details']:
                            continue
                            
                        # Get company name
                        company_name = link.get_text().strip()
                        
                        # If company name is empty, try to find an image alt text
                        if not company_name or len(company_name) < 2:
                            img = link.find('img')
                            if img and 'alt' in img.attrs:
                                company_name = img['alt']
                        
                        # If still no name, use the ID
                        if not company_name or len(company_name) < 2:
                            company_name = company_id.replace('-', ' ').title()
                        
                        # Ensure URL is absolute
                        if not href.startswith('http'):
                            href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                        
                        # Add to our results
                        if company_id not in company_urls:
                            company_urls[company_id] = {
                                'name': company_name,
                                'url': href
                            }
                            logger.info(f"Found company from direct link: {company_name} ({company_id})")
                
                # If we found companies, break
                if company_urls:
                    logger.info(f"Found {len(company_urls)} companies from direct links")
                    break
                    
            except Exception as e:
                logger.error(f"Error searching for direct links in {url}: {e}")
    
    # Save results to a file
    if company_urls:
        with open("company_urls.json", "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to company_urls.json")
    else:
        logger.warning("No company URLs found")
    
    return company_urls

if __name__ == "__main__":
    extract_company_urls()