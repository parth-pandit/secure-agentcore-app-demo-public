# API Testing Quick Reference

## 🚀 Quick Start

### Step 1: Get Your API URL

```bash
STACK_NAME="secure-agentcore-app-dev-<suffix>"

export API_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --profile your-aws-profile \
  --region us-west-2 \
  --no-cli-pager \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

echo "API URL: $API_URL"
```

### Step 2: Get an Azure Token

```bash
export AZURE_TOKEN=$(bash tests/utils/generate_azure_token.sh)
```

Or using Azure CLI:

```bash
export AZURE_TOKEN=$(az account get-access-token \
  --resource <TargetIdpClientId> \
  --query accessToken --output tsv)
```

### Step 3: Run the Automated Test Suite

```bash
bash tests/utils/test_api_live.sh
```

---

## Manual curl Commands

### GET /orders

```bash
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" | jq
```

### POST /orders

```bash
curl -X POST "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "order_date": "2026-01-05",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }' | jq
```

### PUT /orders

```bash
curl -X PUT "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "status": "completed"
  }' | jq
```

---

## Test Scenarios

| Scenario | Command | Expected |
|---|---|---|
| No token | `curl $API_URL/orders` | 401 |
| Invalid token | `curl -H "Authorization: Bearer bad" $API_URL/orders` | 401 |
| Unauthorized user | Valid token, user not in AuthorizedUsers | 403 |
| Authorized GET | Valid token, authorized user | 200 |
| Authorized POST | Valid token, authorized user | 201 |
| Authorized PUT | Valid token, authorized user | 200 |

---

## Check CloudWatch Logs

```bash
FUNC="dev-orders-authorizer-<suffix>"

# Tail in real time
aws logs tail /aws/lambda/$FUNC --follow \
  --profile your-aws-profile --region us-west-2

# Search for failures
aws logs filter-log-events \
  --log-group-name /aws/lambda/$FUNC \
  --filter-pattern "AUTHENTICATION_FAILURE" \
  --profile your-aws-profile --region us-west-2 \
  --no-cli-pager
```

---

## Expected Responses

### Successful GET
```json
{
  "message": "Orders retrieved successfully",
  "count": 2,
  "orders": [...]
}
```

### Successful POST
```json
{
  "message": "Order created successfully",
  "order": { "order_id": "test-001", ... }
}
```

### 401 Unauthorized
```json
{ "message": "Unauthorized" }
```

### 403 Forbidden
```json
{ "message": "User is not authorized to access this resource with an explicit deny" }
```

---

## Related Documentation

- [Testing Guide](../../docs/TESTING_GUIDE.md)
- [Authentication Setup](../../docs/AUTHENTICATION_SETUP.md)
- [API Documentation](../../docs/API_DOCUMENTATION.md)
