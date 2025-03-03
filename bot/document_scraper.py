"""
Document Scraper for Mintos Companies
Handles scraping and monitoring of company document pages for new documents.
"""
import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from .logger import setup_logger
from .config import (
    MAX_RETRIES,
    RETRY_DELAY,
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    DATA_DIR,
    DOCUMENTS_FILE
)

logger = setup_logger(__name__)

class DocumentScraper:
    """Scrapes and monitors company document pages for new documents"""

    def __init__(self):
        """Initialize document scraper with session"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; Mintos Monitor Bot/1.0)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })
        self.documents_data = self._load_documents_data()

    def _load_documents_data(self) -> Dict[str, Any]:
        """Load documents data from file"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            
        if os.path.exists(DOCUMENTS_FILE):
            try:
                with open(DOCUMENTS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading documents data: {str(e)}")
                # If there's an error, create a backup of the corrupted file
                if os.path.getsize(DOCUMENTS_FILE) > 0:
                    backup_file = f"{DOCUMENTS_FILE}.bak.{int(time.time())}"
                    try:
                        with open(DOCUMENTS_FILE, 'r', encoding='utf-8') as src:
                            with open(backup_file, 'w', encoding='utf-8') as dst:
                                dst.write(src.read())
                        logger.info(f"Created backup of corrupted documents file: {backup_file}")
                    except IOError as backup_error:
                        logger.error(f"Failed to create backup: {str(backup_error)}")
        
        # Return empty structure if file doesn't exist or is corrupted
        return {
            "last_check": "",
            "companies": {}
        }

    def _save_documents_data(self) -> None:
        """Save documents data to file"""
        try:
            with open(DOCUMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.documents_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved documents data to {DOCUMENTS_FILE}")
        except IOError as e:
            logger.error(f"Error saving documents data: {str(e)}")

    def _make_request(self, url: str) -> Optional[str]:
        """Make an HTTP request with retries and error handling"""
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(
                    url=url,
                    timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                logger.error(f"Document page request failed, attempt {attempt + 1}/{MAX_RETRIES}: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                continue
            except Exception as e:
                logger.error(f"Unexpected error in document page request: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                continue
        return None

    def get_company_documents(self, company_id: str, company_name: str) -> List[Dict[str, Any]]:
        """Get documents for a specific company
        
        Args:
            company_id: The ID of the company
            company_name: The name of the company
            
        Returns:
            List of documents for the company
        """
        url = f"https://www.mintos.com/en/loan-originators/{company_id}/"
        html_content = self._make_request(url)
        
        if not html_content:
            logger.error(f"Failed to get document page for company {company_name} ({company_id})")
            return []
            
        documents = self._parse_documents(html_content, company_name)
        logger.info(f"Found {len(documents)} documents for company {company_name}")
        return documents
        
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
            
            # Try to find document sections by common class names or headings
            document_sections = []
            
            # Look for document sections with headers like "Documents", "Files", etc.
            for heading in soup.find_all(['h2', 'h3', 'h4']):
                heading_text = heading.get_text().strip().lower()
                if any(keyword in heading_text for keyword in ['document', 'report', 'file', 'statement']):
                    section = heading.find_next('div')
                    if section:
                        document_sections.append(section)
            
            # If no sections found by headers, look for common document container classes
            if not document_sections:
                document_sections = soup.select('.documents-section, .file-list, .document-list, .downloads')
            
            # If still no sections, scan the page for any link that might be a document
            if not document_sections:
                document_sections = [soup]
            
            for section in document_sections:
                links = section.find_all('a')
                for link in links:
                    href = link.get('href')
                    if not href:
                        continue
                        
                    # Check if it's likely a document link
                    if any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']):
                        title = link.get_text().strip()
                        if not title:
                            title = href.split('/')[-1]
                        
                        # Try to find date near the link
                        date_text = None
                        date_element = link.find_next('span', class_='date')
                        if date_element:
                            date_text = date_element.get_text().strip()
                        
                        if not date_text:
                            # Try other common date formats
                            parent = link.parent
                            date_candidates = parent.select('.date, .document-date, .file-date')
                            if date_candidates:
                                date_text = date_candidates[0].get_text().strip()
                        
                        # Fallback to current date if no date found
                        if not date_text:
                            date_text = datetime.now().strftime('%Y-%m-%d')
                        
                        # Ensure URL is absolute
                        if href.startswith('/'):
                            href = f"https://www.mintos.com{href}"
                        
                        documents.append({
                            'title': title,
                            'date': date_text,
                            'url': href,
                            'id': self._generate_document_id(title, href, date_text)
                        })
            
        except Exception as e:
            logger.error(f"Error parsing documents for {company_name}: {str(e)}")
        
        return documents
    
    def _generate_document_id(self, title: str, url: str, date: str) -> str:
        """Generate a unique ID for a document based on its properties
        
        Args:
            title: Document title
            url: Document URL
            date: Document date
            
        Returns:
            String identifier for the document
        """
        # Use the URL as the primary identifier as it's most likely to be unique
        # If URL contains a query string, remove it
        base_url = url.split('?')[0]
        
        # Return the last part of the URL (filename) as the ID
        # If not available, use a combination of title and date
        if '/' in base_url:
            return base_url.split('/')[-1]
        else:
            return f"{title}_{date}".replace(' ', '_')
    
    def check_all_companies(self, company_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """Check all companies for new documents
        
        Args:
            company_mapping: Dictionary mapping company IDs to names
            
        Returns:
            List of new documents detected
        """
        new_documents = []
        current_time = datetime.now().isoformat()
        
        for company_id, company_name in company_mapping.items():
            try:
                # Skip companies that don't have a valid ID (needs to be a slug for URL)
                if not company_id or not isinstance(company_id, str):
                    logger.warning(f"Skipping company with invalid ID: {company_name} ({company_id})")
                    continue
                    
                documents = self.get_company_documents(company_id, company_name)
                
                # Initialize this company in our data structure if it doesn't exist
                if company_id not in self.documents_data["companies"]:
                    self.documents_data["companies"][company_id] = {
                        "name": company_name,
                        "documents": {},
                        "last_check": current_time
                    }
                
                # Get set of existing document IDs
                existing_document_ids = set(self.documents_data["companies"][company_id]["documents"].keys())
                
                # Check for new documents
                for document in documents:
                    doc_id = document["id"]
                    
                    if doc_id not in existing_document_ids:
                        # This is a new document
                        new_documents.append({
                            "company_id": company_id,
                            "company_name": company_name,
                            "document": document
                        })
                        
                        # Add to our data structure
                        self.documents_data["companies"][company_id]["documents"][doc_id] = {
                            "title": document["title"],
                            "date": document["date"],
                            "url": document["url"],
                            "discovered": current_time
                        }
                
                # Update last check time
                self.documents_data["companies"][company_id]["last_check"] = current_time
                
                # Add a small delay between requests to avoid overloading the server
                time.sleep(REQUEST_DELAY)
                
            except Exception as e:
                logger.error(f"Error checking documents for {company_name}: {str(e)}")
        
        # Update overall last check time
        self.documents_data["last_check"] = current_time
        
        # Save updated data
        self._save_documents_data()
        
        logger.info(f"Completed document check. Found {len(new_documents)} new documents.")
        return new_documents