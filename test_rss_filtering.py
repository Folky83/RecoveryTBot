#!/usr/bin/env python3
"""
Test script to verify RSS filtering functionality
"""
import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_rss_filtering():
    """Test RSS filtering with current keywords"""
    from mintos_bot.rss_reader import RSSReader
    
    # Create RSS reader instance
    rss_reader = RSSReader()
    
    print(f"Loaded keywords: {rss_reader.get_keywords()}")
    print(f"Number of keywords: {len(rss_reader.keywords)}")
    
    # Fetch RSS feed
    print("\nFetching RSS feed...")
    items = await rss_reader.fetch_rss_feed()
    print(f"Total RSS items fetched: {len(items)}")
    
    # Test filtering
    print("\nTesting keyword filtering...")
    new_items = rss_reader.get_new_items(items)
    print(f"New filtered items: {len(new_items)}")
    
    # Show some examples
    print("\nFirst 5 filtered items:")
    for i, item in enumerate(new_items[:5]):
        print(f"{i+1}. {item.title} - {item.issuer}")

if __name__ == "__main__":
    asyncio.run(test_rss_filtering())