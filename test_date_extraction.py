#!/usr/bin/env python3
"""
Test script for document date extraction functionality
"""
import asyncio
import logging
from bs4 import BeautifulSoup
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('date_extraction_test')

def _normalize_date(date_str: str) -> str:
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

async def extract_date_from_page(html_content: str):
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

async def main():
    """Test function for date extraction"""
    print("\n*** Testing Date Extraction Logic ***\n")
    
    # Test cases
    test_cases = [
        # Test 1: Standard Mintos table cell format
        ('<td data-label="Last Updated">12.02.2025</td>', 
         'Table cell with data-label'),
        
        # Test 2: Text with "Last Updated" phrase
        ('<div>Basic information Last Updated: 15.01.2025</div>',
         'Div with Last Updated text'),
        
        # Test 3: Text with "Updated" phrase
        ('<span>Updated: 03/15/2025</span>',
         'Span with Updated text'),
        
        # Test 4: Date in various formats
        ('<p>Company report from 2025-02-28</p>',
         'Paragraph with ISO date format'),
        
        # Test 5: Complex HTML with nested elements
        ('''
        <div class="company-info">
            <h2>Company Details</h2>
            <div class="info-section">
                <span class="label">Status:</span> Active
                <span class="label">Last Updated:</span> 20.03.2024
                <div class="documents">
                    <a href="/files/presentation_2024.pdf">Presentation</a>
                    <a href="/files/financial_report_22.04.2024.pdf">Financial Report</a>
                </div>
            </div>
        </div>
        ''', 'Complex nested HTML')
    ]
    
    for html, description in test_cases:
        print(f"\n--- Test: {description} ---")
        print(f"HTML: {html[:50]}..." if len(html) > 50 else f"HTML: {html}")
        
        result = await extract_date_from_page(html)
        print(f"Extracted date: {result}")
    
    print("\n*** Test completed ***\n")

if __name__ == "__main__":
    asyncio.run(main())