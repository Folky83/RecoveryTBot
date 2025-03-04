"""
Simplified function to extract company URLs from Mintos details page
https://www.mintos.com/en/lending-companies/#details
"""
import logging
import requests
from typing import Dict, Any
from bs4 import BeautifulSoup
from requests_html import HTMLSession  # For JavaScript rendering

def fetch_company_urls_from_details() -> Dict[str, Dict[str, str]]:
    """Fetch company URLs from the Mintos lending companies details page
    
    Returns:
        Dictionary mapping company IDs to {name, url} dictionaries
    """
    logger = logging.getLogger(__name__)
    logger.info("Fetching company information from Mintos details page")
    company_urls = {}
    
    # The simplified approach uses the lending companies details page
    details_url = "https://www.mintos.com/en/lending-companies/#details"
    
    # Setup standard session for fallback
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    # First try with requests-html for better JS support
    try:
        logger.info(f"Fetching details page with JS support: {details_url}")
        html_session = HTMLSession()
        
        try:
            response = html_session.get(details_url, timeout=30)
            
            # Render JavaScript content (important for this page)
            response.html.render(timeout=45, sleep=2)
            logger.info("Successfully rendered details page with JavaScript")
            
            # Parse the details page - the lending company details are in a table
            soup = BeautifulSoup(response.html.html, 'html.parser')
            
            # Look for the table with lending company information
            tables = soup.select('table')
            if tables:
                logger.info(f"Found {len(tables)} tables on the page")
                
                # Process each table to find company information
                for table in tables:
                    # Look for table rows with company information
                    rows = table.select('tbody tr')
                    for row in rows:
                        try:
                            # Each row should have cells with company info
                            cells = row.select('td')
                            if len(cells) >= 2:  # Need at least name and possibly a link
                                # First cell usually contains the company name and link
                                name_cell = cells[0]
                                company_link = name_cell.select_one('a')
                                
                                if company_link and company_link.has_attr('href'):
                                    company_url = company_link['href']
                                    company_name = company_link.text.strip()
                                    
                                    # Extract company ID from URL
                                    path_parts = company_url.rstrip('/').split('/')
                                    company_id = path_parts[-1]
                                    
                                    # Skip if not a valid company page
                                    if (company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                                        not company_id or
                                        '?' in company_id or
                                        '#' in company_id or
                                        company_id.isdigit()):
                                        continue
                                    
                                    # Ensure URL is absolute
                                    if not company_url.startswith('http'):
                                        if company_url.startswith('/'):
                                            company_url = f"https://www.mintos.com{company_url}"
                                        else:
                                            company_url = f"https://www.mintos.com/{company_url}"
                                    
                                    # Add to our results if not already present
                                    if company_id not in company_urls:
                                        company_urls[company_id] = {
                                            'name': company_name,
                                            'url': company_url
                                        }
                                        logger.debug(f"Added company from details table: {company_name} ({company_id}) - {company_url}")
                        except Exception as e:
                            logger.warning(f"Error processing table row: {e}")
                            continue
            else:
                logger.warning("No tables found on the details page")
                
            # Also try to extract company links directly from the page
            # This works if the page structure changes but still contains company links
            company_links = response.html.links
            for link in company_links:
                if '/loan-originators/' in link or '/lending-companies/' in link:
                    # Extract company ID from URL
                    path_parts = link.rstrip('/').split('/')
                    company_id = path_parts[-1]
                    
                    # Skip main category pages and invalid IDs
                    if (company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                        not company_id or
                        '?' in company_id or
                        '#' in company_id or
                        company_id.isdigit()):
                        continue
                    
                    # Convert relative URL to absolute
                    if not link.startswith('http'):
                        if link.startswith('/'):
                            link = f"https://www.mintos.com{link}"
                        else:
                            link = f"https://www.mintos.com/{link}"
                    
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
                    
                    # Add to our results if not already present
                    if company_id not in company_urls:
                        company_urls[company_id] = {
                            'name': company_name,
                            'url': link
                        }
                        logger.debug(f"Added company using direct link: {company_name} ({company_id}) - {link}")
            
            # Close the session
            html_session.close()
            
        except Exception as e:
            logger.error(f"Error rendering/scraping details page with requests-html: {e}")
            try:
                html_session.close()
            except:
                pass
        
        if company_urls:
            logger.info(f"Successfully found {len(company_urls)} companies using requests-html")
        
    except ImportError:
        logger.warning("requests-html not available, will use regular requests")
    except Exception as e:
        logger.error(f"Error using requests-html: {e}")
    
    # If we still don't have companies, try with regular requests
    if not company_urls:
        logger.info("Trying regular requests as fallback method")
        try:
            response = session.get(details_url, timeout=10)
            if response.status_code == 200:
                html_content = response.text
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Look for links that might be company pages
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if '/loan-originators/' in href or '/lending-companies/' in href:
                        # Extract company ID from URL
                        path_parts = href.rstrip('/').split('/')
                        company_id = path_parts[-1]
                        
                        # Skip main category pages and invalid IDs
                        if (company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
                            not company_id or
                            '?' in company_id or
                            '#' in company_id or
                            company_id.isdigit()):
                            continue
                        
                        # Get company name from link text
                        company_name = link.get_text().strip()
                        if not company_name or len(company_name) < 2:
                            company_name = company_id.replace('-', ' ').title()
                        
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
                            logger.debug(f"Added company using regular requests: {company_name} ({company_id}) - {href}")
                
                if company_urls:
                    logger.info(f"Successfully found {len(company_urls)} companies using regular requests")
            else:
                logger.warning(f"Failed to fetch details page with regular requests: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching details page with regular requests: {e}")
    
    logger.info(f"Total companies found: {len(company_urls)}")
    return company_urls