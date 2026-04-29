"""
Agent Proxy - Lambda Handler for HTTP Agent Invocations

This Lambda function acts as an HTTP gateway for the AI agent runtime.
It receives REST API requests from clients and forwards them to the
AgentCore runtime (order_agent.py) for processing.

Architecture:
- Deployed behind API Gateway (HTTP API)
- Receives prompts via POST requests
- Invokes AgentCore runtime synchronously
- Returns agent responses to clients
- Handles CORS and OAuth callback redirects

Flow:
Client → API Gateway → agent_proxy.py → AgentCore Runtime → agent_proxy.py → Client

Endpoints:
- POST /invoke              - Send prompt to agent
- GET  /oauth2/callback     - OAuth redirect handler (returns HTML)
- OPTIONS *                 - CORS preflight
"""

import json
import logging
import os

import boto3

# ============================================================================
# Configuration
# ============================================================================

AGENT_RUNTIME_ARN = os.environ.get("AGENT_RUNTIME_ARN", "")  # ARN of order_agent.py runtime
# AWS Region - defaults to us-east-1 if not set
# Set AWS_REGION environment variable to use a different region
REGION = os.environ.get("AWS_REGION", "us-west-2")
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN", "*")  # CORS allowed origin
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()  # Logging level (DEBUG, INFO, WARNING, ERROR)

# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger()
# Set log level from environment variable with fallback to INFO
log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logger.setLevel(log_level)

logger.info("Agent Proxy initializing")
logger.info("  Log Level: %s", LOG_LEVEL)
logger.info("  Region: %s", REGION)
logger.info("  Agent Runtime ARN: %s", AGENT_RUNTIME_ARN if AGENT_RUNTIME_ARN else "(not set)")
logger.info("  CORS Allow Origin: %s", ALLOW_ORIGIN)

# ============================================================================
# AWS Service Clients
# ============================================================================

client = boto3.client("bedrock-agentcore", region_name=REGION)  # AgentCore API client

# ============================================================================
# HTTP Response Utilities
# ============================================================================


def _response(status, body):
    """
    Build standardized HTTP response with CORS headers.
    
    Args:
        status: HTTP status code (e.g., 200, 400, 500)
        body: Response body (dict or other JSON-serializable object)
        
    Returns:
        dict: Lambda proxy integration response format with:
            - statusCode: HTTP status
            - headers: CORS and content-type headers
            - body: JSON-encoded response body
    """
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOW_ORIGIN,
            "Access-Control-Allow-Headers": "content-type,authorization,x-amzn-bedrock-agentcore-runtime-session-id",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


# ============================================================================
# Lambda Handler
# ============================================================================


