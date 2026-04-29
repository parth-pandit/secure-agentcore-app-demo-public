"""
Lambda Authorizer for Orders API.

This function validates authentication tokens from Azure Entra ID and enforces
authorization policies for API Gateway endpoints. It returns IAM policies that
allow or deny access to specific API resources.
"""

import json
import os
import logging
from typing import Dict, Any, Optional

# Import validation and authorization modules
from token_validator import validate_token, TokenValidationError
from authorization_policy import check_authorization
from audit_logger import (
    log_authorization_attempt,
    log_authentication_success,
    log_authentication_failure,
    log_authorization_error
)

# Configure logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))


class AuthorizerError(Exception):
    """Base exception for authorizer errors"""
    pass


class TokenExtractionError(AuthorizerError):
    """Exception raised when token extraction fails"""
    pass


class AuthorizationError(AuthorizerError):
    """Exception raised when authorization fails"""
    pass


def extract_token(event: Dict[str, Any]) -> str:
    """
    Extract JWT token from the Authorization header.
    
    Args:
        event: Lambda authorizer event from API Gateway
        
    Returns:
        JWT token string without the 'Bearer ' prefix
        
    Raises:
        TokenExtractionError: If token is missing or malformed
    """
    try:
        # Get the authorization token from the event
        auth_token = event.get('authorizationToken', '')
        
        if not auth_token:
            logger.error("Missing authorization token in request")
            raise TokenExtractionError("Missing authorization token")
        
        # Check if token has Bearer prefix
        if not auth_token.startswith('Bearer '):
            logger.error("Authorization token missing 'Bearer ' prefix")
            raise TokenExtractionError("Authorization token missing 'Bearer ' prefix")
        
        # Extract token without 'Bearer ' prefix
        token = auth_token[7:].strip()
        
        if not token:
            logger.error("Empty token after removing Bearer prefix")
            raise TokenExtractionError("Empty authorization token")
        
        logger.debug(f"Successfully extracted token (length: {len(token)})")
        return token
        
    except KeyError as e:
        logger.error(f"Missing required field in event: {e}")
        raise TokenExtractionError(f"Invalid event structure: {e}")


