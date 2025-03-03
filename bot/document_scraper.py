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
            
    def _make_request(self, url: str) -> Optional[str]:
        """Make an HTTP request with retries and error handling"""
        max_retries = 3
        retry_delay = 2
        
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
        """Fetch company URLs from the Mintos website or API
        
        Returns:
            Dictionary mapping company IDs to {name, url} dictionaries
        """
        logger.info("Fetching company information from Mintos")
        company_urls = {}
        
        # Try direct API endpoints first - these might provide reliable data
        api_endpoints = [
            "https://www.mintos.com/api/en/loan-originators/",  # API endpoint for loan originators
            "https://www.mintos.com/api/en/lending-companies/",  # Alternative API endpoint
        ]
        
        # Try API endpoints first
        for endpoint in api_endpoints:
            try:
                logger.info(f"Trying API endpoint: {endpoint}")
                response = self.session.get(endpoint, timeout=self.REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    try:
                        # Try to parse JSON response
                        data = response.json()
                        logger.info(f"Successfully fetched data from API: {endpoint}")
                        
                        # API might return data in different formats, try to handle common ones
                        if isinstance(data, list):
                            # List of companies
                            for company in data:
                                if isinstance(company, dict):
                                    company_id = company.get('id') or company.get('slug')
                                    company_name = company.get('name')
                                    company_url = company.get('url')
                                    
                                    if company_id and company_name:
                                        # Use slug ID if available, otherwise use name-based ID
                                        company_id = str(company_id)
                                        
                                        # Create URL if not provided
                                        if not company_url:
                                            company_url = f"https://www.mintos.com/en/loan-originators/{company_id}"
                                            
                                        company_urls[company_id] = {
                                            'name': company_name,
                                            'url': company_url
                                        }
                                        logger.debug(f"Added company from API: {company_name} ({company_id})")
                                        
                        elif isinstance(data, dict):
                            # Data might be in {'companies': [...]} format
                            for key in ['companies', 'lenders', 'loan_originators', 'data', 'items']:
                                if key in data and isinstance(data[key], list):
                                    for company in data[key]:
                                        if isinstance(company, dict):
                                            company_id = company.get('id') or company.get('slug')
                                            company_name = company.get('name')
                                            company_url = company.get('url')
                                            
                                            if company_id and company_name:
                                                company_id = str(company_id)
                                                
                                                # Create URL if not provided
                                                if not company_url:
                                                    company_url = f"https://www.mintos.com/en/loan-originators/{company_id}"
                                                    
                                                company_urls[company_id] = {
                                                    'name': company_name,
                                                    'url': company_url
                                                }
                                                logger.debug(f"Added company from API nested data: {company_name} ({company_id})")
                    except ValueError:
                        logger.warning(f"API response was not valid JSON: {endpoint}")
                
                if company_urls:
                    logger.info(f"Successfully fetched {len(company_urls)} companies from API")
                    return company_urls
                    
            except Exception as e:
                logger.error(f"Error fetching from API endpoint {endpoint}: {e}")
                
        # Fallback to web scraping approach if API didn't work
        logger.info("API approach didn't yield results, falling back to web scraping")
        
        # Known URL patterns for loan originators - based on our test results
        # We confirmed wowwo works with this pattern
        url_patterns = {
            'wowwo': 'https://www.mintos.com/en/loan-originators/wowwo/',
            'iuvo': 'https://www.mintos.com/en/loan-originators/iuvo/',
            'iuvo-group': 'https://www.mintos.com/en/loan-originators/iuvo-group/',
            'creditstar': 'https://www.mintos.com/en/loan-originators/creditstar/',
            'creditstar-group': 'https://www.mintos.com/en/loan-originators/creditstar-group/',
            'delfin-group': 'https://www.mintos.com/en/loan-originators/delfin-group/',
            'novaloans': 'https://www.mintos.com/en/loan-originators/novaloans/',
            'kviku': 'https://www.mintos.com/en/loan-originators/kviku/',
            'placet-group': 'https://www.mintos.com/en/loan-originators/placet-group/',
            'placet': 'https://www.mintos.com/en/lending-companies/placet/',
            
            # Add more company IDs based on the test that worked
            'capitalia': 'https://www.mintos.com/en/loan-originators/capitalia/',
            'eleving-group': 'https://www.mintos.com/en/loan-originators/eleving-group/',
            'credius': 'https://www.mintos.com/en/loan-originators/credius/',
            'sun-finance': 'https://www.mintos.com/en/loan-originators/sun-finance/',
            'mikro-kapital': 'https://www.mintos.com/en/loan-originators/mikro-kapital/',
            'ims': 'https://www.mintos.com/en/loan-originators/ims/',
            'akulaku': 'https://www.mintos.com/en/loan-originators/akulaku/',
            'jet-finance': 'https://www.mintos.com/en/loan-originators/jet-finance/',
            'credissimo': 'https://www.mintos.com/en/loan-originators/credissimo/',
            'cash-credit': 'https://www.mintos.com/en/loan-originators/cash-credit/',
            'monego': 'https://www.mintos.com/en/loan-originators/monego/',
            'axcess': 'https://www.mintos.com/en/loan-originators/axcess/',
        }
        
        # Add these known companies to our results
        for company_id, url in url_patterns.items():
            company_name = company_id.replace('-', ' ').title()
            company_urls[company_id] = {
                'name': company_name,
                'url': url
            }
            logger.debug(f"Added company from known patterns: {company_name} ({company_id})")
        
        # Try to scrape the web pages as a last resort
        web_urls = [
            "https://www.mintos.com/en/loan-originators/",  # Main loan originators page
            "https://www.mintos.com/en/lending-companies/",  # New lending companies page
            "https://www.mintos.com/en/investing/current-loan-originators/",
            "https://www.mintos.com/en/investing/suspended-loan-originators/",
            "https://www.mintos.com/en/investing/"  # Main investing page that might list companies
        ]
        
        for url in web_urls:
            try:
                logger.info(f"Trying to scrape company information from: {url}")
                html_content = self._make_request(url)
                if not html_content:
                    continue
                    
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Look for company links in different HTML structures
                for link in soup.find_all('a'):
                    href = link.get('href', '')
                    if not href:
                        continue
                    
                    # Convert relative URL to absolute
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = f"https://www.mintos.com{href}"
                        else:
                            href = f"https://www.mintos.com/{href}"
                    
                    # Check if it looks like a loan originator URL
                    if '/loan-originators/' in href or '/lending-companies/' in href:
                        # Extract company ID from URL
                        path_parts = href.rstrip('/').split('/')
                        company_id = path_parts[-1]
                        
                        # Skip if not a valid company page
                        if (company_id in ['loan-originators', 'lending-companies'] or
                            not company_id or
                            '?' in company_id or
                            company_id.isdigit()):
                            continue
                        
                        # Get name from link text or fallback to ID
                        company_name = link.get_text(strip=True)
                        if not company_name or len(company_name) < 2:
                            company_name = company_id.replace('-', ' ').title()
                        
                        # Add to our results if not already present
                        if company_id not in company_urls:
                            company_urls[company_id] = {
                                'name': company_name,
                                'url': href
                            }
                            logger.debug(f"Added company from web scraping: {company_name} ({company_id})")
                
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}", exc_info=True)
        
        logger.info(f"Found {len(company_urls)} total company URLs")
        return company_urls
            
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
        
        if company_url:
            # If we have a direct URL, use it
            logger.debug(f"Using provided company URL: {company_url}")
            html_content = self._make_request(company_url)
            if html_content:
                logger.info(f"Successfully fetched content from {company_url}")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {company_url}")
                    return documents
                    
                # If no documents found on the main page, try to find a documents subpage
                if '/' in company_url:
                    base_url = '/'.join(company_url.split('/')[:-1])
                    documents_url = f"{base_url}/documents"
                    logger.debug(f"Trying documents subpage: {documents_url}")
                    
                    html_content = self._make_request(documents_url)
                    if html_content:
                        logger.info(f"Successfully fetched content from {documents_url}")
                        documents = self._parse_documents(html_content, company_name)
                        if documents:
                            logger.info(f"Found {len(documents)} documents at {documents_url}")
                            return documents
        
        # Fallback to common URL patterns if we don't have a URL or it didn't work
        common_patterns = [
            f"https://www.mintos.com/en/lending-companies/{company_id}",
            f"https://www.mintos.com/en/lending-companies/{company_id}/documents",
            f"https://www.mintos.com/en/loan-originators/{company_id}",
            f"https://www.mintos.com/en/loan-originators/{company_id}/documents"
        ]
        
        for url in common_patterns:
            logger.debug(f"Trying fallback URL: {url}")
            
            html_content = self._make_request(url)
            if html_content:
                logger.info(f"Successfully fetched content from {url}")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {url}")
                    return documents
                else:
                    logger.debug(f"No documents found at {url}, trying next pattern")
        
        logger.warning(f"Could not find any documents for {company_name} after trying all URLs")
        return []
        
    def _parse_documents(self, html_content: str, company_name: str) -> List[Dict[str, Any]]:
        """Parse HTML to extract documents
        
        Args:
            html_content: HTML content of the company page
            company_name: Name of the company for logging
            
        Returns:
            List of document dictionaries with title, date, url
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
            for element in soup.find_all(class_=lambda c: c and 'document' in c.lower()):
                document_sections.append(element)
                
            # Option 6: Look for download sections
            download_sections = soup.find_all(class_=lambda c: c and ('download' in c.lower() or 'pdf' in c.lower()))
            if download_sections:
                document_sections.extend(download_sections)
                
            if not document_sections:
                logger.warning(f"No document section found for {company_name}, falling back to PDF link search")
                # Fallback: Look for any PDF links throughout the page
                pdf_links = soup.find_all('a', href=lambda href: href and href.lower().endswith('.pdf'))
                
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
                            title = filename.replace('-', ' ').replace('_', ' ').replace('.pdf', '')
                            
                        # Extract date or use current date
                        date = datetime.now().strftime("%Y-%m-%d")
                        
                        # Create document entry
                        doc_id = self._generate_document_id(title, url, date)
                        document = {
                            'title': title,
                            'url': url,
                            'date': date,
                            'id': doc_id,
                            'company_name': company_name
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
                    {'tag': 'a', 'href': lambda href: href and href.lower().endswith('.pdf')}
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
                        
                        # Skip if not a PDF (to avoid menu links, etc.)
                        if not url.lower().endswith('.pdf'):
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
                            title = filename.replace('-', ' ').replace('_', ' ').replace('.pdf', '')
                                
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
                            
                        # Create document entry
                        doc_id = self._generate_document_id(title, url, date)
                        document = {
                            'title': title,
                            'url': url,
                            'date': date,
                            'id': doc_id,
                            'company_name': company_name
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