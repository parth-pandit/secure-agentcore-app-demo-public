"""
Lambda function to create a new order in DynamoDB.

This function handles POST requests to create new order records in the dev-orders-table.
It validates the input data and creates a new order with all required attributes.
"""

import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb')
# Get table name from environment variable
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'dev-orders-table')
table = dynamodb.Table(TABLE_NAME)


def extract_user_context(event):
    """
    Extract user context from the authorizer context in the API Gateway event.
    
    Args:
        event (dict): API Gateway event object
        
    Returns:
        dict: User context with email, userId, and authTime, or empty dict if not available
    """
    try:
        # Extract authorizer context from the event
        request_context = event.get('requestContext', {})
        authorizer_context = request_context.get('authorizer', {})
        
        # Extract user information from authorizer context
        user_context = {
            'userEmail': authorizer_context.get('userEmail', 'unknown'),
            'userId': authorizer_context.get('userId', 'unknown'),
            'authTime': authorizer_context.get('authTime', 'unknown')
        }
        
        return user_context
    except Exception as e:
        print(f"Warning: Could not extract user context: {str(e)}")
        return {}


def lambda_handler(event, context):
    """
    Main Lambda handler function for POST requests to create new orders.
    
    Expected request body format:
    {
        "order_id": "ORD-12345",
        "order_date": "2025-12-27",
        "item_name": "Product Name",
        "qty": 5,
        "status": "pending"
    }
    
    Args:
        event (dict): API Gateway event object containing request details
        context (object): Lambda context object with runtime information
    
    Returns:
        dict: API Gateway response with status code, headers, and body
    """
    # Extract user context from authorizer
    user_context = extract_user_context(event)
    user_email = user_context.get('userEmail', 'unknown')
    user_id = user_context.get('userId', 'unknown')
    
    # Log request with user information
    print(f"POST /orders request - User: {user_email} (ID: {user_id})")
    
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        # Validate required fields
        required_fields = ['order_id', 'order_date', 'item_name', 'qty', 'status']
        missing_fields = [field for field in required_fields if field not in body]
        
        if missing_fields:
            print(f"Validation failed for user {user_email}: Missing fields {missing_fields}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'message': 'Missing required fields',
                    'missing_fields': missing_fields
                })
            }
        
        # Prepare order item
        order_item = {
            'order_id': body['order_id'],
            'order_date': body['order_date'],
            'item_name': body['item_name'],
            'qty': Decimal(str(body['qty'])),  # Convert to Decimal for DynamoDB
            'status': body['status']
        }
        
        # Put item in DynamoDB table
        table.put_item(Item=order_item)
        
        # Log successful order creation with user information
        print(f"Order {order_item['order_id']} created successfully by user: {user_email}")
        
        # Return success response
        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Order created successfully',
                'order': {
                    'order_id': order_item['order_id'],
                    'order_date': order_item['order_date'],
                    'item_name': order_item['item_name'],
                    'qty': int(order_item['qty']),
                    'status': order_item['status']
                }
            })
        }
    
    except json.JSONDecodeError:
        # Handle invalid JSON in request body
        print(f"Invalid JSON in request from user {user_email}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Invalid JSON in request body'
            })
        }
    
    except Exception as e:
        # Log error with user information
        print(f"Error creating order for user {user_email}: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Failed to create order',
                'error': str(e)
            })
        }
