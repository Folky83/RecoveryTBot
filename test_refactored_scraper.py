"""
Test Script for Refactored Document Scraper

This script tests the refactored document scraper implementation to ensure it
still works correctly with the new modular approach.
"""
import logging
import sys
import os
import json
from typing import Dict, Any

from bot.document_scraper import DocumentScraper
from bot.url_fetcher import URLFetcher
from bot.document_parser import DocumentParser
from bot.logger import setup_logger

# Configure logger
logger = setup_logger('test_refactored_scraper')

def test_url_fetcher():
    """Test the URL fetcher component"""
    logger.info("Testing URL fetcher...")
    
    # Initialize URL fetcher
    url_fetcher = URLFetcher()
    
    # Test fetching company URLs
    company_urls = url_fetcher.fetch_company_urls()
    
    if company_urls:
        logger.info(f"✅ URL fetcher successfully found {len(company_urls)} companies")
        
        # Show a few example companies
        for i, (company_id, company_info) in enumerate(list(company_urls.items())[:3]):
            logger.info(f"  Company {i+1}: {company_info['name']} (ID: {company_id})")
            logger.info(f"  URL: {company_info['url']}")
    else:
        logger.error("❌ URL fetcher failed to find any companies")
    
    # Test URL variation generation
    sample_company_id = "wowwo"
    sample_company_name = "Wowwo"
    
    url_variations = url_fetcher.generate_url_variations(sample_company_id, sample_company_name)
    
    if url_variations:
        logger.info(f"✅ Generated {len(url_variations)} URL variations for {sample_company_name}")
        for i, url in enumerate(url_variations):
            logger.info(f"  Variation {i+1}: {url}")
    else:
        logger.error(f"❌ Failed to generate URL variations for {sample_company_name}")
    
    # Test making a request
    if url_variations:
        # Try the first URL variation
        html_content = url_fetcher.make_request(url_variations[0])
        
        if html_content:
            logger.info(f"✅ Successfully fetched content from {url_variations[0]}")
        else:
            logger.warning(f"⚠️ Failed to fetch content from {url_variations[0]}")
    
    return company_urls

def test_document_parser(html_content=None, company_name="Test Company"):
    """Test the document parser component"""
    logger.info("Testing document parser...")
    
    # Initialize document parser
    document_parser = DocumentParser()
    
    # If no HTML content provided, use a sample
    if not html_content:
        logger.info("No HTML content provided, using sample HTML")
        
        # Create sample HTML with document links
        sample_html = """
        <html>
        <body>
            <h1>Documents for Test Company</h1>
            <div class="documents">
                <a href="sample.pdf">Sample Document (PDF)</a> - January 15, 2023
                <a href="financial.xlsx">Financial Report Q1 2023</a> - March 31, 2023
            </div>
            <h2>Country Specific Documents</h2>
            <h3>Estonia</h3>
            <ul>
                <li><a href="estonia_report.pdf">Estonia Annual Report</a> - December 20, 2022</li>
            </ul>
            <table>
                <tr>
                    <th>Document Title</th>
                    <th>Date</th>
                </tr>
                <tr>
                    <td><a href="presentation.pptx">Company Presentation</a></td>
                    <td>February 10, 2023</td>
                </tr>
            </table>
        </body>
        </html>
        """
        html_content = sample_html
    
    # Parse documents
    documents = document_parser.parse_documents(html_content, company_name)
    
    if documents:
        logger.info(f"✅ Document parser successfully found {len(documents)} documents")
        
        # Show document details
        for i, doc in enumerate(documents):
            logger.info(f"  Document {i+1}:")
            logger.info(f"    Title: {doc.get('title', 'No title')}")
            logger.info(f"    URL: {doc.get('url', 'No URL')}")
            logger.info(f"    Date: {doc.get('date', 'No date')}")
            logger.info(f"    Type: {doc.get('document_type', 'Unknown type')}")
            
            # Show country info if available
            if 'country_info' in doc and doc['country_info']:
                logger.info(f"    Country: {doc['country_info'].get('country', 'Unknown')}")
    else:
        logger.warning("⚠️ Document parser found no documents in the HTML content")
    
    return documents

