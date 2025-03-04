"""
Test the document_scraper's built-in URL detection functionality
"""
from bot.document_scraper import DocumentScraper

def test_url_detection():
    """
    Test the document_scraper's ability to extract company URLs
    """
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Use the test_url_extraction method
    print("Testing URL extraction...")
    company_urls = scraper.test_url_extraction()
    
    print(f"\nExtracted {len(company_urls)} company URLs")
    
    # Look for our problematic companies
    target_companies = [
        "iuvo", "iuvo group", "eleving", "eleving group", 
        "mogo", "delfin", "delfin group", "novaloans", "sun finance"
    ]
    
    print("\nResults for target companies:")
    for target in target_companies:
        found = False
        for company_id, info in company_urls.items():
            name = info.get("name", "")
            url = info.get("url", "")
            
            if target.lower() in company_id.lower() or target.lower() in name.lower():
                print(f"- {target.title()}: Found as '{name}' (ID: {company_id})")
                print(f"  URL: {url}")
                found = True
                
        if not found:
            print(f"- {target.title()}: Not found")
    
    return company_urls

if __name__ == "__main__":
    test_url_detection()