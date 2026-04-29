"""
Property-based tests for token validation.

Feature: api-authentication-authorization
Property 3: Invalid Token Denies Access
Validates: Requirements 1.4, 6.3, 6.5

These tests verify that any invalid, expired, or malformed token is rejected
and results in access denial.
"""

import unittest
import sys
import os
import time
import json
import base64
from datetime import datetime, timedelta

# Add backend/src/lambdas to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

from token_validator import (
    decode_jwt_payload,
    check_expiration,
    validate_audience,
    validate_issuer,
    TokenValidationError,
    TokenExpiredError,
    InvalidAudienceError,
    InvalidIssuerError
)

try:
    from hypothesis import given, strategies as st, settings, example
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Warning: hypothesis not available, property tests will be skipped")
    # Create dummy decorators to avoid NameError
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
        def text(*args, **kwargs):
            return None
        @staticmethod
        def integers(*args, **kwargs):
            return None


def create_jwt_token(payload: dict, header: dict = None) -> str:
    """
    Create a JWT token for testing (without signature verification).
    
    Args:
        payload: Token payload
        header: Token header (optional)
        
    Returns:
        JWT token string
    """
    if header is None:
        header = {"alg": "RS256", "typ": "JWT"}
    
    # Encode header
    header_json = json.dumps(header)
    header_b64 = base64.urlsafe_b64encode(header_json.encode()).decode().rstrip('=')
    
    # Encode payload
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
    
    # Create fake signature
    signature = base64.urlsafe_b64encode(b'fake_signature').decode().rstrip('=')
    
    return f"{header_b64}.{payload_b64}.{signature}"


class TestInvalidTokenDenial(unittest.TestCase):
    """
    Property 3: Invalid Token Denies Access
    
    For any expired, malformed, or invalid JWT token, the Lambda Authorizer
    should return a Deny policy and log the authentication failure.
    
    Validates: Requirements 1.4, 6.3, 6.5
    """
    
    def test_malformed_token_single_part(self):
        """Test that single-part tokens are rejected"""
        token = "malformed_token"
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(token)
    
    def test_malformed_token_two_parts(self):
        """Test that two-part tokens are rejected"""
        token = "part1.part2"
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(token)
    
    def test_malformed_token_four_parts(self):
        """Test that four-part tokens are rejected"""
        token = "part1.part2.part3.part4"
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(token)
    
    def test_token_with_invalid_base64(self):
        """Test that tokens with invalid base64 are rejected"""
        token = "invalid!!!.base64!!!.signature!!!"
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(token)
    
    def test_token_with_invalid_json(self):
        """Test that tokens with invalid JSON payload are rejected"""
        # Create token with invalid JSON in payload
        header_b64 = base64.urlsafe_b64encode(b'{"alg":"RS256"}').decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(b'{invalid json}').decode().rstrip('=')
        signature = base64.urlsafe_b64encode(b'sig').decode().rstrip('=')
        token = f"{header_b64}.{payload_b64}.{signature}"
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(token)
    
    def test_expired_token_past_expiration(self):
        """Test that expired tokens are rejected"""
        # Create token that expired 1 hour ago
        exp_time = int(time.time()) - 3600
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": exp_time
        }
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload)
    
    def test_expired_token_just_expired(self):
        """Test that just-expired tokens are rejected"""
        # Create token that expired beyond clock skew (6 minutes ago)
        # Default clock skew is 5 minutes (300 seconds)
        exp_time = int(time.time()) - 360
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": exp_time
        }
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload)
    
    def test_token_missing_expiration(self):
        """Test that tokens without expiration are rejected"""
        payload = {
            "sub": "user123",
            "email": "test@example.com"
        }
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload)
    
    def test_token_with_wrong_audience(self):
        """Test that tokens with wrong audience are rejected"""
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "aud": "wrong-audience"
        }
        
        with self.assertRaises(InvalidAudienceError):
            validate_audience(payload, "expected-audience")
    
    def test_token_missing_audience(self):
        """Test that tokens without audience are rejected"""
        payload = {
            "sub": "user123",
            "email": "test@example.com"
        }
        
        with self.assertRaises(InvalidAudienceError):
            validate_audience(payload, "expected-audience")
    
    def test_token_with_wrong_issuer(self):
        """Test that tokens with wrong issuer are rejected"""
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "iss": "https://wrong-issuer.com"
        }
        
        with self.assertRaises(InvalidIssuerError):
            validate_issuer(payload, "https://expected-issuer.com")
    
    def test_token_missing_issuer(self):
        """Test that tokens without issuer are rejected"""
        payload = {
            "sub": "user123",
            "email": "test@example.com"
        }
        
        with self.assertRaises(InvalidIssuerError):
            validate_issuer(payload, "https://expected-issuer.com")


@unittest.skipIf(not HYPOTHESIS_AVAILABLE, "hypothesis not available")
class TestInvalidTokenProperties(unittest.TestCase):
    """
    Property-based tests for invalid token denial.
    
    Feature: api-authentication-authorization
    Property 3: Invalid Token Denies Access
    """
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_property_random_strings_rejected(self, random_string):
        """
        Property: For any random string that is not a valid JWT,
        token validation should fail.
        """
        # Skip if string happens to have valid JWT format
        if random_string.count('.') == 2:
            parts = random_string.split('.')
            if all(len(p) > 0 for p in parts):
                return  # Skip valid-looking JWTs
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(random_string)
    
    @given(st.integers(min_value=-86400, max_value=-301))
    @settings(max_examples=100)
    def test_property_expired_tokens_rejected(self, seconds_ago):
        """
        Property: For any token with expiration in the past (beyond clock skew),
        the token should be rejected as expired.
        
        Note: Clock skew is 300 seconds (5 minutes), so we test from -301 to ensure
        tokens are truly expired beyond the tolerance window.
        """
        exp_time = int(time.time()) + seconds_ago
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": exp_time
        }
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload)
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_property_wrong_audience_rejected(self, wrong_audience):
        """
        Property: For any audience value that doesn't match expected,
        the token should be rejected.
        """
        expected_audience = "correct-audience"
        
        # Skip if random string happens to match
        if wrong_audience == expected_audience:
            return
        
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "aud": wrong_audience
        }
        
        with self.assertRaises(InvalidAudienceError):
            validate_audience(payload, expected_audience)
    
    @given(st.text(min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_property_wrong_issuer_rejected(self, wrong_issuer):
        """
        Property: For any issuer value that doesn't match expected,
        the token should be rejected.
        """
        expected_issuer = "https://correct-issuer.com"
        
        # Skip if random string happens to match
        if wrong_issuer == expected_issuer:
            return
        
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "iss": wrong_issuer
        }
        
        with self.assertRaises(InvalidIssuerError):
            validate_issuer(payload, expected_issuer)
    
    @given(
        st.integers(min_value=0, max_value=2),
        st.integers(min_value=4, max_value=10)
    )
    @settings(max_examples=100)
    def test_property_wrong_part_count_rejected(self, part_count, part_length):
        """
        Property: For any token with wrong number of parts (not 3),
        the token should be rejected.
        """
        # Create token with wrong number of parts
        parts = ['x' * part_length for _ in range(part_count)]
        token = '.'.join(parts)
        
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload(token)


if __name__ == '__main__':
    unittest.main()
