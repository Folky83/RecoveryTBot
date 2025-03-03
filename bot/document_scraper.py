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
    
    # Multiple URL patterns to try for each company
    URL_PATTERNS = [
        "https://www.mintos.com/en/lending-companies/{company_id}",
        "https://www.mintos.com/en/loan-originators/{company_id}",
        "https://www.mintos.com/en/loan-originators/{company_id}/documents",
        "https://www.mintos.com/en/lending-companies/{company_id}/documents"
    ]
    
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
        
    def get_company_documents(self, company_id: str, company_name: str) -> List[Dict[str, Any]]:
        """Get documents for a specific company
        
        Args:
            company_id: The ID of the company
            company_name: The name of the company
            
        Returns:
            List of documents for the company
        """
        logger.info(f"Fetching documents for {company_name} (ID: {company_id})")
        
        # Try multiple URL patterns
        for pattern in self.URL_PATTERNS:
            url = pattern.format(company_id=company_id)
            logger.debug(f"Trying URL pattern: {url}")
            
            html_content = self._make_request(url)
            if html_content:
                logger.info(f"Successfully fetched content from {url}")
                documents = self._parse_documents(html_content, company_name)
                if documents:
                    logger.info(f"Found {len(documents)} documents at {url}")
                    return documents
                else:
                    logger.debug(f"No documents found at {url}, trying next pattern")
        
        logger.warning(f"Could not find any documents for {company_name} after trying all URL patterns")
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
        
        for company_id, company_name in company_mapping.items():
            try:
                logger.info(f"Checking documents for {company_name}")
                
                # Get current documents
                current_documents = self.get_company_documents(company_id, company_name)
                
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