#!/usr/bin/env bash
set -euo pipefail

# Update IAM permissions for OAuth2 Callback Lambda
#
# This script adds the necessary permissions for the OAuth callback Lambda to:
# 1. Access Secrets Manager (required by AgentCore's complete_resource_token_auth)
# 2. Call AgentCore APIs
#
# Usage:
#   REGION=us-west-2 \
#   OAUTH_LAMBDA_NAME=agentcore-oauth-callback \
#   ./update-oauth-callback-permissions.sh

# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION or REGION environment variable to use a different region
REGION=${REGION:-${AWS_REGION:-us-west-2}}
OAUTH_LAMBDA_NAME=${OAUTH_LAMBDA_NAME:-agentcore-oauth-callback}

echo "=========================================="
echo "OAuth2 Callback Lambda IAM Update"
echo "=========================================="
echo "Region:            $REGION"
echo "Lambda Name:       $OAUTH_LAMBDA_NAME"
echo "=========================================="

# Get Lambda's execution role
echo ""
echo "Getting Lambda execution role..."
ROLE_ARN=$(aws lambda get-function-configuration \
  --region "$REGION" \
  --function-name "$OAUTH_LAMBDA_NAME" \
  --query 'Role' \
  --output text)

if [ -z "$ROLE_ARN" ]; then
  echo "ERROR: Could not find execution role for Lambda '$OAUTH_LAMBDA_NAME'"
  exit 1
fi

ROLE_NAME=$(echo "$ROLE_ARN" | awk -F'/' '{print $NF}')
echo "✓ Found execution role: $ROLE_NAME"

# Create inline policy for AgentCore and Secrets Manager access
echo ""
echo "Creating inline policy for AgentCore and Secrets Manager access..."

POLICY_NAME="AgentCoreOAuthCallbackPolicy"
POLICY_DOCUMENT=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CompleteResourceTokenAuth",
        "bedrock-agentcore:GetResourceTokenAuthSession"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

# Put inline policy
aws iam put-role-policy \
  --region "$REGION" \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "$POLICY_DOCUMENT"

echo "✓ Inline policy '$POLICY_NAME' added to role '$ROLE_NAME'"

# Display updated role policies
echo ""
echo "=========================================="
echo "Updated Role Policies"
echo "=========================================="
echo ""
echo "Managed Policies:"
aws iam list-attached-role-policies \
  --role-name "$ROLE_NAME" \
  --query 'AttachedPolicies[*].[PolicyName,PolicyArn]' \
  --output table

echo ""
echo "Inline Policies:"
aws iam list-role-policies \
  --role-name "$ROLE_NAME" \
  --query 'PolicyNames' \
  --output table

echo ""
echo "✓ Permissions updated successfully!"
echo ""
echo "The Lambda can now:"
echo "  - Call bedrock-agentcore:CompleteResourceTokenAuth"
echo "  - Access secretsmanager:GetSecretValue"
echo "  - Complete 3LO OAuth flows"
