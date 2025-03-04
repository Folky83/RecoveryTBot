"""
Simplified function to extract company URLs from Mintos details page
https://www.mintos.com/en/lending-companies/#details
"""
import os
import json
import re
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_company_urls_from_details() -> Dict[str, Dict[str, str]]:
    """Fetch company URLs from the Mintos lending companies details page
    
    Returns:
        Dictionary mapping company IDs to {name, url} dictionaries
    """
    company_urls = {}
    details_url = "https://www.mintos.com/en/lending-companies/#details"
    
    # Set up headers to mimic a browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        # Make direct request to the details page
        logger.info(f"Fetching company URLs from: {details_url}")
        response = requests.get(details_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Method 1: Look for company links in table structure
        # Based on the screenshot structure we saw
        company_links = soup.select('a[href*="/en/lending-companies/"], a[href*="/en/loan-originators/"]')
        
        for link in company_links:
            # Get href value safely
            href = link.get('href', '')
            if not isinstance(href, str):
                continue
            
            # Skip main category pages and links with anchors
            if (href.endswith('/lending-companies/') or 
                href.endswith('/loan-originators/') or 
                '#details' in href):
                continue
                
            # Extract company ID from URL
            path_parts = href.split('/')
            company_id = path_parts[-1] if path_parts else ''
            
            # Skip invalid IDs
            if not company_id or company_id in ['lending-companies', 'loan-originators', 'details']:
                continue
            
            # Get company name
            company_name = ''
            img = link.find('img')
            if img and not isinstance(img, str) and hasattr(img, 'get'):
                company_name = img.get('alt', '')
            
            # If no name from image, get text from link
            if not company_name or len(company_name) < 2:
                company_name = link.get_text().strip()
                
                # If still no valid name, create from ID
                if not company_name or len(company_name) < 2:
                    company_name = company_id.replace('-', ' ').title()
            
            # Make URL absolute
            if not href.startswith('http'):
                href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
            
            # Add to results
            company_urls[company_id] = {
                'name': company_name,
                'url': href
            }
            logger.info(f"Found company: {company_name} ({company_id})")
        
        # Method 2: If no links found, try regex pattern matching
        if not company_links:
            logger.info("No company links found in HTML, trying pattern matching")
            pattern = r'href=[\'"]([^\'"]*(?:/en/lending-companies/|/en/loan-originators/)[^\'"#]*)[\'"]'
            matches = re.findall(pattern, response.text)
            
            for href in matches:
                # Skip main category pages
                if not isinstance(href, str):
                    continue
                    
                if href.endswith('/lending-companies/') or href.endswith('/loan-originators/'):
                    continue
                    
                # Extract company ID
                path_parts = href.split('/')
                company_id = path_parts[-1] if path_parts else ''
                
                if not company_id or company_id in ['lending-companies', 'loan-originators', 'details']:
                    continue
                
                # Create simple name from ID
                company_name = company_id.replace('-', ' ').title()
                
                # Make URL absolute
                if not href.startswith('http'):
                    href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                
                # Add to results
                company_urls[company_id] = {
                    'name': company_name,
                    'url': href
                }
                logger.info(f"Found company from regex: {company_name} ({company_id})")
        
        # Method 3: As a last resort, use predefined fallback mapping
        if not company_urls:
            logger.warning("No companies found, using fallback mapping")
            company_urls = {
                "alexcredit": {
                    "name": "Alexcredit",
                    "url": "https://www.mintos.com/en/lending-companies/Alexcredit"
                },
                "creditstar": {
                    "name": "Creditstar",
                    "url": "https://www.mintos.com/en/lending-companies/Creditstar"
                },
                "eleving-group": {
                    "name": "Eleving Group",
                    "url": "https://www.mintos.com/en/lending-companies/eleving-group"
                },
                "finko": {
                    "name": "FINKO",
                    "url": "https://www.mintos.com/en/lending-companies/finko"
                },
                "iute-group": {
                    "name": "Iute Group",
                    "url": "https://www.mintos.com/en/lending-companies/iute-group"
                },
                "mogo": {
                    "name": "Mogo",
                    "url": "https://www.mintos.com/en/lending-companies/mogo"
                },
                "sun-finance": {
                    "name": "Sun Finance",
                    "url": "https://www.mintos.com/en/lending-companies/sun-finance"
                },
                "wowwo": {
                    "name": "Wowwo",
                    "url": "https://www.mintos.com/en/lending-companies/wowwo"
                }
            }
            logger.info(f"Using fallback mapping with {len(company_urls)} companies")
    
    except Exception as e:
        logger.error(f"Error fetching company URLs: {str(e)}")
    
    # Save results
    cache_dir = "data"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "company_urls_cache.json")
    
    if company_urls:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to {cache_file}")
    else:
        logger.warning("No companies found to save")
    
    return company_urls

if __name__ == "__main__":
    # For testing
    companies = fetch_company_urls_from_details()
    print(f"Found {len(companies)} companies")