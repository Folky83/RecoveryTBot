#!/usr/bin/env python3
"""
Test script to simulate document refresh functionality
"""
import asyncio
import logging
import sys
import os

# Add parent directory to path to find bot modules
sys.path.append('.')

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('document_refresh_test')

async def test_document_refresh():
    """Test document refresh functionality"""
    try:
        # Import here to avoid import errors
        from bot.document_scraper import DocumentScraper
        
        logger.info("Initializing document scraper")
        scraper = DocumentScraper()
        
        # Ensure data directory exists
        os.makedirs('data', exist_ok=True)
        
        # Load previous documents
        previous_docs = scraper.load_previous_documents()
        logger.info(f"Loaded {len(previous_docs)} previous documents")
        
        # Check for new documents
        logger.info("Checking for document updates...")
        new_docs = await scraper.check_document_updates()
        
        logger.info(f"Found {len(new_docs)} new/updated documents")
        
        # Print details of new documents
        for i, doc in enumerate(new_docs[:5], 1):  # Show first 5 docs
            doc_date = doc.get('date', 'Unknown date')
            doc_type = doc.get('type', 'Unknown type')
            company = doc.get('company_name', 'Unknown company')
            title = doc.get('title', 'Untitled')
            
            logger.info(f"Document {i}: {company} - {doc_type} - {title} ({doc_date})")
            
        if len(new_docs) > 5:
            logger.info(f"... and {len(new_docs) - 5} more")
            
        logger.info("Document refresh test completed successfully")
        return new_docs
            
    except Exception as e:
        logger.error(f"Error during document refresh test: {e}", exc_info=True)
        return []

if __name__ == "__main__":
    result = asyncio.run(test_document_refresh())
    print(f"\nTotal documents found: {len(result)}")