import os
import json
import sys
import logging
from bot.document_scraper import DocumentScraper
from bot.data_manager import DataManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('test_scraper')

def test_document_scraper():
    """Test the document scraper with the updated URL pattern"""
    logger.info("Starting document scraper test")
    
    # Initialize document scraper
    scraper = DocumentScraper()
    
    # Make sure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Load company mapping
    try:
        with open('data/company_mapping.json', 'r') as f:
            company_mapping = json.load(f)
    except Exception as e:
        logger.error(f"Error loading company mapping: {e}")
        company_mapping = {}
    
    if not company_mapping:
        logger.error("No company mapping found. Please create data/company_mapping.json first.")
        return
    
    logger.info(f"Loaded {len(company_mapping)} companies from mapping")
    
    # Test URL construction
    for company_id, company_name in company_mapping.items():
        url = f"{scraper.BASE_URL}{company_id}"
        logger.info(f"URL for {company_name}: {url}")
    
    # Test document scraping for a single company
    sample_company_id = list(company_mapping.keys())[0]
    sample_company_name = company_mapping[sample_company_id]
    
    logger.info(f"Testing document scraping for {sample_company_name} (ID: {sample_company_id})")
    documents = scraper.get_company_documents(sample_company_id, sample_company_name)
    
    if documents:
        logger.info(f"Found {len(documents)} documents for {sample_company_name}")
        for i, doc in enumerate(documents, 1):
            logger.info(f"Document {i}:")
            logger.info(f"  Title: {doc.get('title')}")
            logger.info(f"  Date: {doc.get('date')}")
            logger.info(f"  URL: {doc.get('url')}")
    else:
        logger.warning(f"No documents found for {sample_company_name}")
    
    # Test document scraping for all companies
    logger.info("Testing document scraping for all companies")
    all_documents = scraper.check_all_companies(company_mapping)
    
    total_docs = sum(len(docs) for company_id, docs in scraper.documents_data.items())
    logger.info(f"Found a total of {total_docs} documents across {len(scraper.documents_data)} companies")
    logger.info(f"Detected {len(all_documents)} new documents")
    
    # Test document storage and retrieval
    try:
        logger.info(f"Documents cache stored at: {scraper.DOCUMENTS_CACHE_FILE}")
        if os.path.exists(scraper.DOCUMENTS_CACHE_FILE):
            with open(scraper.DOCUMENTS_CACHE_FILE, 'r') as f:
                stored_data = json.load(f)
            logger.info(f"Stored data contains {len(stored_data)} companies")
    except Exception as e:
        logger.error(f"Error checking stored documents: {e}")
    
    logger.info("Document scraper test completed")

if __name__ == "__main__":
    test_document_scraper()