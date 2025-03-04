"""
Test script for document extraction from Wowwo
This tests the improved document scraper with a specific company.
"""
import json
import logging
from datetime import datetime
from bot.document_scraper import DocumentScraper
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_wowwo_documents")

def test_wowwo_documents():
    """Test fetching documents specifically for Wowwo company"""
    logger.info("Starting document scraping test for Wowwo")
    
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Use a known working URL for testing
    company_id = "wowwo"
    company_name = "Wowwo"
    company_url = "https://www.mintos.com/en/loan-originators/wowwo/"
    
    # Time the document extraction
    start_time = datetime.now()
    logger.info(f"Starting document extraction at {start_time}")
    
    # Try to extract documents
    documents = scraper.get_company_documents(company_id, company_name, company_url)
    
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
    documents = test_wowwo_documents()
    print(f"\nFound {len(documents)} documents for Wowwo")
    print("Sample of the first 5 documents found:")
    
    sample_count = min(5, len(documents))
    
    for i, doc in enumerate(documents[:sample_count]):
        print(f"\nDocument {i+1}:")
        print(f"  - Title: {doc.get('title', 'N/A')}")
        print(f"  - Date: {doc.get('date', 'N/A')}")
        print(f"  - Type: {doc.get('type', 'N/A')}")
        print(f"  - URL: {doc.get('url', 'N/A')}")