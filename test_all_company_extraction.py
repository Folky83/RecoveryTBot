"""
Test document extraction on a wider range of companies to identify failures
"""
import json
import logging
import requests
import time
import sys
from datetime import datetime
from bot.document_scraper import DocumentScraper
from bot.data_manager import DataManager
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_all_company_extraction")

def test_company_extraction(company_list):
    """
    Test document extraction on a specific list of companies
    
    Args:
        company_list: Dictionary mapping company IDs to names
        
    Returns:
        Results dictionary with success and failure information
    """
    logger.info(f"Starting document extraction test for {len(company_list)} companies")
    
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Results dictionary
    results = {
        "success": {},
        "failure": {},
        "stats": {
            "total_companies": len(company_list),
            "successful_extractions": 0,
            "failed_extractions": 0,
            "total_documents_found": 0,
            "test_date": datetime.now().isoformat(),
        }
    }
    
    # Test each company
    total = len(company_list)
    count = 0
    
    for company_id, company_name in company_list.items():
        count += 1
        logger.info(f"Testing company {count}/{total}: {company_name} (ID: {company_id})")
        
        # Construct URLs to try
        urls = [
            f"https://www.mintos.com/en/loan-originators/{company_id}/",
            f"https://www.mintos.com/en/lending-companies/{company_id}/"
        ]
        
        documents = []
        success = False
        error_message = None
        response_time = 0
        success_url = None
        
        # Try each URL
        for url in urls:
            try:
                logger.info(f"Trying URL: {url}")
                start_time = time.time()
                
                # Make a direct request to get HTML
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    # Parse the HTML for documents
                    html_content = response.text
                    documents = scraper._parse_documents(html_content, company_name)
                    
                    end_time = time.time()
                    response_time = end_time - start_time
                    
                    if documents:
                        logger.info(f"Successfully extracted {len(documents)} documents from {url}")
                        success = True
                        success_url = url
                        break
                    else:
                        logger.warning(f"No documents found at {url}")
                else:
                    logger.warning(f"Failed to access {url}: HTTP {response.status_code}")
                    if not error_message:
                        error_message = f"HTTP status {response.status_code}"
            
            except Exception as e:
                current_url = url  # Store current URL to prevent possible unbinding
                logger.error(f"Error processing {current_url}: {e}")
                if not error_message:
                    error_message = str(e)
        
        # Record the results
        if success:
            results["success"][company_id] = {
                "company_name": company_name,
                "document_count": len(documents),
                "response_time": response_time,
                "success_url": success_url,
                "sample_documents": documents[:3] if documents else []
            }
            results["stats"]["successful_extractions"] += 1
            results["stats"]["total_documents_found"] += len(documents)
        else:
            results["failure"][company_id] = {
                "company_name": company_name,
                "error": error_message or "Unknown error"
            }
            results["stats"]["failed_extractions"] += 1
        
        # Add a short delay to avoid hitting rate limits
        time.sleep(1)
        
        # Print progress to console
        sys.stdout.write(f"\rCompanies processed: {count}/{total} - Success: {results['stats']['successful_extractions']}, Failures: {results['stats']['failed_extractions']}")
        sys.stdout.flush()
    
    # Complete progress line
    sys.stdout.write("\n")
    
    # Calculate statistics
    results["stats"]["success_rate"] = (results["stats"]["successful_extractions"] / results["stats"]["total_companies"]) * 100 if results["stats"]["total_companies"] > 0 else 0
    results["stats"]["average_documents_per_company"] = results["stats"]["total_documents_found"] / results["stats"]["successful_extractions"] if results["stats"]["successful_extractions"] > 0 else 0
    
    return results

def test_all_company_extraction():
    """Test document extraction across all available companies"""
    # Create data manager
    data_manager = DataManager()
    
    # Load company mapping
    company_mapping = data_manager.load_company_mapping()
    logger.info(f"Loaded {len(company_mapping)} companies from mapping")
    
    # Add some additional test companies
    additional_companies = {
        "creditstar": "Creditstar",
        "sebo": "Sebo",
        "akulaku": "Akulaku",
        "credius": "Credius",
        "dineo": "Dineo",
        "kviku": "Kviku",
        "placet-group": "Placet Group",
        "eleving-group": "Eleving Group",
        "delfin-group": "Delfin Group",
        "novaloans": "NovaLoans",
        "mogo": "Mogo",
        "sun-finance": "Sun Finance",
        "capitalia": "Capitalia",
        "henceforth": "HenceForth"
    }
    
    for company_id, company_name in additional_companies.items():
        if company_id not in company_mapping:
            company_mapping[company_id] = company_name
    
    logger.info(f"Total companies to test: {len(company_mapping)}")
    
    # Execute the test in smaller batches
    results = test_company_extraction(company_mapping)
    
    # Save results to a file
    output_file = "all_company_extraction_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving results: {e}")
    
    return results

if __name__ == "__main__":
    # Create a smaller subset of companies to test
    test_companies = {
        "wowwo": "Wowwo",
        "creditstar": "Creditstar",
        "sebo": "Sebo",
        "akulaku": "Akulaku",
        "credius": "Credius",
        "dineo": "Dineo",
        "kviku": "Kviku",
        "placet-group": "Placet Group",
        "eleving-group": "Eleving Group",
        "delfin-group": "Delfin Group"
    }
    
    results = test_company_extraction(test_companies)
    
    print("\n\nDocument Extraction Test Summary:")
    print(f"Total companies: {results['stats']['total_companies']}")
    print(f"Successful extractions: {results['stats']['successful_extractions']} ({results['stats']['success_rate']:.1f}%)")
    print(f"Failed extractions: {results['stats']['failed_extractions']}")
    print(f"Total documents found: {results['stats']['total_documents_found']}")
    print(f"Average documents per company: {results['stats']['average_documents_per_company']:.1f}")
    
    print("\nFailed companies:")
    for company_id, data in results["failure"].items():
        print(f"- {data['company_name']} (ID: {company_id}): {data['error']}")
        
    # Save results to a file
    output_file = "company_extraction_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {output_file}")
    except Exception as e:
        print(f"\nError saving results: {e}")