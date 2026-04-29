# Command Reference

Quick reference for all deployment and testing commands.

## Environment Setup

```bash
# Set your configuration
export STACK_NAME="dev-orders-api"
export S3_BUCKET="your-bucket-name"
export REGION="us-west-2"
export ENVIRONMENT="dev"
```

## Deployment Commands

### Package Lambda Functions

```bash
# Make executable
chmod +x infrastructure/scripts/package-lambdas.sh

# Package all Lambda functions
./infrastructure/scripts/package-lambdas.sh
```

### Deploy Stack

```bash
# Make executable
chmod +x infrastructure/scripts/deploy-stack.sh

# Deploy with Azure Entra ID
./infrastructure/scripts/deploy-stack.sh \
  $STACK_NAME \
  $S3_BUCKET \
  $ENVIRONMENT \
  "https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys" \
  "https://login.microsoftonline.com/<TENANT_ID>/v2.0" \
  "<APPLICATION_ID>" \
  '{"user@yourdomain.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'
```

### Get Stack Information

```bash
# Get all stack outputs
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs' \
  --output table

# Get API URL
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

# Get DynamoDB table name
export TABLE_NAME=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`TableName`].OutputValue' \
  --output text)

# Get Lambda Authorizer function name
export AUTHORIZER_FUNCTION=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id LambdaAuthorizer \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# Get API Gateway ID
export API_ID=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id OrdersApi \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)
```

## Token Generation

### Generate Valid Token

```bash
cd tests/utils
export TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print('Bearer ' + gen.generate_token('user@yourdomain.com'))
")
cd ../..
echo "Token: $TOKEN"
```

### Generate Expired Token

```bash
cd tests/utils
export EXPIRED_TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print('Bearer ' + gen.generate_expired_token('user@yourdomain.com'))
")
cd ../..
```

### Generate Unauthorized User Token

```bash
cd tests/utils
export UNAUTH_TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print('Bearer ' + gen.generate_token('unauthorized@example.com'))
")
cd ../..
```

### Generate Invalid Signature Token

```bash
cd tests/utils
export INVALID_TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print('Bearer ' + gen.generate_invalid_signature_token('user@yourdomain.com'))
")
cd ../..
```

## API Testing Commands

### GET Orders

```bash
# With authentication (should succeed)
curl -X GET "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -v

# Without authentication (should fail)
curl -X GET "$API_URL/orders" -v

# With invalid token (should fail)
curl -X GET "$API_URL/orders" \
  -H "Authorization: Bearer invalid-token" \
  -v
```

### POST Order

```bash
curl -X POST "$API_URL/orders" \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "test-'$(date +%s)'",
    "order_date": "2025-12-30",
    "item_name": "Test Widget",
    "qty": 10,
    "status": "pending"
  }' \
  -v
```

### PUT Order

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

## Test Suite Commands

### Run All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=backend/src/lambdas --cov-report=html

# Run specific test file
pytest tests/unit/test_token_validation.py -v

# Run specific test
pytest tests/unit/test_token_validation.py::TestTokenValidation::test_valid_token -v
```

### Run Test Categories

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Property-based tests only
pytest tests/unit/test_audit_logging_properties.py -v
pytest tests/unit/test_token_validation_properties.py -v
pytest tests/unit/test_authorization_properties.py -v
```

### Run Tests with Filters

```bash
# Run tests matching pattern
pytest tests/ -k "authentication" -v

# Run tests with specific marker
pytest tests/ -m "integration" -v

# Run failed tests only
pytest tests/ --lf -v
```

## CloudWatch Logs Commands

### View Logs

```bash
# Tail Lambda Authorizer logs
aws logs tail /aws/lambda/$AUTHORIZER_FUNCTION --follow

# Tail with filter
aws logs tail /aws/lambda/$AUTHORIZER_FUNCTION \
  --follow \
  --filter-pattern "AUTHENTICATION_FAILURE"

# View last 100 lines
aws logs tail /aws/lambda/$AUTHORIZER_FUNCTION --since 10m
```

### Search Logs

