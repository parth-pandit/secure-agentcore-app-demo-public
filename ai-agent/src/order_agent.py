"""
Order Agent - AI Agent Runtime for AWS Bedrock AgentCore

This module implements an AI agent that:
1. Processes natural language prompts using AWS Bedrock models
2. Integrates with external APIs via MCP (Model Context Protocol) Gateway
3. Handles OAuth authentication for secure API access

Architecture:
- Runs as an AgentCore runtime application
- Invoked by agent_proxy.py via HTTP
- Dynamically loads and registers MCP tools from the Gateway
- Manages authentication tokens and OAuth flows
"""

import json
import logging
import os
import re
import secrets
import threading
import time

import boto3
import httpx
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.tools import PythonAgentTool, normalize_tool_spec
from strands_tools.current_time import current_time  # Built-in calendar/datetime tool

# ============================================================================
# Configuration - Environment Variables
# ============================================================================

# Bedrock model configuration
MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # Claude Sonnet 4.5
)
# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION environment variable to use a different region
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.2"))  # Lower = more deterministic

# MCP Gateway configuration
GATEWAY_SECRET_NAME = os.getenv("GATEWAY_SECRET_NAME", "agentcore/gateway-authcode")
GATEWAY_TOOLS_ENABLED = os.getenv("GATEWAY_TOOLS_ENABLED", "true").lower() in {"1", "true", "yes"}
GATEWAY_PROTOCOL_VERSION = os.getenv("GATEWAY_PROTOCOL_VERSION", "2025-11-25")

# OAuth configuration
OAUTH_FORCE_AUTH = os.getenv("OAUTH_FORCE_AUTH", "false").lower() in {"1", "true", "yes"}

OAUTH_CALLBACK_SERVER_URL = os.getenv("OAUTH_CALLBACK_SERVER_URL")  # OAuth callback server endpoint

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()  # DEBUG, INFO, WARNING, ERROR

# Memory configuration
MEMORY_ID = os.getenv("MEMORY_ID", "")  # AgentCore Memory ID (just the ID, not full ARN)
MEMORY_REGION = os.getenv("MEMORY_REGION", os.getenv("AWS_REGION", "us-east-1"))
MEMORY_RECALL_MAX_EVENTS = int(os.getenv("MEMORY_RECALL_MAX_EVENTS", "10"))

# ============================================================================
# Application Initialization
# ============================================================================

app = BedrockAgentCoreApp()  # AgentCore runtime application
logger = logging.getLogger(__name__)

# Set log level from environment variable
log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logger.setLevel(log_level)

# Log startup configuration
logger.info("Order Agent initializing with configuration:")
logger.info("  Model ID: %s", MODEL_ID)
logger.info("  AWS Region: %s", AWS_REGION)
logger.info("  Temperature: %s", TEMPERATURE)
logger.info("  Gateway Tools Enabled: %s", GATEWAY_TOOLS_ENABLED)
logger.info("  OAuth Force Auth: %s", OAUTH_FORCE_AUTH)
logger.info("  OAuth Callback Server URL: %s", OAUTH_CALLBACK_SERVER_URL or "(not configured)")
logger.info("  Log Level: %s", LOG_LEVEL)
logger.info("  Memory ID: %s", MEMORY_ID or "(not configured)")
logger.info("  Memory Region: %s", MEMORY_REGION)

# ============================================================================
# Global State Management
# ============================================================================

# Gateway secret caching (Azure AD credentials)
_gateway_secret_cache = None  # Cached secrets from AWS Secrets Manager

# Authentication state
_gateway_active_auth_header = None  # Current Authorization header for Gateway requests
_gateway_token_cache = {"access_token": None, "expires_at": 0}  # OAuth token cache
_gateway_lock = threading.Lock()  # Thread-safe token refresh

# MCP tools state
_gateway_tools_loaded = False  # Flag to prevent duplicate tool registration
_gateway_tools_lock = threading.Lock()  # Thread-safe tool loading

# Request-scoped state (thread-local storage)
_request_local = threading.local()  # Stores auth URLs per request

# Agent instance (singleton pattern)
_agent_instance = None  # Cached Strands Agent instance
_agent_lock = threading.Lock()  # Thread-safe agent initialization

# User email cache (thread-local storage)
_user_email_cache = threading.local()  # Stores user email per request

# Global user email cache (for cross-thread access within a request)
_current_user_email = None  # Current user email for the active request
_user_email_lock = threading.Lock()  # Thread-safe access to email

# Tools used tracking (global, reset per request)
_current_tools_used = []  # List of tool names invoked in current request

# Memory state
_memory_client = None  # Lazy-initialized boto3 client for memory
_memory_recalled = False  # Whether memory has been recalled for this microVM lifecycle

# Conversation history — persists within the microVM session
# Seeded from memory on first invocation, appended after each turn
_conversation_history = []

# Patterns to skip saving to memory (auth/admin turns)
_SKIP_RESPONSE_PATTERNS = ["oauth2/authorize", "one-time authorization", "Authorize Access"]
_SKIP_PROMPT_PATTERNS = ["force_reauth", "recall_memory", "test memory"]


# ============================================================================
# Memory Integration
# ============================================================================


def _get_memory_client():
    """Get or create the boto3 bedrock-agentcore client for memory operations."""
    global _memory_client
    if _memory_client is None and MEMORY_ID:
        _memory_client = boto3.client("bedrock-agentcore", region_name=MEMORY_REGION)
    return _memory_client


