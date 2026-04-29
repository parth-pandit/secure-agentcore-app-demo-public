#!/bin/bash

# Script to deploy the CloudFormation stack with authentication
# Usage: ./deploy-stack.sh <stack-name> <s3-bucket> <environment> <jwks-url> <token-issuer> <token-audience> [authorized-users-json]

set -e

# Enable verbose output for debugging
# Uncomment the next line if you need to debug
# set -x

# Check arguments
if [ $# -lt 6 ]; then
    echo "Usage: $0 <stack-name> <s3-bucket> <environment> <jwks-url> <token-issuer> <token-audience> [authorized-users-json]"
    echo ""
    echo "Arguments:"
    echo "  stack-name            - CloudFormation stack name"
    echo "  s3-bucket             - S3 bucket for Lambda code"
    echo "  environment           - Environment name (dev, prod, etc.)"
    echo "  jwks-url              - JWKS URL from Azure Entra ID"
    echo "  token-issuer          - Token issuer from Azure Entra ID"
    echo "  token-audience        - Expected token audience (Azure Application ID)"
    echo "  authorized-users-json - (Optional) JSON configuration of authorized users"
    echo ""
    echo "Example:"
    echo "  $0 orders-stack my-bucket dev \\"
    echo "    'https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys' \\"
    echo "    'https://login.microsoftonline.com/<TENANT_ID>/v2.0' \\"
    echo "    '<APPLICATION_ID>' \\"
    echo "    '{\"user@yourdomain.com\":{\"permissions\":[\"GET\",\"POST\",\"PUT\"],\"resources\":[\"*\"]}}'"
    exit 1
fi

STACK_NAME=$1
S3_BUCKET=$2
ENVIRONMENT=$3
JWKS_URL=$4
TOKEN_ISSUER=$5
TOKEN_AUDIENCE=$6
AUTHORIZED_USERS=${7:-"{\"user@yourdomain.com\":{\"permissions\":[\"GET\",\"POST\",\"PUT\"],\"resources\":[\"*\"]}}"}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_FILE="$PROJECT_ROOT/infrastructure/cloudformation/secure-agentcore-app-cft.yaml"
LAMBDA_PACKAGES_DIR="$PROJECT_ROOT/infrastructure/lambda-packages"

echo "Deploying CloudFormation stack: $STACK_NAME"
echo "Environment: $ENVIRONMENT"
echo "S3 Bucket: $S3_BUCKET"
echo "JWKS URL: $JWKS_URL"
echo "Token Issuer: $TOKEN_ISSUER"
echo "Token Audience: $TOKEN_AUDIENCE"
echo ""

# Verify AWS credentials
echo "Verifying AWS credentials..."
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ Error: AWS credentials are not configured or invalid"
    echo "Fix: Run 'aws configure' to set up your credentials"
    exit 1
fi
echo "✅ AWS credentials verified"
echo ""

# Verify S3 bucket exists
echo "Verifying S3 bucket access..."
if ! aws s3 ls "s3://$S3_BUCKET" &>/dev/null; then
    echo "❌ Error: Cannot access S3 bucket '$S3_BUCKET'"
    echo "Fix: Create the bucket with: aws s3 mb s3://$S3_BUCKET"
    exit 1
fi
echo "✅ S3 bucket accessible"
echo ""

# Check if Lambda packages exist
if [ ! -d "$LAMBDA_PACKAGES_DIR" ]; then
    echo "Error: Lambda packages not found. Run package-lambdas.sh first."
    exit 1
fi

# Upload Lambda packages to S3
echo "Uploading Lambda packages to S3..."
echo "Source: $LAMBDA_PACKAGES_DIR"
echo "Destination: s3://$S3_BUCKET/lambda-code/"
echo ""

# Count packages to upload
PACKAGE_COUNT=$(find "$LAMBDA_PACKAGES_DIR" -name "*.zip" | wc -l)
echo "Found $PACKAGE_COUNT Lambda package(s) to upload:"
find "$LAMBDA_PACKAGES_DIR" -name "*.zip" -exec basename {} \;
echo ""

# Upload each package individually with progress
for package in "$LAMBDA_PACKAGES_DIR"/*.zip; do
    if [ -f "$package" ]; then
        PACKAGE_NAME=$(basename "$package")
        echo "Uploading $PACKAGE_NAME..."
        aws s3 cp "$package" "s3://$S3_BUCKET/lambda-code/$PACKAGE_NAME"
    fi
done

echo "✅ All Lambda packages uploaded successfully"

echo ""
echo "Deploying CloudFormation stack..."

# Deploy or update stack
aws cloudformation deploy \
    --template-file "$TEMPLATE_FILE" \
    --stack-name "$STACK_NAME" \
    --parameter-overrides \
        Environment="$ENVIRONMENT" \
        LambdaCodeBucket="$S3_BUCKET" \
        LambdaCodeKey="lambda-code/" \
        JwksUrl="$JWKS_URL" \
        TokenIssuer="$TOKEN_ISSUER" \
        TokenAudience="$TOKEN_AUDIENCE" \
        AuthorizedUsers="$AUTHORIZED_USERS" \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags \
        Environment="$ENVIRONMENT" \
        ManagedBy=CloudFormation

echo ""
echo "Stack deployment complete!"
echo ""
echo "Getting stack outputs..."
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs' \
    --output table