def generate_policy(principal_id: str, effect: str, resource: str, 
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate an IAM policy document for API Gateway.
    
    Args:
        principal_id: User identifier (typically email)
        effect: 'Allow' or 'Deny'
        resource: ARN of the API Gateway resource
        context: Optional context to pass to backend Lambda functions
        
    Returns:
        IAM policy document in API Gateway format
        
    Raises:
        ValueError: If effect is not 'Allow' or 'Deny'
    """
    if effect not in ['Allow', 'Deny']:
        raise ValueError(f"Invalid effect: {effect}. Must be 'Allow' or 'Deny'")
    
    # Build the policy document
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    }
    
    # Add context if provided
    if context:
        # Ensure all context values are strings (API Gateway requirement)
        policy['context'] = {k: str(v) for k, v in context.items()}
    
    logger.info(f"Generated {effect} policy for principal: {principal_id}")
    return policy


def generate_user_policy(user_email: str, method_arn: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a comprehensive IAM policy for a user based on their permissions.
    
    This creates a policy that includes ALL methods the user is allowed to access,
    not just the current method. This is necessary because API Gateway caches
    authorizer responses based on the token alone, not token+method.
    
    Args:
        user_email: User email address
        method_arn: Current method ARN being accessed
        config: Authorization configuration
        
    Returns:
        IAM policy document with all allowed methods
    """
    from authorization_policy import get_user_permissions, extract_resource_from_arn
    
    # Parse the method ARN to get the base
    # Format: arn:aws:execute-api:region:account:api-id/stage/method/resource
    arn_parts = method_arn.split(':')
    if len(arn_parts) < 6:
        logger.error(f"Invalid method ARN: {method_arn}")
        return generate_deny_policy(user_email, method_arn)
    
    api_gateway_arn = ':'.join(arn_parts[:5])
    path_parts = arn_parts[5].split('/')
    api_id = path_parts[0] if len(path_parts) > 0 else '*'
    stage = path_parts[1] if len(path_parts) > 1 else '*'
    
    # Get user permissions
    try:
        user_perms = get_user_permissions(user_email, config)
        allowed_methods = user_perms.get('permissions', [])
        allowed_resources = user_perms.get('resources', [])
        
        # Build resource ARNs for all allowed methods
        statements = []
        
        for method in allowed_methods:
            for resource in allowed_resources:
                if resource == '*':
                    # Wildcard resource - allow all paths for this method
                    resource_arn = f"{api_gateway_arn}:{api_id}/{stage}/{method}/*"
                else:
                    # Specific resource
                    resource_arn = f"{api_gateway_arn}:{api_id}/{stage}/{method}{resource}"
                
                statements.append({
                    'Action': 'execute-api:Invoke',
                    'Effect': 'Allow',
                    'Resource': resource_arn
                })
        
        if not statements:
            logger.warning(f"No allowed methods found for {user_email}")
            return generate_deny_policy(user_email, method_arn)
        
        # Build the policy
        policy = {
            'principalId': user_email,
            'policyDocument': {
                'Version': '2012-10-17',
                'Statement': statements
            },
            'context': {
                'userEmail': user_email,
            }
        }
        
        logger.info(f"Generated policy for {user_email} with {len(statements)} statement(s)")
        logger.debug(f"Policy statements: {statements}")
        
        return policy
        
    except Exception as e:
        logger.error(f"Error generating user policy: {e}")
        return generate_deny_policy(user_email, method_arn)


def generate_allow_policy(principal_id: str, resource: str, 
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate an Allow IAM policy.
    
    Args:
        principal_id: User identifier
        resource: ARN of the API Gateway resource
        context: Optional context to pass to backend
        
    Returns:
        Allow IAM policy document
    """
    return generate_policy(principal_id, 'Allow', resource, context)


def generate_deny_policy(principal_id: str, resource: str) -> Dict[str, Any]:
    """
    Generate a Deny IAM policy.
    
    Args:
        principal_id: User identifier (or 'unauthorized' if unknown)
        resource: ARN of the API Gateway resource
        
    Returns:
        Deny IAM policy document
    """
    return generate_policy(principal_id, 'Deny', resource)


def get_method_specific_resource(method_arn: str) -> str:
    """
    Return the specific method ARN for fine-grained authorization.
    
    This ensures that authorization is checked per method and resource,
    preventing unauthorized access through policy caching.
    
    Args:
        method_arn: Specific method ARN from the event
        
    Returns:
        The same method ARN (for method-specific authorization)
    """
    # Handle empty or invalid ARN
    if not method_arn or ':' not in method_arn:
        logger.warning(f"Invalid method ARN: {method_arn}, using wildcard")
        return '*'
    
    logger.debug(f"Using method-specific resource: {method_arn}")
    return method_arn


def handle_error(error: Exception, method_arn: str) -> Dict[str, Any]:
    """
    Handle errors by logging and returning a Deny policy.
    
    This implements a fail-closed security model where any error
    results in access denial.
    
    Args:
        error: The exception that occurred
        method_arn: The API Gateway method ARN
        
    Returns:
        Deny IAM policy document
    """
    error_type = type(error).__name__
    error_message = str(error)
    
    logger.error(f"Authorization error ({error_type}): {error_message}")
    
    # Return deny policy with generic principal
    resource = get_method_specific_resource(method_arn)
    return generate_deny_policy('unauthorized', resource)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for API Gateway authorization.
    
    This function is invoked by API Gateway for each request that requires
    authorization. It validates the authentication token and returns an
    IAM policy that allows or denies access.
    
    Args:
        event: API Gateway authorizer event containing:
            - type: 'TOKEN'
            - authorizationToken: Bearer token from Authorization header
            - methodArn: ARN of the API Gateway method being invoked
        context: Lambda context object
        
    Returns:
        IAM policy document with Allow or Deny effect
    """
    method_arn = event.get('methodArn', '*')
    request_id = context.aws_request_id if context else None
    user_email = None
    
    try:
        logger.info("Lambda Authorizer invoked")
        logger.debug(f"Event: {json.dumps(event)}")
        
        # Extract method ARN
        if not method_arn or method_arn == '*':
            raise AuthorizerError("Missing methodArn in event")
        
        logger.info(f"Authorizing request for: {method_arn}")
        
        # Extract token from Authorization header
        token = extract_token(event)
        
        # Step 1: Validate token and extract claims
        try:
            claims = validate_token(token)
            user_email = claims.get('email')
            
            if not user_email:
                logger.error("Token missing email claim")
                log_authentication_failure(
                    reason="Token missing email claim",
                    request_id=request_id
                )
                resource = get_method_specific_resource(method_arn)
                return generate_deny_policy('no-email', resource)
            
            logger.info(f"Token validated for user: {user_email}")
            log_authentication_success(
                user_email=user_email,
                request_id=request_id
            )
            
        except TokenValidationError as e:
            logger.warning(f"Token validation failed: {e}")
            log_authentication_failure(
                reason=str(e),
                request_id=request_id
            )
            resource = get_method_specific_resource(method_arn)
            return generate_deny_policy('invalid-token', resource)
        
        # Step 2: Check authorization
        try:
            is_authorized = check_authorization(user_email, method_arn)
            
            if is_authorized:
                logger.info(f"Authorization granted for {user_email}")
                
                # Log successful authorization
                log_authorization_attempt(
                    user_email=user_email,
                    method=extract_method_from_arn(method_arn),
                    resource=extract_resource_from_arn(method_arn),
                    decision="ALLOW",
                    reason="User has required permissions",
                    request_id=request_id
                )
                
                # Generate comprehensive policy with all user's allowed methods
                # This is necessary because API Gateway caches based on token only
                from authorization_policy import load_policy_config
                config = load_policy_config()
                policy = generate_user_policy(user_email, method_arn, config)
                
                # Add additional context
                if 'context' not in policy:
                    policy['context'] = {}
                policy['context']['userEmail'] = user_email
                policy['context']['userId'] = str(claims.get('sub', ''))
                policy['context']['authTime'] = str(claims.get('auth_time', ''))
                
                return policy
            else:
                logger.warning(f"Authorization denied for {user_email}")
                
                # Log denied authorization
                log_authorization_attempt(
                    user_email=user_email,
                    method=extract_method_from_arn(method_arn),
                    resource=extract_resource_from_arn(method_arn),
                    decision="DENY",
                    reason="User lacks required permissions",
                    request_id=request_id
                )
                
                resource = get_method_specific_resource(method_arn)
                return generate_deny_policy(user_email, resource)
                
        except Exception as e:
            logger.error(f"Authorization check failed: {e}")
            log_authorization_error(
                error_message=str(e),
                user_email=user_email,
                method=extract_method_from_arn(method_arn),
                resource=extract_resource_from_arn(method_arn),
                request_id=request_id
            )
            resource = get_method_specific_resource(method_arn)
            return generate_deny_policy(user_email or 'error', resource)
        
    except TokenExtractionError as e:
        # Token extraction failed - deny access
        logger.warning(f"Token extraction failed: {e}")
        log_authentication_failure(
            reason=str(e),
            request_id=request_id
        )
        return handle_error(e, method_arn)
        
    except AuthorizerError as e:
        # Authorization error - deny access
        logger.error(f"Authorizer error: {e}")
        log_authorization_error(
            error_message=str(e),
            user_email=user_email,
            request_id=request_id
        )
        return handle_error(e, method_arn)
        
    except Exception as e:
        # Unexpected error - deny access (fail closed)
        logger.exception("Unexpected error in authorizer")
        log_authorization_error(
            error_message=f"Unexpected error: {str(e)}",
            user_email=user_email,
            request_id=request_id
        )
        return handle_error(e, method_arn)


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
        arn_parts = method_arn.split(':')
        if len(arn_parts) >= 6:
            path_part = arn_parts[5]
            path_parts = path_part.split('/')
            if len(path_parts) >= 3:
                return path_parts[2]
    except Exception:
        pass
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
        arn_parts = method_arn.split(':')
        if len(arn_parts) >= 6:
            path_part = arn_parts[5]
            path_parts = path_part.split('/')
            if len(path_parts) >= 4:
                return '/' + '/'.join(path_parts[3:])
    except Exception:
        pass
    return "/"
