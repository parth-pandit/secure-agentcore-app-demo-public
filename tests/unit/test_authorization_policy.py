"""
Unit tests for authorization policy manager.

Tests policy loading from environment variables, user permission checking,
and configuration validation.
"""

import unittest
import json
import os
from unittest.mock import patch
import sys
sys.path.insert(0, 'backend/src/lambdas')

from authorization_policy import (
    load_policy_config,
    validate_config,
    get_user_permissions,
    is_user_authorized,
    resource_matches_pattern,
    extract_method_from_arn,
    extract_resource_from_arn,
    check_authorization,
    ConfigurationError,
    UserNotAuthorizedError
)


class TestAuthorizationPolicyLoading(unittest.TestCase):
    """Test policy loading from environment variables."""
    
    def test_load_valid_config_from_env(self):
        """Test loading valid configuration from environment variable."""
        config = {
            "user1@example.com": {
                "permissions": ["GET", "POST"],
                "resources": ["*"]
            }
        }
        
        with patch.dict(os.environ, {'AUTHORIZED_USERS': json.dumps(config)}):
            loaded_config = load_policy_config()
            self.assertIn('authorized_users', loaded_config)
            self.assertIn('user1@example.com', loaded_config['authorized_users'])
    
    def test_load_empty_config(self):
        """Test loading empty configuration."""
        with patch.dict(os.environ, {'AUTHORIZED_USERS': '{}'}):
            loaded_config = load_policy_config()
            self.assertEqual(loaded_config['authorized_users'], {})
    
    def test_load_config_with_multiple_users(self):
        """Test loading configuration with multiple users."""
        config = {
            "admin@example.com": {
                "permissions": ["GET", "POST", "PUT", "DELETE"],
                "resources": ["*"]
            },
            "viewer@example.com": {
                "permissions": ["GET"],
                "resources": ["*"]
            }
        }
        
        with patch.dict(os.environ, {'AUTHORIZED_USERS': json.dumps(config)}):
            loaded_config = load_policy_config()
            self.assertEqual(len(loaded_config['authorized_users']), 2)
            self.assertIn('admin@example.com', loaded_config['authorized_users'])
            self.assertIn('viewer@example.com', loaded_config['authorized_users'])
    
    def test_missing_env_variable(self):
        """Test behavior when environment variable is missing."""
        with patch.dict(os.environ, {}, clear=True):
            loaded_config = load_policy_config()
            # Should return empty config when no env var is provided
            self.assertEqual(loaded_config['authorized_users'], {})
    
    def test_invalid_json_in_env(self):
        """Test handling of invalid JSON in environment variable."""
        with patch.dict(os.environ, {'AUTHORIZED_USERS': 'invalid json'}):
            with self.assertRaises(ConfigurationError):
                load_policy_config()


