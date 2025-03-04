"""
Test JavaScript rendering on a sample company page with a timeout
"""
import json
import signal
import logging
import requests
from datetime import datetime
from bot.document_scraper import DocumentScraper
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_js_rendering")

# Define a timeout handler
class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Function call timed out")

def test_js_rendering(company_id="wowwo", max_time=60):
    """
    Test JavaScript rendering with a timeout
    
    Args:
        company_id: ID of the company to test
        max_time: Maximum execution time in seconds
    """
    # Set up the timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(max_time)
    
    try:
        # Create document scraper instance
        scraper = DocumentScraper()
        
        # Company details
        company_name = company_id.replace('-', ' ').title()
        company_url = f"https://www.mintos.com/en/loan-originators/{company_id}/"
        
        logger.info(f"Testing JS rendering for {company_name} (URL: {company_url})")
        logger.info(f"Maximum execution time: {max_time} seconds")
        
        # First try with JavaScript rendering
        start_time = datetime.now()
        
        # Make a direct request first to verify the URL is accessible
        logger.info("Checking URL accessibility with simple request...")
        response = requests.get(company_url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"URL not accessible: {company_url} (status code: {response.status_code})")
            return []
        
        logger.info(f"URL is accessible (status code: {response.status_code})")
        logger.info("Testing document extraction with JavaScript rendering...")
        
        # Use JS rendering to get content
        html_content = scraper._make_request(company_url, use_js_rendering=True)
        
        if not html_content:
            logger.error("JavaScript rendering failed to return content")
            return []
        
        # Parse the JS-rendered content
        documents = scraper._parse_documents(html_content, company_name)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"JS rendering document extraction completed in {duration:.2f} seconds")
        logger.info(f"Found {len(documents)} documents with JavaScript rendering")
        
        # Compare with direct request without JS
        start_time = datetime.now()
        direct_html = response.text  # Use the content from the earlier request
        direct_documents = scraper._parse_documents(direct_html, company_name)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"Direct document extraction completed in {duration:.2f} seconds")
        logger.info(f"Found {len(direct_documents)} documents without JavaScript rendering")
        
        # Compare document counts
        if len(documents) > len(direct_documents):
            logger.info(f"JavaScript rendering found {len(documents) - len(direct_documents)} more documents")
        elif len(documents) < len(direct_documents):
            logger.warning(f"JavaScript rendering found {len(direct_documents) - len(documents)} FEWER documents")
        else:
            logger.info("Both methods found the same number of documents")
        
        # Save results to files
        try:
            with open(f"{company_id}_js_documents.json", 'w', encoding='utf-8') as f:
                json.dump(documents, f, indent=2)
            with open(f"{company_id}_direct_documents.json", 'w', encoding='utf-8') as f:
                json.dump(direct_documents, f, indent=2)
            logger.info("Results saved to files")
        except Exception as e:
            logger.error(f"Error saving results: {e}")
        
        return documents
    
    except TimeoutError:
        logger.error(f"Test timed out after {max_time} seconds")
        return []
    except Exception as e:
        logger.error(f"Error in test: {e}")
        return []
    finally:
        # Cancel the alarm
        signal.alarm(0)

if __name__ == "__main__":
    # Test with a 30-second timeout
    documents = test_js_rendering(max_time=30)
    
    print(f"\nFound {len(documents)} documents with JavaScript rendering")
    
    if documents:
        print("\nSample of the first 3 documents found:")
        sample_count = min(3, len(documents))
        
        for i, doc in enumerate(documents[:sample_count]):
            print(f"\nDocument {i+1}:")
            print(f"  - Title: {doc.get('title', 'N/A')}")
            print(f"  - Date: {doc.get('date', 'N/A')}")
            print(f"  - Type: {doc.get('document_type', 'N/A')}")
            print(f"  - URL: {doc.get('url', 'N/A')}")
    else:
        print("\nNo documents found or test timed out")