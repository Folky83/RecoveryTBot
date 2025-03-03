import os
import sys
import json
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

logger = logging.getLogger('all_companies_test')

def test_all_company_documents():
    """Test document scraping for all companies in our mapping"""
    logger.info("Starting document scraping test for all companies in our mapping")
    
    # Initialize document scraper
    scraper = DocumentScraper()
    
    # Get all company URLs from our implementation
    company_urls = scraper.fetch_company_urls()
    logger.info(f"Found {len(company_urls)} company URLs from our implementation")
    
    # Test each company
    successful_companies = []
    failed_companies = []
    
    # Test only the first 5 companies to save time
    test_companies = list(company_urls.items())[:5]
    
    for company_id, company_info in test_companies:
        company_name = company_info['name']
        company_url = company_info['url']
        
        logger.info(f"Testing document scraping for {company_name} (ID: {company_id})")
        documents = scraper.get_company_documents(company_id, company_name, company_url)
        
        if documents:
            logger.info(f"✅ SUCCESS! Found {len(documents)} documents for {company_name}")
            successful_companies.append({
                'id': company_id,
                'name': company_name,
                'url': company_url,
                'document_count': len(documents)
            })
            
            # Show first document details
            if documents:
                doc = documents[0]
                logger.info(f"  Sample document:")
                logger.info(f"    Title: {doc.get('title')}")
                logger.info(f"    URL: {doc.get('url')}")
        else:
            logger.warning(f"❌ No documents found for {company_name}")
            failed_companies.append({
                'id': company_id,
                'name': company_name,
                'url': company_url
            })
    
    # Summary
    logger.info("\n--- TEST SUMMARY ---")
    logger.info(f"Total companies tested: {len(test_companies)}")
    logger.info(f"Successful companies: {len(successful_companies)}")
    logger.info(f"Failed companies: {len(failed_companies)}")
    
    if successful_companies:
        logger.info("\nSuccessful companies:")
        for company in successful_companies:
            logger.info(f"  ✅ {company['name']}: {company['document_count']} documents")
            
    if failed_companies:
        logger.info("\nFailed companies:")
        for company in failed_companies:
            logger.info(f"  ❌ {company['name']}")
            
    logger.info("\nTest completed")

if __name__ == "__main__":
    test_all_company_documents()