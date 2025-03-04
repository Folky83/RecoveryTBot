#!/usr/bin/env python3
"""
Improved Document Scraper
Specifically for extracting presentation, financials, and loan agreement PDFs
from Mintos company pages, with proper date attribution.
"""
import os
import json
import logging
import asyncio
import aiohttp
import re
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('improved_document_scraper')

# Define constants
DOCUMENT_TYPES = ['presentation', 'financials', 'loan_agreement']
DATA_DIR = 'data'
DOCS_OUTPUT_FILE = os.path.join(DATA_DIR, 'document_extraction_results.json')

def _normalize_date(date_str):
    """Normalize date format to YYYY-MM-DD"""
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

async def fetch_page(url):
    """Fetch a web page with error handling and retries"""
    max_retries = 3
    retry_delay = 1  # seconds
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                        
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Error fetching {url} (attempt {attempt+1}/{max_retries}): {e}")
            
        # Wait before retrying (except on last attempt)
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
            
    logger.error(f"Failed to fetch {url} after {max_retries} attempts")
    return None

async def extract_date_from_page(html_content):
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
                    return _normalize_date(date_text)
        
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
                    normalized_date = _normalize_date(date_str)
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
                normalized_date = _normalize_date(date_str)
                logger.debug(f"Found date in page text: {date_str} -> {normalized_date}")
                return normalized_date
                
        logger.warning("No date found in page, using today's date")
        return today
    except Exception as e:
        logger.error(f"Error extracting date from page: {e}")
        return datetime.now().strftime('%Y-%m-%d')

