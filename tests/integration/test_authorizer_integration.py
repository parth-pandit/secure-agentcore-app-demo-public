"""
Integration tests for Lambda Authorizer.

Tests the complete authorization flow with all modules integrated:
- Token validation
- Authorization policy checking
- Audit logging
- Error handling
"""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
sys.path.insert(0, 'backend/src/lambdas')

from authorizer import lambda_handler


class TestCompleteAuthorizationFlow(unittest.TestCase):
    """Test complete authorization flow with all modules."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authentication_success')
    @patch('authorizer.log_authorization_attempt')
    def test_successful_authorization_flow(
        self, mock_log_authz, mock_log_auth, mock_check_authz, mock_validate
    ):
        """Test complete flow for successful authorization."""
        # Mock token validation
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123',
            'auth_time': 1234567890,
            'iss': 'https://identity-center.example.com',
            'aud': 'orders-api'
        }
        
        # Mock authorization check
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token-12345',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify token validation was called
        mock_validate.assert_called_once_with('valid-token-12345')
        
        # Verify authorization check was called
        mock_check_authz.assert_called_once_with('user@example.com', event['methodArn'])
        
        # Verify authentication success was logged
        mock_log_auth.assert_called_once()
        
        # Verify authorization attempt was logged
        mock_log_authz.assert_called_once()
        call_args = mock_log_authz.call_args[1]
        self.assertEqual(call_args['user_email'], 'user@example.com')
        self.assertEqual(call_args['decision'], 'ALLOW')
        
        # Verify Allow policy is returned
        self.assertEqual(result['principalId'], 'user@example.com')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Allow')
        
        # Verify context is included
        self.assertIn('context', result)
        self.assertEqual(result['context']['userEmail'], 'user@example.com')
        self.assertEqual(result['context']['userId'], 'user-123')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authentication_success')
    @patch('authorizer.log_authorization_attempt')
    def test_denied_authorization_flow(
        self, mock_log_authz, mock_log_auth, mock_check_authz, mock_validate
    ):
        """Test complete flow for denied authorization."""
        # Mock token validation
        mock_validate.return_value = {
            'email': 'unauthorized@example.com',
            'sub': 'user-456'
        }
        
        # Mock authorization check to deny
        mock_check_authz.return_value = False
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token-67890',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/POST/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-456'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify token validation was called
        mock_validate.assert_called_once()
        
        # Verify authorization check was called
        mock_check_authz.assert_called_once()
        
        # Verify authentication success was logged
        mock_log_auth.assert_called_once()
        
        # Verify authorization denial was logged
        mock_log_authz.assert_called_once()
        call_args = mock_log_authz.call_args[1]
        self.assertEqual(call_args['user_email'], 'unauthorized@example.com')
        self.assertEqual(call_args['decision'], 'DENY')
        
        # Verify Deny policy is returned
        self.assertEqual(result['principalId'], 'unauthorized@example.com')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestAuthenticationFailureFlow(unittest.TestCase):
    """Test authentication failure scenarios."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authentication_failure')
    def test_invalid_token_flow(self, mock_log_failure, mock_validate):
        """Test flow when token validation fails."""
        from token_validator import TokenValidationError
        mock_validate.side_effect = TokenValidationError("Invalid signature")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer invalid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-789'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify token validation was attempted
        mock_validate.assert_called_once()
        
        # Verify authentication failure was logged
        mock_log_failure.assert_called_once()
        call_args = mock_log_failure.call_args[1]
        self.assertEqual(call_args['reason'], 'Invalid signature')
        
        # Verify Deny policy is returned
        self.assertEqual(result['principalId'], 'invalid-token')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.log_authentication_failure')
    def test_missing_token_flow(self, mock_log_failure):
        """Test flow when token is missing."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-101'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify authentication failure was logged
        mock_log_failure.assert_called_once()
        
        # Verify Deny policy is returned
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.log_authentication_failure')
    def test_token_without_email_flow(self, mock_log_failure, mock_validate):
        """Test flow when token is missing email claim."""
        # Mock token validation to return claims without email
        mock_validate.return_value = {
            'sub': 'user-999',
            'iss': 'https://identity-center.example.com'
        }
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer token-without-email',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-202'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify authentication failure was logged
        mock_log_failure.assert_called_once()
        call_args = mock_log_failure.call_args[1]
        self.assertEqual(call_args['reason'], 'Token missing email claim')
        
        # Verify Deny policy is returned
        self.assertEqual(result['principalId'], 'no-email')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestAuthorizationErrorFlow(unittest.TestCase):
    """Test authorization error scenarios."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authentication_success')
    @patch('authorizer.log_authorization_error')
    def test_authorization_check_error_flow(
        self, mock_log_error, mock_log_auth, mock_check_authz, mock_validate
    ):
        """Test flow when authorization check raises an error."""
        # Mock token validation
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-303'
        }
        
        # Mock authorization check to raise error
        mock_check_authz.side_effect = Exception("Configuration error")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-303'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify authentication success was logged
        mock_log_auth.assert_called_once()
        
        # Verify authorization error was logged
        mock_log_error.assert_called_once()
        call_args = mock_log_error.call_args[1]
        self.assertIn('Configuration error', call_args['error_message'])
        
        # Verify Deny policy is returned
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestMultipleEndpoints(unittest.TestCase):
    """Test authorization for multiple endpoints."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_get_orders_endpoint(self, mock_check_authz, mock_validate):
        """Test authorization for GET /orders endpoint."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-get'
        
        result = lambda_handler(event, context)
        
        # Verify authorization was checked for correct endpoint
        mock_check_authz.assert_called_once_with('user@example.com', event['methodArn'])
        
        # Verify Allow policy
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Allow')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_post_orders_endpoint(self, mock_check_authz, mock_validate):
        """Test authorization for POST /orders endpoint."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/POST/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-post'
        
        result = lambda_handler(event, context)
        
        # Verify authorization was checked for correct endpoint
        mock_check_authz.assert_called_once_with('user@example.com', event['methodArn'])
        
        # Verify Allow policy
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Allow')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_put_orders_endpoint(self, mock_check_authz, mock_validate):
        """Test authorization for PUT /orders endpoint."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/PUT/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-put'
        
        result = lambda_handler(event, context)
        
        # Verify authorization was checked for correct endpoint
        mock_check_authz.assert_called_once_with('user@example.com', event['methodArn'])
        
        # Verify Allow policy
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Allow')


