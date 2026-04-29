# Complete Deployment Guide

This guide provides step-by-step instructions to deploy the Orders API with authentication and authorization to your AWS account and run tests.

## Prerequisites

Before you begin, ensure you have:

- ✅ AWS account with administrative access
- ✅ AWS CLI installed and configured (`aws --version`)
- ✅ Python 3.7+ installed (`python3 --version`)
- ✅ pip installed (`pip3 --version`)
- ✅ Git installed (to clone/access the repository)
- ✅ An S3 bucket for Lambda code storage

## Quick Start (5 Steps)

```bash
# 1. Package Lambda functions
./infrastructure/scripts/package-lambdas.sh

# 2. Deploy the stack
./infrastructure/scripts/deploy-stack.sh \
  dev-orders-api \
  your-s3-bucket-name \
  dev \
  "https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys" \
  "https://login.microsoftonline.com/<TENANT_ID>/v2.0" \
  "<APPLICATION_ID>" \
  '{"user@yourdomain.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'

# 3. Get your API URL
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name dev-orders-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

# 4. Run tests
cd tests/utils
python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
token = gen.generate_token('user@yourdomain.com')
print(f'Bearer {token}')
" > /tmp/token.txt

export TOKEN=$(cat /tmp/token.txt)

# 5. Test the API
curl -X GET "$API_URL/orders" -H "Authorization: $TOKEN"
```

## Detailed Deployment Steps

### Step 1: Verify Prerequisites

```bash
# Check AWS CLI
aws --version
# Expected: aws-cli/2.x.x or higher

# Check Python
python3 --version
# Expected: Python 3.7 or higher

# Check pip
pip3 --version

# Verify AWS credentials
aws sts get-caller-identity
# Should return your AWS account details
```

### Step 2: Create S3 Bucket (if needed)

If you don't have an S3 bucket for Lambda code:

```bash
# Replace with your desired bucket name
BUCKET_NAME="your-name-lambda-code-$(date +%Y%m%d)"
REGION="us-west-2"

# Create bucket
aws s3 mb s3://$BUCKET_NAME --region $REGION

# Enable versioning (recommended)
aws s3api put-bucket-versioning \
  --bucket $BUCKET_NAME \
  --versioning-configuration Status=Enabled

echo "Created bucket: $BUCKET_NAME"
```

### Step 3: Install Python Dependencies

```bash
# Install required Python packages
pip3 install PyJWT>=2.8.0 cryptography>=41.0.0 requests>=2.28.0 boto3

# Verify installation
python3 -c "import jwt; import cryptography; import requests; print('Dependencies OK')"
```

### Step 4: Package Lambda Functions

```bash
# Navigate to project root
cd /path/to/secure-agentcore-app-demo

# Make script executable
chmod +x infrastructure/scripts/package-lambdas.sh

# Run packaging script
./infrastructure/scripts/package-lambdas.sh
```

**Expected Output:**
```
Packaging Lambda functions...
Packaging get_orders...
✓ Created infrastructure/lambda-packages/get_orders.zip
Packaging create_order...
✓ Created infrastructure/lambda-packages/create_order.zip
Packaging update_order...
✓ Created infrastructure/lambda-packages/update_order.zip
Packaging authorizer (with dependencies)...
Installing dependencies for authorizer...
✓ Created infrastructure/lambda-packages/authorizer.zip

All Lambda functions packaged successfully!
```

### Step 5: Deploy CloudFormation Stack

```bash
# Set your configuration
STACK_NAME="dev-orders-api"
S3_BUCKET="your-s3-bucket-name"
ENVIRONMENT="dev"

# For initial testing, use mock values
JWKS_URL="https://mock-jwks-url.example.com/jwks"
TOKEN_ISSUER="https://mock-issuer.example.com"
TOKEN_AUDIENCE="orders-api"
AUTHORIZED_USERS='{"user@yourdomain.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'

# Make deploy script executable
chmod +x infrastructure/scripts/deploy-stack.sh

# Deploy the stack
./infrastructure/scripts/deploy-stack.sh \
  "$STACK_NAME" \
  "$S3_BUCKET" \
  "$ENVIRONMENT" \
  "$JWKS_URL" \
  "$TOKEN_ISSUER" \
  "$TOKEN_AUDIENCE" \
  "$AUTHORIZED_USERS"
```

**Expected Output:**
```
Deploying CloudFormation stack: dev-orders-api
Environment: dev
S3 Bucket: your-s3-bucket-name
...
Uploading Lambda packages to S3...
Deploying CloudFormation stack...

Waiting for changeset to be created...
Waiting for stack create/update to complete...
Successfully created/updated stack - dev-orders-api

Stack deployment complete!
```

### Step 6: Get API Endpoint

```bash
# Get the API URL from CloudFormation outputs
aws cloudformation describe-stacks \
  --stack-name dev-orders-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text

# Save it to environment variable
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name dev-orders-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

echo "API URL: $API_URL"
# Example: https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>
```

### Step 7: Generate Test Token

