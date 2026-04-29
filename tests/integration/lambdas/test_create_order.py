"""
Integration test for create_order Lambda function.
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
from create_order import lambda_handler

def test_create_order():
    """Test creating a new order"""
    
    # Test event simulating API Gateway request
    event = {
        'body': json.dumps({
            'order_id': 'ORD-TEST-001',
            'order_date': '2025-12-27',
            'item_name': 'Test Widget',
            'qty': 5,
            'status': 'pending'
        })
    }
    
    context = {}  # Mock context object
    
    print("Testing CREATE ORDER...")
    print(f"Request: {event['body']}")
    print("-" * 50)
    
    # Invoke the Lambda handler
    response = lambda_handler(event, context)
    
    print(f"Status Code: {response['statusCode']}")
    print(f"Response Body: {response['body']}")
    print("-" * 50)
    
    # Parse and display the response
    if response['statusCode'] == 201:
        print("✓ Order created successfully!")
        body = json.loads(response['body'])
        print(f"Order ID: {body['order']['order_id']}")
        print(f"Item: {body['order']['item_name']}")
        print(f"Quantity: {body['order']['qty']}")
        print(f"Status: {body['order']['status']}")
    else:
        print("✗ Failed to create order")
        print(json.loads(response['body']))
    
    return response

if __name__ == '__main__':
    test_create_order()
