"""
Authorization Policy Manager for Orders API.

This module manages user permissions and authorization policies,
determining which users can access which API endpoints.
"""

import json
import os
import logging
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger()


class AuthorizationError(Exception):
    """Base exception for authorization errors"""
    pass


class ConfigurationError(AuthorizationError):
    """Exception raised when configuration is invalid"""
    pass


class UserNotAuthorizedError(AuthorizationError):
    """Exception raised when user is not authorized"""
    pass


def load_policy_config() -> Dict[str, Any]:
    """
    Load authorization policy configuration from environment variables.
    
    Expected environment variable format:
    AUTHORIZED_USERS = {
        "user@example.com": {
            "permissions": ["GET", "POST", "PUT"],
            "resources": ["*"]
        }
    }
    
    Returns:
        Dictionary containing authorization policies
        
    Raises:
        ConfigurationError: If configuration is invalid or missing
    """
    try:
        # Get configuration from environment variable
        config_str = os.environ.get('AUTHORIZED_USERS', '{}')
        
        if not config_str or config_str == '{}':
            logger.warning("No authorized users configured")
            return {"authorized_users": {}}
        
        # Parse JSON configuration
        config = json.loads(config_str)
        
        # Validate configuration structure
        if not isinstance(config, dict):
            raise ConfigurationError("Configuration must be a dictionary")
        
        # Wrap in authorized_users key if not present
        if 'authorized_users' not in config:
            config = {"authorized_users": config}
        
        logger.info(f"Loaded authorization config for {len(config['authorized_users'])} users")
        return config
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in AUTHORIZED_USERS: {e}")
        raise ConfigurationError(f"Invalid JSON in authorization configuration: {e}")
    except Exception as e:
        logger.error(f"Error loading authorization config: {e}")
        raise ConfigurationError(f"Failed to load authorization configuration: {e}")


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate authorization configuration structure.
    
    Args:
        config: Authorization configuration dictionary
        
    Returns:
        True if configuration is valid
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    if 'authorized_users' not in config:
        raise ConfigurationError("Configuration missing 'authorized_users' key")
    
    authorized_users = config['authorized_users']
    
    if not isinstance(authorized_users, dict):
        raise ConfigurationError("'authorized_users' must be a dictionary")
    
    # Validate each user configuration
    for email, user_config in authorized_users.items():
        if not isinstance(user_config, dict):
            raise ConfigurationError(f"User config for {email} must be a dictionary")
        
        if 'permissions' not in user_config:
            raise ConfigurationError(f"User {email} missing 'permissions' field")
        
        if not isinstance(user_config['permissions'], list):
            raise ConfigurationError(f"Permissions for {email} must be a list")
        
        # Validate permissions are valid HTTP methods
        valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        for permission in user_config['permissions']:
            if permission not in valid_methods:
                raise ConfigurationError(
                    f"Invalid permission '{permission}' for {email}. "
                    f"Must be one of: {valid_methods}"
                )
    
    logger.debug("Authorization configuration validated successfully")
    return True


