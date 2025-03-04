"""
Document Scraper for the Mintos Telegram Bot
Handles scraping and monitoring of company document pages for presentations,
financials, and loan agreements.
"""
import os
import json
import hashlib
import logging
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Union, Tuple
import pandas as pd
import aiohttp
from bs4 import BeautifulSoup
import re

from bot.logger import setup_logger
from bot.config import (
    DATA_DIR, DOCUMENTS_FILE, DOCUMENTS_CACHE_FILE, 
    SENT_DOCUMENTS_FILE, BACKUP_SENT_DOCUMENTS_FILE,
    DOCUMENT_TYPES
)

logger = setup_logger("document_scraper")

# Don't redefine constants already imported from config.py

class DocumentScraper:
    """Scrapes and manages document information from company pages"""

    def __init__(self):
        """Initialize the document scraper"""
        self.ensure_data_directory()
        self.company_pages = {}
        self._load_company_pages()
        self.sent_documents: Set[str] = set()
        self._load_sent_documents()

    def ensure_data_directory(self) -> None:
        """Ensure data directory exists"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            logger.info(f"Created data directory: {DATA_DIR}")

    def _load_company_pages(self) -> None:
        """Load company pages from CSV file"""
        try:
            # Check both locations for the CSV file
            csv_paths = ['company_pages.csv', 'attached_assets/company_pages.csv']
            found_path = None
            
            for path in csv_paths:
                if os.path.exists(path):
                    found_path = path
                    break
            
            if found_path:
                try:
                    df = pd.read_csv(found_path)
                    
                    # Convert DataFrame to dict for easier access
                    # New format: 'Company,URL'
                    self.company_pages = {}
                    
                    for _, row in df.iterrows():
                        company_name = row.get('Company')
                        url = row.get('URL')
                        if company_name and url:
                            # Use the company name as the key
                            self.company_pages[company_name] = {
                                'name': company_name,
                                'url': url
                            }
                    
                    logger.info(f"Loaded {len(self.company_pages)} company pages from {found_path}")
                except pd.errors.EmptyDataError:
                    logger.warning(f"CSV file {found_path} is empty")
                except pd.errors.ParserError:
                    logger.warning(f"Could not parse CSV file {found_path}")
                except Exception as e:
                    logger.error(f"Error loading company pages: {e}")
            else:
                logger.warning("Company pages CSV file not found in any location")
        except Exception as e:
            logger.error(f"Error loading company pages: {e}", exc_info=True)

    def _load_sent_documents(self) -> None:
        """Load set of already sent document IDs with verification and backup"""
        try:
            if os.path.exists(SENT_DOCUMENTS_FILE):
                with open(SENT_DOCUMENTS_FILE, 'r') as f:
                    self.sent_documents = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_documents)} sent document IDs")
            else:
                # Create an empty file if it doesn't exist
                with open(SENT_DOCUMENTS_FILE, 'w') as f:
                    json.dump(list(self.sent_documents), f)
                logger.info("Created empty sent documents file")
        except Exception as e:
            logger.error(f"Error loading sent documents, attempting backup: {e}", exc_info=True)
            try:
                if os.path.exists(BACKUP_SENT_DOCUMENTS_FILE):
                    with open(BACKUP_SENT_DOCUMENTS_FILE, 'r') as f:
                        self.sent_documents = set(json.load(f))
                    logger.info(f"Loaded {len(self.sent_documents)} sent document IDs from backup")
                    # Restore from backup
                    with open(SENT_DOCUMENTS_FILE, 'w') as f:
                        json.dump(list(self.sent_documents), f)
                    logger.info("Restored sent documents file from backup")
            except Exception as backup_error:
                logger.error(f"Error loading backup sent documents: {backup_error}", exc_info=True)
                # Initialize empty set and save
                self.sent_documents = set()
                with open(SENT_DOCUMENTS_FILE, 'w') as f:
                    json.dump(list(self.sent_documents), f)
                logger.warning("Initialized empty sent documents set due to errors")

    def save_sent_document(self, document: Dict[str, Any]) -> None:
        """Mark a document as sent with backup"""
        doc_id = self._create_document_id(document)
        self.sent_documents.add(doc_id)
        
        # Save to file with backup
        try:
            # First create a backup of the current file if it exists
            if os.path.exists(SENT_DOCUMENTS_FILE):
                with open(SENT_DOCUMENTS_FILE, 'r') as f:
                    current_data = f.read()
                with open(BACKUP_SENT_DOCUMENTS_FILE, 'w') as f:
                    f.write(current_data)
            
            # Now save the updated data
            with open(SENT_DOCUMENTS_FILE, 'w') as f:
                json.dump(list(self.sent_documents), f)
            
            logger.debug(f"Saved document ID to sent documents: {doc_id}")
        except Exception as e:
            logger.error(f"Error saving sent document: {e}", exc_info=True)

    def is_document_sent(self, document: Dict[str, Any]) -> bool:
        """Check if a document has already been sent"""
        doc_id = self._create_document_id(document)
        return doc_id in self.sent_documents

    def _create_document_id(self, document: Dict[str, Any]) -> str:
        """Create a unique identifier for a document"""
        hash_content = "_".join([
            str(document.get('company_id', '')),
            str(document.get('company_name', '')),
            str(document.get('document_type', '')), 
            str(document.get('document_url', '')),
            str(document.get('document_date', ''))
        ])
        return hashlib.md5(hash_content.encode()).hexdigest()

    def get_cache_age(self) -> float:
        """Get age of cache in seconds"""
        try:
            if os.path.exists(DOCUMENTS_CACHE_FILE):
                mtime = os.path.getmtime(DOCUMENTS_CACHE_FILE)
                age_seconds = time.time() - mtime
                return age_seconds
            return float('inf')  # File doesn't exist
        except Exception as e:
            logger.error(f"Error getting cache age: {e}", exc_info=True)
            return float('inf')  # Error case

    def load_previous_documents(self) -> List[Dict[str, Any]]:
        """Load previous documents from cache file"""
        try:
            if os.path.exists(DOCUMENTS_CACHE_FILE):
                with open(DOCUMENTS_CACHE_FILE, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading previous documents: {e}", exc_info=True)
            return []

    def save_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Save documents to cache file"""
        try:
            with open(DOCUMENTS_CACHE_FILE, 'w') as f:
                json.dump(documents, f, indent=2)
            logger.info(f"Saved {len(documents)} documents to cache")
        except Exception as e:
            logger.error(f"Error saving documents: {e}", exc_info=True)

    def compare_documents(self, new_docs: List[Dict[str, Any]], prev_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare documents to find new ones"""
        if not prev_docs:
            logger.info("No previous documents to compare, considering all as new")
            return new_docs

        added_docs = []
        seen_docs = set()

        # Create lookup dictionary for previous documents
        prev_doc_dict = {}
        for doc in prev_docs:
            key = (
                doc.get('company_id', ''),
                doc.get('document_type', ''),
                doc.get('document_url', '')
            )
            prev_doc_dict[key] = doc

        # Check each new document
        for new_doc in new_docs:
            key = (
                new_doc.get('company_id', ''),
                new_doc.get('document_type', ''),
                new_doc.get('document_url', '')
            )
            
            # Mark this document as seen
            seen_docs.add(key)
            
            # If new document or date changed
            if key not in prev_doc_dict or new_doc.get('document_date') != prev_doc_dict[key].get('document_date'):
                added_docs.append(new_doc)
                logger.debug(f"New or updated document: {new_doc.get('company_name')} - {new_doc.get('document_type')}")

        # Now merge in all previous documents that weren't seen in the new documents
        # This ensures we don't lose older document history
        for doc in prev_docs:
            key = (
                doc.get('company_id', ''),
                doc.get('document_type', ''),
                doc.get('document_url', '')
            )
            if key not in seen_docs:
                new_docs.append(doc)

        logger.info(f"Found {len(added_docs)} new or updated documents")
        return added_docs

    async def extract_date_from_page(self, html_content: str) -> Optional[str]:
        """Extract document date from HTML content"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for common date patterns in the HTML
            date_patterns = [
                r'Last Updated:\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'Last Updated:\s*(\d{4}-\d{1,2}-\d{1,2})',
                r'Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'Date:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'(\d{1,2}\.\d{1,2}\.\d{4})',
                r'(\d{4}-\d{2}-\d{2})'
            ]
            
            # Try to find any span or div with "Last Updated" or similar text
            update_elements = soup.find_all(['span', 'div', 'p'], string=re.compile(r'(Last\s+Updated|Updated|Date)', re.I))
            
            for element in update_elements:
                text = element.get_text().strip()
                for pattern in date_patterns:
                    match = re.search(pattern, text)
                    if match:
                        date_str = match.group(1)
                        return self._normalize_date(date_str)
            
            # If not found in specific elements, try the whole page
            text = soup.get_text()
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    date_str = match.group(1)
                    return self._normalize_date(date_str)
                    
            return None
        except Exception as e:
            logger.error(f"Error extracting date from page: {e}", exc_info=True)
            return None

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
            logger.error(f"Error normalizing date {date_str}: {e}", exc_info=True)
            return date_str  # Return original if parsing fails

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a web page with error handling and retries"""
        if not url or url.strip() == "":
            return None
            
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=15) as response:
                        if response.status == 200:
                            return await response.text()
                        else:
                            logger.warning(f"Failed to fetch {url}, status: {response.status}")
                            return None
            except Exception as e:
                retry_num = attempt + 1
                if retry_num < max_retries:
                    logger.warning(f"Error fetching {url} (attempt {retry_num}/{max_retries}): {e}")
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.error(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                    return None
        
        return None

    async def scrape_documents(self) -> List[Dict[str, Any]]:
        """Scrape document information from company pages"""
        all_documents = []
        
        for company_id, company_data in self.company_pages.items():
            company_name = company_data.get('name', f"Unknown Company {company_id}")
            company_url = company_data.get('url', '')
            
            if not company_url:
                logger.warning(f"No URL for company {company_name}, skipping")
                continue
                
            logger.info(f"Scraping documents for {company_name}")
                
            # Fetch the company page
            logger.debug(f"Fetching company page for {company_name}: {company_url}")
            html_content = await self.fetch_page(company_url)
            
            if not html_content:
                logger.warning(f"Failed to fetch page for {company_name}")
                continue
            
            # Extract date
            document_date = await self.extract_date_from_page(html_content)
            
            if not document_date:
                document_date = datetime.now().strftime('%Y-%m-%d')
                logger.warning(f"Couldn't find date for {company_name}, using today's date")
            
            # Create document record for the company page
            document = {
                'company_id': company_id,
                'company_name': company_name,
                'title': f"{company_name} Mintos Page",
                'type': 'company_page',
                'url': company_url,
                'date': document_date,
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            all_documents.append(document)
            logger.info(f"Found company page for {company_name}, date: {document_date}")
            
            # Look for related documents on the page
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for links that might be documents
            document_keywords = ['presentation', 'financial', 'report', 'agreement', 'document', 'pdf']
            
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().lower().strip()
                
                # Skip empty links or navigation
                if not href or href.startswith('#') or len(text) < 3:
                    continue
                    
                # Check if this link might be a document based on text or URL
                is_document = any(keyword in text.lower() for keyword in document_keywords) or href.endswith('.pdf')
                
                if is_document:
                    # Make sure URL is absolute
                    if href.startswith('/'):
                        # Convert relative URL to absolute
                        base_url = "/".join(company_url.split("/")[:3])  # Get domain part
                        doc_url = f"{base_url}{href}"
                    elif not href.startswith(('http://', 'https://')):
                        # Might be relative to current path
                        doc_url = company_url.rstrip('/') + '/' + href
                    else:
                        doc_url = href
                        
                    # Determine document type based on link text or URL
                    doc_type = 'document'
                    for keyword in ['presentation', 'financial', 'report', 'agreement']:
                        if keyword in text.lower() or keyword in href.lower():
                            doc_type = keyword
                            break
                    
                    # Create document record
                    document = {
                        'company_id': company_id,
                        'company_name': company_name,
                        'title': text if text else f"{company_name} {doc_type.capitalize()}",
                        'type': doc_type,
                        'url': doc_url,
                        'date': document_date,  # Use same date as company page for now
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    all_documents.append(document)
                    logger.debug(f"Found document link: {text} ({doc_url})")
            
        return all_documents

    async def check_document_updates(self) -> List[Dict[str, Any]]:
        """Check for document updates and return new documents"""
        # Load previous documents
        previous_documents = self.load_previous_documents()
        logger.info(f"Loaded {len(previous_documents)} previous documents")
        
        # Scrape current documents
        current_documents = await self.scrape_documents()
        logger.info(f"Scraped {len(current_documents)} current documents")
        
        # Save all current documents for future comparison
        self.save_documents(current_documents)
        
        # Find new or updated documents
        new_documents = self.compare_documents(current_documents, previous_documents)
        logger.info(f"Found {len(new_documents)} new/updated documents")
        
        return new_documents