```bash
# Search for authentication failures
aws logs filter-log-events \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --filter-pattern "AUTHENTICATION_FAILURE" \
  --max-items 10

# Search for specific user
aws logs filter-log-events \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --filter-pattern "user@yourdomain.com" \
  --max-items 10

# Search for authorization denials
aws logs filter-log-events \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --filter-pattern "AUTHORIZATION_ATTEMPT" \
  --max-items 10
```

### CloudWatch Logs Insights Queries

```bash
# Authentication failures by reason
aws logs start-query \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --start-time $(date -u -d '1 hour ago' +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, @message
    | filter @message like /AUTHENTICATION_FAILURE/
    | parse @message /reason: "(?<reason>[^"]+)"/
    | stats count() by reason'

# Authorization denials by user
aws logs start-query \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION \
  --start-time $(date -u -d '1 hour ago' +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, @message
    | filter @message like /AUTHORIZATION_ATTEMPT/ and @message like /DENY/
    | parse @message /user_email: "(?<user>[^"]+)"/
    | stats count() by user'
```

## Monitoring Commands

### Create Dashboard

```bash
python3 infrastructure/monitoring/create_dashboard.py \
  --stack-name $STACK_NAME \
  --region $REGION \
  --api-id $API_ID \
  --authorizer-function-name $AUTHORIZER_FUNCTION
```

### Create Alarms

```bash
# Without SNS notifications
python3 infrastructure/monitoring/create_alarms.py \
  --stack-name $STACK_NAME \
  --region $REGION \
  --authorizer-function-name $AUTHORIZER_FUNCTION

# With SNS notifications
python3 infrastructure/monitoring/create_alarms.py \
  --stack-name $STACK_NAME \
  --region $REGION \
  --authorizer-function-name $AUTHORIZER_FUNCTION \
  --sns-topic-arn arn:aws:sns:$REGION:123456789012:alerts
```

### View Metrics

```bash
# Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=$AUTHORIZER_FUNCTION \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=$AUTHORIZER_FUNCTION \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Lambda duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=$AUTHORIZER_FUNCTION \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

## DynamoDB Commands

### Scan Table

```bash
# Scan all items
aws dynamodb scan --table-name $TABLE_NAME

# Scan with limit
aws dynamodb scan --table-name $TABLE_NAME --max-items 10

# Count items
aws dynamodb scan \
  --table-name $TABLE_NAME \
  --select COUNT \
  --query 'Count'
```

### Query Items

```bash
# Get specific order
aws dynamodb get-item \
  --table-name $TABLE_NAME \
  --key '{"order_id": {"S": "test-001"}}'

# Query by order_date (using GSI)
aws dynamodb query \
  --table-name $TABLE_NAME \
  --index-name OrderDateIndex \
  --key-condition-expression "order_date = :date" \
  --expression-attribute-values '{":date": {"S": "2025-12-30"}}'
```

### Put Item

```bash
aws dynamodb put-item \
  --table-name $TABLE_NAME \
  --item '{
    "order_id": {"S": "test-001"},
    "order_date": {"S": "2025-12-30"},
    "item_name": {"S": "Test Widget"},
    "qty": {"N": "10"},
    "status": {"S": "pending"}
  }'
```

## Stack Management Commands

### Update Stack

```bash
# Update with new parameters
aws cloudformation update-stack \
  --stack-name $STACK_NAME \
  --use-previous-template \
  --parameters \
    ParameterKey=Environment,ParameterValue=$ENVIRONMENT \
    ParameterKey=LambdaCodeBucket,ParameterValue=$S3_BUCKET \
    ParameterKey=AuthorizedUsers,ParameterValue='{"newuser@example.com":{"permissions":["GET"],"resources":["*"]}}'
```

### View Stack Events

```bash
# View recent events
aws cloudformation describe-stack-events \
  --stack-name $STACK_NAME \
  --max-items 20

# Watch events in real-time
watch -n 5 'aws cloudformation describe-stack-events \
  --stack-name $STACK_NAME \
  --max-items 10 \
  --output table'
```

### Delete Stack

```bash
# Delete stack
aws cloudformation delete-stack --stack-name $STACK_NAME

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME

