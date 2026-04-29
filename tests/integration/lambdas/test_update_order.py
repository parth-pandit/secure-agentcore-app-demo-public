"""
Integration test for update_order Lambda function.
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
from update_order import lambda_handler

def test_update_order():
    """Test updating an existing order"""
    
    # Test event simulating API Gateway request
    # Update the order_id to match an existing order in your table
    event = {
        'body': json.dumps({
            'order_id': 'ORD-TEST-001',  # Change this to an existing order ID
            'status': 'completed',
            'qty': 10
        })
    }
    
    context = {}  # Mock context object
    
    print("Testing UPDATE ORDER...")
    print(f"Request: {event['body']}")
    print("-" * 50)
    
    # Invoke the Lambda handler
    response = lambda_handler(event, context)
    
    print(f"Status Code: {response['statusCode']}")
    print(f"Response Body: {response['body']}")
    print("-" * 50)
    
    # Parse and display the response
    if response['statusCode'] == 200:
        print("✓ Order updated successfully!")
        body = json.loads(response['body'])
        print("\nUpdated Order:")
        print(f"Order ID: {body['order']['order_id']}")
        print(f"Date: {body['order'].get('order_date')}")
        print(f"Item: {body['order'].get('item_name')}")
        print(f"Quantity: {body['order']['qty']}")
        print(f"Status: {body['order']['status']}")
    elif response['statusCode'] == 404:
        print("✗ Order not found")
        print("Note: Make sure the order_id exists in the table")
        print(json.loads(response['body']))
    else:
        print("✗ Failed to update order")
        print(json.loads(response['body']))
    
    return response

if __name__ == '__main__':
    test_update_order()