class TestUserPermissionChecking(unittest.TestCase):
    """Test user permission checking for various scenarios."""
    
    def setUp(self):
        """Set up test configuration."""
        self.config = {
            "authorized_users": {
                "admin@example.com": {
                    "permissions": ["GET", "POST", "PUT", "DELETE"],
                    "resources": ["*"]
                },
                "editor@example.com": {
                    "permissions": ["GET", "POST", "PUT"],
                    "resources": ["/orders", "/orders/*"]
                },
                "viewer@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                },
                "limited@example.com": {
                    "permissions": ["GET"],
                    "resources": ["/orders/123"]
                }
            }
        }
    
    def test_admin_has_all_permissions(self):
        """Test that admin user has all permissions."""
        self.assertTrue(is_user_authorized("admin@example.com", "GET", "/orders", self.config))
        self.assertTrue(is_user_authorized("admin@example.com", "POST", "/orders", self.config))
        self.assertTrue(is_user_authorized("admin@example.com", "PUT", "/orders/123", self.config))
        self.assertTrue(is_user_authorized("admin@example.com", "DELETE", "/orders/456", self.config))
    
    def test_editor_has_limited_permissions(self):
        """Test that editor user has limited permissions."""
        self.assertTrue(is_user_authorized("editor@example.com", "GET", "/orders", self.config))
        self.assertTrue(is_user_authorized("editor@example.com", "POST", "/orders", self.config))
        self.assertTrue(is_user_authorized("editor@example.com", "PUT", "/orders/123", self.config))
        self.assertFalse(is_user_authorized("editor@example.com", "DELETE", "/orders", self.config))
    
    def test_viewer_can_only_read(self):
        """Test that viewer user can only read."""
        self.assertTrue(is_user_authorized("viewer@example.com", "GET", "/orders", self.config))
        self.assertFalse(is_user_authorized("viewer@example.com", "POST", "/orders", self.config))
        self.assertFalse(is_user_authorized("viewer@example.com", "PUT", "/orders", self.config))
        self.assertFalse(is_user_authorized("viewer@example.com", "DELETE", "/orders", self.config))
    
    def test_limited_user_specific_resource(self):
        """Test user with access to specific resource only."""
        self.assertTrue(is_user_authorized("limited@example.com", "GET", "/orders/123", self.config))
        self.assertFalse(is_user_authorized("limited@example.com", "GET", "/orders/456", self.config))
        self.assertFalse(is_user_authorized("limited@example.com", "GET", "/orders", self.config))
    
    def test_unknown_user_denied(self):
        """Test that unknown user is denied access."""
        self.assertFalse(is_user_authorized("unknown@example.com", "GET", "/orders", self.config))
    
    def test_case_sensitive_email(self):
        """Test that email comparison is case-sensitive."""
        # Exact match should work
        self.assertTrue(is_user_authorized("admin@example.com", "GET", "/orders", self.config))
        
        # Different case should not work (unless we implement case-insensitive matching)
        # This test documents current behavior
        self.assertFalse(is_user_authorized("Admin@example.com", "GET", "/orders", self.config))
    
    def test_wildcard_resource_matching(self):
        """Test wildcard resource matching."""
        # Admin has wildcard access
        self.assertTrue(is_user_authorized("admin@example.com", "GET", "/orders", self.config))
        self.assertTrue(is_user_authorized("admin@example.com", "GET", "/orders/123", self.config))
        self.assertTrue(is_user_authorized("admin@example.com", "GET", "/anything", self.config))


