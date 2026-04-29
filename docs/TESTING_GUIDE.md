# API Testing Guide

This guide provides practical instructions for testing the Orders API with Azure Entra ID authentication and authorization.

## Quick Start

### Prerequisites

- AWS account with the Orders API deployed
- Azure Entra ID tenant with application registered
- Python 3.7+ installed
- `curl` or Postman for making API requests
- Your AWS credentials configured

### 1. Get Your API Endpoint

```bash
# Get the API Gateway URL from CloudFormation
aws cloudformation describe-stacks \
  --stack-name <your-stack-name> \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text
```

Example output: `https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders`

### 2. Generate a Test Token

#### Option A: Mock Token (for local testing)

For local testing without Azure, use the mock token generator:

```bash
cd tests/utils
python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
token = gen.generate_token('user@yourdomain.com')
print(f'Bearer {token}')
"
```

**Important**: Mock tokens work for local testing but won't validate against real Azure Entra ID. For integration testing, use real Azure tokens.

#### Option B: Real Azure Token (recommended)

Generate a real Azure Entra ID token:

```bash
./tests/utils/generate_azure_token.sh
```

This script will guide you through:
1. Client Credentials Flow (requires client secret)
2. Device Code Flow (interactive browser authentication)
3. Azure CLI (if installed)

### 3. Test the API

```bash
# Set your API URL and token
export API_URL="https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>"
export TOKEN="Bearer eyJhbGc..."  # From step 2

# Test GET /orders
curl -X GET "$API_URL/orders" \
  -H "Authorization: $TOKEN"

# Test POST /orders
curl -X POST "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "order_date": "2025-01-05",
    "item_name": "Test Widget",
    "qty": 10,
    "status": "pending"
  }'

# Test PUT /orders
curl -X PUT "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "status": "completed"
  }'
```

## Testing with Real Azure Entra ID Tokens

### Step 1: Azure Entra ID Setup

Before testing with real tokens, ensure your Azure Entra ID application is configured:

1. **Application registered** in Azure Entra ID
2. **API permissions** granted (openid, email, profile)
3. **Admin consent** provided for permissions
4. **Token claims** configured (email, upn, preferred_username)
5. **Application ID** and **Tenant ID** noted

See [AUTHENTICATION_SETUP.md](./AUTHENTICATION_SETUP.md) for detailed setup instructions.

### Step 2: Obtain Azure Entra ID Token

#### Method 1: Using Azure CLI (Recommended)

```bash
# Login to Azure
az login

# Get access token for your application
az account get-access-token \
  --resource <YOUR-APPLICATION-ID> \
  --query accessToken \
  --output tsv
```

#### Method 2: Using Device Code Flow

```bash
# Run the token generator script
./tests/utils/generate_azure_token.sh

# Choose option 2 (Device Code Flow)
# Follow the prompts to authenticate in your browser
```

This will:
1. Display a device code
2. Open your browser to Azure login
3. Prompt you to enter the code
4. Return an access token after successful authentication

#### Method 3: Using Client Credentials Flow

```bash
# Run the token generator script
./tests/utils/generate_azure_token.sh

# Choose option 1 (Client Credentials Flow)
# Enter your Application ID and Client Secret
```

**Note**: This requires a client secret configured in your Azure application.

#### Method 4: Using OAuth 2.0 Authorization Code Flow

```bash
# Step 1: Get authorization code
# Open this URL in your browser (replace placeholders):
https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/authorize?client_id=<APPLICATION_ID>&response_type=code&scope=openid%20email%20profile&redirect_uri=<REDIRECT_URI>

# Step 2: Exchange code for token
curl -X POST https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "client_id=<APPLICATION_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "code=<AUTHORIZATION_CODE>" \
  -d "redirect_uri=<REDIRECT_URI>"
```

### Step 3: Verify Token Claims

Before testing, verify your token has the correct claims:

```bash
# Decode token (without verification)
echo "<YOUR_TOKEN>" | cut -d. -f2 | base64 -d 2>/dev/null | jq .
```

Expected claims:
```json
{
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "aud": "<APPLICATION_ID>",
  "email": "user@yourdomain.com",
  "exp": 1704470400,
  "iat": 1704466800
}
```

### Step 4: Test with Real Token

```bash
# Export the Azure token
export AZURE_TOKEN="eyJ0eXAiOiJ..."

# Test API
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $AZURE_TOKEN" \
  -v
```

## Testing Scenarios

### Scenario 1: Successful Authentication and Authorization

**Test**: Authorized user accessing allowed endpoint

