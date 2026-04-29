# CloudFormation Stack Deployment Guide

This guide explains how to deploy the Orders API infrastructure using CloudFormation.

## Architecture Overview

The stack creates:
- **DynamoDB Table**: `{Environment}-orders-table` with GSIs
- **Lambda Functions**: 
  - `{Environment}-get-orders` - GET all orders
  - `{Environment}-create-order` - POST new order
  - `{Environment}-update-order` - PUT update order
- **API Gateway**: `{Environment}-orders-api` with REST endpoints
- **IAM Role**: `{Environment}-orders-lambda-role` with DynamoDB permissions

## Prerequisites

1. AWS CLI installed and configured
2. Python 3.9+ installed
3. pip installed
4. S3 bucket for Lambda code storage
5. Appropriate AWS permissions to create resources

## Deployment Steps

### Step 1: Package Lambda Functions

```bash
cd infrastructure/scripts
./package-lambdas.sh
```

This creates zip files in `infrastructure/lambda-packages/`:
- `get_orders.zip`
- `create_order.zip`
- `update_order.zip`

### Step 2: Deploy CloudFormation Stack

```bash
./deploy-stack.sh <stack-name> <s3-bucket-name> <environment>
```

**Example:**
```bash
./deploy-stack.sh orders-api-stack my-lambda-code-bucket dev
```

**Parameters:**
- `stack-name`: Name for your CloudFormation stack
- `s3-bucket-name`: S3 bucket where Lambda code will be uploaded
- `environment`: Environment name (dev/staging/prod) - defaults to 'dev'

### Step 3: Get API Endpoint

After deployment, the script displays stack outputs including the API Gateway URL:

```
https://{api-id}.execute-api.{region}.amazonaws.com/{environment}/orders
```

## Manual Deployment (Alternative)

If you prefer manual deployment:

### 1. Package Lambdas
```bash
cd backend/src/lambdas
pip install -r requirements.txt -t ./package
cd package
zip -r ../get_orders.zip .
cd ..
zip -g get_orders.zip get_orders.py
```

Repeat for `create_order.py` and `update_order.py`.

### 2. Upload to S3
```bash
aws s3 cp get_orders.zip s3://your-bucket/lambda-code/
aws s3 cp create_order.zip s3://your-bucket/lambda-code/
aws s3 cp update_order.zip s3://your-bucket/lambda-code/
```

### 3. Deploy Stack
```bash
aws cloudformation create-stack \
  --stack-name orders-api-stack \
  --template-body file://infrastructure/cloudformation/secure-agentcore-app-cft.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=dev \
    ParameterKey=LambdaCodeBucket,ParameterValue=your-bucket \
    ParameterKey=LambdaCodeKey,ParameterValue=lambda-code/ \
  --capabilities CAPABILITY_NAMED_IAM
```

## Testing the API

### GET - Retrieve All Orders
```bash
curl -X GET https://{api-url}/orders
```

### POST - Create Order
```bash
curl -X POST https://{api-url}/orders \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD-001",
    "order_date": "2025-12-27",
    "item_name": "Widget",
    "qty": 10,
    "status": "pending"
  }'
```

### PUT - Update Order
```bash
curl -X PUT https://{api-url}/orders \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD-001",
    "status": "completed",
    "qty": 15
  }'
```

## Stack Updates

To update the stack after making changes:

```bash
./deploy-stack.sh <stack-name> <s3-bucket> <environment>
```

The script automatically handles updates to existing stacks.

## Cleanup

To delete the stack and all resources:

```bash
aws cloudformation delete-stack --stack-name orders-api-stack
```

**Note:** DynamoDB table has deletion protection enabled. You must disable it before deleting the stack.

## Troubleshooting

### Lambda Function Errors
Check CloudWatch Logs:
```bash
aws logs tail /aws/lambda/{environment}-get-orders --follow
```

### API Gateway Issues
Test Lambda directly:
```bash
aws lambda invoke \
  --function-name dev-get-orders \
  --payload '{}' \
  response.json
```

### Stack Creation Failures
View stack events:
```bash
aws cloudformation describe-stack-events \
  --stack-name orders-api-stack \
  --max-items 20
```

## Cost Considerations

- **DynamoDB**: PAY_PER_REQUEST billing (no cost when idle)
- **Lambda**: Free tier includes 1M requests/month
- **API Gateway**: Free tier includes 1M API calls/month
- **CloudWatch Logs**: Charges apply for log storage

## Security Notes

- API Gateway endpoints are currently public (no authentication)
- Consider adding API keys, IAM authorization, or Cognito for production
- Lambda functions have minimal IAM permissions (DynamoDB access only)
- Enable AWS WAF for API Gateway in production environments