def get_user_permissions(email: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get permissions for a specific user.
    
    Email matching is case-insensitive as per RFC 5321.
    
    Args:
        email: User email address
        config: Authorization configuration
        
    Returns:
        User permissions dictionary with 'permissions' and 'resources' keys
        
    Raises:
        UserNotAuthorizedError: If user is not in authorized users list
    """
    authorized_users = config.get('authorized_users', {})
    
    # Normalize email to lowercase for case-insensitive comparison
    email_lower = email.lower()
    
    # Create a case-insensitive lookup dictionary
    users_lower = {k.lower(): v for k, v in authorized_users.items()}
    
    if email_lower not in users_lower:
        logger.warning(f"User {email} not found in authorized users")
        raise UserNotAuthorizedError(f"User {email} is not authorized")
    
    user_permissions = users_lower[email_lower]
    
    logger.debug(f"Retrieved permissions for {email}: {user_permissions}")
    return user_permissions


def is_user_authorized(email: str, method: str, resource: str, 
                       config: Dict[str, Any]) -> bool:
    """
    Check if a user is authorized to access a specific resource with a method.
    
    Args:
        email: User email address
        method: HTTP method (GET, POST, PUT, etc.)
        resource: Resource path or ARN
        config: Authorization configuration
        
    Returns:
        True if user is authorized, False otherwise
    """
    try:
        # Get user permissions
        user_perms = get_user_permissions(email, config)
        
        # Check if method is in user's permissions
        if method not in user_perms.get('permissions', []):
            logger.info(f"User {email} does not have {method} permission")
            return False
        
        # Check resource access
        allowed_resources = user_perms.get('resources', [])
        
        # If user has wildcard access, allow all resources
        if '*' in allowed_resources:
            logger.debug(f"User {email} has wildcard resource access")
            return True
        
        # Check if specific resource is allowed
        if resource in allowed_resources:
            logger.debug(f"User {email} has access to resource {resource}")
            return True
        
        # Check if resource matches any pattern
        for allowed_resource in allowed_resources:
            if resource_matches_pattern(resource, allowed_resource):
                logger.debug(f"User {email} resource {resource} matches pattern {allowed_resource}")
                return True
        
        logger.info(f"User {email} does not have access to resource {resource}")
        return False
        
    except UserNotAuthorizedError:
        return False
    except Exception as e:
        logger.error(f"Error checking authorization for {email}: {e}")
        return False


def resource_matches_pattern(resource: str, pattern: str) -> bool:
    """
    Check if a resource matches a pattern.
    
    Supports simple wildcard patterns:
    - "*" matches everything
    - "/orders/*" matches any path under /orders
    - "*/GET/*" matches any GET method
    
    Args:
        resource: Resource string (e.g., ARN or path)
        pattern: Pattern string with optional wildcards
        
    Returns:
        True if resource matches pattern
    """
    # Exact match
    if resource == pattern:
        return True
    
    # Wildcard match
    if pattern == '*':
        return True
    
    # Simple prefix match for paths
    if pattern.endswith('/*'):
        prefix = pattern[:-2]
        if resource.startswith(prefix):
            return True
    
    # Pattern matching for ARNs
    if '/*/' in pattern:
        # Split pattern and resource by '/'
        pattern_parts = pattern.split('/')
        resource_parts = resource.split('/')
        
        if len(pattern_parts) != len(resource_parts):
            return False
        
        # Check each part
        for p_part, r_part in zip(pattern_parts, resource_parts):
            if p_part != '*' and p_part != r_part:
                return False
        
        return True
    
    return False


def extract_method_from_arn(method_arn: str) -> str:
    """
    Extract HTTP method from API Gateway method ARN.
    
    ARN format: arn:aws:execute-api:region:account:api-id/stage/method/resource
    
    Args:
        method_arn: API Gateway method ARN
        
    Returns:
        HTTP method (GET, POST, PUT, etc.)
    """
    try:
        # Split ARN to get the path part
        # Format: arn:aws:execute-api:region:account:api-id/stage/method/resource
        arn_parts = method_arn.split(':')
        if len(arn_parts) < 6:
            logger.warning(f"Invalid ARN format: {method_arn}")
            return "UNKNOWN"
        
        # Get the path part (api-id/stage/method/resource)
        path_part = arn_parts[5]
        path_parts = path_part.split('/')
        
        if len(path_parts) < 3:
            logger.warning(f"Invalid ARN path format: {path_part}")
            return "UNKNOWN"
        
        # Method is the third part (index 2)
        method = path_parts[2]
        
        logger.debug(f"Extracted method {method} from ARN")
        return method
        
    except Exception as e:
        logger.error(f"Error extracting method from ARN {method_arn}: {e}")
        return "UNKNOWN"


def extract_resource_from_arn(method_arn: str) -> str:
    """
    Extract resource path from API Gateway method ARN.
    
    ARN format: arn:aws:execute-api:region:account:api-id/stage/method/resource
    
    Args:
        method_arn: API Gateway method ARN
        
    Returns:
        Resource path (e.g., /orders)
    """
    try:
        # Split ARN to get the path part
        arn_parts = method_arn.split(':')
        if len(arn_parts) < 6:
            logger.warning(f"Invalid ARN format: {method_arn}")
            return "/"
        
        # Get the path part (api-id/stage/method/resource)
        path_part = arn_parts[5]
        path_parts = path_part.split('/')
        
        if len(path_parts) < 4:
            # No resource path specified
            return "/"
        
        # Resource is everything after method (index 3+)
        resource = '/' + '/'.join(path_parts[3:])
        
        logger.debug(f"Extracted resource {resource} from ARN")
        return resource
        
    except Exception as e:
        logger.error(f"Error extracting resource from ARN {method_arn}: {e}")
        return "/"


def check_authorization(user_email: str, method_arn: str) -> bool:
    """
    Check if a user is authorized to access a specific API Gateway method.
    
    This is the main authorization check function that combines all checks.
    
    Args:
        user_email: User email address from token
        method_arn: API Gateway method ARN
        
    Returns:
        True if user is authorized, False otherwise
    """
    try:
        # Load configuration
        config = load_policy_config()
        
        # Validate configuration
        validate_config(config)
        
        # Extract method and resource from ARN
        method = extract_method_from_arn(method_arn)
        resource = extract_resource_from_arn(method_arn)
        
        # Check authorization
        authorized = is_user_authorized(user_email, method, resource, config)
        
        if authorized:
            logger.info(f"Authorization granted for {user_email} to {method} {resource}")
        else:
            logger.warning(f"Authorization denied for {user_email} to {method} {resource}")
        
        return authorized
        
    except ConfigurationError as e:
        logger.error(f"Configuration error during authorization: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during authorization: {e}")
        return False
