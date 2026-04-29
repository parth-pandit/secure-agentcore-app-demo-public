"""
Lambda function to update existing order details in DynamoDB.

This function handles PUT requests to update order records in the dev-orders-table.
It allows updating specific attributes of an order identified by order_id.
"""

import json
import boto3
import os
from decimal import Decimal
from botocore.exceptions import ClientError

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
    Main Lambda handler function for PUT requests to update orders.
    
    Expected request body format:
    {
        "order_id": "ORD-12345",
        "order_date": "2025-12-28",  (optional)
        "item_name": "Updated Product",  (optional)
        "qty": 10,  (optional)
        "status": "completed"  (optional)
    }
    
    Args:
        event (dict): API Gateway event object containing request details
        context (object): Lambda context object with runtime information
    
    Returns:
        dict: API Gateway response with status code, headers, and updated order details
    """
    # Extract user context from authorizer
    user_context = extract_user_context(event)
    user_email = user_context.get('userEmail', 'unknown')
    user_id = user_context.get('userId', 'unknown')
    
    # Log request with user information
    print(f"PUT /orders request - User: {user_email} (ID: {user_id})")
    
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        # Validate order_id is provided
        if 'order_id' not in body:
            print(f"Validation failed for user {user_email}: Missing order_id")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'message': 'order_id is required to update an order'
                })
            }
        
        order_id = body['order_id']
        
        # Build update expression dynamically based on provided fields
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}
        
        # Map of updatable fields
        updatable_fields = {
            'order_date': 'order_date',
            'item_name': 'item_name',
            'qty': 'qty',
            'status': 'status'
        }
        
        for field, attr_name in updatable_fields.items():
            if field in body and field != 'order_id':
                # Use attribute names to handle reserved keywords
                placeholder = f"#{field}"
                value_placeholder = f":{field}"
                
                update_expression_parts.append(f"{placeholder} = {value_placeholder}")
                expression_attribute_names[placeholder] = attr_name
                
                # Convert qty to Decimal for DynamoDB
                if field == 'qty':
                    expression_attribute_values[value_placeholder] = Decimal(str(body[field]))
                else:
                    expression_attribute_values[value_placeholder] = body[field]
        
        # Check if there are any fields to update
        if not update_expression_parts:
            print(f"Validation failed for user {user_email}: No fields to update for order {order_id}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'message': 'No fields provided to update'
                })
            }
        
        # Construct the update expression
        update_expression = "SET " + ", ".join(update_expression_parts)
        
        # Update the item in DynamoDB
        response = table.update_item(
            Key={'order_id': order_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues='ALL_NEW'
        )
        
        # Convert Decimal to int/float for JSON response
        updated_attributes = response.get('Attributes', {})
        if 'qty' in updated_attributes:
            updated_attributes['qty'] = int(updated_attributes['qty'])
        
        # Log successful order update with user information
        print(f"Order {order_id} updated successfully by user: {user_email}")
        
        # Return success response with updated order
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Order updated successfully',
                'order': updated_attributes
            })
        }
    
    except ClientError as e:
        # Handle DynamoDB specific errors
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            print(f"Order {order_id} not found for user {user_email}")
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'message': f'Order with order_id {order_id} not found'
                })
            }
        else:
            print(f"DynamoDB error for user {user_email}: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'message': 'Failed to update order',
                    'error': str(e)
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
        print(f"Error updating order for user {user_email}: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Failed to update order',
                'error': str(e)
            })
        }
