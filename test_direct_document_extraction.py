import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
import hashlib
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('direct_extraction_test')

# Test URLs - Based on our findings, Mintos is redirecting from loan-originators to lending-companies
# So we should use the newer pattern directly to avoid unnecessary redirects
TEST_URLS = [
    # Pattern: lending-companies (newer pattern that all URLs redirect to)
    ("Wowwo", "https://www.mintos.com/en/lending-companies/wowwo/"),
    ("Creditstar", "https://www.mintos.com/en/lending-companies/creditstar/"),
    ("Kviku", "https://www.mintos.com/en/lending-companies/kviku/"),
    ("Placet Group", "https://www.mintos.com/en/lending-companies/placet-group/"),
    ("IuvoGroup", "https://www.mintos.com/en/lending-companies/iuvo-group/"),
    ("Delfin Group", "https://www.mintos.com/en/lending-companies/delfin-group/"),
]

def test_direct_document_extraction():
    """Test direct document extraction from known Mintos URLs"""
    logger.info("Testing direct document extraction from known Mintos URLs")
    
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.mintos.com/en/'
    }
    session.headers.update(headers)
    
    all_results = []
    
    for company_name, url in TEST_URLS:
        logger.info(f"Testing document extraction for {company_name} from {url}")
        
        try:
            # Allow redirects to follow from loan-originators to lending-companies
            response = session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            
            # Log any redirects that happened
            if response.history:
                redirect_chain = ' -> '.join([r.url for r in response.history])
                final_url = response.url
                logger.info(f"  Redirected: {redirect_chain} -> {final_url}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Method 1: Look for PDF links directly
            pdf_links = []
            for a_tag in soup.find_all('a', href=lambda href: href and href.lower().endswith('.pdf')):
                pdf_links.append({
                    'url': a_tag['href'],
                    'title': a_tag.text.strip() or "Unnamed Document",
                })
            
            # Method 2: Look for document sections
            document_sections = []
            for section in soup.find_all('div', class_=lambda c: c and 'document' in c.lower()):
                document_sections.append(section)
                
            # Method 3: Look for sections with cards that might contain documents
            card_sections = []
            for section in soup.find_all('div', class_=lambda c: c and ('card' in c.lower() or 'download' in c.lower())):
                card_sections.append(section)
            
            logger.info(f"Results for {company_name}:")
            logger.info(f"  Direct PDF links found: {len(pdf_links)}")
            logger.info(f"  Document sections found: {len(document_sections)}")
            logger.info(f"  Card sections found: {len(card_sections)}")
            
            if pdf_links:
                for i, link in enumerate(pdf_links[:3], 1):  # Show first 3 links
                    logger.info(f"  PDF Link {i}: {link['title']} - {link['url']}")
            
            # Store results
            all_results.append({
                'company': company_name,
                'url': url,
                'pdf_links_count': len(pdf_links),
                'document_sections_count': len(document_sections),
                'card_sections_count': len(card_sections),
                'pdf_links': pdf_links[:5]  # Store first 5 links
            })
            
        except Exception as e:
            logger.error(f"Error processing {company_name}: {str(e)}")
            all_results.append({
                'company': company_name,
                'url': url,
                'error': str(e)
            })
    
    # Summary
    logger.info("\n--- TEST SUMMARY ---")
    for result in all_results:
        if 'error' in result:
            logger.info(f"❌ {result['company']}: Error - {result['error']}")
        elif result['pdf_links_count'] > 0:
            logger.info(f"✅ {result['company']}: Found {result['pdf_links_count']} PDF links")
        else:
            logger.info(f"⚠️ {result['company']}: No PDF links found")
    
    logger.info("\nTest completed")

if __name__ == "__main__":
    test_direct_document_extraction()