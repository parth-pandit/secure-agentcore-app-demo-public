"""
OAuth2 Callback Server - Lambda Handler for 3-Legged OAuth Flow

This Lambda function handles the OAuth2 callback flow for user authentication
with external services (e.g., Microsoft Graph, Google APIs) via AgentCore Gateway.

OAuth Flow:
1. User initiates action requiring authentication
2. Gateway returns authorization URL
3. User authenticates with external provider
4. Provider redirects to this callback endpoint
5. This handler completes the OAuth flow with AgentCore

Endpoints:
- GET  /ping                    - Health check
- POST /userIdentifier/token    - Store user token for OAuth completion
- GET  /oauth2/callback         - OAuth provider redirect target

Architecture:
- Uses DynamoDB to temporarily store user tokens
- Calls AgentCore API to complete OAuth flow
- Returns HTML page that closes the OAuth popup window
"""

import json
import logging
import os
import time
from urllib.parse import urlencode

import boto3

# ============================================================================
# Configuration
# ============================================================================

# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION environment variable to use a different region
REGION = os.getenv("AWS_REGION", "us-west-2")
TABLE_NAME = os.getenv("OAUTH_CALLBACK_TABLE", "agentcore-oauth-callback")

# Endpoint paths
PING_PATH = "/ping"  # Health check endpoint
TOKEN_PATH = "/userIdentifier/token"  # Store user token
CALLBACK_PATH = "/oauth2/callback"  # OAuth redirect target

# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.info("OAuth2 Callback Server initializing")
logger.info("  Region: %s", REGION)
logger.info("  DynamoDB Table: %s", TABLE_NAME)

# ============================================================================
# AWS Service Clients
# ============================================================================

ddb = boto3.resource("dynamodb", region_name=REGION)  # DynamoDB for token storage
dp_client = boto3.client("bedrock-agentcore", region_name=REGION)  # AgentCore API

# ============================================================================
# HTTP Response Utilities
# ============================================================================


def _response(status, body, content_type="application/json"):
    """
    Build standardized HTTP response with CORS headers.
    
    Args:
        status: HTTP status code (e.g., 200, 400, 500)
        body: Response body (dict, string, or other)
        content_type: Content-Type header value
        
    Returns:
        dict: Lambda proxy integration response format
    """
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": body if isinstance(body, str) else json.dumps(body),
    }


def _get_body(event):
    """
    Extract and decode request body from Lambda event.
    
    Handles both plain text and base64-encoded bodies.
    
    Args:
        event: Lambda event object
        
    Returns:
        str: Decoded request body
    """
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = json.loads(json.dumps(body)).encode("utf-8").decode("utf-8")
    return body


# ============================================================================
# DynamoDB Token Storage
# ============================================================================


def _store_user_token(state: str, user_token: str):
    """
    Store user token in DynamoDB for OAuth completion.
    
    The token is stored with state (custom_state) as the unique key to ensure proper
    session isolation in concurrent OAuth flows. Expires after 10 minutes.
    
    Flow:
    1. order_agent.py generates random state value (custom_state)
    2. order_agent.py calls POST /userIdentifier/token with state and user_token
    3. Token is stored in DynamoDB with state as key
    4. order_agent.py passes state to AgentCore via customState parameter
    5. AgentCore returns state in callback URL
    6. Callback retrieves token using state from URL to complete OAuth flow
    
    Args:
        state: CSRF protection token used as DynamoDB key (custom_state from order_agent.py)
        user_token: User identifier token from AgentCore
        
    Side effects:
        Writes to DynamoDB table
    """
    logger.info("Storing user token in DynamoDB with state: %s...", state[:10] if state else "")
    logger.debug("User token (first 10 chars): %s...", user_token[:10] if user_token else "")
    
    try:
        table = ddb.Table(TABLE_NAME)
        now = int(time.time())
        item = {
            "id": state,  # Use state as unique key
            "user_token": user_token,
            "expires_at": now + 600,  # 10 minute expiration
        }
        
        table.put_item(Item=item)
        logger.info("Successfully stored user token for state: %s... (expires at %d)", state[:10], now + 600)
    except Exception as exc:
        logger.error("Failed to store user token in DynamoDB: %s", exc, exc_info=True)
        raise