def test_document_scraper(company_urls=None):
    """Test the main document scraper"""
    logger.info("Testing document scraper...")
    
    # Initialize document scraper
    scraper = DocumentScraper()
    
    # If no company URLs provided, fetch them
    if not company_urls:
        logger.info("No company URLs provided, fetching from scraper")
        company_urls = scraper.fetch_company_urls()
    
    if not company_urls:
        logger.error("❌ Failed to get company URLs")
        return False
    
    # Test document scraping for a single company
    sample_company_id = list(company_urls.keys())[0]
    sample_company_info = company_urls[sample_company_id]
    sample_company_name = sample_company_info['name']
    sample_company_url = sample_company_info['url']
    
    logger.info(f"Testing document scraping for {sample_company_name} (ID: {sample_company_id})")
    documents = scraper.get_company_documents(sample_company_id, sample_company_name, sample_company_url)
    
    if documents:
        logger.info(f"✅ Successfully found {len(documents)} documents for {sample_company_name}")
        
        # Show document details for the first few documents
        for i, doc in enumerate(documents[:3]):
            logger.info(f"  Document {i+1}:")
            logger.info(f"    Title: {doc.get('title', 'No title')}")
            logger.info(f"    URL: {doc.get('url', 'No URL')}")
            logger.info(f"    Date: {doc.get('date', 'No date')}")
            logger.info(f"    Type: {doc.get('document_type', 'Unknown type')}")
    else:
        logger.warning(f"⚠️ No documents found for {sample_company_name}")
    
    return True

def test_company_mapping():
    """Test loading the company mapping"""
    logger.info("Testing company mapping...")
    
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Try to load company mapping
    mapping_file = 'data/company_mapping.json'
    
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, 'r') as f:
                company_mapping = json.load(f)
                
            logger.info(f"✅ Successfully loaded company mapping with {len(company_mapping)} companies")
            return company_mapping
        except Exception as e:
            logger.error(f"❌ Error loading company mapping: {e}")
    else:
        logger.warning(f"⚠️ Company mapping file not found: {mapping_file}")
        
        # Create a simple mapping for testing
        logger.info("Creating simple company mapping for testing")
        test_mapping = {
            "wowwo": "Wowwo",
            "sun-finance": "Sun Finance",
            "creditstar": "Creditstar"
        }
        
        # Save mapping
        try:
            with open(mapping_file, 'w') as f:
                json.dump(test_mapping, f, indent=2)
                
            logger.info(f"✅ Created test company mapping with {len(test_mapping)} companies")
            return test_mapping
        except Exception as e:
            logger.error(f"❌ Error creating test company mapping: {e}")
    
    return {}

def main():
    """Main test function"""
    logger.info("Starting test of refactored document scraper")
    
    # Test URL fetcher
    company_urls = test_url_fetcher()
    
    # Test document parser
    test_document_parser()
    
    # Test document scraper
    test_document_scraper(company_urls)
    
    # Test company mapping
    company_mapping = test_company_mapping()
    
    # If we have a company mapping, test the check_all_companies method
    if company_mapping:
        logger.info("Testing check_all_companies method")
        
        # Initialize document scraper
        scraper = DocumentScraper()
        
        # Limit to 2 companies for faster testing
        test_mapping = dict(list(company_mapping.items())[:2])
        
        # Check all companies
        new_documents = scraper.check_all_companies(test_mapping)
        
        if new_documents is not None:
            logger.info(f"✅ check_all_companies completed with {len(new_documents)} new documents")
        else:
            logger.error("❌ check_all_companies failed")
    
    logger.info("Test of refactored document scraper completed")

if __name__ == "__main__":
    main()