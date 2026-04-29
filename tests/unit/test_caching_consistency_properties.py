"""
Property-Based Tests for Authorization Caching Consistency.

Feature: api-authentication-authorization, Property 7: Authorization Caching Consistency

Property 7: Authorization Caching Consistency
For any authorization decision cached by API Gateway, subsequent requests with 
the same token within the TTL period should receive the same authorization 
outcome without re-invoking the Lambda Authorizer.

Validates: Requirements 9.1, 9.2
"""

import unittest
import json
import os
import sys
from unittest.mock import Mock, patch, call
from hypothesis import given, strategies as st, settings

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

# Set environment variables
os.environ['AUTHORIZED_USERS'] = json.dumps({
    "authorized@example.com": {
        "permissions": ["GET", "POST", "PUT"],
        "resources": ["*"]
    }
})

from authorizer import lambda_handler


# Custom strategies for generating test data
@st.composite
def valid_token(draw):
    """Generate valid token strings."""
    prefix = draw(st.sampled_from(['token', 'jwt', 'auth']))
    suffix = draw(st.integers(min_value=1000, max_value=9999))
    return f"{prefix}-{suffix}"


@st.composite
def user_email(draw):
    """Generate user email addresses."""
    username = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll',), min_codepoint=97, max_codepoint=122),
        min_size=3,
        max_size=15
    ))
    domain = draw(st.sampled_from(['example.com', 'test.org', 'demo.net']))
    return f"{username}@{domain}"


@st.composite
def http_method(draw):
    """Generate valid HTTP methods."""
    return draw(st.sampled_from(['GET', 'POST', 'PUT']))


@st.composite
def api_resource(draw):
    """Generate valid API resource paths."""
    return draw(st.sampled_from(['/orders', '/items', '/products']))


@st.composite
def authorizer_event(draw, token=None):
    """Generate a valid Lambda Authorizer event."""
    if token is None:
        token = draw(valid_token())
    method = draw(http_method())
    resource = draw(api_resource())
    
    return {
        'type': 'TOKEN',
        'authorizationToken': f'Bearer {token}',
        'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}{resource}'
    }


