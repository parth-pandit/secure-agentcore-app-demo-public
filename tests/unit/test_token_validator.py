"""
Unit tests for token validator module.

Tests JWKS fetching, signature verification, expiration checking,
and audience/issuer validation.
"""

import unittest
import sys
import os
import json
import time
import base64
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, timedelta

# Add backend/src/lambdas to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend/src/lambdas'))

from token_validator import (
    decode_jwt_payload,
    fetch_jwks,
    get_jwks_cached,
    verify_signature,
    check_expiration,
    validate_audience,
    validate_issuer,
    validate_token,
    get_user_claims,
    TokenValidationError,
    JWKSFetchError,
    SignatureVerificationError,
    TokenExpiredError,
    InvalidAudienceError,
    InvalidIssuerError
)


def create_jwt_token(payload: dict, header: dict = None) -> str:
    """Helper to create JWT tokens for testing"""
    if header is None:
        header = {"alg": "RS256", "typ": "JWT", "kid": "key123"}
    
    header_json = json.dumps(header)
    header_b64 = base64.urlsafe_b64encode(header_json.encode()).decode().rstrip('=')
    
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
    
    signature = base64.urlsafe_b64encode(b'fake_signature').decode().rstrip('=')
    
    return f"{header_b64}.{payload_b64}.{signature}"


class TestDecodeJWTPayload(unittest.TestCase):
    """Test JWT payload decoding"""
    
    def test_decode_valid_payload(self):
        """Test decoding a valid JWT payload"""
        payload = {"sub": "user123", "email": "test@example.com", "exp": 1234567890}
        token = create_jwt_token(payload)
        
        decoded = decode_jwt_payload(token)
        
        self.assertEqual(decoded['sub'], 'user123')
        self.assertEqual(decoded['email'], 'test@example.com')
        self.assertEqual(decoded['exp'], 1234567890)
    
    def test_decode_payload_with_special_characters(self):
        """Test decoding payload with special characters"""
        payload = {"name": "Test User™", "email": "test+tag@example.com"}
        token = create_jwt_token(payload)
        
        decoded = decode_jwt_payload(token)
        
        self.assertEqual(decoded['name'], 'Test User™')
        self.assertEqual(decoded['email'], 'test+tag@example.com')
    
    def test_decode_invalid_format(self):
        """Test error on invalid token format"""
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload("invalid.token")
    
    def test_decode_empty_string(self):
        """Test error on empty token"""
        with self.assertRaises(TokenValidationError):
            decode_jwt_payload("")


