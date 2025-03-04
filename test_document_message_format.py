"""
Test script to verify document message formatting
"""
import sys
import os

# Add parent directory to path to import bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the format_document_message function from the telegram bot
from bot.telegram_bot import MintosBot

def test_message_format():
    """Test document message formatting with company_page_url"""
    # Create test document data
    test_documents = [
        {
            'company_name': 'TestCompany1',
            'type': 'presentation',
            'title': 'Test Presentation',
            'url': 'https://assets.mintos.com/test-presentation.pdf',
            'date': '2025-03-04',
            'company_page_url': 'https://www.mintos.com/en/lending-companies/TestCompany1'
        },
        {
            'company_name': 'TestCompany2',
            'type': 'financials',
            'title': 'Test Financials',
            'url': 'https://assets.mintos.com/test-financials.pdf',
            'date': '2025-03-01',
            # Omit company_page_url to test fallback
        },
        {
            'company_name': 'TestCompany3',
            'type': 'loan_agreement',
            'title': 'Test Loan Agreement',
            'url': 'https://assets.mintos.com/test-agreement.pdf',
            'date': '2025-02-28',
            'company_page_url': 'https://www.mintos.com/en/lending-companies/TestCompany3'
        }
    ]
    
    # Create bot instance
    bot = MintosBot()
    
    # Test message formatting for each document
    print("Testing document message formatting:\n")
    for i, doc in enumerate(test_documents):
        print(f"Document {i+1} - {doc['company_name']} ({doc['type']}):")
        print("Document data:")
        for key, value in doc.items():
            print(f"  {key}: {value}")
        
        # Format the message
        message = bot.format_document_message(doc)
        print("\nFormatted message:")
        print(message)
        print("\n" + "-"*50 + "\n")

if __name__ == "__main__":
    test_message_format()