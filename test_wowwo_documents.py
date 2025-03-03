#!/usr/bin/env python3
import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('wowwo_documents_test')

def test_wowwo_documents():
    """Test fetching documents specifically for Wowwo company"""
    logger.info("Testing Wowwo company document extraction")
    
    # Wowwo URL
    url = "https://www.mintos.com/en/lending-companies/wowwo/"
    
    try:
        # Fetch the company page
        logger.info(f"Fetching Wowwo company page from {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # Parse HTML content
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all PDF links on the page
        pdf_links = []
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if href and href.lower().endswith('.pdf'):
                title = link.get_text(strip=True)
                if not title:
                    # Try to get title from the filename
                    filename = href.split('/')[-1]
                    title = filename.replace('-', ' ').replace('_', ' ').replace('.pdf', '')
                
                pdf_links.append({
                    'title': title,
                    'url': href if href.startswith('http') else f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                })
        
        # Log results
        logger.info(f"Found {len(pdf_links)} PDF links on Wowwo page")
        for i, link in enumerate(pdf_links, 1):
            logger.info(f"  Link {i}: {link['title']} - {link['url']}")
            
        # Analyze document titles for country-specific terms
        country_terms = [
            'turkey', 'turkish', 'europe', 'european', 'asia', 'asian',
            'middle east', 'country', 'region', 'location'
        ]
        
        country_specific_docs = []
        for link in pdf_links:
            title_lower = link['title'].lower()
            if any(term in title_lower for term in country_terms):
                country_specific_docs.append(link)
                
        logger.info(f"Found {len(country_specific_docs)} country-specific documents based on title")
        for i, doc in enumerate(country_specific_docs, 1):
            logger.info(f"  Country Document {i}: {doc['title']} - {doc['url']}")
            
        # Get company metadata
        company_info = {}
        
        # Try to find company description
        description_elem = soup.select_one('.company-description') or soup.select_one('.description')
        if description_elem:
            company_info['description'] = description_elem.get_text(strip=True)
            
        # Try to find company country of operations
        country_elem = None
        for elem in soup.find_all(['p', 'div', 'li']):
            text = elem.get_text(strip=True).lower()
            if 'country' in text or 'countries' in text or 'operations in' in text:
                country_elem = elem
                break
                
        if country_elem:
            company_info['countries'] = country_elem.get_text(strip=True)
            
        logger.info("Company metadata:")
        for key, value in company_info.items():
            logger.info(f"  {key}: {value}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        
    logger.info("Test completed")

if __name__ == "__main__":
    test_wowwo_documents()