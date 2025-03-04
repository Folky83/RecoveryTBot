"""
Test script to simulate document refresh functionality and verify the company_page_url field
"""
import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent directory to path to import bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the DocumentScraper class
from bot.document_scraper import DocumentScraper

async def test_document_refresh():
    """Test document refresh functionality and verify the company_page_url field"""
    print(f"Starting document scrape test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create document scraper
    scraper = DocumentScraper()
    
    # Print previous document count
    previous_docs = scraper.load_previous_documents()
    print(f"Previous document count: {len(previous_docs)}")
    
    # Count documents with company_page_url
    docs_with_url = sum(1 for doc in previous_docs if 'company_page_url' in doc)
    print(f"Documents with company_page_url field: {docs_with_url} / {len(previous_docs)}")
    
    # Perform document check with just 3 companies to save time
    # Load company pages
    company_pages = []
    try:
        import pandas as pd
        company_csv = os.path.join('attached_assets', 'company_pages.csv')
        if os.path.exists(company_csv):
            df = pd.read_csv(company_csv)
            for _, row in df.iterrows():
                company_pages.append((row['company_name'], row['url']))
    except Exception as e:
        print(f"Error loading company pages: {e}")
        company_pages = [
            ('Capitalia', 'https://www.mintos.com/en/lending-companies/Capitalia'),
            ('DelfinGroup', 'https://www.mintos.com/en/lending-companies/DelfinGroup'),
            ('Everest Finanse', 'https://www.mintos.com/en/lending-companies/EverestFinanse')
        ]
    
    # Limit to 3 companies for testing
    test_companies = company_pages[:3]
    print(f"Testing with {len(test_companies)} companies:")
    for company_name, url in test_companies:
        print(f"  - {company_name}: {url}")
    
    # Process companies directly
    all_docs = []
    for company_name, url in test_companies:
        print(f"Processing company: {company_name}")
        docs = await scraper._process_company(company_name, url)
        all_docs.extend(docs)
        print(f"  Found {len(docs)} documents")
    
    # Check if documents have company_page_url field
    docs_with_url = sum(1 for doc in all_docs if 'company_page_url' in doc)
    print(f"New documents with company_page_url field: {docs_with_url} / {len(all_docs)}")
    
    # Print sample document
    if all_docs:
        print("\nSample document fields:")
        for key, value in all_docs[0].items():
            print(f"  {key}: {value}")
    
    print(f"Document scrape test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

async def main():
    """Test function for document refresh"""
    await test_document_refresh()

if __name__ == "__main__":
    asyncio.run(main())