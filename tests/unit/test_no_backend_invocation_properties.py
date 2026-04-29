"""
Property-based tests for no backend invocation on auth failure.

Property 8: No Backend Invocation on Auth Failure
- Authentication/authorization failures must not invoke backend Lambda
- Deny policies must prevent API Gateway from forwarding requests
- Backend should never receive requests from unauthorized users
- Validates Requirements: 3.4
"""

import unittest
import json
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, 'backend/src/lambdas')

from authorizer import lambda_handler

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


class TestNoBackendInvocationProperties(unittest.TestCase):
    """Property-based tests for no backend invocation on auth failure."""
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    def test_property_missing_token_returns_deny_policy(self, method, resource):
        """
        Property: Missing token must return Deny policy.
        
        For any endpoint, a missing token must result in a Deny policy
        that prevents API Gateway from invoking the backend.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        event = {
            'type': 'TOKEN',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Verify Deny policy is returned
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify policy structure prevents backend invocation
        self.assertIn('policyDocument', result)
        self.assertIn('Statement', result['policyDocument'])
        self.assertEqual(result['policyDocument']['Statement'][0]['Action'], 'execute-api:Invoke')
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    @patch('authorizer.validate_token')
    def test_property_invalid_token_returns_deny_policy(self, mock_validate, method, resource):
        """
        Property: Invalid token must return Deny policy.
        
        For any endpoint, an invalid token must result in a Deny policy.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Mock token validation to fail
        from token_validator import TokenValidationError
        mock_validate.side_effect = TokenValidationError("Invalid signature")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer invalid-token',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Verify Deny policy is returned
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50),
        user_email=st.emails()
    )
    @settings(max_examples=50, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_property_unauthorized_user_returns_deny_policy(
        self, mock_authz, mock_validate, method, resource, user_email
    ):
        """
        Property: Unauthorized user must return Deny policy.
        
        For any endpoint, even with valid token, unauthorized users
        must receive a Deny policy.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Mock token validation to succeed
        mock_validate.return_value = {
            'email': user_email,
            'sub': 'user-123'
        }
        
        # Mock authorization to fail
        mock_authz.return_value = False
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Verify Deny policy is returned
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
        self.assertEqual(result['principalId'], user_email)
    
    @given(
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    @patch('authorizer.validate_token')
    def test_property_auth_failure_never_calls_backend(self, mock_validate, method, resource):
        """
        Property: Authentication failures must not proceed to authorization.
        
        When token validation fails, authorization check should not be called,
        ensuring no backend processing occurs.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Mock token validation to fail
        from token_validator import TokenValidationError
        mock_validate.side_effect = TokenValidationError("Token expired")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer expired-token',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}/{resource}'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        with patch('authorizer.check_authorization') as mock_authz:
            result = lambda_handler(event, context)
            
            # Authorization check should NOT have been called
            mock_authz.assert_not_called()
            
            # Verify Deny policy is returned
            self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestDenyPolicyStructure(unittest.TestCase):
    """Test that Deny policies have correct structure to prevent backend invocation."""
    
    def test_deny_policy_has_required_fields(self):
        """Test that Deny policy contains all required fields."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Verify required fields
        self.assertIn('principalId', result)
        self.assertIn('policyDocument', result)
        self.assertIn('Version', result['policyDocument'])
        self.assertIn('Statement', result['policyDocument'])
        
        # Verify statement structure
        statement = result['policyDocument']['Statement'][0]
        self.assertIn('Action', statement)
        self.assertIn('Effect', statement)
        self.assertIn('Resource', statement)
        
        # Verify Deny effect
        self.assertEqual(statement['Effect'], 'Deny')
    
    def test_deny_policy_applies_to_wildcard_resource(self):
        """Test that Deny policy applies to wildcard resource for caching."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Verify resource is wildcard for caching
        resource = result['policyDocument']['Statement'][0]['Resource']
        self.assertIn('*', resource)
        self.assertIn('api123', resource)
        self.assertIn('dev', resource)
    
    def test_deny_policy_action_is_execute_api_invoke(self):
        """Test that Deny policy denies execute-api:Invoke action."""
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer invalid',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/POST/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Verify action
        action = result['policyDocument']['Statement'][0]['Action']
        self.assertEqual(action, 'execute-api:Invoke')


class TestAuthenticationFailureScenarios(unittest.TestCase):
    """Test specific authentication failure scenarios."""
    
    def test_missing_authorization_header_denies(self):
        """Test that missing authorization header results in Deny."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    def test_empty_authorization_header_denies(self):
        """Test that empty authorization header results in Deny."""
        event = {
            'type': 'TOKEN',
            'authorizationToken': '',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    def test_malformed_bearer_token_denies(self):
        """Test that malformed Bearer token results in Deny."""
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'NotBearer token123',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    def test_expired_token_denies(self, mock_validate):
        """Test that expired token results in Deny."""
        from token_validator import TokenValidationError
        mock_validate.side_effect = TokenValidationError("Token expired")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer expired-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    def test_invalid_signature_denies(self, mock_validate):
        """Test that invalid signature results in Deny."""
        from token_validator import TokenValidationError
        mock_validate.side_effect = TokenValidationError("Invalid signature")
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer tampered-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestAuthorizationFailureScenarios(unittest.TestCase):
    """Test specific authorization failure scenarios."""
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_valid_token_insufficient_permissions_denies(self, mock_authz, mock_validate):
        """Test that valid token with insufficient permissions results in Deny."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        mock_authz.return_value = False
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/DELETE/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_valid_token_wrong_resource_denies(self, mock_authz, mock_validate):
        """Test that valid token for wrong resource results in Deny."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        mock_authz.return_value = False
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/admin'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')


class TestNoContextInDenyPolicy(unittest.TestCase):
    """Test that Deny policies do not include context."""
    
    def test_deny_policy_has_no_context(self):
        """Test that Deny policies do not include context field."""
        event = {
            'type': 'TOKEN',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Deny policy should not have context
        self.assertNotIn('context', result)
    
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    def test_unauthorized_deny_policy_has_no_context(self, mock_authz, mock_validate):
        """Test that unauthorized Deny policies do not include context."""
        mock_validate.return_value = {
            'email': 'user@example.com',
            'sub': 'user-123'
        }
        mock_authz.return_value = False
        
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer valid-token',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/POST/orders'
        }
        
        context = Mock()
        context.request_id = 'test-request-123'
        
        result = lambda_handler(event, context)
        
        # Deny policy should not have context
        self.assertNotIn('context', result)


if __name__ == '__main__':
    unittest.main()