def _seed_history_from_recall(recall_text: str):
    """Parse recalled memory text and seed conversation history for context continuity."""
    global _conversation_history
    if not recall_text or _conversation_history:
        return  # Don't re-seed if we already have history

    lines = recall_text.split("\n")
    for line in lines:
        line = line.strip()
        # User messages: "**🗣️ some text**"
        if "🗣️" in line:
            text = line.replace("**", "").replace("🗣️", "").strip()
            if text:
                _conversation_history.append({"role": "user", "content": [{"text": text}]})
        # Assistant messages: "💬 some text"
        elif "💬" in line:
            text = line.replace("💬", "").strip()
            if text:
                _conversation_history.append({"role": "assistant", "content": [{"text": text}]})

    if _conversation_history:
        logger.info("Seeded %d messages from memory recall", len(_conversation_history))


def memory_save_turn(actor_id: str, session_id: str, user_text: str, assistant_text: str):
    """Save a conversation turn (user + assistant) to AgentCore Memory."""
    client = _get_memory_client()
    if not client or not MEMORY_ID:
        return

    # Skip auth-related and admin turns
    if any(p in assistant_text for p in _SKIP_RESPONSE_PATTERNS):
        return
    if any(p in user_text.lower() for p in _SKIP_PROMPT_PATTERNS):
        return

    # Sanitize actor_id for memory API (only allows [a-zA-Z0-9-_/])
    import re
    safe_actor = re.sub(r'[^a-zA-Z0-9\-_/]', '-', actor_id)

    try:
        from datetime import datetime, timezone
        client.create_event(
            memoryId=MEMORY_ID,
            actorId=safe_actor,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            payload=[
                {"conversational": {"content": {"text": user_text}, "role": "USER"}},
                {"conversational": {"content": {"text": assistant_text}, "role": "ASSISTANT"}},
            ],
        )
        logger.info("Saved turn to memory: actor=%s, session=%s", safe_actor, session_id[:12])
    except Exception as e:
        logger.warning("Failed to save turn to memory: %s", e)


def memory_recall(actor_id: str) -> str | None:
    """Recall recent conversation history for an actor across all sessions.

    Returns a formatted string of recent messages, or None if no history.
    """
    client = _get_memory_client()
    if not client or not MEMORY_ID:
        return None

    # Sanitize actor_id for memory API
    import re
    safe_actor = re.sub(r'[^a-zA-Z0-9\-_/]', '-', actor_id)

    try:
        # List sessions for this actor
        resp = client.list_sessions(memoryId=MEMORY_ID, actorId=safe_actor, maxResults=20)
        sessions = resp.get("sessionSummaries", [])
        if not sessions:
            return None

        # Sort oldest first
        sessions.sort(key=lambda s: str(s.get("createdAt", "")))

        # Collect interactions
        all_interactions = []
        for sess in sessions:
            sid = sess.get("sessionId", "")
            if not sid:
                continue
            try:
                ev_resp = client.list_events(
                    memoryId=MEMORY_ID, actorId=safe_actor, sessionId=sid,
                    includePayloads=True, maxResults=20,
                )
                session_events = []
                for ev in ev_resp.get("events", []):
                    event_msgs = []
                    for msg in ev.get("payload", []):
                        conv = msg.get("conversational", {})
                        role = conv.get("role", "")
                        text = conv.get("content", {}).get("text", "")
                        if text and role:
                            event_msgs.append({"role": role, "text": text})
                    if event_msgs:
                        session_events.append(event_msgs)
                # Reverse (newest-first → chronological)
                session_events.reverse()
                for event_msgs in session_events:
                    all_interactions.extend(event_msgs)
            except Exception:
                pass

        if not all_interactions:
            return None

        # Take last N turns
        recent = all_interactions[-(MEMORY_RECALL_MAX_EVENTS * 2):]

        num_turns = sum(1 for m in recent if m["role"] == "USER")
        lines = [f"📝 **Recent conversation history** ({num_turns} turns):\n"]
        i = 0
        while i < len(recent):
            msg = recent[i]
            if msg["role"] == "USER":
                lines.append(f"**🗣️ {msg['text'][:300]}**")
                if i + 1 < len(recent) and recent[i + 1]["role"] == "ASSISTANT":
                    lines.append(f"💬 {recent[i + 1]['text'][:500]}")
                    i += 2
                else:
                    i += 1
                lines.append("\n---\n")
            else:
                lines.append(f"💬 {msg['text'][:500]}")
                lines.append("\n---\n")
                i += 1

        return "\n".join(lines)

    except Exception as e:
        logger.warning("Memory recall failed: %s", e)
        return None


# ============================================================================
# Secret Management
# ============================================================================


def _load_gateway_secret():
    """
    Load and cache Gateway credentials from AWS Secrets Manager.
    
    The secret contains Azure AD OAuth credentials:
    - tenant_id: Azure AD tenant
    - client_id: Application (client) ID
    - client_secret: Application secret
    - gateway_mcp_url: MCP Gateway endpoint URL
    
    Returns:
        dict: Parsed secret containing authentication credentials
    """
    global _gateway_secret_cache
    if _gateway_secret_cache is not None:
        logger.debug("Using cached gateway secret")
        return _gateway_secret_cache

    logger.info("Loading gateway secret from Secrets Manager: %s", GATEWAY_SECRET_NAME)
    try:
        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        resp = client.get_secret_value(SecretId=GATEWAY_SECRET_NAME)
        secret_str = resp.get("SecretString") or "{}"
        _gateway_secret_cache = json.loads(secret_str)
        logger.info("Successfully loaded gateway secret")
        logger.debug("Gateway secret contains keys: %s", list(_gateway_secret_cache.keys()))
        return _gateway_secret_cache
    except Exception as exc:
        logger.error("Failed to load gateway secret: %s", exc, exc_info=True)
        raise


# ============================================================================
# Authentication Utilities
# ============================================================================


def _normalize_bearer(auth_header: str) -> str | None:
    """
    Normalize authorization header to Bearer token format.
    
    Args:
        auth_header: Raw authorization header value
        
    Returns:
        Normalized "Bearer <token>" string or None if empty
    """
    if not auth_header:
        return None
    value = auth_header.strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        return value
    return f"Bearer {value}"


