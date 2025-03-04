"""
Extract company URLs from raw HTML content
Designed specifically for Mintos lending companies page content
"""
import os
import json
import re
import logging
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_from_html_file(html_file_path):
    """Extract company URLs from a raw HTML file"""
    logger.info(f"Extracting companies from HTML file: {html_file_path}")
    
    if not os.path.exists(html_file_path):
        logger.error(f"File not found: {html_file_path}")
        return {}
    
    # Load HTML content
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    return extract_from_html_content(html_content)

def extract_from_html_content(html_content):
    """Extract company URLs from HTML content string"""
    company_urls = {}
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Method 1: Direct href pattern matching (most reliable based on your screenshot)
    # Look for any link that matches the lending-companies pattern
    company_links = []
    
    # Find all 'a' tags with href containing 'lending-companies/' or 'loan-originators/'
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/lending-companies/' in href or '/loan-originators/' in href:
            # Skip main category pages
            if href.endswith('/lending-companies/') or href.endswith('/loan-originators/'):
                continue
            # Skip links with anchors that aren't actual company pages
            if '#details' in href:
                continue
                
            company_links.append(link)
    
    logger.info(f"Found {len(company_links)} potential company links")
    
    # Process each link to extract company information
    for link in company_links:
        href = link['href']
        
        # Extract company ID from the URL
        path_parts = href.split('/')
        company_id = path_parts[-1] if path_parts else None
        
        # Skip invalid company IDs
        if not company_id or company_id in ['lending-companies', 'loan-originators', 'details']:
            continue
        
        # Get company name from link text or image alt
        company_name = link.get_text().strip()
        
        # If text is empty, check for image with alt text
        if not company_name or len(company_name) < 2:
            img = link.find('img')
            if img and img.has_attr('alt'):
                company_name = img['alt']
        
        # If still no name, use ID
        if not company_name or len(company_name) < 2:
            company_name = company_id.replace('-', ' ').title()
        
        # Make URL absolute
        if not href.startswith('http'):
            href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
        
        # Add to results
        if company_id not in company_urls:
            company_urls[company_id] = {
                'name': company_name,
                'url': href
            }
            logger.info(f"Found company: {company_name} ({company_id})")
    
    # Method 2: Search for table structure based on your screenshot
    if not company_urls:
        logger.info("No companies found in direct links, looking for table structure")
        
        # Look for tables with specific classes
        tables = soup.find_all('table')
        for table in tables:
            table_classes = table.get('class', [])
            if any(cls in str(table_classes) for cls in ['loan-table', 'loan-originator-details-table']):
                logger.info(f"Found potential company table: {table_classes}")
                
                # Look for rows
                for row in table.find_all('tr'):
                    # Look for cells that might contain company links
                    cells = row.find_all('td')
                    for cell in cells:
                        links = cell.find_all('a', href=True)
                        for link in links:
                            href = link['href']
                            
                            # Check if it's a company link
                            if '/lending-companies/' in href or '/loan-originators/' in href:
                                # Skip main category pages
                                if href.endswith('/lending-companies/') or href.endswith('/loan-originators/'):
                                    continue
                                    
                                # Extract company ID
                                path_parts = href.split('/')
                                company_id = path_parts[-1] if path_parts else None
                                
                                if not company_id or company_id in ['lending-companies', 'loan-originators', 'details']:
                                    continue
                                
                                # Get company name
                                company_name = None
                                img = link.find('img')
                                if img and img.has_attr('alt'):
                                    company_name = img['alt']
                                
                                if not company_name:
                                    company_name = link.get_text().strip()
                                    
                                    if not company_name or len(company_name) < 2:
                                        company_name = company_id.replace('-', ' ').title()
                                
                                # Make URL absolute
                                if not href.startswith('http'):
                                    href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                                
                                # Add to results
                                if company_id not in company_urls:
                                    company_urls[company_id] = {
                                        'name': company_name,
                                        'url': href
                                    }
                                    logger.info(f"Found company in table: {company_name} ({company_id})")
    
    # Method 3: Direct pattern matching in HTML content
    if not company_urls:
        logger.info("Trying direct pattern matching in raw HTML")
        
        # Look for href patterns directly
        pattern = r'href="([^"]*(?:/en/lending-companies/|/en/loan-originators/)[^"#]*)"'
        matches = re.findall(pattern, html_content)
        
        for href in matches:
            # Skip main category pages
            if href.endswith('/lending-companies/') or href.endswith('/loan-originators/'):
                continue
                
            # Extract company ID
            path_parts = href.split('/')
            company_id = path_parts[-1] if path_parts else None
            
            if not company_id or company_id in ['lending-companies', 'loan-originators', 'details']:
                continue
            
            # Create simple name from ID
            company_name = company_id.replace('-', ' ').title()
            
            # Make URL absolute
            if not href.startswith('http'):
                href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
            
            # Add to results
            if company_id not in company_urls:
                company_urls[company_id] = {
                    'name': company_name,
                    'url': href
                }
                logger.info(f"Found company from regex: {company_name} ({company_id})")
    
    # Save results
    if company_urls:
        with open("extracted_companies.json", "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to extracted_companies.json")
    else:
        logger.warning("No companies found in HTML")
    
    return company_urls

if __name__ == "__main__":
    # Try to extract from provided files
    file_path = "attached_assets/Lending companies _ Mintos.html"
    extract_from_html_file(file_path)