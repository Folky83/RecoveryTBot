"""
Script to test the company_page_url field in document objects
"""
import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent directory to path to import bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.document_scraper import DocumentScraper

async def test_company_page_url():
    """Test company_page_url field in document objects"""
    print(f"Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create document scraper
    scraper = DocumentScraper()
    
    # Test with a single company
    company_name = "Capitalia"
    company_url = "https://www.mintos.com/en/lending-companies/Capitalia"
    
    print(f"Processing company: {company_name}")
    docs = await scraper._process_company(company_name, company_url)
    
    # Print document details
    print(f"Found {len(docs)} documents:")
    for i, doc in enumerate(docs):
        print(f"\nDocument {i+1}:")
        for key, value in doc.items():
            print(f"  {key}: {value}")
    
    print(f"\nTest completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

async def main():
    await test_company_page_url()

if __name__ == "__main__":
    asyncio.run(main())