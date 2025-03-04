"""
Simplified test script for requests-html
This script tests basic functionality without JavaScript rendering.
"""
import sys
import json
from datetime import datetime

def test_simple_requests_html():
    """Test basic requests-html functionality without JavaScript rendering"""
    print("Starting simplified requests-html test")
    
    try:
        print("Importing requests_html...")
        from requests_html import HTMLSession
        print("Successfully imported requests_html!")
        
        print("\nCreating HTMLSession...")
        session = HTMLSession()
        print("Successfully created HTMLSession!")
        
        print("\nMaking a simple request to Mintos loan originators page...")
        url = "https://www.mintos.com/en/loan-originators/"
        r = session.get(url, timeout=10)
        print(f"Request status: {r.status_code}")
        
        print("\nLooking for links without JavaScript rendering...")
        links = [link for link in r.html.links 
                if '/loan-originators/' in link and link != url]
        
        print(f"Found {len(links)} links with '/loan-originators/' in them")
        
        # Show a sample of the links
        print("\nSample links (max 5):")
        for i, link in enumerate(links[:5]):
            print(f"{i+1}. {link}")
        
        # Extract potential company IDs
        company_ids = {}
        for link in links:
            parts = link.rstrip('/').split('/')
            if len(parts) > 0:
                potential_id = parts[-1]
                if potential_id != 'loan-originators' and len(potential_id) > 0:
                    if potential_id not in company_ids:
                        company_ids[potential_id] = link
        
        print(f"\nExtracted {len(company_ids)} potential company IDs")
        
        # Show a sample of company IDs
        print("\nSample company IDs (max 5):")
        keys = list(company_ids.keys())[:5]
        for i, key in enumerate(keys):
            print(f"{i+1}. {key}: {company_ids[key]}")
        
        # Save results to a file
        results = {
            "timestamp": datetime.now().isoformat(),
            "company_ids": company_ids
        }
        
        with open("simple_test_results.json", "w") as f:
            json.dump(results, f, indent=2)
        print("\nResults saved to simple_test_results.json")
        
        print("\nTest completed successfully!")
        session.close()
        return True
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_simple_requests_html()