"""
Test the simplified company URL extraction function
"""
import os
import json
import logging
from bot.fetch_company_urls_simplified import fetch_company_urls_from_details

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_simplified_extraction():
    """Test the simplified URL extraction function"""
    logger.info("Testing simplified company URL extraction")
    
    # Run the extraction
    companies = fetch_company_urls_from_details()
    
    # Check results
    logger.info(f"Extracted {len(companies)} companies")
    
    # Check specific companies
    key_companies = [
        "alexcredit",
        "creditstar", 
        "eleving-group", 
        "finko", 
        "iute-group", 
        "mogo", 
        "sun-finance", 
        "wowwo"
    ]
    
    # Check that key companies are in the results
    found_key_companies = []
    missing_key_companies = []
    
    for company_id in key_companies:
        if company_id in companies:
            found_key_companies.append(company_id)
            logger.info(f"Found key company: {company_id} ({companies[company_id]['name']})")
        else:
            missing_key_companies.append(company_id)
            logger.warning(f"Missing key company: {company_id}")
    
    # Report success rate
    success_rate = len(found_key_companies) / len(key_companies) * 100
    logger.info(f"Found {len(found_key_companies)}/{len(key_companies)} key companies ({success_rate:.1f}%)")
    
    if len(missing_key_companies) > 0:
        logger.warning(f"Missing companies: {', '.join(missing_key_companies)}")
    else:
        logger.info("All key companies found successfully!")
    
    # Save the full results to a JSON file for inspection
    with open("simplified_extraction_results.json", "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2)
    logger.info(f"Saved full results to simplified_extraction_results.json")
    
    return companies

if __name__ == "__main__":
    test_simplified_extraction()