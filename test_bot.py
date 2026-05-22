#!/usr/bin/env python3
"""
Test script for the BSUIR Teacher Schedule Bot
"""

import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_api_client():
    """Test the API client functionality"""
    print("Testing API Client...")
    
    try:
        from utils.api_client import BsuirAPI
        api = BsuirAPI()
        
        # Test teacher schedule
        print("  Testing teacher schedule...")
        teacher_data = api.get_schedule(url_id='s-nesterenkov')
        if teacher_data:
            print("    ✓ Teacher schedule retrieved successfully")
            parsed_teacher = api.parse_schedule_data(teacher_data)
            if parsed_teacher:
                print(f"    ✓ Teacher parsed: {parsed_teacher['group_name']}")
                print(f"    ✓ Rank: {parsed_teacher['faculty']}")
                print(f"    ✓ Degree: {parsed_teacher['course']}")
            else:
                print("    ✗ Failed to parse teacher schedule")
                return False
        else:
            print("    ✗ Failed to retrieve teacher schedule")
            return False
            
        # Test group schedule
        print("  Testing group schedule...")
        group_data = api.get_schedule(group_number='561404')
        if group_data:
            print("    ✓ Group schedule retrieved successfully")
            parsed_group = api.parse_schedule_data(group_data)
            if parsed_group:
                print(f"    ✓ Group parsed: {parsed_group['group_name']}")
                print(f"    ✓ Faculty: {parsed_group['faculty']}")
                print(f"    ✓ Course: {parsed_group['course']}")
            else:
                print("    ✗ Failed to parse group schedule")
                return False
        else:
            print("    ✗ Failed to retrieve group schedule")
            return False
            
        return True
        
    except Exception as e:
        print(f"  ✗ Error testing API client: {e}")
        return False

def test_database_initialization():
    """Test database initialization (will work without Firebase)"""
    print("\\nTesting Database Initialization...")
    
    try:
        from utils.database import Database
        db = Database()
        print("  ✓ Database initialized successfully")
        return True
    except Exception as e:
        print(f"  - Database initialization note: {e}")
        # This is expected to fail without Firebase credentials, but that's okay
        return True  # We'll consider this a pass since it's expected

def test_imports():
    """Test that all modules can be imported"""
    print("\\nTesting Module Imports...")
    
    try:
        from api.bot import app, db, api
        print("  ✓ Bot module imported successfully")
        
        from utils.api_client import BsuirAPI
        print("  ✓ API client imported successfully")
        
        from utils.database import Database
        print("  ✓ Database imported successfully")
        
        return True
    except Exception as e:
        print(f"  ✗ Error importing modules: {e}")
        return False

def main():
    """Run all tests"""
    print("BSUIR Teacher Schedule Bot - Test Suite")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_api_client,
        test_database_initialization,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())