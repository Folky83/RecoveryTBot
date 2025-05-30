#!/usr/bin/env python3
"""
Test script for the updated multi-RSS reader functionality
"""
import asyncio
import sys
import os
sys.path.insert(0, '.')

from mintos_bot.rss_reader import RSSReader

async def test_multi_rss():
    """Test the multi-RSS functionality"""
    print("Testing Multi-RSS Reader...")
    
    # Initialize RSS reader
    rss_reader = RSSReader()
    
    # Test fetching from all feeds
    print("\n1. Testing fetch from all feeds...")
    items = await rss_reader.fetch_rss_feed()
    print(f"Total items fetched: {len(items)}")
    
    # Group items by feed source
    by_source = {}
    for item in items:
        source = item.feed_source
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)
    
    # Display stats
    print("\nItems by feed source:")
    for source, source_items in by_source.items():
        print(f"  {source}: {len(source_items)} items")
        if source_items:
            print(f"    Latest: {source_items[0].title[:60]}...")
    
    # Test keyword filtering
    print("\n2. Testing keyword filtering...")
    new_items = rss_reader.get_new_items(items)
    print(f"Items after filtering: {len(new_items)}")
    
    # Show filtered items by source
    filtered_by_source = {}
    for item in new_items:
        source = item.feed_source
        if source not in filtered_by_source:
            filtered_by_source[source] = []
        filtered_by_source[source].append(item)
    
    print("\nFiltered items by feed source:")
    for source, source_items in filtered_by_source.items():
        print(f"  {source}: {len(source_items)} items")
    
    # Test message formatting
    print("\n3. Testing message formatting...")
    if new_items:
        for source in ['nasdaq', 'mintos', 'ffnews']:
            source_items = [item for item in new_items if item.feed_source == source]
            if source_items:
                print(f"\n--- Sample {source} message ---")
                message = rss_reader.format_rss_message(source_items[0])
                print(message)
                break
    
    print("\nTest completed!")

if __name__ == "__main__":
    asyncio.run(test_multi_rss())