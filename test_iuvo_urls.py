"""
Special test for Iuvo Group with multiple URL formats
"""
import requests
import time
from bot.document_scraper import DocumentScraper

def test_iuvo_urls():
    """Test different URL formats for Iuvo Group"""
    scraper = DocumentScraper()
    
    # Different URL patterns to try
    url_patterns = [
        "https://www.mintos.com/en/loan-originators/iuvo/",
        "https://www.mintos.com/en/lending-companies/iuvo/",
        "https://www.mintos.com/en/loan-originators/iuvo-group/",
        "https://www.mintos.com/en/lending-companies/iuvo-group/",
        "https://www.mintos.com/en/loan-originators/iuvogroup/",
        "https://www.mintos.com/en/lending-companies/iuvogroup/",
        "https://www.mintos.com/en/investing/loan-originators/all/?name=iuvo",
        "https://www.mintos.com/en/investing/lending-companies/all/?name=iuvo"
    ]
    
    print("Testing different URL patterns for Iuvo Group:")
    print("---------------------------------------------")
    
    success = False
    
    for url in url_patterns:
        try:
            print(f"\nTrying URL: {url}")
            
            # Request the URL
            start_time = time.time()
            response = requests.get(url, timeout=15)
            end_time = time.time()
            
            status = response.status_code
            response_time = end_time - start_time
            
            print(f"Status code: {status}")
            print(f"Response time: {response_time:.2f} seconds")
            
            if status == 200:
                # Check content
                content_length = len(response.text)
                print(f"Content length: {content_length} bytes")
                
                # Check for keywords that might indicate a valid page
                has_iuvo = "iuvo" in response.text.lower()
                has_group = "group" in response.text.lower()
                has_documents = "document" in response.text.lower() 
                has_pdf = ".pdf" in response.text.lower()
                
                print(f"Contains 'iuvo': {has_iuvo}")
                print(f"Contains 'group': {has_group}")
                print(f"Contains 'document': {has_documents}")
                print(f"Contains '.pdf': {has_pdf}")
                
                # Try to extract documents
                docs = scraper._parse_documents(response.text, "Iuvo Group")
                print(f"Documents found: {len(docs)}")
                
                if docs:
                    success = True
                    print("\nDocument titles:")
                    for i, doc in enumerate(docs):
                        print(f"  {i+1}. {doc.get('title', 'No title')} ({doc.get('date', 'No date')})")
                else:
                    print("No documents found in the HTML content")
            else:
                print("URL returned error status")
                
        except Exception as e:
            print(f"Error: {str(e)}")
    
    if not success:
        print("\nNo successful document extraction found for any URL pattern")
    
    return success

if __name__ == "__main__":
    test_iuvo_urls()