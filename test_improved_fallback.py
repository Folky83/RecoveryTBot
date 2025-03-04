"""
Test improved fallback mapping system for problematic companies
"""
import json
import logging
import sys
import os
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def load_fallback_mapping() -> Dict[str, Any]:
    """Load the company fallback mapping from the JSON file"""
    try:
        with open("company_fallback_mapping.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading fallback mapping: {e}")
        return {}

def get_direct_urls_for_company(company_id: str, fallback_mapping: Dict[str, Any]) -> List[str]:
    """Get all direct URLs for a company from the fallback mapping"""
    direct_urls = []
    
    # Check direct entry
    if company_id in fallback_mapping:
        if "alt_urls" in fallback_mapping[company_id]:
            direct_urls.extend(fallback_mapping[company_id]["alt_urls"])
            
        # Check redirect
        if "redirect_id" in fallback_mapping[company_id]:
            redirect_id = fallback_mapping[company_id]["redirect_id"]
            if redirect_id in fallback_mapping and "alt_urls" in fallback_mapping[redirect_id]:
                direct_urls.extend(fallback_mapping[redirect_id]["alt_urls"])
    
    # Check two-way mappings
    for mapped_id, info in fallback_mapping.items():
        if "alt_ids" in info and company_id in info["alt_ids"] and "alt_urls" in info:
            direct_urls.extend(info["alt_urls"])
    
    # Remove duplicates while preserving order
    return list(dict.fromkeys(direct_urls))

def check_url(url: str) -> Dict[str, Any]:
    """Check if a URL is accessible and contains document sections"""
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        
        response = session.get(url, timeout=10)
        if response.status_code != 200:
            return {
                "accessible": False, 
                "status_code": response.status_code,
                "error": f"HTTP error: {response.status_code}"
            }
        
        # Check for document indicators
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for document sections
        doc_sections = soup.find_all('div', class_=['document-list', 'loan-originator-info__documents'])
        
        # Look for PDF links
        pdf_links = soup.find_all('a', href=lambda href: href and (href.lower().endswith('.pdf') or '.pdf' in href.lower()))
        
        # Look for document keywords
        doc_keywords = ['document', 'financial', 'report', 'presentation', 'prospectus', 'download']
        has_doc_keywords = any(keyword in response.text.lower() for keyword in doc_keywords)
        
        return {
            "accessible": True,
            "has_document_sections": len(doc_sections) > 0,
            "has_pdf_links": len(pdf_links) > 0,
            "has_document_keywords": has_doc_keywords,
            "title": soup.title.string if soup.title else None,
            "content_length": len(response.text)
        }
    except Exception as e:
        return {
            "accessible": False,
            "error": str(e)
        }

def test_improved_fallback_system():
    """Test the improved fallback mapping system"""
    
    # Companies to test - focusing on problematic ones
    problem_companies = {
        "iuvo": "Iuvo",
        "iuvo-group": "Iuvo Group",
        "finko": "Finko",
        "eleving": "Eleving",
        "eleving-group": "Eleving Group",
        "mogo": "Mogo",
        "creditstar": "Creditstar",
        "creditstar-group": "Creditstar Group",
        "delfin": "Delfin",
        "delfin-group": "Delfin Group"
    }
    
    # Load fallback mapping
    fallback_mapping = load_fallback_mapping()
    
    # Results dictionary
    results = {
        "success": {},
        "failure": {}
    }
    
    # Test each company
    for company_id, company_name in problem_companies.items():
        logger.info(f"Testing URLs for {company_name} (ID: {company_id})...")
        
        # Get direct URLs for this company
        direct_urls = get_direct_urls_for_company(company_id, fallback_mapping)
        
        if direct_urls:
            logger.info(f"Found {len(direct_urls)} direct URLs for {company_id}")
            
            successful_urls = []
            for url in direct_urls:
                logger.info(f"Checking URL: {url}")
                check_result = check_url(url)
                
                if check_result["accessible"]:
                    logger.info(f"URL is accessible: {url}")
                    
                    # Check for document indicators
                    has_documents = (check_result.get("has_document_sections", False) or 
                                    check_result.get("has_pdf_links", False) or 
                                    check_result.get("has_document_keywords", False))
                    
                    if has_documents:
                        logger.info(f"URL likely contains documents: {url}")
                        successful_urls.append({
                            "url": url,
                            "indicators": {
                                "doc_sections": check_result.get("has_document_sections", False),
                                "pdf_links": check_result.get("has_pdf_links", False),
                                "doc_keywords": check_result.get("has_document_keywords", False)
                            }
                        })
                else:
                    logger.warning(f"URL not accessible: {url} - {check_result.get('error', 'Unknown error')}")
            
            if successful_urls:
                results["success"][company_id] = {
                    "company_name": company_name,
                    "successful_urls": successful_urls,
                    "url_count": len(successful_urls)
                }
                logger.info(f"Success! Found {len(successful_urls)} working URLs for {company_name}")
            else:
                results["failure"][company_id] = {
                    "company_name": company_name,
                    "error": "No accessible URLs with document indicators found"
                }
        else:
            logger.warning(f"No direct URLs found for {company_name}")
            results["failure"][company_id] = {
                "company_name": company_name,
                "error": "No direct URLs in fallback mapping"
            }
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"improved_fallback_results_{timestamp}.json"
    
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {results_file}")
    
    # Print summary
    logger.info("\n--- SUMMARY ---")
    logger.info(f"Total companies tested: {len(problem_companies)}")
    logger.info(f"Successful: {len(results['success'])}")
    logger.info(f"Failed: {len(results['failure'])}")
    
    if results["success"]:
        logger.info("\nSuccessful companies:")
        for company_id, data in results["success"].items():
            logger.info(f"- {data['company_name']}: {data['url_count']} working URLs")
    
    if results["failure"]:
        logger.info("\nFailed companies:")
        for company_id, data in results["failure"].items():
            logger.info(f"- {data['company_name']}: {data['error']}")
            
    return results

if __name__ == "__main__":
    test_improved_fallback_system()