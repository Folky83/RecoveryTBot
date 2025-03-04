"""
Test the direct API approach for fetching company URLs
This tests the new implementation that tries to fetch company data directly from Mintos API endpoints.
"""
import os
import json
import logging
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_api_approach():
    """Test the direct API approach for fetching company URLs"""
    logger.info("Testing direct API approach for company URLs")
    company_urls = {}
    
    # Define the API endpoints to try
    api_endpoints = [
        # Main lending companies API endpoint
        "https://www.mintos.com/api/en/lending-companies/",
        "https://www.mintos.com/api/en/loan-originators/",
        # Alternative URLs with different formats
        "https://www.mintos.com/api/loan-originators/",
        "https://www.mintos.com/api/lending-companies/"
    ]
    
    # Set up session with appropriate headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # Try each API endpoint
    for endpoint in api_endpoints:
        try:
            logger.info(f"Fetching data from API endpoint: {endpoint}")
            response = session.get(endpoint, timeout=10)
            
            if response.status_code == 200:
                try:
                    # Try to parse JSON response
                    data = response.json()
                    logger.info(f"Successfully got JSON data from API: {endpoint}")
                    
                    # Save the raw response for inspection
                    endpoint_name = endpoint.split('/')[-2] if endpoint.endswith('/') else endpoint.split('/')[-1]
                    with open(f"api_response_{endpoint_name}.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"Saved raw API response to api_response_{endpoint_name}.json")
                    
                    # Process different API response formats
                    if isinstance(data, list):
                        # Direct list of companies
                        for company in data:
                            if isinstance(company, dict):
                                company_id = company.get('id') or company.get('slug')
                                company_name = company.get('name')
                                company_url = company.get('url')
                                
                                if company_id and company_name:
                                    # Convert ID to string if it's numeric
                                    company_id = str(company_id)
                                    
                                    # Create URL if not provided
                                    if not company_url:
                                        company_url = f"https://www.mintos.com/en/loan-originators/{company_id}/"
                                    
                                    # Ensure URL is absolute
                                    if not company_url.startswith('http'):
                                        if company_url.startswith('/'):
                                            company_url = f"https://www.mintos.com{company_url}"
                                        else:
                                            company_url = f"https://www.mintos.com/{company_url}"
                                    
                                    # Add to our results
                                    company_urls[company_id] = {
                                        'name': company_name,
                                        'url': company_url
                                    }
                                    logger.debug(f"Added company from API list: {company_name} ({company_id})")
                    
                    elif isinstance(data, dict):
                        # Look for companies in different possible nested structures
                        for key in ['data', 'companies', 'lenders', 'loan_originators', 'results', 'items']:
                            if key in data and isinstance(data[key], list):
                                companies_list = data[key]
                                logger.info(f"Found companies list in key: {key} (count: {len(companies_list)})")
                                
                                for company in companies_list:
                                    if isinstance(company, dict):
                                        company_id = company.get('id') or company.get('slug')
                                        company_name = company.get('name')
                                        company_url = company.get('url')
                                        
                                        # Log the keys in the company dict to understand structure
                                        logger.debug(f"Company keys: {list(company.keys())}")
                                        
                                        if company_id and company_name:
                                            # Convert ID to string if it's numeric
                                            company_id = str(company_id)
                                            
                                            # Create URL if not provided
                                            if not company_url:
                                                company_url = f"https://www.mintos.com/en/loan-originators/{company_id}/"
                                            
                                            # Ensure URL is absolute
                                            if not company_url.startswith('http'):
                                                if company_url.startswith('/'):
                                                    company_url = f"https://www.mintos.com{company_url}"
                                                else:
                                                    company_url = f"https://www.mintos.com/{company_url}"
                                            
                                            # Add to our results
                                            company_urls[company_id] = {
                                                'name': company_name,
                                                'url': company_url
                                            }
                                            logger.info(f"Added company: {company_name} ({company_id})")
                    
                    # If we found companies, break out of the loop
                    if company_urls:
                        logger.info(f"Successfully found {len(company_urls)} companies from API endpoint: {endpoint}")
                        break
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON response from API endpoint: {endpoint}")
                    # Save the raw response for inspection
                    with open(f"api_response_raw_{endpoint.split('/')[-1]}.txt", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.info(f"Saved raw text response to api_response_raw_{endpoint.split('/')[-1]}.txt")
            else:
                logger.warning(f"API request failed with status code {response.status_code}: {endpoint}")
                
        except Exception as e:
            logger.error(f"Error accessing API endpoint {endpoint}: {e}")
    
    # Save the results to a JSON file
    if company_urls:
        with open("direct_api_company_urls.json", "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to direct_api_company_urls.json")
    else:
        logger.warning("No companies found via direct API approach")
    
    return company_urls

if __name__ == "__main__":
    test_api_approach()