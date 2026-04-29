# API Testing Quick Reference

## 🚀 Quick Start

### Option 1: Automated Testing Script (Recommended)

```bash
# Make the script executable
chmod +x test_api_live.sh

# Run the script
./test_api_live.sh
```

The script will:
1. ✅ Automatically find your API URL from CloudFormation
2. ✅ Generate test tokens
3. ✅ Run 8 comprehensive tests
4. ✅ Show you manual testing commands

### Option 2: Browser Testing (Visual)

```bash
# Open the HTML file in your browser
open test_api_browser.html
# or on Linux: xdg-open test_api_browser.html
```

Then:
1. Enter your API URL
2. Generate or paste a token
3. Click buttons to test different scenarios
4. See responses in real-time

### Option 3: Manual curl Commands

#### Step 1: Get Your API URL

```bash
# Replace with your stack name
STACK_NAME="dev-orders-api"

# Get API URL
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

echo "API URL: $API_URL"
```

#### Step 2: Generate a Test Token

```bash
# Generate token for authorized user
cd tests/utils
export TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('user@example.com'))
")
cd ../..

echo "Token: $TOKEN"
```

#### Step 3: Test the API

```bash
# Test GET /orders
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq

# Test POST /orders
curl -X POST "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD-001",
    "order_date": "2025-01-05",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }' | jq

# Test PUT /orders
curl -X PUT "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD-001",
    "status": "completed"
  }' | jq
```

## 🧪 Test Scenarios

### ✅ Successful Requests (200/201)

```bash
# Valid token, authorized user
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:** HTTP 200, JSON response with orders

### ❌ Authentication Failures (401)

```bash
# No token
curl -X GET "$API_URL/orders"

# Invalid token
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer invalid-token"

# Expired token
EXPIRED_TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_expired_token('user@example.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $EXPIRED_TOKEN"
```

**Expected:** HTTP 401 Unauthorized

### 🚫 Authorization Failures (403)

```bash
# Valid token but unauthorized user
UNAUTH_TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('unauthorized@example.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $UNAUTH_TOKEN"
```

**Expected:** HTTP 403 Forbidden

## 📊 Verify Results

### Check API Response

```bash
# Pretty print with jq
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" | jq

# Show HTTP status code
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nHTTP Status: %{http_code}\n"

# Show full response with headers
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -v
```

### Check CloudWatch Logs

```bash
# Get Lambda function name
FUNC=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id LambdaAuthorizer \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# View logs in real-time
aws logs tail /aws/lambda/$FUNC --follow

# Search for specific user
aws logs filter-log-events \
  --log-group-name /aws/lambda/$FUNC \
  --filter-pattern "user@example.com"

# Search for authentication failures
aws logs filter-log-events \
  --log-group-name /aws/lambda/$FUNC \
  --filter-pattern "AUTHENTICATION_FAILURE"
```

### Check DynamoDB

```bash
# Get table name
TABLE=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id OrdersTable \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# Scan table
aws dynamodb scan --table-name $TABLE --max-items 10

# Get specific order
aws dynamodb get-item \
  --table-name $TABLE \
  --key '{"order_id": {"S": "ORD-001"}}'
```

## 🔧 Troubleshooting

### Issue: "Could not find API URL"

```bash
# List all stacks
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# Check stack outputs
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs'
```

### Issue: "ModuleNotFoundError: No module named 'token_generator'"

```bash
# Make sure you're in the project root
pwd

# Check if file exists
ls tests/utils/token_generator.py

# Install dependencies
pip3 install PyJWT cryptography
```

### Issue: "401 Unauthorized with valid token"

This usually means the Lambda Authorizer is rejecting the token. Check:

```bash
# View authorizer logs
aws logs tail /aws/lambda/$FUNC --follow

# Common causes:
# 1. Token signature doesn't match JWKS
# 2. Token issuer doesn't match configuration
# 3. Token audience doesn't match configuration
# 4. Token has expired
```

### Issue: "403 Forbidden"

This means authentication succeeded but authorization failed. Check:

```bash
# View authorized users configuration
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Parameters[?ParameterKey==`AuthorizedUsers`].ParameterValue' \
  --output text

# Make sure your user email is in the list
```

### Issue: CORS errors in browser

If testing from browser and getting CORS errors:

1. Check API Gateway CORS configuration
2. Make sure OPTIONS method is enabled
3. Verify CORS headers are returned

## 📝 Example Test Session

```bash
# Complete test session
export STACK_NAME="dev-orders-api"
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

cd tests/utils
export TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('user@example.com'))
")
cd ../..

echo "Testing API: $API_URL"

# Test 1: GET orders
echo "Test 1: GET /orders"
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -w "\nStatus: %{http_code}\n\n"

# Test 2: POST order
echo "Test 2: POST /orders"
curl -X POST "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "TEST-001",
    "order_date": "2025-01-05",
    "item_name": "Test Widget",
    "qty": 10,
    "status": "pending"
  }' \
  -w "\nStatus: %{http_code}\n\n"

# Test 3: PUT order
echo "Test 3: PUT /orders"
curl -X PUT "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "TEST-001",
    "status": "completed"
  }' \
  -w "\nStatus: %{http_code}\n\n"

# Test 4: Verify update
echo "Test 4: Verify update"
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" | jq '.orders[] | select(.order_id=="TEST-001")'
```

## 🎯 Expected Results

### Successful GET Request
```json
{
  "message": "Orders retrieved successfully",
  "count": 2,
  "orders": [
    {
      "order_id": "ORD-001",
      "order_date": "2025-01-05",
      "item_name": "Widget",
      "qty": 5,
      "status": "pending"
    }
  ]
}
```

### Successful POST Request
```json
{
  "message": "Order created successfully",
  "order": {
    "order_id": "ORD-001",
    "order_date": "2025-01-05",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }
}
```

### Successful PUT Request
```json
{
  "message": "Order updated successfully",
  "order": {
    "order_id": "ORD-001",
    "status": "completed"
  }
}
```

### Authentication Failure (401)
```json
{
  "message": "Unauthorized"
}
```

### Authorization Failure (403)
```json
{
  "message": "User is not authorized to access this resource with an explicit deny"
}
```

## 🔗 Related Documentation

- **Full Testing Guide:** `docs/TESTING_GUIDE.md`
- **Authentication Setup:** `docs/AUTHENTICATION_SETUP.md`
- **API Documentation:** `docs/API_DOCUMENTATION.md`
- **Deployment Guide:** `DEPLOYMENT_GUIDE.md`

## 💡 Tips

1. **Use jq for pretty JSON:** Install with `brew install jq` (Mac) or `apt-get install jq` (Linux)
2. **Save tokens as environment variables** to avoid typing them repeatedly
3. **Use the automated script** for comprehensive testing
4. **Check CloudWatch logs** when debugging issues
5. **Test all scenarios** (success, auth failure, authz failure) to ensure security

## 🎉 Success Checklist

- ✅ API URL obtained from CloudFormation
- ✅ Test token generated successfully
- ✅ GET request returns 200 OK
- ✅ POST request creates order (201 Created)
- ✅ PUT request updates order (200 OK)
- ✅ No token returns 401 Unauthorized
- ✅ Invalid token returns 401 Unauthorized
- ✅ Unauthorized user returns 403 Forbidden
- ✅ CloudWatch logs show authentication/authorization events
- ✅ DynamoDB contains created/updated orders

**You're all set! 🚀**
