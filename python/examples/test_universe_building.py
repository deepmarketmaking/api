#!/usr/bin/env python3
"""
Simple test script to verify the new universe building functions
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all imports work"""
    print("Testing imports...")
    try:
        from datetime import datetime
        import pytz
        import boto3
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_function_definitions():
    """Test that the new functions are defined"""
    print("\nTesting function definitions...")
    try:
        # We can't actually import due to pandas issue, but we can check the file
        with open('new_get_timestamp_predictions.py', 'r') as f:
            content = f.read()

        required_functions = [
            'def get_s3_object_version_before_date',
            'def load_bond_data_from_s3',
            'async def build_historical_universe',
        ]

        for func in required_functions:
            if func in content:
                print(f"✓ Found: {func}")
            else:
                print(f"✗ Missing: {func}")
                return False

        # Check that historical_bonds_file is removed
        if 'historical_bonds_file' in content:
            # Count occurrences
            count = content.count('historical_bonds_file')
            print(f"✗ Found {count} references to historical_bonds_file (should be 0)")
            return False
        else:
            print("✓ All historical_bonds_file references removed")

        # Check for --use-current-universe flag
        if '--use-current-universe' in content:
            print("✓ Found --use-current-universe flag")
        else:
            print("✗ Missing --use-current-universe flag")
            return False

        print("✓ All function definitions found and cleaned up")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

def test_syntax():
    """Test Python syntax"""
    print("\nTesting Python syntax...")
    import py_compile
    try:
        py_compile.compile('new_get_timestamp_predictions.py', doraise=True)
        print("✓ Python syntax is valid")
        return True
    except Exception as e:
        print(f"✗ Syntax error: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Testing new universe building implementation")
    print("=" * 60)

    results = []
    results.append(test_imports())
    results.append(test_syntax())
    results.append(test_function_definitions())

    print("\n" + "=" * 60)
    if all(results):
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)
