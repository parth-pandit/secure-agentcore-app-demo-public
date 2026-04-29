"""
Unit tests for Lambda Authorizer core functionality.

Tests token extraction, IAM policy generation, and error handling.
"""

import unittest
import json
import sys
import os
from unittest.mock import Mock, patch

# Add backend/src/lambdas to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

from authorizer import (
    extract_token,
    generate_policy,
    generate_allow_policy,
    generate_deny_policy,
    get_method_specific_resource,
    handle_error,
    TokenExtractionError,
    AuthorizerError
)


class TestTokenExtraction(unittest.TestCase):
    """Test token extraction from Authorization header"""
    
    def test_extract_valid_token(self):
        """Test extracting a valid Bearer token"""
        event = {
            'authorizationToken': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token'
        }
        token = extract_token(event)
        self.assertEqual(token, 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token')
    
    def test_extract_token_with_extra_spaces(self):
        """Test extracting token with extra spaces after Bearer"""
        event = {
            'authorizationToken': 'Bearer    eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token'
        }
        token = extract_token(event)
        self.assertEqual(token, 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token')
    
    def test_extract_token_missing_authorization(self):
        """Test error when authorizationToken is missing"""
        event = {}
        with self.assertRaises(TokenExtractionError) as context:
            extract_token(event)
        self.assertIn('Missing authorization token', str(context.exception))
    
    def test_extract_token_empty_string(self):
        """Test error when authorizationToken is empty"""
        event = {'authorizationToken': ''}
        with self.assertRaises(TokenExtractionError) as context:
            extract_token(event)
        self.assertIn('Missing authorization token', str(context.exception))
    
    def test_extract_token_missing_bearer_prefix(self):
        """Test error when Bearer prefix is missing"""
        event = {'authorizationToken': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token'}
        with self.assertRaises(TokenExtractionError) as context:
            extract_token(event)
        self.assertIn('Bearer', str(context.exception))
    
    def test_extract_token_only_bearer(self):
        """Test error when only 'Bearer ' is present without token"""
        event = {'authorizationToken': 'Bearer '}
        with self.assertRaises(TokenExtractionError) as context:
            extract_token(event)
        self.assertIn('Empty', str(context.exception))
    
    def test_extract_token_case_sensitive(self):
        """Test that Bearer prefix is case-sensitive"""
        event = {'authorizationToken': 'bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token'}
        with self.assertRaises(TokenExtractionError):
            extract_token(event)


class TestPolicyGeneration(unittest.TestCase):
    """Test IAM policy document generation"""
    
    def test_generate_allow_policy(self):
        """Test generating an Allow policy"""
        policy = generate_policy(
            'user@example.com',
            'Allow',
            'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        )
        
        self.assertEqual(policy['principalId'], 'user@example.com')
        self.assertEqual(policy['policyDocument']['Version'], '2012-10-17')
        self.assertEqual(len(policy['policyDocument']['Statement']), 1)
        
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Action'], 'execute-api:Invoke')
        self.assertEqual(statement['Effect'], 'Allow')
        self.assertEqual(statement['Resource'], 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders')
    
    def test_generate_deny_policy(self):
        """Test generating a Deny policy"""
        policy = generate_policy(
            'user@example.com',
            'Deny',
            'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/POST/orders'
        )
        
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
    
    def test_generate_policy_with_context(self):
        """Test generating policy with context"""
        context = {
            'userEmail': 'user@example.com',
            'userName': 'Test User',
            'timestamp': '2025-12-27T12:00:00Z'
        }
        
        policy = generate_policy(
            'user@example.com',
            'Allow',
            'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders',
            context
        )
        
        self.assertIn('context', policy)
        self.assertEqual(policy['context']['userEmail'], 'user@example.com')
        self.assertEqual(policy['context']['userName'], 'Test User')
        self.assertEqual(policy['context']['timestamp'], '2025-12-27T12:00:00Z')
    
    def test_generate_policy_context_values_are_strings(self):
        """Test that context values are converted to strings"""
        context = {
            'userEmail': 'user@example.com',
            'requestCount': 42,
            'isAdmin': True
        }
        
        policy = generate_policy(
            'user@example.com',
            'Allow',
            'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders',
            context
        )
        
        # All context values should be strings
        self.assertEqual(policy['context']['requestCount'], '42')
        self.assertEqual(policy['context']['isAdmin'], 'True')
    
    def test_generate_policy_invalid_effect(self):
        """Test error when effect is invalid"""
        with self.assertRaises(ValueError) as context:
            generate_policy('user@example.com', 'Maybe', 'arn:aws:execute-api:*')
        self.assertIn('Invalid effect', str(context.exception))
    
    def test_generate_allow_policy_helper(self):
        """Test generate_allow_policy helper function"""
        policy = generate_allow_policy(
            'user@example.com',
            'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        )
        
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Allow')
    
    def test_generate_deny_policy_helper(self):
        """Test generate_deny_policy helper function"""
        policy = generate_deny_policy(
            'user@example.com',
            'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        )
        
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')


class TestWildcardResource(unittest.TestCase):
    """Test method-specific resource ARN (no wildcards for security)"""
    
    def test_get_method_specific_resource_full_arn(self):
        """Test that method ARN is returned as-is for fine-grained authorization"""
        method_arn = 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        result = get_method_specific_resource(method_arn)
        self.assertEqual(result, method_arn)
    
    def test_get_method_specific_resource_different_stage(self):
        """Test method-specific resource with different stage"""
        method_arn = 'arn:aws:execute-api:us-east-1:987654321098:xyz789/prod/POST/orders'
        result = get_method_specific_resource(method_arn)
        self.assertEqual(result, method_arn)
    
    def test_get_method_specific_resource_nested_path(self):
        """Test method-specific resource with nested resource path"""
        method_arn = 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/PUT/orders/123/items'
        result = get_method_specific_resource(method_arn)
        self.assertEqual(result, method_arn)


class TestErrorHandling(unittest.TestCase):
    """Test error handling functionality"""
    
    def test_handle_token_extraction_error(self):
        """Test handling TokenExtractionError"""
        error = TokenExtractionError("Invalid token format")
        method_arn = 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        
        policy = handle_error(error, method_arn)
        
        self.assertEqual(policy['principalId'], 'unauthorized')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
        self.assertEqual(statement['Resource'], 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/*/*')
    
    def test_handle_authorizer_error(self):
        """Test handling AuthorizerError"""
        error = AuthorizerError("Authorization failed")
        method_arn = 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/POST/orders'
        
        policy = handle_error(error, method_arn)
        
        self.assertEqual(policy['principalId'], 'unauthorized')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
    
    def test_handle_generic_exception(self):
        """Test handling generic Exception"""
        error = Exception("Unexpected error")
        method_arn = 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/PUT/orders'
        
        policy = handle_error(error, method_arn)
        
        self.assertEqual(policy['principalId'], 'unauthorized')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')


class TestLambdaHandler(unittest.TestCase):
    """Test the main Lambda handler function"""
    
    @patch('authorizer.validate_token')
    def test_handler_with_valid_token_calls_validation(self, mock_validate):
        """Test handler calls token validation with valid token"""
        from authorizer import lambda_handler
        from token_validator import TokenValidationError
        
        # Mock validation to fail (simulating invalid token)
        mock_validate.side_effect = TokenValidationError("Invalid token")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-123'
        
        policy = lambda_handler(event, context)
        
        # Should call validate_token
        mock_validate.assert_called_once()
        
        # Should return deny policy since validation failed
        self.assertEqual(policy['principalId'], 'invalid-token')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
    
    def test_handler_with_missing_token(self):
        """Test handler with missing token"""
        from authorizer import lambda_handler
        
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        }
        
        policy = lambda_handler(event, None)
        
        self.assertEqual(policy['principalId'], 'unauthorized')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
    
    def test_handler_with_invalid_token_format(self):
        """Test handler with invalid token format"""
        from authorizer import lambda_handler
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'InvalidToken',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders'
        }
        
        policy = lambda_handler(event, None)
        
        self.assertEqual(policy['principalId'], 'unauthorized')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
    
    def test_handler_with_missing_method_arn(self):
        """Test handler with missing methodArn"""
        from authorizer import lambda_handler
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token'
        }
        
        policy = lambda_handler(event, None)
        
        self.assertEqual(policy['principalId'], 'unauthorized')
        statement = policy['policyDocument']['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')


if __name__ == '__main__':
    unittest.main()
