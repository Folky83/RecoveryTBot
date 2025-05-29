#!/usr/bin/env python3
"""
Test script to verify handling of missing company names
"""
import sys
import os

# Add bot directory to path
sys.path.insert(0, '.')

def test_missing_company_names():
    """Test that missing company names fall back to ID"""
    print("Testing missing company name handling...")
    
    try:
        from bot.data_manager import DataManager
        
        # Initialize data manager
        dm = DataManager()
        
        # Test with a known company ID (should return name)
        known_id = 26  # Aforti from the CSV
        result = dm.get_company_name(known_id)
        print(f"Known ID {known_id}: '{result}'")
        
        # Test with an unknown ID (should return just the ID)
        unknown_id = 99999
        result = dm.get_company_name(unknown_id)
        print(f"Unknown ID {unknown_id}: '{result}'")
        
        # Verify the unknown ID returns just the number
        if result == str(unknown_id):
            print("✓ Missing names correctly fall back to ID")
            return True
        else:
            print(f"✗ Expected '{unknown_id}', got '{result}'")
            return False
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

def test_with_current_data():
    """Test with actual data to see current behavior"""
    print("\nTesting with current CSV data...")
    
    try:
        from bot.data_manager import DataManager
        import pandas as pd
        
        # Load current CSV
        csv_path = 'attached_assets/lo_names.csv'
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            print(f"CSV contains {len(df)} entries")
            print(f"ID range: {df['id'].min()} to {df['id'].max()}")
            
            # Test with an ID that's likely missing
            test_id = df['id'].max() + 100
            
            dm = DataManager()
            result = dm.get_company_name(test_id)
            print(f"Test ID {test_id} (not in CSV): '{result}'")
            
            return result == str(test_id)
        else:
            print("CSV file not found")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("Running missing company name tests...\n")
    
    test1_passed = test_missing_company_names()
    test2_passed = test_with_current_data()
    
    if test1_passed and test2_passed:
        print("\n✓ All tests passed! Missing names are handled correctly.")
    else:
        print("\n✗ Some tests failed.")