class TestContextPropagation(unittest.TestCase):
    """Test that user context is properly propagated to backend."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_context_includes_user_email(self, mock_check_authz, mock_validate):
        """Test that context includes user email."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123',
            'auth_time': 1234567890
        }
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-ctx'
        
        result = lambda_handler(event, context)
        
        # Verify context is included
        self.assertIn('context', result)
        self.assertEqual(result['context']['userEmail'], 'user@example.com')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_context_includes_user_id(self, mock_check_authz, mock_validate):
        """Test that context includes user ID."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-456',
            'auth_time': 1234567890
        }
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-ctx2'
        
        result = lambda_handler(event, context)
        
        # Verify context includes user ID
        self.assertEqual(result['context']['userId'], 'user-456')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_context_values_are_strings(self, mock_check_authz, mock_validate):
        """Test that all context values are strings (API Gateway requirement)."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-999',
            'auth_time': 1234567890
        }
        mock_check_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-ctx4'
        
        result = lambda_handler(event, context)
        
        # Verify all context values are strings
        for key, value in result['context'].items():
            self.assertIsInstance(value, str, f"Context value '{key}' should be string")


class TestErrorScenarios(unittest.TestCase):
    """Test various error scenarios."""
    
    def test_missing_method_arn(self):
        """Test handling of missing methodArn."""
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token'
        }
        
        context = Mock()
        context.request_id = 'test-request-err1'
        
        result = lambda_handler(event, context)
        
        # Should return Deny policy
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    def test_unexpected_exception_in_validation(self, mock_validate):
        """Test handling of unexpected exception during validation."""
        mock_validate.side_effect = Exception("Unexpected error")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-err2'
        
        result = lambda_handler(event, context)
        
        # Should return Deny policy
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


if __name__ == '__main__':
    unittest.main()
