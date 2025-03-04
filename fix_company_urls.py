#!/usr/bin/env python3
"""
Fix the company_urls_cache.json file to include all companies
"""
import os
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
COMPANY_URLS_CACHE = "data/company_urls_cache.json"
COMPANY_URLS_MANUAL = "data/company_urls_manual.json"
COMPANY_MAPPING_FILE = "data/company_mapping.json"

def read_json_file(file_path, default=None):
    """Read JSON file with error handling"""
    if default is None:
        default = {}
    
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return default
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {file_path}")
        return default
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return default

def write_json_file(file_path, data):
    """Write JSON file with error handling"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully wrote to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error writing to {file_path}: {e}")
        return False

def generate_fake_company_urls():
    """Generate fake company URLs for all companies from the mapping file"""
    # Read the mapping file
    company_mapping = read_json_file(COMPANY_MAPPING_FILE, {})
    
    # Read existing URLs cache
    existing_urls = read_json_file(COMPANY_URLS_CACHE, {})
    
    # Read manual URLs
    manual_urls = read_json_file(COMPANY_URLS_MANUAL, {})
    
    # Merge everything
    all_companies = {}
    
    # Start with existing URLs
    for company_id, company_data in existing_urls.items():
        all_companies[company_id] = company_data
    
    # Add manual URLs
    for company_id, company_data in manual_urls.items():
        if company_id not in all_companies:
            all_companies[company_id] = company_data
    
    # Ensure all companies from mapping are included
    for company_id, company_name in company_mapping.items():
        if company_id not in all_companies:
            # Create a fake URL
            url = f"https://www.mintos.com/en/lending-companies/{company_id}"
            all_companies[company_id] = {"name": company_name, "url": url}
    
    # Write the combined data back to the cache file
    write_json_file(COMPANY_URLS_CACHE, all_companies)
    logger.info(f"Updated {COMPANY_URLS_CACHE} with {len(all_companies)} companies")

def main():
    """Main function"""
    logger.info("Starting company URL fix")
    generate_fake_company_urls()
    logger.info("Completed company URL fix")

if __name__ == "__main__":
    main()