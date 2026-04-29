"""
Integration tests for Orders API with Authentication and Authorization.

This test suite validates the complete API flow including:
- Authentication with valid and invalid tokens
- Authorization for authorized and unauthorized users
- All three endpoints (GET, POST, PUT)
- Audit logging verification

Requirements tested: 1.1, 2.1, 2.2, 2.3, 4.1
"""

import unittest
import json
import os
import sys
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../tests/utils'))

# Set environment variables
os.environ['DYNAMODB_TABLE_NAME'] = 'dev-orders-table'
os.environ['AUTHORIZED_USERS'] = json.dumps({
    "user@example.com": {
        "permissions": ["GET", "POST", "PUT"],
        "resources": ["*"]
    }
})

# Import Lambda functions
from authorizer import lambda_handler as authorizer_handler
from get_orders import lambda_handler as get_orders_handler
from create_order import lambda_handler as create_order_handler
from update_order import lambda_handler as update_order_handler

# Import token generator
from token_generator import MockTokenGenerator, create_authorizer_event


class BaseAuthenticationTest(unittest.TestCase):
    """Base class for authentication tests with proper cleanup."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Ensure environment variables are set
        os.environ['DYNAMODB_TABLE_NAME'] = 'dev-orders-table'
        os.environ['AUTHORIZED_USERS'] = json.dumps({
            "user@example.com": {
                "permissions": ["GET", "POST", "PUT"],
                "resources": ["*"]
            }
        })
        
        # Clear any cached audit logger state
        import audit_logger
        if hasattr(audit_logger, '_audit_logger_instance'):
            delattr(audit_logger, '_audit_logger_instance')
        
        # Clear authorization policy cache
        import authorization_policy
        if hasattr(authorization_policy, '_policy_cache'):
            authorization_policy._policy_cache = None
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Clear audit logger cache
        import audit_logger
        if hasattr(audit_logger, '_audit_logger_instance'):
            delattr(audit_logger, '_audit_logger_instance')
        
        # Clear authorization policy cache
        import authorization_policy
        if hasattr(authorization_policy, '_policy_cache'):
            authorization_policy._policy_cache = None
        
        # Stop all patches
        from unittest.mock import patch
        patch.stopall()


class TestCompleteAPIFlowWithAuthentication(BaseAuthenticationTest):
    """Test complete API flow with authentication and authorization."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.token_generator = MockTokenGenerator()
        self.authorized_user = "user@example.com"
        self.unauthorized_user = "unauthorized@example.com"
        self.test_order_id = f"ORD-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    @patch('get_orders.table')
    def test_get_orders_with_valid_token(
        self, mock_table, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test GET /orders with valid authentication token."""
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-123',
            'auth_time': 1234567890
        }
        
        # Setup: Mock DynamoDB response
        mock_table.scan.return_value = {
            'Items': [
                {
                    'order_id': 'ORD-001',
                    'order_date': '2025-12-27',
                    'item_name': 'Widget',
                    'qty': 5,
                    'status': 'pending'
                }
            ]
        }
        
        # Step 1: Authorize the request
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-001'
        
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authorization succeeded
        self.assertEqual(auth_response['principalId'], self.authorized_user)
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Allow')
        self.assertIn('context', auth_response)
        self.assertEqual(auth_response['context']['userEmail'], self.authorized_user)
        
        # Step 2: Call GET orders endpoint
        get_event = {'httpMethod': 'GET'}
        get_context = Mock()
        
        get_response = get_orders_handler(get_event, get_context)
        
        # Verify GET response
        self.assertEqual(get_response['statusCode'], 200)
        body = json.loads(get_response['body'])
        self.assertEqual(body['message'], 'Orders retrieved successfully')
        self.assertEqual(body['count'], 1)
        self.assertEqual(len(body['orders']), 1)
        
        # Verify authentication and authorization were logged
        mock_log_auth.assert_called_once()
        mock_log_authz.assert_called_once()
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    @patch('create_order.table')
    def test_post_orders_with_valid_token(
        self, mock_table, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test POST /orders with valid authentication token."""
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-456',
            'auth_time': 1234567890
        }
        
        # Setup: Mock DynamoDB put_item
        mock_table.put_item.return_value = {}
        
        # Step 1: Authorize the request
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="POST", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-002'
        
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authorization succeeded
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Allow')
        
        # Step 2: Call POST orders endpoint
        order_data = {
            'order_id': self.test_order_id,
            'order_date': '2025-12-27',
            'item_name': 'Test Widget',
            'qty': 10,
            'status': 'pending'
        }
        
        post_event = {
            'httpMethod': 'POST',
            'body': json.dumps(order_data)
        }
        post_context = Mock()
        
        post_response = create_order_handler(post_event, post_context)
        
        # Verify POST response
        self.assertEqual(post_response['statusCode'], 201)
        body = json.loads(post_response['body'])
        self.assertEqual(body['message'], 'Order created successfully')
        self.assertEqual(body['order']['order_id'], self.test_order_id)
        
        # Verify DynamoDB was called
        mock_table.put_item.assert_called_once()
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    @patch('update_order.table')
    def test_put_orders_with_valid_token(
        self, mock_table, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test PUT /orders with valid authentication token."""
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-789',
            'auth_time': 1234567890
        }
        
        # Setup: Mock DynamoDB update_item
        mock_table.update_item.return_value = {
            'Attributes': {
                'order_id': self.test_order_id,
                'order_date': '2025-12-27',
                'item_name': 'Test Widget',
                'qty': 20,
                'status': 'completed'
            }
        }
        
        # Step 1: Authorize the request
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="PUT", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-003'
        
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authorization succeeded
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Allow')
        
        # Step 2: Call PUT orders endpoint
        update_data = {
            'order_id': self.test_order_id,
            'qty': 20,
            'status': 'completed'
        }
        
        put_event = {
            'httpMethod': 'PUT',
            'body': json.dumps(update_data)
        }
        put_context = Mock()
        
        put_response = update_order_handler(put_event, put_context)
        
        # Verify PUT response
        self.assertEqual(put_response['statusCode'], 200)
        body = json.loads(put_response['body'])
        self.assertEqual(body['message'], 'Order updated successfully')
        self.assertEqual(body['order']['status'], 'completed')
        
        # Verify DynamoDB was called
        mock_table.update_item.assert_called_once()


class TestInvalidTokenScenarios(BaseAuthenticationTest):
    """Test API access with invalid tokens."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.token_generator = MockTokenGenerator()
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authentication_failure')
    def test_expired_token_denied(self, mock_log_failure, mock_validate):
        """Test that expired tokens are denied access."""
        from token_validator import TokenValidationError
        
        # Setup: Mock token validation to raise error
        mock_validate.side_effect = TokenValidationError("Token has expired")
        
        # Create expired token
        expired_token = self.token_generator.generate_expired_token("user@example.com")
        auth_event = create_authorizer_event(expired_token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-expired'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify failure was logged
        mock_log_failure.assert_called_once()
        call_args = mock_log_failure.call_args[1]
        self.assertIn('expired', call_args['reason'].lower())
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authentication_failure')
    def test_invalid_signature_denied(self, mock_log_failure, mock_validate):
        """Test that tokens with invalid signatures are denied."""
        from token_validator import TokenValidationError
        
        # Setup: Mock token validation to raise error
        mock_validate.side_effect = TokenValidationError("Invalid signature")
        
        # Create token with invalid signature
        invalid_token = self.token_generator.generate_invalid_signature_token("user@example.com")
        auth_event = create_authorizer_event(invalid_token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-invalid-sig'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify failure was logged
        mock_log_failure.assert_called_once()
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authentication_failure')
    def test_malformed_token_denied(self, mock_log_failure, mock_validate):
        """Test that malformed tokens are denied."""
        from token_validator import TokenValidationError
        
        # Setup: Mock token validation to raise error for malformed token
        mock_validate.side_effect = TokenValidationError("Invalid token format")
        
        # Create malformed token
        malformed_token = "not.a.valid.jwt"
        auth_event = create_authorizer_event(malformed_token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-malformed'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify failure was logged
        mock_log_failure.assert_called_once()
    
    @patch('authorizer.log_authentication_failure')
    def test_missing_token_denied(self, mock_log_failure):
        """Test that requests without tokens are denied."""
        # Create event without token
        auth_event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api/dev/GET/orders'
        }
        auth_context = Mock()
        auth_context.request_id = 'test-request-missing'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify failure was logged
        mock_log_failure.assert_called_once()


class TestUnauthorizedUserScenarios(BaseAuthenticationTest):
    """Test API access with unauthorized users."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.token_generator = MockTokenGenerator()
        self.unauthorized_user = "unauthorized@example.com"
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_unauthorized_user_denied_get(
        self, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test that unauthorized users are denied GET access."""
        # Setup: Mock token validation for unauthorized user
        mock_validate.return_value = {
            'email': self.unauthorized_user,
            'sub': 'user-unauth-1',
            'auth_time': 1234567890
        }
        
        # Create valid token for unauthorized user
        token = self.token_generator.generate_token(self.unauthorized_user)
        auth_event = create_authorizer_event(token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-unauth-get'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['principalId'], self.unauthorized_user)
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify authentication succeeded but authorization denied
        mock_log_auth.assert_called_once()
        mock_log_authz.assert_called_once()
        call_args = mock_log_authz.call_args[1]
        self.assertEqual(call_args['decision'], 'DENY')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_unauthorized_user_denied_post(
        self, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test that unauthorized users are denied POST access."""
        # Setup: Mock token validation for unauthorized user
        mock_validate.return_value = {
            'email': self.unauthorized_user,
            'sub': 'user-unauth-2',
            'auth_time': 1234567890
        }
        
        # Create valid token for unauthorized user
        token = self.token_generator.generate_token(self.unauthorized_user)
        auth_event = create_authorizer_event(token, method="POST", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-unauth-post'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify denial was logged
        call_args = mock_log_authz.call_args[1]
        self.assertEqual(call_args['decision'], 'DENY')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_unauthorized_user_denied_put(
        self, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test that unauthorized users are denied PUT access."""
        # Setup: Mock token validation for unauthorized user
        mock_validate.return_value = {
            'email': self.unauthorized_user,
            'sub': 'user-unauth-3',
            'auth_time': 1234567890
        }
        
        # Create valid token for unauthorized user
        token = self.token_generator.generate_token(self.unauthorized_user)
        auth_event = create_authorizer_event(token, method="PUT", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-unauth-put'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify access denied
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify denial was logged
        call_args = mock_log_authz.call_args[1]
        self.assertEqual(call_args['decision'], 'DENY')


class TestAuditLogging(BaseAuthenticationTest):
    """Test that audit logs are created for all access attempts."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.token_generator = MockTokenGenerator()
        self.authorized_user = "user@example.com"
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_successful_access_logged(
        self, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test that successful access attempts are logged."""
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-log-1',
            'auth_time': 1234567890
        }
        
        # Create valid token
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-log-success'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authentication success was logged
        mock_log_auth.assert_called_once()
        auth_call_args = mock_log_auth.call_args[1]
        self.assertEqual(auth_call_args['user_email'], self.authorized_user)
        self.assertEqual(auth_call_args['request_id'], 'test-request-log-success')
        
        # Verify authorization attempt was logged
        mock_log_authz.assert_called_once()
        authz_call_args = mock_log_authz.call_args[1]
        self.assertEqual(authz_call_args['user_email'], self.authorized_user)
        self.assertEqual(authz_call_args['decision'], 'ALLOW')
        self.assertEqual(authz_call_args['method'], 'GET')
        self.assertEqual(authz_call_args['resource'], '/orders')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authentication_failure')
    def test_failed_authentication_logged(self, mock_log_failure, mock_validate):
        """Test that failed authentication attempts are logged."""
        from token_validator import TokenValidationError
        
        # Setup: Mock token validation to fail
        mock_validate.side_effect = TokenValidationError("Invalid token")
        
        # Create invalid token
        token = self.token_generator.generate_malformed_token()
        auth_event = create_authorizer_event(token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-log-fail-auth'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authentication failure was logged
        mock_log_failure.assert_called_once()
        call_args = mock_log_failure.call_args[1]
        self.assertEqual(call_args['request_id'], 'test-request-log-fail-auth')
        self.assertIn('reason', call_args)
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_failed_authorization_logged(
        self, mock_log_auth, mock_log_authz, mock_validate
    ):
        """Test that failed authorization attempts are logged."""
        # Setup: Mock token validation for unauthorized user
        unauthorized_user = "unauthorized@example.com"
        mock_validate.return_value = {
            'email': unauthorized_user,
            'sub': 'user-log-fail-authz',
            'auth_time': 1234567890
        }
        
        # Create valid token for unauthorized user
        token = self.token_generator.generate_token(unauthorized_user)
        auth_event = create_authorizer_event(token, method="POST", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-request-log-fail-authz'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authentication success was logged
        mock_log_auth.assert_called_once()
        
        # Verify authorization denial was logged
        mock_log_authz.assert_called_once()
        call_args = mock_log_authz.call_args[1]
        self.assertEqual(call_args['user_email'], unauthorized_user)
        self.assertEqual(call_args['decision'], 'DENY')
        self.assertEqual(call_args['request_id'], 'test-request-log-fail-authz')


class TestAllThreeEndpoints(BaseAuthenticationTest):
    """Test authorization for all three API endpoints."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.token_generator = MockTokenGenerator()
        self.authorized_user = "user@example.com"
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_get_endpoint_authorization(self, mock_check_authz, mock_validate):
        """Test authorization specifically for GET /orders endpoint."""
        # Setup
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-get',
            'auth_time': 1234567890
        }
        mock_check_authz.return_value = True
        
        # Create token and event
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="GET", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-get-endpoint'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authorization was checked for GET method
        mock_check_authz.assert_called_once()
        call_args = mock_check_authz.call_args[0]
        self.assertEqual(call_args[0], self.authorized_user)
        self.assertIn('GET', call_args[1])
        
        # Verify access granted
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Allow')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_post_endpoint_authorization(self, mock_check_authz, mock_validate):
        """Test authorization specifically for POST /orders endpoint."""
        # Setup
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-post',
            'auth_time': 1234567890
        }
        mock_check_authz.return_value = True
        
        # Create token and event
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="POST", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-post-endpoint'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authorization was checked for POST method
        mock_check_authz.assert_called_once()
        call_args = mock_check_authz.call_args[0]
        self.assertIn('POST', call_args[1])
        
        # Verify access granted
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Allow')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_put_endpoint_authorization(self, mock_check_authz, mock_validate):
        """Test authorization specifically for PUT /orders endpoint."""
        # Setup
        mock_validate.return_value = {
            'email': self.authorized_user,
            'sub': 'user-put',
            'auth_time': 1234567890
        }
        mock_check_authz.return_value = True
        
        # Create token and event
        token = self.token_generator.generate_token(self.authorized_user)
        auth_event = create_authorizer_event(token, method="PUT", resource="/orders")
        auth_context = Mock()
        auth_context.request_id = 'test-put-endpoint'
        
        # Call authorizer
        auth_response = authorizer_handler(auth_event, auth_context)
        
        # Verify authorization was checked for PUT method
        mock_check_authz.assert_called_once()
        call_args = mock_check_authz.call_args[0]
        self.assertIn('PUT', call_args[1])
        
        # Verify access granted
        self.assertEqual(auth_response['policyDocument']['Statement'][0]['Effect'], 'Allow')


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
