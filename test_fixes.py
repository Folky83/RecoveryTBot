#!/usr/bin/env python3
"""
Quick test script to verify the critical fixes are working
"""
import asyncio
import logging
import sys
import os

# Add bot directory to path
sys.path.insert(0, '.')

async def test_imports():
    """Test that all imports work correctly"""
    print("Testing imports...")
    
    try:
        from bot.constants import LOCK_FILE, STREAMLIT_PORT
        print("✓ Constants import successful")
        
        from bot.utils import safe_get_text, safe_get_attribute, FileBackupManager
        print("✓ Utils import successful")
        
        from bot.document_scraper import DocumentScraper
        print("✓ Document scraper import successful")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

async def test_document_scraper():
    """Test basic document scraper functionality"""
    print("\nTesting document scraper...")
    
    try:
        scraper = DocumentScraper()
        print("✓ Document scraper initialization successful")
        
        # Test cache age (should return infinity if no cache file)
        age = scraper.get_cache_age()
        print(f"✓ Cache age check successful: {age}")
        
        return True
    except Exception as e:
        print(f"✗ Document scraper test failed: {e}")
        return False

async def test_utils():
    """Test utility functions"""
    print("\nTesting utility functions...")
    
    try:
        from bot.utils import SafeElementHandler, create_unique_id
        
        # Test URL normalization
        test_url = SafeElementHandler.normalize_url("/test.pdf")
        expected = "https://www.mintos.com/test.pdf"
        assert test_url == expected, f"Expected {expected}, got {test_url}"
        print("✓ URL normalization working")
        
        # Test PDF link detection
        assert SafeElementHandler.is_pdf_link("test.pdf") == True
        assert SafeElementHandler.is_pdf_link("test.html") == False
        print("✓ PDF link detection working")
        
        # Test unique ID creation
        uid = create_unique_id("test", "data", 123)
        assert len(uid) == 32  # MD5 hash length
        print("✓ Unique ID creation working")
        
        return True
    except Exception as e:
        print(f"✗ Utils test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("Running fix verification tests...\n")
    
    tests_passed = 0
    total_tests = 3
    
    if await test_imports():
        tests_passed += 1
    
    if await test_document_scraper():
        tests_passed += 1
    
    if await test_utils():
        tests_passed += 1
    
    print(f"\nTests completed: {tests_passed}/{total_tests} passed")
    
    if tests_passed == total_tests:
        print("✓ All critical fixes verified successfully!")
        return True
    else:
        print("✗ Some tests failed - fixes need more work")
        return False

if __name__ == "__main__":
    asyncio.run(main())