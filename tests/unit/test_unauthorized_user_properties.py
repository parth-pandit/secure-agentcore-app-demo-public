"""
Property-based tests for unauthorized user denial.

Feature: api-authentication-authorization
Property 4: Unauthorized User Denied
Validates: Requirements 2.2, 2.3

These tests verify that valid tokens for users not in the authorized list
are denied access with a 403 Forbidden response.
"""

import unittest
import sys
import os
import json
from unittest.mock import patch

# Add backend/src/lambdas to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

from authorization_policy import (
    is_user_authorized,
    check_authorization,
    get_user_permissions,
    UserNotAuthorizedError
)

try:
    from hypothesis import given, strategies as st, settings
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Warning: hypothesis not available, property tests will be skipped")
    def given(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def settings(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    class st:
        @staticmethod
        def text(*args, **kwargs):
            return None
        @staticmethod
        def sampled_from(*args, **kwargs):
            return None
        @staticmethod
        def emails(*args, **kwargs):
            return None


class TestUnauthorizedUserDenial(unittest.TestCase):
    """
    Property 4: Unauthorized User Denied
    
    For any valid JWT token for a user not in the authorized users list,
    the Lambda Authorizer should return a Deny policy and return a
    403 Forbidden response.
    
    Validates: Requirements 2.2, 2.3
    """
    
    def setUp(self):
        """Set up test configuration"""
        self.test_config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            }
        }
    
    def test_unauthorized_user_denied_get(self):
        """Test unauthorized user is denied GET access"""
        result = is_user_authorized(
            "unauthorized@example.com",
            "GET",
            "/orders",
            self.test_config
        )
        self.assertFalse(result)
    
    def test_unauthorized_user_denied_post(self):
        """Test unauthorized user is denied POST access"""
        result = is_user_authorized(
            "unauthorized@example.com",
            "POST",
            "/orders",
            self.test_config
        )
        self.assertFalse(result)
    
    def test_unauthorized_user_denied_put(self):
        """Test unauthorized user is denied PUT access"""
        result = is_user_authorized(
            "unauthorized@example.com",
            "PUT",
            "/orders",
            self.test_config
        )
        self.assertFalse(result)
    
    def test_unauthorized_user_all_methods_denied(self):
        """Test unauthorized user is denied all methods"""
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        
        for method in methods:
            with self.subTest(method=method):
                result = is_user_authorized(
                    "unauthorized@example.com",
                    method,
                    "/orders",
                    self.test_config
                )
                self.assertFalse(result, f"Unauthorized user should not have {method} access")
    
    def test_unauthorized_user_all_resources_denied(self):
        """Test unauthorized user is denied access to all resources"""
        resources = ["/orders", "/orders/123", "/api/v1/orders", "/admin"]
        
        for resource in resources:
            with self.subTest(resource=resource):
                result = is_user_authorized(
                    "unauthorized@example.com",
                    "GET",
                    resource,
                    self.test_config
                )
                self.assertFalse(result, f"Unauthorized user should not have access to {resource}")
    
    def test_get_user_permissions_raises_error(self):
        """Test getting permissions for unauthorized user raises error"""
        with self.assertRaises(UserNotAuthorizedError):
            get_user_permissions("unauthorized@example.com", self.test_config)
    
    def test_check_authorization_unauthorized_user_with_arn(self):
        """Test authorization check denies unauthorized user with ARN"""
        with patch.dict(os.environ, {
            'AUTHORIZED_USERS': json.dumps({
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            })
        }):
            arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders"
            result = check_authorization("unauthorized@example.com", arn)
            self.assertFalse(result)
    
    def test_check_authorization_all_methods_denied_with_arn(self):
        """Test all methods are denied for unauthorized user using ARNs"""
        with patch.dict(os.environ, {
            'AUTHORIZED_USERS': json.dumps({
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            })
        }):
            methods = ["GET", "POST", "PUT", "DELETE"]
            
            for method in methods:
                with self.subTest(method=method):
                    arn = f"arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/{method}/orders"
                    result = check_authorization("unauthorized@example.com", arn)
                    self.assertFalse(result, f"Unauthorized user should be denied {method}")
    
    def test_empty_email_denied(self):
        """Test empty email is denied"""
        result = is_user_authorized(
            "",
            "GET",
            "/orders",
            self.test_config
        )
        self.assertFalse(result)
    
    def test_malformed_email_denied(self):
        """Test malformed email is denied"""
        malformed_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user@@example.com",
            "user@example",
        ]
        
        for email in malformed_emails:
            with self.subTest(email=email):
                result = is_user_authorized(
                    email,
                    "GET",
                    "/orders",
                    self.test_config
                )
                self.assertFalse(result, f"Malformed email {email} should be denied")
    
    def test_case_sensitive_email_denied(self):
        """Test email matching is case-sensitive"""
        # user@example.com is authorized, but PARTHPG@amazon.com is not
        result = is_user_authorized(
            "PARTHPG@amazon.com",
            "GET",
            "/orders",
            self.test_config
        )
        self.assertFalse(result)


@unittest.skipIf(not HYPOTHESIS_AVAILABLE, "hypothesis not available")
class TestUnauthorizedUserProperties(unittest.TestCase):
    """Property-based tests for unauthorized user denial"""
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_property_random_users_denied(self, random_email):
        """
        Property: For any email that is not user@example.com,
        the user should be denied access.
        """
        # Skip if random email happens to match authorized user
        if random_email == "user@example.com":
            return
        
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            }
        }
        
        result = is_user_authorized(random_email, "GET", "/orders", config)
        self.assertFalse(result, f"Random user {random_email} should be denied")
    
    @given(
        st.text(min_size=1, max_size=100),
        st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH"])
    )
    @settings(max_examples=100)
    def test_property_unauthorized_users_all_methods_denied(self, random_email, method):
        """
        Property: For any unauthorized user and any HTTP method,
        access should be denied.
        """
        # Skip if random email happens to match authorized user
        if random_email == "user@example.com":
            return
        
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            }
        }
        
        result = is_user_authorized(random_email, method, "/orders", config)
        self.assertFalse(result, f"User {random_email} should be denied {method}")
    
    @given(
        st.text(min_size=1, max_size=100),
        st.text(min_size=1, max_size=100)
    )
    @settings(max_examples=100)
    def test_property_unauthorized_users_all_resources_denied(self, random_email, random_resource):
        """
        Property: For any unauthorized user and any resource,
        access should be denied.
        """
        # Skip if random email happens to match authorized user
        if random_email == "user@example.com":
            return
        
        # Ensure resource starts with /
        if not random_resource.startswith('/'):
            random_resource = '/' + random_resource
        
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        result = is_user_authorized(random_email, "GET", random_resource, config)
        self.assertFalse(result, f"User {random_email} should be denied access to {random_resource}")


if __name__ == '__main__':
    unittest.main()
