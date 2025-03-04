"""
Test the enhanced document scraper with improved URL variation handling
"""
from bot.document_scraper import DocumentScraper
import json
import os

def test_enhanced_scraper():
    """Test document extraction with the enhanced URL variation handling"""
    # Create document scraper instance
    scraper = DocumentScraper()
    
    # List of problematic companies to test
    test_companies = [
        {"id": "iuvo", "name": "Iuvo"},
        {"id": "iuvo-group", "name": "Iuvo Group"},
        {"id": "eleving", "name": "Eleving"},
        {"id": "eleving-group", "name": "Eleving Group"},
        {"id": "mogo", "name": "Mogo"},
        {"id": "delfin", "name": "Delfin"},
        {"id": "delfin-group", "name": "Delfin Group"},
        {"id": "creditstar", "name": "Creditstar"},  # Known working company for comparison
        {"id": "wowwo", "name": "Wowwo"}  # Known working company for comparison
    ]
    
    results = {}
    
    for company in test_companies:
        company_id = company["id"]
        company_name = company["name"]
        
        print(f"\nTesting {company_name} (ID: {company_id})...")
        
        # Generate URL variations
        url_variations = scraper._generate_url_variations(company_id, company_name)
        print(f"Generated {len(url_variations)} URL variations")
        
        # Try to get documents
        documents = scraper.get_company_documents(company_id, company_name)
        
        # Print and store results
        if documents:
            print(f"SUCCESS: Found {len(documents)} documents for {company_name}")
            print("Document titles:")
            for doc in documents[:5]:  # Print first 5 docs
                print(f"- {doc.get('title', 'Untitled')} ({doc.get('date', 'No date')})")
            
            results[company_id] = {
                "success": True,
                "name": company_name,
                "document_count": len(documents),
                "documents": documents[:3]  # Include first 3 docs for reference
            }
        else:
            print(f"FAILURE: Could not find any documents for {company_name}")
            results[company_id] = {
                "success": False,
                "name": company_name,
                "document_count": 0,
                "documents": []
            }
    
    # Save detailed results to JSON file
    output_file = "enhanced_scraper_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")
    
    # Print summary
    print("\nSUMMARY:")
    success_count = sum(1 for company_id, result in results.items() if result["success"])
    print(f"Success: {success_count} / {len(test_companies)} companies")
    
    print("\nSuccessful companies:")
    for company_id, result in results.items():
        if result["success"]:
            print(f"- {result['name']}: {result['document_count']} documents")
    
    print("\nFailed companies:")
    for company_id, result in results.items():
        if not result["success"]:
            print(f"- {result['name']}")
    
    return results

if __name__ == "__main__":
    test_enhanced_scraper()