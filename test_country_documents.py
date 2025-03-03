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
logger = logging.getLogger('country_documents_test')

def test_country_documents():
    """Test finding documents in country-specific sections"""
    logger.info("Testing country-specific document extraction")
    
    # Mintos URLs with known country sections
    test_urls = [
        {
            "company": "Wowwo",
            "url": "https://www.mintos.com/en/lending-companies/wowwo/"
        },
        {
            "company": "Creditstar",
            "url": "https://www.mintos.com/en/lending-companies/creditstar/"
        },
        {
            "company": "Kviku",
            "url": "https://www.mintos.com/en/lending-companies/kviku/"
        }
    ]
    
    supported_extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar']
    
    # Process each URL
    for test_item in test_urls:
        company = test_item["company"]
        url = test_item["url"]
        
        logger.info(f"Testing country document extraction for {company} from {url}")
        
        try:
            # Fetch the company page
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            html_content = response.text
            
            # Parse HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Data structures to store extracted information
            country_sections = []
            country_documents = []
            
            # Find country-specific sections
            # Look for headings with country terms
            country_terms = [
                'country', 'countries', 'region', 'regions', 'location', 'operations',
                'europe', 'asia', 'africa', 'america', 'australia', 'oceania',
                'baltic', 'northern europe', 'eastern europe', 'western europe', 'central europe',
                'southeast asia', 'latin america', 'north america', 'central america',
                'portugal', 'spain', 'france', 'italy', 'germany', 'uk', 'united kingdom',
                'norway', 'sweden', 'finland', 'denmark', 'estonia', 'latvia', 'lithuania',
                'poland', 'czech', 'slovakia', 'hungary', 'romania', 'bulgaria', 'greece',
                'russia', 'ukraine', 'belarus', 'kazakhstan', 'georgia', 'azerbaijan',
                'turkey', 'morocco', 'algeria', 'tunisia', 'egypt', 'kenya', 'south africa',
                'mexico', 'brazil', 'argentina', 'chile', 'peru', 'colombia', 'venezuela',
                'usa', 'united states', 'canada', 'china', 'japan', 'korea', 'singapore',
                'vietnam', 'thailand', 'malaysia', 'indonesia', 'philippines', 'india',
                'pakistan', 'bangladesh', 'australia', 'new zealand'
            ]
            
            # Find country section headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                heading_text = heading.get_text(strip=True).lower()
                if any(term in heading_text for term in country_terms):
                    logger.info(f"  Found country section: '{heading.get_text(strip=True)}'")
                    country_sections.append({
                        "heading": heading.get_text(strip=True),
                        "element": heading
                    })
                    
                    # Find document links in and after this heading
                    section = heading.parent
                    if section:
                        # Look for document links in the section
                        for link in section.find_all('a'):
                            href = link.get('href', '')
                            if href and any(href.lower().endswith(ext) for ext in supported_extensions):
                                title = link.get_text(strip=True)
                                if not title:
                                    # Extract from filename if no text
                                    filename = href.split('/')[-1]
                                    title = filename
                                    
                                # Format URL if needed
                                url = href
                                if not url.startswith('http'):
                                    if url.startswith('/'):
                                        url = f"https://www.mintos.com{url}"
                                    else:
                                        url = f"https://www.mintos.com/{url}"
                                        
                                country_documents.append({
                                    "section": heading.get_text(strip=True),
                                    "title": title,
                                    "url": url,
                                })
                                
                        # Also check siblings after the heading
                        next_elem = heading.find_next_sibling()
                        while next_elem and next_elem.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            for link in next_elem.find_all('a'):
                                href = link.get('href', '')
                                if href and any(href.lower().endswith(ext) for ext in supported_extensions):
                                    title = link.get_text(strip=True)
                                    if not title:
                                        # Extract from filename if no text
                                        filename = href.split('/')[-1]
                                        title = filename
                                        
                                    # Format URL if needed
                                    url = href
                                    if not url.startswith('http'):
                                        if url.startswith('/'):
                                            url = f"https://www.mintos.com{url}"
                                        else:
                                            url = f"https://www.mintos.com/{url}"
                                            
                                    country_documents.append({
                                        "section": heading.get_text(strip=True),
                                        "title": title,
                                        "url": url,
                                    })
                            
                            next_elem = next_elem.find_next_sibling()
            
            # Summarize results
            logger.info(f"Results for {company}:")
            logger.info(f"  Found {len(country_sections)} country sections")
            logger.info(f"  Found {len(country_documents)} country-specific documents")
            
            # List the documents found
            for i, doc in enumerate(country_documents, 1):
                logger.info(f"  Document {i}: {doc['title']} in '{doc['section']}' - {doc['url']}")
                
            if len(country_documents) == 0:
                logger.warning(f"No country-specific documents found for {company}")
                
        except Exception as e:
            logger.error(f"Error processing {company}: {e}")
    
    logger.info("\nTest completed")

if __name__ == "__main__":
    test_country_documents()