"""
Property-Based Tests for User Context Propagation.

Feature: api-authentication-authorization, Property 9: User Context Propagation

Property 9: User Context Propagation
For any authorized request, the Lambda Authorizer should pass user context 
(email, name, timestamp) to the backend Lambda function for additional 
logging and auditing.

Validates: Requirements 1.5, 4.1
"""

import unittest
import json
import os
import sys
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings, assume

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

# Set environment variables
os.environ['AUTHORIZED_USERS'] = json.dumps({
    "test@example.com": {
        "permissions": ["GET", "POST", "PUT"],
        "resources": ["*"]
    }
})

from authorizer import lambda_handler


# Custom strategies for generating test data
@st.composite
def valid_email(draw):
    """Generate valid email addresses."""
    username = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Nd'), min_codepoint=97, max_codepoint=122),
        min_size=3,
        max_size=20
    ))
    domain = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll',), min_codepoint=97, max_codepoint=122),
        min_size=3,
        max_size=15
    ))
    tld = draw(st.sampled_from(['com', 'org', 'net', 'edu', 'gov']))
    return f"{username}@{domain}.{tld}"


@st.composite
def valid_user_id(draw):
    """Generate valid user IDs."""
    prefix = draw(st.sampled_from(['user', 'usr', 'id']))
    number = draw(st.integers(min_value=1, max_value=999999))
    return f"{prefix}-{number}"


@st.composite
def valid_timestamp(draw):
    """Generate valid Unix timestamps."""
    # Generate timestamps from 2020 to 2030
    return draw(st.integers(min_value=1577836800, max_value=1893456000))


@st.composite
def http_method(draw):
    """Generate valid HTTP methods."""
    return draw(st.sampled_from(['GET', 'POST', 'PUT', 'DELETE', 'PATCH']))


@st.composite
def api_resource(draw):
    """Generate valid API resource paths."""
    return draw(st.sampled_from(['/orders', '/users', '/products', '/items']))


@st.composite
def authorizer_event(draw):
    """Generate a valid Lambda Authorizer event."""
    method = draw(http_method())
    resource = draw(api_resource())
    
    return {
        'type': 'TOKEN',
        'authorizationToken': 'Bearer mock-token-12345',
        'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api123/dev/{method}{resource}'
    }


