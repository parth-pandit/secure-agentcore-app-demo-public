# Quick Start Guide

Get your Orders API with authentication deployed and tested in 10 minutes.

## Prerequisites Checklist

```bash
# Check all prerequisites
aws --version          # AWS CLI installed
python3 --version      # Python 3.7+
pip3 --version         # pip installed
aws sts get-caller-identity  # AWS credentials configured
```

## 5-Minute Deployment

### 1. Set Configuration

```bash
# Set these variables
export STACK_NAME="dev-orders-api"
export S3_BUCKET="your-s3-bucket-name"  # Change this!
export REGION="us-west-2"
```

### 2. Create S3 Bucket (if needed)

```bash
aws s3 mb s3://$S3_BUCKET --region $REGION
```

### 3. Package and Deploy

```bash
# Package Lambda functions
./infrastructure/scripts/package-lambdas.sh

# Deploy stack
./infrastructure/scripts/deploy-stack.sh \
  $STACK_NAME \
  $S3_BUCKET \
  dev \
  "https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys" \
  "https://login.microsoftonline.com/<TENANT_ID>/v2.0" \
  "<APPLICATION_ID>" \
  '{"user@yourdomain.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'
```

### 4. Get API URL

```bash
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

echo "API URL: $API_URL"
```

### 5. Test It!

```bash
# Generate token
cd tests/utils
export TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print('Bearer ' + gen.generate_token('user@yourdomain.com'))
")
cd ../..

# Test API
curl -X GET "$API_URL/orders" -H "Authorization: $TOKEN"
```

## Expected Results

✅ **Successful Response:**
```json
{
  "message": "Orders retrieved successfully",
  "count": 0,
  "orders": []
}
```

## Run All Tests

```bash
# Run automated test suite
pytest tests/ -v

# Expected: 296 passed, 1 skipped
```

## Run API Tests

```bash
# Create test script
cat > test_api.sh << 'EOF'
#!/bin/bash
set -e

cd tests/utils
VALID_TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('user@yourdomain.com'))")
cd ../..

echo "Testing API: $API_URL"

# Test 1: Valid token (should succeed)
echo -n "Test 1 - Valid token: "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_URL/orders" -H "Authorization: Bearer $VALID_TOKEN")
[ "$STATUS" = "200" ] && echo "✓ PASS" || echo "✗ FAIL (got $STATUS)"

# Test 2: No token (should fail)
echo -n "Test 2 - No token: "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_URL/orders")
[ "$STATUS" = "401" ] && echo "✓ PASS" || echo "✗ FAIL (got $STATUS)"

# Test 3: Invalid token (should fail)
echo -n "Test 3 - Invalid token: "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_URL/orders" -H "Authorization: Bearer invalid")
[ "$STATUS" = "401" ] && echo "✓ PASS" || echo "✗ FAIL (got $STATUS)"

echo "All tests completed!"
EOF

chmod +x test_api.sh
./test_api.sh
```

## View Logs

```bash
# Get function name
FUNC=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id LambdaAuthorizer \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# View logs
aws logs tail /aws/lambda/$FUNC --follow
```

## Troubleshooting

### Issue: "No such bucket"
```bash
# Create the bucket
aws s3 mb s3://$S3_BUCKET --region $REGION
```

### Issue: "ModuleNotFoundError"
```bash
# Install dependencies
pip3 install PyJWT cryptography requests boto3 pytest hypothesis moto
```

### Issue: "401 Unauthorized"
```bash
# Generate fresh token
cd tests/utils
python3 -c "from token_generator import MockTokenGenerator; print('Bearer ' + MockTokenGenerator().generate_token('user@yourdomain.com'))"
```

### Issue: "403 Forbidden"
```bash
# Check authorized users in stack parameters
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Parameters[?ParameterKey==`AuthorizedUsers`].ParameterValue'
```

## Cleanup

```bash
# Delete everything
aws cloudformation delete-stack --stack-name $STACK_NAME
aws s3 rm s3://$S3_BUCKET/lambda-code/ --recursive
```

## What's Next?

- 📖 Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions
- 🔐 Configure real Azure Entra ID: [docs/AUTHENTICATION_SETUP.md](docs/AUTHENTICATION_SETUP.md)
- 🧪 Explore testing scenarios: [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)
- 📊 Set up monitoring: [docs/MONITORING_AND_ALERTING.md](docs/MONITORING_AND_ALERTING.md)

## Success Checklist

- ✅ Stack deployed successfully
- ✅ API URL obtained
- ✅ Test token generated
- ✅ API responds to authenticated requests
- ✅ API rejects unauthenticated requests
- ✅ All tests passing
- ✅ Logs visible in CloudWatch

**You're ready to go! 🚀**
