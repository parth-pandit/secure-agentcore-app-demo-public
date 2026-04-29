# Monitoring Scripts

This directory contains scripts for setting up CloudWatch monitoring and alerting for the Orders API authentication and authorization system.

## Prerequisites

- Python 3.7+
- AWS CLI configured with appropriate credentials
- boto3 library: `pip install boto3`
- Permissions to create CloudWatch dashboards, alarms, and metric filters

## Scripts

### create_dashboard.py

Creates a CloudWatch dashboard with comprehensive authentication and authorization metrics.

**Usage:**
```bash
python create_dashboard.py \
  --stack-name dev-orders-api \
  --region us-west-2 \
  --api-id abc123xyz \
  --authorizer-function-name dev-orders-api-authorizer \
  --dashboard-name my-custom-dashboard  # Optional
```

**Parameters:**
- `--stack-name`: CloudFormation stack name (required)
- `--region`: AWS region (default: us-west-2)
- `--api-id`: API Gateway REST API ID (required)
- `--authorizer-function-name`: Lambda Authorizer function name (required)
- `--dashboard-name`: Custom dashboard name (optional, defaults to `<stack-name>-auth-monitoring`)

**Output:**
- Creates CloudWatch dashboard
- Prints dashboard URL for viewing

### create_alarms.py

Creates CloudWatch alarms for monitoring authentication and authorization issues.

**Usage:**
```bash
python create_alarms.py \
  --stack-name dev-orders-api \
  --region us-west-2 \
  --authorizer-function-name dev-orders-api-authorizer \
  --sns-topic-arn arn:aws:sns:us-west-2:123456789012:alerts  # Optional
```

**Parameters:**
- `--stack-name`: CloudFormation stack name, used as alarm prefix (required)
- `--region`: AWS region (default: us-west-2)
- `--authorizer-function-name`: Lambda Authorizer function name (required)
- `--sns-topic-arn`: SNS topic ARN for notifications (optional)

**Output:**
- Creates 5 CloudWatch alarms
- Creates 3 metric filters
- Prints alarm URLs for viewing

## Alarms Created

1. **High Authentication Failures**: >10 failures in 5 minutes
2. **Authorization Errors**: >5 system errors in 5 minutes
3. **Lambda Errors**: >5 Lambda errors in 5 minutes
4. **Unusual Access Pattern**: >20 denials in 10 minutes
5. **Lambda Throttles**: >1 throttle in 5 minutes

## Metric Filters Created

1. **AuthenticationFailures**: Counts authentication failure events
2. **AuthorizationErrors**: Counts authorization system errors
3. **AuthorizationDenials**: Counts authorization denial events

## Getting Stack Information

To get the required parameters from your CloudFormation stack:

```bash
# Get stack outputs
aws cloudformation describe-stacks \
  --stack-name dev-orders-api \
  --query 'Stacks[0].Outputs'

# Get API ID
aws cloudformation describe-stack-resources \
  --stack-name dev-orders-api \
  --logical-resource-id OrdersApi \
  --query 'StackResources[0].PhysicalResourceId'

# Get Lambda function name
aws cloudformation describe-stack-resources \
  --stack-name dev-orders-api \
  --logical-resource-id LambdaAuthorizer \
  --query 'StackResources[0].PhysicalResourceId'
```

## Example: Complete Setup

```bash
#!/bin/bash

# Configuration
STACK_NAME="dev-orders-api"
REGION="us-west-2"
SNS_TOPIC="arn:aws:sns:us-west-2:123456789012:security-alerts"

# Get API ID and function name from CloudFormation
API_ID=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id OrdersApi \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

FUNCTION_NAME=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --logical-resource-id LambdaAuthorizer \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)

# Create dashboard
python create_dashboard.py \
  --stack-name $STACK_NAME \
  --region $REGION \
  --api-id $API_ID \
  --authorizer-function-name $FUNCTION_NAME

# Create alarms
python create_alarms.py \
  --stack-name $STACK_NAME \
  --region $REGION \
  --authorizer-function-name $FUNCTION_NAME \
  --sns-topic-arn $SNS_TOPIC

echo "Monitoring setup complete!"
```

## Viewing Monitoring Data

### CloudWatch Dashboard
```
https://<region>.console.aws.amazon.com/cloudwatch/home?region=<region>#dashboards:name=<dashboard-name>
```

### CloudWatch Alarms
```
https://<region>.console.aws.amazon.com/cloudwatch/home?region=<region>#alarmsV2:
```

### CloudWatch Logs Insights
```
https://<region>.console.aws.amazon.com/cloudwatch/home?region=<region>#logsV2:logs-insights
```

## Troubleshooting

### Permission Errors

If you get permission errors, ensure your IAM user/role has these permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutDashboard",
        "cloudwatch:PutMetricAlarm",
        "logs:PutMetricFilter",
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    }
  ]
}
```

### Dashboard Not Showing Data

- Wait 5-10 minutes after first Lambda invocation
- Verify Lambda function name is correct
- Check that log group exists: `/aws/lambda/<function-name>`
- Verify CloudWatch Logs Insights queries are valid

### Alarms Not Triggering

- Verify metric filters are created correctly
- Check that logs contain expected event types
- Verify alarm thresholds match your traffic patterns
- Ensure SNS topic ARN is correct (if using)

## Cleanup

To remove monitoring resources:

```bash
# Delete dashboard
aws cloudwatch delete-dashboards \
  --dashboard-names <dashboard-name>

# Delete alarms
aws cloudwatch delete-alarms \
  --alarm-names \
    <stack-name>-high-auth-failures \
    <stack-name>-authorization-errors \
    <stack-name>-lambda-errors \
    <stack-name>-unusual-access-pattern \
    <stack-name>-lambda-throttles

# Delete metric filters
aws logs delete-metric-filter \
  --log-group-name /aws/lambda/<function-name> \
  --filter-name AuthenticationFailures

aws logs delete-metric-filter \
  --log-group-name /aws/lambda/<function-name> \
  --filter-name AuthorizationErrors

aws logs delete-metric-filter \
  --log-group-name /aws/lambda/<function-name> \
  --filter-name AuthorizationDenials
```

## Further Documentation

See [MONITORING_AND_ALERTING.md](../../docs/MONITORING_AND_ALERTING.md) for:
- Detailed alarm descriptions
- Incident response procedures
- Log query examples
- Best practices
- Troubleshooting guide
