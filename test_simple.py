"""
Simple test for refactored document scraper
Tests just the parser functionality without making external requests
"""
import logging
import sys
from bot.document_parser import DocumentParser
from bot.logger import setup_logger

# Configure logger
logger = setup_logger('test_simple')

def test_document_parser():
    """Test the document parser component with a sample HTML"""
    logger.info("Testing document parser...")
    
    # Initialize document parser
    document_parser = DocumentParser()
    
    # Create sample HTML with document links
    sample_html = """
    <html>
    <body>
        <h1>Documents for Test Company</h1>
        <div class="documents">
            <a href="sample.pdf">Sample Document (PDF)</a> - January 15, 2023
            <a href="financial.xlsx">Financial Report Q1 2023</a> - March 31, 2023
        </div>
        <h2>Country Specific Documents</h2>
        <h3>Estonia</h3>
        <ul>
            <li><a href="estonia_report.pdf">Estonia Annual Report</a> - December 20, 2022</li>
        </ul>
        <table>
            <tr>
                <th>Document Title</th>
                <th>Date</th>
            </tr>
            <tr>
                <td><a href="presentation.pptx">Company Presentation</a></td>
                <td>February 10, 2023</td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    # Parse documents
    documents = document_parser.parse_documents(sample_html, "Test Company")
    
    if documents:
        logger.info(f"✅ Document parser successfully found {len(documents)} documents")
        
        # Show document details
        for i, doc in enumerate(documents):
            logger.info(f"  Document {i+1}:")
            logger.info(f"    Title: {doc.get('title', 'No title')}")
            logger.info(f"    URL: {doc.get('url', 'No URL')}")
            logger.info(f"    Date: {doc.get('date', 'No date')}")
            logger.info(f"    Type: {doc.get('document_type', 'Unknown type')}")
            
            # Show country info if available
            if 'country_info' in doc and doc['country_info']:
                logger.info(f"    Country: {doc['country_info'].get('country', 'Unknown')}")
    else:
        logger.warning("⚠️ Document parser found no documents in the HTML content")
    
    return documents

def test_document_type_detection():
    """Test document type detection"""
    logger.info("Testing document type detection...")
    
    # Initialize document parser
    document_parser = DocumentParser()
    
    # Test cases
    test_cases = [
        {"title": "Annual Report 2022", "url": "annual_report.pdf", "expected": "Annual Financial Report"},
        {"title": "Q1 Financial Results", "url": "q1_results.xlsx", "expected": "Quarterly Financial Report"},
        {"title": "Company Presentation", "url": "presentation.pptx", "expected": "Presentation"},
        {"title": "Prospectus for Bond Issuance", "url": "prospectus.pdf", "expected": "Prospectus"},
        {"title": "Regular Document", "url": "document.pdf", "expected": "PDF Document"},
    ]
    
    success_count = 0
    for i, test in enumerate(test_cases):
        result = document_parser.detect_document_type(test["title"], test["url"])
        
        if result == test["expected"]:
            logger.info(f"✅ Test {i+1}: Correctly detected '{result}' for '{test['title']}'")
            success_count += 1
        else:
            logger.warning(f"⚠️ Test {i+1}: Expected '{test['expected']}' but got '{result}' for '{test['title']}'")
    
    logger.info(f"Document type detection tests: {success_count}/{len(test_cases)} passed")

def test_country_detection():
    """Test country information detection"""
    logger.info("Testing country detection...")
    
    # Initialize document parser
    document_parser = DocumentParser()
    
    # Test cases
    test_cases = [
        {"title": "Estonia Annual Report", "url": "estonia_report.pdf", "expected": "Estonia"},
        {"title": "Financial Results", "url": "latvia/report.pdf", "expected": "Latvia"},
        {"title": "Polish Quarterly Report", "url": "poland.xlsx", "expected": "Poland"},
        {"title": "Report for UK Operations", "url": "uk_report.pdf", "expected": "United Kingdom"},
        {"title": "No Country Report", "url": "report.pdf", "expected": None},
    ]
    
    success_count = 0
    for i, test in enumerate(test_cases):
        result = document_parser.detect_country_info(test["title"], test["url"])
        country = result.get('country') if result else None
        
        if (country == test["expected"]) or (not country and not test["expected"]):
            logger.info(f"✅ Test {i+1}: Correctly detected '{country}' for '{test['title']}'")
            success_count += 1
        else:
            logger.warning(f"⚠️ Test {i+1}: Expected '{test['expected']}' but got '{country}' for '{test['title']}'")
    
    logger.info(f"Country detection tests: {success_count}/{len(test_cases)} passed")

def main():
    """Main test function"""
    logger.info("Starting simple test of refactored document parser")
    
    # Test document parser
    test_document_parser()
    
    # Test document type detection
    test_document_type_detection()
    
    # Test country detection
    test_country_detection()
    
    logger.info("Simple test completed")

if __name__ == "__main__":
    main()