def _get_user_token(state: str):
    """
    Retrieve user token from DynamoDB using state as key.
    
    Args:
        state: CSRF protection token from callback URL (custom_state)
    
    Returns:
        tuple: (user_token, expires_at) if found, (None, None) otherwise
    """
    logger.info("Retrieving user token from DynamoDB for state: %s...", state[:10] if state else "")
    
    try:
        table = ddb.Table(TABLE_NAME)
        resp = table.get_item(Key={"id": state})
        item = resp.get("Item") or {}
        user_token = item.get("user_token")
        expires_at = item.get("expires_at", 0)
        
        if user_token:
            logger.info("Retrieved user token for state: %s... (expires at %d)", state[:10], expires_at)
            logger.debug("User token (first 10 chars): %s...", user_token[:10])
            
            # Check if token is expired
            if expires_at < time.time():
                logger.warning("Retrieved user token is expired (expired at %d, now is %d)", 
                             expires_at, int(time.time()))
        else:
            logger.warning("No user token found in DynamoDB for state: %s...", state[:10])
        
        return (user_token, expires_at)
    except Exception as exc:
        logger.error("Failed to retrieve user token from DynamoDB for state %s...: %s", 
                    state[:10] if state else "", exc, exc_info=True)
        raise


# ============================================================================
# User Verification
# ============================================================================


def _get_current_user_from_request(event):
    """
    Extract current user token from request headers or cookies.
    
    This function attempts to identify the user making the OAuth callback
    request by checking:
    1. Authorization header (Bearer token)
    2. Cookie header (auth token)
    
    Args:
        event: Lambda event object containing headers
        
    Returns:
        str: User token if found, None otherwise
    """
    logger.debug("Extracting current user from request")
    
    # Get headers (case-insensitive)
    headers = event.get("headers") or {}
    
    # Try Authorization header first
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if auth_header:
        # Handle "Bearer <token>" format
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            logger.debug("Found user token in Authorization header (first 10 chars): %s...", token[:10])
            return token
        else:
            logger.debug("Found user token in Authorization header (first 10 chars): %s...", auth_header[:10])
            return auth_header
    
    # Try Cookie header
    cookie_header = headers.get("cookie") or headers.get("Cookie")
    if cookie_header:
        logger.debug("Parsing cookies from Cookie header")
        # Parse cookies (format: "name1=value1; name2=value2")
        cookies = {}
        for cookie in cookie_header.split(";"):
            cookie = cookie.strip()
            if "=" in cookie:
                name, value = cookie.split("=", 1)
                cookies[name.strip()] = value.strip()
        
        # Look for common auth token cookie names
        for cookie_name in ["auth_token", "token", "user_token", "session"]:
            if cookie_name in cookies:
                token = cookies[cookie_name]
                logger.debug("Found user token in cookie '%s' (first 10 chars): %s...", cookie_name, token[:10])
                return token
    
    logger.debug("No user token found in request headers or cookies")
    return None


# ============================================================================
# AgentCore OAuth Completion
# ============================================================================


def _complete_oauth(session_uri: str, user_token: str):
    """
    Complete the OAuth flow by calling AgentCore API.
    
    This notifies AgentCore that the user has successfully authenticated
    with the external OAuth provider, allowing the agent to proceed with
    the original request.
    
    Args:
        session_uri: OAuth session identifier from callback parameters
        user_token: User identifier token from DynamoDB
        
    Returns:
        dict: Response from AgentCore API
        
    Raises:
        botocore.exceptions.ClientError: If API call fails
    """
    logger.info("Completing OAuth flow with AgentCore")
    logger.debug("Session URI: %s", session_uri)
    logger.debug("User token (first 10 chars): %s...", user_token[:10] if user_token else "")
    
    try:
        response = dp_client.complete_resource_token_auth(
            userIdentifier={"userToken": user_token},
            sessionUri=session_uri,
        )
        logger.info("Successfully completed OAuth flow with AgentCore")
        logger.debug("AgentCore response: %s", response)
        return response
    except Exception as exc:
        logger.error("Failed to complete OAuth flow with AgentCore: %s", exc, exc_info=True)
        raise


# ============================================================================
# HTML Response Templates
# ============================================================================


def _success_html():
    """
    Generate success page HTML for OAuth callback.
    
    This page:
    1. Posts a message to the opener window (if opened as popup)
    2. Automatically closes the window
    3. Shows a fallback message if auto-close fails
    
    Returns:
        str: HTML content for successful OAuth completion
    """
    return """<!DOCTYPE html>
            <html>
                <head>
                    <title>OAuth Success</title>
                </head>
                <body>
                    <script>
                    // Notify parent window that OAuth is complete
                    if (window.opener) {
                        window.opener.postMessage({ type: "oauth_complete" }, "*");

                    }
                    // Auto-close the popup window
                    window.close();
                    </script>
                    <p>Authentication complete. You can close this window.</p>
                </body>
            </html>
        """

    # New code changes provided Adarsh on 20260211
    # logger.debug("Using new HTML template to trigger 'oauth_success'")
    # return """<!DOCTYPE html>
    #     <html>
    #         <head>
    #             <title>OAuth Success</title>
    #         </head>
    #         <body>
    #             <script>
    #             // Notify parent window that OAuth is complete
    #             if (window.opener) {
    #                 window.opener.postMessage({ type: "oauth_success" }, "*");
    #                 setTimeout(() => window.close(), 500);
    #             } else {
    #                 window.location.href = "/?oauth=success";
    #             }
    #             </script>
    #             <p>✓ Authentication complete. Closing window...</p>
    #         </body>
    #     </html>    
    # """