```bash
# Navigate to test utilities
cd tests/utils

# Generate a test token for authorized user
python3 << 'EOF'
from token_generator import MockTokenGenerator

gen = MockTokenGenerator()
token = gen.generate_token('user@example.com')
print(f"\nYour test token:")
print(f"Bearer {token}")
print(f"\nExport command:")
print(f'export TOKEN="Bearer {token}"')
EOF

# Copy the export command from output and run it
# export TOKEN="Bearer eyJhbGc..."
```

### Step 8: Test the API

#### Test 1: GET Orders (Should succeed)

```bash
curl -X GET "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -v
```

**Expected Response:**
- HTTP 200 OK
- JSON response with orders list

#### Test 2: POST Order (Should succeed)

```bash
curl -X POST "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "order_date": "2025-12-30",
    "item_name": "Test Widget",
    "qty": 10,
    "status": "pending"
  }' \
  -v
```

**Expected Response:**
- HTTP 201 Created
- JSON response confirming order creation

#### Test 3: PUT Order (Should succeed)

```bash
curl -X PUT "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-001",
    "status": "completed"
  }' \
  -v
```

**Expected Response:**
- HTTP 200 OK
- JSON response confirming order update

#### Test 4: No Token (Should fail with 401)

```bash
curl -X GET "$API_URL/orders" -v
```

**Expected Response:**
- HTTP 401 Unauthorized
- Error message: "Unauthorized"

#### Test 5: Invalid Token (Should fail with 401)

```bash
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer invalid-token-12345" \
  -v
```

**Expected Response:**
- HTTP 401 Unauthorized

#### Test 6: Unauthorized User (Should fail with 403)

```bash
# Generate token for unauthorized user
cd tests/utils
UNAUTH_TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('unauthorized@example.com'))
")

curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer $UNAUTH_TOKEN" \
  -v
```

**Expected Response:**
- HTTP 403 Forbidden
- Error message about explicit deny

### Step 9: Run Automated Test Suite

```bash
# Navigate to project root
cd /path/to/secure-agentcore-app-demo

# Run all tests
pytest tests/ -v

# Run specific test categories
pytest tests/unit/ -v                    # Unit tests only
pytest tests/integration/ -v             # Integration tests only
pytest tests/unit/test_audit_logging_properties.py -v  # Property tests
```

**Expected Output:**
```
======================== test session starts =========================
collected 296 items

tests/unit/test_audit_logging.py ...................... [ 7%]
tests/unit/test_authorization_policy.py ............... [12%]
tests/unit/test_token_validation.py ................... [18%]
...

===================== 296 passed, 1 skipped in 6.20s ================
```

### Step 10: Run Automated API Test Script

```bash
# Create and run the automated test script
cat > test_api.sh << 'SCRIPT_EOF'
#!/bin/bash
set -e

# Configuration
API_URL="${API_URL:-}"
if [ -z "$API_URL" ]; then
    echo "Error: API_URL not set"
    echo "Run: export API_URL=<your-api-url>"
    exit 1
fi

AUTHORIZED_USER="user@yourdomain.com"
UNAUTHORIZED_USER="unauthorized@example.com"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

PASSED=0
FAILED=0

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

echo "Testing Orders API: $API_URL"
echo "================================"
echo

# Generate tokens
cd tests/utils
VALID_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('$AUTHORIZED_USER'))")
UNAUTHORIZED_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('$UNAUTHORIZED_USER'))")
EXPIRED_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_expired_token('$AUTHORIZED_USER'))")
cd ../..

# Run tests
run_test "No authentication token" "401" \
    -X GET "$API_URL/orders"

run_test "Invalid token format" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer invalid-token"

run_test "Expired token" "401" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $EXPIRED_TOKEN"

run_test "Unauthorized user" "403" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $UNAUTHORIZED_TOKEN"

run_test "GET /orders (authorized)" "200" \
    -X GET "$API_URL/orders" \
    -H "Authorization: Bearer $VALID_TOKEN"

run_test "POST /orders (authorized)" "201" \
    -X POST "$API_URL/orders" \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"order_id":"test-'$(date +%s)'","order_date":"2025-12-30","item_name":"Test","qty":1,"status":"pending"}'

run_test "PUT /orders (authorized)" "200" \
    -X PUT "$API_URL/orders" \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"order_id":"test-'$(date +%s)'","status":"completed"}'

echo
echo "================================"
echo "Results: $PASSED passed, $FAILED failed"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
SCRIPT_EOF

# Make executable and run
chmod +x test_api.sh
./test_api.sh
```

**Expected Output:**
```
Testing Orders API: https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>
================================

✓ No authentication token (HTTP 401)
✓ Invalid token format (HTTP 401)
✓ Expired token (HTTP 401)
✓ Unauthorized user (HTTP 403)
✓ GET /orders (authorized) (HTTP 200)
✓ POST /orders (authorized) (HTTP 201)
✓ PUT /orders (authorized) (HTTP 200)

================================
Results: 7 passed, 0 failed
All tests passed!
```

### Step 11: Verify CloudWatch Logs

