"""
Test different document extraction approaches without relying on live JS rendering
This script tests the document parser with different input strategies.
"""
import json
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from bot.document_scraper import DocumentScraper
from bot.logger import setup_logger

# Set up logger
logger = setup_logger("test_document_extraction")

def test_document_extraction():
    """Test document extraction with different approaches"""
    logger.info("Starting document extraction test")
    
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # Test URLs for several companies
    test_companies = [
        {"id": "wowwo", "name": "Wowwo", "url": "https://www.mintos.com/en/loan-originators/wowwo/"},
        {"id": "creditstar", "name": "Creditstar", "url": "https://www.mintos.com/en/loan-originators/creditstar/"},
        {"id": "sebo", "name": "Sebo", "url": "https://www.mintos.com/en/loan-originators/sebo/"}
    ]
    
    results = {}
    
    for company in test_companies:
        company_id = company["id"]
        company_name = company["name"]
        company_url = company["url"]
        
        logger.info(f"Testing document extraction for {company_name} (URL: {company_url})")
        
        # Make a direct request to get HTML
        try:
            response = requests.get(company_url, timeout=10)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Test 1: Direct document parsing
                start_time = datetime.now()
                documents_direct = scraper._parse_documents(html_content, company_name)
                end_time = datetime.now()
                duration_direct = (end_time - start_time).total_seconds()
                
                logger.info(f"Direct parsing found {len(documents_direct)} documents in {duration_direct:.2f} seconds")
                
                # Test 2: Try to extract document links directly from HTML
                start_time = datetime.now()
                pdf_links = []
                soup = BeautifulSoup(html_content, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if href and any(href.lower().endswith(ext) for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls']):
                        title = link.get_text(strip=True) or href.split('/')[-1]
                        pdf_links.append({
                            'title': title,
                            'url': href if href.startswith('http') else f"https://www.mintos.com{href}" if href.startswith('/') else f"https://www.mintos.com/{href}"
                        })
                
                end_time = datetime.now()
                duration_links = (end_time - start_time).total_seconds()
                
                logger.info(f"Direct link extraction found {len(pdf_links)} document links in {duration_links:.2f} seconds")
                
                # Save results
                results[company_id] = {
                    "company_name": company_name,
                    "url": company_url,
                    "direct_parse_count": len(documents_direct),
                    "direct_parse_time": duration_direct,
                    "link_extraction_count": len(pdf_links),
                    "link_extraction_time": duration_links,
                    "direct_parse_documents": documents_direct[:5],  # Save first 5 for sample
                    "link_extraction_documents": pdf_links[:5]  # Save first 5 for sample
                }
                
            else:
                logger.error(f"Failed to fetch company page for {company_name}: {response.status_code}")
                results[company_id] = {
                    "company_name": company_name,
                    "url": company_url,
                    "error": f"HTTP status {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Error testing {company_name}: {e}")
            results[company_id] = {
                "company_name": company_name,
                "url": company_url,
                "error": str(e)
            }
    
    # Save results to a file
    output_file = "document_extraction_test_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving results: {e}")
        
    return results

if __name__ == "__main__":
    results = test_document_extraction()
    
    print("\nDocument Extraction Test Results:\n")
    
    for company_id, data in results.items():
        print(f"Company: {data.get('company_name')}")
        print(f"URL: {data.get('url')}")
        
        if 'error' in data:
            print(f"Error: {data['error']}")
        else:
            print(f"Direct parsing found {data['direct_parse_count']} documents in {data['direct_parse_time']:.2f} seconds")
            print(f"Link extraction found {data['link_extraction_count']} document links in {data['link_extraction_time']:.2f} seconds")
            
            # Show sample of documents
            if data['direct_parse_documents']:
                print("\nSample documents from direct parsing:")
                for i, doc in enumerate(data['direct_parse_documents'][:3]):
                    print(f"  {i+1}. {doc.get('title', 'N/A')} - {doc.get('url', 'N/A')}")
            
            if data['link_extraction_documents']:
                print("\nSample documents from link extraction:")
                for i, doc in enumerate(data['link_extraction_documents'][:3]):
                    print(f"  {i+1}. {doc.get('title', 'N/A')} - {doc.get('url', 'N/A')}")
                    
        print("\n" + "-"*50 + "\n")