class TestCachingConsistencyProperty(unittest.TestCase):
    """Property-based tests for authorization caching consistency."""
    
    @given(
        token=valid_token(),
        email=user_email(),
        num_requests=st.integers(min_value=2, max_value=10)
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_same_token_produces_consistent_allow_decisions(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        token,
        email,
        num_requests
    ):
        """
        Property: For any token that results in Allow, repeated requests 
        should produce identical Allow policies.
        
        This simulates caching behavior where the same token should always
        produce the same authorization decision.
        """
        # Setup: Mock token validation to return consistent user claims
        mock_validate.return_value = {
            'email': email,
            'sub': f'user-{hash(email) % 10000}',
            'auth_time': 1234567890
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Execute: Make multiple requests with the same token
        results = []
        for i in range(num_requests):
            event = {
                'type': 'TOKEN',
                'authorizationToken': f'Bearer {token}',
                'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api/dev/GET/orders'
            }
            context = Mock()
            context.request_id = f'test-request-{i}'
            
            result = lambda_handler(event, context)
            results.append(result)
        
        # Verify: All results should be identical Allow policies
        first_result = results[0]
        self.assertEqual(first_result['policyDocument']['Statement'][0]['Effect'], 'Allow',
                        f"First request should be allowed for token {token}")
        
        for i, result in enumerate(results[1:], start=1):
            # Verify: Same effect
            self.assertEqual(
                result['policyDocument']['Statement'][0]['Effect'],
                first_result['policyDocument']['Statement'][0]['Effect'],
                f"Request {i} has different effect than first request for token {token}"
            )
            
            # Verify: Same principal
            self.assertEqual(
                result['principalId'],
                first_result['principalId'],
                f"Request {i} has different principalId for token {token}"
            )
            
            # Verify: Same resource
            self.assertEqual(
                result['policyDocument']['Statement'][0]['Resource'],
                first_result['policyDocument']['Statement'][0]['Resource'],
                f"Request {i} has different resource for token {token}"
            )
            
            # Verify: Same context
            self.assertEqual(
                result.get('context', {}),
                first_result.get('context', {}),
                f"Request {i} has different context for token {token}"
            )
    
    @given(
        token=valid_token(),
        email=user_email(),
        num_requests=st.integers(min_value=2, max_value=10)
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_same_token_produces_consistent_deny_decisions(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        token,
        email,
        num_requests
    ):
        """
        Property: For any token that results in Deny, repeated requests 
        should produce identical Deny policies.
        
        This ensures caching consistency for denied requests as well.
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': email,
            'sub': f'user-{hash(email) % 10000}',
            'auth_time': 1234567890
        }
        
        # Setup: Mock authorization to fail
        mock_check_authz.return_value = False
        
        # Execute: Make multiple requests with the same token
        results = []
        for i in range(num_requests):
            event = {
                'type': 'TOKEN',
                'authorizationToken': f'Bearer {token}',
                'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api/dev/POST/orders'
            }
            context = Mock()
            context.request_id = f'test-request-{i}'
            
            result = lambda_handler(event, context)
            results.append(result)
        
        # Verify: All results should be identical Deny policies
        first_result = results[0]
        self.assertEqual(first_result['policyDocument']['Statement'][0]['Effect'], 'Deny',
                        f"First request should be denied for token {token}")
        
        for i, result in enumerate(results[1:], start=1):
            # Verify: Same effect (Deny)
            self.assertEqual(
                result['policyDocument']['Statement'][0]['Effect'],
                first_result['policyDocument']['Statement'][0]['Effect'],
                f"Request {i} has different effect than first request for token {token}"
            )
            
            # Verify: Same principal
            self.assertEqual(
                result['principalId'],
                first_result['principalId'],
                f"Request {i} has different principalId for token {token}"
            )
    
    @given(
        token=valid_token(),
        email=user_email(),
        method=http_method(),
        resource=api_resource(),
        num_requests=st.integers(min_value=2, max_value=8)
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_same_token_same_endpoint_produces_consistent_results(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        token,
        email,
        method,
        resource,
        num_requests
    ):
        """
        Property: For any token and endpoint combination, repeated requests 
        should produce consistent authorization decisions.
        
        This tests caching consistency across different endpoints.
        """
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': email,
            'sub': f'user-{hash(email) % 10000}',
            'auth_time': 1234567890
        }
        
        # Setup: Mock authorization (randomly allow or deny based on email hash)
        is_authorized = (hash(email) % 2 == 0)
        mock_check_authz.return_value = is_authorized
        
        # Execute: Make multiple requests to the same endpoint with same token
        results = []
        for i in range(num_requests):
            event = {
                'type': 'TOKEN',
                'authorizationToken': f'Bearer {token}',
                'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api/dev/{method}{resource}'
            }
            context = Mock()
            context.request_id = f'test-{method}-{resource}-{i}'
            
            result = lambda_handler(event, context)
            results.append(result)
        
        # Verify: All results should have the same effect
        first_effect = results[0]['policyDocument']['Statement'][0]['Effect']
        
        for i, result in enumerate(results):
            self.assertEqual(
                result['policyDocument']['Statement'][0]['Effect'],
                first_effect,
                f"Request {i} to {method} {resource} has inconsistent effect for token {token}"
            )
    
    @given(
        token=valid_token(),
        email=user_email(),
        num_requests=st.integers(min_value=3, max_value=10)
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_wildcard_resource_consistent_across_requests(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        token,
        email,
        num_requests
    ):
        """
        Property: For any token, the wildcard resource in the policy should 
        be consistent across all requests.
        
        This ensures that caching can work properly with wildcard resources.
        """
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': email,
            'sub': f'user-{hash(email) % 10000}',
            'auth_time': 1234567890
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Execute: Make multiple requests with the same token
        resources = []
        for i in range(num_requests):
            event = {
                'type': 'TOKEN',
                'authorizationToken': f'Bearer {token}',
                'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api123/dev/GET/orders'
            }
            context = Mock()
            context.request_id = f'test-wildcard-{i}'
            
            result = lambda_handler(event, context)
            resource = result['policyDocument']['Statement'][0]['Resource']
            resources.append(resource)
        
        # Verify: All resources should be identical (wildcard)
        first_resource = resources[0]
        for i, resource in enumerate(resources[1:], start=1):
            self.assertEqual(
                resource,
                first_resource,
                f"Request {i} has different wildcard resource for token {token}"
            )
    
    @given(
        token=valid_token(),
        email=user_email(),
        num_requests=st.integers(min_value=2, max_value=10)
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_policy_structure_consistent_across_requests(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        token,
        email,
        num_requests
    ):
        """
        Property: For any token, the policy document structure should be 
        consistent across all requests.
        
        This ensures that cached policies have the same structure.
        """
        # Setup: Mock token validation
        mock_validate.return_value = {
            'email': email,
            'sub': f'user-{hash(email) % 10000}',
            'auth_time': 1234567890
        }
        
        # Setup: Mock authorization
        mock_check_authz.return_value = True
        
        # Execute: Make multiple requests with the same token
        policies = []
        for i in range(num_requests):
            event = {
                'type': 'TOKEN',
                'authorizationToken': f'Bearer {token}',
                'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api/dev/GET/orders'
            }
            context = Mock()
            context.request_id = f'test-structure-{i}'
            
            result = lambda_handler(event, context)
            policies.append(result['policyDocument'])
        
        # Verify: All policies should have the same structure
        first_policy = policies[0]
        
        for i, policy in enumerate(policies[1:], start=1):
            # Verify: Same version
            self.assertEqual(
                policy.get('Version'),
                first_policy.get('Version'),
                f"Request {i} has different policy version for token {token}"
            )
            
            # Verify: Same number of statements
            self.assertEqual(
                len(policy.get('Statement', [])),
                len(first_policy.get('Statement', [])),
                f"Request {i} has different number of statements for token {token}"
            )
            
            # Verify: Same statement structure
            if policy.get('Statement'):
                first_stmt = first_policy['Statement'][0]
                curr_stmt = policy['Statement'][0]
                
                self.assertEqual(
                    curr_stmt.get('Action'),
                    first_stmt.get('Action'),
                    f"Request {i} has different Action for token {token}"
                )
                
                self.assertEqual(
                    curr_stmt.get('Effect'),
                    first_stmt.get('Effect'),
                    f"Request {i} has different Effect for token {token}"
                )
    
    @given(
        token=valid_token(),
        email=user_email()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_context_values_consistent_for_same_token(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        token,
        email
    ):
        """
        Property: For any authorized token, the context values should be 
        consistent across multiple requests.
        
        This ensures that cached authorization includes consistent user context.
        """
        # Setup: Mock token validation with specific claims
        user_id = f'user-{hash(email) % 10000}'
        auth_time = 1234567890
        
        mock_validate.return_value = {
            'email': email,
            'sub': user_id,
            'auth_time': auth_time
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Execute: Make two requests with the same token
        event = {
            'type': 'TOKEN',
            'authorizationToken': f'Bearer {token}',
            'methodArn': 'arn:aws:execute-api:us-west-2:123456789012:api/dev/GET/orders'
        }
        
        context1 = Mock()
        context1.request_id = 'test-context-1'
        result1 = lambda_handler(event, context1)
        
        context2 = Mock()
        context2.request_id = 'test-context-2'
        result2 = lambda_handler(event, context2)
        
        # Verify: Both results should have the same context values
        self.assertEqual(
            result1.get('context', {}).get('userEmail'),
            result2.get('context', {}).get('userEmail'),
            f"userEmail inconsistent for token {token}"
        )
        
        self.assertEqual(
            result1.get('context', {}).get('userId'),
            result2.get('context', {}).get('userId'),
            f"userId inconsistent for token {token}"
        )
        
        self.assertEqual(
            result1.get('context', {}).get('authTime'),
            result2.get('context', {}).get('authTime'),
            f"authTime inconsistent for token {token}"
        )


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
