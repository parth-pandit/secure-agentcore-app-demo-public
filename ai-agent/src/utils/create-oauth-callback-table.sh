#!/usr/bin/env bash
set -euo pipefail

# Create DynamoDB table for OAuth2 Callback Server
#
# Usage:
#   REGION=us-west-2 \
#   OAUTH_TABLE=agentcore-oauth-callback \
#   ./create-oauth-callback-table.sh

# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION or REGION environment variable to use a different region
REGION=${REGION:-${AWS_REGION:-us-west-2}}
OAUTH_TABLE=${OAUTH_TABLE:-agentcore-oauth-callback}

echo "=========================================="
echo "OAuth2 Callback DynamoDB Table Creation"
echo "=========================================="
echo "Region:            $REGION"
echo "Table Name:        $OAUTH_TABLE"
echo "=========================================="

# Check if table already exists
echo ""
echo "Checking if table already exists..."
if aws dynamodb describe-table \
  --region "$REGION" \
  --table-name "$OAUTH_TABLE" \
  --query 'Table.TableName' \
  --output text &>/dev/null; then
  echo "✓ Table '$OAUTH_TABLE' already exists"
  echo ""
  echo "Table details:"
  aws dynamodb describe-table \
    --region "$REGION" \
    --table-name "$OAUTH_TABLE" \
    --query '{TableName:Table.TableName,TableStatus:Table.TableStatus,ItemCount:Table.ItemCount,TableSizeBytes:Table.TableSizeBytes}' \
    --output json | jq '.'
  exit 0
fi

# Create table
echo "Creating DynamoDB table..."
aws dynamodb create-table \
  --region "$REGION" \
  --table-name "$OAUTH_TABLE" \
  --attribute-definitions \
    AttributeName=id,AttributeType=S \
  --key-schema \
    AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags \
    Key=Purpose,Value=OAuth2CallbackServer \
    Key=ManagedBy,Value=Script \
  --output json \
  --query '{TableName:TableDescription.TableName,TableStatus:TableDescription.TableStatus,TableArn:TableDescription.TableArn}' \
  | jq -r 'to_entries | .[] | "  \(.key): \(.value)"'

# Wait for table to be active
echo ""
echo "Waiting for table to become active..."
aws dynamodb wait table-exists \
  --region "$REGION" \
  --table-name "$OAUTH_TABLE"

# Enable TTL on expires_at attribute
echo ""
echo "Enabling TTL on 'expires_at' attribute..."
aws dynamodb update-time-to-live \
  --region "$REGION" \
  --table-name "$OAUTH_TABLE" \
  --time-to-live-specification "Enabled=true,AttributeName=expires_at" \
  --output json \
  --query 'TimeToLiveSpecification' \
  | jq '.'

echo ""
echo "✓ Table created successfully!"

# Display table details
echo ""
echo "=========================================="
echo "Table Details"
echo "=========================================="
aws dynamodb describe-table \
  --region "$REGION" \
  --table-name "$OAUTH_TABLE" \
  --query '{TableName:Table.TableName,TableStatus:Table.TableStatus,TableArn:Table.TableArn,BillingMode:Table.BillingModeSummary.BillingMode,ItemCount:Table.ItemCount}' \
  --output json | jq '.'

echo ""
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Deploy the OAuth callback Lambda: ./deploy-oauth-callback.sh"
echo "  2. Set OAUTH_CALLBACK_SERVER_URL in your agent environment"
