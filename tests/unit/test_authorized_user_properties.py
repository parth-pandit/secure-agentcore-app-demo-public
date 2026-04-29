"""
Property-based tests for authorized user access.

Feature: api-authentication-authorization
Property 2: Valid Token Grants Access
Validates: Requirements 2.1, 5.5

These tests verify that valid tokens for authorized users grant access
to all permitted endpoints.
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
    extract_method_from_arn,
    extract_resource_from_arn
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
        def sampled_from(*args, **kwargs):
            return None
        @staticmethod
        def text(*args, **kwargs):
            return None


class TestAuthorizedUserAccess(unittest.TestCase):
    """
    Property 2: Valid Token Grants Access
    
    For any valid JWT token from IAM Identity Center for user "user@example.com",
    the Lambda Authorizer should return an Allow policy for all three endpoints
    (GET, POST, PUT).
    
    Validates: Requirements 2.1, 5.5
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
    
    def test_authorized_user_get_access(self):
        """Test authorized user can access GET endpoint"""
        result = is_user_authorized(
            "user@example.com",
            "GET",
            "/orders",
            self.test_config
        )
        self.assertTrue(result)
    
    def test_authorized_user_post_access(self):
        """Test authorized user can access POST endpoint"""
        result = is_user_authorized(
            "user@example.com",
            "POST",
            "/orders",
            self.test_config
        )
        self.assertTrue(result)
    
    def test_authorized_user_put_access(self):
        """Test authorized user can access PUT endpoint"""
        result = is_user_authorized(
            "user@example.com",
            "PUT",
            "/orders",
            self.test_config
        )
        self.assertTrue(result)
    
    def test_authorized_user_all_methods(self):
        """Test authorized user can access all permitted methods"""
        methods = ["GET", "POST", "PUT"]
        
        for method in methods:
            with self.subTest(method=method):
                result = is_user_authorized(
                    "user@example.com",
                    method,
                    "/orders",
                    self.test_config
                )
                self.assertTrue(result, f"User should have {method} access")
    
    def test_authorized_user_wildcard_resources(self):
        """Test authorized user with wildcard can access any resource"""
        resources = ["/orders", "/orders/123", "/orders/123/items", "/api/v1/orders"]
        
        for resource in resources:
            with self.subTest(resource=resource):
                result = is_user_authorized(
                    "user@example.com",
                    "GET",
                    resource,
                    self.test_config
                )
                self.assertTrue(result, f"User should have access to {resource}")
    
    def test_authorized_user_method_not_permitted(self):
        """Test authorized user cannot access non-permitted methods"""
        result = is_user_authorized(
            "user@example.com",
            "DELETE",
            "/orders",
            self.test_config
        )
        self.assertFalse(result)
    
    def test_check_authorization_with_arn(self):
        """Test authorization check with full API Gateway ARN"""
        with patch.dict(os.environ, {
            'AUTHORIZED_USERS': json.dumps({
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            })
        }):
            arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders"
            result = check_authorization("user@example.com", arn)
            self.assertTrue(result)
    
    def test_check_authorization_all_methods_with_arn(self):
        """Test authorization for all methods using ARNs"""
        with patch.dict(os.environ, {
            'AUTHORIZED_USERS': json.dumps({
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            })
        }):
            methods = ["GET", "POST", "PUT"]
            
            for method in methods:
                with self.subTest(method=method):
                    arn = f"arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/{method}/orders"
                    result = check_authorization("user@example.com", arn)
                    self.assertTrue(result, f"User should be authorized for {method}")


class TestARNParsing(unittest.TestCase):
    """Test ARN parsing for method and resource extraction"""
    
    def test_extract_method_from_arn(self):
        """Test extracting HTTP method from ARN"""
        test_cases = [
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders", "GET"),
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/POST/orders", "POST"),
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/PUT/orders", "PUT"),
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/prod/DELETE/orders", "DELETE"),
        ]
        
        for arn, expected_method in test_cases:
            with self.subTest(arn=arn):
                method = extract_method_from_arn(arn)
                self.assertEqual(method, expected_method)
    
    def test_extract_resource_from_arn(self):
        """Test extracting resource path from ARN"""
        test_cases = [
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders", "/orders"),
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/POST/orders", "/orders"),
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders/123", "/orders/123"),
            ("arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders/123/items", "/orders/123/items"),
        ]
        
        for arn, expected_resource in test_cases:
            with self.subTest(arn=arn):
                resource = extract_resource_from_arn(arn)
                self.assertEqual(resource, expected_resource)


@unittest.skipIf(not HYPOTHESIS_AVAILABLE, "hypothesis not available")
class TestAuthorizedUserProperties(unittest.TestCase):
    """Property-based tests for authorized user access"""
    
    @given(st.sampled_from(["GET", "POST", "PUT"]))
    @settings(max_examples=100)
    def test_property_authorized_user_all_permitted_methods(self, method):
        """Property: For any permitted HTTP method, authorized user should have access"""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["*"]
                }
            }
        }
        
        result = is_user_authorized("user@example.com", method, "/orders", config)
        self.assertTrue(result, f"User should have {method} access")
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_property_authorized_user_wildcard_resources(self, resource_path):
        """Property: For any resource path, user with wildcard should have access"""
        if not resource_path.startswith('/'):
            resource_path = '/' + resource_path
        
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        result = is_user_authorized("user@example.com", "GET", resource_path, config)
        self.assertTrue(result, f"User should have access to {resource_path}")


if __name__ == '__main__':
    unittest.main()
