"""
Test script to detect API endpoints by examining JavaScript content on the page
This looks for potential API URLs in the JavaScript code of the page
"""
import os
import json
import logging
import re
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def find_api_endpoints():
    """Find API endpoints by examining JavaScript on the page"""
    logger.info("Looking for API endpoints in page JavaScript")
    
    # Set up session with appropriate headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # URLs to examine for API endpoints
    urls_to_check = [
        "https://www.mintos.com/en/",
        "https://www.mintos.com/en/loan-originators/",
        "https://www.mintos.com/en/lending-companies/",
        "https://www.mintos.com/en/investing/"
    ]
    
    api_endpoints = []
    
    for url in urls_to_check:
        try:
            logger.info(f"Fetching page: {url}")
            response = session.get(url, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Save HTML for inspection
                url_parts = url.split('/')
                filename = url_parts[-2] if url.endswith('/') and url_parts[-1] == '' else url_parts[-1]
                filename = filename if filename else 'home'
                
                with open(f"{filename}_page.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"Saved HTML to {filename}_page.html")
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Look for script tags
                scripts = soup.find_all('script')
                logger.info(f"Found {len(scripts)} script tags")
                
                # Extract all script content and save to a file
                all_script_content = ""
                for idx, script in enumerate(scripts):
                    script_content = script.string
                    if script_content:
                        all_script_content += f"\n\n// SCRIPT {idx+1}\n"
                        all_script_content += script_content
                
                with open(f"{filename}_scripts.js", "w", encoding="utf-8") as f:
                    f.write(all_script_content)
                logger.info(f"Saved all scripts to {filename}_scripts.js")
                
                # Look for potential API URLs in script tags
                api_pattern = re.compile(r'(https?://[^/]*?/api/[^"\'\s>)]+)', re.IGNORECASE)
                for script in scripts:
                    script_content = script.string
                    if script_content:
                        matches = api_pattern.findall(script_content)
                        for match in matches:
                            logger.info(f"Found potential API URL: {match}")
                            # Clean up any trailing characters
                            clean_url = match.rstrip('\\').rstrip(',').rstrip('"').rstrip("'")
                            if clean_url not in api_endpoints:
                                api_endpoints.append(clean_url)
                
                # Look for API endpoints in other ways - data attributes
                elements_with_data = soup.find_all(attrs=lambda attr: any(a.startswith('data-') for a in attr if isinstance(a, str)))
                for element in elements_with_data:
                    for attr, value in element.attrs.items():
                        if isinstance(attr, str) and attr.startswith('data-') and 'api' in attr:
                            logger.info(f"Found data attribute with API reference: {attr}={value}")
                            if isinstance(value, str) and 'api' in value:
                                if value.startswith('http'):
                                    if value not in api_endpoints:
                                        api_endpoints.append(value)
                                        logger.info(f"Added API URL from data attribute: {value}")
            else:
                logger.warning(f"Failed to fetch page: {url} (status code: {response.status_code})")
        
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
    
    # Additional patterns to try
    additional_patterns = [
        "https://api.mintos.com/",
        "https://api.mintos.com/v1/",
        "https://api.mintos.com/v2/",
        "https://www.mintos.com/api/loan-originators",
        "https://www.mintos.com/graphql",
        "https://www.mintos.com/wp-json/"
    ]
    
    for pattern in additional_patterns:
        try:
            logger.info(f"Trying additional API pattern: {pattern}")
            response = session.get(pattern, timeout=10)
            
            if response.status_code < 400:  # Consider anything not 4xx or 5xx as potentially valid
                logger.info(f"Got response from additional pattern: {pattern} (status: {response.status_code})")
                if pattern not in api_endpoints:
                    api_endpoints.append(pattern)
                
                # Try to parse as JSON
                try:
                    data = response.json()
                    logger.info(f"Successfully parsed JSON from {pattern}")
                    
                    # Save response for inspection
                    pattern_name = pattern.split('/')[-1] if pattern.endswith('/') else pattern.split('/')[-1]
                    if not pattern_name:
                        pattern_name = "additional_" + str(len(api_endpoints))
                    
                    with open(f"api_response_{pattern_name}.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"Saved response to api_response_{pattern_name}.json")
                    
                except json.JSONDecodeError:
                    # Not JSON, save as text
                    pattern_name = pattern.split('/')[-1] if pattern.endswith('/') else pattern.split('/')[-1]
                    if not pattern_name:
                        pattern_name = "additional_" + str(len(api_endpoints))
                    
                    with open(f"api_response_{pattern_name}.txt", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.info(f"Saved non-JSON response to api_response_{pattern_name}.txt")
            
            elif response.status_code != 404:  # If not a standard 404, might be interesting
                logger.warning(f"Got non-404 error response from {pattern}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error trying additional pattern {pattern}: {e}")
    
    # Save all found API endpoints
    if api_endpoints:
        with open("found_api_endpoints.json", "w", encoding="utf-8") as f:
            json.dump(api_endpoints, f, indent=2)
        logger.info(f"Saved {len(api_endpoints)} API endpoints to found_api_endpoints.json")
    else:
        logger.warning("No API endpoints found")
    
    return api_endpoints

if __name__ == "__main__":
    find_api_endpoints()