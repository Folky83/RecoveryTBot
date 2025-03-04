"""
Script to directly trigger document checking in the bot
"""
import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path to import bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import bot modules
from bot.telegram_bot import MintosBot

async def test_document_check():
    """Test document checking functionality"""
    print(f"Starting document check test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize bot (singleton pattern will return existing instance)
    bot = MintosBot()
    
    # Make sure bot is initialized
    if not await bot.initialize():
        print("Failed to initialize bot")
        return
    
    print("Checking for document updates...")
    # Directly call the check_documents method
    new_documents = await bot.check_documents()
    
    print(f"Found {len(new_documents)} new documents")
    
    # Print new document details
    for i, doc in enumerate(new_documents):
        print(f"\nDocument {i+1}:")
        for key, value in doc.items():
            print(f"  {key}: {value}")
        
        # Format message the way the bot would
        message = bot.format_document_message(doc)
        print("\nFormatted message:")
        print(message)
    
    print(f"\nDocument check test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

async def main():
    await test_document_check()

if __name__ == "__main__":
    asyncio.run(main())