#!/usr/bin/env python3
"""
Test script to verify RSS tracking works correctly
"""
import json
import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_rss_tracking():
    """Test RSS tracking system"""
    print("Testing RSS tracking system...")
    
    # Check current state
    sent_items_file = 'data/rss_sent_items.json'
    print(f"Checking file: {sent_items_file}")
    
    if os.path.exists(sent_items_file):
        with open(sent_items_file, 'r') as f:
            data = json.load(f)
            print(f"Current sent items count: {len(data)}")
            if data:
                print(f"First few items: {data[:3]}")
    else:
        print("File does not exist")
    
    # Test creating the RSS reader and marking items
    from mintos_bot.rss_reader import RSSReader, RSSItem
    
    rss_reader = RSSReader()
    print(f"RSS Reader loaded {len(rss_reader.sent_items)} sent items")
    
    # Create a test item
    test_item = RSSItem(
        title="Test RSS Item",
        link="https://example.com/test",
        pub_date="Thu, 30 May 2025 06:00:00 +0000",
        guid="test-guid-12345",
        issuer="Test Company"
    )
    
    print(f"Test item GUID: {test_item.guid}")
    print(f"Is test item already sent? {test_item.guid in rss_reader.sent_items}")
    
    # Mark as sent
    print("Marking test item as sent...")
    rss_reader.mark_item_as_sent(test_item)
    
    print(f"RSS Reader now has {len(rss_reader.sent_items)} sent items")
    print(f"Is test item now sent? {test_item.guid in rss_reader.sent_items}")
    
    # Check file again
    if os.path.exists(sent_items_file):
        with open(sent_items_file, 'r') as f:
            data = json.load(f)
            print(f"File now contains {len(data)} items")
            if "test-guid-12345" in data:
                print("✅ Test item successfully saved to file")
            else:
                print("❌ Test item NOT found in file")
    
if __name__ == "__main__":
    test_rss_tracking()