def _get_gateway_token():
    """
    Get or refresh OAuth access token for Gateway authentication.
    
    Uses Azure AD OAuth 2.0 client credentials flow:
    1. Check if cached token is still valid
    2. If expired, request new token from Azure AD
    3. Cache token with expiration time
    
    Returns:
        str: Valid OAuth access token
        
    Thread-safe: Uses lock to prevent concurrent token refreshes
    """
    with _gateway_lock:
        # Return cached token if still valid
        logger.debug("_gateway_token_cache[\"access_token\"] (first 20 chars): %s", _gateway_token_cache["access_token"])
        logger.debug("_gateway_token_cache[\"expires_at\"]: %d", _gateway_token_cache["expires_at"])

        if _gateway_token_cache["access_token"] and time.time() < _gateway_token_cache["expires_at"]:
            logger.debug("Using cached OAuth token (expires in %d seconds)", 
                        int(_gateway_token_cache["expires_at"] - time.time()))
            return _gateway_token_cache["access_token"]

        logger.info("Refreshing OAuth token from Azure AD")
        try:
            # Load credentials from Secrets Manager
            secret = _load_gateway_secret()
            tenant_id = secret["tenant_id"]
            client_id = secret["client_id"]
            client_secret = secret["client_secret"]

            # Request new token from Azure AD
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": f"{client_id}/.default",
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            logger.debug("Requesting OAuth token from: %s", token_url)
            response = httpx.post(token_url, data=data, headers=headers, timeout=10.0)
            response.raise_for_status()
            payload = response.json()

            # Cache token with 30-second buffer before expiration
            access_token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 300))
            _gateway_token_cache["access_token"] = access_token
            _gateway_token_cache["expires_at"] = time.time() + max(expires_in - 30, 30)
            
            logger.info("Successfully refreshed OAuth token (expires in %d seconds)", expires_in)
            return access_token
        except httpx.HTTPStatusError as exc:
            logger.error("OAuth token request failed with status %d: %s", 
                        exc.response.status_code, exc.response.text)
            raise
        except Exception as exc:
            logger.error("Failed to refresh OAuth token: %s", exc, exc_info=True)
            raise


def _set_gateway_auth_from_context(context):
    """
    Set the active Gateway authentication header from request context.
    
    Priority:
    1. User-provided Authorization header from request
    2. System-generated OAuth token (fallback)
    
    Args:
        context: AgentCore request context with headers
        
    Side effects:
        Updates global _gateway_active_auth_header
    """
    global _gateway_active_auth_header
    auth_header = None
    if context and getattr(context, "request_headers", None):
        auth_header = context.request_headers.get("Authorization")

    desired_header = _normalize_bearer(auth_header)
    if not desired_header:
        logger.debug("No user auth header, using system OAuth token")
        desired_header = _normalize_bearer(_get_gateway_token())
    else:
        logger.debug("Using user-provided auth header")

    if desired_header != _gateway_active_auth_header:
        _gateway_active_auth_header = desired_header
        logger.info("Gateway auth header updated")


def _set_request_auth_url(auth_url: str | None):
    """
    Store OAuth authorization URL in thread-local storage.
    
    Used when MCP tools require user authentication (3-legged OAuth).
    
    Args:
        auth_url: OAuth authorization URL or None to clear
    """
    setattr(_request_local, "auth_url", auth_url)


def _get_request_auth_url() -> str | None:
    """
    Retrieve OAuth authorization URL from thread-local storage.
    
    Returns:
        str: OAuth authorization URL if set, None otherwise
    """
    return getattr(_request_local, "auth_url", None)


def _get_request_custom_state() -> str | None:
    """
    Retrieve CSRF token (custom_state) from thread-local storage.
    
    Returns:
        str: CSRF token if set, None otherwise
    """
    return getattr(_request_local, "custom_state", None)


def _set_request_session_id(session_id: str | None):
    """
    Store OAuth session ID in thread-local storage.
    
    Used when MCP tools require user authentication (3-legged OAuth).
    The session_id is extracted from the Gateway response and used as
    the DynamoDB key for token storage.
    
    Args:
        session_id: OAuth session ID or None to clear
    """
    setattr(_request_local, "session_id", session_id)


def _get_request_session_id() -> str | None:
    """
    Retrieve OAuth session ID from thread-local storage.
    
    Returns:
        str: OAuth session ID if set, None otherwise
    """
    return getattr(_request_local, "session_id", None)


def _extract_auth_url(value) -> str | None:
    """
    Recursively extract OAuth authorization URL from various data structures.
    
    Searches for authorization URLs in:
    - Strings containing "authorize"
    - Dict keys: auth_url, authorization_url, authorizationUrl, url
    - Nested dicts and lists
    
    Args:
        value: String, dict, list, or other value to search
        
    Returns:
        str: First found authorization URL or None
    """
    if not value:
        return None
    if isinstance(value, str):
        if value.startswith("http") and "authorize" in value:
            url = value.rstrip("*).]")
            logger.debug("Extracted auth URL from string: %s", url)
            return url
        match = re.search(r"(https?://[^\s\"']+)", value)
        if match and "authorize" in match.group(1):
            url = match.group(1).rstrip("*).]")
            logger.debug("Extracted auth URL from regex match: %s", url)
            return url
        return None
    if isinstance(value, dict):
        for key in ("auth_url", "authorization_url", "authorizationUrl", "url"):
            if key in value:
                return _extract_auth_url(value[key])
        for nested in value.values():
            found = _extract_auth_url(nested)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _extract_auth_url(item)
            if found:
                return found
    return None


