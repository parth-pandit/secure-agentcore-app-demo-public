#!/bin/bash

# Change to the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "AgentCore Components Deployment Script"
echo "=========================================="
echo ""

# Check Python version
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD="python"
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo "Detected Python version: $PYTHON_VERSION"

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "ERROR: Python 3.10 or higher is required"
    echo "Current version: $PYTHON_VERSION"
    echo ""
    echo "Please install Python 3.10+ or use a virtual environment:"
    echo "  python3.10 -m venv venv"
    echo "  source venv/bin/activate"
    exit 1
fi

echo "✓ Python version check passed"
echo ""

# Check if virtual environment exists, create if not
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment found"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "✓ Virtual environment activated"
echo ""

echo "Installing dependencies..."
if ! pip install --force-reinstall --no-cache-dir -r requirements.txt; then
    echo "ERROR: Failed to install dependencies"
    deactivate
    exit 1
fi

echo ""
echo ""
echo "✓ All dependencies installed"
echo ""

# Prompt for required variables
echo "Please provide the following configuration values:"
echo ""

read -p "AWS Region (e.g., us-east-1): " REGION
if [ -z "$REGION" ]; then
    echo "ERROR: AWS Region cannot be empty"
    deactivate
    exit 1
fi

read -p "Identity Provider Discovery URL: " IDP_DISCOVERY_URL
if [ -z "$IDP_DISCOVERY_URL" ]; then
    echo "ERROR: Identity Provider Discovery URL cannot be empty"
    deactivate
    exit 1
fi
read -p "Agent's Identity Provider Client ID: " AGENT_IDP_CLIENT_ID
read -p "Gateway's Identity Provider Client ID: " GATEWAY_IDP_CLIENT_ID
read -p "Target's IDP Client ID: " TARGET_IDP_CLIENT_ID
read -sp "Target's IDP Client Secret: " TARGET_IDP_CLIENT_SECRET
echo ""
read -p "Target's IDP Tenant ID: " TARGET_IDP_TENANT_ID
read -p "OAuth2 Callback Server Endpoint: " OAUTH2_CALLBACK_SERVER_ENDPOINT
read -p "S3 Account ID: " S3_ACCOUNT
read -p "S3 URI for OpenAPI Schema (e.g., s3://bucket/path/schema.yaml): " S3_URI_OPEN_API_SCHEMA

echo ""
echo "=========================================="
echo "Configuration Summary:"
echo "=========================================="
echo "Region: $REGION"
echo "IDP Discovery URL: $IDP_DISCOVERY_URL"
echo "Agent's IDP Client ID: $AGENT_IDP_CLIENT_ID"
echo "Gateway's IDP Client ID: $GATEWAY_IDP_CLIENT_ID"
echo "Target's IDP Client ID: $TARGET_IDP_CLIENT_ID"
echo "Target's IDP Client Secret: [HIDDEN]"
echo "Target's IDP Tenant ID: $TARGET_IDP_TENANT_ID"
echo "OAuth2 Callback Server Endpoint: $OAUTH2_CALLBACK_SERVER_ENDPOINT"
echo "S3 Account: $S3_ACCOUNT"
echo "S3 URI: $S3_URI_OPEN_API_SCHEMA"
echo "=========================================="
echo ""

read -p "Proceed with deployment? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "Deploying AgentCore components..."
echo ""

# Pass variables as command-line arguments to Python script
python deploy-agentcore-components.py \
    --region "$REGION" \
    --idp-discovery-url "$IDP_DISCOVERY_URL" \
    --agent-idp-client-id "$AGENT_IDP_CLIENT_ID" \
    --gateway-idp-client-id "$GATEWAY_IDP_CLIENT_ID" \
    --target-idp-client-id "$TARGET_IDP_CLIENT_ID" \
    --target-idp-client-secret "$TARGET_IDP_CLIENT_SECRET" \
    --target-idp-tenant-id "$TARGET_IDP_TENANT_ID" \
    --oauth2-callback-server-endpoint "$OAUTH2_CALLBACK_SERVER_ENDPOINT" \
    --s3-account "$S3_ACCOUNT" \
    --s3-uri "$S3_URI_OPEN_API_SCHEMA"

# Check if Python script succeeded
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Deployment failed"
    deactivate
    exit 1
fi

# Deactivate virtual environment
deactivate

echo ""
echo "=========================================="
echo "Deployment completed successfully!"
echo "=========================================="