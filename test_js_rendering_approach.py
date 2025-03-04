"""
Test the web scraping approach with JavaScript rendering support
This script uses requests-html to render JavaScript for better extraction of company URLs.
"""
import os
import json
import logging
import time
from requests_html import HTMLSession

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_js_rendering_approach():
    """Test web scraping with JavaScript rendering for company URLs"""
    logger.info("Testing web scraping with JavaScript rendering")
    company_urls = {}
    
    # URLs to try (in order of preference) - only testing one for now
    urls_to_try = [
        "https://www.mintos.com/en/investing/"
    ]
    
    session = HTMLSession()
    
    for url in urls_to_try:
        if company_urls:  # If we already found companies, skip remaining URLs
            break
            
        try:
            logger.info(f"Fetching page with JS rendering: {url}")
            response = session.get(url, timeout=30)
            
            # Check if we got a valid response
            if response.status_code != 200:
                logger.warning(f"Failed to fetch page: {url} (status: {response.status_code})")
                continue
                
            # Save original HTML for comparison
            url_parts = url.split('/')
            base_filename = url_parts[-1].split('#')[0] if '#' in url_parts[-1] else url_parts[-1]
            if not base_filename:
                base_filename = url_parts[-2] if len(url_parts) > 1 else 'index'
            
            with open(f"{base_filename}_original.html", "w", encoding="utf-8") as f:
                f.write(response.html.html)
            logger.info(f"Saved original HTML to {base_filename}_original.html")
            
            # Render JavaScript with shorter timeout
            logger.info(f"Rendering JavaScript for {url}...")
            start_time = time.time()
            response.html.render(timeout=20, sleep=2)  # Shorter timeout to avoid hanging
            render_time = time.time() - start_time
            logger.info(f"JavaScript rendering completed in {render_time:.2f} seconds")
            
            # Save rendered HTML
            with open(f"{base_filename}_rendered.html", "w", encoding="utf-8") as f:
                f.write(response.html.html)
            logger.info(f"Saved rendered HTML to {base_filename}_rendered.html")
            
            # Extract company links from the rendered page
            found_links = 0
            
            # Method 1: Try to find company links in tables (details page)
            tables = response.html.find('table')
            if tables:
                logger.info(f"Found {len(tables)} tables on the page")
                
                # Process each table to find company information
                for table_index, table in enumerate(tables):
                    logger.debug(f"Processing table {table_index+1}")
                    
                    # Look for table rows with company information
                    rows = table.find('tr')
                    logger.debug(f"Table {table_index+1} has {len(rows)} rows")
                    
                    for row in rows:
                        try:
                            # Each row should have cells with company info
                            cells = row.find('td')
                            if len(cells) >= 2:  # Need at least name and possibly a link
                                # First cell usually contains the company name and link
                                links = cells[0].find('a')
                                
                                if links:
                                    link = links[0]
                                    href = link.attrs.get('href', '')
                                    company_name = link.text.strip()
                                    
                                    # Skip if not a company link
                                    if not href or not href.strip() or not ('/loan-originators/' in href or '/lending-companies/' in href):
                                        continue
                                        
                                    # Extract company ID from URL
                                    if href.endswith('/'):
                                        href = href[:-1]  # Remove trailing slash
                                    path_parts = href.split('/')
                                    company_id = path_parts[-1] if path_parts else None
                                    
                                    # Skip if not a valid company ID
                                    if (not company_id or
                                        company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                                        '?' in company_id or
                                        '#' in company_id or
                                        company_id.isdigit()):
                                        continue
                                    
                                    # Ensure URL is absolute
                                    if not href.startswith('http'):
                                        if href.startswith('/'):
                                            href = f"https://www.mintos.com{href}"
                                        else:
                                            href = f"https://www.mintos.com/{href}"
                                    
                                    # Add to our results if not already present
                                    if company_id not in company_urls:
                                        company_urls[company_id] = {
                                            'name': company_name,
                                            'url': href
                                        }
                                        found_links += 1
                                        logger.info(f"Found company in table: {company_name} ({company_id})")
                        except Exception as e:
                            logger.warning(f"Error processing table row: {e}")
                            continue
                            
            # Method 2: Look for all links that might be company pages
            company_links = []
            for link in response.html.links:
                if '/loan-originators/' in link or '/lending-companies/' in link:
                    company_links.append(link)
            
            logger.info(f"Found {len(company_links)} potential company links")
            
            for link in company_links:
                try:
                    # Extract company ID from URL
                    if link.endswith('/'):
                        link = link[:-1]  # Remove trailing slash
                    path_parts = link.split('/')
                    company_id = path_parts[-1] if path_parts else None
                    
                    # Skip main category pages and invalid IDs
                    if (not company_id or
                        company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                        '?' in company_id or
                        '#' in company_id or
                        company_id.isdigit()):
                        continue
                    
                    # Find the element with this link to get the name
                    elements = response.html.find(f'a[href*="{company_id}"]')
                    company_name = None
                    
                    if elements:
                        # Get text from the first matching element
                        element_text = elements[0].text.strip()
                        if element_text and len(element_text) > 1:
                            company_name = element_text
                    
                    # Fallback to ID-based name if element text not found
                    if not company_name:
                        company_name = company_id.replace('-', ' ').title()
                    
                    # Convert relative URL to absolute
                    if not link.startswith('http'):
                        if link.startswith('/'):
                            link = f"https://www.mintos.com{link}"
                        else:
                            link = f"https://www.mintos.com/{link}"
                    
                    # Add to our results if not already present
                    if company_id not in company_urls:
                        company_urls[company_id] = {
                            'name': company_name,
                            'url': link
                        }
                        found_links += 1
                        logger.info(f"Found company from link: {company_name} ({company_id})")
                
                except Exception as e:
                    logger.warning(f"Error processing link {link}: {e}")
                    continue
            
            logger.info(f"Found a total of {found_links} company links")
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
        
    # Close the session
    session.close()
    
    # Save results to a file
    if company_urls:
        with open("js_rendering_results.json", "w", encoding="utf-8") as f:
            json.dump(company_urls, f, indent=2)
        logger.info(f"Saved {len(company_urls)} companies to js_rendering_results.json")
    else:
        logger.warning("No companies found via JavaScript rendering")
    
    return company_urls

if __name__ == "__main__":
    test_js_rendering_approach()