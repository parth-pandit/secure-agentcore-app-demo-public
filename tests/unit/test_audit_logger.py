"""
Unit tests for audit logger module.

Tests log entry formatting, different log types, sensitive data filtering,
and CloudWatch integration.
"""

import unittest
import json
import logging
from io import StringIO
from datetime import datetime
import sys
sys.path.insert(0, 'backend/src/lambdas')

from audit_logger import (
    AuditLogger,
    get_audit_logger,
    log_authorization_attempt,
    log_authentication_success,
    log_authentication_failure,
    log_authorization_error
)


class TestAuditLoggerInitialization(unittest.TestCase):
    """Test audit logger initialization."""
    
    def test_create_audit_logger_default_level(self):
        """Test creating audit logger with default log level."""
        logger = AuditLogger()
        self.assertIsNotNone(logger)
        self.assertEqual(logger.logger.level, logging.INFO)
    
    def test_create_audit_logger_custom_level(self):
        """Test creating audit logger with custom log level."""
        logger = AuditLogger(log_level="DEBUG")
        self.assertEqual(logger.logger.level, logging.DEBUG)
    
    def test_create_audit_logger_warning_level(self):
        """Test creating audit logger with WARNING level."""
        logger = AuditLogger(log_level="WARNING")
        self.assertEqual(logger.logger.level, logging.WARNING)
    
    def test_get_default_audit_logger(self):
        """Test getting default audit logger instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        # Should return the same instance
        self.assertIs(logger1, logger2)


class TestLogEntryFormatting(unittest.TestCase):
    """Test log entry formatting."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        self.audit_logger = AuditLogger()
        self.audit_logger.logger.handlers = []
        self.audit_logger.logger.addHandler(self.handler)
        self.audit_logger.logger.setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.audit_logger.logger.removeHandler(self.handler)
        self.handler.close()
    
    def get_log_entry(self):
        """Get the first log entry from the buffer."""
        log_output = self.log_buffer.getvalue().strip()
        if not log_output:
            return None
        lines = log_output.split('\n')
        return json.loads(lines[0])
    
    def test_log_entry_contains_timestamp(self):
        """Test that log entries contain timestamp."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        entry = self.get_log_entry()
        self.assertIn('timestamp', entry)
        # Verify timestamp format
        self.assertRegex(entry['timestamp'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')
    
    def test_log_entry_contains_event_type(self):
        """Test that log entries contain event type."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        entry = self.get_log_entry()
        self.assertIn('event_type', entry)
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ATTEMPT')
    
    def test_log_entry_contains_service_name(self):
        """Test that log entries contain service name."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        entry = self.get_log_entry()
        self.assertIn('service', entry)
        self.assertEqual(entry['service'], 'orders-api-authorizer')
    
    def test_log_entry_is_valid_json(self):
        """Test that log entries are valid JSON."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        log_output = self.log_buffer.getvalue().strip()
        # Should not raise JSONDecodeError
        entry = json.loads(log_output)
        self.assertIsInstance(entry, dict)


