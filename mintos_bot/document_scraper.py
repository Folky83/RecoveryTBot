#!/usr/bin/env python3
"""
Document Scraper for the Mintos Telegram Bot
Handles scraping and monitoring of company document pages for presentations,
financials, and loan agreements.
"""
import os
import json
import logging
import asyncio
import aiohttp
import re
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Set
from bs4 import BeautifulSoup, Tag
import pandas as pd

from .constants import (
    DATA_DIR, DOCUMENTS_CACHE_FILE, SENT_DOCUMENTS_FILE, SENT_DOCUMENTS_BACKUP,
    COMPANY_PAGES_CSV, DOCUMENT_TYPES, MAX_HTTP_RETRIES, HTTP_RETRY_DELAY,
    HTTP_CLIENT_TIMEOUT, DEFAULT_USER_AGENT, DOCUMENT_CACHE_TTL
)
from .config import PROXY_HOST, PROXY_AUTH, USE_PROXY
from .utils import safe_get_text, safe_get_attribute, safe_find, safe_find_all, FileBackupManager, create_unique_id

# Configure logging
logger = logging.getLogger(__name__)

class DocumentScraper:
    """Scrapes and manages document information from company pages"""

    def __init__(self):
        """Initialize the document scraper"""
        self.data_dir = DATA_DIR
        self.documents_cache_file = DOCUMENTS_CACHE_FILE
        self.sent_documents_file = SENT_DOCUMENTS_FILE
        self.sent_documents_backup_file = SENT_DOCUMENTS_BACKUP
        self.document_types = DOCUMENT_TYPES
        
        # Company pages mapping
        self.company_pages = []
        
        # Set of document IDs that have already been sent
        self.sent_documents: Set[str] = set()
        
        # Ensure data directory exists
        self.ensure_data_directory()
        
        # Load company pages
        self._load_company_pages()
        
        # Load sent documents
        self._load_sent_documents()

    def ensure_data_directory(self) -> None:
        """Ensure data directory exists"""
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_company_pages(self) -> None:
        """Load company pages from CSV file"""
        try:
            # Try package data first, then local file
            csv_path = self._find_data_file('company_pages.csv', COMPANY_PAGES_CSV)
            if csv_path and os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                self.company_pages = df.to_dict('records')
                logger.info(f"Loaded {len(self.company_pages)} company pages from {csv_path}")
            else:
                logger.error(f"Company pages CSV file not found: {COMPANY_PAGES_CSV}")
                self.company_pages = []
        except Exception as e:
            logger.error(f"Error loading company pages: {e}")
            self.company_pages = []

    def _find_data_file(self, package_filename: str, fallback_path: str) -> str:
        """Find data file in package or fallback to local path"""
        try:
            # Try to find in package data
            import mintos_bot
            package_dir = os.path.dirname(mintos_bot.__file__)
            package_data_path = os.path.join(package_dir, 'data', package_filename)
            
            if os.path.exists(package_data_path):
                return package_data_path
        except Exception:
            pass
        
        # Fallback to local path
        return fallback_path

    def _load_sent_documents(self) -> None:
        """Load set of already sent document IDs with verification and backup"""
        try:
            # Try to load the main file
            if os.path.exists(self.sent_documents_file):
                with open(self.sent_documents_file, 'r', encoding='utf-8') as f:
                    self.sent_documents = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_documents)} sent document IDs")
                return
                
            # If main file doesn't exist, try backup
            if os.path.exists(self.sent_documents_backup_file):
                with open(self.sent_documents_backup_file, 'r', encoding='utf-8') as f:
                    self.sent_documents = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_documents)} sent document IDs from backup")
                # Save to main file
                with open(self.sent_documents_file, 'w', encoding='utf-8') as f:
                    json.dump(list(self.sent_documents), f)
                return
                
        except Exception as e:
            logger.error(f"Error loading sent documents: {e}")
            
        # If we get here, either there was an error or files don't exist
        # Start with an empty set
        self.sent_documents = set()
        logger.warning("Starting with empty sent documents set")
        
        # Create both files for future use
        try:
            with open(self.sent_documents_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.sent_documents), f)
            with open(self.sent_documents_backup_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.sent_documents), f)
        except Exception as e:
            logger.error(f"Error creating sent documents files: {e}")

    def save_sent_document(self, document: Dict[str, Any]) -> None:
        """Mark a document as sent with backup and timestamp"""
        try:
            # Create document ID
            doc_id = self._create_document_id(document)
            
            # Add to set
            self.sent_documents.add(doc_id)
            
            # Load existing data to add timestamps
            sent_data = []
            try:
                with open(self.sent_documents_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    # Convert simple list to dict format if needed
                    sent_data = [entry if isinstance(entry, dict) else {'id': entry} for entry in existing_data]
            except (FileNotFoundError, json.JSONDecodeError):
                pass
                
            # Add or update entry with timestamp
            now = time.time()
            updated = False
            for entry in sent_data:
                if entry.get('id') == doc_id:
                    entry['timestamp'] = now
                    updated = True
                    break
            
            if not updated:
                sent_data.append({'id': doc_id, 'timestamp': now})
            
            # Save to both files
            for file_path in [self.sent_documents_file, self.sent_documents_backup_file]:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(sent_data, f)
                
            logger.debug(f"Marked document as sent: {doc_id}")
            
        except Exception as e:
            logger.error(f"Error saving sent document: {e}")

    def is_document_sent(self, document: Dict[str, Any]) -> bool:
        """Check if a document has already been sent on the same day"""
        try:
            doc_id = self._create_document_id(document)
            
            # Quick check if not in sent documents at all
            if doc_id not in self.sent_documents:
                return False
                
            # Now check when it was last sent
            try:
                with open(self.sent_documents_file, 'r', encoding='utf-8') as f:
                    sent_data = json.load(f)
                    
                # Get timestamp if available
                for entry in sent_data:
                    if isinstance(entry, dict) and entry.get('id') == doc_id:
                        last_sent = entry.get('timestamp', 0)
                        
                        # If we have a timestamp, check if it was today
                        if last_sent > 0:
                            last_sent_date = time.strftime("%Y-%m-%d", time.localtime(last_sent))
                            current_date = time.strftime("%Y-%m-%d")
                            
                            # Don't resend if it was sent today
                            if last_sent_date == current_date:
                                logger.info(f"Document {doc_id} already sent today ({current_date}), skipping")
                                return True
                            
                            # If it wasn't sent today, can resend
                            logger.info(f"Document {doc_id} was sent on {last_sent_date}, can send again today")
                            return False
                        
                # If we reach here with no timestamp, assume it was sent recently
                return True
                
            except Exception as e:
                logger.error(f"Error checking document sent timestamp: {e}")
                # Default to treating as sent if we can't verify
                return True
                
        except Exception as e:
            logger.error(f"Error checking if document sent: {e}")
            return False

    def _create_document_id(self, document: Dict[str, Any]) -> str:
        """Create a unique identifier for a document"""
        try:
            # Use company name, document type, and URL
            company = document.get('company_name', '')
            doc_type = document.get('type', '')
            url = document.get('url', '')
            
            # Create a unique ID
            return f"{company}_{doc_type}_{url}"
        except Exception as e:
            logger.error(f"Error creating document ID: {e}")
            return ""

    def get_cache_age(self) -> float:
        """Get age of cache in seconds"""
        try:
            if os.path.exists(self.documents_cache_file):
                modified_time = os.path.getmtime(self.documents_cache_file)
                current_time = datetime.now().timestamp()
                return current_time - modified_time
            return float('inf')  # If file doesn't exist, return infinity
        except Exception as e:
            logger.error(f"Error getting cache age: {e}")
            return float('inf')

    def load_previous_documents(self) -> List[Dict[str, Any]]:
        """Load previous documents from cache file"""
        try:
            if os.path.exists(self.documents_cache_file):
                with open(self.documents_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading previous documents: {e}")
            return []

    def save_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Save documents to cache file"""
        try:
            with open(self.documents_cache_file, 'w', encoding='utf-8') as f:
                json.dump(documents, f, indent=2)
            logger.debug(f"Saved {len(documents)} documents to cache")
        except Exception as e:
            logger.error(f"Error saving documents: {e}")

    def compare_documents(self, new_docs: List[Dict[str, Any]], prev_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare documents to find new ones"""
        try:
            # Create a dictionary of previous documents for faster lookup
            prev_dict = {}
            for doc in prev_docs:
                key = f"{doc.get('company_name', '')}_{doc.get('type', '')}_{doc.get('url', '')}"
                prev_dict[key] = doc
            
            # Find new or updated documents
            new_documents = []
            for doc in new_docs:
                key = f"{doc.get('company_name', '')}_{doc.get('type', '')}_{doc.get('url', '')}"
                
                # Check if this is a new document or has an updated date
                if key not in prev_dict or doc.get('date') != prev_dict[key].get('date'):
                    # Only include if not already sent
                    if not self.is_document_sent(doc):
                        new_documents.append(doc)
            
            logger.info(f"Found {len(new_documents)} new documents")
            return new_documents
        except Exception as e:
            logger.error(f"Error comparing documents: {e}")
            return []

    async def extract_date_from_page(self, html_content: str) -> Optional[str]:
        """Extract document date from HTML content"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            today = datetime.now().strftime('%Y-%m-%d')
            
            # First, try to find the most reliable indicator - table cell with "Last Updated" label
            last_updated_cells = soup.find_all('td', attrs={'data-label': 'Last Updated'})
            if last_updated_cells:
                for cell in last_updated_cells:
                    date_text = cell.get_text().strip()
                    if date_text:
                        logger.debug(f"Found 'Last Updated' cell with date: {date_text}")
                        return self._normalize_date(date_text)
            
            # Next, try to find any span, div, or p element containing the text "Last Updated"
            update_elements = soup.find_all(['span', 'div', 'p'], string=re.compile(r'(Last\s+Updated|Updated|Date)', re.I))
            
            # Look for common date patterns in these elements
            date_patterns = [
                r'Last Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'Last Updated:?\s*(\d{4}-\d{1,2}-\d{1,2})',
                r'Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'Updated:?\s*(\d{4}-\d{1,2}-\d{1,2})',
                r'Date:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'Date:?\s*(\d{4}-\d{1,2}-\d{1,2})'
            ]
            
            for element in update_elements:
                text = element.get_text().strip()
                for pattern in date_patterns:
                    match = re.search(pattern, text)
                    if match:
                        date_str = match.group(1)
                        normalized_date = self._normalize_date(date_str)
                        logger.debug(f"Found date in element text: {date_str} -> {normalized_date}")
                        return normalized_date
            
            # As a last resort, search for date patterns in the entire page text
            text = soup.get_text()
            general_date_patterns = [
                r'(\d{1,2}\.\d{1,2}\.\d{4})',
                r'(\d{4}-\d{2}-\d{2})',
                r'(\d{1,2}/\d{1,2}/\d{4})'
            ]
            
            for pattern in general_date_patterns:
                match = re.search(pattern, text)
                if match:
                    date_str = match.group(1)
                    normalized_date = self._normalize_date(date_str)
                    logger.debug(f"Found date in page text: {date_str} -> {normalized_date}")
                    return normalized_date
                    
            logger.warning("No date found in page, using today's date")
            return today
        except Exception as e:
            logger.error(f"Error extracting date from page: {e}")
            return datetime.now().strftime('%Y-%m-%d')

    def _normalize_date(self, date_str: str) -> str:
        """
        Normalize various date formats to YYYY-MM-DD format.
        Handles formats like DD.MM.YYYY, DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, etc.
        """
        try:
            # First, detect the format
            if re.match(r'\d{4}-\d{1,2}-\d{1,2}', date_str):
                # Already in YYYY-MM-DD format
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            elif re.match(r'\d{1,2}\.\d{1,2}\.\d{4}', date_str):
                # DD.MM.YYYY format
                date_obj = datetime.strptime(date_str, '%d.%m.%Y')
            elif re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                # Try MM/DD/YYYY first (common in US)
                try:
                    date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                except ValueError:
                    # If that fails, try DD/MM/YYYY (common in Europe)
                    date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            elif re.match(r'\d{1,2}\.\d{1,2}\.\d{2}', date_str):
                # DD.MM.YY format
                date_obj = datetime.strptime(date_str, '%d.%m.%y')
            elif re.match(r'\d{1,2}/\d{1,2}/\d{2}', date_str):
                # Try MM/DD/YY first
                try:
                    date_obj = datetime.strptime(date_str, '%m/%d/%y')
                except ValueError:
                    # If that fails, try DD/MM/YY
                    date_obj = datetime.strptime(date_str, '%d/%m/%y')
            else:
                # Fallback - return original string if format not recognized
                logger.warning(f"Unknown date format: {date_str}")
                return date_str
                    
            # Convert to standardized format
            return date_obj.strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(f"Error normalizing date {date_str}: {e}")
            return date_str  # Return original if parsing fails

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a web page with error handling and retries"""
        headers = {
            'User-Agent': DEFAULT_USER_AGENT
        }
        
        # Configure connector
        connector_kwargs = {}
        if USE_PROXY and PROXY_HOST and PROXY_AUTH:
            logger.debug(f"Using proxy for document scraping: {PROXY_HOST}")
        
        for attempt in range(MAX_HTTP_RETRIES):
            try:
                connector = aiohttp.TCPConnector(**connector_kwargs)
                async with aiohttp.ClientSession(timeout=HTTP_CLIENT_TIMEOUT, connector=connector) as session:
                    # Configure proxy if enabled
                    proxy = None
                    if USE_PROXY and PROXY_HOST and PROXY_AUTH:
                        proxy = f'http://{PROXY_AUTH}@{PROXY_HOST}'
                    
                    async with session.get(url, headers=headers, proxy=proxy) as response:
                        if response.status == 200:
                            return await response.text()
                        else:
                            logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Error fetching {url} (attempt {attempt+1}/{MAX_HTTP_RETRIES}): {e}")
                
            # Wait before retrying (except on last attempt)
            if attempt < MAX_HTTP_RETRIES - 1:
                await asyncio.sleep(HTTP_RETRY_DELAY)
                
        logger.error(f"Failed to fetch {url} after {MAX_HTTP_RETRIES} attempts")
        return None

    async def scrape_documents(self) -> List[Dict[str, Any]]:
        """Scrape document information from company pages"""
        all_documents = []
        
        # Process in batches to avoid timeouts
        batch_size = 10
        
        for i in range(0, len(self.company_pages), batch_size):
            batch = self.company_pages[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(self.company_pages) + batch_size - 1)//batch_size}: {len(batch)} companies")
            
            # Create tasks for this batch
            tasks = []
            for company in batch:
                company_name = company['Company']
                url = company['URL']
                task = self._process_company(company_name, url)
                tasks.append(task)
            
            # Run tasks concurrently
            batch_results = await asyncio.gather(*tasks)
            
            # Add results to all_documents
            for result in batch_results:
                if result:
                    all_documents.extend(result)
            
            # Sleep briefly between batches to avoid overwhelming the server
            await asyncio.sleep(1)
        
        logger.info(f"Scraped {len(all_documents)} documents from {len(self.company_pages)} companies")
        return all_documents

    async def _process_company(self, company_name: str, url: str) -> List[Dict[str, Any]]:
        """Process a single company page and extract document information"""
        try:
            logger.debug(f"Processing company: {company_name}")
            
            # Fetch the company page
            html_content = await self.fetch_page(url)
            if not html_content:
                logger.error(f"Failed to fetch page for {company_name}")
                return []
            
            # Extract page date
            page_date = await self.extract_date_from_page(html_content)
            logger.debug(f"Page date for {company_name}: {page_date}")
            
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract documents
            documents = []
            
            # Look for exact matches first (most reliable)
            for doc_type in self.document_types:
                doc_type_display = doc_type.replace('_', ' ').title()
                
                # Find links with matching text
                for link in soup.find_all('a', href=True):
                    link_text = safe_get_text(link)
                    href = safe_get_attribute(link, 'href')
                    
                    if link_text.lower() == doc_type_display.lower() and href.endswith('.pdf'):
                        logger.debug(f"Found exact match for {doc_type}: {href}")
                        
                        # Try to extract date from context
                        specific_date = None
                        parent = link.parent
                        
                        # Look for dates in parent elements
                        for _ in range(3):  # Look up to 3 levels up
                            if parent:
                                parent_text = parent.get_text()
                                for pattern in [
                                    r'Last Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                                    r'Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                                    r'Date:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                                    r'(\d{1,2}\.\d{1,2}\.\d{4})',
                                    r'(\d{4}-\d{2}-\d{2})'
                                ]:
                                    match = re.search(pattern, parent_text)
                                    if match:
                                        specific_date = self._normalize_date(match.group(1))
                                        break
                                parent = parent.parent
                                if specific_date:
                                    break
                        
                        # Make sure we have an absolute URL
                        if not href.startswith('http'):
                            href = f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                        
                        # Create document entry
                        doc = {
                            'company_name': company_name,
                            'type': doc_type,
                            'title': link_text,
                            'url': href,
                            'company_page_url': url,
                            'date': specific_date if specific_date else page_date
                        }
                        
                        documents.append(doc)
                        break  # Found this document type, move to next
            
            # If we haven't found all document types, try other strategies
            found_types = {doc['type'] for doc in documents}
            missing_types = set(self.document_types) - found_types
            
            if missing_types:
                # Try the document container approach - look for sections with multiple document types
                card_containers = soup.find_all('div')
                for container in card_containers:
                    # Check if this is likely a document container
                    container_text = container.get_text().lower()
                    matches = 0
                    for doc_type in self.document_types:
                        doc_text = doc_type.replace('_', ' ').lower()
                        if doc_text in container_text:
                            matches += 1
                    
                    # If this container mentions multiple document types, extract PDF links
                    if matches >= 2:
                        # Look for links to PDF files
                        pdf_links = container.find_all('a', href=lambda h: h and h.lower().endswith('.pdf'))
                        
                        # Try to match links to document types
                        for link in pdf_links:
                            link_text = link.get_text().strip()
                            href = link.get('href', '')
                            
                            # Find which document type this matches
                            matched_type = None
                            for doc_type in missing_types:
                                doc_text = doc_type.replace('_', ' ').lower()
                                if doc_text == link_text.lower() or doc_text in link_text.lower():
                                    matched_type = doc_type
                                    break
                            
                            if matched_type:
                                # Make sure we have an absolute URL
                                if not href.startswith(('http://', 'https://')):
                                    if href.startswith('/'):
                                        href = f"https://www.mintos.com{href}"
                                    else:
                                        href = f"https://www.mintos.com/{href}"
                                
                                # Create document entry
                                doc = {
                                    'company_name': company_name,
                                    'type': matched_type,
                                    'title': link_text,
                                    'url': href,
                                    'company_page_url': url,
                                    'date': page_date  # Use page date as we don't have a specific one
                                }
                                
                                documents.append(doc)
                                missing_types.remove(matched_type)
                                
                                # Break if we've found all document types
                                if not missing_types:
                                    break
            
            logger.info(f"Found {len(documents)}/{len(self.document_types)} document types for {company_name}")
            for doc in documents:
                logger.debug(f"  - {doc['type']}: {doc['title']} ({doc['date']})")
            
            return documents
            
        except Exception as e:
            logger.error(f"Error processing company {company_name}: {e}")
            return []

    async def check_document_updates(self) -> List[Dict[str, Any]]:
        """Check for document updates and return new documents"""
        try:
            # Load previous documents
            previous_documents = self.load_previous_documents()
            logger.info(f"Loaded {len(previous_documents)} previous documents")
            
            # Scrape current documents
            current_documents = await self.scrape_documents()
            
            # Save current documents to cache
            self.save_documents(current_documents)
            
            # Compare to find new documents
            new_documents = self.compare_documents(current_documents, previous_documents)
            
            return new_documents
            
        except Exception as e:
            logger.error(f"Error checking document updates: {e}")
            return []