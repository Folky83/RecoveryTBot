"""
Test document extraction for specific problematic companies
"""
import json
import requests
import time
from bot.document_scraper import DocumentScraper
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_problematic_companies")

def test_companies():
    """Test document extraction for specific problematic companies"""
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # List of problematic companies to test
    companies = {
        "iuvo": "Iuvo",
        "iuvo-group": "Iuvo Group",
        "akulaku": "Akulaku",
        "sun-finance": "Sun Finance",
        "mogo": "Mogo",
        "placet-group": "Placet Group",
        "delfin-group": "Delfin Group",
        "creditstar": "Creditstar",
        "wowwo": "Wowwo"
    }
    
    results = {
        "success": {},
        "failure": {}
    }
    
    for company_id, company_name in companies.items():
        logger.info(f"Testing company: {company_name} (ID: {company_id})")
        
        # Try different URL patterns
        url_patterns = [
            f"https://www.mintos.com/en/loan-originators/{company_id}/",
            f"https://www.mintos.com/en/lending-companies/{company_id}/",
            f"https://www.mintos.com/en/loan-originators/{company_id}",
            f"https://www.mintos.com/en/lending-companies/{company_id}"
        ]
        
        success = False
        document_count = 0
        error_message = "All URL patterns failed"
        success_url = None
        
        for url in url_patterns:
            try:
                logger.info(f"Trying URL: {url}")
                
                # Request the URL
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    # Process the HTML
                    documents = scraper._parse_documents(response.text, company_name)
                    
                    logger.info(f"URL: {url}, Status: {response.status_code}, Documents: {len(documents)}")
                    
                    if documents:
                        success = True
                        document_count = len(documents)
                        error_message = None
                        success_url = url
                        
                        # Record the success
                        results["success"][company_id] = {
                            "company_name": company_name,
                            "url": url,
                            "document_count": document_count,
                            "documents": [doc["title"] for doc in documents[:3]]
                        }
                        
                        break
                else:
                    logger.warning(f"URL {url} returned status code {response.status_code}")
            
            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                error_message = str(e)
        
        if not success:
            # Record the failure
            results["failure"][company_id] = {
                "company_name": company_name,
                "error": error_message
            }
            
        # Add a short delay
        time.sleep(1)
    
    # Save results
    with open("problematic_companies_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("Document Extraction Test Results for Problematic Companies")
    print(f"Total companies tested: {len(companies)}")
    print(f"Successful extractions: {len(results['success'])}")
    print(f"Failed extractions: {len(results['failure'])}")
    
    if results["success"]:
        print("\nSuccessful companies:")
        for company_id, data in results["success"].items():
            print(f"- {data['company_name']} ({data['document_count']} docs): {data['url']}")
    
    if results["failure"]:
        print("\nFailed companies:")
        for company_id, data in results["failure"].items():
            print(f"- {data['company_name']}: {data['error']}")
    
    return results

if __name__ == "__main__":
    test_companies()