```bash
# Generate token for authorized user (must be in AUTHORIZED_USERS config)
TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('user@yourdomain.com'))
")

# Make request
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -v
```

**Expected Result**:
- HTTP 200 OK
- JSON response with orders list
- CloudWatch logs show AUTHENTICATION_SUCCESS and AUTHORIZATION_ATTEMPT with ALLOW

**Verify in CloudWatch**:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/<authorizer-function-name> \
  --filter-pattern "AUTHORIZATION_SUCCESS" \
  --max-items 5
```

### Scenario 2: Missing Authentication Token

**Test**: Request without Authorization header

```bash
curl -X GET "$API_URL/orders" -v
```

**Expected Result**:
- HTTP 401 Unauthorized
- Error message: `{"message": "Unauthorized"}`
- CloudWatch logs show AUTHENTICATION_FAILURE with "Missing authorization token"

### Scenario 3: Invalid Token Format

**Test**: Request with malformed token

```bash
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer invalid-token-12345" \
  -v
```

**Expected Result**:
- HTTP 401 Unauthorized
- CloudWatch logs show AUTHENTICATION_FAILURE with "Invalid JWT format"

### Scenario 4: Expired Token

**Test**: Request with expired token

```bash
# Generate expired token
TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_expired_token('user@yourdomain.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -v
```

**Expected Result**:
- HTTP 401 Unauthorized
- CloudWatch logs show AUTHENTICATION_FAILURE with "Token expired"

### Scenario 5: Unauthorized User

**Test**: Valid token but user not in authorized list

```bash
# Generate token for user NOT in AUTHORIZED_USERS configuration
TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('unauthorized@example.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -v
```

**Expected Result**:
- HTTP 403 Forbidden
- Error message: `{"message": "User is not authorized to access this resource with an explicit deny"}`
- CloudWatch logs show AUTHENTICATION_SUCCESS but AUTHORIZATION_ATTEMPT with DENY

### Scenario 6: Wrong Issuer

**Test**: Token from wrong Azure tenant

```bash
# Generate token with wrong issuer
TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_wrong_issuer_token('user@yourdomain.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -v
```

**Expected Result**:
- HTTP 401 Unauthorized
- CloudWatch logs show AUTHENTICATION_FAILURE with "Invalid issuer"

### Scenario 7: Wrong Audience

**Test**: Token for different application

```bash
# Generate token with wrong audience
TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_wrong_audience_token('user@yourdomain.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -v
```

**Expected Result**:
- HTTP 401 Unauthorized
- CloudWatch logs show AUTHENTICATION_FAILURE with "Invalid audience"

### Scenario 8: Missing Required Permission

**Test**: User tries to access endpoint without permission

```bash
# Assume user only has GET permission, try POST
TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('readonly-user@yourdomain.com'))
")

curl -X POST "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"order_id":"test-001","item_name":"Test","qty":1,"status":"pending"}' \
  -v
```

**Expected Result**:
- HTTP 403 Forbidden
- CloudWatch logs show AUTHORIZATION_ATTEMPT with DENY

## Testing with Postman

### Setup

1. **Create New Collection**: "Orders API Tests"
2. **Set Collection Variables**:
   - `api_url`: Your API Gateway URL
   - `azure_tenant_id`: Your Azure Tenant ID
   - `azure_client_id`: Your Azure Application ID
   - `azure_client_secret`: Your Azure Client Secret (if using)

### Configure OAuth 2.0 Authorization

1. Go to Collection → Authorization
2. Select "OAuth 2.0"
3. Configure:
   - **Grant Type**: Authorization Code (or Device Code)
   - **Auth URL**: `https://login.microsoftonline.com/{{azure_tenant_id}}/oauth2/v2.0/authorize`
   - **Access Token URL**: `https://login.microsoftonline.com/{{azure_tenant_id}}/oauth2/v2.0/token`
   - **Client ID**: `{{azure_client_id}}`
   - **Client Secret**: `{{azure_client_secret}}`
   - **Scope**: `openid email profile`
4. Click "Get New Access Token"
5. Complete authentication in browser
6. Click "Use Token"

### Create Test Requests

#### GET Orders
```
GET {{api_url}}/orders
Authorization: Inherit from parent (OAuth 2.0)
```

**Tests** (in Tests tab):
```javascript
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

pm.test("Response has orders array", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('orders');
});
```

#### POST Order
```
POST {{api_url}}/orders
Authorization: Inherit from parent
Headers:
  Content-Type: application/json
Body (raw JSON):
{
  "order_id": "{{$randomUUID}}",
  "order_date": "{{$isoTimestamp}}",
  "item_name": "Test Item",
  "qty": 5,
  "status": "pending"
}
```

**Tests**:
```javascript
pm.test("Status code is 201", function () {
    pm.response.to.have.status(201);
});

pm.test("Order created successfully", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.message).to.include("created");
});
```

#### PUT Order
```
PUT {{api_url}}/orders
Authorization: Inherit from parent
Headers:
  Content-Type: application/json
Body (raw JSON):
{
  "order_id": "{{saved_order_id}}",
  "status": "completed"
}
```

### Test Different Scenarios

Create separate requests for error scenarios:

**No Token Test**:
```
GET {{api_url}}/orders
Authorization: No Auth
```
Expected: 401 Unauthorized

**Invalid Token Test**:
```
GET {{api_url}}/orders
Authorization: Bearer Token
Token: invalid-token-12345
```
Expected: 401 Unauthorized

## Automated Testing Script

Create a comprehensive test script:

```bash
#!/bin/bash
# test_api.sh - Automated API testing script

set -e

# Configuration
API_URL="${API_URL:-https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>}"
AUTHORIZED_USER="user@yourdomain.com"
UNAUTHORIZED_USER="unauthorized@example.com"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

echo "=========================================="
echo "Orders API Test Suite"
echo "=========================================="
echo "API URL: $API_URL"
echo "Authorized User: $AUTHORIZED_USER"
echo ""

# Helper function to run test
run_test() {
    local test_name="$1"
    local expected_code="$2"
    shift 2
    local response=$(curl -s -w "\n%{http_code}" "$@")
    local body=$(echo "$response" | head -n -1)
    local code=$(echo "$response" | tail -n 1)
    
    if [ "$code" == "$expected_code" ]; then
        echo -e "${GREEN}✓${NC} $test_name (HTTP $code)"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $test_name (Expected $expected_code, got $code)"
        echo "  Response: $body"
        ((FAILED++))
    fi
}

# Generate tokens
echo -e "${YELLOW}Generating test tokens...${NC}"
cd tests/utils
VALID_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('$AUTHORIZED_USER'))")
UNAUTHORIZED_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('$UNAUTHORIZED_USER'))")
EXPIRED_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_expired_token('$AUTHORIZED_USER'))")
INVALID_SIG_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_invalid_signature_token('$AUTHORIZED_USER'))")
WRONG_ISSUER_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_wrong_issuer_token('$AUTHORIZED_USER'))")
WRONG_AUD_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_wrong_audience_token('$AUTHORIZED_USER'))")
cd ../..
echo ""

# Authentication Tests
echo "Authentication Tests"
echo "--------------------"

run_test "No authentication token" "401" \
    -X GET "$API_URL/orders"

run_test "Invalid token format" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer invalid-token"

run_test "Expired token" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $EXPIRED_TOKEN"

run_test "Invalid signature" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $INVALID_SIG_TOKEN"

run_test "Wrong issuer" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $WRONG_ISSUER_TOKEN"

run_test "Wrong audience" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $WRONG_AUD_TOKEN"

echo ""

# Authorization Tests
echo "Authorization Tests"
echo "-------------------"

run_test "Unauthorized user" "403" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $UNAUTHORIZED_TOKEN"

echo ""

# Functional Tests
echo "Functional Tests"
echo "----------------"

run_test "GET /orders (authorized)" "200" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $VALID_TOKEN"

ORDER_ID="test-$(date +%s)"
run_test "POST /orders (authorized)" "201" \
    -X POST "$API_URL/orders" \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"order_id\":\"$ORDER_ID\",\"order_date\":\"2025-01-05\",\"item_name\":\"Test Item\",\"qty\":1,\"status\":\"pending\"}"

run_test "PUT /orders (authorized)" "200" \
    -X PUT "$API_URL/orders" \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"order_id\":\"$ORDER_ID\",\"status\":\"completed\"}"

run_test "GET specific order" "200" \
    -X GET "$API_URL/orders?order_id=$ORDER_ID" \
    -H "Authorization: Bearer $VALID_TOKEN"

echo ""
echo "=========================================="
echo "Test Results"
echo "=========================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo "Total:  $((PASSED + FAILED))"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
```

Make it executable and run:
```bash
chmod +x test_api.sh
export API_URL="https://your-api-id.execute-api.us-west-2.amazonaws.com/dev"
./test_api.sh
```

## Verifying Results

### Check API Response

**Successful GET response**:
```json
{
  "orders": [
    {
      "order_id": "test-001",
      "order_date": "2025-01-05",
      "item_name": "Widget",
      "qty": 10,
      "status": "pending"
    }
  ]
}
```

**Successful POST response**:
```json
{
  "message": "Order created successfully",
  "order": {
    "order_id": "test-001",
    "item_name": "Widget",
    "qty": 10,
    "status": "pending"
  }
}
```

**Error responses**:
```json
{
  "message": "Unauthorized"
}
```

```json
{
  "message": "User is not authorized to access this resource with an explicit deny"
}
```

### Check CloudWatch Logs

#### View Real-Time Logs
```bash
# Tail Lambda Authorizer logs
aws logs tail /aws/lambda/<authorizer-function-name> --follow

# Tail with filter
aws logs tail /aws/lambda/<authorizer-function-name> \
  --follow \
  --filter-pattern "AUTHENTICATION_FAILURE"
```

#### Search Historical Logs
```bash
# Search for specific user
aws logs filter-log-events \
  --log-group-name /aws/lambda/<authorizer-function-name> \
  --filter-pattern "user@yourdomain.com" \
  --max-items 10

# Search for authentication failures
aws logs filter-log-events \
  --log-group-name /aws/lambda/<authorizer-function-name> \
  --filter-pattern "AUTHENTICATION_FAILURE" \
  --start-time $(date -u -d '1 hour ago' +%s)000

# Search for authorization denials
aws logs filter-log-events \
  --log-group-name /aws/lambda/<authorizer-function-name> \
  --filter-pattern "DENY" \
  --max-items 10
```

#### Example Log Entries

**Successful authentication and authorization**:
```json
{
  "timestamp": "2025-01-05T12:00:00.000Z",
  "event_type": "AUTHENTICATION_SUCCESS",
  "service": "orders-api-authorizer",
  "user": {
    "email": "user@yourdomain.com"
  },
  "request_id": "abc-123-def"
}
```

```json
{
  "timestamp": "2025-01-05T12:00:00.100Z",
  "event_type": "AUTHORIZATION_SUCCESS",
  "service": "orders-api-authorizer",
  "user": {
    "email": "user@yourdomain.com"
  },
  "request": {
    "method": "GET",
    "resource": "/orders"
  },
  "result": "ALLOW"
}
```

**Failed authentication**:
```json
{
  "timestamp": "2025-01-05T12:00:00.000Z",
  "event_type": "AUTHENTICATION_FAILURE",
  "service": "orders-api-authorizer",
  "reason": "Token expired at 2025-01-05T11:00:00Z",
  "request_id": "xyz-789-abc"
}
```

### Check DynamoDB

```bash
# Scan orders table
aws dynamodb scan \
  --table-name <your-table-name> \
  --max-items 10

# Get specific order
aws dynamodb get-item \
  --table-name <your-table-name> \
  --key '{"order_id": {"S": "test-001"}}'

# Query by status
aws dynamodb query \
  --table-name <your-table-name> \
  --index-name StatusIndex \
  --key-condition-expression "status = :status" \
  --expression-attribute-values '{":status": {"S": "pending"}}'
```

## Performance Testing

### Authorization Caching Test

The Lambda Authorizer caches decisions for 5 minutes. Verify caching:

```bash
# Generate token
TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('user@yourdomain.com'))")

# First request - invokes authorizer
echo "First request (cold):"
time curl -s -o /dev/null -w "Time: %{time_total}s\n" \
  -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN"

# Subsequent requests - uses cache
echo "Second request (cached):"
time curl -s -o /dev/null -w "Time: %{time_total}s\n" \
  -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN"

echo "Third request (cached):"
time curl -s -o /dev/null -w "Time: %{time_total}s\n" \
  -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: Subsequent requests should be faster due to caching.

### Load Testing with Apache Bench

```bash
# Generate token
TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('user@yourdomain.com'))")

# Run load test (100 requests, 10 concurrent)
ab -n 100 -c 10 \
  -H "Authorization: Bearer $TOKEN" \
  "$API_URL/orders"
```

### Load Testing with wrk

```bash
# Install wrk (if not installed)
# macOS: brew install wrk
# Linux: apt-get install wrk

# Create Lua script for authorization header
cat > wrk-auth.lua << 'EOF'
wrk.method = "GET"
wrk.headers["Authorization"] = "Bearer YOUR_TOKEN_HERE"
EOF

# Run load test (10 threads, 100 connections, 30 seconds)
wrk -t10 -c100 -d30s -s wrk-auth.lua "$API_URL/orders"
```

## Troubleshooting

### Issue: 401 Unauthorized with valid Azure token

**Possible Causes**:
1. Token has expired
2. JWKS URL is incorrect in CloudFormation
3. Token issuer doesn't match configuration
4. Token audience doesn't match configuration

**Debug Steps**:
```bash
# 1. Decode token to check claims
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq .

# 2. Check CloudFormation parameters
aws cloudformation describe-stacks \
  --stack-name <your-stack-name> \
  --query 'Stacks[0].Parameters'

# 3. Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name <authorizer-function-name> \
  --query 'Environment.Variables'

# 4. Check CloudWatch logs for specific error
aws logs filter-log-events \
  --log-group-name /aws/lambda/<authorizer-function-name> \
  --filter-pattern "AUTHENTICATION_FAILURE" \
  --max-items 5
```

### Issue: 403 Forbidden with valid token

**Possible Causes**:
1. User email not in AUTHORIZED_USERS configuration
2. User doesn't have permission for the HTTP method
3. User doesn't have access to the resource

**Debug Steps**:
```bash
# 1. Check user email in token
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq '.email'

# 2. Check AUTHORIZED_USERS configuration
aws lambda get-function-configuration \
  --function-name <authorizer-function-name> \
  --query 'Environment.Variables.AUTHORIZED_USERS' \
  --output text | jq .

# 3. Check CloudWatch logs for authorization details
aws logs filter-log-events \
  --log-group-name /aws/lambda/<authorizer-function-name> \
  --filter-pattern "AUTHORIZATION" \
  --max-items 5
```

### Issue: Cannot generate Azure token

**Possible Causes**:
1. Azure application not configured correctly
2. User not assigned to application
3. API permissions not granted
4. Admin consent not provided

**Debug Steps**:
1. Verify application registration in Azure Portal
2. Check API permissions are granted
3. Verify admin consent is provided
4. Check user is assigned to application
5. Try different authentication flow (Device Code vs Client Credentials)

### Issue: Slow API responses

**Possible Causes**:
1. Lambda cold starts
2. DynamoDB throttling
3. Authorization caching not working
4. JWKS fetching on every request

**Debug Steps**:
```bash
# Check Lambda duration metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=<authorizer-function-name> \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum

# Check API Gateway latency
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Latency \
  --dimensions Name=ApiName,Value=<api-name> \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

### Issue: Mock tokens work but real Azure tokens don't

**Explanation**: Mock tokens bypass Azure Entra ID validation. Real tokens must:
1. Be signed by Azure Entra ID
2. Have correct issuer (Azure tenant)
3. Have correct audience (your Application ID)
4. Not be expired
5. Have required claims (email)

**Solution**: Use real Azure tokens for integration testing. Mock tokens are only for unit tests.

## Integration Testing Checklist

- [ ] Azure Entra ID application registered
- [ ] API permissions configured and granted
- [ ] Admin consent provided
- [ ] Test user assigned to application
- [ ] CloudFormation stack deployed with correct parameters
- [ ] JWKS URL accessible from Lambda
- [ ] Token issuer matches Azure tenant
- [ ] Token audience matches Application ID
- [ ] AUTHORIZED_USERS includes test user email
- [ ] Can generate real Azure tokens
- [ ] All authentication scenarios tested
- [ ] All authorization scenarios tested
- [ ] CloudWatch logs verified
- [ ] Performance testing completed
- [ ] Error handling verified

## Next Steps

1. ✅ Test all endpoints with mock tokens (local testing)
2. ✅ Test all endpoints with real Azure tokens (integration testing)
3. ✅ Test error scenarios (401, 403)
4. ✅ Verify audit logs in CloudWatch
5. ✅ Test authorization caching
6. ✅ Run performance tests
7. ✅ Set up monitoring dashboard
8. ✅ Configure CloudWatch alarms
9. ✅ Document test results
10. ✅ Integrate into CI/CD pipeline

## Additional Resources

- [Authentication Setup Guide](./AUTHENTICATION_SETUP.md) - Azure Entra ID configuration
- [API Documentation](./API_DOCUMENTATION.md) - Complete API reference
- [Monitoring Guide](./MONITORING_AND_ALERTING.md) - CloudWatch setup and incident response
- [Azure Entra ID Documentation](https://docs.microsoft.com/en-us/azure/active-directory/) - Official Azure docs
- [OAuth 2.0 Specification](https://oauth.net/2/) - OAuth 2.0 protocol details
