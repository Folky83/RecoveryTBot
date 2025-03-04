"""
Test script for document extraction from Wowwo
This tests the improved document scraper with a specific company.
"""
import json
import logging
import requests
from datetime import datetime
from bot.document_scraper import DocumentScraper
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_wowwo_documents")

def test_wowwo_documents(use_js_rendering=False):
    """
    Test fetching documents specifically for Wowwo company
    
    Args:
        use_js_rendering: Whether to use JavaScript rendering (slow but more complete)
                         If False, uses simpler extraction method
    """
    logger.info(f"Starting document scraping test for Wowwo (JS rendering: {use_js_rendering})")
    
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Use a known working URL for testing
    company_id = "wowwo"
    company_name = "Wowwo"
    company_url = "https://www.mintos.com/en/loan-originators/wowwo/"
    
    # Time the document extraction
    start_time = datetime.now()
    logger.info(f"Starting document extraction at {start_time}")
    
    if use_js_rendering:
        # Full test with JS rendering
        documents = scraper.get_company_documents(company_id, company_name, company_url)
    else:
        # Simplified test with direct request (no JS rendering)
        logger.info("Using simplified extraction method (no JS rendering)")
        try:
            # Make a direct request to the company URL without JS rendering
            response = requests.get(company_url, timeout=10)
            
            if response.status_code == 200:
                # Parse the page content
                html_content = response.text
                documents = scraper._parse_documents(html_content, company_name)
                logger.info(f"Successfully extracted {len(documents)} documents using simplified method")
            else:
                logger.error(f"Failed to fetch company page: {response.status_code}")
                documents = []
        except Exception as e:
            logger.error(f"Error during document extraction: {e}")
            documents = []
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"Document extraction completed in {duration:.2f} seconds")
    logger.info(f"Found {len(documents)} documents for {company_name}")
    
    # Save results to a file for inspection
    output_file = f"{company_id}_documents_test_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(documents, f, indent=2)
        logger.info(f"Results saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving results: {e}")
    
    # Print a sample of the results
    logger.info("Sample of extracted documents:")
    sample_count = min(5, len(documents))
    
    for i, doc in enumerate(documents[:sample_count]):
        logger.info(f"Document {i+1}:")
        logger.info(f"  - Title: {doc.get('title', 'N/A')}")
        logger.info(f"  - Date: {doc.get('date', 'N/A')}")
        logger.info(f"  - Type: {doc.get('type', 'N/A')}")
        logger.info(f"  - URL: {doc.get('url', 'N/A')}")
    
    return documents

if __name__ == "__main__":
    # Test with simplified extraction (no JS rendering - faster)
    documents = test_wowwo_documents(use_js_rendering=False)
    
    print(f"\nFound {len(documents)} documents for Wowwo")
    print("Sample of the first 5 documents found:")
    
    sample_count = min(5, len(documents))
    
    for i, doc in enumerate(documents[:sample_count]):
        print(f"\nDocument {i+1}:")
        print(f"  - Title: {doc.get('title', 'N/A')}")
        print(f"  - Date: {doc.get('date', 'N/A')}")
        print(f"  - Type: {doc.get('type', 'N/A')}")
        print(f"  - URL: {doc.get('url', 'N/A')}")