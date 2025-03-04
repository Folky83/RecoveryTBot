"""
Test the company fallback mapping functionality
"""
from bot.document_scraper import DocumentScraper
import json
import os

def test_fallback_mapping():
    """Test the company fallback mapping system"""
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Load the fallback mapping
    fallback_mapping = scraper._load_company_fallback_mapping()
    
    print(f"Loaded fallback mapping with {len(fallback_mapping)} companies\n")
    
    for company_id, mapping_info in fallback_mapping.items():
        print(f"Testing fallback for {company_id}:")
        print(f"  - Redirects to: {mapping_info.get('redirect_id')}")
        print(f"  - Redirect name: {mapping_info.get('redirect_name')}")
        print(f"  - Notes: {mapping_info.get('notes')}")
        
        # Generate URL variations using the original company ID
        print("\nURL variations before fallback:")
        original_urls = scraper._generate_url_variations(company_id, company_id)
        for i, url in enumerate(original_urls[:3]):  # Show first 3 for brevity
            print(f"  {i+1}. {url}")
        if len(original_urls) > 3:
            print(f"  ... and {len(original_urls) - 3} more")
            
        # Now test if fallback is applied correctly
        print("\nTesting get_company_documents with fallback:")
        documents = scraper.get_company_documents(company_id, company_id.replace('-', ' ').title())
        
        if documents:
            print(f"SUCCESS: Found {len(documents)} documents using fallback")
            print("Document titles:")
            for doc in documents[:3]:  # Print first 3 docs
                print(f"- {doc.get('title', 'Untitled')} ({doc.get('date', 'No date')})")
        else:
            print("FAILURE: No documents found even with fallback")
        
        print("\n" + "="*50 + "\n")
    
    return fallback_mapping

if __name__ == "__main__":
    test_fallback_mapping()