"""
Integration test for get_orders Lambda function.
Tests the function against the dev-orders-table in AWS.
"""

import json
import os
import sys

# Add backend/src/lambdas to path to import Lambda functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../backend/src/lambdas'))

# Set environment variable for table name
os.environ['DYNAMODB_TABLE_NAME'] = 'dev-orders-table'

# Import the Lambda handler
from get_orders import lambda_handler

def test_get_orders():
    """Test retrieving all orders"""
    
    # Test event simulating API Gateway request
    event = {}
    context = {}  # Mock context object
    
    print("Testing GET ORDERS...")
    print("-" * 50)
    
    # Invoke the Lambda handler
    response = lambda_handler(event, context)
    
    print(f"Status Code: {response['statusCode']}")
    print("-" * 50)
    
    # Parse and display the response
    if response['statusCode'] == 200:
        body = json.loads(response['body'])
        print(f"✓ Retrieved {body['count']} orders successfully!")
        print("\nOrders:")
        for i, order in enumerate(body['orders'], 1):
            print(f"\n{i}. Order ID: {order.get('order_id')}")
            print(f"   Date: {order.get('order_date')}")
            print(f"   Item: {order.get('item_name')}")
            print(f"   Quantity: {order.get('qty')}")
            print(f"   Status: {order.get('status')}")
    else:
        print("✗ Failed to retrieve orders")
        print(json.loads(response['body']))
    
    return response

if __name__ == '__main__':
    test_get_orders()
