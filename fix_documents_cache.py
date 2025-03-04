#!/usr/bin/env python3
"""
Convert documents_cache.json from list format to dictionary format
"""
import os
import json
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DOCUMENTS_CACHE_FILE = "data/documents_cache.json"
DOCUMENTS_BACKUP_FILE = "data/documents_cache_backup.json"
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

def convert_document_format():
    """Convert documents_cache.json from list format to dictionary format"""
    # First, make a backup of the current file
    documents = read_json_file(DOCUMENTS_CACHE_FILE, [])
    write_json_file(DOCUMENTS_BACKUP_FILE, documents)
    logger.info(f"Created backup at {DOCUMENTS_BACKUP_FILE}")
    
    # If already a dict, do nothing
    if isinstance(documents, dict):
        logger.info("Document cache is already in dictionary format")
        return
    
    # Get company mapping
    company_mapping = read_json_file(COMPANY_MAPPING_FILE, {})
    
    # Convert list to dictionary
    documents_dict = {}
    for doc in documents:
        # Get company name
        company_name = doc.get('company_name')
        if not company_name:
            continue
        
        # Create company ID
        company_id = None
        
        # Try to find in mapping
        for cid, cname in company_mapping.items():
            if cname.lower() == company_name.lower():
                company_id = cid
                break
        
        # If not found in mapping, create from company name
        if company_id is None:
            # Create a slug for the company name
            company_id = re.sub(r'[^a-z0-9]', '-', company_name.lower())
            company_id = re.sub(r'-+', '-', company_id).strip('-')
        
        # Initialize company dict if needed
        if company_id not in documents_dict:
            documents_dict[company_id] = []
        
        # Add document to company
        documents_dict[company_id].append(doc)
    
    # Write the new format
    write_json_file(DOCUMENTS_CACHE_FILE, documents_dict)
    logger.info(f"Converted document cache to dictionary format with {len(documents_dict)} companies")

def main():
    """Main function"""
    logger.info("Starting document cache format conversion")
    convert_document_format()
    logger.info("Completed document cache format conversion")

if __name__ == "__main__":
    main()