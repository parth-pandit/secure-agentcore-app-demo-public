"""
Property-based tests for authentication requirement.

Property 1: Authentication Required for All Endpoints
- Every API endpoint must require authentication
- Requests without valid tokens must be denied
- No endpoint should be accessible without authentication
- Validates Requirements: 1.1, 3.1, 3.2
"""

import unittest
import json
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, 'backend/src/lambdas')

from authorizer import lambda_handler, generate_deny_policy

# Try to import hypothesis for property-based testing
try:
    from hypothesis import given, strategies as st, settings, assume
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Warning: hypothesis not available, property tests will be skipped")
    # Create dummy decorators
    def given(*args, **kwargs):
        def decorator(func):
            return lambda self: self.skipTest("Hypothesis not installed")
        return decorator
    
    def settings(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    def assume(condition):
        pass
    
    class DummyStrategy:
        def filter(self, *args, **kwargs):
            return self
    
    class st:
        @staticmethod
        def text(**kwargs):
            return DummyStrategy()
        
        @staticmethod
        def sampled_from(items):
            return DummyStrategy()
        
        @staticmethod
        def dictionaries(keys, values, **kwargs):
            return DummyStrategy()
        
        @staticmethod
        def one_of(*args):
            return DummyStrategy()
        
        @staticmethod
        def none():
            return DummyStrategy()


class TestAuthenticationRequirementProperties(unittest.TestCase):
    """Property-based tests for authentication requirement."""
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    def test_property_missing_token_denies_access(self, method, resource):
        """
        Property: Requests without authorization token must be denied.
        
        For any endpoint and method, a request without an authorization
        token must result in a Deny policy.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Create event without authorization token
        event = {
            'type': 'TOKEN',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        # Call authorizer
        result = lambda_handler(event, context)
        
        # Verify access is denied
        self.assertEqual(result['principalId'], 'unauthorized')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    def test_property_empty_token_denies_access(self, method, resource):
        """
        Property: Requests with empty authorization token must be denied.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Create event with empty token
        event = {
            'type': 'TOKEN',
            'authorizationToken': '',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        # Call authorizer
        result = lambda_handler(event, context)
        
        # Verify access is denied
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50),
        token=st.text(min_size=1, max_size=100)
    )
    @settings(max_examples=50)
    def test_property_token_without_bearer_prefix_denies_access(self, method, resource, token):
        """
        Property: Requests with token missing 'Bearer ' prefix must be denied.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Ensure token doesn't start with 'Bearer '
        assume(not token.startswith('Bearer '))
        
        # Create event with token missing Bearer prefix
        event = {
            'type': 'TOKEN',
            'authorizationToken': token,
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        # Call authorizer
        result = lambda_handler(event, context)
        
        # Verify access is denied
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    @patch('authorizer.validate_token')
    def test_property_invalid_token_denies_access(self, mock_validate, method, resource):
        """
        Property: Requests with invalid tokens must be denied.
        
        For any endpoint, if token validation fails, access must be denied.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Mock token validation to fail
        from token_validator import TokenValidationError
        mock_validate.side_effect = TokenValidationError("Invalid token")
        
        # Create event with invalid token
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer invalid-token-12345',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        # Call authorizer
        result = lambda_handler(event, context)
        
        # Verify access is denied
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
        self.assertEqual(result['principalId'], 'invalid-token')
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    @patch('authorizer.validate_token')
    def test_property_token_without_email_denies_access(self, mock_validate, method, resource):
        """
        Property: Tokens without email claim must be denied.
        
        Even if token is valid, it must contain an email claim.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Mock token validation to return claims without email
        mock_validate.return_value = {
            'sub': 'user-123',
            'iss': 'https://identity-center.example.com'
        }
        
        # Create event
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token-without-email',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        # Call authorizer
        result = lambda_handler(event, context)
        
        # Verify access is denied
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
        self.assertEqual(result['principalId'], 'no-email')


class TestAuthenticationForAllEndpoints(unittest.TestCase):
    """Test that authentication is required for all endpoints."""
    
    def test_get_orders_requires_authentication(self):
        """Test that GET /orders requires authentication."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny without token
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    def test_post_orders_requires_authentication(self):
        """Test that POST /orders requires authentication."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/POST/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny without token
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    def test_put_orders_requires_authentication(self):
        """Test that PUT /orders requires authentication."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/PUT/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny without token
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    def test_valid_token_proceeds_to_authorization(self, mock_validate):
        """Test that valid token proceeds to authorization check."""
        # Mock token validation to succeed
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        with patch('authorizer.check_authorization') as mock_authz:
            mock_authz.return_value = False  # User not authorized
            
            result = lambda_handler(event, context)
            
            # Token validation should have been called
            mock_validate.assert_called_once()
            
            # Authorization check should have been called
            mock_authz.assert_called_once_with('user@example.com', event['methodArn'])
            
            # Should deny due to authorization failure
            self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestFailClosedBehavior(unittest.TestCase):
    """Test that authorizer fails closed on errors."""
    
    @patch('authorizer.validate_token')
    def test_token_validation_exception_denies_access(self, mock_validate):
        """Test that exceptions during token validation result in denial."""
        # Mock token validation to raise unexpected exception
        mock_validate.side_effect = Exception("Unexpected error")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer some-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny access
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_authorization_exception_denies_access(self, mock_authz, mock_validate):
        """Test that exceptions during authorization result in denial."""
        # Mock token validation to succeed
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        
        # Mock authorization to raise exception
        mock_authz.side_effect = Exception("Authorization error")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny access
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    def test_malformed_event_denies_access(self):
        """Test that malformed events result in denial."""
        # Event missing methodArn
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer some-token'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny access
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestPolicyGeneration(unittest.TestCase):
    """Test that policies are generated correctly."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_authorized_request_generates_allow_policy(self, mock_authz, mock_validate):
        """Test that authorized requests generate Allow policies."""
        # Mock token validation to succeed
        mock_validate.return_value = {
            'email': 'authorized@example.com',
            'sub': 'user-123',
            'auth_time': 1234567890
        }
        
        # Mock authorization to succeed
        mock_authz.return_value = True
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should allow access
        self.assertEqual(result['principalId'], 'authorized@example.com')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Allow')
        
        # Should include context
        self.assertIn('context', result)
        self.assertEqual(result['context']['userEmail'], 'authorized@example.com')
        self.assertEqual(result['context']['userId'], 'user-123')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_unauthorized_request_generates_deny_policy(self, mock_authz, mock_validate):
        """Test that unauthorized requests generate Deny policies."""
        # Mock token validation to succeed
        mock_validate.return_value = {
            'email': 'unauthorized@example.com',
            'sub': 'user-456'
        }
        
        # Mock authorization to fail
        mock_authz.return_value = False
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/POST/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Should deny access
        self.assertEqual(result['principalId'], 'unauthorized@example.com')
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


if __name__ == '__main__':
    unittest.main()
