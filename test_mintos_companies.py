"""
Test to extract company URLs directly from the Mintos main page
"""
import json
import requests
from bs4 import BeautifulSoup

def search_for_companies():
    """Search for company URLs on the Mintos main pages"""
    
    # Main URLs to search
    main_urls = [
        "https://www.mintos.com/en/investing/",
        "https://www.mintos.com/en/investing/all-loans/",
        "https://www.mintos.com/en/investing/lending-companies/all/"
    ]
    
    # Companies we're particularly interested in
    target_companies = [
        "iuvo", 
        "iuvo group", 
        "eleving", 
        "eleving group", 
        "mogo", 
        "delfin", 
        "delfin group", 
        "novaloans", 
        "sun finance"
    ]
    
    results = {}
    
    for url in main_urls:
        print(f"\nChecking URL: {url}")
        
        try:
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                print(f"Failed to access URL: {response.status_code}")
                continue
                
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for links
            links = soup.find_all('a')
            print(f"Found {len(links)} links on the page")
            
            # Filter links
            company_links = []
            for link in links:
                href = link.get('href', '')
                text = link.text.strip().lower()
                
                # Check if the link contains any of our target companies in the URL or text
                is_target = any(company in href.lower() or company in text for company in target_companies)
                
                # Look for links related to loan originators or lending companies
                if ('loan-originators' in href or 'lending-companies' in href or is_target) and href not in company_links:
                    company_links.append(href)
                    company_name = link.text.strip()
                    
                    # Make URL absolute if it's relative
                    if href.startswith('/'):
                        href = 'https://www.mintos.com' + href
                    
                    print(f"Found company link: {company_name} -> {href}")
                    
                    # Save to results
                    if company_name not in results:
                        results[company_name] = []
                    
                    if href not in results[company_name]:
                        results[company_name].append(href)
        
        except Exception as e:
            print(f"Error processing URL {url}: {str(e)}")
    
    # Save results to a file
    with open('mintos_companies_urls.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nFound information for {len(results)} companies")
    
    # Check specifically for our target companies
    print("\nResults for target companies:")
    for company in target_companies:
        found = False
        for name, urls in results.items():
            if company.lower() in name.lower():
                print(f"- {company.title()}: Found as '{name}' with {len(urls)} URLs")
                for url in urls:
                    print(f"  - {url}")
                found = True
        
        if not found:
            print(f"- {company.title()}: Not found")
    
    return results

if __name__ == "__main__":
    search_for_companies()