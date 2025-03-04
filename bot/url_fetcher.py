"""
URL Fetcher for Mintos Companies
Handles fetching company URLs and page content with proper error handling and retries.
"""
import os
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any, Union
from requests_html import HTMLSession

from .logger import setup_logger

logger = setup_logger(__name__)

class URLFetcher:
    """Handles URL fetching with proper error handling and retries"""
    
    CACHE_DIR = "data"
    COMPANY_URLS_CACHE_FILE = os.path.join(CACHE_DIR, "company_urls_cache.json")
    FALLBACK_MAPPING_FILE = os.path.join(CACHE_DIR, "company_fallback_mapping.json")
    
    # Main Mintos URLs
    MAIN_URL = "https://www.mintos.com/en/"
    COMPANIES_URL = "https://www.mintos.com/en/investing/"
    DETAILS_URL = "https://www.mintos.com/en/lending-companies/#details"
    
    REQUEST_TIMEOUT = 10
    
    def __init__(self):
        """Initialize URL fetcher with session"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        
    def make_request(self, url: str, use_js_rendering: bool = False) -> Optional[str]:
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
        
        # Load cached company URLs if available
        cached_urls = self._load_cached_company_urls()
        if cached_urls:
            logger.info(f"Using cached company URLs: {len(cached_urls)} companies")
            return cached_urls
        
        # First try the simplified extraction approach
        try:
            from .fetch_company_urls_simplified import fetch_company_urls_from_details
            
            logger.info("Using simplified extraction approach")
            simplified_urls = fetch_company_urls_from_details()
            
            if simplified_urls and len(simplified_urls) > 0:
                logger.info(f"Successfully found {len(simplified_urls)} companies using simplified approach")
                self._save_company_urls(simplified_urls)
                return simplified_urls
            else:
                logger.warning("Simplified approach returned no results, falling back to alternatives")
        except Exception as e:
            logger.error(f"Error using simplified extraction approach: {str(e)}", exc_info=True)
            logger.warning("Falling back to alternative extraction methods")
        
        # Try the main web scraping approach
        company_urls = self._fetch_company_urls_from_web()
        
        # If web scraping approach didn't work, use fallback mapping
        if not company_urls:
            logger.warning("Web scraping approach failed, using fallback mapping")
            company_urls = self._get_fallback_company_urls()
        
        # Save the company URLs to cache
        if company_urls:
            self._save_company_urls(company_urls)
            
        return company_urls
    
    def _fetch_company_urls_from_web(self) -> Dict[str, Dict[str, str]]:
        """Fetch company URLs using web scraping approach
        
        Returns:
            Dictionary mapping company IDs to {name, url} dictionaries
        """
        company_urls = {}
        
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
                html_content = self.make_request(page_url)
                
                if html_content:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Look for links that might be company pages
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if '/loan-originators/' in href or '/lending-companies/' in href:
                            # Extract company ID from URL
                            company_id = self._extract_company_id_from_url(href)
                            if not company_id:
                                continue
                            
                            # Get company name from link text
                            company_name = link.get_text().strip()
                            if not company_name or len(company_name) < 2:
                                company_name = company_id.replace('-', ' ').title()
                            
                            # Ensure URL is absolute
                            href = self._ensure_absolute_url(href)
                            
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
        
        # If HTML approach didn't work, try with JavaScript rendering
        if not company_urls:
            logger.info("Trying with JavaScript rendering")
            js_urls = self._fetch_company_urls_with_js()
            if js_urls:
                company_urls = js_urls
        
        return company_urls
    
    def _fetch_company_urls_with_js(self) -> Dict[str, Dict[str, str]]:
        """Fetch company URLs using JavaScript rendering
        
        Returns:
            Dictionary mapping company IDs to {name, url} dictionaries
        """
        company_urls = {}
        
        try:
            logger.info(f"Fetching details page with JS support: {self.DETAILS_URL}")
            html_content = self.make_request(self.DETAILS_URL, use_js_rendering=True)
            
            if not html_content:
                logger.warning("Failed to fetch details page with JS rendering")
                return company_urls
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for the table with lending company information
            tables = soup.select('table')
            if not tables:
                logger.warning("No tables found on the page")
                return company_urls
            
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
                                company_id = self._extract_company_id_from_url(company_url)
                                if not company_id:
                                    continue
                                
                                # Ensure URL is absolute
                                company_url = self._ensure_absolute_url(company_url)
                                
                                # Add to company URLs
                                company_urls[company_id] = {
                                    'name': company_name,
                                    'url': company_url
                                }
                                logger.debug(f"Added company from table: {company_name} ({company_id})")
                    except Exception as e:
                        logger.error(f"Error processing table row: {e}")
                        continue
            
            if company_urls:
                logger.info(f"Found {len(company_urls)} companies with JS rendering")
            else:
                logger.warning("No company links found with JS rendering")
                
        except Exception as e:
            logger.error(f"Error in JS rendering approach: {e}", exc_info=True)
            
        return company_urls
    
    def _extract_company_id_from_url(self, url: str) -> Optional[str]:
        """Extract company ID from URL
        
        Args:
            url: URL to extract company ID from
            
        Returns:
            Company ID or None if not found
        """
        if not isinstance(url, str):
            logger.warning(f"Non-string URL encountered: {url}")
            return None
            
        # Remove trailing slash
        if url.endswith('/'):
            url = url[:-1]
            
        # Extract ID from path
        path_parts = url.split('/')
        company_id = path_parts[-1] if path_parts else None
        
        # Skip main category pages and invalid IDs
        if (not company_id or
            company_id in ['loan-originators', 'lending-companies', 'details', '#details'] or
            '?' in company_id or
            '#' in company_id or
            company_id.isdigit()):
            return None
            
        return company_id
    
    def _ensure_absolute_url(self, url: str) -> str:
        """Ensure URL is absolute
        
        Args:
            url: URL to check
            
        Returns:
            Absolute URL
        """
        if not url.startswith('http'):
            if url.startswith('/'):
                url = f"https://www.mintos.com{url}"
            else:
                url = f"https://www.mintos.com/{url}"
        return url
    
    def _load_cached_company_urls(self) -> Dict[str, Dict[str, str]]:
        """Load cached company URLs
        
        Returns:
            Dictionary mapping company IDs to {name, url} dictionaries
        """
        if os.path.exists(self.COMPANY_URLS_CACHE_FILE):
            try:
                with open(self.COMPANY_URLS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded {len(data)} companies from cache")
                return data
            except Exception as e:
                logger.error(f"Error loading cached company URLs: {e}", exc_info=True)
        
        return {}
    
    def _save_company_urls(self, company_urls: Dict[str, Dict[str, str]]) -> None:
        """Save company URLs to cache
        
        Args:
            company_urls: Dictionary mapping company IDs to {name, url} dictionaries
        """
        if not company_urls:
            logger.warning("No company URLs to save")
            return
            
        try:
            with open(self.COMPANY_URLS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(company_urls, f, indent=2)
            logger.info(f"Saved {len(company_urls)} companies to cache")
        except Exception as e:
            logger.error(f"Error saving company URLs: {e}", exc_info=True)
    
    def _get_fallback_company_urls(self) -> Dict[str, Dict[str, str]]:
        """Get fallback company URLs
        
        Returns:
            Dictionary mapping company IDs to {name, url} dictionaries
        """
        # Basic fallback company URLs
        fallback_urls = {
            "alexcredit": {
                "name": "Alexcredit",
                "url": "https://www.mintos.com/en/lending-companies/Alexcredit"
            },
            "creditstar": {
                "name": "Creditstar",
                "url": "https://www.mintos.com/en/lending-companies/Creditstar"
            },
            "eleving-group": {
                "name": "Eleving Group",
                "url": "https://www.mintos.com/en/lending-companies/eleving-group"
            },
            "finko": {
                "name": "FINKO",
                "url": "https://www.mintos.com/en/lending-companies/finko"
            },
            "iute-group": {
                "name": "Iute Group",
                "url": "https://www.mintos.com/en/lending-companies/iute-group"
            },
            "mogo": {
                "name": "Mogo",
                "url": "https://www.mintos.com/en/lending-companies/mogo"
            },
            "sun-finance": {
                "name": "Sun Finance",
                "url": "https://www.mintos.com/en/lending-companies/sun-finance"
            },
            "wowwo": {
                "name": "Wowwo",
                "url": "https://www.mintos.com/en/lending-companies/wowwo"
            }
        }
        
        # Try to load more from fallback mapping file
        try:
            if os.path.exists(self.FALLBACK_MAPPING_FILE):
                with open(self.FALLBACK_MAPPING_FILE, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                    
                # Extract company URLs from mapping
                for company_id, company_data in mapping.items():
                    if isinstance(company_data, dict) and 'url' in company_data:
                        fallback_urls[company_id] = {
                            'name': company_data.get('name', company_id.replace('-', ' ').title()),
                            'url': company_data['url']
                        }
        except Exception as e:
            logger.error(f"Error loading fallback mapping: {e}", exc_info=True)
        
        logger.info(f"Using fallback mapping with {len(fallback_urls)} companies")
        return fallback_urls
    
    def load_company_fallback_mapping(self) -> Dict[str, Dict[str, str]]:
        """Load company fallback mapping from JSON file
        
        This mapping provides alternative company IDs for companies that have
        been renamed or have special URL patterns.
        
        Returns:
            Dictionary mapping original company IDs to alternative IDs
        """
        fallback_mapping = {}
        
        # Try to load from fallback mapping file
        try:
            if os.path.exists(self.FALLBACK_MAPPING_FILE):
                with open(self.FALLBACK_MAPPING_FILE, 'r', encoding='utf-8') as f:
                    fallback_mapping = json.load(f)
                logger.info(f"Loaded fallback mapping with {len(fallback_mapping)} entries")
            else:
                logger.info("No fallback mapping file found")
        except Exception as e:
            logger.error(f"Error loading fallback mapping: {e}", exc_info=True)
            
        return fallback_mapping
    
    def generate_url_variations(self, company_id: str, company_name: str) -> List[str]:
        """Generate multiple URL variations for a company
        
        Args:
            company_id: The ID of the company
            company_name: The name of the company
            
        Returns:
            List of possible URLs to try
        """
        urls = []
        
        # Check fallback mapping first
        fallback_mapping = self.load_company_fallback_mapping()
        if company_id in fallback_mapping:
            mapping_data = fallback_mapping[company_id]
            
            # If direct URLs are provided, use them
            if 'direct_urls' in mapping_data and isinstance(mapping_data['direct_urls'], list):
                urls.extend(mapping_data['direct_urls'])
                logger.debug(f"Using {len(mapping_data['direct_urls'])} direct URLs from fallback mapping for {company_id}")
            
            # If alternative IDs are provided, use them
            if 'alternative_ids' in mapping_data and isinstance(mapping_data['alternative_ids'], list):
                for alt_id in mapping_data['alternative_ids']:
                    # Generate variations for alternative ID
                    urls.append(f"https://www.mintos.com/en/lending-companies/{alt_id}")
                    urls.append(f"https://www.mintos.com/en/loan-originators/{alt_id}")
                logger.debug(f"Using {len(mapping_data['alternative_ids'])} alternative IDs from fallback mapping for {company_id}")
        
        # Standard URL variations
        urls.append(f"https://www.mintos.com/en/lending-companies/{company_id}")
        urls.append(f"https://www.mintos.com/en/loan-originators/{company_id}")
        
        # Variations with different capitalization
        titlized_id = company_id.replace('-', ' ').title().replace(' ', '-')
        if titlized_id != company_id:
            urls.append(f"https://www.mintos.com/en/lending-companies/{titlized_id}")
            urls.append(f"https://www.mintos.com/en/loan-originators/{titlized_id}")
        
        # Variations with different formats
        clean_name = company_name.lower().replace(' ', '-')
        if clean_name != company_id:
            urls.append(f"https://www.mintos.com/en/lending-companies/{clean_name}")
            urls.append(f"https://www.mintos.com/en/loan-originators/{clean_name}")
        
        # Remove duplicates while preserving order
        unique_urls = []
        seen = set()
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        return unique_urls