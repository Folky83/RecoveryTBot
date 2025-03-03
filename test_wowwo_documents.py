import os
import sys
import logging
from bot.document_scraper import DocumentScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('wowwo_test')

def test_wowwo_documents():
    """Test fetching documents specifically for Wowwo company"""
    logger.info("Testing document scraping for Wowwo company")
    
    # Initialize document scraper
    scraper = DocumentScraper()
    
    # Use the specific URL that worked in our tests
    company_id = "wowwo"
    company_name = "Wowwo"
    company_url = "https://www.mintos.com/en/loan-originators/wowwo/"
    
    logger.info(f"Fetching documents for {company_name} using URL: {company_url}")
    documents = scraper.get_company_documents(company_id, company_name, company_url)
    
    if documents:
        logger.info(f"SUCCESS! Found {len(documents)} documents for {company_name}")
        for i, doc in enumerate(documents, 1):
            logger.info(f"Document {i}:")
            logger.info(f"  Title: {doc.get('title')}")
            logger.info(f"  Date: {doc.get('date')}")
            logger.info(f"  URL: {doc.get('url')}")
            logger.info(f"  ID: {doc.get('id')}")
    else:
        logger.error(f"No documents found for {company_name}")
        
    logger.info("Test completed")

if __name__ == "__main__":
    test_wowwo_documents()