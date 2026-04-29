# Authentication Setup Guide

## Overview

The Orders API uses Azure Entra ID for authentication and authorization. All API requests must include a valid JWT token in the Authorization header. This guide explains how to configure Azure Entra ID and obtain access tokens for API calls.

## Prerequisites

- Azure Entra ID tenant with administrative access
- Administrative access to Azure App Registrations
- AWS CLI configured with appropriate credentials
- Access to the deployed CloudFormation stack

## Azure Entra ID Configuration

### Step 1: Register Application in Azure Entra ID

1. Navigate to Azure Portal → Microsoft Entra ID → App registrations
2. Click "New registration"
3. Configure the application:
   - **Name**: Orders API
   - **Supported account types**: Accounts in this organizational directory only (Single tenant)
   - **Redirect URI**: (leave empty for now, add later if needed)
4. Click "Register"

### Step 2: Note Application Details

After registration, note the following values from the Overview page:
- **Application (client) ID**: This will be your TOKEN_AUDIENCE
- **Directory (tenant) ID**: Used to construct issuer and JWKS URLs

### Step 3: Configure API Permissions

1. Go to "API permissions" in your app registration
2. Click "Add a permission"
3. Select "Microsoft Graph"
4. Choose "Delegated permissions"
5. Add these permissions:
   - `openid` (required)
   - `profile` (required)
   - `email` (required)
6. Click "Add permissions"
7. Click "Grant admin consent" for your organization

### Step 4: Configure Token Claims

1. Go to "Token configuration" in your app registration
2. Click "Add optional claim"
3. Select "Access" token type
4. Add these claims:
   - `email`
   - `upn` (User Principal Name)
   - `preferred_username`
5. Click "Add"

### Step 5: Enable Public Client Flow (Required for Device Code Flow)

**Important**: For API applications using Device Code Flow, you must enable public client flow.

1. Go to "Authentication" in your app registration
2. Scroll down to "Advanced settings"
3. Under "Allow public client flows", set to **Yes**
4. Click "Save"

**Alternative Method (using Manifest)**:
1. Go to "Manifest" in your app registration
2. Find the `allowPublicClient` property
3. Change `"allowPublicClient": false` to `"allowPublicClient": true`
4. Click "Save"

**Why this is needed**: Device Code Flow is considered a public client flow because it doesn't require a client secret. Enabling this setting allows your application to use Device Code Flow for authentication.

### Step 6: Create Client Secret (Optional - Only for Client Credentials Flow)

**Note**: Client secret is NOT required for Device Code Flow. Only create this if you plan to use Client Credentials Flow for service-to-service authentication.

