"""
Lambda function to retrieve all order details from DynamoDB.

This function handles GET requests to fetch all orders from the dev-orders-table.
It returns all order records with their complete details including order_id, 
order_date, item_name, qty, and status.
"""

import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb')
# Get table name from environment variable
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'dev-orders-table')
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    """
    Helper class to convert Decimal types to int/float for JSON serialization.
    DynamoDB returns numbers as Decimal objects which aren't JSON serializable.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


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
    Main Lambda handler function for GET requests.
    
    Args:
        event (dict): API Gateway event object containing request details
        context (object): Lambda context object with runtime information
    
    Returns:
        dict: API Gateway response with status code, headers, and body containing orders
    """
    # Extract user context from authorizer
    user_context = extract_user_context(event)
    user_email = user_context.get('userEmail', 'unknown')
    user_id = user_context.get('userId', 'unknown')
    
    # Log request with user information
    print(f"GET /orders request - User: {user_email} (ID: {user_id})")
    
    try:
        # Scan the table to retrieve all orders
        # Note: For large tables, consider using pagination or Query with GSI
        response = table.scan()
        orders = response.get('Items', [])
        
        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            orders.extend(response.get('Items', []))
        
        # Log successful retrieval with user information
        print(f"Successfully retrieved {len(orders)} orders for user: {user_email}")
        
        # Return successful response with orders
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Orders retrieved successfully',
                'count': len(orders),
                'orders': orders
            }, cls=DecimalEncoder)
        }
    
    except Exception as e:
        # Log error with user information
        print(f"Error retrieving orders for user {user_email}: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Failed to retrieve orders',
                'error': str(e)
            })
        }
