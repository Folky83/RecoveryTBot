#!/usr/bin/env python3
"""
Simple test for RSS feeds functionality
"""
import asyncio
import sys
sys.path.insert(0, '.')

async def test_feeds():
    """Test RSS feeds"""
    from mintos_bot.rss_reader import RSSReader
    
    print("Testing RSS feeds...")
    rss = RSSReader()
    
    # Test individual feeds
    for source, url in rss.feed_urls.items():
        print(f"\nTesting {source} feed...")
        try:
            items = await rss.fetch_single_feed(source, url)
            print(f"  ✓ {source}: {len(items)} items fetched")
            if items:
                print(f"  Latest: {items[0].title[:50]}...")
        except Exception as e:
            print(f"  ✗ {source}: Error - {e}")

if __name__ == "__main__":
    asyncio.run(test_feeds())