def _extract_email_from_token(token: str) -> str | None:
    """
    Extract user email from JWT token.
    
    Attempts to decode the JWT token and extract the email claim.
    Common email claim names: email, preferred_username, upn, unique_name
    
    Args:
        token: JWT token string (may include "Bearer " prefix)
        
    Returns:
        str: User email if found, None otherwise
    """
    logger.info("DIAGNOSTIC: _extract_email_from_token called")
    if not token:
        logger.warning("DIAGNOSTIC: Token is None or empty")
        return None
    
    # Remove "Bearer " prefix if present
    token = token.replace("Bearer ", "").replace("bearer ", "").strip()
    logger.debug("DIAGNOSTIC: Token after removing Bearer prefix (first 20 chars): %s...", token[:20])
    
    try:
        # JWT tokens have 3 parts separated by dots: header.payload.signature
        parts = token.split(".")
        logger.debug("DIAGNOSTIC: Token split into %d parts", len(parts))
        if len(parts) != 3:
            logger.debug("DIAGNOSTIC: Token does not appear to be a valid JWT (expected 3 parts, got %d)", len(parts))
            return None
        
        # Decode the payload (second part)
        # Add padding if needed (JWT base64 encoding may omit padding)
        payload_part = parts[1]
        logger.debug("DIAGNOSTIC: Payload part length: %d", len(payload_part))
        padding = 4 - (len(payload_part) % 4)
        if padding != 4:
            payload_part += "=" * padding
            logger.debug("DIAGNOSTIC: Added %d padding characters", padding)
        
        import base64
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload = json.loads(decoded_bytes.decode("utf-8"))
        
        logger.debug("DIAGNOSTIC: JWT payload decoded successfully")
        logger.debug("DIAGNOSTIC: Available claims in token: %s", list(payload.keys()))
        
        # Try common email claim names
        for claim in ["email", "preferred_username", "upn", "unique_name"]:
            if claim in payload:
                email = payload[claim]
                logger.debug("DIAGNOSTIC: Extracted email from token claim '%s': %s", claim, email)
                return email
        
        logger.debug("DIAGNOSTIC: No email claim found in token. Available claims: %s", list(payload.keys()))
        return None
        
    except Exception as exc:
        logger.error("DIAGNOSTIC: Failed to extract email from token: %s", exc, exc_info=True)
        return None


def _set_user_email(email: str | None):
    """
    Store user email in global storage accessible to all threads.
    
    Args:
        email: User email or None to clear
    """
    global _current_user_email
    with _user_email_lock:
        _current_user_email = email
    logger.debug("Set current user email to: %s", email)


def _get_user_email() -> str | None:
    """
    Retrieve user email from global storage.
    
    Returns:
        str: User email if set, None otherwise
    """
    with _user_email_lock:
        return _current_user_email


# ============================================================================
# OAuth Callback Server Communication
# ============================================================================


def _store_token_in_callback_server(user_token=None, custom_state=None):
    """
    Store user token in OAuth callback server for 3-legged OAuth flows.
    
    This function proactively stores the user's authentication token in the
    callback server's DynamoDB table, using custom_state (CSRF token) as the unique key.
    When the user completes OAuth authentication, the callback server will
    retrieve this token using the state parameter from the callback URL.
    
    Flow:
    1. Agent generates random state value (custom_state)
    2. Agent stores user_token with state as DynamoDB key
    3. Agent passes state to AgentCore via customState parameter
    4. AgentCore returns state in callback URL
    5. Callback server retrieves token using state from URL
    
    Args:
        user_token: User's JWT authentication token (without "Bearer " prefix)
        custom_state: CSRF protection token used as DynamoDB key
        
    Side effects:
        Makes HTTP POST request to callback server
        
    Raises:
        httpx.HTTPError: If callback server request fails
    """
    if not OAUTH_CALLBACK_SERVER_URL:
        logger.warning("OAuth callback server URL not configured, skipping token storage")
        return
    
    if not user_token:
        logger.warning("No user token provided for callback server storage")
        return
    
    if not custom_state:
        logger.error("No custom_state provided - cannot store token without unique key")
        return
    
    callback_url = OAUTH_CALLBACK_SERVER_URL.rstrip('/') + '/userIdentifier/token'
    
    # Build payload with custom_state as key
    payload_data = {
        "user_token": user_token,
        "state": custom_state  # Use state as DynamoDB key
    }
    
    logger.info("Storing user token in callback server with state: %s...", custom_state[:10])
    logger.debug("Callback server URL: %s", callback_url)
    logger.debug("Payload keys: %s", list(payload_data.keys()))
    
    try:
        response = httpx.post(
            callback_url,
            json=payload_data,
            headers={"Content-Type": "application/json"},
            timeout=5.0,
        )
        response.raise_for_status()
        logger.info("Successfully stored user token in callback server (state: %s...)", custom_state[:10])
    except httpx.HTTPStatusError as exc:
        logger.error("Callback server returned error status %d: %s", 
                    exc.response.status_code, exc.response.text)
        raise
    except Exception as exc:
        logger.error("Failed to store user token in callback server: %s", exc, exc_info=True)
        raise


# ============================================================================
# MCP Gateway Communication
# ============================================================================


def _get_gateway_url():
    """
    Get the MCP Gateway endpoint URL.
    
    Returns:
        str: Gateway URL from environment or secrets
        
    Raises:
        RuntimeError: If Gateway URL is not configured
    """
    secret = _load_gateway_secret()
    gateway_url = os.getenv("GATEWAY_MCP_URL", secret.get("gateway_mcp_url", ""))
    if not gateway_url:
        logger.error("Gateway MCP URL is not configured in environment or secrets")
        raise RuntimeError("Gateway MCP URL is not configured.")
    logger.debug("Using Gateway URL: %s", gateway_url)
    return gateway_url


def _gateway_headers():
    """
    Build HTTP headers for Gateway requests.
    
    Returns:
        dict: Headers including Authorization and MCP protocol version
        
    Raises:
        RuntimeError: If auth header is not set
    """
    if not _gateway_active_auth_header:
        raise RuntimeError("Gateway auth header is not set.")
    return {
        "Authorization": _gateway_active_auth_header,
        "Content-Type": "application/json",
        "MCP-Protocol-Version": GATEWAY_PROTOCOL_VERSION,
    }


