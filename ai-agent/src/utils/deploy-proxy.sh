#!/usr/bin/env bash
set -euo pipefail

# Deploy agent_proxy.py Lambda function
#
# Usage Option 1 (using properties file):
#   1. Edit agent-proxy.properties with your configuration
#   2. Run: ./deploy-proxy.sh
#
# Usage Option 2 (using environment variables):
#   REGION=us-west-2 \
#   LAMBDA_NAME=agentcore-proxy-strands-sonnet45-west2 \
#   AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:<acct>:runtime/strands_sonnet45_west2-orA4CSAzQ0 \
#   ./deploy-proxy.sh
#
# Optional:
#   ALLOW_ORIGIN=* (default: *)
#   LOG_LEVEL=INFO (default: INFO, options: DEBUG, INFO, WARNING, ERROR)

# Paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROPERTIES_FILE="$SCRIPT_DIR/agent-proxy.properties"

# Source properties file if it exists
if [ -f "$PROPERTIES_FILE" ]; then
  echo "Loading configuration from agent-proxy.properties..."
  # Source the properties file, ignoring comments and empty lines
  set -a  # automatically export all variables
  source <(grep -v '^#' "$PROPERTIES_FILE" | grep -v '^$')
  set +a
  echo "✓ Configuration loaded"
  echo ""
fi

# Set defaults (can be overridden by properties file or environment variables)
# AWS Region - defaults to us-west-2 if not set
REGION=${REGION:-${AWS_REGION:-us-west-2}}
LAMBDA_NAME=${LAMBDA_NAME:-agentcore-proxy-strands-sonnet45-west2}
AGENT_RUNTIME_ARN=${AGENT_RUNTIME_ARN:?ERROR: AGENT_RUNTIME_ARN must be set}
ALLOW_ORIGIN=${ALLOW_ORIGIN:-*}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROPERTIES_FILE="$SCRIPT_DIR/agent-proxy.properties"

# Source properties file if it exists
if [ -f "$PROPERTIES_FILE" ]; then
  echo "Loading configuration from agent-proxy.properties..."
  # Source the properties file, ignoring comments and empty lines
  set -a  # automatically export all variables
  source <(grep -v '^#' "$PROPERTIES_FILE" | grep -v '^$')
  set +a
  echo "✓ Configuration loaded"
  echo ""
fi

# Set defaults (can be overridden by properties file or environment variables)
# AWS Region - defaults to us-west-2 if not set
REGION=${REGION:-${AWS_REGION:-us-west-2}}
LAMBDA_NAME=${LAMBDA_NAME:-agentcore-proxy-strands-sonnet45-west2}
AGENT_RUNTIME_ARN=${AGENT_RUNTIME_ARN:?ERROR: AGENT_RUNTIME_ARN must be set}
ALLOW_ORIGIN=${ALLOW_ORIGIN:-*}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAMBDA_DIR="$SRC_DIR/lambdas"
LIB_DIR="$SRC_DIR/lib"
BUILD_DIR="$SRC_DIR/build"
ZIP_PATH="$BUILD_DIR/agent_proxy.zip"

echo "=========================================="
echo "Agent Proxy Lambda Deployment"
echo "=========================================="
echo "Region:            $REGION"
echo "Lambda Name:       $LAMBDA_NAME"
echo "Agent Runtime ARN: $AGENT_RUNTIME_ARN"
echo "Allow Origin:      $ALLOW_ORIGIN"
echo "Log Level:         $LOG_LEVEL"
echo "=========================================="

# Verify Lambda exists
echo ""
echo "Verifying Lambda function exists..."
if ! aws lambda get-function-configuration \
  --region "$REGION" \
  --function-name "$LAMBDA_NAME" \
  --query 'FunctionName' \
  --output text &>/dev/null; then
  echo "ERROR: Lambda function '$LAMBDA_NAME' not found in region $REGION"
  exit 1
fi
echo "✓ Lambda function found"

# Package Lambda code
echo ""
echo "Packaging Lambda code..."

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/package"

# Copy Lambda code
echo "  - Copying agent_proxy.py..."
cp "$LAMBDA_DIR/agent_proxy.py" "$BUILD_DIR/package/"

# Copy lib directory (contains all dependencies)
if [ -d "$LIB_DIR" ]; then
  echo "  - Copying lib directory with dependencies..."
  cp -r "$LIB_DIR"/* "$BUILD_DIR/package/"
else
  echo "  - WARNING: lib directory not found at $LIB_DIR"
  echo "  - Installing dependencies from requirements.txt..."
  if [ -f "$SRC_DIR/requirements.txt" ]; then
    pip install -q -r "$SRC_DIR/requirements.txt" -t "$BUILD_DIR/package/" --upgrade
  else
    echo "  - ERROR: No lib directory and no requirements.txt found"
    exit 1
  fi
fi

# Create zip file
echo "  - Creating deployment package..."
cd "$BUILD_DIR/package"
zip -q -r "$ZIP_PATH" .
cd - > /dev/null

# Verify zip was created
if [ ! -f "$ZIP_PATH" ]; then
  echo "ERROR: Failed to create deployment package at $ZIP_PATH"
  exit 1
fi

ZIP_SIZE=$(du -h "$ZIP_PATH" | cut -f1)
echo "✓ Deployment package created: $ZIP_PATH ($ZIP_SIZE)"

# Update Lambda code
echo ""
echo "Updating Lambda function code..."
aws lambda update-function-code \
  --region "$REGION" \
  --function-name "$LAMBDA_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --output json \
  --query '{FunctionName:FunctionName,LastModified:LastModified,CodeSize:CodeSize,State:State}' \
  | jq -r 'to_entries | .[] | "  \(.key): \(.value)"'

# Wait for update to complete
echo ""
echo "Waiting for Lambda update to complete..."
aws lambda wait function-updated \
  --region "$REGION" \
  --function-name "$LAMBDA_NAME"
echo "✓ Lambda code updated"

# Update Lambda configuration (handler + environment variables)
echo ""
echo "Updating Lambda configuration..."
aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name "$LAMBDA_NAME" \
  --handler "agent_proxy.handler" \
  --environment "Variables={AGENT_RUNTIME_ARN=$AGENT_RUNTIME_ARN,ALLOW_ORIGIN=$ALLOW_ORIGIN,LOG_LEVEL=$LOG_LEVEL}" \
  --output json \
  --query '{FunctionName:FunctionName,Handler:Handler,LastModified:LastModified,State:State}' \
  | jq -r 'to_entries | .[] | "  \(.key): \(.value)"'

# Wait for configuration update to complete
echo ""
echo "Waiting for configuration update to complete..."
aws lambda wait function-updated \
  --region "$REGION" \
  --function-name "$LAMBDA_NAME"
echo "✓ Lambda configuration updated"

# Verify deployment
echo ""
echo "=========================================="
echo "Deployment Complete - Verification"
echo "=========================================="
aws lambda get-function-configuration \
  --region "$REGION" \
  --function-name "$LAMBDA_NAME" \
  --query '{Runtime:Runtime,Handler:Handler,Timeout:Timeout,MemorySize:MemorySize,State:State,LastUpdateStatus:LastUpdateStatus,Environment:Environment.Variables}' \
  --output json | jq '.'

echo ""
echo "✓ Deployment successful!"

