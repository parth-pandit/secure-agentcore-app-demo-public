"""
Property-based tests for audit logging.

Property 5: All Access Attempts Logged
- Every authorization attempt must be logged
- Logs must contain user identity, resource, method, and decision
- Logs must be immutable and tamper-evident
- Validates Requirements: 4.1, 4.2, 4.3, 4.4
"""

import unittest
import json
import logging
from io import StringIO
import sys
sys.path.insert(0, 'backend/src/lambdas')

from audit_logger import AuditLogger, get_audit_logger

# Try to import hypothesis for property-based testing
try:
    from hypothesis import given, strategies as st, settings
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Warning: hypothesis not available, property tests will be skipped")
    # Create dummy decorators
    def given(*args, **kwargs):
        def decorator(func):
            return lambda self: self.skipTest("Hypothesis not installed")
        return decorator
    
    def settings(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    class DummyStrategy:
        def filter(self, *args, **kwargs):
            return self
    
    class st:
        @staticmethod
        def text(**kwargs):
            return DummyStrategy()
        
        @staticmethod
        def sampled_from(items):
            return DummyStrategy()
        
        @staticmethod
        def dictionaries(keys, values, **kwargs):
            return DummyStrategy()


class TestAuditLoggingProperties(unittest.TestCase):
    """Property-based tests for audit logging."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a string buffer to capture log output
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        # Create audit logger with custom handler
        self.audit_logger = AuditLogger()
        self.audit_logger.logger.handlers = []
        self.audit_logger.logger.addHandler(self.handler)
        self.audit_logger.logger.setLevel(logging.DEBUG)
        self.audit_logger.logger.propagate = False
        
        # Clear buffer to ensure clean state
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.audit_logger.logger.removeHandler(self.handler)
        self.handler.close()
    
    def get_log_entries(self):
        """Get all log entries from the buffer."""
        log_output = self.log_buffer.getvalue()
        entries = []
        for line in log_output.strip().split('\n'):
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    
    @given(
        user_email=st.emails(),
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=100),
        decision=st.sampled_from(['ALLOW', 'DENY'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_all_authorization_attempts_logged(
        self, user_email, method, resource, decision
    ):
        """
        Property: Every authorization attempt must be logged.
        
        For any authorization attempt, there must be a corresponding log entry
        with all required fields.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Clear buffer before test
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
        
        # Log authorization attempt
        self.audit_logger.log_authorization_attempt(
            user_email=user_email,
            method=method,
            resource=resource,
            decision=decision
        )
        
        # Verify log entry was created
        entries = self.get_log_entries()
        self.assertEqual(len(entries), 1, "Exactly one log entry should be created")
        
        entry = entries[0]
        
        # Verify required fields are present
        self.assertIn('timestamp', entry, "Log must contain timestamp")
        self.assertIn('event_type', entry, "Log must contain event type")
        self.assertIn('user', entry, "Log must contain user information")
        self.assertIn('method', entry, "Log must contain HTTP method")
        self.assertIn('resource', entry, "Log must contain resource")
        self.assertIn('decision', entry, "Log must contain decision")
        
        # Verify field values
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ATTEMPT')
        self.assertEqual(entry['method'], method)
        self.assertEqual(entry['resource'], resource)
        self.assertEqual(entry['decision'], decision)
    
    @given(
        user_email=st.emails()
    )
    @settings(max_examples=50, deadline=None)
    def test_property_authentication_success_logged(self, user_email):
        """
        Property: Every successful authentication must be logged.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Clear buffer before test
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
        
        # Log authentication success
        self.audit_logger.log_authentication_success(user_email=user_email)
        
        # Verify log entry was created
        entries = self.get_log_entries()
        self.assertEqual(len(entries), 1)
        
        entry = entries[0]
        self.assertEqual(entry['event_type'], 'AUTHENTICATION_SUCCESS')
        self.assertIn('user', entry)
    
    @given(
        reason=st.text(min_size=5, max_size=100)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_authentication_failure_logged(self, reason):
        """
        Property: Every failed authentication must be logged.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Clear buffer before test
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
        
        # Log authentication failure
        self.audit_logger.log_authentication_failure(reason=reason)
        
        # Verify log entry was created
        entries = self.get_log_entries()
        self.assertEqual(len(entries), 1)
        
        entry = entries[0]
        self.assertEqual(entry['event_type'], 'AUTHENTICATION_FAILURE')
        self.assertIn('reason', entry)
    
    @given(
        error_message=st.text(min_size=5, max_size=100)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_authorization_error_logged(self, error_message):
        """
        Property: Every authorization error must be logged.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Clear buffer before test
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
        
        # Log authorization error
        self.audit_logger.log_authorization_error(error_message=error_message)
        
        # Verify log entry was created
        entries = self.get_log_entries()
        self.assertEqual(len(entries), 1)
        
        entry = entries[0]
        self.assertEqual(entry['event_type'], 'AUTHORIZATION_ERROR')
        self.assertIn('error', entry)
    
    @given(
        user_email=st.emails(),
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=100),
        decision=st.sampled_from(['ALLOW', 'DENY'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_logs_contain_timestamp(
        self, user_email, method, resource, decision
    ):
        """
        Property: All log entries must contain a valid timestamp.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Clear buffer before test
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
        
        # Log authorization attempt
        self.audit_logger.log_authorization_attempt(
            user_email=user_email,
            method=method,
            resource=resource,
            decision=decision
        )
        
        # Verify timestamp is present and valid
        entries = self.get_log_entries()
        entry = entries[0]
        
        self.assertIn('timestamp', entry)
        # Timestamp should be in ISO format
        self.assertRegex(entry['timestamp'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')
    
    @given(
        user_email=st.emails(),
        method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE']),
        resource=st.text(min_size=1, max_size=100),
        decision=st.sampled_from(['ALLOW', 'DENY'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_logs_are_structured_json(
        self, user_email, method, resource, decision
    ):
        """
        Property: All log entries must be valid JSON.
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")
        
        # Clear buffer before test
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
        
        # Log authorization attempt
        self.audit_logger.log_authorization_attempt(
            user_email=user_email,
            method=method,
            resource=resource,
            decision=decision
        )
        
        # Verify log output is valid JSON
        log_output = self.log_buffer.getvalue().strip()
        lines = log_output.split('\n')
        
        for line in lines:
            if line:
                # Should not raise JSONDecodeError
                entry = json.loads(line)
                self.assertIsInstance(entry, dict)


class TestSensitiveDataFiltering(unittest.TestCase):
    """Test sensitive data filtering in audit logs."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.log_buffer = StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(logging.DEBUG)
        
        self.audit_logger = AuditLogger()
        self.audit_logger.logger.handlers = []
        self.audit_logger.logger.addHandler(self.handler)
        self.audit_logger.logger.setLevel(logging.DEBUG)
        self.audit_logger.logger.propagate = False
        
        # Clear buffer to ensure clean state
        self.log_buffer.truncate(0)
        self.log_buffer.seek(0)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.audit_logger.logger.removeHandler(self.handler)
        self.handler.close()
        self.log_buffer.close()
    
    def get_log_entries(self):
        """Get all log entries from the buffer."""
        log_output = self.log_buffer.getvalue()
        entries = []
        for line in log_output.strip().split('\n'):
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    
    def test_email_addresses_are_filtered(self):
        """Test that email addresses are partially masked."""
        self.audit_logger.log_authorization_attempt(
            user_email="testuser@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW"
        )
        
        entries = self.get_log_entries()
        entry = entries[0]
        
        # Email should be masked
        user_email = entry['user']['email']
        self.assertNotEqual(user_email, "testuser@example.com")
        self.assertIn("@example.com", user_email)
        self.assertIn("*", user_email)
    
    def test_ip_addresses_are_filtered(self):
        """Test that IP addresses are partially masked."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            source_ip="192.168.1.100"
        )
        
        entries = self.get_log_entries()
        entry = entries[0]
        
        # IP should be masked
        source_ip = entry['source_ip']
        self.assertNotEqual(source_ip, "192.168.1.100")
        self.assertIn("192.168.1", source_ip)
        self.assertIn("xxx", source_ip)
    
    def test_sensitive_context_fields_are_redacted(self):
        """Test that sensitive fields in context are redacted."""
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            additional_context={
                "token": "secret-token-value",
                "password": "secret-password",
                "api_key": "secret-api-key",
                "safe_field": "safe-value"
            }
        )
        
        entries = self.get_log_entries()
        entry = entries[0]
        
        # Sensitive fields should be redacted
        context = entry['context']
        self.assertEqual(context['token'], '[REDACTED]')
        self.assertEqual(context['password'], '[REDACTED]')
        self.assertEqual(context['api_key'], '[REDACTED]')
        self.assertEqual(context['safe_field'], 'safe-value')
    
    def test_long_strings_are_truncated(self):
        """Test that very long strings are truncated."""
        long_string = "x" * 2000
        
        self.audit_logger.log_authorization_attempt(
            user_email="user@example.com",
            method="GET",
            resource="/orders",
            decision="ALLOW",
            additional_context={
                "long_field": long_string
            }
        )
        
        entries = self.get_log_entries()
        entry = entries[0]
        
        # Long string should be truncated
        context = entry['context']
        self.assertLess(len(context['long_field']), 1100)
        self.assertIn('[TRUNCATED]', context['long_field'])


if __name__ == '__main__':
    unittest.main()
