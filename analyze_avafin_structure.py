#!/usr/bin/env python3
"""
Script to analyze the structure of a Mintos company page to identify
document card patterns for Presentation, Financials, and Loan Agreement
"""
import logging
import json
import re
from bs4 import BeautifulSoup, Comment

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('analyze_structure')

def get_document_count(html_content):
    """Count references to document types"""
    terms = {
        'presentation': ['presentation', 'company presentation', 'investor presentation'],
        'financials': ['financials', 'financial reports', 'financial statements'],
        'loan_agreement': ['loan agreement', 'assignment agreement', 'credit agreement']
    }
    
    results = {}
    soup = BeautifulSoup(html_content, 'html.parser')
    page_text = soup.get_text().lower()
    
    for doc_type, keywords in terms.items():
        count = 0
        for keyword in keywords:
            count += page_text.count(keyword.lower())
        results[doc_type] = count
    
    return results

def find_vue_data(html_content):
    """Try to extract Vue.js data structures that might contain document info"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Look for script tags with Vue data
    scripts = soup.find_all('script')
    data_patterns = []
    
    for script in scripts:
        if script.string:
            # Look for data structures with our document types
            for pattern in [
                r'(presentation|financials|loan\s+agreement)',
                r'(\.pdf)',
                r'(documents\s*:)',
                r'(document\s*:)'
            ]:
                if re.search(pattern, script.string, re.I):
                    # Extract potential data objects
                    data_patterns.append(script.string)
                    break
    
    # Also look for JSON data in commented sections (sometimes frameworks do this)
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    for comment in comments:
        if 'presentation' in comment.lower() or 'financials' in comment.lower() or 'loan agreement' in comment.lower():
            data_patterns.append(f"COMMENT: {comment}")
    
    return data_patterns

def find_document_cards(html_content):
    """Look for card-like structures that might contain document links"""
    soup = BeautifulSoup(html_content, 'html.parser')
    card_candidates = []
    
    # Look for div elements that might be cards
    for div in soup.find_all('div', class_=True):
        class_attr = ' '.join(div.get('class', []))
        # Look for common card class names
        if 'card' in class_attr.lower() or 'document' in class_attr.lower() or 'item' in class_attr.lower():
            text = div.get_text(strip=True)
            # Only keep divs with our document keywords
            if ('presentation' in text.lower() or 'financials' in text.lower() or 
                'loan' in text.lower() or 'agreement' in text.lower()):
                
                # Get any links inside this card
                links = []
                for a in div.find_all('a', href=True):
                    href = a.get('href', '')
                    if href and ('.pdf' in href.lower()):
                        links.append({
                            'text': a.get_text(strip=True),
                            'href': href
                        })
                
                card_candidates.append({
                    'class': class_attr,
                    'text': text[:100] + ('...' if len(text) > 100 else ''),
                    'links': links
                })
    
    return card_candidates

def find_document_containers(html_content):
    """Look for container elements that group documents together"""
    soup = BeautifulSoup(html_content, 'html.parser')
    containers = []
    
    # Look for sections that might contain document groups
    for section in soup.find_all(['section', 'div']):
        # Check if this section contains multiple document types
        text = section.get_text(strip=True).lower()
        
        if (('presentation' in text and 'financials' in text) or
            ('presentation' in text and 'agreement' in text) or
            ('financials' in text and 'agreement' in text)):
            
            # This section contains multiple document types - could be a container
            pdf_links = []
            for a in section.find_all('a', href=True):
                href = a.get('href', '')
                if href and '.pdf' in href.lower():
                    pdf_links.append({
                        'text': a.get_text(strip=True),
                        'href': href
                    })
            
            if pdf_links:
                containers.append({
                    'id': section.get('id', ''),
                    'class': ' '.join(section.get('class', [])),
                    'pdf_links': pdf_links,
                    'text_snippet': text[:150] + ('...' if len(text) > 150 else '')
                })
    
    return containers

def analyze_pdf_links(html_content):
    """Analyze all PDF links and their surrounding context"""
    soup = BeautifulSoup(html_content, 'html.parser')
    pdf_links = []
    
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if href and '.pdf' in href.lower():
            # Get the link text
            link_text = a.get_text(strip=True)
            
            # Get parent element's text for context
            parent_text = ""
            parent = a.parent
            if parent:
                parent_text = parent.get_text(strip=True)
            
            # Look for a heading above this link
            heading = None
            prev = a
            for _ in range(5):  # Look at 5 previous elements max
                prev = prev.previous_element
                if prev and prev.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    heading = prev.get_text(strip=True)
                    break
            
            # Try to determine document type
            doc_type = 'unknown'
            if 'presentation' in link_text.lower() or 'presentation' in parent_text.lower():
                doc_type = 'presentation'
            elif 'financials' in link_text.lower() or 'financial' in parent_text.lower():
                doc_type = 'financials'
            elif 'loan agreement' in link_text.lower() or 'loan agreement' in parent_text.lower():
                doc_type = 'loan_agreement'
            elif 'agreement' in link_text.lower() or 'agreement' in parent_text.lower():
                doc_type = 'loan_agreement'  # Assume loan_agreement for any agreement
            
            pdf_links.append({
                'href': href,
                'text': link_text,
                'parent_text': parent_text[:100] + ('...' if len(parent_text) > 100 else ''),
                'heading': heading,
                'probable_type': doc_type
            })
    
    return pdf_links

def analyze_html_structure(html_content):
    """Analyze HTML structure to understand document patterns"""
    results = {
        'document_counts': get_document_count(html_content),
        'document_cards': find_document_cards(html_content),
        'document_containers': find_document_containers(html_content),
        'pdf_links': analyze_pdf_links(html_content)
    }
    
    return results

def main():
    """Main function to analyze the AvaFin page"""
    try:
        with open('data/AvaFin_page.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        logger.info("Analyzing AvaFin page structure")
        
        results = analyze_html_structure(html_content)
        
        # Print summary
        print("\n=== DOCUMENT REFERENCES COUNT ===")
        for doc_type, count in results['document_counts'].items():
            print(f"{doc_type}: {count} references")
        
        print("\n=== PDF LINKS ANALYSIS ===")
        doc_types = {
            'presentation': 0,
            'financials': 0,
            'loan_agreement': 0,
            'unknown': 0
        }
        
        print("\nDetailed PDF Links:")
        for i, link in enumerate(results['pdf_links'], 1):
            print(f"\n{i}. {link['text']} ({link['probable_type']})")
            print(f"   URL: {link['href']}")
            if link['heading']:
                print(f"   Heading: {link['heading']}")
            print(f"   Context: {link['parent_text']}")
            
            doc_types[link['probable_type']] += 1
        
        print("\nSummary by document type:")
        for doc_type, count in doc_types.items():
            print(f"{doc_type}: {count} links")
        
        # Save detailed results to file
        with open('data/avafin_analysis.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        logger.info("Analysis saved to data/avafin_analysis.json")
        
    except Exception as e:
        logger.error(f"Error analyzing page: {e}", exc_info=True)

if __name__ == "__main__":
    main()