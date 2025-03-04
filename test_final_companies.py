"""
Final test for specific company document extraction
"""
import json
import requests
import time
from bot.document_scraper import DocumentScraper

def test_companies():
    """Test document extraction for specific companies"""
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Key companies to test (smaller set)
    companies = {
        "iuvo": "Iuvo",
        "iuvo-group": "Iuvo Group",
        "wowwo": "Wowwo",
        "eleving-group": "Eleving Group"
    }
    
    results = {
        "success": {},
        "failure": {}
    }
    
    for company_id, company_name in companies.items():
        print(f"Testing company: {company_name} (ID: {company_id})")
        
        # Try different URL patterns
        url_patterns = [
            f"https://www.mintos.com/en/loan-originators/{company_id}/",
            f"https://www.mintos.com/en/lending-companies/{company_id}/"
        ]
        
        success = False
        document_count = 0
        error_message = "All URL patterns failed"
        success_url = None
        documents_found = []
        
        for url in url_patterns:
            try:
                print(f"  Trying URL: {url}")
                
                # Request the URL
                response = requests.get(url, timeout=10)
                status = response.status_code
                
                print(f"  Status code: {status}")
                
                if status == 200:
                    # Process the HTML
                    documents = scraper._parse_documents(response.text, company_name)
                    document_count = len(documents)
                    
                    print(f"  Documents found: {document_count}")
                    
                    if documents:
                        success = True
                        error_message = None
                        success_url = url
                        documents_found = documents
                        
                        # Show document titles
                        for i, doc in enumerate(documents[:3]):
                            print(f"    Document {i+1}: {doc.get('title', 'No title')} ({doc.get('date', 'No date')})")
                        
                        break
                    else:
                        print("  No documents found in the HTML content")
                else:
                    print(f"  URL returned error status {status}")
            
            except Exception as e:
                print(f"  Error: {str(e)}")
                error_message = str(e)
        
        # Record results
        if success:
            results["success"][company_id] = {
                "company_name": company_name,
                "url": success_url,
                "document_count": document_count,
                "documents": [
                    {"title": doc.get("title", ""), "date": doc.get("date", "")} 
                    for doc in documents_found[:3]
                ]
            }
        else:
            results["failure"][company_id] = {
                "company_name": company_name,
                "error": error_message
            }
            
        print("")  # Add blank line between companies
        
    # Save results
    with open("final_company_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\nDocument Extraction Test Results")
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