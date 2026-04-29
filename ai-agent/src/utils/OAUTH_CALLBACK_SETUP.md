# OAuth2 Callback Server Setup Guide

This guide explains how to set up the OAuth2 callback server infrastructure required for 3LO (3-legged OAuth) authentication flows.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Permissions to create DynamoDB tables and modify IAM roles
- The OAuth callback Lambda function already deployed

## Why These Components Are Needed

### 1. DynamoDB Table (`agentcore-oauth-callback`)
**Purpose**: Temporarily stores the agent's 2LO authentication token (session binding identifier)

**Flow**:
1. Agent stores its 2LO token in DynamoDB via `POST /userIdentifier/token`
2. User authenticates with external OAuth provider
3. Provider redirects to callback Lambda
4. Callback Lambda retrieves the stored token from DynamoDB
5. Callback Lambda calls AgentCore's `complete_resource_token_auth` with the token

**TTL**: Tokens expire after 10 minutes (auto-deleted by DynamoDB TTL)

### 2. IAM Permissions
**Purpose**: Allow the callback Lambda to complete OAuth flows

**Required Permissions**:
- `secretsmanager:GetSecretValue` - AgentCore needs to retrieve OAuth credentials (client_id, client_secret) from Secrets Manager when completing the OAuth flow
- `bedrock-agentcore:CompleteResourceTokenAuth` - Complete the OAuth flow with AgentCore
- `bedrock-agentcore:GetResourceTokenAuthSession` - Retrieve OAuth session details

## Setup Steps

### Step 1: Create DynamoDB Table

```bash
cd ai-agent/src/utils
chmod +x create-oauth-callback-table.sh
REGION=us-west-2 ./create-oauth-callback-table.sh
```

**What it creates**:
- Table name: `agentcore-oauth-callback`
- Partition key: `id` (String)
- Billing mode: On-demand (PAY_PER_REQUEST)
- TTL enabled on `expires_at` attribute

**Verify**:
```bash
aws dynamodb describe-table --table-name agentcore-oauth-callback --region us-east-1
```

### Step 2: Update Lambda IAM Permissions

```bash
cd ai-agent/src/utils
chmod +x update-oauth-callback-permissions.sh
REGION=us-east-1 OAUTH_LAMBDA_NAME=agentcore-oauth-callback ./update-oauth-callback-permissions.sh
```

**What it adds**:
- Inline policy: `AgentCoreOAuthCallbackPolicy`
- Permissions for AgentCore API calls
- Permissions for Secrets Manager access

**Verify**:
```bash
aws iam list-role-policies --role-name <your-lambda-role-name>
```

### Step 3: Configure Agent Environment Variable

Set the `OAUTH_CALLBACK_SERVER_URL` environment variable in your agent (order_agent.py):

```bash
export OAUTH_CALLBACK_SERVER_URL="https://your-callback-lambda-url.execute-api.us-east-1.amazonaws.com/prod"
```

Or if deploying via Lambda, add it to the Lambda environment variables.

## Troubleshooting

### Error: "ResourceNotFoundException" (DynamoDB)
**Cause**: DynamoDB table doesn't exist
**Solution**: Run `create-oauth-callback-table.sh`

### Error: "AccessDeniedException: secretsmanager:GetSecretValue"
**Cause**: Lambda IAM role lacks Secrets Manager permissions
**Solution**: Run `update-oauth-callback-permissions.sh`

**Why this happens**: When AgentCore's `complete_resource_token_auth` is called, it needs to retrieve OAuth credentials from Secrets Manager to exchange the authorization code for access tokens with the external OAuth provider.

### Error: "AccessDeniedException: bedrock-agentcore:CompleteResourceTokenAuth"
**Cause**: Lambda IAM role lacks AgentCore permissions
**Solution**: Run `update-oauth-callback-permissions.sh`

## Architecture

```
┌─────────────┐
│   Agent     │
│ (order_agent)│
└──────┬──────┘
       │ 1. Store 2LO token
       ▼
┌─────────────────────────┐
│ OAuth Callback Lambda   │
│ POST /userIdentifier/   │
│      token              │
└──────┬──────────────────┘
       │ 2. Store in DynamoDB
       ▼
┌─────────────────────────┐
│   DynamoDB Table        │
│ agentcore-oauth-callback│
└─────────────────────────┘

... User authenticates with OAuth provider ...

┌─────────────────────────┐
│ OAuth Provider          │
│ (Microsoft, Google, etc)│
└──────┬──────────────────┘
       │ 3. Redirect with code
       ▼
┌─────────────────────────┐
│ OAuth Callback Lambda   │
│ GET /oauth2/callback    │
└──────┬──────────────────┘
       │ 4. Retrieve token from DynamoDB
       ▼
┌─────────────────────────┐
│   DynamoDB Table        │
└──────┬──────────────────┘
       │ 5. Call AgentCore API
       ▼
┌─────────────────────────┐
│   AgentCore             │
│ complete_resource_      │
│ token_auth()            │
└──────┬──────────────────┘
       │ 6. Get OAuth credentials
       ▼
┌─────────────────────────┐
│  Secrets Manager        │ ← Requires secretsmanager:GetSecretValue
└─────────────────────────┘
```

## Verification

After setup, test the flow:

1. **Check agent logs** for token storage:
   ```
   INFO: Storing authentication token in OAuth callback server
   INFO: Successfully stored authentication token in OAuth callback server
   ```

2. **Check DynamoDB** for stored tokens:
   ```bash
   aws dynamodb scan --table-name agentcore-oauth-callback --region us-east-1
   ```

3. **Invoke a tool** that requires 3LO authentication and verify the OAuth flow completes successfully

## Cost Considerations

- **DynamoDB**: On-demand pricing, minimal cost (tokens expire after 10 minutes)
- **Lambda**: No additional cost for IAM policy changes
- **Secrets Manager**: Existing cost (no change)

## Security Notes

- Tokens are stored with 10-minute TTL and auto-deleted
- DynamoDB table uses encryption at rest (AWS managed keys)
- IAM permissions follow least-privilege principle
- Secrets Manager access is required by AgentCore, not directly by the Lambda