class TestContextPropagationProperty(unittest.TestCase):
    """Property-based tests for user context propagation."""
    
    @given(
        user_email=valid_email(),
        user_id=valid_user_id(),
        auth_time=valid_timestamp(),
        event=authorizer_event()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_context_includes_user_email_for_all_authorized_requests(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        user_email,
        user_id,
        auth_time,
        event
    ):
        """
        Property: For any authorized request, context must include user email.
        
        This test verifies that regardless of the specific user, endpoint, or
        method, the authorizer always includes the user's email in the context
        when authorization succeeds.
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': user_email,
            'sub': user_id,
            'auth_time': auth_time
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Create context
        context = Mock()
        context.request_id = f'test-request-{user_id}'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify: Policy allows access
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Allow')
        
        # Verify: Context is included
        self.assertIn('context', result, 
                     f"Context missing for user {user_email}")
        
        # Verify: User email is in context
        self.assertIn('userEmail', result['context'],
                     f"userEmail missing in context for {user_email}")
        self.assertEqual(result['context']['userEmail'], user_email,
                        f"userEmail mismatch for {user_email}")
    
    @given(
        user_email=valid_email(),
        user_id=valid_user_id(),
        auth_time=valid_timestamp(),
        event=authorizer_event()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_context_includes_user_id_for_all_authorized_requests(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        user_email,
        user_id,
        auth_time,
        event
    ):
        """
        Property: For any authorized request, context must include user ID.
        
        This test verifies that the user ID (sub claim) is always propagated
        to the backend Lambda functions through the context.
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': user_email,
            'sub': user_id,
            'auth_time': auth_time
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Create context
        context = Mock()
        context.request_id = f'test-request-{user_id}'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify: Context includes user ID
        self.assertIn('userId', result['context'],
                     f"userId missing in context for {user_email}")
        self.assertEqual(result['context']['userId'], user_id,
                        f"userId mismatch for {user_email}")
    
    @given(
        user_email=valid_email(),
        user_id=valid_user_id(),
        auth_time=valid_timestamp(),
        event=authorizer_event()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_context_includes_auth_time_for_all_authorized_requests(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        user_email,
        user_id,
        auth_time,
        event
    ):
        """
        Property: For any authorized request, context must include auth time.
        
        This test verifies that the authentication timestamp is always
        propagated to backend Lambda functions for audit logging.
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': user_email,
            'sub': user_id,
            'auth_time': auth_time
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Create context
        context = Mock()
        context.request_id = f'test-request-{user_id}'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify: Context includes auth time
        self.assertIn('authTime', result['context'],
                     f"authTime missing in context for {user_email}")
        self.assertEqual(result['context']['authTime'], str(auth_time),
                        f"authTime mismatch for {user_email}")
    
    @given(
        user_email=valid_email(),
        user_id=valid_user_id(),
        auth_time=valid_timestamp(),
        event=authorizer_event()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_all_context_values_are_strings(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        user_email,
        user_id,
        auth_time,
        event
    ):
        """
        Property: For any authorized request, all context values must be strings.
        
        API Gateway requires all context values to be strings. This test verifies
        that regardless of the input types, all context values are converted to
        strings before being returned.
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': user_email,
            'sub': user_id,
            'auth_time': auth_time
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Create context
        context = Mock()
        context.request_id = f'test-request-{user_id}'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify: All context values are strings
        for key, value in result['context'].items():
            self.assertIsInstance(value, str,
                                f"Context value '{key}' is not a string: {type(value)}")
    
    @given(
        user_email=valid_email(),
        user_id=valid_user_id(),
        auth_time=valid_timestamp(),
        method=http_method(),
        resource=api_resource()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_context_propagated_for_all_http_methods(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        user_email,
        user_id,
        auth_time,
        method,
        resource
    ):
        """
        Property: Context is propagated for all HTTP methods and resources.
        
        This test verifies that user context propagation works consistently
        across all HTTP methods (GET, POST, PUT, etc.) and all API resources.
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': user_email,
            'sub': user_id,
            'auth_time': auth_time
        }
        
        # Setup: Mock authorization to succeed
        mock_check_authz.return_value = True
        
        # Create event for specific method and resource
        event = {
            'type': 'TOKEN',
            'authorizationToken': 'Bearer mock-token',
            'methodArn': f'arn:aws:execute-api:us-west-2:123456789012:api/dev/{method}{resource}'
        }
        
        # Create context
        context = Mock()
        context.request_id = f'test-{method}-{resource}'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify: Context is complete regardless of method/resource
        self.assertIn('context', result,
                     f"Context missing for {method} {resource}")
        self.assertIn('userEmail', result['context'],
                     f"userEmail missing for {method} {resource}")
        self.assertIn('userId', result['context'],
                     f"userId missing for {method} {resource}")
        self.assertIn('authTime', result['context'],
                     f"authTime missing for {method} {resource}")
        
        # Verify: Context values are correct
        self.assertEqual(result['context']['userEmail'], user_email)
        self.assertEqual(result['context']['userId'], user_id)
        self.assertEqual(result['context']['authTime'], str(auth_time))
    
    @given(
        user_email=valid_email(),
        user_id=valid_user_id(),
        event=authorizer_event()
    )
    @settings(max_examples=100, deadline=None)
    @patch('authorizer.validate_token')
    @patch('authorizer.check_authorization')
    @patch('authorizer.log_authorization_attempt')
    @patch('authorizer.log_authentication_success')
    def test_context_not_included_for_denied_requests(
        self,
        mock_log_auth,
        mock_log_authz,
        mock_check_authz,
        mock_validate,
        user_email,
        user_id,
        event
    ):
        """
        Property: Context should not be included when authorization is denied.
        
        This test verifies that when a request is denied, no user context is
        propagated to the backend (since the backend won't be invoked).
        """
        # Setup: Mock token validation to return user claims
        mock_validate.return_value = {
            'email': user_email,
            'sub': user_id,
            'auth_time': 1234567890
        }
        
        # Setup: Mock authorization to fail
        mock_check_authz.return_value = False
        
        # Create context
        context = Mock()
        context.request_id = f'test-denied-{user_id}'
        
        # Execute
        result = lambda_handler(event, context)
        
        # Verify: Access denied
        self.assertEqual(result['policyDocument']['Statement'][0]['Effect'], 'Deny')
        
        # Verify: Context is not included (or is empty) for denied requests
        # Note: Some implementations may include empty context, others may omit it
        if 'context' in result:
            # If context exists, it should be empty or minimal
            self.assertEqual(len(result.get('context', {})), 0,
                           f"Context should be empty for denied request")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
