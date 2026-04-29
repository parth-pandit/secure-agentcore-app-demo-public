"""
Unit tests for context logging in backend Lambda functions.

Tests context extraction from API Gateway events and logging with user information
for get_orders, create_order, and update_order Lambda functions.

Requirements: 1.5, 4.1
"""

import unittest
import json
import os
import sys
from unittest.mock import Mock, patch, call
from decimal import Decimal

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

# Set environment variables
os.environ['DYNAMODB_TABLE_NAME'] = 'test-orders-table'

# Import Lambda functions
from get_orders import lambda_handler as get_orders_handler, extract_user_context as get_extract_context
from create_order import lambda_handler as create_order_handler, extract_user_context as create_extract_context
from update_order import lambda_handler as update_order_handler, extract_user_context as update_extract_context


class TestContextExtraction(unittest.TestCase):
    """Test context extraction from API Gateway events."""
    
    def test_extract_context_with_full_authorizer_data(self):
        """Test extracting context when all authorizer data is present."""
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'test@example.com',
                    'userId': 'user-123',
                    'authTime': '1234567890'
                }
            }
        }
        
        context = get_extract_context(event)
        
        self.assertEqual(context['userEmail'], 'test@example.com')
        self.assertEqual(context['userId'], 'user-123')
        self.assertEqual(context['authTime'], '1234567890')
    
    def test_extract_context_with_missing_authorizer(self):
        """Test extracting context when authorizer is missing."""
        event = {
            'requestContext': {}
        }
        
        context = get_extract_context(event)
        
        self.assertEqual(context['userEmail'], 'unknown')
        self.assertEqual(context['userId'], 'unknown')
        self.assertEqual(context['authTime'], 'unknown')
    
    def test_extract_context_with_missing_request_context(self):
        """Test extracting context when requestContext is missing."""
        event = {}
        
        context = get_extract_context(event)
        
        self.assertEqual(context['userEmail'], 'unknown')
        self.assertEqual(context['userId'], 'unknown')
        self.assertEqual(context['authTime'], 'unknown')
    
    def test_extract_context_with_partial_authorizer_data(self):
        """Test extracting context when some authorizer fields are missing."""
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'partial@example.com'
                    # userId and authTime missing
                }
            }
        }
        
        context = get_extract_context(event)
        
        self.assertEqual(context['userEmail'], 'partial@example.com')
        self.assertEqual(context['userId'], 'unknown')
        self.assertEqual(context['authTime'], 'unknown')


class TestGetOrdersContextLogging(unittest.TestCase):
    """Test context logging in get_orders Lambda function."""
    
    @patch('get_orders.table')
    @patch('builtins.print')
    def test_logs_user_email_on_request(self, mock_print, mock_table):
        """Test that user email is logged when GET request is made."""
        # Setup: Mock DynamoDB response
        mock_table.scan.return_value = {
            'Items': []
        }
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'test@example.com',
                    'userId': 'user-123'
                }
            }
        }
        context = Mock()
        
        # Execute
        response = get_orders_handler(event, context)
        
        # Verify: User email was logged
        mock_print.assert_any_call('GET /orders request - User: test@example.com (ID: user-123)')
        
        # Verify: Success response
        self.assertEqual(response['statusCode'], 200)
    
    @patch('get_orders.table')
    @patch('builtins.print')
    def test_logs_user_email_on_success(self, mock_print, mock_table):
        """Test that user email is logged on successful retrieval."""
        # Setup: Mock DynamoDB response with orders
        mock_table.scan.return_value = {
            'Items': [
                {'order_id': 'ORD-001', 'item_name': 'Widget', 'qty': Decimal('5')}
            ]
        }
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'success@example.com',
                    'userId': 'user-456'
                }
            }
        }
        context = Mock()
        
        # Execute
        response = get_orders_handler(event, context)
        
        # Verify: Success log includes user email
        mock_print.assert_any_call('Successfully retrieved 1 orders for user: success@example.com')
    
    @patch('get_orders.table')
    @patch('builtins.print')
    def test_logs_user_email_on_error(self, mock_print, mock_table):
        """Test that user email is logged on error."""
        # Setup: Mock DynamoDB to raise error
        mock_table.scan.side_effect = Exception('Database error')
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'error@example.com',
                    'userId': 'user-789'
                }
            }
        }
        context = Mock()
        
        # Execute
        response = get_orders_handler(event, context)
        
        # Verify: Error log includes user email
        mock_print.assert_any_call('Error retrieving orders for user error@example.com: Database error')
        
        # Verify: Error response
        self.assertEqual(response['statusCode'], 500)
    
    @patch('get_orders.table')
    @patch('builtins.print')
    def test_handles_missing_user_context(self, mock_print, mock_table):
        """Test that function handles missing user context gracefully."""
        # Setup: Mock DynamoDB response
        mock_table.scan.return_value = {
            'Items': []
        }
        
        # Create event without user context
        event = {}
        context = Mock()
        
        # Execute
        response = get_orders_handler(event, context)
        
        # Verify: Logs with 'unknown' user
        mock_print.assert_any_call('GET /orders request - User: unknown (ID: unknown)')
        
        # Verify: Still returns success
        self.assertEqual(response['statusCode'], 200)


