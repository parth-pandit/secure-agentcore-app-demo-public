# Testing MCP Client with 3-Legged OAuth (3LO)

This guide explains how to test the MCP client with 3-legged OAuth authentication flow.

## What is Workload Identity?

**Workload Identity** is an AWS Bedrock AgentCore concept that represents your application's identity when making requests to the gateway. It's similar to a "service account" that:

- Authenticates your application to the AgentCore Gateway
- Authorizes specific OAuth2 return URLs your application can use
- Defines what audiences (client IDs) your application can request tokens for

**The name is arbitrary** - you choose it! Examples:
- `test-mcp-client-identity` (for testing)
- `my-app-production-identity` (for production)
- `{app-name}-{environment}-identity`

## Prerequisites

1. Python 3.10 or higher
2. AWS credentials configured
3. AgentCore Gateway deployed with authorization code grant
4. Identity provider (e.g., Microsoft Entra ID) configured

## Step 1: Register Workload Identity

**You need to create a workload identity first.** Choose any name you like (e.g., `test-mcp-client-identity`).

```bash
python register_workload_identity.py \
  --region us-west-2 \
  --identity-name test-mcp-client-identity \
  --return-url 'http://localhost:9090/oauth2/callback' \
  --gateway-client-id YOUR_GATEWAY_CLIENT_ID
```

**Parameters:**
- `--region`: AWS region where your gateway is deployed
- `--identity-name`: **Choose any name you want** - this is your workload identity name
- `--return-url`: The OAuth2 callback URL (default: http://localhost:9090/oauth2/callback)
- `--gateway-client-id`: The client ID of your AgentCore Gateway from the identity provider

**Example:**
```bash
python register_workload_identity.py \
  --region us-west-2 \
  --identity-name my-cool-test-app \
  --return-url 'http://localhost:9090/oauth2/callback' \
  --gateway-client-id f8595cc5-9f3a-4459-81d7-abd0c3d67b1a
```

**Note:** If you're running in a different environment (e.g., SageMaker), the return URL will be different. The test script will show you the correct URL.

## Step 2: Run the Test

### Option A: Using the Shell Script (Recommended)

```bash
./test_mcp_client_3lo.sh
```

The script will prompt you for:
- AWS Region
- Gateway's IDP Client ID
- Gateway's IDP Client Secret
- Gateway's IDP Tenant ID
- Gateway URL
- **Workload Identity Name** (use the same name from Step 1, e.g., `test-mcp-client-identity`)

### Option B: Direct Python Execution

```bash
python test_mcp_client_3lo.py \
  --region us-west-2 \
  --gateway-idp-client-id YOUR_CLIENT_ID \
  --gateway-idp-client-secret YOUR_CLIENT_SECRET \
  --gateway-idp-tenant-id YOUR_TENANT_ID \
  --gateway-url YOUR_GATEWAY_URL \
  --workload-identity-name test-mcp-client-identity
```

**Important:** Use the **exact same name** you chose in Step 1!

## What the Test Does

1. **Obtains Access Token**: Gets a JWT token from the identity provider using client credentials
2. **Starts OAuth2 Callback Server**: Launches a local server on port 9090 to handle OAuth callbacks
3. **Verifies Workload Identity**: Checks that the return URL is properly registered
4. **Lists Tools**: Tests basic authentication by listing available MCP tools
5. **Invokes Tool with OAuth**: Calls a tool that requires 3-legged OAuth authentication
6. **Handles OAuth Flow**: The callback server handles the OAuth redirect and completes the flow
7. **Invokes Tool Again**: Tests that the OAuth session is cached and reused

## Troubleshooting

### Port 9090 Already in Use

If you see "address already in use" error, kill the existing process:

```bash
lsof -ti:9090 | xargs kill -9
```

The test script now automatically handles this.

### 403 Forbidden Error

This usually means:
1. **Return URL not registered**: Run Step 1 to register the workload identity
2. **Wrong workload identity name**: Ensure you're using the correct identity name
3. **Gateway configuration issue**: Verify the gateway is properly configured for authorization code grant

### Token Issues

If you see authentication errors:
- Verify your client ID and secret are correct
- Check that the tenant ID matches your identity provider
- Ensure the client has the necessary permissions in the identity provider

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Test      │  Token  │  AgentCore       │  OAuth  │  External       │
│   Script    ├────────>│  Gateway         ├────────>│  Resource       │
│             │         │                  │         │  (Orders API)   │
└──────┬──────┘         └──────────────────┘         └─────────────────┘
       │                         │
       │                         │ OAuth Redirect
       │                         ▼
       │                ┌─────────────────┐
       │                │  OAuth2         │
       └───────────────>│  Callback       │
         Handles        │  Server         │
         Callback       │  (Port 9090)    │
                        └─────────────────┘
```

## Files

- `test_mcp_client_3lo.py`: Main test script
- `test_mcp_client_3lo.sh`: Shell wrapper for easy execution
- `register_workload_identity.py`: Helper to register workload identity
- `oauth2_callback_server.py`: OAuth2 callback server implementation
- `requirements.txt`: Python dependencies

## Next Steps

After successful testing, you can:
1. Integrate this pattern into your application
2. Use different return URLs for different environments
3. Register multiple return URLs in the same workload identity
4. Test with different OAuth providers