# ============================================================================
# Lambda Handler
# ============================================================================


def handler(event, _context):
    """
    Main Lambda handler for OAuth callback server.
    
    Routes requests to appropriate handlers based on path and method:
    
    - OPTIONS * -> CORS preflight (204)
    - GET /ping -> Health check (200)
    - POST /userIdentifier/token -> Store user token (200)
    - GET /oauth2/callback -> Complete OAuth flow (200 with HTML)
    
    Args:
        event: Lambda event from API Gateway (HTTP API format)
        _context: Lambda context (unused)
        
    Returns:
        dict: HTTP response in Lambda proxy integration format
    """
    # Extract request details
    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    method = (event.get("requestContext", {}).get("http", {}).get("method") or "").upper()
    
    logger.info("Request received: %s %s", method, path)
    logger.debug("Event: %s", json.dumps(event, default=str))

    # Handle CORS preflight requests
    if method == "OPTIONS":
        logger.debug("Handling CORS preflight request")
        return _response(204, "")

    # Health check endpoint
    if path == "" or path == PING_PATH:
        logger.info("Health check request")
        return _response(200, {"status": "ok"})

    # Store user token endpoint
    # Called before OAuth flow starts to associate user with session
    if path == TOKEN_PATH and method == "POST":
        logger.info("Store user token request")
        
        try:
            body = json.loads(_get_body(event) or "{}")
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON body: %s", exc)
            return _response(400, {"error": "Invalid JSON body"})
        
        user_token = body.get("user_token")
        state = body.get("state")
        
        if not user_token:
            logger.warning("Missing user_token in request body")
            return _response(400, {"error": "Missing user_token"})
        
        if not state:
            logger.warning("Missing state in request body")
            return _response(400, {"error": "Missing state"})
        
        try:
            _store_user_token(state, user_token)
            logger.info("User token stored successfully for state: %s...", state[:10])
            return _response(200, {"status": "stored"})
        except Exception as exc:
            logger.error("Failed to store user token: %s", exc, exc_info=True)
            return _response(500, {"error": "Failed to store user token"})

    # OAuth callback endpoint
    # Called by OAuth provider after user authenticates
    if path == CALLBACK_PATH and method == "GET":
        logger.info("OAuth callback request")
        
        # Extract parameters from query string
        params = event.get("queryStringParameters") or {}
        logger.debug("Query parameters: %s", params)
        
        # Extract BOTH session_id and state from callback URL
        # session_id: Used for AgentCore API call (complete_resource_token_auth)
        # state: Used as DynamoDB key to retrieve user token
        session_id = params.get("session_id")
        state = params.get("state")
        
        if not session_id:
            logger.error("Missing session_id in callback parameters")
            return _response(400, "Missing session_id parameter", content_type="text/plain")
        
        if not state:
            logger.error("Missing state in callback parameters")
            return _response(400, "Missing state parameter", content_type="text/plain")
        
        logger.info("Extracted session_id from callback: %s", session_id)
        logger.info("Extracted state from callback: %s...", state[:10])
        
        # Retrieve stored user token using state as key
        try:
            stored_user_token, expires_at = _get_user_token(state)
        except Exception as exc:
            logger.error("Failed to retrieve user token for state %s...: %s", state[:10], exc, exc_info=True)
            return _response(500, "Failed to retrieve user token", content_type="text/plain")
        
        # Check if session exists
        if not stored_user_token:
            logger.error("Session not found for state: %s...", state[:10])
            return _response(404, f"Session not found for state: {state[:10]}...", content_type="text/plain")
        
        # Check if session is expired
        if expires_at < time.time():
            logger.error("Session expired for state: %s... (token stored at %d, now is %d)", 
                        state[:10], expires_at, int(time.time()))
            return _response(410, f"Session expired: token stored at {expires_at}", content_type="text/plain")
        
        logger.info("Session validation successful for state: %s...", state[:10])
        
        # Complete OAuth flow with AgentCore using session_id
        logger.info("Completing OAuth flow with AgentCore for session_id: %s", session_id)
        try:
            _complete_oauth(session_id, stored_user_token)
            logger.info("OAuth flow completed successfully for session_id: %s", session_id)
        except Exception as exc:
            logger.error("Failed to complete OAuth flow for session_id %s: %s", session_id, exc, exc_info=True)
            return _response(500, "Failed to complete OAuth flow", content_type="text/plain")
        
        # Return success page that closes the popup
        logger.info("Returning success page for session_id: %s", session_id)
        return _response(200, _success_html(), content_type="text/html")

    # 404 for unknown paths
    logger.warning("Unknown path requested: %s %s", method, path)
    return _response(404, {"error": "Not Found"})