class TestCreateOrderContextLogging(unittest.TestCase):
    """Test context logging in create_order Lambda function."""
    
    @patch('create_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_request(self, mock_print, mock_table):
        """Test that user email is logged when POST request is made."""
        # Setup: Mock DynamoDB
        mock_table.put_item.return_value = {}
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'creator@example.com',
                    'userId': 'user-create-1'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-TEST-001',
                'order_date': '2025-12-30',
                'item_name': 'Test Item',
                'qty': 5,
                'status': 'pending'
            })
        }
        context = Mock()
        
        # Execute
        response = create_order_handler(event, context)
        
        # Verify: User email was logged
        mock_print.assert_any_call('POST /orders request - User: creator@example.com (ID: user-create-1)')
        
        # Verify: Success response
        self.assertEqual(response['statusCode'], 201)
    
    @patch('create_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_success(self, mock_print, mock_table):
        """Test that user email is logged on successful order creation."""
        # Setup: Mock DynamoDB
        mock_table.put_item.return_value = {}
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'success@example.com',
                    'userId': 'user-create-2'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-SUCCESS-001',
                'order_date': '2025-12-30',
                'item_name': 'Success Item',
                'qty': 10,
                'status': 'pending'
            })
        }
        context = Mock()
        
        # Execute
        response = create_order_handler(event, context)
        
        # Verify: Success log includes user email and order ID
        mock_print.assert_any_call('Order ORD-SUCCESS-001 created successfully by user: success@example.com')
    
    @patch('builtins.print')
    def test_logs_user_email_on_validation_error(self, mock_print):
        """Test that user email is logged on validation error."""
        # Create event with missing fields
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'invalid@example.com',
                    'userId': 'user-create-3'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-INVALID-001'
                # Missing required fields
            })
        }
        context = Mock()
        
        # Execute
        response = create_order_handler(event, context)
        
        # Verify: Validation error log includes user email
        self.assertTrue(any(
            'Validation failed for user invalid@example.com' in str(call_args)
            for call_args in mock_print.call_args_list
        ))
        
        # Verify: Error response
        self.assertEqual(response['statusCode'], 400)
    
    @patch('create_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_error(self, mock_print, mock_table):
        """Test that user email is logged on error."""
        # Setup: Mock DynamoDB to raise error
        mock_table.put_item.side_effect = Exception('Database error')
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'error@example.com',
                    'userId': 'user-create-4'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-ERROR-001',
                'order_date': '2025-12-30',
                'item_name': 'Error Item',
                'qty': 5,
                'status': 'pending'
            })
        }
        context = Mock()
        
        # Execute
        response = create_order_handler(event, context)
        
        # Verify: Error log includes user email
        mock_print.assert_any_call('Error creating order for user error@example.com: Database error')
        
        # Verify: Error response
        self.assertEqual(response['statusCode'], 500)