async def extract_document_pdf_links(html_content, company_name):
    """Extract PDF links for specific document types from the company page"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract the page date as fallback
        page_date = await extract_date_from_page(html_content)
        logger.info(f"Page date for {company_name}: {page_date}")
        
        # Prepare results dictionary
        result = {}
        
        # Strategy 1: Find direct pattern matches
        # - Look for anchor tags with exact document type names
        # - Extract URLs and dates
        
        for doc_type in DOCUMENT_TYPES:
            # Skip if we already found this document type
            if doc_type in result:
                continue
                
            # Create display text for the document type (for matching)
            doc_type_display = doc_type.replace('_', ' ').title()
            
            # Find links with matching text
            for link in soup.find_all('a', href=True):
                link_text = link.get_text().strip()
                if link_text.lower() == doc_type_display.lower():
                    href = link.get('href', '')
                    if href and href.lower().endswith('.pdf'):
                        logger.debug(f"Found exact match for {doc_type}: {href}")
                        
                        # Try to extract a specific date for this document
                        specific_date = None
                        
                        # First, look in the containing elements
                        parent = link.parent
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
                                        specific_date = _normalize_date(match.group(1))
                                        break
                                parent = parent.parent
                                if specific_date:
                                    break
                        
                        # Make sure we have an absolute URL
                        if not href.startswith(('http://', 'https://')):
                            if href.startswith('/'):
                                href = f"https://www.mintos.com{href}"
                            else:
                                href = f"https://www.mintos.com/{href}"
                        
                        # Use document-specific date if found, otherwise use page date
                        date_to_use = specific_date if specific_date else page_date
                        
                        # Store the result
                        result[doc_type] = {
                            'url': href,
                            'title': link_text,
                            'date': date_to_use
                        }
                        break
        
        # Strategy 2: Look for document-type elements and their associated links
        # Check for document cards or sections
        for doc_type in DOCUMENT_TYPES:
            # Skip if we already found this document type
            if doc_type in result:
                continue
                
            # Create display text for the document type (for matching)
            doc_type_display = doc_type.replace('_', ' ').title()
            
            # Find elements containing doc_type text
            doc_elements = soup.find_all(
                ['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
                string=lambda s: s and doc_type_display.lower() in s.lower()
            )
            
            for element in doc_elements:
                # Check if this element or its parent contains a PDF link
                search_elements = [element]
                if element.parent:
                    search_elements.append(element.parent)
                if element.parent and element.parent.parent:
                    search_elements.append(element.parent.parent)
                
                for search_el in search_elements:
                    pdf_links = search_el.find_all('a', href=lambda h: h and h.lower().endswith('.pdf'))
                    if pdf_links:
                        link = pdf_links[0]  # Take the first PDF link
                        href = link.get('href', '')
                        if href:
                            link_text = link.get_text().strip() or doc_type_display
                            logger.debug(f"Found {doc_type} by element association: {href}")
                            
                            # Make sure we have an absolute URL
                            if not href.startswith(('http://', 'https://')):
                                if href.startswith('/'):
                                    href = f"https://www.mintos.com{href}"
                                else:
                                    href = f"https://www.mintos.com/{href}"
                            
                            # Store the result
                            result[doc_type] = {
                                'url': href,
                                'title': link_text,
                                'date': page_date  # Use page date since we don't have specific date
                            }
                            break
                
                if doc_type in result:
                    break
        
        # Strategy 3: Parse document link cards with common containers
        if len(result) < len(DOCUMENT_TYPES):
            # Look for document "cards" grouped together
            card_containers = soup.find_all('div')
            for container in card_containers:
                # Check if this container has at least 2 of our document types
                container_text = container.get_text().lower()
                matches = 0
                for doc_type in DOCUMENT_TYPES:
                    doc_text = doc_type.replace('_', ' ').lower()
                    if doc_text in container_text:
                        matches += 1
                
                # If this looks like a document container, extract PDF links
                if matches >= 2:
                    # This might be a container of document cards
                    pdf_links = container.find_all('a', href=lambda h: h and h.lower().endswith('.pdf'))
                    
                    # Try to associate links with document types
                    for link in pdf_links:
                        link_text = link.get_text().strip()
                        href = link.get('href', '')
                        
                        # Determine document type
                        doc_match = None
                        for doc_type in DOCUMENT_TYPES:
                            if doc_type not in result:  # Skip if already found
                                doc_text = doc_type.replace('_', ' ').lower()
                                if doc_text == link_text.lower() or doc_text in link_text.lower():
                                    doc_match = doc_type
                                    break
                        
                        if doc_match:
                            # Make sure we have an absolute URL
                            if not href.startswith(('http://', 'https://')):
                                if href.startswith('/'):
                                    href = f"https://www.mintos.com{href}"
                                else:
                                    href = f"https://www.mintos.com/{href}"
                            
                            # Store the result
                            result[doc_match] = {
                                'url': href,
                                'title': link_text,
                                'date': page_date
                            }
                            
                            # Break if we've found all document types
                            if len(result) == len(DOCUMENT_TYPES):
                                break
        
        # Log the results
        logger.info(f"Found {len(result)}/{len(DOCUMENT_TYPES)} document types for {company_name}")
        for doc_type, data in result.items():
            logger.info(f"  - {doc_type}: {data['title']} ({data['date']})")
        
        return result
    
    except Exception as e:
        logger.error(f"Error extracting document PDF links: {e}")
        return {}

async def process_company(company_name, url):
    """Process a single company page"""
    logger.info(f"Processing company: {company_name}")
    
    # Fetch the company page
    html_content = await fetch_page(url)
    if not html_content:
        logger.error(f"Failed to fetch page for {company_name}")
        return {
            'company_name': company_name,
            'success': False,
            'error': 'Failed to fetch page',
            'documents': {}
        }
    
    # Extract document PDF links
    documents = await extract_document_pdf_links(html_content, company_name)
    
    # Build result
    result = {
        'company_name': company_name,
        'url': url,
        'success': True,
        'documents': documents
    }
    
    return result

async def main():
    """Main function"""
    try:
        # Ensure data directory exists
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Load company pages from CSV
        try:
            df = pd.read_csv('attached_assets/company_pages.csv')
            logger.info(f"Loaded {len(df)} companies from CSV")
        except Exception as e:
            logger.error(f"Error loading company pages CSV: {e}")
            return
        
        # Process all companies
        sample = df
        
        logger.info(f"Processing all {len(sample)} companies")
        
        # Process each company
        tasks = []
        for _, row in sample.iterrows():
            company_name = row['Company']
            url = row['URL']
            task = process_company(company_name, url)
            tasks.append(task)
        
        # Run tasks concurrently
        results = await asyncio.gather(*tasks)
        
        # Save results
        with open(DOCS_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Saved document extraction results to {DOCS_OUTPUT_FILE}")
        
        # Print summary
        total_docs = 0
        for result in results:
            company_name = result['company_name']
            success = result['success']
            doc_count = len(result.get('documents', {}))
            total_docs += doc_count
            
            status = "✅" if success else "❌"
            print(f"{status} {company_name}: {doc_count} documents")
        
        print(f"\nTotal documents found: {total_docs}")
        print(f"Average documents per company: {total_docs / len(results):.1f}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())