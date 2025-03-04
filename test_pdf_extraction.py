#!/usr/bin/env python3
"""
Test script for PDF document extraction
Specifically targeting presentation, financials, and loan agreement PDF files
"""
import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
import re
from datetime import datetime
import os
import json

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('pdf_extraction_test')

# Define the document types we're interested in
DOCUMENT_TYPES = ['presentation', 'financials', 'loan_agreement']

async def fetch_page(url):
    """Fetch a web page with error handling and retries"""
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
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

async def extract_pdf_links(html_content, company_name):
    """Extract PDF links for specific document types"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {}
        
        # Extract the document date from the page first
        page_date = await extract_date_from_page(html_content)
        logger.info(f"Page date for {company_name}: {page_date}")
        
        # Find all links to PDFs
        all_links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
        logger.debug(f"Found {len(all_links)} PDF links on the page")
        
        # 1. First look for direct labeled links - clearest indicators
        for doc_type in DOCUMENT_TYPES:
            # Replace underscores with spaces for matching
            doc_type_text = doc_type.replace('_', ' ')
            
            # Find links with the exact document type text
            type_links = soup.find_all('a', string=re.compile(rf'\b{re.escape(doc_type_text)}\b', re.I))
            
            if type_links:
                for link in type_links:
                    href = link.get('href', '')
                    if href and href.lower().endswith('.pdf'):
                        text = link.get_text().strip()
                        logger.debug(f"Found {doc_type} link with text '{text}': {href}")
                        
                        # Try to find a date specific to this document
                        specific_date = None
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
                        
                        # Use specific date if found, otherwise use page date
                        date_to_use = specific_date if specific_date else page_date
                        
                        # Make sure we have absolute URL
                        if not href.startswith(('http://', 'https://')):
                            if href.startswith('/'):
                                href = f"https://www.mintos.com{href}"
                            else:
                                href = f"https://www.mintos.com/{href}"
                        
                        result[doc_type] = {
                            'url': href,
                            'text': text,
                            'date': date_to_use
                        }
                        break  # Take the first matching link for this type
        
        # 2. Look for links inside or near elements containing the document type text
        for doc_type in DOCUMENT_TYPES:
            # Skip if we already found this document type
            if doc_type in result:
                continue
                
            doc_type_text = doc_type.replace('_', ' ')
            
            # Find elements containing the document type text
            containing_elements = soup.find_all(
                ['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td', 'th'],
                string=re.compile(rf'\b{re.escape(doc_type_text)}\b', re.I)
            )
            
            for element in containing_elements:
                # Look for PDF links in this element or its parent
                search_elements = [element, element.parent] if element.parent else [element]
                
                for search_el in search_elements:
                    pdf_links = search_el.find_all('a', href=re.compile(r'\.pdf', re.I))
                    if pdf_links:
                        link = pdf_links[0]  # Take the first PDF link
                        href = link.get('href', '')
                        if href:
                            text = link.get_text().strip() or doc_type_text.capitalize()
                            logger.debug(f"Found {doc_type} PDF near '{doc_type_text}' text: {href}")
                            
                            # Make sure we have absolute URL
                            if not href.startswith(('http://', 'https://')):
                                if href.startswith('/'):
                                    href = f"https://www.mintos.com{href}"
                                else:
                                    href = f"https://www.mintos.com/{href}"
                            
                            result[doc_type] = {
                                'url': href,
                                'text': text,
                                'date': page_date  # Use page date as fallback
                            }
                            break
                
                if doc_type in result:
                    break
        
        # 3. Look in fixed company page structure (based on provided images)
        if len(result) < len(DOCUMENT_TYPES):
            # The images show consistent structure with labeled document cards
            cards = soup.find_all('div', class_=re.compile(r'card'))
            for card in cards:
                card_text = card.get_text().lower()
                
                for doc_type in DOCUMENT_TYPES:
                    if doc_type in result:
                        continue
                        
                    doc_type_text = doc_type.replace('_', ' ').lower()
                    
                    if doc_type_text in card_text:
                        # This card is for the document type we're looking for
                        pdf_links = card.find_all('a', href=re.compile(r'\.pdf', re.I))
                        if pdf_links:
                            link = pdf_links[0]
                            href = link.get('href', '')
                            if href:
                                text = link.get_text().strip() or doc_type_text.capitalize()
                                logger.debug(f"Found {doc_type} PDF in card: {href}")
                                
                                # Look for date within the card
                                date_elements = card.find_all(
                                    ['span', 'div', 'p'],
                                    string=re.compile(r'(Last\s+Updated|Updated)', re.I)
                                )
                                
                                specific_date = None
                                if date_elements:
                                    for date_el in date_elements:
                                        date_text = date_el.get_text()
                                        for pattern in [
                                            r'Last Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                                            r'Updated:?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                                            r'(\d{1,2}\.\d{1,2}\.\d{4})',
                                            r'(\d{4}-\d{2}-\d{2})'
                                        ]:
                                            match = re.search(pattern, date_text)
                                            if match:
                                                specific_date = _normalize_date(match.group(1))
                                                break
                                        if specific_date:
                                            break
                                
                                # Make sure we have absolute URL
                                if not href.startswith(('http://', 'https://')):
                                    if href.startswith('/'):
                                        href = f"https://www.mintos.com{href}"
                                    else:
                                        href = f"https://www.mintos.com/{href}"
                                
                                result[doc_type] = {
                                    'url': href,
                                    'text': text,
                                    'date': specific_date if specific_date else page_date
                                }
        
        # 4. Look for specific section identifiers and then PDFs
        sections = {
            'presentation': ['company presentation', 'lender presentation', 'investor presentation'],
            'financials': ['financial reports', 'financial statements', 'financial data'],
            'loan_agreement': ['loan agreement', 'assignment agreement', 'credit agreement']
        }
        
        for doc_type, section_texts in sections.items():
            if doc_type in result:
                continue
                
            for section_text in section_texts:
                # Find headers, paragraphs, or divs containing the section text
                section_elements = soup.find_all(
                    ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p'],
                    string=re.compile(rf'\b{re.escape(section_text)}\b', re.I)
                )
                
                for element in section_elements:
                    # Look in this element and up to 3 levels below
                    found_link = False
                    current = element
                    
                    # First check the element itself
                    pdf_links = current.find_all('a', href=re.compile(r'\.pdf', re.I))
                    if pdf_links:
                        link = pdf_links[0]
                        href = link.get('href', '')
                        if href:
                            text = link.get_text().strip() or section_text.capitalize()
                            logger.debug(f"Found {doc_type} PDF in section '{section_text}': {href}")
                            
                            # Make sure we have absolute URL
                            if not href.startswith(('http://', 'https://')):
                                if href.startswith('/'):
                                    href = f"https://www.mintos.com{href}"
                                else:
                                    href = f"https://www.mintos.com/{href}"
                            
                            result[doc_type] = {
                                'url': href,
                                'text': text,
                                'date': page_date
                            }
                            found_link = True
                            break
                    
                    # Then check siblings and nearby elements
                    if not found_link:
                        siblings = list(current.next_siblings)[:5]  # Check next 5 siblings
                        for sibling in siblings:
                            if hasattr(sibling, 'find_all'):
                                pdf_links = sibling.find_all('a', href=re.compile(r'\.pdf', re.I))
                                if pdf_links:
                                    link = pdf_links[0]
                                    href = link.get('href', '')
                                    if href:
                                        text = link.get_text().strip() or section_text.capitalize()
                                        logger.debug(f"Found {doc_type} PDF in sibling of '{section_text}': {href}")
                                        
                                        # Make sure we have absolute URL
                                        if not href.startswith(('http://', 'https://')):
                                            if href.startswith('/'):
                                                href = f"https://www.mintos.com{href}"
                                            else:
                                                href = f"https://www.mintos.com/{href}"
                                        
                                        result[doc_type] = {
                                            'url': href,
                                            'text': text,
                                            'date': page_date
                                        }
                                        found_link = True
                                        break
                    
                    if found_link:
                        break
                
                if doc_type in result:
                    break
        
        # Log the results
        logger.info(f"Found {len(result)}/{len(DOCUMENT_TYPES)} document types for {company_name}")
        for doc_type, data in result.items():
            logger.info(f"  - {doc_type}: {data['text']} ({data['date']})")
        
        return result
        
    except Exception as e:
        logger.error(f"Error extracting PDF links: {e}")
        return {}

async def test_company_pdf_extraction(company_name, url):
    """Test PDF extraction for a single company"""
    logger.info(f"Testing PDF extraction for {company_name}")
    
    # Fetch the company page
    html_content = await fetch_page(url)
    if not html_content:
        logger.error(f"Failed to fetch page for {company_name}")
        return None
    
    # Extract PDF links
    pdf_links = await extract_pdf_links(html_content, company_name)
    
    # Return the results
    return {
        'company_name': company_name,
        'url': url,
        'documents': pdf_links
    }

async def main():
    """Main test function"""
    # Load company pages from CSV
    import pandas as pd
    
    try:
        df = pd.read_csv('attached_assets/company_pages.csv')
        logger.info(f"Loaded {len(df)} companies from CSV")
    except Exception as e:
        logger.error(f"Error loading company pages CSV: {e}")
        return
    
    # Test with a small sample of companies first
    sample_size = 3
    sample = df.sample(n=min(sample_size, len(df)))
    
    logger.info(f"Testing PDF extraction for {sample_size} companies")
    
    results = []
    for _, row in sample.iterrows():
        company_name = row['Company']
        url = row['URL']
        
        result = await test_company_pdf_extraction(company_name, url)
        if result:
            results.append(result)
            
            # Print detailed results
            print(f"\n--- Results for {company_name} ---")
            print(f"URL: {url}")
            
            if not result['documents']:
                print("No PDFs found")
            else:
                for doc_type, data in result['documents'].items():
                    print(f"{doc_type}:")
                    print(f"  Title: {data['text']}")
                    print(f"  Date:  {data['date']}")
                    print(f"  URL:   {data['url']}")
    
    # Save the results to a file for inspection
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/pdf_extraction_test.json', 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Saved results to data/pdf_extraction_test.json")
    except Exception as e:
        logger.error(f"Error saving results: {e}")
    
    logger.info("Test completed")

if __name__ == "__main__":
    asyncio.run(main())