# Verify deletion
aws cloudformation describe-stacks --stack-name $STACK_NAME
```

## S3 Commands

### Upload Lambda Packages

```bash
# Upload all packages
aws s3 cp infrastructure/lambda-packages/ \
  s3://$S3_BUCKET/lambda-code/ \
  --recursive \
  --exclude "*" \
  --include "*.zip"

# Upload specific package
aws s3 cp infrastructure/lambda-packages/authorizer.zip \
  s3://$S3_BUCKET/lambda-code/authorizer.zip
```

### List Lambda Packages

```bash
aws s3 ls s3://$S3_BUCKET/lambda-code/
```

### Delete Lambda Packages

```bash
aws s3 rm s3://$S3_BUCKET/lambda-code/ --recursive
```

## Cleanup Commands

### Delete All Resources

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name $STACK_NAME

# Delete Lambda packages from S3
aws s3 rm s3://$S3_BUCKET/lambda-code/ --recursive

# Delete CloudWatch dashboard
aws cloudwatch delete-dashboards \
  --dashboard-names $STACK_NAME-auth-monitoring

# Delete CloudWatch alarms
aws cloudwatch delete-alarms --alarm-names \
  $STACK_NAME-high-auth-failures \
  $STACK_NAME-authorization-errors \
  $STACK_NAME-lambda-errors \
  $STACK_NAME-unusual-access-pattern \
  $STACK_NAME-lambda-throttles

# Delete CloudWatch log groups (optional)
aws logs delete-log-group \
  --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION
```

## Useful One-Liners

```bash
# Get API URL and test in one command
curl -X GET $(aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text)/orders -H "Authorization: $TOKEN"

# Generate token and test API
curl -X GET "$API_URL/orders" -H "Authorization: $(cd tests/utils && python3 -c 'from token_generator import MockTokenGenerator; print("Bearer " + MockTokenGenerator().generate_token("user@yourdomain.com"))')"

# Count authentication failures in last hour
aws logs filter-log-events --log-group-name /aws/lambda/$AUTHORIZER_FUNCTION --filter-pattern "AUTHENTICATION_FAILURE" --start-time $(($(date +%s) - 3600))000 --query 'events[*].message' | grep -c AUTHENTICATION_FAILURE

# Check if stack is ready
aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].StackStatus' --output text

# Get all Lambda function names
aws cloudformation describe-stack-resources --stack-name $STACK_NAME --query 'StackResources[?ResourceType==`AWS::Lambda::Function`].PhysicalResourceId' --output table
```

## Troubleshooting Commands

```bash
# Check Lambda function configuration
aws lambda get-function --function-name $AUTHORIZER_FUNCTION

# Check Lambda function environment variables
aws lambda get-function-configuration \
  --function-name $AUTHORIZER_FUNCTION \
  --query 'Environment.Variables'

# Test Lambda function directly
aws lambda invoke \
  --function-name $AUTHORIZER_FUNCTION \
  --payload file://test-event.json \
  response.json

# Check API Gateway configuration
aws apigateway get-rest-api --rest-api-id $API_ID

# Check API Gateway authorizer
aws apigateway get-authorizers --rest-api-id $API_ID

# Check DynamoDB table status
aws dynamodb describe-table --table-name $TABLE_NAME --query 'Table.TableStatus'
```

## Quick Reference

| Task | Command |
|------|---------|
| Package Lambdas | `./infrastructure/scripts/package-lambdas.sh` |
| Deploy Stack | `./infrastructure/scripts/deploy-stack.sh ...` |
| Get API URL | `aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==\`ApiUrl\`].OutputValue' --output text` |
| Generate Token | `cd tests/utils && python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('user@yourdomain.com'))"` |
| Test API | `curl -X GET "$API_URL/orders" -H "Authorization: $TOKEN"` |
| View Logs | `aws logs tail /aws/lambda/$AUTHORIZER_FUNCTION --follow` |
| Run Tests | `pytest tests/ -v` |
| Delete Stack | `aws cloudformation delete-stack --stack-name $STACK_NAME` |

---

**Tip:** Save these commands in a script for easy reuse!
