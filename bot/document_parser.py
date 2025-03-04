"""
Document Parser for Mintos Companies
Handles parsing HTML content for documents from company pages.
"""
import hashlib
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from bs4 import BeautifulSoup, Tag

from .logger import setup_logger

logger = setup_logger(__name__)

class DocumentParser:
    """Parses HTML content to extract document information"""
    
    def parse_documents(self, html_content: str, company_name: str) -> List[Dict[str, Any]]:
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
        
        if not html_content:
            logger.warning(f"No HTML content provided for {company_name}")
            return documents
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # STAGE 1: Look for direct document links with document extensions
            documents.extend(self._extract_direct_document_links(soup, company_name))
            
            # STAGE 2: Look for document sections by class names and common patterns
            documents.extend(self._extract_document_sections(soup, company_name))
            
            # STAGE 3: Look for country-specific sections
            documents.extend(self._extract_country_sections(soup, company_name))
            
            # STAGE 4: Look for tables that might contain documents
            documents.extend(self._extract_document_tables(soup, company_name))
            
            # STAGE 5: If no documents found, search the entire page for document links
            if not documents:
                documents.extend(self._extract_fallback_document_links(soup, company_name))
            
            # Add unique IDs and enhance metadata
            processed_documents = []
            seen_ids = set()
            
            for doc in documents:
                # Skip empty documents
                if not doc.get('title') or not doc.get('url'):
                    continue
                
                # Generate a unique ID based on title, url, and date
                doc_id = self.generate_document_id(
                    doc.get('title', ''), 
                    doc.get('url', ''), 
                    doc.get('date', '')
                )
                
                # Skip duplicates
                if doc_id in seen_ids:
                    continue
                
                seen_ids.add(doc_id)
                doc['id'] = doc_id
                
                # Add document type if missing
                if 'document_type' not in doc:
                    doc['document_type'] = self.detect_document_type(doc.get('title', ''), doc.get('url', ''))
                
                # Add country info if missing
                if 'country_info' not in doc:
                    doc['country_info'] = self.detect_country_info(doc.get('title', ''), doc.get('url', ''))
                
                processed_documents.append(doc)
            
            logger.info(f"Extracted {len(processed_documents)} unique documents for {company_name}")
            return processed_documents
            
        except Exception as e:
            logger.error(f"Error parsing documents for {company_name}: {e}", exc_info=True)
            return documents
    
    def _extract_direct_document_links(self, soup: BeautifulSoup, company_name: str) -> List[Dict[str, Any]]:
        """Extract direct document links with document extensions
        
        Args:
            soup: BeautifulSoup object
            company_name: Name of the company
            
        Returns:
            List of document dictionaries
        """
        documents = []
        doc_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
        
        try:
            # Find all links that might be documents
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Check if link has a document extension
                if any(href.lower().endswith(ext) for ext in doc_extensions):
                    title = link.get_text().strip()
                    
                    # Skip empty titles
                    if not title:
                        continue
                    
                    # Look for date near the link
                    date = self._extract_date_near_element(link)
                    
                    documents.append({
                        'title': title,
                        'url': href,
                        'date': date or 'Unknown',
                        'document_type': self.detect_document_type(title, href),
                        'country_info': self.detect_country_info(title, href)
                    })
            
            logger.debug(f"Found {len(documents)} direct document links for {company_name}")
        except Exception as e:
            logger.error(f"Error extracting direct document links for {company_name}: {e}", exc_info=True)
        
        return documents
    
    def _extract_document_sections(self, soup: BeautifulSoup, company_name: str) -> List[Dict[str, Any]]:
        """Extract documents from sections with document-related class names
        
        Args:
            soup: BeautifulSoup object
            company_name: Name of the company
            
        Returns:
            List of document dictionaries
        """
        documents = []
        
        try:
            # Common class names for document sections
            document_section_selectors = [
                '.documents', '.document-list', '.files', '.file-list', 
                '.downloads', '.download-list', '.reports', '.report-list',
                '[class*="document"]', '[class*="report"]', '[class*="file"]',
                '[id*="document"]', '[id*="report"]', '[id*="file"]'
            ]
            
            # Try each selector
            for selector in document_section_selectors:
                sections = soup.select(selector)
                
                for section in sections:
                    # Find all links in this section
                    links = section.find_all('a', href=True)
                    
                    for link in links:
                        href = link['href']
                        title = link.get_text().strip()
                        
                        # Skip empty titles or navigation links
                        if not title or title.lower() in ['home', 'back', 'next', 'previous']:
                            continue
                        
                        # Look for date near the link
                        date = self._extract_date_near_element(link)
                        
                        documents.append({
                            'title': title,
                            'url': href,
                            'date': date or 'Unknown',
                            'document_type': self.detect_document_type(title, href),
                            'country_info': self.detect_country_info(title, href)
                        })
            
            logger.debug(f"Found {len(documents)} documents in sections for {company_name}")
        except Exception as e:
            logger.error(f"Error extracting document sections for {company_name}: {e}", exc_info=True)
        
        return documents
    
    def _extract_country_sections(self, soup: BeautifulSoup, company_name: str) -> List[Dict[str, Any]]:
        """Extract documents from country-specific sections
        
        Args:
            soup: BeautifulSoup object
            company_name: Name of the company
            
        Returns:
            List of document dictionaries
        """
        documents = []
        
        try:
            # Look for headings that might indicate country sections
            country_headings = []
            
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = heading.get_text().strip()
                
                # Check if heading contains a country name
                if self._contains_country_name(text):
                    country_headings.append((heading, text))
            
            # Process each country heading
            for heading, heading_text in country_headings:
                country_info = self._extract_country_from_text(heading_text)
                
                # Find all link elements after this heading
                current = heading.next_sibling
                while current and not (hasattr(current, 'name') and current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    if hasattr(current, 'find_all'):
                        links = current.find_all('a', href=True)
                        
                        for link in links:
                            href = link['href']
                            title = link.get_text().strip()
                            
                            # Skip empty titles
                            if not title:
                                continue
                            
                            # Look for date near the link
                            date = self._extract_date_near_element(link)
                            
                            documents.append({
                                'title': title,
                                'url': href,
                                'date': date or 'Unknown',
                                'document_type': self.detect_document_type(title, href),
                                'country_info': country_info
                            })
                    
                    current = current.next_sibling
            
            logger.debug(f"Found {len(documents)} documents in country sections for {company_name}")
        except Exception as e:
            logger.error(f"Error extracting country sections for {company_name}: {e}", exc_info=True)
        
        return documents
    
    def _extract_document_tables(self, soup: BeautifulSoup, company_name: str) -> List[Dict[str, Any]]:
        """Extract documents from tables
        
        Args:
            soup: BeautifulSoup object
            company_name: Name of the company
            
        Returns:
            List of document dictionaries
        """
        documents = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            for table in tables:
                # Find all rows
                rows = table.find_all('tr')
                
                for row in rows:
                    # Find all cells
                    cells = row.find_all(['td', 'th'])
                    
                    # Skip header rows
                    if all(cell.name == 'th' for cell in cells):
                        continue
                    
                    # Look for links in this row
                    links = row.find_all('a', href=True)
                    
                    if not links:
                        continue
                    
                    # Get cell texts
                    cell_texts = [cell.get_text().strip() for cell in cells]
                    
                    # Try to identify date column
                    date = None
                    for cell_text in cell_texts:
                        if self._looks_like_date(cell_text):
                            date = cell_text
                            break
                    
                    # Process links
                    for link in links:
                        href = link['href']
                        title = link.get_text().strip()
                        
                        # Skip empty titles
                        if not title:
                            continue
                        
                        # If we didn't find a date in a cell, look near the link
                        if not date:
                            date = self._extract_date_near_element(link)
                        
                        documents.append({
                            'title': title,
                            'url': href,
                            'date': date or 'Unknown',
                            'document_type': self.detect_document_type(title, href),
                            'country_info': self.detect_country_info(title, href)
                        })
            
            logger.debug(f"Found {len(documents)} documents in tables for {company_name}")
        except Exception as e:
            logger.error(f"Error extracting document tables for {company_name}: {e}", exc_info=True)
        
        return documents
    
    def _extract_fallback_document_links(self, soup: BeautifulSoup, company_name: str) -> List[Dict[str, Any]]:
        """Extract document links as a fallback approach
        
        Args:
            soup: BeautifulSoup object
            company_name: Name of the company
            
        Returns:
            List of document dictionaries
        """
        documents = []
        doc_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
        
        try:
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Only consider links that might be documents
                if (any(href.lower().endswith(ext) for ext in doc_extensions) or
                    'document' in href.lower() or
                    'report' in href.lower() or
                    'financial' in href.lower()):
                    
                    title = link.get_text().strip()
                    
                    # Skip empty titles or navigation links
                    if not title or title.lower() in ['home', 'back', 'next', 'previous']:
                        continue
                    
                    # Look for date near the link
                    date = self._extract_date_near_element(link)
                    
                    documents.append({
                        'title': title,
                        'url': href,
                        'date': date or 'Unknown',
                        'document_type': self.detect_document_type(title, href),
                        'country_info': self.detect_country_info(title, href)
                    })
            
            logger.debug(f"Found {len(documents)} documents in fallback approach for {company_name}")
        except Exception as e:
            logger.error(f"Error extracting fallback document links for {company_name}: {e}", exc_info=True)
        
        return documents
    
    def _extract_date_near_element(self, element: Tag) -> Optional[str]:
        """Extract date near an element
        
        Args:
            element: BeautifulSoup Tag
            
        Returns:
            Date string or None if not found
        """
        # First, check for "Last Updated" spans or divs nearby
        # Look in parent, siblings, and nearby elements
        
        # Check if we can find any "Last Updated" text nearby
        parent = element.parent
        if parent:
            # Look for elements with text containing "Last Updated"
            for nearby in parent.find_all(['div', 'span', 'p', 'small']):
                text = nearby.get_text().strip()
                if 'last updated' in text.lower():
                    date_match = self._extract_date_from_text(text)
                    if date_match:
                        return date_match
        
        # Look for the nearest div that might contain a date
        current = element
        for _ in range(3):  # Check up to 3 levels up
            if current.parent:
                current = current.parent
                for date_container in current.find_all(['div', 'span', 'p', 'small']):
                    text = date_container.get_text().strip()
                    if 'last updated' in text.lower() or self._looks_like_date(text):
                        date_match = self._extract_date_from_text(text)
                        if date_match:
                            return date_match
        
        # Check element text first
        element_text = element.get_text().strip()
        date_match = self._extract_date_from_text(element_text)
        if date_match:
            return date_match
        
        # Check parent and sibling elements
        date = None
        
        # Check parent
        if element.parent:
            parent_text = element.parent.get_text().strip()
            parent_date = self._extract_date_from_text(parent_text)
            if parent_date:
                return parent_date
            
            # Check siblings
            for sibling in element.parent.children:
                if sibling == element:
                    continue
                
                sibling_text = sibling.get_text().strip() if hasattr(sibling, 'get_text') else ''
                sibling_date = self._extract_date_from_text(sibling_text)
                if sibling_date:
                    return sibling_date
        
        return None
    
    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """Extract date from text
        
        Args:
            text: Text to extract date from
            
        Returns:
            Date string or None if not found
        """
        if not text:
            return None
        
        # Special patterns for "Last Updated: " format from company pages
        # Handle multiple date formats that appear on the Mintos website
        last_updated_patterns = [
            r'Last Updated:?\s*(\d{1,2}\.\d{1,2}\.\d{4})',  # Format: DD.MM.YYYY
            r'Last Updated:?\s*(\d{1,2}-\d{1,2}-\d{4})',    # Format: DD-MM-YYYY
            r'Last Updated:?\s*(\d{1,2}/\d{1,2}/\d{4})',    # Format: DD/MM/YYYY
            r'Last Updated:?\s*(\w+ \d{1,2},? \d{4})',      # Format: Month DD, YYYY
            r'Updated:?\s*(\d{1,2}\.\d{1,2}\.\d{4})',       # Format without "Last"
            r'Updated on:?\s*(\d{1,2}\.\d{1,2}\.\d{4})'     # Another variation
        ]
        
        for pattern in last_updated_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)  # Return just the date part
        
        # Common date patterns
        date_patterns = [
            # ISO format: yyyy-mm-dd
            r'(\d{4}-\d{1,2}-\d{1,2})',
            # European format: dd.mm.yyyy
            r'(\d{1,2}\.\d{1,2}\.\d{4})',
            # US format: mm/dd/yyyy
            r'(\d{1,2}/\d{1,2}/\d{4})',
            # Text format: Month dd, yyyy
            r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        
        return None
    
    def _looks_like_date(self, text: str) -> bool:
        """Check if text looks like a date
        
        Args:
            text: Text to check
            
        Returns:
            True if text looks like a date, False otherwise
        """
        if not text:
            return False
        
        # Common date patterns
        date_patterns = [
            # ISO format: yyyy-mm-dd
            r'^\d{4}-\d{1,2}-\d{1,2}$',
            # European format: dd.mm.yyyy
            r'^\d{1,2}\.\d{1,2}\.\d{4}$',
            # US format: mm/dd/yyyy
            r'^\d{1,2}/\d{1,2}/\d{4}$',
            # Text format: Month dd, yyyy
            r'^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}$'
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def _contains_country_name(self, text: str) -> bool:
        """Check if text contains a country name
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains a country name, False otherwise
        """
        common_countries = [
            'estonia', 'latvia', 'lithuania', 'finland', 'spain', 'poland',
            'czech', 'republic', 'czech republic', 'romania', 'bulgaria',
            'croatia', 'ukraine', 'russia', 'kazakhstan', 'georgia',
            'armenia', 'moldova', 'belarus', 'azerbaijan', 'uzbekistan',
            'kyrgyzstan', 'tajikistan', 'turkmenistan', 'mongolia',
            'indonesia', 'philippines', 'vietnam', 'malaysia', 'thailand',
            'singapore', 'cambodia', 'myanmar', 'laos', 'brunei',
            'india', 'pakistan', 'bangladesh', 'sri lanka', 'nepal',
            'bhutan', 'maldives', 'kenya', 'uganda', 'tanzania',
            'rwanda', 'burundi', 'south africa', 'nigeria', 'ghana',
            'botswana', 'namibia', 'zambia', 'zimbabwe', 'mozambique',
            'malawi', 'lesotho', 'swaziland', 'mexico', 'brazil',
            'argentina', 'chile', 'colombia', 'peru', 'venezuela',
            'bolivia', 'ecuador', 'paraguay', 'uruguay', 'guatemala',
            'el salvador', 'honduras', 'nicaragua', 'costa rica',
            'panama', 'belize', 'dominican republic', 'cuba', 'haiti',
            'jamaica', 'bahamas', 'barbados', 'trinidad and tobago',
            'grenada', 'antigua and barbuda', 'dominica', 'saint lucia',
            'saint vincent and the grenadines', 'saint kitts and nevis',
            'united states', 'usa', 'canada', 'australia', 'new zealand',
            'uk', 'united kingdom', 'germany', 'france', 'italy', 'spain',
            'portugal', 'ireland', 'belgium', 'netherlands', 'luxembourg',
            'switzerland', 'austria', 'denmark', 'sweden', 'norway',
            'iceland', 'greece', 'turkey', 'cyprus', 'malta'
        ]
        
        text_lower = text.lower()
        
        for country in common_countries:
            if country in text_lower:
                return True
        
        return False
    
    def _extract_country_from_text(self, text: str) -> Dict[str, Any]:
        """Extract country information from text
        
        Args:
            text: Text to extract country from
            
        Returns:
            Dictionary with country information
        """
        common_countries = [
            'estonia', 'latvia', 'lithuania', 'finland', 'spain', 'poland',
            'czech republic', 'romania', 'bulgaria', 'croatia', 'ukraine',
            'russia', 'kazakhstan', 'georgia', 'armenia', 'moldova',
            'belarus', 'azerbaijan', 'uzbekistan', 'kyrgyzstan', 'tajikistan',
            'turkmenistan', 'mongolia', 'indonesia', 'philippines', 'vietnam',
            'malaysia', 'thailand', 'singapore', 'cambodia', 'myanmar',
            'laos', 'brunei', 'india', 'pakistan', 'bangladesh', 'sri lanka',
            'nepal', 'bhutan', 'maldives', 'kenya', 'uganda', 'tanzania',
            'rwanda', 'burundi', 'south africa', 'nigeria', 'ghana',
            'botswana', 'namibia', 'zambia', 'zimbabwe', 'mozambique',
            'malawi', 'lesotho', 'swaziland', 'mexico', 'brazil',
            'argentina', 'chile', 'colombia', 'peru', 'venezuela',
            'bolivia', 'ecuador', 'paraguay', 'uruguay', 'guatemala',
            'el salvador', 'honduras', 'nicaragua', 'costa rica',
            'panama', 'belize', 'dominican republic', 'cuba', 'haiti',
            'jamaica', 'bahamas', 'barbados', 'trinidad and tobago',
            'grenada', 'antigua and barbuda', 'dominica', 'saint lucia',
            'saint vincent and the grenadines', 'saint kitts and nevis',
            'united states', 'usa', 'canada', 'australia', 'new zealand',
            'uk', 'united kingdom', 'germany', 'france', 'italy', 'spain',
            'portugal', 'ireland', 'belgium', 'netherlands', 'luxembourg',
            'switzerland', 'austria', 'denmark', 'sweden', 'norway',
            'iceland', 'greece', 'turkey', 'cyprus', 'malta'
        ]
        
        text_lower = text.lower()
        
        for country in common_countries:
            if country in text_lower:
                return {'country': country.title()}
        
        return {}
    
    def detect_document_type(self, title: str, url: str) -> str:
        """Detect the type of document based on title and URL
        
        Args:
            title: Document title
            url: Document URL
            
        Returns:
            Document type/category as a string
        """
        title_lower = title.lower()
        url_lower = url.lower()
        
        # Financial document keywords
        financial_keywords = [
            'financial', 'finance', 'statement', 'report', 'annual', 'quarterly',
            'interim', 'balance', 'sheet', 'income', 'cash', 'flow', 'profit',
            'loss', 'earnings', 'q1', 'q2', 'q3', 'q4', 'year', 'fiscal'
        ]
        
        # Presentation keywords
        presentation_keywords = [
            'presentation', 'slide', 'deck', 'investor', 'corporate', 'overview',
            'introduction', 'summary', 'profile', 'factsheet', 'fact sheet'
        ]
        
        # Regulatory document keywords
        regulatory_keywords = [
            'prospectus', 'regulatory', 'regulation', 'compliance', 'legal',
            'filing', 'sec', 'exchange', 'commission', 'authority', 'regulator',
            'supervision', 'supervisory', 'registration', 'offering', 'memorandum'
        ]
        
        # Check for financial document
        if any(keyword in title_lower or keyword in url_lower for keyword in financial_keywords):
            if 'annual' in title_lower or 'annual' in url_lower:
                return 'Annual Financial Report'
            elif any(q in title_lower or q in url_lower for q in ['q1', 'q2', 'q3', 'q4']):
                return 'Quarterly Financial Report'
            else:
                return 'Financial Report'
        
        # Check for presentation
        if any(keyword in title_lower or keyword in url_lower for keyword in presentation_keywords):
            return 'Presentation'
        
        # Check for regulatory document
        if any(keyword in title_lower or keyword in url_lower for keyword in regulatory_keywords):
            if 'prospectus' in title_lower or 'prospectus' in url_lower:
                return 'Prospectus'
            else:
                return 'Regulatory Document'
        
        # Default document type based on file extension
        if url_lower.endswith('.pdf'):
            return 'PDF Document'
        elif url_lower.endswith('.doc') or url_lower.endswith('.docx'):
            return 'Word Document'
        elif url_lower.endswith('.xls') or url_lower.endswith('.xlsx'):
            return 'Excel Document'
        elif url_lower.endswith('.ppt') or url_lower.endswith('.pptx'):
            return 'PowerPoint Document'
        
        # Default type
        return 'Document'
    
    def detect_country_info(self, title: str, url: str) -> Dict[str, Any]:
        """Detect country information in document title or URL
        
        Args:
            title: Document title
            url: Document URL
            
        Returns:
            Dictionary with country information or empty dict if none detected
        """
        title_lower = title.lower()
        url_lower = url.lower()
        
        # Common country mappings
        country_mapping = {
            'estonia': 'Estonia',
            'estonian': 'Estonia',
            'latvia': 'Latvia',
            'latvian': 'Latvia',
            'lithuania': 'Lithuania',
            'lithuanian': 'Lithuania',
            'finland': 'Finland',
            'finnish': 'Finland',
            'spain': 'Spain',
            'spanish': 'Spain',
            'poland': 'Poland',
            'polish': 'Poland',
            'czech': 'Czech Republic',
            'romania': 'Romania',
            'romanian': 'Romania',
            'bulgaria': 'Bulgaria',
            'bulgarian': 'Bulgaria',
            'croatia': 'Croatia',
            'croatian': 'Croatia',
            'ukraine': 'Ukraine',
            'ukrainian': 'Ukraine',
            'russia': 'Russia',
            'russian': 'Russia',
            'kazakhstan': 'Kazakhstan',
            'georgia': 'Georgia',
            'armenian': 'Armenia',
            'armenia': 'Armenia',
            'moldova': 'Moldova',
            'moldovan': 'Moldova',
            'belarus': 'Belarus',
            'belarusian': 'Belarus',
            'azerbaijan': 'Azerbaijan',
            'uzbekistan': 'Uzbekistan',
            'kyrgyzstan': 'Kyrgyzstan',
            'tajikistan': 'Tajikistan',
            'turkmenistan': 'Turkmenistan',
            'mongolia': 'Mongolia',
            'indonesian': 'Indonesia',
            'indonesia': 'Indonesia',
            'philippines': 'Philippines',
            'philippine': 'Philippines',
            'vietnam': 'Vietnam',
            'vietnamese': 'Vietnam',
            'malaysia': 'Malaysia',
            'malaysian': 'Malaysia',
            'thailand': 'Thailand',
            'thai': 'Thailand',
            'singapore': 'Singapore',
            'cambodia': 'Cambodia',
            'cambodian': 'Cambodia',
            'myanmar': 'Myanmar',
            'burmese': 'Myanmar',
            'laos': 'Laos',
            'laotian': 'Laos',
            'brunei': 'Brunei',
            'india': 'India',
            'indian': 'India',
            'pakistan': 'Pakistan',
            'pakistani': 'Pakistan',
            'bangladesh': 'Bangladesh',
            'sri lanka': 'Sri Lanka',
            'nepal': 'Nepal',
            'bhutan': 'Bhutan',
            'maldives': 'Maldives'
        }
        
        # Check for country in title or URL
        for key, country in country_mapping.items():
            if key in title_lower or key in url_lower:
                return {'country': country}
        
        # Special cases for abbreviations and complex patterns
        if 'uk' in title_lower.split() or 'uk' in url_lower.split():
            return {'country': 'United Kingdom'}
        
        if 'usa' in title_lower.split() or 'usa' in url_lower.split():
            return {'country': 'United States'}
        
        # Check for country codes
        country_codes = {
            'ee': 'Estonia',
            'lv': 'Latvia',
            'lt': 'Lithuania',
            'fi': 'Finland',
            'es': 'Spain',
            'pl': 'Poland',
            'cz': 'Czech Republic',
            'ro': 'Romania',
            'bg': 'Bulgaria',
            'hr': 'Croatia',
            'ua': 'Ukraine',
            'ru': 'Russia',
            'kz': 'Kazakhstan',
            'ge': 'Georgia',
            'am': 'Armenia',
            'md': 'Moldova',
            'by': 'Belarus',
            'az': 'Azerbaijan',
            'uz': 'Uzbekistan',
            'kg': 'Kyrgyzstan',
            'tj': 'Tajikistan',
            'tm': 'Turkmenistan',
            'mn': 'Mongolia',
            'id': 'Indonesia',
            'ph': 'Philippines',
            'vn': 'Vietnam',
            'my': 'Malaysia',
            'th': 'Thailand',
            'sg': 'Singapore',
            'kh': 'Cambodia',
            'mm': 'Myanmar',
            'la': 'Laos',
            'bn': 'Brunei',
            'in': 'India',
            'pk': 'Pakistan',
            'bd': 'Bangladesh',
            'lk': 'Sri Lanka',
            'np': 'Nepal',
            'bt': 'Bhutan',
            'mv': 'Maldives',
            'ke': 'Kenya',
            'ug': 'Uganda',
            'tz': 'Tanzania',
            'rw': 'Rwanda',
            'bi': 'Burundi',
            'za': 'South Africa',
            'ng': 'Nigeria',
            'gh': 'Ghana',
            'bw': 'Botswana',
            'na': 'Namibia',
            'zm': 'Zambia',
            'zw': 'Zimbabwe',
            'mz': 'Mozambique',
            'mw': 'Malawi',
            'ls': 'Lesotho',
            'sz': 'Swaziland',
            'mx': 'Mexico',
            'br': 'Brazil',
            'ar': 'Argentina',
            'cl': 'Chile',
            'co': 'Colombia',
            'pe': 'Peru',
            've': 'Venezuela',
            'bo': 'Bolivia',
            'ec': 'Ecuador',
            'py': 'Paraguay',
            'uy': 'Uruguay',
            'gt': 'Guatemala',
            'sv': 'El Salvador',
            'hn': 'Honduras',
            'ni': 'Nicaragua',
            'cr': 'Costa Rica',
            'pa': 'Panama',
            'bz': 'Belize',
            'do': 'Dominican Republic',
            'cu': 'Cuba',
            'ht': 'Haiti',
            'jm': 'Jamaica',
            'bs': 'Bahamas',
            'bb': 'Barbados',
            'tt': 'Trinidad and Tobago',
            'gd': 'Grenada',
            'ag': 'Antigua and Barbuda',
            'dm': 'Dominica',
            'lc': 'Saint Lucia',
            'vc': 'Saint Vincent and the Grenadines',
            'kn': 'Saint Kitts and Nevis',
            'us': 'United States',
            'ca': 'Canada',
            'au': 'Australia',
            'nz': 'New Zealand',
            'gb': 'United Kingdom',
            'uk': 'United Kingdom',
            'de': 'Germany',
            'fr': 'France',
            'it': 'Italy',
            'pt': 'Portugal',
            'ie': 'Ireland',
            'be': 'Belgium',
            'nl': 'Netherlands',
            'lu': 'Luxembourg',
            'ch': 'Switzerland',
            'at': 'Austria',
            'dk': 'Denmark',
            'se': 'Sweden',
            'no': 'Norway',
            'is': 'Iceland',
            'gr': 'Greece',
            'tr': 'Turkey',
            'cy': 'Cyprus',
            'mt': 'Malta'
        }
        
        # Check for country codes in URL or title
        for code, country in country_codes.items():
            # Make sure it's a standalone code (surrounded by non-alphanumeric characters)
            if f"/{code}/" in url_lower or f"_{code}_" in url_lower or f"-{code}-" in url_lower:
                return {'country': country}
            
            # Check in title with word boundaries
            if re.search(r'\b' + code + r'\b', title_lower):
                return {'country': country}
        
        return {}
    
    def generate_document_id(self, title: str, url: str, date: str) -> str:
        """Generate a unique ID for a document based on its properties
        
        Args:
            title: Document title
            url: Document URL
            date: Document date
            
        Returns:
            String identifier for the document
        """
        # Create composite key
        key = f"{title}|{url}|{date}"
        
        # Generate hash
        return hashlib.md5(key.encode()).hexdigest()