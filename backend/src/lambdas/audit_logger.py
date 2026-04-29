"""
Audit Logger for Orders API Authorization.

This module provides comprehensive audit logging for all authorization
attempts, including successful and failed access attempts, with structured
logging to CloudWatch Logs.
"""

import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime

# Configure logging
logger = logging.getLogger()


class AuditLogger:
    """
    Audit logger for authorization events.
    
    Logs all authorization attempts with structured data including:
    - User identity
    - Requested resource and method
    - Authorization decision
    - Timestamp
    - Request context
    """
    
    def __init__(self, log_level: str = "INFO"):
        """
        Initialize audit logger.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    def log_authorization_attempt(
        self,
        user_email: str,
        method: str,
        resource: str,
        decision: str,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an authorization attempt.
        
        Args:
            user_email: Email of the user attempting access
            method: HTTP method (GET, POST, PUT, DELETE)
            resource: Resource path or ARN
            decision: Authorization decision (ALLOW or DENY)
            reason: Optional reason for the decision
            request_id: Optional request ID for correlation
            source_ip: Optional source IP address
            user_agent: Optional user agent string
            additional_context: Optional additional context data
        """
        log_entry = self._create_log_entry(
            event_type="AUTHORIZATION_ATTEMPT",
            user_email=user_email,
            method=method,
            resource=resource,
            decision=decision,
            reason=reason,
            request_id=request_id,
            source_ip=source_ip,
            user_agent=user_agent,
            additional_context=additional_context
        )
        
        # Log at appropriate level based on decision
        if decision == "ALLOW":
            self.logger.info(json.dumps(log_entry))
        else:
            self.logger.warning(json.dumps(log_entry))
    
    def log_authentication_success(
        self,
        user_email: str,
        request_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log successful authentication.
        
        Args:
            user_email: Email of the authenticated user
            request_id: Optional request ID for correlation
            source_ip: Optional source IP address
            additional_context: Optional additional context data
        """
        log_entry = self._create_log_entry(
            event_type="AUTHENTICATION_SUCCESS",
            user_email=user_email,
            request_id=request_id,
            source_ip=source_ip,
            additional_context=additional_context
        )
        
        self.logger.info(json.dumps(log_entry))
    
    def log_authentication_failure(
        self,
        reason: str,
        user_email: Optional[str] = None,
        request_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log failed authentication attempt.
        
        Args:
            reason: Reason for authentication failure
            user_email: Optional email (may not be available for failed auth)
            request_id: Optional request ID for correlation
            source_ip: Optional source IP address
            additional_context: Optional additional context data
        """
        log_entry = self._create_log_entry(
            event_type="AUTHENTICATION_FAILURE",
            user_email=user_email or "UNKNOWN",
            reason=reason,
            request_id=request_id,
            source_ip=source_ip,
            additional_context=additional_context
        )
        
        self.logger.warning(json.dumps(log_entry))
    
    def log_authorization_error(
        self,
        error_message: str,
        user_email: Optional[str] = None,
        method: Optional[str] = None,
        resource: Optional[str] = None,
        request_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log authorization error.
        
        Args:
            error_message: Error message
            user_email: Optional user email
            method: Optional HTTP method
            resource: Optional resource
            request_id: Optional request ID for correlation
            additional_context: Optional additional context data
        """
        log_entry = self._create_log_entry(
            event_type="AUTHORIZATION_ERROR",
            user_email=user_email or "UNKNOWN",
            method=method,
            resource=resource,
            error=error_message,
            request_id=request_id,
            additional_context=additional_context
        )
        
        self.logger.error(json.dumps(log_entry))
    
    def _create_log_entry(
        self,
        event_type: str,
        user_email: Optional[str] = None,
        method: Optional[str] = None,
        resource: Optional[str] = None,
        decision: Optional[str] = None,
        reason: Optional[str] = None,
        error: Optional[str] = None,
        request_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create structured log entry.
        
        Args:
            event_type: Type of event being logged
            user_email: User email (filtered for sensitive data)
            method: HTTP method
            resource: Resource path
            decision: Authorization decision
            reason: Reason for decision
            error: Error message
            request_id: Request ID
            source_ip: Source IP address
            user_agent: User agent string
            additional_context: Additional context data
            
        Returns:
            Structured log entry dictionary
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "service": "orders-api-authorizer"
        }
        
        # Add user information (filtered)
        if user_email:
            log_entry["user"] = {
                "email": self._filter_sensitive_data(user_email)
            }
        
        # Add request information
        if method:
            log_entry["method"] = method
        
        if resource:
            log_entry["resource"] = resource
        
        # Add decision information
        if decision:
            log_entry["decision"] = decision
        
        if reason:
            log_entry["reason"] = reason
        
        if error:
            log_entry["error"] = error
        
        # Add request context
        if request_id:
            log_entry["request_id"] = request_id
        
        if source_ip:
            log_entry["source_ip"] = self._filter_ip_address(source_ip)
        
        if user_agent:
            log_entry["user_agent"] = user_agent[:200]  # Truncate long user agents
        
        # Add additional context
        if additional_context:
            log_entry["context"] = self._filter_context(additional_context)
        
        return log_entry
    
    def _filter_sensitive_data(self, data: str) -> str:
        """
        Filter sensitive data from log entries.
        
        For email addresses, we keep the domain but partially mask the username
        to maintain privacy while allowing for debugging.
        
        Args:
            data: Data to filter
            
        Returns:
            Filtered data
        """
        if not data or "@" not in data:
            return data
        
        # For email addresses, keep first 3 chars and domain
        parts = data.split("@")
        if len(parts) == 2:
            username = parts[0]
            domain = parts[1]
            
            if len(username) <= 3:
                masked_username = username[0] + "*" * (len(username) - 1)
            else:
                masked_username = username[:3] + "*" * (len(username) - 3)
            
            return f"{masked_username}@{domain}"
        
        return data
    
    def _filter_ip_address(self, ip: str) -> str:
        """
        Filter IP address for privacy.
        
        Masks the last octet of IPv4 addresses.
        
        Args:
            ip: IP address
            
        Returns:
            Filtered IP address
        """
        if not ip:
            return ip
        
        # For IPv4, mask last octet
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
        
        # For IPv6 or other formats, return as-is
        return ip
    
    def _filter_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive data from context dictionary.
        
        Removes or masks sensitive fields like tokens, passwords, etc.
        
        Args:
            context: Context dictionary
            
        Returns:
            Filtered context dictionary
        """
        filtered = {}
        sensitive_keys = {
            "token", "password", "secret", "key", "authorization",
            "api_key", "access_token", "refresh_token"
        }
        
        for key, value in context.items():
            # Check if key contains sensitive terms
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                filtered[key] = "[REDACTED]"
            elif isinstance(value, dict):
                filtered[key] = self._filter_context(value)
            elif isinstance(value, str) and len(value) > 1000:
                # Truncate very long strings
                filtered[key] = value[:1000] + "...[TRUNCATED]"
            else:
                filtered[key] = value
        
        return filtered


# Module-level functions for convenience
_default_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get the default audit logger instance.
    
    Returns:
        AuditLogger instance
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = AuditLogger()
    return _default_logger


def log_authorization_attempt(
    user_email: str,
    method: str,
    resource: str,
    decision: str,
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an authorization attempt using the default logger.
    
    Args:
        user_email: Email of the user attempting access
        method: HTTP method (GET, POST, PUT, DELETE)
        resource: Resource path or ARN
        decision: Authorization decision (ALLOW or DENY)
        reason: Optional reason for the decision
        request_id: Optional request ID for correlation
        source_ip: Optional source IP address
        user_agent: Optional user agent string
        additional_context: Optional additional context data
    """
    get_audit_logger().log_authorization_attempt(
        user_email=user_email,
        method=method,
        resource=resource,
        decision=decision,
        reason=reason,
        request_id=request_id,
        source_ip=source_ip,
        user_agent=user_agent,
        additional_context=additional_context
    )


def log_authentication_success(
    user_email: str,
    request_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log successful authentication using the default logger.
    
    Args:
        user_email: Email of the authenticated user
        request_id: Optional request ID for correlation
        source_ip: Optional source IP address
        additional_context: Optional additional context data
    """
    get_audit_logger().log_authentication_success(
        user_email=user_email,
        request_id=request_id,
        source_ip=source_ip,
        additional_context=additional_context
    )


def log_authentication_failure(
    reason: str,
    user_email: Optional[str] = None,
    request_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log failed authentication attempt using the default logger.
    
    Args:
        reason: Reason for authentication failure
        user_email: Optional email (may not be available for failed auth)
        request_id: Optional request ID for correlation
        source_ip: Optional source IP address
        additional_context: Optional additional context data
    """
    get_audit_logger().log_authentication_failure(
        reason=reason,
        user_email=user_email,
        request_id=request_id,
        source_ip=source_ip,
        additional_context=additional_context
    )


def log_authorization_error(
    error_message: str,
    user_email: Optional[str] = None,
    method: Optional[str] = None,
    resource: Optional[str] = None,
    request_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log authorization error using the default logger.
    
    Args:
        error_message: Error message
        user_email: Optional user email
        method: Optional HTTP method
        resource: Optional resource
        request_id: Optional request ID for correlation
        additional_context: Optional additional context data
    """
    get_audit_logger().log_authorization_error(
        error_message=error_message,
        user_email=user_email,
        method=method,
        resource=resource,
        request_id=request_id,
        additional_context=additional_context
    )