def _gateway_jsonrpc(method: str, params: dict | None = None, request_id: int = 1):
    """
    Make a JSON-RPC 2.0 call to the MCP Gateway.
    
    Args:
        method: JSON-RPC method name (e.g., "tools/list", "tools/call")
        params: Method parameters
        request_id: JSON-RPC request ID
        
    Returns:
        dict: JSON-RPC response
        
    Raises:
        httpx.HTTPStatusError: If request fails
    """
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    
    logger.debug("Gateway JSON-RPC call: method=%s, request_id=%d", method, request_id)
    try:
        resp = httpx.post(
            _get_gateway_url(),
            headers=_gateway_headers(),
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.debug("Gateway JSON-RPC response: status=%d", resp.status_code)
        logger.debug("Tool call result=%s", result)
        return result
    except httpx.HTTPStatusError as exc:
        logger.error("Gateway JSON-RPC call failed: method=%s, status=%d, response=%s",
                    method, exc.response.status_code, exc.response.text)
        raise
    except Exception as exc:
        logger.error("Gateway JSON-RPC call error: method=%s, error=%s", method, exc, exc_info=True)
        raise


# ============================================================================
# MCP Tool Registration
# ============================================================================


def _register_gateway_tools(tools: list[dict]):
    """
    Register MCP tools with the Strands agent.
    
    Converts MCP tool definitions to Strands PythonAgentTool format:
    1. Clear existing tools, then re-register built-in tools (e.g. current_time)
    2. For each MCP tool, create a wrapper function that calls Gateway
    3. Register tool with agent's tool registry
    
    Args:
        tools: List of MCP tool definitions with name, description, inputSchema
        
    Side effects:
        Clears and repopulates agent.tool_registry
    """
    logger.info("Registering %d MCP tools with agent", len(tools))
    
    # Ensure only MCP tools are registered.
    agent = _get_agent()
    agent.tool_registry.registry.clear()
    
    # Re-register the calendar tool after clearing (it's always available)
    agent.tool_registry.register_tool(current_time)
    
    registered_count = 0
    for tool in tools:
        name = tool.get("name")
        if not name:
            logger.warning("Skipping tool with no name: %s", tool)
            continue

        logger.debug("Registering tool: %s", name)
        
        # Build tool specification
        description = tool.get("description") or f"Tool which performs {name}"
        input_schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
        tool_spec = {
            "name": name,
            "description": description,
            "inputSchema": {"json": input_schema},
        }
        if tool.get("outputSchema"):
            tool_spec["outputSchema"] = {"json": tool.get("outputSchema")}

        tool_spec = normalize_tool_spec(tool_spec)

        # Create tool function factory (closure to capture tool_name)
        def _make_tool_func(tool_name: str):
            """
            Factory function to create tool execution wrapper.
            
            Args:
                tool_name: Name of the MCP tool to call
                
            Returns:
                Function that executes the tool via Gateway
            """
            def _tool_func(tool_use=None, **_invocation_state):
                """
                Execute MCP tool via Gateway JSON-RPC call.
                
                Args:
                    tool_use: Tool invocation details (input, toolUseId)
                    **_invocation_state: Additional state passed by the agent framework
                    
                Returns:
                    dict: Tool result with status, content, and toolUseId
                """
                # Extract arguments from tool_use
                arguments = {}
                tool_use_id = None
                if isinstance(tool_use, dict):
                    arguments = tool_use.get("input") or {}
                    tool_use_id = tool_use.get("toolUseId")
                
                # Global declarations (must be before any use of these variables)
                global _current_tools_used
                global OAUTH_FORCE_AUTH
                
                # Get user email for logging
                user_email = _get_user_email() or "unknown-user"
                
                # Log tool invocation request
                logger.info("%s requested to invoke %s tool.", user_email, tool_name)
                logger.debug("Tool arguments: %s", arguments)
                
                # Track tools used in this request
                _current_tools_used.append(tool_name)
                
                try:
                    # Build Gateway request
                    params = {
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    # Add OAuth configuration if callback server is configured
                    if OAUTH_CALLBACK_SERVER_URL:
                        oauth_config = {}
                        
                        # Generate CSRF token for OAuth flow
                        custom_state = secrets.token_urlsafe(32)
                        setattr(_request_local, "custom_state", custom_state)
                        logger.info("Generated CSRF token for OAuth flow: %s...", custom_state[:10])
                        
                        # Add return URL for OAuth redirects
                        callback_url = OAUTH_CALLBACK_SERVER_URL.rstrip('/') + '/oauth2/callback?state=' + custom_state
                        logger.debug("callback_url: %s...", callback_url)
                        oauth_config["returnUrl"] = callback_url
                        
                        # Force authentication if enabled
                        if OAUTH_FORCE_AUTH:
                            oauth_config["forceAuthentication"] = True
                        else:
                            oauth_config["forceAuthentication"] = False
                        
                        # CRITICAL: Store user token IMMEDIATELY with custom_state as key
                        # This must happen BEFORE the Gateway call, so the token is available
                        # when the callback occurs
                        user_token = _gateway_active_auth_header
                        if user_token:
                            user_token_clean = user_token.replace("Bearer ", "").replace("bearer ", "").strip()
                            logger.info("Proactively storing user token with state: %s...", custom_state[:10])
                            try:
                                _store_token_in_callback_server(
                                    user_token=user_token_clean,
                                    custom_state=custom_state
                                )
                            except Exception as store_exc:
                                logger.warning("Failed to store token in callback server: %s. "
                                             "OAuth flow may not complete successfully.", store_exc)
                        else:
                            logger.warning("No user token available to store for OAuth flow")
                        
                        logger.debug("oauth_config: %s", oauth_config)

                        params["_meta"] = {
                            "aws.bedrock-agentcore.gateway/credentialProviderConfiguration": {
                                "oauthCredentialProvider": oauth_config
                            }
                        }
                        
                        logger.debug("OAuth configuration: returnUrl=%s, forceAuth=%s", 
                                   callback_url, OAUTH_FORCE_AUTH)

                    logger.debug("Triggering tool execution for tool: %s", tool_name)
                    logger.debug("Tool call params: %s", params)

                    result = _gateway_jsonrpc(method="tools/call", params=params)
                    logger.debug("Gateway JSON-RPC call completed for tool: %s", tool_name)
                    logger.info("Tool call raw result keys: %s", list(result.keys()) if isinstance(result, dict) else type(result))
                    if isinstance(result, dict) and "error" in result:
                        logger.info("Tool call returned error: %s", json.dumps(result["error"])[:500])
                    
                    # Reset force auth after successful call
                    if OAUTH_FORCE_AUTH:
                        OAUTH_FORCE_AUTH = False
                        logger.info("Force re-auth reset after tool call")
                    
                except Exception as exc:
                    logger.error("Tool execution failed: %s, error=%s", tool_name, exc, exc_info=True)
                    return {
                        "status": "error",
                        "toolUseId": tool_use_id,
                        "content": [{"text": f"Gateway call failed: {exc}"}],
                    }

                # Handle error responses (may contain OAuth URL or permission errors)
                if isinstance(result, dict) and "error" in result:
                    error_info = result["error"]
                    error_message = str(error_info)
                    
                    # Check if this is a permission/authorization error
                    is_permission_error = any(keyword in error_message.lower() for keyword in 
                                             ["permission", "unauthorized", "forbidden", "access denied", "not allowed"])
                    
                    if is_permission_error:
                        logger.warning("%s was blocked from invoking %s tool.", user_email, tool_name)
                    else:
                        logger.warning("Tool returned error: %s, error=%s", tool_name, error_info)
                    
                    auth_url = _extract_auth_url(error_info)
                    if auth_url:
                        logger.info("OAuth authentication required for tool: %s, auth_url=%s", tool_name, auth_url)
                        _set_request_auth_url(auth_url)
                    
                    return {
                        "status": "error",
                        "toolUseId": tool_use_id,
                        "content": [{"text": json.dumps(error_info)}],
                    }

                # Handle success responses (may contain OAuth URL)
                payload = result.get("result") if isinstance(result, dict) else result
                logger.info("Tool success payload (first 500 chars): %s", str(payload)[:500])
                
                # Log successful tool invocation
                logger.info("%s successfully invoked %s tool.", user_email, tool_name)
                
                auth_url = _extract_auth_url(payload)
                if auth_url:
                    logger.info("OAuth URL found in tool response: %s", auth_url)
                    _set_request_auth_url(auth_url)
                
                logger.debug("Tool result: %s", payload)
                return {
                    "status": "success",
                    "toolUseId": tool_use_id,
                    "content": [{"text": json.dumps(payload)}],
                }

            return _tool_func

        # Create and register tool
        tool_func = _make_tool_func(name)
        agent.tool_registry.register_tool(PythonAgentTool(name, tool_spec, tool_func))
        registered_count += 1
    
    logger.info("Successfully registered %d MCP tools", registered_count)


def _ensure_gateway_tools_loaded():
    """
    Ensure MCP tools are loaded from Gateway (idempotent).
    
    Process:
    1. Check if tools already loaded (skip if so)
    2. Call Gateway "tools/list" to discover available tools
    3. Register all tools with the agent
    
    Thread-safe: Uses lock to prevent duplicate loading
    
    Side effects:
        Sets _gateway_tools_loaded flag
        Populates agent tool registry
    """
    global _gateway_tools_loaded
    if not GATEWAY_TOOLS_ENABLED:
        logger.info("Gateway tools are disabled")
        return
    if _gateway_tools_loaded:
        logger.debug("Gateway tools already loaded")
        return
    
    with _gateway_tools_lock:
        if _gateway_tools_loaded:
            return
        
        logger.info("Loading MCP tools from Gateway")
        try:
            # Discover tools from Gateway
            response = _gateway_jsonrpc(method="tools/list", params={})
            tools = (response.get("result") or {}).get("tools") or []
            
            if not tools:
                logger.warning("No MCP tools returned from Gateway")
            
            _register_gateway_tools(tools)
            tool_names = [tool.get("name") for tool in tools if tool.get("name")]
            logger.info("Registered MCP tools: %s", ", ".join(tool_names) if tool_names else "(none)")
            _gateway_tools_loaded = True
        except Exception as exc:
            logger.error("Failed to load Gateway tools: %s", exc, exc_info=True)
            raise


# ============================================================================
# Agent Initialization
# ============================================================================

_agent_instance = None
_agent_lock = threading.Lock()


def _get_agent():
    """
    Get or create the Strands Agent instance (singleton pattern).
    
    The agent is configured with:
    - Bedrock model (Claude Sonnet 4.5)
    - Temperature setting
    - AWS region
    
    Returns:
        Agent: Initialized Strands Agent instance
        
    Thread-safe: Uses double-checked locking pattern
    """
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance
    
    with _agent_lock:
        if _agent_instance is not None:
            return _agent_instance
        
        logger.info("Initializing Strands Agent with model: %s", MODEL_ID)
        try:
            _agent_instance = Agent(
                model=BedrockModel(
                    model_id=MODEL_ID,
                    region_name=AWS_REGION,
                    temperature=TEMPERATURE,
                ),
                tools=[current_time],  # Calendar tool for resolving relative date references
                system_prompt=_get_standard_system_prompt(),
            )
            logger.info("Successfully initialized Strands Agent with a system prompt")
            return _agent_instance
        except Exception as exc:
            logger.error("Failed to initialize Strands Agent: %s", exc, exc_info=True)
            raise


def _get_standard_system_prompt():
    system_prompt = """
        You are a helpful, polite, and knowledgeable expert of order 
        and inventory management operations. Your job is to answer 
        general questions about best practices around your domain of 
        expertize. You can use required tools that are at your 
        disposal as and when required. You can access the tools if 
        the end user has required permissions to do so. Operate with 
        the following guidelines in mind.

        <guidelines>
        - When you need to create orders, make sure you have the values 
        of the following attributes from the user: 
            * item_name: String
            * order_date: yyyy-mm-dd
            * qty: integer
        - When you need to create orders, you use the following attribute 
        values as default if not explicitly provided the user
            * order_id: "ord-<9-digit-unique-number>"
            * status: "pending"
        - When you update an order, get the order_id value from the user 
        if not provided
        - When you update an order for its status, only use one of the 
        following status values
            * pending
            * in-process
            * completed
            * cancelled
        - When you update an order for its order_date, only use yyyy-mm-dd  
        date format to update the value
        - When you update an order for its qty, only use a positive integer 
        value
        - Always confirm the changes with the user that you are planning to 
        do using a tool
        - Always list the orders in a tabular format
        - Always use the calendar tool reference the time in the user inputs - 
        e.g. Use the calendar tool for the references like today, tomorrow, 
        yesterday, one week from now, etc.

        - Do not entertain any requests from the user that are not related to 
        either order or inventory management domains.
        - Never update or create more than one order at a time.
        - Never provide order data out of memory as the user might not have 
        required permissions to see the data. Always invoke tools for any 
        data related query. 
        - Never assume things unless there are genuine typos in the request 
        that you can understand. Otherwise, ask the user to clarify the request 
        again. 
        </guidelines>
    """
    return system_prompt

# ============================================================================
# AgentCore Entrypoints
# ============================================================================


@app.entrypoint
def invoke(payload, context):
    """
    HTTP entrypoint for synchronous agent invocations.
    
    Called by agent_proxy.py Lambda when clients send HTTP requests.
    
    Flow:
    1. Initialize authentication from request context
    2. Load MCP tools from Gateway
    3. Process prompt with Strands agent
    4. Extract and return response with optional OAuth URL
    
    Args:
        payload: Request body with structure:
            {
                "prompt": "User's natural language request",
                "system": "Optional system prompt"
            }
        context: AgentCore request context with headers
        
    Returns:
        dict: Response with structure:
            {
                "result": "Agent's response text",
                "auth_url": "OAuth URL if authentication required (optional)"
            }
    """
    logger.info("HTTP invocation started")
    logger.info("=== DIAGNOSTIC LOGGING START ===")
    
    # Reset per-request state
    global _current_tools_used
    _current_tools_used.clear()
    _set_request_auth_url(None)

    # Auto-recall memory on first invocation (new microVM)
    global _memory_recalled
    if not _memory_recalled and MEMORY_ID:
        actor_email = None  # Will be set after token parsing below
    
    try:
        # Reset request-scoped state
        _set_request_auth_url(None)
        _set_user_email(None)
        
        # DIAGNOSTIC: Log context and payload structure
        logger.info("DIAGNOSTIC: Context object type: %s", type(context))
        logger.info("DIAGNOSTIC: Context has request_headers attribute: %s", hasattr(context, "request_headers") if context else False)
        if context and hasattr(context, "request_headers"):
            headers = context.request_headers
            logger.info("DIAGNOSTIC: request_headers type: %s", type(headers))
            if headers:
                logger.info("DIAGNOSTIC: request_headers keys: %s", list(headers.keys()))
                auth_header = headers.get("Authorization") or headers.get("authorization")
                if auth_header:
                    logger.info("DIAGNOSTIC: Authorization header found in context (first 20 chars): %s...", auth_header[:20])
                else:
                    logger.info("DIAGNOSTIC: No Authorization header found in context.request_headers")
            else:
                logger.info("DIAGNOSTIC: request_headers is None")
        else:
            logger.info("DIAGNOSTIC: Context is None or has no request_headers attribute")
        
        logger.info("DIAGNOSTIC: Payload type: %s", type(payload))
        logger.info("DIAGNOSTIC: Payload keys: %s", list(payload.keys()) if payload else "None")
        
        # Extract auth token from payload if present
        auth_token = (payload or {}).get("auth_token", "").strip()
        logger.info("DIAGNOSTIC: auth_token from payload: %s", "FOUND (first 20 chars): " + auth_token[:20] + "..." if auth_token else "NOT FOUND")
        if auth_token:
            logger.info("DIAGNOSTIC: User auth token found in payload - ENTERING TOKEN PROCESSING BLOCK")
            logger.debug("DIAGNOSTIC: Auth token (first 20 chars): %s...", auth_token[:20])
            
            # Extract user email from token
            logger.info("DIAGNOSTIC: Attempting to extract user email from token")
            user_email = _extract_email_from_token(auth_token)
            if user_email:
                _set_user_email(user_email)
                logger.info("DIAGNOSTIC: User email extracted from token: %s", user_email)
            else:
                logger.error("DIAGNOSTIC: Could not extract email from auth token - email extraction failed")
            
            # Set the token as the active auth header for Gateway requests
            global _gateway_active_auth_header
            _gateway_active_auth_header = _normalize_bearer(auth_token)
            logger.info("DIAGNOSTIC: Set gateway auth header from payload token")
            
            # CRITICAL: Proactively store user token with custom_state for OAuth flows
            # The custom_state is generated before tool calls and used as DynamoDB key
            # This enables the callback server to retrieve the correct token using state parameter
            if user_email and OAUTH_CALLBACK_SERVER_URL:
                logger.info("DIAGNOSTIC: Preparing for potential OAuth flow - user_email=%s", user_email)
                # Note: custom_state will be generated when tool is called
                # Token storage happens in tool execution wrapper when OAuth is needed
                logger.info("DIAGNOSTIC: Token will be stored when OAuth flow is initiated with custom_state")
        else:
            logger.warning("DIAGNOSTIC: No auth_token in payload - SKIPPING TOKEN PROCESSING BLOCK")
            # Fallback to context headers or system OAuth token
            _set_gateway_auth_from_context(context)
            logger.info("DIAGNOSTIC: Using fallback authentication from context")
        
        # Ensure MCP tools are loaded
        logger.info("DIAGNOSTIC: About to load MCP tools")

        # Auto-recall memory on first invocation of this microVM
        _memory_loaded_this_request = None  # Track if recall happened THIS invocation
        if not _memory_recalled and MEMORY_ID:
            actor_for_recall = _get_user_email() or "anonymous"
            if actor_for_recall != "anonymous":
                try:
                    import re as _re
                    safe_actor_recall = _re.sub(r'[^a-zA-Z0-9\-_/]', '-', actor_for_recall)
                    recall_result = memory_recall(actor_for_recall)
                    if recall_result:
                        _seed_history_from_recall(recall_result)
                        logger.info("Auto-recalled memory context for %s (%d messages seeded)",
                                    safe_actor_recall, len(_conversation_history))
                        _memory_loaded_this_request = True
                    else:
                        _memory_loaded_this_request = False
                    _memory_recalled = True
                except Exception as e:
                    logger.warning("Auto-recall failed: %s", e)
                    _memory_recalled = True
                    _memory_loaded_this_request = False
        _ensure_gateway_tools_loaded()
        logger.info("DIAGNOSTIC: MCP tools loaded successfully")
        
        # Validate prompt
        prompt = (payload or {}).get("prompt", "").strip()
        if not prompt:
            logger.warning("HTTP invocation missing prompt")
            logger.info("=== DIAGNOSTIC LOGGING END (ERROR: missing prompt) ===")
            return {"error": "Missing 'prompt' in request body."}
        
        # Handle force_reauth — sets flag for next tool call to force re-authorization
        global OAUTH_FORCE_AUTH
        if prompt.lower() == "force_reauth":
            OAUTH_FORCE_AUTH = True
            logger.info("Force re-auth enabled — next tool call will force authentication")
            return {"result": "🔐 Re-authorization enabled. The next tool call will force a fresh OAuth flow."}
        
        logger.info("Processing prompt (length=%d)", len(prompt))
        logger.debug("Prompt: %s", prompt[:200] + "..." if len(prompt) > 200 else prompt)

        # Get agent and process prompt
        system = (payload or {}).get("system", "").strip()
        if system:
            logger.debug("Using system prompt (length=%d)", len(system))
        
        agent = _get_agent()
        
        # Inject conversation history for context continuity
        agent.messages = list(_conversation_history)
        
        logger.info("Invoking agent with prompt (history: %d messages)", len(_conversation_history))
        if system:
            response = agent(prompt, system=system)
        else:
            response = agent(prompt)
        
        logger.info("Agent invocation completed")

        # Extract text from Strands response
        # Strands returns an object with .message that may be structured content.
        result = response.message
        if isinstance(result, dict) and "content" in result:
            parts = []
            for item in result.get("content") or []:
                text = item.get("text") if isinstance(item, dict) else str(item)
                if text:
                    parts.append(text)
            result = "\n".join(parts) if parts else str(result)
        
        # Append this turn to conversation history (text only, no tool blocks)
        _conversation_history.append({"role": "user", "content": [{"text": prompt}]})
        _conversation_history.append({"role": "assistant", "content": [{"text": str(result)[:2000]}]})
        
        logger.debug("Agent response (length=%d)", len(str(result)))
        
        # Check for OAuth authorization URL
        # Prefer auth_url captured during tool calls; fall back to parsing the model text.
        auth_url = _get_request_auth_url() or _extract_auth_url(result)
        response_payload = {"result": result}
        
        # Include tools used in this invocation
        tools_used = _current_tools_used
        tools_str = " | ".join(tools_used) if tools_used else "none"
        
        # Prepend metadata to result (region + tools)
        meta_line = f"🔧 Tools Used: {tools_str} | Region: {AWS_REGION}"
        if isinstance(result, str):
            result = meta_line + "\n\n" + result
        response_payload = {"result": result}
        
        # Include memory status only on the first invocation of this microVM
        if _memory_loaded_this_request is not None:
            response_payload["memory_loaded"] = _memory_loaded_this_request
        
        if auth_url:
            logger.info("Including OAuth URL in response: %s", auth_url)
            response_payload["auth_url"] = auth_url
        
        logger.info("HTTP invocation successful")
        
        # Save turn to memory (async, non-blocking)
        if MEMORY_ID and not auth_url:
            actor_for_save = _get_user_email() or "anonymous"
            session_for_save = getattr(_request_local, "session_id", "") or "default"
            # Use the raw result (without metadata prefix) for memory
            raw_result = str(response.message) if hasattr(response, 'message') else str(result)
            if actor_for_save != "anonymous":
                memory_save_turn(actor_for_save, session_for_save, prompt, raw_result[:2000])
        
        logger.info("=== DIAGNOSTIC LOGGING END (SUCCESS) ===")
        return response_payload
        
    except Exception as exc:
        logger.error("HTTP invocation failed: %s", exc, exc_info=True)
        logger.info("=== DIAGNOSTIC LOGGING END (EXCEPTION) ===")
        return {"error": f"Agent invocation failed: {str(exc)}"}


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # Run the AgentCore application
    # This starts the runtime server that handles HTTP requests
    logger.info("Starting AgentCore application")
    try:
        app.run()
    except Exception as exc:
        logger.error("AgentCore application failed to start: %s", exc, exc_info=True)
        raise