class TestFetchJWKS(unittest.TestCase):
    """Test JWKS fetching from IAM Identity Center"""
    
    @patch('requests.get')
    def test_fetch_jwks_success(self, mock_get):
        """Test successful JWKS fetch"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "keys": [
                {"kid": "key1", "kty": "RSA", "use": "sig"},
                {"kid": "key2", "kty": "RSA", "use": "sig"}
            ]
        }
        mock_get.return_value = mock_response
        
        jwks = fetch_jwks("https://example.com/.well-known/jwks.json")
        
        self.assertEqual(len(jwks['keys']), 2)
        self.assertEqual(jwks['keys'][0]['kid'], 'key1')
        mock_get.assert_called_once()
    
    @patch('requests.get')
    def test_fetch_jwks_network_error(self, mock_get):
        """Test JWKS fetch with network error"""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        
        with self.assertRaises(JWKSFetchError):
            fetch_jwks("https://example.com/.well-known/jwks.json")
    
    @patch('requests.get')
    def test_fetch_jwks_invalid_json(self, mock_get):
        """Test JWKS fetch with invalid JSON response"""
        mock_response = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)
        mock_get.return_value = mock_response
        
        with self.assertRaises(JWKSFetchError):
            fetch_jwks("https://example.com/.well-known/jwks.json")
    
    @patch('requests.get')
    def test_fetch_jwks_http_error(self, mock_get):
        """Test JWKS fetch with HTTP error"""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("404 Not Found")
        
        with self.assertRaises(JWKSFetchError):
            fetch_jwks("https://example.com/.well-known/jwks.json")


class TestGetJWKSCached(unittest.TestCase):
    """Test JWKS caching functionality"""
    
    def setUp(self):
        """Clear cache before each test"""
        if hasattr(get_jwks_cached, 'cache'):
            get_jwks_cached.cache.clear()
    
    @patch('token_validator.fetch_jwks')
    def test_cache_first_fetch(self, mock_fetch):
        """Test first fetch stores in cache"""
        mock_fetch.return_value = {"keys": [{"kid": "key1"}]}
        
        jwks = get_jwks_cached("https://example.com/jwks.json")
        
        self.assertEqual(len(jwks['keys']), 1)
        mock_fetch.assert_called_once()
    
    @patch('token_validator.fetch_jwks')
    def test_cache_reuse(self, mock_fetch):
        """Test cache is reused for subsequent calls"""
        mock_fetch.return_value = {"keys": [{"kid": "key1"}]}
        
        # First call
        jwks1 = get_jwks_cached("https://example.com/jwks.json")
        # Second call (should use cache)
        jwks2 = get_jwks_cached("https://example.com/jwks.json")
        
        # fetch_jwks should only be called once
        self.assertEqual(mock_fetch.call_count, 1)
        self.assertEqual(jwks1, jwks2)
    
    @patch('token_validator.fetch_jwks')
    @patch('token_validator.time.time')
    def test_cache_expiration(self, mock_time, mock_fetch):
        """Test cache expires after TTL"""
        mock_fetch.return_value = {"keys": [{"kid": "key1"}]}
        
        # First call at time 0
        mock_time.return_value = 0
        jwks1 = get_jwks_cached("https://example.com/jwks.json", cache_duration=3600)
        
        # Second call at time 3601 (expired)
        mock_time.return_value = 3601
        jwks2 = get_jwks_cached("https://example.com/jwks.json", cache_duration=3600)
        
        # fetch_jwks should be called twice
        self.assertEqual(mock_fetch.call_count, 2)


class TestCheckExpiration(unittest.TestCase):
    """Test token expiration checking"""
    
    def test_valid_token_not_expired(self):
        """Test valid token that hasn't expired"""
        exp_time = int(time.time()) + 3600  # Expires in 1 hour
        payload = {"exp": exp_time}
        
        result = check_expiration(payload)
        self.assertTrue(result)
    
    def test_token_expired(self):
        """Test expired token"""
        exp_time = int(time.time()) - 3600  # Expired 1 hour ago
        payload = {"exp": exp_time}
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload)
    
    def test_token_missing_exp(self):
        """Test token without exp claim"""
        payload = {"sub": "user123"}
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload)
    
    def test_token_within_clock_skew(self):
        """Test token within clock skew tolerance"""
        # Token expired 2 minutes ago, but within 5 minute clock skew
        exp_time = int(time.time()) - 120
        payload = {"exp": exp_time}
        
        result = check_expiration(payload, clock_skew=300)
        self.assertTrue(result)
    
    def test_token_beyond_clock_skew(self):
        """Test token beyond clock skew tolerance"""
        # Token expired 6 minutes ago, beyond 5 minute clock skew
        exp_time = int(time.time()) - 360
        payload = {"exp": exp_time}
        
        with self.assertRaises(TokenExpiredError):
            check_expiration(payload, clock_skew=300)


class TestValidateAudience(unittest.TestCase):
    """Test audience validation"""
    
    def test_valid_audience_string(self):
        """Test valid audience as string"""
        payload = {"aud": "my-api-gateway"}
        
        result = validate_audience(payload, "my-api-gateway")
        self.assertTrue(result)
    
    def test_valid_audience_array(self):
        """Test valid audience in array"""
        payload = {"aud": ["api1", "my-api-gateway", "api3"]}
        
        result = validate_audience(payload, "my-api-gateway")
        self.assertTrue(result)
    
    def test_invalid_audience(self):
        """Test invalid audience"""
        payload = {"aud": "wrong-audience"}
        
        with self.assertRaises(InvalidAudienceError):
            validate_audience(payload, "my-api-gateway")
    
    def test_missing_audience(self):
        """Test missing audience claim"""
        payload = {"sub": "user123"}
        
        with self.assertRaises(InvalidAudienceError):
            validate_audience(payload, "my-api-gateway")
    
    def test_audience_not_in_array(self):
        """Test audience not in array"""
        payload = {"aud": ["api1", "api2", "api3"]}
        
        with self.assertRaises(InvalidAudienceError):
            validate_audience(payload, "my-api-gateway")


