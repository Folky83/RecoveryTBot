"""
Document Scraper for Mintos Companies
Handles scraping and monitoring of company document pages for new documents.
"""
import os
import json
import time
import logging
import hashlib
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import requests
from bs4 import BeautifulSoup

from .logger import setup_logger

logger = setup_logger(__name__)

class DocumentScraper:
    """Scrapes and monitors company document pages for new documents"""
    
    CACHE_DIR = "data"
    DOCUMENTS_CACHE_FILE = os.path.join(CACHE_DIR, "documents_cache.json")
    
    # Main Mintos URLs
    MAIN_URL = "https://www.mintos.com/en/"
    COMPANIES_URL = "https://www.mintos.com/en/investing/"
    
    REQUEST_TIMEOUT = 10
    
    def __init__(self):
        """Initialize document scraper with session"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        
        # Load previous document data
        self.documents_data = self._load_documents_data()
        
    def _load_documents_data(self) -> Dict[str, Any]:
        """Load documents data from file"""
        try:
            if os.path.exists(self.DOCUMENTS_CACHE_FILE):
                with open(self.DOCUMENTS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded documents data: {len(data)} companies")
                return data
            else:
                logger.info("No document cache file found, creating a new one")
                return {}
        except Exception as e:
            logger.error(f"Error loading documents data: {e}", exc_info=True)
            return {}
            
    def _save_documents_data(self) -> None:
        """Save documents data to file"""
        try:
            with open(self.DOCUMENTS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.documents_data, f, indent=2)
            logger.info(f"Saved documents data: {len(self.documents_data)} companies")
        except Exception as e:
            logger.error(f"Error saving documents data: {e}", exc_info=True)
            
    def _make_request(self, url: str, use_js_rendering: bool = False) -> Optional[str]:
        """Make an HTTP request with retries, error handling, and optional JavaScript rendering
        
        Args:
            url: URL to request
            use_js_rendering: Whether to use requests-html with JavaScript rendering
            
        Returns:
            HTML content as string or None if request failed
        """
        max_retries = 3
        retry_delay = 2
        
        # Try using requests-html with JavaScript rendering if requested
        if use_js_rendering:
            try:
                from requests_html import HTMLSession
                
                logger.debug(f"Using JavaScript rendering for: {url}")
                html_session = HTMLSession()
                
                for attempt in range(max_retries):
                    try:
                        # Use longer timeouts for JavaScript rendering
                        response = html_session.get(url, timeout=30)
                        
                        if response.status_code == 200:
                            logger.debug(f"Successfully fetched {url}, rendering JavaScript...")
                            
                            try:
                                # Render with JavaScript and wait for any dynamic content
                                response.html.render(timeout=45, sleep=2)
                                logger.debug(f"JavaScript rendering successful for {url}")
                                
                                html_content = response.html.html
                                html_session.close()
                                return html_content
                            except Exception as js_error:
                                logger.warning(f"JavaScript rendering failed for {url}: {js_error}")
                                # Continue with regular content if rendering fails
                                html_content = response.text
                                html_session.close()
                                return html_content
                        elif response.status_code == 404:
                            logger.warning(f"Page not found: {url}")
                            html_session.close()
                            return None
                        else:
                            logger.warning(f"Request failed with status code {response.status_code}: {url}")
                    except Exception as e:
                        logger.error(f"Request error for {url}: {e}")
                        
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                
                # Close session if it's still open
                try:
                    html_session.close()
                except:
                    pass
                    
                logger.error(f"Max retries reached for {url} with JavaScript rendering")
                
            except ImportError:
                logger.warning("requests-html not available for JavaScript rendering, falling back to regular requests")
            except Exception as e:
                logger.error(f"Error using requests-html: {e}")
        
        # Fall back to regular requests
        for attempt in range(max_retries):
            try:
                logger.debug(f"Fetching URL: {url} (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    logger.debug(f"Successfully fetched {url}")
                    return response.text
                elif response.status_code == 404:
                    logger.warning(f"Page not found: {url}")
                    return None
                else:
                    logger.warning(f"Request failed with status code {response.status_code}: {url}")
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                
        logger.error(f"Max retries reached for {url}")
        return None
        
    def fetch_company_urls(self) -> Dict[str, Dict[str, str]]:
        """Fetch company URLs from the Mintos lending companies details page
        
        Returns:
            Dictionary mapping company IDs to {name, url} dictionaries
        """
        logger.info("Fetching company information from Mintos details page")
        company_urls = {}
        
        # First try the simplified extraction approach
        try:
            from .fetch_company_urls_simplified import fetch_company_urls_from_details
            
            logger.info("Using simplified extraction approach")
            simplified_urls = fetch_company_urls_from_details()
            
            if simplified_urls and len(simplified_urls) > 0:
                logger.info(f"Successfully found {len(simplified_urls)} companies using simplified approach")
                return simplified_urls
            else:
                logger.warning("Simplified approach returned no results, falling back to alternatives")
        except Exception as e:
            logger.error(f"Error using simplified extraction approach: {str(e)}", exc_info=True)
            logger.warning("Falling back to alternative extraction methods")
        
        # The simplified approach uses the lending companies details page
        details_url = "https://www.mintos.com/en/lending-companies/#details"
        
        # Fallback: Try using a more direct web scraping approach with the main lending companies page
        # This approach will look for company links in the main pages
        logger.info("Using direct web scraping approach to find company URLs")
        
        # Pages to check for company links
        pages_to_check = [
            "https://www.mintos.com/en/loan-originators/",
            "https://www.mintos.com/en/lending-companies/",
            "https://www.mintos.com/en/investing/"
        ]
        
        found_urls = 0
        
        # Try each page
        for page_url in pages_to_check:
            if found_urls > 0:
                # If we already found some URLs, skip remaining pages
                break
                
            try:
                logger.info(f"Fetching main page: {page_url}")
                html_content = self._make_request(page_url)
                
                if html_content:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Look for links that might be company pages
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if '/loan-originators/' in href or '/lending-companies/' in href:
                            # Extract company ID from URL
                            url_str = href
                            if isinstance(url_str, str):
                                if url_str.endswith('/'):
                                    url_str = url_str[:-1]  # Remove trailing slash
                                path_parts = url_str.split('/')
                                company_id = path_parts[-1] if path_parts else None
                            else:
                                logger.warning(f"Non-string URL encountered: {href}")
                                company_id = None
                            
                            # Skip main category pages and invalid IDs
                            if (not company_id or
                                company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
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
                                found_urls += 1
                                logger.debug(f"Added company from main page: {company_name} ({company_id}) - {href}")
                            
                    if company_urls:
                        logger.info(f"Successfully found {len(company_urls)} companies from main page")
                    else:
                        logger.warning(f"No company links found in {page_url}")
                else:
                    logger.warning(f"Failed to fetch page content from {page_url}")
                    
            except Exception as e:
                logger.error(f"Error scraping page {page_url}: {e}", exc_info=True)
        
        # If API approach didn't work, try with requests-html for JS rendering
        if not company_urls:
            try:
                from requests_html import HTMLSession
                
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
                        for table_index, table in enumerate(tables):
                            logger.debug(f"Processing table {table_index+1}")
                            
                            # Look for table rows with company information
                            rows = table.select('tbody tr')
                            logger.debug(f"Table {table_index+1} has {len(rows)} rows")
                            
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
                                            url_str = company_url
                                            if url_str.endswith('/'):
                                                url_str = url_str[:-1]  # Remove trailing slash
                                            path_parts = url_str.split('/')
                                            company_id = path_parts[-1] if len(path_parts) > 0 else None
                                            
                                            # Skip if not a valid company page
                                            if (not company_id or
                                                company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
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
                    link_count = 0
                    
                    for link in company_links:
                        if '/loan-originators/' in link or '/lending-companies/' in link:
                            link_count += 1
                            # Extract company ID from URL
                            url_str = link
                            if isinstance(url_str, str):
                                if url_str.endswith('/'):
                                    url_str = url_str[:-1]  # Remove trailing slash
                                path_parts = url_str.split('/')
                                company_id = path_parts[-1] if len(path_parts) > 0 else None
                            else:
                                logger.warning(f"Non-string URL encountered: {link}")
                                company_id = None
                            
                            # Skip main category pages and invalid IDs
                            if (not company_id or
                                company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
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
                    
                    logger.debug(f"Processed {link_count} company-related links")
                    
                    # Close the session
                    html_session.close()
                    
                except Exception as e:
                    logger.error(f"Error rendering/scraping details page with requests-html: {e}", exc_info=True)
                    try:
                        html_session.close()
                    except:
                        pass
                
                if company_urls:
                    logger.info(f"Successfully found {len(company_urls)} companies using requests-html")
                
            except ImportError:
                logger.warning("requests-html not available, will use regular requests")
            except Exception as e:
                logger.error(f"Error using requests-html: {e}", exc_info=True)
        
        # If we still don't have companies, try with regular requests
        if not company_urls:
            logger.info("Trying regular requests as fallback method")
            try:
                html_content = self._make_request(details_url)
                if html_content:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Look for links that might be company pages
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if '/loan-originators/' in href or '/lending-companies/' in href:
                            # Extract company ID from URL
                            url_str = href
                            if isinstance(url_str, str):
                                if url_str.endswith('/'):
                                    url_str = url_str[:-1]  # Remove trailing slash
                                path_parts = url_str.split('/')
                                company_id = path_parts[-1] if len(path_parts) > 0 else None
                            else:
                                logger.warning(f"Non-string URL encountered: {href}")
                                company_id = None
                            
                            # Skip main category pages and invalid IDs
                            if (not company_id or
                                company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
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
                    logger.warning("Failed to fetch details page with regular requests")
            except Exception as e:
                logger.error(f"Error fetching details page with regular requests: {e}", exc_info=True)
        
        # Fallback: If still no companies found, use the fallback mapping
        if not company_urls:
            logger.info("No companies found via simplified approach, using fallback mapping")
            company_urls = self._load_company_fallback_mapping()
            logger.info(f"Loaded {len(company_urls)} companies from fallback mapping")
        
        logger.info(f"Total companies found: {len(company_urls)}")
        return company_urls
            
    def _load_company_fallback_mapping(self) -> Dict[str, Dict[str, str]]:
        """Load company fallback mapping from JSON file
        
        This mapping provides alternative company IDs for companies that have
        been renamed or have special URL patterns.
        
        Returns:
            Dictionary mapping original company IDs to alternative IDs
        """
        try:
            mapping_file = "company_fallback_mapping.json"
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                logger.info(f"Loaded company fallback mapping: {len(mapping)} companies")
                return mapping
            else:
                logger.debug("No company fallback mapping file found")
                return {}
        except Exception as e:
            logger.error(f"Error loading company fallback mapping: {e}", exc_info=True)
            return {}
    
    def _generate_url_variations(self, company_id: str, company_name: str) -> List[str]:
        """Generate multiple URL variations for a company
        
        Args:
            company_id: The ID of the company
            company_name: The name of the company
            
        Returns:
            List of possible URLs to try
        """
        # Load fallback mapping for companies that have been renamed
        fallback_mapping = self._load_company_fallback_mapping()
        
        # Start with a list of direct URLs to try
        direct_urls = []
        
        # Check if we have a special fallback for this company
        if company_id in fallback_mapping:
            fallback_info = fallback_mapping[company_id]
            
            # Check for direct alt_urls that we know work
            if "alt_urls" in fallback_info and fallback_info["alt_urls"]:
                direct_urls.extend(fallback_info["alt_urls"])
                logger.info(f"Using {len(fallback_info['alt_urls'])} direct URLs from fallback for {company_id}")
            
            # Apply redirect if available
            redirect_id = fallback_info.get("redirect_id")
            if redirect_id:
                logger.info(f"Using fallback for {company_id}: redirecting to {redirect_id} ({fallback_info.get('notes', '')})")
                company_id = redirect_id
                # Update company name if provided
                redirect_name = fallback_info.get("redirect_name")
                if redirect_name:
                    company_name = redirect_name
                
                # Check if the redirect also has alt_urls
                if redirect_id in fallback_mapping and "alt_urls" in fallback_mapping[redirect_id]:
                    direct_urls.extend(fallback_mapping[redirect_id]["alt_urls"])
                    logger.info(f"Using {len(fallback_mapping[redirect_id]['alt_urls'])} direct URLs from redirect target")
        
        # Create variations of the company ID
        id_variations = [company_id]
        
        # Add variations with spaces/hyphens converted
        if ' ' in company_id:
            id_variations.append(company_id.replace(' ', '-'))
        if '-' in company_id:
            id_variations.append(company_id.replace('-', ''))
            id_variations.append(company_id.replace('-', ' '))
        
        # Add variations with "group" added/removed
        if 'group' not in company_id.lower():
            id_variations.append(f"{company_id}-group")
            id_variations.append(f"{company_id}group")
        else:
            # Try without "group"
            clean_id = company_id.lower().replace('-group', '').replace('group', '')
            if clean_id and clean_id != company_id:
                id_variations.append(clean_id)
        
        # Same for company name - create a slug from the name for URL usage
        name_slug = company_name.lower().replace(' ', '-')
        if name_slug not in id_variations:
            id_variations.append(name_slug)
        
        # Check for two-way mappings - for companies that have been renamed
        # but we might need to check previous names as well
        for mapped_id, info in fallback_mapping.items():
            if "alt_ids" in info and company_id in info["alt_ids"]:
                logger.info(f"Found two-way mapping: {company_id} is also referenced as {mapped_id}")
                if mapped_id not in id_variations:
                    id_variations.append(mapped_id)
        
        # Remove duplicates
        id_variations = list(set(id_variations))
        
        # Base URL patterns - No /documents URLs as they don't exist
        base_patterns = [
            "https://www.mintos.com/en/lending-companies/{}",
            "https://www.mintos.com/en/loan-originators/{}",
            "https://www.mintos.com/en/investing/loan-originators/{}",
            "https://www.mintos.com/en/investing/lending-companies/{}"
        ]
        
        # Generate all combinations
        urls = list(direct_urls)  # Start with our known direct URLs
        for pattern in base_patterns:
            for variation in id_variations:
                url = pattern.format(variation)
                if url not in urls:  # Avoid duplicates
                    urls.append(url)
        
        logger.debug(f"Generated {len(urls)} URL variations for {company_name} (including {len(direct_urls)} direct URLs)")
        return urls

    def get_company_documents(self, company_id: str, company_name: str, company_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get documents for a specific company
        
        Args:
            company_id: The ID of the company
            company_name: The name of the company
            company_url: Optional direct URL to the company page
            
        Returns:
            List of documents for the company
        """
        logger.info(f"Fetching documents for {company_name} (ID: {company_id})")
        
        # Track all URLs we've tried to avoid duplication
        tried_urls = set()
        
        # Check if this company has a fallback mapping with direct URLs
        fallback_mapping = self._load_company_fallback_mapping()
        direct_urls = []
        
        # First check the company directly
        if company_id in fallback_mapping and "alt_urls" in fallback_mapping[company_id]:
            direct_urls.extend(fallback_mapping[company_id]["alt_urls"])
            logger.info(f"Found {len(fallback_mapping[company_id]['alt_urls'])} direct URLs in fallback mapping for {company_id}")
        
        # Then check if this company has a redirect, and that redirect has direct URLs
        if company_id in fallback_mapping and fallback_mapping[company_id].get("redirect_id"):
            redirect_id = fallback_mapping[company_id]["redirect_id"]
            if redirect_id in fallback_mapping and "alt_urls" in fallback_mapping[redirect_id]:
                direct_urls.extend(fallback_mapping[redirect_id]["alt_urls"])
                logger.info(f"Found {len(fallback_mapping[redirect_id]['alt_urls'])} direct URLs from redirect target {redirect_id}")
        
        # Finally, check for two-way mappings
        for mapped_id, info in fallback_mapping.items():
            if "alt_ids" in info and company_id in info["alt_ids"] and "alt_urls" in info:
                direct_urls.extend(info["alt_urls"])
                logger.info(f"Found {len(info['alt_urls'])} direct URLs from two-way mapping with {mapped_id}")
                
        # If we have a provided URL, add it to our direct URLs list with highest priority
        if company_url:
            # If we have a direct URL, add it to the front of the list
            logger.debug(f"Using provided company URL: {company_url}")
            direct_urls.insert(0, company_url)
            
        # Make all direct URLs unique
        direct_urls = list(dict.fromkeys(direct_urls))
        
        # First try all our direct URLs, which we know have worked in the past
        for url in direct_urls:
            tried_urls.add(url)
            logger.info(f"Trying known working URL: {url}")
            
            # First try with JavaScript rendering for better document detection
            html_content = self._make_request(url, use_js_rendering=True)
            if html_content:
                logger.info(f"Successfully fetched content from {url} with JS rendering")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {url} with JS rendering")
                    return documents
            
            # Fall back to regular request if JS rendering fails or finds no documents
            html_content = self._make_request(url)
            if html_content:
                logger.info(f"Successfully fetched content from {url}")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {url}")
                    return documents
        
        # If direct URLs didn't work, generate all possible URL variations and try them
        urls_to_try = self._generate_url_variations(company_id, company_name)
        
        # Remove URLs we've already tried
        urls_to_try = [url for url in urls_to_try if url not in tried_urls]
        
        for url in urls_to_try:
            tried_urls.add(url)
            logger.debug(f"Trying URL variation: {url}")
            
            # Try with JavaScript rendering first
            html_content = self._make_request(url, use_js_rendering=True)
            if html_content:
                logger.info(f"Successfully fetched content from {url} with JS rendering")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {url} with JS rendering")
                    return documents
            
            # Fall back to regular request
            html_content = self._make_request(url)
            if html_content:
                logger.info(f"Successfully fetched content from {url}")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {url}")
                    return documents
                else:
                    logger.debug(f"No documents found at {url}, trying next variation")
        
        logger.warning(f"Could not find any documents for {company_name} after trying {len(tried_urls)} URL variations")
        return []
        
    def _parse_documents(self, html_content: str, company_name: str) -> List[Dict[str, Any]]:
        """Parse HTML to extract documents
        
        Args:
            html_content: HTML content of the company page
            company_name: Name of the company for logging
            
        Returns:
            List of document dictionaries with title, date, url, and metadata
            
        Note:
            This method implements a multi-stage approach to document extraction:
            1. Look for direct document links (PDFs, DOCs, etc.)
            2. Look for document sections by class name
            3. Look for country-specific sections based on headings
            4. Look for table sections that might contain documents
            5. As a fallback, search the entire page for document links
            
            Document metadata is enhanced with categorization (financial, presentation, 
            country-specific, etc.) when possible.
        """
        documents = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try multiple possible document section selectors for the new site structure
            document_sections = []
            
            # Option 1: Look for document sections with a specific class
            doc_sections = soup.find_all('div', class_='document-list')
            if doc_sections:
                document_sections.extend(doc_sections)
                
            # Option 2: Look for alternative document section classes
            alt_sections = soup.find_all('div', class_='loan-originator-info__documents')
            if alt_sections:
                document_sections.extend(alt_sections)
                
            # Option 3: Look for accordion sections that might contain documents
            accordion_sections = soup.find_all('div', class_='accordion')
            if accordion_sections:
                document_sections.extend(accordion_sections)
                
            # Option 4: Look for tab content areas that might contain documents
            tab_sections = soup.find_all('div', class_='tab-content')
            if tab_sections:
                document_sections.extend(tab_sections)
                
            # Option 5: Look for sections with "document" in their class name or id
            for element in soup.find_all(lambda tag: tag.has_attr('class') and isinstance(tag['class'], list) and any('document' in c.lower() for c in tag['class'])):
                document_sections.append(element)
            
            # Look for elements with "document" in their ID
            for element in soup.find_all(lambda tag: tag.has_attr('id') and isinstance(tag['id'], str) and 'document' in tag['id'].lower()):
                document_sections.append(element)
                
            # Option 6: Look for download sections
            for element in soup.find_all(lambda tag: tag.has_attr('class') and isinstance(tag['class'], list) and 
                                        any(any(term in c.lower() for term in ['download', 'pdf']) 
                                            for c in tag['class'])):
                document_sections.append(element)
                
            # Option 7: Look for country sections that might contain documents
            country_sections = []
            # Look for headings that might indicate a country section
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = heading.get_text(strip=True).lower()
                # If the heading contains country-related terms
                country_terms = [
                    'country', 'countries', 'region', 'regions', 'location', 'operations',
                    'europe', 'asia', 'africa', 'america', 'australia', 'oceania',
                    'baltic', 'northern europe', 'eastern europe', 'western europe', 'central europe',
                    'southeast asia', 'latin america', 'north america', 'central america',
                    'portugal', 'spain', 'france', 'italy', 'germany', 'uk', 'united kingdom',
                    'norway', 'sweden', 'finland', 'denmark', 'estonia', 'latvia', 'lithuania',
                    'poland', 'czech', 'slovakia', 'hungary', 'romania', 'bulgaria', 'greece',
                    'russia', 'ukraine', 'belarus', 'kazakhstan', 'georgia', 'azerbaijan',
                    'turkey', 'morocco', 'algeria', 'tunisia', 'egypt', 'kenya', 'south africa',
                    'mexico', 'brazil', 'argentina', 'chile', 'peru', 'colombia', 'venezuela',
                    'usa', 'united states', 'canada', 'china', 'japan', 'korea', 'singapore',
                    'vietnam', 'thailand', 'malaysia', 'indonesia', 'philippines', 'india',
                    'pakistan', 'bangladesh', 'australia', 'new zealand'
                ]
                if any(term in text for term in country_terms):
                    # Include both the heading and the content following it
                    section = heading.parent
                    if section:
                        country_sections.append(section)
                        
                        # Also look at siblings after the heading
                        next_elem = heading.find_next_sibling()
                        while next_elem:
                            if next_elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                                # Stop if we hit another heading
                                break
                            country_sections.append(next_elem)
                            next_elem = next_elem.find_next_sibling()
            
            if country_sections:
                document_sections.extend(country_sections)
                
            # Option 8: Look for sections with tables that might contain documents
            table_sections = soup.find_all('table')
            if table_sections:
                document_sections.extend(table_sections)
                
            if not document_sections:
                logger.warning(f"No document section found for {company_name}, falling back to PDF link search")
                # Fallback: Look for any document links throughout the page
                pdf_links = soup.find_all('a', href=lambda href: href and any(href.lower().endswith(ext) for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar']))
                
                for link in pdf_links:
                    try:
                        url = link.get('href')
                        if not url.startswith('http'):
                            # Convert relative URL to absolute
                            if url.startswith('/'):
                                url = f"https://www.mintos.com{url}"
                            else:
                                url = f"https://www.mintos.com/{url}"
                                
                        # Get document title
                        title = link.get_text(strip=True)
                        if not title or len(title) < 2:
                            # If link text is empty, try to use the filename from URL
                            filename = url.split('/')[-1]
                            # Clean up the filename to create a nice title
                            # Remove file extension
                            for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar']:
                                if filename.lower().endswith(ext):
                                    filename = filename[:-len(ext)]
                            # Replace common separators with spaces
                            title = filename.replace('-', ' ').replace('_', ' ').replace('.', ' ')
                            # Clean up multiple spaces
                            title = ' '.join(title.split())
                            # Capitalize the title for better appearance
                            title = title.capitalize()
                            
                        # Extract date or use current date
                        date = datetime.now().strftime("%Y-%m-%d")
                        
                        # Detect document type/category based on title and context
                        doc_type = self._detect_document_type(title, url)
                        
                        # Detect if this is a country-specific document
                        country_info = self._detect_country_info(title, url)
                        
                        # Create document entry
                        doc_id = self._generate_document_id(title, url, date)
                        document = {
                            'title': title,
                            'url': url,
                            'date': date,
                            'id': doc_id,
                            'company_name': company_name,
                            'document_type': doc_type,
                            'country_info': country_info
                        }
                        documents.append(document)
                    except Exception as e:
                        logger.error(f"Error parsing PDF link for {company_name}: {e}")
                
                return documents
                
            # Process all found document sections
            for section in document_sections:
                # Try multiple document item selectors
                doc_items = []
                
                # Try to find document items using different selectors
                selectors = [
                    {'tag': 'div', 'class': 'document-list__item'},
                    {'tag': 'a', 'class': 'file-item'},
                    {'tag': 'a', 'class': 'document-item'},
                    {'tag': 'div', 'class': 'file-item'},
                    {'tag': 'div', 'class': 'document-item'},
                    {'tag': 'a', 'href': lambda href: href and any(href.lower().endswith(ext) for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar'])}
                ]
                
                for selector in selectors:
                    if 'href' in selector:
                        items = section.find_all(selector['tag'], href=selector['href'])
                    else:
                        items = section.find_all(selector['tag'], class_=selector['class'])
                        
                    if items:
                        doc_items.extend(items)
                
                # Final fallback: get all links in the section
                if not doc_items:
                    doc_items = section.find_all('a')
                
                for doc_item in doc_items:
                    try:
                        # Get the actual link element if not already a link
                        link_element = doc_item.find('a') if doc_item.name != 'a' else doc_item
                        
                        if not link_element or not link_element.get('href'):
                            continue
                            
                        url = link_element.get('href')
                        
                        # Skip if not a document file (to avoid menu links, etc.)
                        supported_extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar']
                        if not any(url.lower().endswith(ext) for ext in supported_extensions):
                            continue
                            
                        if not url.startswith('http'):
                            # Convert relative URL to absolute
                            if url.startswith('/'):
                                url = f"https://www.mintos.com{url}"
                            else:
                                url = f"https://www.mintos.com/{url}"
                                
                        # Get document title using multiple approaches
                        title = link_element.get_text(strip=True)
                        
                        if not title or len(title) < 2:
                            # Try to find title in nested elements
                            title_candidates = [
                                link_element.find('span', class_='file-item__title'),
                                link_element.find('span', class_='document-title'),
                                link_element.find('div', class_='title'),
                                link_element.parent.find('h3'),
                                link_element.parent.find('h4')
                            ]
                            
                            for candidate in title_candidates:
                                if candidate and candidate.get_text(strip=True):
                                    title = candidate.get_text(strip=True)
                                    break
                                    
                        if not title or len(title) < 2:
                            # Fallback: Use the filename from the URL
                            filename = url.split('/')[-1]
                            # Clean up the filename to create a nice title
                            # Remove file extension
                            for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar']:
                                if filename.lower().endswith(ext):
                                    filename = filename[:-len(ext)]
                            # Replace common separators with spaces
                            title = filename.replace('-', ' ').replace('_', ' ').replace('.', ' ')
                            # Clean up multiple spaces
                            title = ' '.join(title.split())
                            # Capitalize the title for better appearance
                            title = title.capitalize()
                                
                        # Extract date using multiple approaches
                        date = ""
                        date_candidates = [
                            doc_item.find('span', class_='file-item__date'),
                            doc_item.find('span', class_='document-list__date'),
                            doc_item.find('span', class_='date'),
                            doc_item.find('div', class_='date'),
                            doc_item.parent.find(class_=lambda c: c and 'date' in c.lower())
                        ]
                        
                        for candidate in date_candidates:
                            if candidate and candidate.get_text(strip=True):
                                date = candidate.get_text(strip=True)
                                break
                                
                        if not date:
                            # Default to today's date if not found
                            date = datetime.now().strftime("%Y-%m-%d")
                            
                        # Detect document type/category based on title and context
                        doc_type = self._detect_document_type(title, url)
                        
                        # Detect if this is a country-specific document
                        country_info = self._detect_country_info(title, url)
                        
                        # Create document entry
                        doc_id = self._generate_document_id(title, url, date)
                        document = {
                            'title': title,
                            'url': url,
                            'date': date,
                            'id': doc_id,
                            'company_name': company_name,
                            'document_type': doc_type,
                            'country_info': country_info
                        }
                        documents.append(document)
                        
                    except Exception as e:
                        logger.error(f"Error parsing document item for {company_name}: {e}")
            
            # Remove duplicate documents (by URL)
            unique_docs = []
            seen_urls = set()
            for doc in documents:
                if doc['url'] not in seen_urls:
                    seen_urls.add(doc['url'])
                    unique_docs.append(doc)
                        
            logger.info(f"Found {len(unique_docs)} documents for {company_name}")
            return unique_docs
            
        except Exception as e:
            logger.error(f"Error parsing documents for {company_name}: {e}", exc_info=True)
            return []
            
    def _detect_document_type(self, title: str, url: str) -> str:
        """Detect the type of document based on title and URL
        
        Args:
            title: Document title
            url: Document URL
            
        Returns:
            Document type/category as a string
        """
        title_lower = title.lower()
        url_lower = url.lower()
        
        # Financial documents
        if any(term in title_lower for term in ['financial', 'finance', 'statement', 'report', 'balance sheet', 
                                               'income statement', 'cash flow', 'annual report',
                                               'quarterly report', 'profit', 'loss']):
            return 'financial'
            
        # Presentation documents
        if any(term in title_lower for term in ['presentation', 'overview', 'introduction', 'about',
                                              'company profile', 'investor']):
            return 'presentation'
            
        # Regulatory documents
        if any(term in title_lower for term in ['regulatory', 'regulation', 'compliance', 'law', 'legal',
                                              'terms', 'conditions', 'policy', 'procedure']):
            return 'regulatory'
            
        # Agreement documents
        if any(term in title_lower for term in ['agreement', 'contract', 'terms', 'loan agreement', 
                                              'assignment', 'guarantee']):
            return 'agreement'
            
        # Default to generic document
        return 'general'
        
    def _detect_country_info(self, title: str, url: str) -> Dict[str, Any]:
        """Detect country information in document title or URL
        
        Args:
            title: Document title
            url: Document URL
            
        Returns:
            Dictionary with country information or empty dict if none detected
        """
        title_lower = title.lower()
        url_lower = url.lower()
        
        country_data = {}
        
        # List of countries to check for
        countries = [
            # Europe
            'latvia', 'estonia', 'lithuania', 'poland', 'germany', 'france', 'spain', 'italy',
            'uk', 'united kingdom', 'great britain', 'netherlands', 'belgium', 'luxembourg',
            'sweden', 'norway', 'finland', 'denmark', 'czech', 'slovakia', 'austria', 'switzerland',
            'hungary', 'romania', 'bulgaria', 'greece', 'croatia', 'slovenia', 'serbia', 'bosnia',
            'albania', 'macedonia', 'montenegro', 'moldova', 'ukraine', 'belarus', 'russia',
            
            # Asia
            'turkey', 'kazakhstan', 'uzbekistan', 'kyrgyzstan', 'tajikistan', 'turkmenistan',
            'azerbaijan', 'armenia', 'georgia', 'china', 'japan', 'korea', 'india', 'pakistan',
            'bangladesh', 'vietnam', 'thailand', 'malaysia', 'indonesia', 'philippines', 'singapore',
            
            # Africa
            'egypt', 'morocco', 'algeria', 'tunisia', 'libya', 'nigeria', 'south africa', 'kenya',
            'ethiopia', 'ghana', 'tanzania', 'uganda',
            
            # Americas
            'usa', 'united states', 'canada', 'mexico', 'brazil', 'argentina', 'chile', 
            'colombia', 'peru', 'venezuela', 'ecuador', 'bolivia'
        ]
        
        # Regions
        regions = [
            'europe', 'western europe', 'eastern europe', 'central europe', 'northern europe', 'southern europe',
            'asia', 'east asia', 'south asia', 'southeast asia', 'central asia', 'middle east',
            'africa', 'north africa', 'sub-saharan africa', 'west africa', 'east africa', 'southern africa',
            'americas', 'north america', 'south america', 'central america', 'latin america',
            'oceania', 'australia', 'new zealand', 'pacific'
        ]
        
        # Check for country mentions
        detected_countries = []
        for country in countries:
            if country in title_lower or country in url_lower:
                detected_countries.append(country)
                
        # Check for region mentions
        detected_regions = []
        for region in regions:
            if region in title_lower or region in url_lower:
                detected_regions.append(region)
                
        # If we found country information, return it
        if detected_countries or detected_regions:
            country_data = {
                'is_country_specific': True,
                'countries': detected_countries,
                'regions': detected_regions
            }
        else:
            country_data = {
                'is_country_specific': False
            }
            
        return country_data
        
    def _generate_document_id(self, title: str, url: str, date: str) -> str:
        """Generate a unique ID for a document based on its properties
        
        Args:
            title: Document title
            url: Document URL
            date: Document date
            
        Returns:
            String identifier for the document
        """
        # Create a unique hash using the document properties
        hash_input = f"{title}|{url}|{date}".encode('utf-8')
        return hashlib.md5(hash_input).hexdigest()
        
    def test_url_extraction(self) -> Dict[str, Dict[str, str]]:
        """Test method to extract and return company URLs
        
        Returns:
            Dictionary of company IDs to URL and name information
        """
        # First try the simplified approach
        try:
            from .fetch_company_urls_simplified import fetch_company_urls_from_details
            return fetch_company_urls_from_details()
        except Exception as e:
            logger.error(f"Error using simplified extraction: {e}", exc_info=True)
            # Fall back to normal scraping method
            return self.fetch_company_urls()
    
    def check_all_companies(self, company_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """Check all companies for new documents
        
        Args:
            company_mapping: Dictionary mapping company IDs to names
            
        Returns:
            List of new documents detected
        """
        new_documents = []
        
        # Try to fetch company URLs directly from Mintos website
        fetched_company_urls = self.fetch_company_urls()
        logger.info(f"Fetched {len(fetched_company_urls)} companies directly from Mintos website")
        
        # Combine the provided mapping with the fetched URLs
        combined_companies = {}
        
        # Start with the fetched company data (it has URLs)
        for company_id, company_info in fetched_company_urls.items():
            combined_companies[company_id] = {
                'name': company_info['name'],
                'url': company_info['url']
            }
            
        # Add any companies from the provided mapping that aren't already included
        for company_id, company_name in company_mapping.items():
            if company_id not in combined_companies:
                combined_companies[company_id] = {
                    'name': company_name,
                    'url': None  # No direct URL, will use fallback patterns
                }
            elif not combined_companies[company_id]['name']:
                # Update name if it's missing in the fetched data
                combined_companies[company_id]['name'] = company_name
        
        logger.info(f"Checking documents for {len(combined_companies)} companies")
        
        # Process all companies
        for company_id, company_info in combined_companies.items():
            company_name = company_info['name']
            company_url = company_info['url']
            
            try:
                logger.info(f"Checking documents for {company_name}")
                
                # Get current documents
                current_documents = self.get_company_documents(company_id, company_name, company_url)
                
                # Get previous documents for this company
                previous_documents = self.documents_data.get(company_id, [])
                
                # Find new documents
                previous_doc_ids = {doc.get('id') for doc in previous_documents}
                for doc in current_documents:
                    if doc.get('id') not in previous_doc_ids:
                        logger.info(f"New document found for {company_name}: {doc.get('title')}")
                        new_document = {
                            'company_id': company_id,
                            'company_name': company_name,
                            'document': doc
                        }
                        new_documents.append(new_document)
                        
                # Update stored documents for this company
                self.documents_data[company_id] = current_documents
                
                # Add a small delay to avoid overwhelming the server
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error checking documents for {company_name}: {e}", exc_info=True)
                
        # Save updated document data
        self._save_documents_data()
        
        return new_documents