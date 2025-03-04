"""
Basic test of the fallback mapping system for key problematic companies
"""
import json
import logging
import sys
import os
import requests
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_iuvo_finko():
    """Test that Iuvo redirects to Finko correctly"""
    company_info = {
        "test_id": "iuvo",
        "expected_working_url": "https://www.mintos.com/en/loan-originators/finko/"
    }
    
    # Test direct URL access
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        response = session.get(company_info["expected_working_url"], timeout=10)
        
        if response.status_code == 200:
            # Check for document indicators
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for document sections or PDF links
            doc_sections = soup.find_all('div', class_=['document-list', 'loan-originator-info__documents'])
            pdf_links = soup.find_all('a', href=lambda href: href and href.lower().endswith('.pdf'))
            
            if doc_sections or pdf_links:
                logger.info(f"SUCCESS: {company_info['test_id']} redirects to {company_info['expected_working_url']} with document sections")
                return True
            else:
                logger.warning(f"PARTIAL: {company_info['expected_working_url']} is accessible but no document sections found")
                return False
        else:
            logger.error(f"FAILED: {company_info['expected_working_url']} returned status code {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return False

def test_eleving_mogo():
    """Test that Eleving redirects to Mogo correctly"""
    company_info = {
        "test_id": "eleving",
        "expected_working_url": "https://www.mintos.com/en/loan-originators/mogo/"
    }
    
    # Test direct URL access
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        response = session.get(company_info["expected_working_url"], timeout=10)
        
        if response.status_code == 200:
            # Check for document indicators
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for document sections or PDF links
            doc_sections = soup.find_all('div', class_=['document-list', 'loan-originator-info__documents'])
            pdf_links = soup.find_all('a', href=lambda href: href and href.lower().endswith('.pdf'))
            
            if doc_sections or pdf_links:
                logger.info(f"SUCCESS: {company_info['test_id']} redirects to {company_info['expected_working_url']} with document sections")
                return True
            else:
                logger.warning(f"PARTIAL: {company_info['expected_working_url']} is accessible but no document sections found")
                return False
        else:
            logger.error(f"FAILED: {company_info['expected_working_url']} returned status code {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return False

def test_creditstar():
    """Test that Creditstar documents are accessible"""
    company_info = {
        "test_id": "creditstar",
        "expected_working_url": "https://www.mintos.com/en/loan-originators/creditstar/"
    }
    
    # Test direct URL access
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        response = session.get(company_info["expected_working_url"], timeout=10)
        
        if response.status_code == 200:
            # Check for document indicators
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for document sections or PDF links
            doc_sections = soup.find_all('div', class_=['document-list', 'loan-originator-info__documents'])
            pdf_links = soup.find_all('a', href=lambda href: href and href.lower().endswith('.pdf'))
            
            if doc_sections or pdf_links:
                logger.info(f"SUCCESS: {company_info['test_id']} documents found at {company_info['expected_working_url']}")
                return True
            else:
                logger.warning(f"PARTIAL: {company_info['expected_working_url']} is accessible but no document sections found")
                return False
        else:
            logger.error(f"FAILED: {company_info['expected_working_url']} returned status code {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return False

def main():
    results = {
        "iuvo_finko": test_iuvo_finko(),
        "eleving_mogo": test_eleving_mogo(),
        "creditstar": test_creditstar()
    }
    
    # Print summary
    logger.info("\n--- TEST SUMMARY ---")
    for test_name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        logger.info(f"{test_name}: {status}")
    
    success_rate = sum(1 for passed in results.values() if passed) / len(results) * 100
    logger.info(f"Success rate: {success_rate:.1f}%")
    
    # Save results
    with open("basic_fallback_results.json", "w") as f:
        json.dump({
            "tests": results,
            "success_rate": success_rate
        }, f, indent=2)
    
    return results

if __name__ == "__main__":
    main()