class TestAuthorizationAttemptLogging(unittest.TestCase):
    """Test authorization attempt logging."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        self.audit_logger = AuditLogger()
        self.audit_logger.logger.handlers = []
        self.audit_logger.logger.addHandler(self.handler)
        self.audit_logger.logger.setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.audit_logger.logger.removeHandler(self.handler)
        self.handler.close()
    
    def get_log_entry(self):
        """Get the first log entry from the buffer."""
        log_output = self.log_buffer.getvalue().strip()
        if not log_output:
            return None
        lines = log_output.split('\n')
        return json.loads(lines[0])
    
    def test_log_authorization_allow(self):
        """Test logging successful authorization."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ATTEMPT')
        self.assertEqual(entry['method'], 'GET')
        self.assertEqual(entry['resource'], '/orders')
        self.assertEqual(entry['decision'], 'ALLOW')
    
    def test_log_authorization_deny(self):
        """Test logging denied authorization."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="POST",
            resource="/orders",
            decision="DENY",
            reason="Insufficient permissions"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['decision'], 'DENY')
        self.assertEqual(entry['reason'], 'Insufficient permissions')
    
    def test_log_authorization_with_request_id(self):
        """Test logging authorization with request ID."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            request_id="req-12345"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['request_id'], 'req-12345')
    
    def test_log_authorization_with_source_ip(self):
        """Test logging authorization with source IP."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            source_ip="192.168.1.100"
        )
        
        entry = self.get_log_entry()
        self.assertIn('source_ip', entry)
        # IP should be filtered
        self.assertIn('192.168.1', entry['source_ip'])
    
    def test_log_authorization_with_user_agent(self):
        """Test logging authorization with user agent."""
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            user_agent=user_agent
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['user_agent'], user_agent)
    
    def test_log_authorization_with_additional_context(self):
        """Test logging authorization with additional context."""
        context = {"api_version": "v1", "client_id": "client-123"}
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            additional_context=context
        )
        
        entry = self.get_log_entry()
        self.assertIn('context', entry)
        self.assertEqual(entry['context']['api_version'], 'v1')
        self.assertEqual(entry['context']['client_id'], 'client-123')


class TestAuthenticationLogging(unittest.TestCase):
    """Test authentication logging."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        self.audit_logger = AuditLogger()
        self.audit_logger.logger.handlers = []
        self.audit_logger.logger.addHandler(self.handler)
        self.audit_logger.logger.setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.audit_logger.logger.removeHandler(self.handler)
        self.handler.close()
    
    def get_log_entry(self):
        """Get the first log entry from the buffer."""
        log_output = self.log_buffer.getvalue().strip()
        if not log_output:
            return None
        lines = log_output.split('\n')
        return json.loads(lines[0])
    
    def test_log_authentication_success(self):
        """Test logging successful authentication."""
        self.audit_logger.log_authentication_success(
            user_email="user@example.com"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHENTICATION_SUCCESS')
        self.assertIn('user', entry)
    
    def test_log_authentication_failure(self):
        """Test logging failed authentication."""
        self.audit_logger.log_authentication_failure(
            reason="Invalid token"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHENTICATION_FAILURE')
        self.assertEqual(entry['reason'], 'Invalid token')
    
    def test_log_authentication_failure_with_email(self):
        """Test logging failed authentication with email."""
        self.audit_logger.log_authentication_failure(
            reason="Token expired",
            user_email="user@example.com"
        )
        
        entry = self.get_log_entry()
        self.assertIn('user', entry)
        self.assertEqual(entry['reason'], 'Token expired')


class TestAuthorizationErrorLogging(unittest.TestCase):
    """Test authorization error logging."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        self.audit_logger = AuditLogger()
        self.audit_logger.logger.handlers = []
        self.audit_logger.logger.addHandler(self.handler)
        self.audit_logger.logger.setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.audit_logger.logger.removeHandler(self.handler)
        self.handler.close()
    
    def get_log_entry(self):
        """Get the first log entry from the buffer."""
        log_output = self.log_buffer.getvalue().strip()
        if not log_output:
            return None
        lines = log_output.split('\n')
        return json.loads(lines[0])
    
    def test_log_authorization_error(self):
        """Test logging authorization error."""
        self.audit_logger.log_authorization_error(
            error_message="Configuration error"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ERROR')
        self.assertEqual(entry['error'], 'Configuration error')
    
    def test_log_authorization_error_with_context(self):
        """Test logging authorization error with full context."""
        self.audit_logger.log_authorization_error(
            error_message="Database connection failed",
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            request_id="req-12345"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['error'], 'Database connection failed')
        self.assertIn('user', entry)
        self.assertEqual(entry['method'], 'GET')
        self.assertEqual(entry['resource'], '/orders')
        self.assertEqual(entry['request_id'], 'req-12345')


class TestSensitiveDataFiltering(unittest.TestCase):
    """Test sensitive data filtering."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.audit_logger = AuditLogger()
    
    def test_filter_email_short(self):
        """Test filtering short email addresses."""
        filtered = self.audit_logger._filter_sensitive_data("ab@example.com")
        self.assertNotEqual(filtered, "ab@example.com")
        self.assertIn("@example.com", filtered)
        self.assertIn("*", filtered)
    
    def test_filter_email_long(self):
        """Test filtering long email addresses."""
        filtered = self.audit_logger._filter_sensitive_data("testuser@example.com")
        self.assertNotEqual(filtered, "testuser@example.com")
        self.assertIn("@example.com", filtered)
        self.assertIn("*", filtered)
        # First 3 characters should be preserved
        self.assertTrue(filtered.startswith("tes"))
    
    def test_filter_email_preserves_domain(self):
        """Test that email filtering preserves domain."""
        filtered = self.audit_logger._filter_sensitive_data("user@company.org")
        self.assertIn("@company.org", filtered)
    
    def test_filter_non_email_unchanged(self):
        """Test that non-email strings are unchanged."""
        text = "not an email"
        filtered = self.audit_logger._filter_sensitive_data(text)
        self.assertEqual(filtered, text)
    
    def test_filter_ipv4_address(self):
        """Test filtering IPv4 addresses."""
        filtered = self.audit_logger._filter_ip_address("192.168.1.100")
        self.assertEqual(filtered, "192.168.1.xxx")
    
    def test_filter_ipv4_different_octets(self):
        """Test filtering different IPv4 addresses."""
        filtered = self.audit_logger._filter_ip_address("10.0.0.5")
        self.assertEqual(filtered, "10.0.0.xxx")
    
    def test_filter_non_ipv4_unchanged(self):
        """Test that non-IPv4 strings are unchanged."""
        ip = "2001:0db8:85a3::8a2e:0370:7334"
        filtered = self.audit_logger._filter_ip_address(ip)
        self.assertEqual(filtered, ip)
    
    def test_filter_context_redacts_token(self):
        """Test that context filtering redacts tokens."""
        context = {"token": "secret-value", "safe": "public"}
        filtered = self.audit_logger._filter_context(context)
        self.assertEqual(filtered['token'], '[REDACTED]')
        self.assertEqual(filtered['safe'], 'public')
    
    def test_filter_context_redacts_password(self):
        """Test that context filtering redacts passwords."""
        context = {"password": "secret123"}
        filtered = self.audit_logger._filter_context(context)
        self.assertEqual(filtered['password'], '[REDACTED]')
    
    def test_filter_context_redacts_api_key(self):
        """Test that context filtering redacts API keys."""
        context = {"api_key": "key-12345", "API_KEY": "key-67890"}
        filtered = self.audit_logger._filter_context(context)
        self.assertEqual(filtered['api_key'], '[REDACTED]')
        self.assertEqual(filtered['API_KEY'], '[REDACTED]')
    
    def test_filter_context_redacts_authorization(self):
        """Test that context filtering redacts authorization headers."""
        context = {"authorization": "Bearer token123"}
        filtered = self.audit_logger._filter_context(context)
        self.assertEqual(filtered['authorization'], '[REDACTED]')
    
    def test_filter_context_nested_dict(self):
        """Test that context filtering works on nested dictionaries."""
        context = {
            "outer": {
                "token": "secret",
                "safe": "value"
            }
        }
        filtered = self.audit_logger._filter_context(context)
        self.assertEqual(filtered['outer']['token'], '[REDACTED]')
        self.assertEqual(filtered['outer']['safe'], 'value')
    
    def test_filter_context_truncates_long_strings(self):
        """Test that very long strings are truncated."""
        long_string = "x" * 2000
        context = {"long_field": long_string}
        filtered = self.audit_logger._filter_context(context)
        self.assertLess(len(filtered['long_field']), 1100)
        self.assertIn('[TRUNCATED]', filtered['long_field'])


class TestModuleLevelFunctions(unittest.TestCase):
    """Test module-level convenience functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        logger = get_audit_logger()
        logger.logger.handlers = []
        logger.logger.addHandler(self.handler)
        logger.logger.setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up test fixtures."""
        logger = get_audit_logger()
        logger.logger.removeHandler(self.handler)
        self.handler.close()
    
    def get_log_entry(self):
        """Get the first log entry from the buffer."""
        log_output = self.log_buffer.getvalue().strip()
        if not log_output:
            return None
        lines = log_output.split('\n')
        return json.loads(lines[0])
    
    def test_module_log_authorization_attempt(self):
        """Test module-level log_authorization_attempt function."""
        log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ATTEMPT')
    
    def test_module_log_authentication_success(self):
        """Test module-level log_authentication_success function."""
        log_authentication_success(user_email="user@example.com")
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHENTICATION_SUCCESS')
    
    def test_module_log_authentication_failure(self):
        """Test module-level log_authentication_failure function."""
        log_authentication_failure(reason="Invalid token")
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHENTICATION_FAILURE')
    
    def test_module_log_authorization_error(self):
        """Test module-level log_authorization_error function."""
        log_authorization_error(error_message="Configuration error")
        
        entry = self.get_log_entry()
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ERROR')


if __name__ == '__main__':
    unittest.main()
