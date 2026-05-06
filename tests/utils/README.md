# Testing Utilities

This directory contains utilities for testing the Orders API and the agentic application.

## Scripts

### `generate_azure_token.sh`

Generates a real Azure Entra ID access token for integration testing.

```bash
bash tests/utils/generate_azure_token.sh
```

Supports:
- **Device Code Flow** — interactive browser authentication (recommended)
- **Client Credentials Flow** — service-to-service (requires client secret)

Export the token for use in tests:

```bash
export AZURE_TOKEN=$(bash tests/utils/generate_azure_token.sh)
```

### `test_api_live.sh`

Runs 8 end-to-end tests against the live Orders API. Auto-discovers the API URL from CloudFormation.

```bash
export AZURE_TOKEN=$(bash tests/utils/generate_azure_token.sh)
bash tests/utils/test_api_live.sh
```

Tests cover:
- Unauthenticated access (expects 401)
- Invalid/expired tokens (expects 401)
- Unauthorized users (expects 403)
- Authorized GET, POST, PUT operations (expects 200/201)

### `setup_test_env.sh`

Sets up environment variables needed for testing.

```bash
source tests/utils/setup_test_env.sh
```

## Related Documentation

- [Authentication Setup Guide](../../docs/AUTHENTICATION_SETUP.md)
- [API Documentation](../../docs/API_DOCUMENTATION.md)
- [Testing Guide](../../docs/TESTING_GUIDE.md)