If your application needs to authenticate as itself:
1. Go to "Certificates & secrets"
2. Click "New client secret"
3. Add a description and select expiration
4. Click "Add"
5. **Important**: Copy the secret value immediately (it won't be shown again)

### Step 7: Get Endpoints

1. In your app registration, click "Overview"
2. Click "Endpoints" button
3. Note these URLs:
   - **OAuth 2.0 authorization endpoint (v2)**
   - **OAuth 2.0 token endpoint (v2)**
   - **OpenID Connect metadata document**

### Step 8: Construct Required URLs

From the endpoints, construct the following:

```bash
# Your Tenant ID (from Overview page)
TENANT_ID="your-tenant-id-here"

# Application (Client) ID (from Overview page)
APPLICATION_ID="your-application-id-here"

# Issuer URL (remove /.well-known/openid-configuration from metadata URL)
TOKEN_ISSUER="https://login.microsoftonline.com/${TENANT_ID}/v2.0"

# JWKS URL (get from OpenID Connect metadata document or construct)
JWKS_URL="https://login.microsoftonline.com/${TENANT_ID}/discovery/v2.0/keys"

# Token Audience (same as Application ID)
TOKEN_AUDIENCE="${APPLICATION_ID}"
```

### Step 9: Verify JWKS URL

Test that the JWKS URL is accessible:

```bash
curl https://login.microsoftonline.com/${TENANT_ID}/discovery/v2.0/keys
```

You should see a JSON response with public keys.

## Deployment Configuration

### Update CloudFormation Stack

Deploy the stack with Azure Entra ID parameters:

```bash
./infrastructure/scripts/deploy-stack.sh \
  secure-agentcore-app \
  your-s3-bucket \
  dev \
  "https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys" \
  "https://login.microsoftonline.com/<TENANT_ID>/v2.0" \
  "<APPLICATION_ID>" \
  '{"user@yourdomain.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'
```

### Parameters Explained

- **JWKS URL**: URL to fetch public keys for token verification from Azure Entra ID
- **Token Issuer**: Expected issuer claim in JWT tokens (Azure Entra ID issuer)
- **Token Audience**: Expected audience claim (your Azure Application ID)
- **Authorized Users**: JSON configuration of users and their permissions

## Obtaining Access Tokens

### Method 1: Using Azure CLI (Recommended for Testing)

```bash
# Login to Azure
az login

# Get access token for your application
az account get-access-token --resource <APPLICATION_ID> --query accessToken --output tsv
```

This is the simplest method for testing and returns a valid Azure Entra ID token.

### Method 2: Using Device Code Flow (Recommended for API Applications)

The Device Code Flow is ideal for API applications without a redirect URI. This method allows users to authenticate via a browser while the application polls for the token.

#### Step-by-Step Device Code Flow

**Step 1: Request Device Code**

```bash
# Set your configuration
TENANT_ID="your-tenant-id"
APPLICATION_ID="your-application-id"

# Request device code
curl -X POST "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/devicecode" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=${APPLICATION_ID}" \
  -d "scope=openid email profile ${APPLICATION_ID}/.default"
```

**Response**:
```json
{
  "user_code": "ABC123DEF",
  "device_code": "BAQABAAEAAAAm-06blBE1TpVMil8KPQ41...",
  "verification_uri": "https://microsoft.com/devicelogin",
  "expires_in": 900,
  "interval": 5,
  "message": "To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code ABC123DEF to authenticate."
}
```

**Step 2: User Authentication**

1. Open the `verification_uri` in a browser: https://microsoft.com/devicelogin
2. Enter the `user_code` displayed (e.g., ABC123DEF)
3. Sign in with your Azure credentials
4. Approve the authentication request

**Step 3: Poll for Token**

While the user is authenticating, poll the token endpoint:

```bash
# Save the device_code from Step 1
DEVICE_CODE="BAQABAAEAAAAm-06blBE1TpVMil8KPQ41..."

# Poll for token (repeat every 5 seconds until successful)
curl -X POST "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  -d "client_id=${APPLICATION_ID}" \
  -d "device_code=${DEVICE_CODE}"
```

**While waiting** (before user completes authentication):
```json
{
  "error": "authorization_pending",
  "error_description": "AADSTS70016: OAuth 2.0 device flow error..."
}
```

**After successful authentication**:
```json
{
  "token_type": "Bearer",
  "scope": "openid email profile",
  "expires_in": 3600,
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "0.AXoA...",
  "id_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Automated Device Code Flow Script

Use the provided script for automated device code flow:

```bash
./tests/utils/generate_azure_token.sh
```

Select option 2 (Device Code Flow) and follow the prompts.

**Script Features**:
- Automatically requests device code
- Displays user code and verification URL
- Polls for token automatically
- Handles errors and timeouts
- Returns access token when ready

### Method 3: Using Client Credentials Flow (Service-to-Service)

**Note**: This method requires a client secret and is typically used for service-to-service authentication without user interaction.

**Step 1: Create Client Secret** (if not already done)

1. Go to Azure Portal → Your App → Certificates & secrets
2. Click "New client secret"
3. Add description and expiration
4. Copy the secret value immediately

**Step 2: Get Token**

```bash
TENANT_ID="your-tenant-id"
APPLICATION_ID="your-application-id"
CLIENT_SECRET="your-client-secret"

curl -X POST "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${APPLICATION_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "scope=${APPLICATION_ID}/.default"
```

**Response**:
```json
{
  "token_type": "Bearer",
  "expires_in": 3599,
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Important**: Client Credentials tokens don't contain user information (no email claim), so they may not work with user-based authorization unless you configure service principal permissions.

### Method 4: Using Postman with Device Code Flow

Postman can be used to test the API with Azure tokens obtained via Device Code Flow.

**Step 1: Get Token Using Device Code Flow**

Since Postman doesn't natively support Device Code Flow for Azure, use one of the methods above to obtain a token:

```bash
# Option A: Use Azure CLI
az login
TOKEN=$(az account get-access-token --resource <APPLICATION_ID> --query accessToken --output tsv)

# Option B: Use the provided script
./tests/utils/generate_azure_token.sh
# Select option 2 (Device Code Flow)
# Copy the token from the output
```

**Step 2: Configure Postman**

1. Create a new request in Postman
2. Set the request URL to your API endpoint
3. Go to the "Authorization" tab
4. Select "Bearer Token" as the type
5. Paste your access token in the Token field

**Step 3: Test API Endpoints**

Create requests for each endpoint:

**GET Orders**:
- Method: GET
- URL: `https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders`
- Authorization: Bearer Token (from Step 2)

**POST Order**:
- Method: POST
- URL: `https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders`
- Authorization: Bearer Token
- Headers: `Content-Type: application/json`
- Body (raw JSON):
```json
{
  "order_id": "order-{{$randomUUID}}",
  "order_date": "{{$isoTimestamp}}",
  "item_name": "Test Item",
  "qty": 5,
  "status": "pending"
}
```

**PUT Order**:
- Method: PUT
- URL: `https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders`
- Authorization: Bearer Token
- Headers: `Content-Type: application/json`
- Body (raw JSON):
```json
{
  "order_id": "existing-order-id",
  "status": "completed"
}
```

**Step 4: Refresh Token When Expired**

Azure tokens typically expire after 1 hour. When you get a 401 error:
1. Run the token generation command again
2. Copy the new token
3. Update the Bearer Token in Postman

**Tip**: Save your token as a Postman environment variable for easy reuse across requests:
- Create an environment
- Add variable: `azure_token`
- Use in Authorization: `{{azure_token}}`

## Making Authenticated API Requests

### Request Format

All API requests must include the access token in the Authorization header:

```bash
curl -X GET https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Example: GET Orders

```bash
curl -X GET https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders \
  -H "Authorization: Bearer eyJ0eXAiOiJ..."
```

### Example: Create Order

```bash
curl -X POST https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders \
  -H "Authorization: Bearer eyJ0eXAiOiJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order-123",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }'
```

### Example: Update Order

```bash
curl -X PUT https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders \
  -H "Authorization: Bearer eyJ0eXAiOiJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order-123",
    "status": "completed"
  }'