def handler(event, _context):
    """
    Main Lambda handler for agent proxy.
    
    Routes requests based on path and method:
    - OPTIONS * -> CORS preflight (204)
    - GET /oauth2/callback -> OAuth redirect handler (HTML)
    - POST /invoke -> Forward prompt to AgentCore runtime
    
    Request Format (POST /invoke):
        {
            "prompt": "User's natural language request",
            "system": "Optional system prompt"
        }
        Headers:
            Authorization: Bearer <token> (optional)
    
    Response Format:
        {
            "result": "Agent's response text",
            "auth_url": "OAuth URL if authentication required (optional)"
        }
    
    Args:
        event: Lambda event from API Gateway (HTTP API format)
        _context: Lambda context (unused)
        
    Returns:
        dict: HTTP response in Lambda proxy integration format
    """
    # Extract request details
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "")
    path = (http.get("path") or event.get("rawPath") or "").rstrip("/")
    
    # Log all request headers in a single statement
    request_headers = event.get("headers") or {}
    logger.info("Request received: %s %s - Headers: %s", method, path, json.dumps(request_headers))
    logger.debug("Event: %s", json.dumps(event, default=str))

    # ========================================================================
    # OAuth Callback Handler
    # ========================================================================
    # Simple callback handler to avoid 404 during OAuth redirects
    # Returns HTML page that closes the popup window
    if path.endswith("/oauth2/callback"):
        logger.info("OAuth callback request")
        if method == "OPTIONS":
            logger.debug("Handling CORS preflight for OAuth callback")
            return _response(204, {})
        logger.info("Returning OAuth callback success page")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html",
                "Access-Control-Allow-Origin": ALLOW_ORIGIN,
                "Access-Control-Allow-Headers": "content-type,authorization,x-amzn-bedrock-agentcore-runtime-session-id",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
            },
            "body": "<html><body><p>You can close this window.</p><script>window.close();</script></body></html>",
        }

    # ========================================================================
    # CORS Preflight Handler
    # ========================================================================
    if method == "OPTIONS":
        logger.debug("Handling CORS preflight request")
        return _response(204, {})

    # ========================================================================
    # Validation
    # ========================================================================
    if not AGENT_RUNTIME_ARN:
        logger.error("AGENT_RUNTIME_ARN environment variable not set")
        return _response(500, {"error": "AGENT_RUNTIME_ARN not set"})

    # ========================================================================
    # Request Body Parsing
    # ========================================================================
    body = event.get("body") or "{}"
    # Handle base64-encoded bodies (from API Gateway)
    if event.get("isBase64Encoded"):
        logger.debug("Decoding base64-encoded request body")
        body = json.loads(json.dumps(body)).encode("utf-8")
        body = body.decode("utf-8")

    try:
        payload = json.loads(body)
        logger.debug("Request body parsed successfully")
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in request body: %s", exc)
        return _response(400, {"error": "Invalid JSON body"})

    # ========================================================================
    # Extract and Validate Prompt
    # ========================================================================
    prompt = (payload or {}).get("prompt", "").strip()
    system = (payload or {}).get("system", "").strip()
    incoming_session_id = (payload or {}).get("runtime_session_id", "").strip()
    
    if not prompt:
        logger.warning("Missing prompt in request")
        return _response(400, {"error": "Missing 'prompt'"})
    
    if incoming_session_id:
        logger.info("Received runtime session ID from client: %s", incoming_session_id)
    else:
        logger.debug("No runtime session ID in request body")
    
    logger.info("Processing agent request (prompt length=%d, has_system=%s)", 
                len(prompt), bool(system))
    logger.debug("Prompt: %s", prompt[:200] + "..." if len(prompt) > 200 else prompt)
    if system:
        logger.debug("System prompt (length=%d): %s", len(system), 
                    system[:100] + "..." if len(system) > 100 else system)

    # ========================================================================
    # Build AgentCore Request
    # ========================================================================
    request_body = {"prompt": prompt}
    if system:
        request_body["system"] = system
    
    # Forward Authorization header if present (for user-specific OAuth)
    # Note: request_headers already extracted earlier for logging
    auth_header = request_headers.get("authorization") or request_headers.get("Authorization")
    if auth_header:
        logger.info("Forwarding user authorization header to AgentCore")
        logger.debug("Auth header (first 20 chars): %s...", auth_header[:20])
        request_body["auth_token"] = auth_header
    else:
        logger.debug("No authorization header in request")

    # ========================================================================
    # Invoke AgentCore Runtime
    # ========================================================================
    # Synchronously invoke the agent runtime (order_agent.py)
    logger.info("Invoking AgentCore runtime: %s", AGENT_RUNTIME_ARN)
    
    try:
        # Build invoke parameters
        invoke_params = {
            "agentRuntimeArn": AGENT_RUNTIME_ARN,
            "payload": json.dumps(request_body).encode("utf-8"),
            "qualifier": "DEFAULT",  # Runtime version/alias
        }
        
        # Add runtime session ID if present
        if incoming_session_id:
            invoke_params["runtimeSessionId"] = incoming_session_id
            #logger.debug("Configuring incoming_session_id in mcpSessionId parameter")
            #invoke_params["mcpSessionId"] = incoming_session_id
            logger.info("Passing runtime session ID to AgentCore: %s", incoming_session_id)
        
        response = client.invoke_agent_runtime(**invoke_params)
        logger.info("AgentCore runtime invocation successful")
        
        # Log response metadata and headers in debug mode (single log event)
        response_metadata = response.get("ResponseMetadata", {})
        http_headers = response_metadata.get("HTTPHeaders", {})
        http_status = response_metadata.get("HTTPStatusCode")
        logger.debug("AgentCore Runtime response - Status: %s, Headers: %s", http_status, json.dumps(http_headers))
        
        # Extract runtime session ID from response headers
        runtime_session_id = http_headers.get("x-amzn-bedrock-agentcore-runtime-session-id")
        if runtime_session_id:
            logger.info("AgentCore Runtime Session ID: %s", runtime_session_id)
        else:
            logger.debug("No runtime session ID in response headers")
    except Exception as exc:
        logger.error("Failed to invoke AgentCore runtime: %s", exc, exc_info=True)
        return _response(500, {"error": f"Failed to invoke agent: {str(exc)}"})

    # ========================================================================
    # Parse AgentCore Response
    # ========================================================================
    response_body = response.get("response")
    # Handle different response formats (stream vs bytes vs string)
    try:
        if hasattr(response_body, "read"):
            logger.debug("Reading streaming response body")
            text = response_body.read().decode("utf-8")
        else:
            logger.debug("Processing non-streaming response body")
            text = response_body.decode("utf-8") if isinstance(response_body, (bytes, bytearray)) else str(response_body)
        
        logger.debug("Response body (length=%d)", len(text))
    except Exception as exc:
        logger.error("Failed to read response body: %s", exc, exc_info=True)
        return _response(500, {"error": "Failed to read agent response"})

    # Parse JSON response from agent
    try:
        parsed = json.loads(text)
        logger.info("Agent response parsed successfully")
        
        # Log if OAuth URL is present
        if "auth_url" in parsed:
            logger.info("Agent response includes OAuth URL: %s", parsed["auth_url"])
        
        # Log result length
        if "result" in parsed:
            logger.debug("Agent result (length=%d)", len(str(parsed["result"])))
        
        logger.debug("Parsed response: %s", json.dumps(parsed, default=str)[:500])
        
    except json.JSONDecodeError as exc:
        logger.warning("Agent response is not valid JSON, wrapping in result field: %s", exc)
        # Fallback if response is not JSON
        parsed = {"result": text}

    # Add runtime session ID to response if available
    if runtime_session_id:
        parsed["runtime_session_id"] = runtime_session_id
        logger.debug("Added runtime_session_id to response")

    logger.info("Request completed successfully")
    return _response(200, parsed)