class TestUpdateOrderContextLogging(unittest.TestCase):
    """Test context logging in update_order Lambda function."""
    
    @patch('update_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_request(self, mock_print, mock_table):
        """Test that user email is logged when PUT request is made."""
        # Setup: Mock DynamoDB
        mock_table.update_item.return_value = {
            'Attributes': {
                'order_id': 'ORD-UPDATE-001',
                'status': 'completed',
                'qty': Decimal('10')
            }
        }
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'updater@example.com',
                    'userId': 'user-update-1'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-UPDATE-001',
                'status': 'completed'
            })
        }
        context = Mock()
        
        # Execute
        response = update_order_handler(event, context)
        
        # Verify: User email was logged
        mock_print.assert_any_call('PUT /orders request - User: updater@example.com (ID: user-update-1)')
        
        # Verify: Success response
        self.assertEqual(response['statusCode'], 200)
    
    @patch('update_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_success(self, mock_print, mock_table):
        """Test that user email is logged on successful order update."""
        # Setup: Mock DynamoDB
        mock_table.update_item.return_value = {
            'Attributes': {
                'order_id': 'ORD-SUCCESS-002',
                'status': 'shipped',
                'qty': Decimal('15')
            }
        }
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'success@example.com',
                    'userId': 'user-update-2'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-SUCCESS-002',
                'status': 'shipped'
            })
        }
        context = Mock()
        
        # Execute
        response = update_order_handler(event, context)
        
        # Verify: Success log includes user email and order ID
        mock_print.assert_any_call('Order ORD-SUCCESS-002 updated successfully by user: success@example.com')
    
    @patch('builtins.print')
    def test_logs_user_email_on_validation_error(self, mock_print):
        """Test that user email is logged on validation error."""
        # Create event with missing order_id
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'invalid@example.com',
                    'userId': 'user-update-3'
                }
            },
            'body': json.dumps({
                'status': 'completed'
                # Missing order_id
            })
        }
        context = Mock()
        
        # Execute
        response = update_order_handler(event, context)
        
        # Verify: Validation error log includes user email
        mock_print.assert_any_call('Validation failed for user invalid@example.com: Missing order_id')
        
        # Verify: Error response
        self.assertEqual(response['statusCode'], 400)
    
    @patch('update_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_not_found_error(self, mock_print, mock_table):
        """Test that user email is logged when order is not found."""
        from botocore.exceptions import ClientError
        
        # Setup: Mock DynamoDB to raise ResourceNotFoundException
        error_response = {'Error': {'Code': 'ResourceNotFoundException'}}
        mock_table.update_item.side_effect = ClientError(error_response, 'UpdateItem')
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'notfound@example.com',
                    'userId': 'user-update-4'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-NOTFOUND-001',
                'status': 'completed'
            })
        }
        context = Mock()
        
        # Execute
        response = update_order_handler(event, context)
        
        # Verify: Not found log includes user email
        mock_print.assert_any_call('Order ORD-NOTFOUND-001 not found for user notfound@example.com')
        
        # Verify: Not found response
        self.assertEqual(response['statusCode'], 404)
    
    @patch('update_order.table')
    @patch('builtins.print')
    def test_logs_user_email_on_error(self, mock_print, mock_table):
        """Test that user email is logged on error."""
        # Setup: Mock DynamoDB to raise error
        mock_table.update_item.side_effect = Exception('Database error')
        
        # Create event with user context
        event = {
            'requestContext': {
                'authorizer': {
                    'userEmail': 'error@example.com',
                    'userId': 'user-update-5'
                }
            },
            'body': json.dumps({
                'order_id': 'ORD-ERROR-002',
                'status': 'completed'
            })
        }
        context = Mock()
        
        # Execute
        response = update_order_handler(event, context)
        
        # Verify: Error log includes user email
        mock_print.assert_any_call('Error updating order for user error@example.com: Database error')
        
        # Verify: Error response
        self.assertEqual(response['statusCode'], 500)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
