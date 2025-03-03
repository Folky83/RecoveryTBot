import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import hashlib
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('direct_document_test')

def test_direct_document_extraction():
    """Test direct document extraction from known Mintos URLs"""
    logger.info("Starting direct document extraction test")
    
    # Session for making requests
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # List of test URLs to try
    test_urls = [
        # Test different possible URL patterns for companies
        "https://www.mintos.com/en/loan-originators/iuvo-group/",
        "https://www.mintos.com/en/loan-originators/iuvo-group/documents/",
        "https://www.mintos.com/en/loan-originators/wowwo/",
        "https://www.mintos.com/en/loan-originators/wowwo/documents/",
        "https://www.mintos.com/en/lending-companies/iuvo/",
        # Test current companies page
        "https://www.mintos.com/en/investing/current-loan-originators/",
        # Test suspended companies page
        "https://www.mintos.com/en/investing/suspended-loan-originators/",
    ]
    
    for url in test_urls:
        logger.info(f"Testing URL: {url}")
        try:
            response = session.get(url, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✅ Successfully accessed: {url}")
                
                # Parse HTML to look for PDF links
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for document links (PDFs)
                pdf_links = soup.find_all('a', href=lambda href: href and href.lower().endswith('.pdf'))
                
                if pdf_links:
                    logger.info(f"✅ Found {len(pdf_links)} PDF links on {url}")
                    
                    # Show details of first 3 PDFs
                    for i, link in enumerate(pdf_links[:3], 1):
                        pdf_url = link.get('href')
                        if not pdf_url.startswith('http'):
                            if pdf_url.startswith('/'):
                                pdf_url = f"https://www.mintos.com{pdf_url}"
                            else:
                                pdf_url = f"https://www.mintos.com/{pdf_url}"
                                
                        title = link.get_text(strip=True)
                        if not title or len(title) < 2:
                            # If link text is empty, try to use the filename from URL
                            filename = pdf_url.split('/')[-1]
                            title = filename.replace('-', ' ').replace('_', ' ').replace('.pdf', '')
                            
                        logger.info(f"  Document {i}:")
                        logger.info(f"    Title: {title}")
                        logger.info(f"    URL: {pdf_url}")
                else:
                    # Look for sections that might contain documents
                    doc_sections = []
                    potential_doc_sections = soup.find_all(['div', 'section'], class_=lambda c: c and (
                        'document' in str(c).lower() or 
                        'download' in str(c).lower() or
                        'files' in str(c).lower()
                    ))
                    
                    if potential_doc_sections:
                        logger.info(f"Found {len(potential_doc_sections)} potential document sections")
                        for section in potential_doc_sections:
                            section_links = section.find_all('a')
                            pdf_count = sum(1 for link in section_links if link.get('href') and link.get('href').lower().endswith('.pdf'))
                            logger.info(f"  Section contains {pdf_count} PDF links")
                    else:
                        logger.info(f"❌ No document sections or PDF links found on {url}")
            else:
                logger.info(f"❌ Failed to access URL: {url} (Status: {response.status_code})")
                
        except Exception as e:
            logger.error(f"❌ Error testing {url}: {e}")
    
    # Test API endpoints that might provide data
    api_endpoints = [
        "https://www.mintos.com/api/en/loan-originators/",
        "https://www.mintos.com/api/en/lending-companies/",
    ]
    
    for endpoint in api_endpoints:
        logger.info(f"Testing API endpoint: {endpoint}")
        try:
            response = session.get(endpoint, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✅ Successfully accessed API: {endpoint}")
                
                try:
                    # Try to parse as JSON
                    data = response.json()
                    logger.info(f"API returned valid JSON data: {type(data)}")
                    
                    # Check data structure
                    if isinstance(data, list):
                        logger.info(f"JSON contains a list with {len(data)} items")
                        if data and isinstance(data[0], dict):
                            logger.info(f"First item keys: {list(data[0].keys())}")
                    elif isinstance(data, dict):
                        logger.info(f"JSON is an object with keys: {list(data.keys())}")
                except ValueError:
                    logger.info("API response is not valid JSON")
                    logger.info(f"First 200 characters: {response.text[:200]}")
            else:
                logger.info(f"❌ Failed to access API: {endpoint} (Status: {response.status_code})")
                
        except Exception as e:
            logger.error(f"❌ Error testing API {endpoint}: {e}")
                
    logger.info("Direct document extraction test completed")

if __name__ == "__main__":
    test_direct_document_extraction()