class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation."""
    
    def test_valid_config(self):
        """Test validation of valid configuration."""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST"],
                    "resources": ["*"]
                }
            }
        }
        
        # Should not raise any exception
        self.assertTrue(validate_config(config))
    
    def test_config_missing_users_key(self):
        """Test validation when 'authorized_users' key is missing."""
        config = {}
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_config_users_not_dict(self):
        """Test validation when 'authorized_users' is not a dictionary."""
        config = {"authorized_users": []}
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_user_config_missing_permissions(self):
        """Test validation when user config is missing 'permissions'."""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "resources": ["*"]
                }
            }
        }
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_user_config_permissions_not_list(self):
        """Test validation when 'permissions' is not a list."""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": "GET",
                    "resources": ["*"]
                }
            }
        }
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_user_config_invalid_permission(self):
        """Test validation when permission is not a valid HTTP method."""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "INVALID"],
                    "resources": ["*"]
                }
            }
        }
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)


class TestResourceMatching(unittest.TestCase):
    """Test resource matching logic."""
    
    def test_exact_resource_match(self):
        """Test exact resource matching."""
        self.assertTrue(resource_matches_pattern("/orders/123", "/orders/123"))
        self.assertFalse(resource_matches_pattern("/orders/456", "/orders/123"))
    
    def test_wildcard_matches_all(self):
        """Test that wildcard matches all resources."""
        self.assertTrue(resource_matches_pattern("/orders", "*"))
        self.assertTrue(resource_matches_pattern("/orders/123", "*"))
        self.assertTrue(resource_matches_pattern("/anything", "*"))
    
    def test_prefix_wildcard_matching(self):
        """Test prefix wildcard matching (e.g., /orders/*)."""
        self.assertTrue(resource_matches_pattern("/orders/123", "/orders/*"))
        self.assertTrue(resource_matches_pattern("/orders/456", "/orders/*"))
        # Note: /orders matches /orders/* because it starts with /orders prefix
        self.assertTrue(resource_matches_pattern("/orders", "/orders/*"))
        self.assertFalse(resource_matches_pattern("/products/123", "/orders/*"))
    
    def test_multiple_resource_patterns(self):
        """Test user with multiple resource patterns."""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["/orders", "/orders/*", "/products"]
                }
            }
        }
        
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders", config))
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders/123", config))
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/products", config))
        self.assertFalse(is_user_authorized("user@example.com", "GET", "/products/456", config))


class TestARNExtraction(unittest.TestCase):
    """Test ARN parsing functions."""
    
    def test_extract_method_from_arn(self):
        """Test extracting HTTP method from API Gateway ARN."""
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders"
        method = extract_method_from_arn(arn)
        self.assertEqual(method, "GET")
    
    def test_extract_method_from_arn_post(self):
        """Test extracting POST method from ARN."""
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/POST/orders"
        method = extract_method_from_arn(arn)
        self.assertEqual(method, "POST")
    
    def test_extract_resource_from_arn(self):
        """Test extracting resource path from API Gateway ARN."""
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders"
        resource = extract_resource_from_arn(arn)
        self.assertEqual(resource, "/orders")
    
    def test_extract_resource_from_arn_with_id(self):
        """Test extracting resource path with ID from ARN."""
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders/123"
        resource = extract_resource_from_arn(arn)
        self.assertEqual(resource, "/orders/123")
    
    def test_extract_method_invalid_arn(self):
        """Test extracting method from invalid ARN."""
        arn = "invalid-arn"
        method = extract_method_from_arn(arn)
        self.assertEqual(method, "UNKNOWN")
    
    def test_extract_resource_invalid_arn(self):
        """Test extracting resource from invalid ARN."""
        arn = "invalid-arn"
        resource = extract_resource_from_arn(arn)
        self.assertEqual(resource, "/")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""
    
    def setUp(self):
        """Set up test configuration."""
        self.config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
    
    def test_empty_email(self):
        """Test authorization check with empty email."""
        self.assertFalse(is_user_authorized("", "GET", "/orders", self.config))
    
    def test_none_email(self):
        """Test authorization check with None email."""
        self.assertFalse(is_user_authorized(None, "GET", "/orders", self.config))
    
    def test_empty_method(self):
        """Test authorization check with empty method."""
        self.assertFalse(is_user_authorized("user@example.com", "", "/orders", self.config))
    
    def test_empty_resource(self):
        """Test authorization check with empty resource."""
        # Empty resource should still be checked against patterns
        self.assertTrue(is_user_authorized("user@example.com", "GET", "", self.config))
    
    def test_case_sensitive_method(self):
        """Test that HTTP method comparison is case-sensitive."""
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders", self.config))
        # Lowercase method should not match
        self.assertFalse(is_user_authorized("user@example.com", "get", "/orders", self.config))
    
    def test_get_user_permissions_unknown_user(self):
        """Test getting permissions for unknown user raises exception."""
        with self.assertRaises(UserNotAuthorizedError):
            get_user_permissions("unknown@example.com", self.config)
    
    def test_get_user_permissions_valid_user(self):
        """Test getting permissions for valid user."""
        perms = get_user_permissions("user@example.com", self.config)
        self.assertIn("permissions", perms)
        self.assertIn("resources", perms)
        self.assertEqual(perms["permissions"], ["GET"])


class TestCheckAuthorization(unittest.TestCase):
    """Test the main check_authorization function."""
    
    def test_check_authorization_with_valid_user(self):
        """Test authorization check with valid user and ARN."""
        config = {
            "user@example.com": {
                "permissions": ["GET", "POST", "PUT"],
                "resources": ["*"]
            }
        }
        
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders"
        
        with patch.dict(os.environ, {'AUTHORIZED_USERS': json.dumps(config)}):
            result = check_authorization("user@example.com", arn)
            self.assertTrue(result)
    
    def test_check_authorization_with_unauthorized_user(self):
        """Test authorization check with unauthorized user."""
        config = {
            "user@example.com": {
                "permissions": ["GET"],
                "resources": ["*"]
            }
        }
        
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/GET/orders"
        
        with patch.dict(os.environ, {'AUTHORIZED_USERS': json.dumps(config)}):
            result = check_authorization("other@example.com", arn)
            self.assertFalse(result)
    
    def test_check_authorization_with_insufficient_permissions(self):
        """Test authorization check when user lacks required permission."""
        config = {
            "user@example.com": {
                "permissions": ["GET"],
                "resources": ["*"]
            }
        }
        
        arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/dev/POST/orders"
        
        with patch.dict(os.environ, {'AUTHORIZED_USERS': json.dumps(config)}):
            result = check_authorization("user@example.com", arn)
            self.assertFalse(result)
    
    def test_check_authorization_with_invalid_config(self):
        """Test authorization check with invalid configuration."""
        with patch.dict(os.environ, {'AUTHORIZED_USERS': 'invalid json'}):
            result = check_authorization("user@example.com", "some-arn")
            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
