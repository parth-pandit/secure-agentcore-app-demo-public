#!/bin/bash

# Diagnostic script to troubleshoot deployment issues
# Usage: ./diagnose-deployment.sh <s3-bucket>

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <s3-bucket>"
    echo ""
    echo "This script checks common deployment issues:"
    echo "  - AWS credentials"
    echo "  - S3 bucket access"
    echo "  - Lambda packages"
    echo "  - Network connectivity"
    exit 1
fi

S3_BUCKET=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAMBDA_PACKAGES_DIR="$PROJECT_ROOT/infrastructure/lambda-packages"

echo "=========================================="
echo "Deployment Diagnostics"
echo "=========================================="
echo ""

# Check 1: AWS credentials
echo "1. Checking AWS credentials..."
if aws sts get-caller-identity &>/dev/null; then
    echo "   ✅ AWS credentials are valid"
    aws sts get-caller-identity --output table
else
    echo "   ❌ AWS credentials are NOT valid or not configured"
    echo "   Fix: Run 'aws configure' to set up your credentials"
    exit 1
fi
echo ""

# Check 2: AWS region
echo "2. Checking AWS region..."
REGION=$(aws configure get region)
if [ -z "$REGION" ]; then
    echo "   ⚠️  No default region configured"
    echo "   Fix: Run 'aws configure set region us-west-2' (or your preferred region)"
else
    echo "   ✅ Region: $REGION"
fi
echo ""

# Check 3: S3 bucket exists
echo "3. Checking if S3 bucket exists..."
if aws s3 ls "s3://$S3_BUCKET" &>/dev/null; then
    echo "   ✅ S3 bucket '$S3_BUCKET' exists and is accessible"
else
    echo "   ❌ S3 bucket '$S3_BUCKET' does NOT exist or is not accessible"
    echo "   Fix: Create the bucket with: aws s3 mb s3://$S3_BUCKET"
    echo "   Or check if you have permissions to access it"
    exit 1
fi
echo ""

# Check 4: S3 write permissions
echo "4. Checking S3 write permissions..."
TEST_FILE="/tmp/test-upload-$$"
echo "test" > "$TEST_FILE"
if aws s3 cp "$TEST_FILE" "s3://$S3_BUCKET/test-upload.txt" &>/dev/null; then
    echo "   ✅ Can write to S3 bucket"
    aws s3 rm "s3://$S3_BUCKET/test-upload.txt" &>/dev/null
    rm "$TEST_FILE"
else
    echo "   ❌ Cannot write to S3 bucket"
    echo "   Fix: Check your IAM permissions for s3:PutObject on this bucket"
    rm "$TEST_FILE"
    exit 1
fi
echo ""

# Check 5: Lambda packages exist
echo "5. Checking Lambda packages..."
if [ ! -d "$LAMBDA_PACKAGES_DIR" ]; then
    echo "   ❌ Lambda packages directory not found: $LAMBDA_PACKAGES_DIR"
    echo "   Fix: Run './infrastructure/scripts/package-lambdas.sh' first"
    exit 1
fi

PACKAGE_COUNT=$(find "$LAMBDA_PACKAGES_DIR" -name "*.zip" | wc -l)
if [ "$PACKAGE_COUNT" -eq 0 ]; then
    echo "   ❌ No Lambda packages found in $LAMBDA_PACKAGES_DIR"
    echo "   Fix: Run './infrastructure/scripts/package-lambdas.sh' first"
    exit 1
else
    echo "   ✅ Found $PACKAGE_COUNT Lambda package(s):"
    find "$LAMBDA_PACKAGES_DIR" -name "*.zip" -exec basename {} \; | sed 's/^/      - /'
fi
echo ""

# Check 6: Lambda package sizes
echo "6. Checking Lambda package sizes..."
for package in "$LAMBDA_PACKAGES_DIR"/*.zip; do
    if [ -f "$package" ]; then
        SIZE=$(du -h "$package" | cut -f1)
        NAME=$(basename "$package")
        echo "      $NAME: $SIZE"
    fi
done
echo ""

# Check 7: Test S3 upload speed
echo "7. Testing S3 upload speed..."
TEST_PACKAGE=$(find "$LAMBDA_PACKAGES_DIR" -name "*.zip" | head -1)
if [ -n "$TEST_PACKAGE" ]; then
    echo "   Uploading test package: $(basename "$TEST_PACKAGE")"
    START_TIME=$(date +%s)
    if aws s3 cp "$TEST_PACKAGE" "s3://$S3_BUCKET/test-lambda-upload.zip" 2>&1; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        echo "   ✅ Upload successful (took ${DURATION}s)"
        aws s3 rm "s3://$S3_BUCKET/test-lambda-upload.zip" &>/dev/null
    else
        echo "   ❌ Upload failed"
        exit 1
    fi
else
    echo "   ⚠️  No test package found"
fi
echo ""

# Check 8: Network connectivity to AWS
echo "8. Checking network connectivity to AWS..."
if curl -s --max-time 5 https://s3.amazonaws.com &>/dev/null; then
    echo "   ✅ Can reach AWS S3 endpoints"
else
    echo "   ❌ Cannot reach AWS S3 endpoints"
    echo "   Fix: Check your internet connection or proxy settings"
    exit 1
fi
echo ""

echo "=========================================="
echo "All checks passed! ✅"
echo "=========================================="
echo ""
echo "You should be able to deploy now. Try running:"
echo "  ./infrastructure/scripts/deploy-stack.sh \\"
echo "    <stack-name> $S3_BUCKET <environment> \\"
echo "    <jwks-url> <token-issuer> <token-audience>"
echo ""