```

## Authentication Flow

1. **Client Request**: Client sends request with Bearer token from Azure Entra ID
2. **API Gateway**: Invokes Lambda Authorizer before routing to backend
3. **Token Validation**: Authorizer validates token signature, expiration, issuer, and audience against Azure Entra ID
4. **Authorization Check**: Authorizer verifies user has permission for the requested operation
5. **Audit Logging**: All authentication attempts are logged to CloudWatch
6. **Policy Generation**: Authorizer returns Allow or Deny policy
7. **Request Processing**: If allowed, API Gateway routes to backend Lambda
8. **Response**: Backend processes request and returns response

## Error Responses

### 401 Unauthorized

Missing or invalid token:
```json
{
  "message": "Unauthorized"
}
```

**Causes**:
- No Authorization header provided
- Token is malformed or invalid
- Token signature verification failed
- Token has expired
- Token issuer or audience doesn't match

### 403 Forbidden

Valid token but insufficient permissions:
```json
{
  "message": "User is not authorized to access this resource with an explicit deny"
}
```

**Causes**:
- User email not in authorized users list
- User doesn't have permission for the requested HTTP method
- User doesn't have access to the requested resource

## Token Caching

The Lambda Authorizer caches authorization decisions for 300 seconds (5 minutes) to improve performance. This means:

- Successful authorizations are cached per token
- Changes to user permissions may take up to 5 minutes to take effect
- Revoked tokens may remain valid for up to 5 minutes
- To force immediate re-authorization, use a new token

## Audit Logging

All authentication and authorization attempts are logged to CloudWatch Logs:

- **Log Group**: `/aws/lambda/orders-api-authorizer`
- **Log Format**: Structured JSON
- **Retention**: 30 days (configurable)

### Log Entry Example

```json
{
  "timestamp": "2025-01-05T12:00:00.000Z",
  "event_type": "AUTHORIZATION_SUCCESS",
  "service": "orders-api-authorizer",
  "user": {
    "email": "user@yourdomain.com"
  },
  "request": {
    "method": "GET",
    "resource": "/orders",
    "source_ip": "203.0.113.1"
  },
  "result": "ALLOW"
}
```

## Troubleshooting

### Token Validation Fails

1. Verify JWKS URL is correct and accessible
2. Check token hasn't expired (exp claim)
3. Verify issuer matches configuration (should be Azure Entra ID issuer)
4. Verify audience matches configuration (should be your Application ID)
5. Check CloudWatch Logs for detailed error messages

### User Not Authorized

1. Verify user email is in AuthorizedUsers configuration
2. Check user has required permissions for the HTTP method
3. Verify user has access to the requested resource
4. Check CloudWatch Logs for authorization details

### Cannot Obtain Token

1. Verify Azure Entra ID application is properly configured
2. Check user has access to the application
3. Verify OAuth/OIDC settings are correct
4. Check redirect URIs are properly configured
5. Ensure API permissions are granted and admin consent is provided

## Security Best Practices

1. **Token Storage**: Never store tokens in client-side code or version control
2. **Token Transmission**: Always use HTTPS for API requests
3. **Token Expiration**: Implement token refresh logic in your application
4. **Least Privilege**: Grant users only the permissions they need
5. **Monitoring**: Regularly review CloudWatch Logs for suspicious activity
6. **Rotation**: Rotate client secrets regularly
7. **Revocation**: Implement token revocation for compromised tokens

## Next Steps

1. Register application in Azure Entra ID
2. Configure API permissions and token claims
3. Deploy the CloudFormation stack with authentication parameters
4. Test authentication with sample API calls
5. Integrate authentication into your client applications
6. Set up monitoring and alerting for security events

## Support

For issues or questions:
- Check CloudWatch Logs: `/aws/lambda/orders-api-authorizer`
- Review API Gateway execution logs
- Verify Azure Entra ID configuration
- Contact your Azure administrator