class TestValidateIssuer(unittest.TestCase):
    """Test issuer validation"""
    
    def test_valid_issuer(self):
        """Test valid issuer"""
        payload = {"iss": "https://identity-center.amazonaws.com"}
        
        result = validate_issuer(payload, "https://identity-center.amazonaws.com")
        self.assertTrue(result)
    
    def test_invalid_issuer(self):
        """Test invalid issuer"""
        payload = {"iss": "https://wrong-issuer.com"}
        
        with self.assertRaises(InvalidIssuerError):
            validate_issuer(payload, "https://identity-center.amazonaws.com")
    
    def test_missing_issuer(self):
        """Test missing issuer claim"""
        payload = {"sub": "user123"}
        
        with self.assertRaises(InvalidIssuerError):
            validate_issuer(payload, "https://identity-center.amazonaws.com")


class TestValidateToken(unittest.TestCase):
    """Test complete token validation"""
    
    @patch('token_validator.get_jwks_cached')
    @patch('token_validator.verify_signature')
    def test_validate_token_success(self, mock_verify, mock_jwks):
        """Test successful token validation"""
        mock_jwks.return_value = {"keys": [{"kid": "key1"}]}
        mock_verify.return_value = True
        
        exp_time = int(time.time()) + 3600
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": exp_time,
            "aud": "my-api",
            "iss": "https://issuer.com"
        }
        token = create_jwt_token(payload)
        
        result = validate_token(
            token,
            "https://issuer.com/.well-known/jwks.json",
            "my-api",
            "https://issuer.com"
        )
        
        self.assertEqual(result['sub'], 'user123')
        self.assertEqual(result['email'], 'test@example.com')
    
    @patch('token_validator.get_jwks_cached')
    @patch('token_validator.verify_signature')
    def test_validate_token_expired(self, mock_verify, mock_jwks):
        """Test validation fails for expired token"""
        mock_jwks.return_value = {"keys": [{"kid": "key1"}]}
        mock_verify.return_value = True
        
        exp_time = int(time.time()) - 3600  # Expired
        payload = {
            "sub": "user123",
            "exp": exp_time,
            "aud": "my-api",
            "iss": "https://issuer.com"
        }
        token = create_jwt_token(payload)
        
        with self.assertRaises(TokenExpiredError):
            validate_token(
                token,
                "https://issuer.com/.well-known/jwks.json",
                "my-api",
                "https://issuer.com"
            )
    
    @patch('token_validator.get_jwks_cached')
    @patch('token_validator.verify_signature')
    def test_validate_token_wrong_audience(self, mock_verify, mock_jwks):
        """Test validation fails for wrong audience"""
        mock_jwks.return_value = {"keys": [{"kid": "key1"}]}
        mock_verify.return_value = True
        
        exp_time = int(time.time()) + 3600
        payload = {
            "sub": "user123",
            "exp": exp_time,
            "aud": "wrong-api",
            "iss": "https://issuer.com"
        }
        token = create_jwt_token(payload)
        
        with self.assertRaises(InvalidAudienceError):
            validate_token(
                token,
                "https://issuer.com/.well-known/jwks.json",
                "my-api",
                "https://issuer.com"
            )


class TestGetUserClaims(unittest.TestCase):
    """Test user claims extraction"""
    
    def test_extract_all_claims(self):
        """Test extracting all user claims"""
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "groups": ["admin", "users"]
        }
        
        claims = get_user_claims(payload)
        
        self.assertEqual(claims['sub'], 'user123')
        self.assertEqual(claims['email'], 'test@example.com')
        self.assertEqual(claims['name'], 'Test User')
        self.assertEqual(claims['groups'], ['admin', 'users'])
    
    def test_extract_partial_claims(self):
        """Test extracting claims when some are missing"""
        payload = {
            "sub": "user123",
            "email": "test@example.com"
        }
        
        claims = get_user_claims(payload)
        
        self.assertEqual(claims['sub'], 'user123')
        self.assertEqual(claims['email'], 'test@example.com')
        self.assertEqual(claims['name'], '')
        self.assertEqual(claims['groups'], [])
    
    def test_extract_empty_payload(self):
        """Test extracting claims from empty payload"""
        payload = {}
        
        claims = get_user_claims(payload)
        
        self.assertEqual(claims['sub'], '')
        self.assertEqual(claims['email'], '')
        self.assertEqual(claims['name'], '')
        self.assertEqual(claims['groups'], [])


if __name__ == '__main__':
    unittest.main()
