"""
Run all Lambda function integration tests in sequence.
This script tests the complete workflow: CREATE -> GET -> UPDATE -> GET
"""

import os
import sys
import time

# Add backend/src/lambdas to path to import Lambda functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../backend/src/lambdas'))

# Set environment variable for table name
os.environ['DYNAMODB_TABLE_NAME'] = 'dev-orders-table'

from test_create_order import test_create_order
from test_get_orders import test_get_orders
from test_update_order import test_update_order

def main():
    """Run all tests in sequence"""
    
    print("=" * 60)
    print("TESTING ORDERS API - COMPLETE WORKFLOW")
    print("=" * 60)
    print()
    
    # Test 1: Create a new order
    print("\n" + "=" * 60)
    print("TEST 1: CREATE ORDER")
    print("=" * 60)
    create_response = test_create_order()
    time.sleep(1)  # Brief pause between tests
    
    # Test 2: Get all orders
    print("\n" + "=" * 60)
    print("TEST 2: GET ALL ORDERS")
    print("=" * 60)
    get_response = test_get_orders()
    time.sleep(1)
    
    # Test 3: Update the order
    print("\n" + "=" * 60)
    print("TEST 3: UPDATE ORDER")
    print("=" * 60)
    update_response = test_update_order()
    time.sleep(1)
    
    # Test 4: Get all orders again to verify update
    print("\n" + "=" * 60)
    print("TEST 4: GET ALL ORDERS (VERIFY UPDATE)")
    print("=" * 60)
    get_response_2 = test_get_orders()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"CREATE: {'✓ PASSED' if create_response['statusCode'] == 201 else '✗ FAILED'}")
    print(f"GET:    {'✓ PASSED' if get_response['statusCode'] == 200 else '✗ FAILED'}")
    print(f"UPDATE: {'✓ PASSED' if update_response['statusCode'] == 200 else '✗ FAILED'}")
    print(f"GET:    {'✓ PASSED' if get_response_2['statusCode'] == 200 else '✗ FAILED'}")
    print("=" * 60)

if __name__ == '__main__':
    main()
