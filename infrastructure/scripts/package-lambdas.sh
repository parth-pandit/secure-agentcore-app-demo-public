#!/bin/bash

# Script to package Lambda functions for deployment
# This script creates zip files for each Lambda function with dependencies

set -e

echo "Packaging Lambda functions..."

# Create temporary directory for packaging
TEMP_DIR=$(mktemp -d)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAMBDA_SRC="$PROJECT_ROOT/backend/src/lambdas"
OUTPUT_DIR="$PROJECT_ROOT/infrastructure/lambda-packages"

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Function to package a Lambda function
package_lambda() {
    local function_name=$1
    local function_file="${function_name}.py"
    
    echo "Packaging ${function_name}..."
    
    # Create temporary directory for this function
    local temp_function_dir="$TEMP_DIR/$function_name"
    mkdir -p "$temp_function_dir"
    
    # Copy function code
    cp "$LAMBDA_SRC/$function_file" "$temp_function_dir/"
    
    # Install dependencies if requirements.txt exists
    if [ -f "$LAMBDA_SRC/requirements.txt" ]; then
        echo "Installing dependencies for ${function_name}..."
        pip install -r "$LAMBDA_SRC/requirements.txt" -t "$temp_function_dir" --quiet
    fi
    
    # Create zip file
    cd "$temp_function_dir"
    zip -r "$OUTPUT_DIR/${function_name}.zip" . -q
    cd - > /dev/null
    
    echo "✓ Created $OUTPUT_DIR/${function_name}.zip"
}

# Package each Lambda function
package_lambda "get_orders"
package_lambda "create_order"
package_lambda "update_order"

# Package Lambda Authorizer with all required modules
echo "Packaging authorizer (with dependencies)..."
AUTHORIZER_DIR="$TEMP_DIR/authorizer"
mkdir -p "$AUTHORIZER_DIR"

# Copy all authorizer-related modules
cp "$LAMBDA_SRC/authorizer.py" "$AUTHORIZER_DIR/"
cp "$LAMBDA_SRC/token_validator.py" "$AUTHORIZER_DIR/"
cp "$LAMBDA_SRC/authorization_policy.py" "$AUTHORIZER_DIR/"
cp "$LAMBDA_SRC/audit_logger.py" "$AUTHORIZER_DIR/"

# Install dependencies for authorizer (PyJWT, cryptography, requests)
echo "Installing dependencies for authorizer..."
# Use --platform to ensure Linux-compatible binaries for Lambda
pip install \
    PyJWT>=2.8.0 \
    cryptography>=41.0.0 \
    requests>=2.28.0 \
    -t "$AUTHORIZER_DIR" \
    --platform manylinux2014_x86_64 \
    --only-binary=:all: \
    --python-version 3.11 \
    --implementation cp \
    --quiet 2>/dev/null || \
    pip install \
        PyJWT>=2.8.0 \
        cryptography>=41.0.0 \
        requests>=2.28.0 \
        -t "$AUTHORIZER_DIR" \
        --quiet

# Create zip file
cd "$AUTHORIZER_DIR"
zip -r "$OUTPUT_DIR/authorizer.zip" . -q
cd - > /dev/null

echo "✓ Created $OUTPUT_DIR/authorizer.zip"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "All Lambda functions packaged successfully!"
echo "Output directory: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "1. Upload the zip files to your S3 bucket"
echo "2. Deploy the CloudFormation stack with the S3 bucket name"
