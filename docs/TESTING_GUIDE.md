# API Testing Guide

This guide covers how to test the Orders API and the end-to-end agentic application.

## Prerequisites

- Stack deployed (see root `README.md`)
- Azure Entra ID application configured
- AWS CLI configured with your profile

## Get Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name secure-agentcore-app-dev-<suffix> \
  --profile your-aws-profile \
  --region us-west-2 \
  --no-cli-pager \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
  --output table
```

Key outputs you'll need:
- `ApiUrl` — Orders API base URL
- `AgentProxyFunctionUrl` — Agent Proxy endpoint (append `/invoke`)
- `CloudFrontDomainName` — Frontend URL

---

## 1. Obtain an Azure Entra ID Token

All API requests require a valid JWT from Azure Entra ID.

### Using the provided script

```bash
bash tests/utils/generate_azure_token.sh
```

Follow the prompts to authenticate via Device Code Flow or Client Credentials.

### Using Azure CLI

```bash
az login
az account get-access-token --resource <TargetIdpClientId> --query accessToken --output tsv
```

Export the token:

```bash
export AZURE_TOKEN="eyJ0eXAiOiJ..."
export API_URL="https://<api-id>.execute-api.us-west-2.amazonaws.com/dev"
```

---

## 2. Test the Orders API Directly

### GET — Retrieve all orders

```bash
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  --no-cli-pager
```

**Expected:** HTTP 200, JSON with orders list.

### POST — Create an order

```bash
curl -X POST "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "order_date": "2026-01-05",
    "item_name": "Test Widget",
    "qty": 5,
    "status": "pending"
  }'
```

**Expected:** HTTP 201, order created.

### PUT — Update an order

```bash
curl -X PUT "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "status": "completed"
  }'
```

**Expected:** HTTP 200, order updated.

---

## 3. Test Authentication and Authorization Scenarios

### No token → 401

```bash
curl -X GET "$API_URL/orders"
```

### Invalid token → 401

```bash
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer invalid-token-12345"
```

### Unauthorized user → 403

Use a valid Azure token for a user whose email is **not** in the `AuthorizedUsers` parameter. The response should be HTTP 403.

---

## 4. Test the Full Agent Flow

The agent is invoked via the Agent Proxy Lambda. The frontend does this automatically, but you can also call it directly:

```bash
AGENT_ENDPOINT="https://<api-id>.execute-api.us-west-2.amazonaws.com/invoke"

curl -X POST "$AGENT_ENDPOINT" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Get all orders",
    "auth_token": "Bearer '"$AZURE_TOKEN"'"
  }'
```

**Expected:** JSON response with `result` containing the agent's answer, and optionally `auth_url` if the 3LO OAuth flow needs to be completed.

### 3LO OAuth Flow

If the agent returns an `auth_url`, open it in a browser to authorize the agent to access the Orders API on your behalf. After authorization, retry the request — the agent will use the cached OAuth token.

---

## 5. Live API Test Script

```bash
bash tests/utils/test_api_live.sh
```

This script runs 8 tests covering authentication, authorization, and CRUD operations. It auto-discovers the API URL from CloudFormation.

---

## 6. Integration Tests

```bash
cd tests/integration
python test_api_with_authentication.py
```

---

## 7. Verify in CloudWatch

```bash
# Get authorizer function name from stack outputs
FUNC="dev-orders-authorizer-<suffix>"

# Tail logs in real time
aws logs tail /aws/lambda/$FUNC --follow --profile your-aws-profile --region us-west-2

# Search for authentication failures
aws logs filter-log-events \
  --log-group-name /aws/lambda/$FUNC \
  --filter-pattern "AUTHENTICATION_FAILURE" \
  --profile your-aws-profile \
  --region us-west-2 \
  --no-cli-pager
```

---

## Related Documentation

- [Authentication Setup Guide](./AUTHENTICATION_SETUP.md) — Azure Entra ID configuration
- [API Documentation](./API_DOCUMENTATION.md) — Complete API reference
- [Monitoring Guide](./MONITORING_AND_ALERTING.md) — CloudWatch setup