```bash
# Get Lambda Authorizer function name
AUTHORIZER_FUNCTION=$(aws cloudformation describe-stack-resources \
  --stack-name dev-orders-api \
  --logical-resource-id LambdaAuthorizer \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# View recent logs
aws logs tail /aws/lambda/$AUTHORIZER_FUNCTION --follow

# Search for authentication successes
aws logs filter-log-events \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --filter-pattern "AUTHENTICATION_SUCCESS" \
  --max-items 5

# Search for authorization attempts
aws logs filter-log-events \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --filter-pattern "AUTHORIZATION_ATTEMPT" \
  --max-items 5
```

### Step 12: Set Up Monitoring (Optional)

```bash
# Get API ID
API_ID=$(aws cloudformation describe-stack-resources \
  --stack-name dev-orders-api \
  --logical-resource-id OrdersApi \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# Create CloudWatch dashboard
python3 infrastructure/monitoring/create_dashboard.py \
  --stack-name dev-orders-api \
  --region us-west-2 \
  --api-id $API_ID \
  --authorizer-function-name $AUTHORIZER_FUNCTION

# Create CloudWatch alarms (optional - requires SNS topic)
# python3 infrastructure/monitoring/create_alarms.py \
#   --stack-name dev-orders-api \
#   --region us-west-2 \
#   --authorizer-function-name $AUTHORIZER_FUNCTION \
#   --sns-topic-arn arn:aws:sns:us-west-2:123456789012:alerts
```

## Troubleshooting

### Issue: Package script fails

**Error:** `pip: command not found`

**Solution:**
```bash
# Install pip
python3 -m ensurepip --upgrade

# Or use pip3
which pip3
```

### Issue: Deploy script fails with S3 error

**Error:** `An error occurred (NoSuchBucket) when calling the PutObject operation`

**Solution:**
```bash
# Verify bucket exists
aws s3 ls s3://your-bucket-name

# Create bucket if needed
aws s3 mb s3://your-bucket-name --region us-west-2
```

### Issue: API returns 401 even with valid token

**Possible Causes:**
1. Token expired (tokens are valid for 1 hour by default)
2. JWKS URL not accessible
3. Token issuer/audience mismatch

**Solution:**
```bash
# Generate a fresh token
cd tests/utils
python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('user@yourdomain.com'))"

# Check CloudWatch logs for details
aws logs tail /aws/lambda/$AUTHORIZER_FUNCTION --follow
```

### Issue: API returns 403 Forbidden

**Cause:** User not in authorized users list

**Solution:**
```bash
# Update stack with correct authorized users
./infrastructure/scripts/deploy-stack.sh \
  dev-orders-api \
  your-s3-bucket-name \
  dev \
  "$JWKS_URL" \
  "$TOKEN_ISSUER" \
  "$TOKEN_AUDIENCE" \
  '{"your-email@example.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'
```

### Issue: Tests fail with import errors

**Error:** `ModuleNotFoundError: No module named 'jwt'`

**Solution:**
```bash
# Install test dependencies
pip3 install -r backend/src/lambdas/requirements.txt
pip3 install pytest hypothesis boto3 moto
```

## Cleanup

To remove all deployed resources:

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name dev-orders-api

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete --stack-name dev-orders-api

# Delete Lambda packages from S3
aws s3 rm s3://your-bucket-name/lambda-code/ --recursive

# Delete monitoring resources (if created)
aws cloudwatch delete-dashboards --dashboard-names dev-orders-api-auth-monitoring

# Delete alarms
aws cloudwatch delete-alarms --alarm-names \
  dev-orders-api-high-auth-failures \
  dev-orders-api-authorization-errors \
  dev-orders-api-lambda-errors \
  dev-orders-api-unusual-access-pattern \
  dev-orders-api-lambda-throttles
```

## Next Steps

1. ✅ Deploy to your AWS account
2. ✅ Run tests to verify functionality
3. ✅ Set up monitoring dashboard
4. ⬜ Configure real Azure Entra ID (see [AUTHENTICATION_SETUP.md](docs/AUTHENTICATION_SETUP.md))
5. ⬜ Integrate with your application
6. ⬜ Set up CI/CD pipeline
7. ⬜ Configure production environment

## Additional Resources

- [Authentication Setup Guide](docs/AUTHENTICATION_SETUP.md) - Configure Azure Entra ID
- [Testing Guide](docs/TESTING_GUIDE.md) - Comprehensive testing scenarios
- [Monitoring Guide](docs/MONITORING_AND_ALERTING.md) - CloudWatch setup and incident response
- [API Documentation](docs/API_DOCUMENTATION.md) - Complete API reference

## Support

If you encounter issues:

1. Check CloudWatch Logs: `/aws/lambda/<function-name>`
2. Review CloudFormation events in AWS Console
3. Verify all prerequisites are met
4. Check AWS service quotas and limits
5. Review the troubleshooting section above

## Summary

You've successfully:
- ✅ Packaged Lambda functions with dependencies
- ✅ Deployed CloudFormation stack with authentication
- ✅ Generated test tokens
- ✅ Tested all API endpoints
- ✅ Verified authentication and authorization
- ✅ Checked audit logs in CloudWatch
- ✅ Set up monitoring (optional)

Your Orders API is now secured with JWT authentication and role-based authorization!
