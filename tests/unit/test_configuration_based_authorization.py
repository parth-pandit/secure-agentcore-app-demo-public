"""
Property-based tests for configuration-based authorization.

Feature: api-authentication-authorization
Property 10: Configuration-Based Authorization
Validates: Requirements 2.5, 10.2, 10.3

These tests verify that authorization rules can be changed through
configuration without requiring code changes.
"""

import unittest
import sys
import os
import json
from unittest.mock import patch

# Add backend/src/lambdas to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

from authorization_policy import (
    load_policy_config,
    validate_config,
    is_user_authorized,
    check_authorization,
    ConfigurationError
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
        def lists(*args, **kwargs):
            return None
        @staticmethod
        def sampled_from(*args, **kwargs):
            return None


class TestConfigurationBasedAuthorization(unittest.TestCase):
    """
    Property 10: Configuration-Based Authorization
    
    For any change to the authorized users list in the Lambda Authorizer
    configuration, the system should enforce the new authorization rules
    without requiring code changes.
    
    Validates: Requirements 2.5, 10.2, 10.3
    """
    
    def test_add_new_user_to_config(self):
        """Test adding a new user to configuration grants them access"""
        # Initial config with one user
        config1 = {
            "authorized_users": {
                "user1@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        # user2 should not have access
        result1 = is_user_authorized("user2@example.com", "GET", "/orders", config1)
        self.assertFalse(result1)
        
        # Updated config with two users
        config2 = {
            "authorized_users": {
                "user1@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                },
                "user2@example.com": {
                    "permissions": ["GET", "POST"],
                    "resources": ["*"]
                }
            }
        }
        
        # user2 should now have access
        result2 = is_user_authorized("user2@example.com", "GET", "/orders", config2)
        self.assertTrue(result2)
    
    def test_remove_user_from_config(self):
        """Test removing a user from configuration denies them access"""
        # Initial config with two users
        config1 = {
            "authorized_users": {
                "user1@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                },
                "user2@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        # user2 should have access
        result1 = is_user_authorized("user2@example.com", "GET", "/orders", config1)
        self.assertTrue(result1)
        
        # Updated config with user2 removed
        config2 = {
            "authorized_users": {
                "user1@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        # user2 should no longer have access
        result2 = is_user_authorized("user2@example.com", "GET", "/orders", config2)
        self.assertFalse(result2)
    
    def test_change_user_permissions(self):
        """Test changing user permissions in configuration"""
        # Initial config with GET only
        config1 = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        # User should have GET but not POST
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders", config1))
        self.assertFalse(is_user_authorized("user@example.com", "POST", "/orders", config1))
        
        # Updated config with GET and POST
        config2 = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST"],
                    "resources": ["*"]
                }
            }
        }
        
        # User should now have both GET and POST
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders", config2))
        self.assertTrue(is_user_authorized("user@example.com", "POST", "/orders", config2))
    
    def test_change_user_resources(self):
        """Test changing user resource access in configuration"""
        # Initial config with wildcard resources
        config1 = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                }
            }
        }
        
        # User should have access to all resources
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders", config1))
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/admin", config1))
        
        # Updated config with specific resources only
        config2 = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET"],
                    "resources": ["/orders"]
                }
            }
        }
        
        # User should only have access to /orders
        self.assertTrue(is_user_authorized("user@example.com", "GET", "/orders", config2))
        self.assertFalse(is_user_authorized("user@example.com", "GET", "/admin", config2))
    
    def test_load_config_from_environment(self):
        """Test loading configuration from environment variable"""
        config_json = json.dumps({
            "user@example.com": {
                "permissions": ["GET"],
                "resources": ["*"]
            }
        })
        
        with patch.dict(os.environ, {'AUTHORIZED_USERS': config_json}):
            config = load_policy_config()
            self.assertIn('authorized_users', config)
            self.assertIn('user@example.com', config['authorized_users'])
    
    def test_validate_config_valid(self):
        """Test validation passes for valid configuration"""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["GET", "POST"],
                    "resources": ["*"]
                }
            }
        }
        
        result = validate_config(config)
        self.assertTrue(result)
    
    def test_validate_config_missing_permissions(self):
        """Test validation fails when permissions are missing"""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "resources": ["*"]
                }
            }
        }
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_validate_config_invalid_permission(self):
        """Test validation fails for invalid HTTP method"""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": ["INVALID_METHOD"],
                    "resources": ["*"]
                }
            }
        }
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_validate_config_permissions_not_list(self):
        """Test validation fails when permissions is not a list"""
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": "GET",  # Should be a list
                    "resources": ["*"]
                }
            }
        }
        
        with self.assertRaises(ConfigurationError):
            validate_config(config)
    
    def test_multiple_users_different_permissions(self):
        """Test multiple users with different permissions"""
        config = {
            "authorized_users": {
                "admin@example.com": {
                    "permissions": ["GET", "POST", "PUT", "DELETE"],
                    "resources": ["*"]
                },
                "readonly@example.com": {
                    "permissions": ["GET"],
                    "resources": ["*"]
                },
                "editor@example.com": {
                    "permissions": ["GET", "PUT"],
                    "resources": ["/orders"]
                }
            }
        }
        
        # Admin should have all permissions
        self.assertTrue(is_user_authorized("admin@example.com", "DELETE", "/orders", config))
        
        # Readonly should only have GET
        self.assertTrue(is_user_authorized("readonly@example.com", "GET", "/orders", config))
        self.assertFalse(is_user_authorized("readonly@example.com", "POST", "/orders", config))
        
        # Editor should have GET and PUT on /orders only
        self.assertTrue(is_user_authorized("editor@example.com", "GET", "/orders", config))
        self.assertTrue(is_user_authorized("editor@example.com", "PUT", "/orders", config))
        self.assertFalse(is_user_authorized("editor@example.com", "DELETE", "/orders", config))


@unittest.skipIf(not HYPOTHESIS_AVAILABLE, "hypothesis not available")
class TestConfigurationBasedAuthorizationProperties(unittest.TestCase):
    """Property-based tests for configuration-based authorization"""
    
    @given(st.lists(st.sampled_from(["GET", "POST", "PUT", "DELETE"]), min_size=1, max_size=4, unique=True))
    @settings(max_examples=100)
    def test_property_any_permission_set_enforced(self, permissions):
        """
        Property: For any set of permissions in configuration,
        only those permissions should be granted.
        """
        config = {
            "authorized_users": {
                "user@example.com": {
                    "permissions": permissions,
                    "resources": ["*"]
                }
            }
        }
        
        all_methods = ["GET", "POST", "PUT", "DELETE"]
        
        for method in all_methods:
            result = is_user_authorized("user@example.com", method, "/orders", config)
            if method in permissions:
                self.assertTrue(result, f"User should have {method} permission")
            else:
                self.assertFalse(result, f"User should not have {method} permission")


if __name__ == '__main__':
    unittest.main()
