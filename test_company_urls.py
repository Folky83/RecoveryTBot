"""
Test script for the improved company URL extraction
This script tests the new document_scraper implementation with requests-html
to efficiently find company pages on the Mintos website.
"""
import os
import sys
import json
import logging
from datetime import datetime

# Ensure parent directory is in path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the document scraper
from bot.document_scraper import DocumentScraper
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_company_urls")

def test_company_url_extraction():
    """Test the improved company URL extraction"""
    logger.info("Starting company URL extraction test")
    
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Use the test method to extract company URLs
    start_time = datetime.now()
    logger.info(f"Starting URL extraction at {start_time}")
    
    company_urls = scraper.test_url_extraction()
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"URL extraction completed in {duration:.2f} seconds")
    logger.info(f"Found {len(company_urls)} company URLs")
    
    # Save results to a file for inspection
    output_file = "company_urls_test_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Results saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving results: {e}")
    
    # Print a sample of the results
    logger.info("Sample of extracted company URLs:")
    sample_count = min(5, len(company_urls))
    sample_keys = list(company_urls.keys())[:sample_count]
    
    for key in sample_keys:
        company = company_urls[key]
        logger.info(f"- {company['name']} (ID: {key}): {company['url']}")
    
    return company_urls

if __name__ == "__main__":
    company_urls = test_company_url_extraction()
    print(f"\nFound {len(company_urls)} companies")
    print("Sample of the first 5 companies found:")
    
    sample_count = min(5, len(company_urls))
    sample_keys = list(company_urls.keys())[:sample_count]
    
    for key in sample_keys:
        company = company_urls[key]
        print(f"- {company['name']} (ID: {key}): {company['url']}")