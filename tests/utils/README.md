# Testing Utilities

This directory contains utilities for testing the authenticated Orders API.

## Token Generator (`token_generator.py`)

Python module for generating mock JWT tokens for unit testing.

### Usage

```python
from tests.utils.token_generator import MockTokenGenerator, create_test_token

# Create a token generator
generator = MockTokenGenerator()

# Generate a valid token
token = generator.generate_token(
    email="user@yourdomain.com",
    name="Test User"
)

# Generate an expired token
expired_token = generator.generate_expired_token(
    email="user@yourdomain.com",
    name="Test User"
)

# Generate tokens with various issues
wrong_issuer = generator.generate_wrong_issuer_token("test@example.com")
wrong_audience = generator.generate_wrong_audience_token("test@example.com")
invalid_sig = generator.generate_invalid_signature_token("test@example.com")
malformed = generator.generate_malformed_token()

# Convenience function
token = create_test_token(
    email="user@yourdomain.com",
    expired=True  # or wrong_issuer=True, wrong_audience=True, etc.
)
```

### Helper Functions

```python
from tests.utils.token_generator import (
    create_authorization_header,
    create_authorizer_event
)

# Create Authorization header for API requests
headers = create_authorization_header(token)
# Returns: {"Authorization": "Bearer <token>"}

# Create Lambda Authorizer event for testing
event = create_authorizer_event(
    token=token,
    method="GET",
    resource="/orders"
)
```

### Running Examples

```bash
python3 tests/utils/token_generator.py
```

## Real Token Script (`generate_azure_token.sh`)

Bash script to obtain real JWT tokens from Azure Entra ID for integration testing.

### Prerequisites

1. Azure CLI installed and configured
2. Azure Entra ID application registered
3. `jq` installed for JSON parsing

### Usage

```bash
# Get token using device code flow
./tests/utils/generate_azure_token.sh

# Show help
./tests/utils/generate_azure_token.sh --help
```

### Make Script Executable

```bash
chmod +x tests/utils/get_real_token.sh
```

### Using the Token

Once you have a real token, you can use it in tests:

```bash
# Export as environment variable
export TEST_TOKEN="<your-token>"

# Use in curl
curl -X GET \
  'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders' \
  -H "Authorization: Bearer $TEST_TOKEN"
```

In Python tests:

```python
import os

# Get token from environment
token = os.environ.get('TEST_TOKEN')

# Use in requests
import requests
response = requests.get(
    'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders',
    headers={'Authorization': f'Bearer {token}'}
)
```

## Testing Workflow

### 1. Unit Tests (Mock Tokens)

Use `token_generator.py` for unit tests that mock the token validation:

```python
from tests.utils.token_generator import create_test_token

def test_authorizer_with_valid_token():
    token = create_test_token(email="user@yourdomain.com")
    # Mock the token validation
    # Test authorizer logic
```

### 2. Integration Tests (Real Tokens)

Use `get_real_token.sh` for integration tests against real AWS services:

```bash
# Get real token
./tests/utils/get_real_token.sh --save token.txt

# Run integration tests
export TEST_TOKEN=$(cat token.txt)
python3 -m pytest tests/integration/
```

### 3. Manual API Testing

Use real tokens for manual testing with curl or Postman:

```bash
# Get token
TOKEN=$(./tests/utils/get_real_token.sh | grep -A1 "Access Token" | tail -1)

# Test GET endpoint
curl -X GET \
  'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders' \
  -H "Authorization: Bearer $TOKEN"

# Test POST endpoint
curl -X POST \
  'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders' \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-123",
    "item_name": "Test Item",
    "qty": 5,
    "status": "pending"
  }'
```

## Token Expiration

- Mock tokens: Configurable expiration (default: 1 hour)
- Real tokens: Typically expire after 1 hour
- Run `get_real_token.sh` again to get a fresh token when expired

## Security Notes

1. **Never commit real tokens** to version control
2. Mock tokens are for testing only and are not cryptographically secure
3. Real tokens should be treated as sensitive credentials
4. Tokens should only be used over HTTPS
5. Rotate tokens regularly in production environments

## Troubleshooting

### "Azure CLI is not installed"

Install Azure CLI:
- macOS: `brew install azure-cli`
- Linux: Follow https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
- Windows: Download from https://aka.ms/installazurecliwindows

### "jq is not installed"

Install jq:
- macOS: `brew install jq`
- Linux: `sudo apt-get install jq`

### "Azure login failed"

1. Run `az login` to authenticate
2. Ensure you have access to the Azure tenant
3. Check your network connection
4. Verify Azure Entra ID is accessible

### "Could not get device code"

1. Verify your Azure Application ID is correct
2. Check that public client flow is enabled in Azure app registration
3. Ensure the application has proper API permissions

### "Token expired"

Run the script again to get a fresh token:
```bash
./tests/utils/get_real_token.sh
```

## Related Documentation

- [Authentication Setup Guide](../../docs/AUTHENTICATION_SETUP.md)
- [API Documentation](../../docs/API_DOCUMENTATION.md)
- [Testing Guide](../../docs/TESTING_GUIDE.md)
