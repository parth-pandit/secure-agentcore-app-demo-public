#!/bin/bash

# Change to the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "===================================="
echo "  MCP Client Test Script with 3LO"
echo "===================================="
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

read -p "AgentCore Gateway's IDP Client ID: " AC_GATEWAY_IDP_CLIENT_ID
read -sp "AgentCore Gateway's IDP Client Secret: " AC_GATEWAY_IDP_CLIENT_SECRET
echo ""
read -p "AgentCore Gateway's IDP Tenant ID: " AC_GATEWAY_IDP_TENANT_ID
read -p "AgentCore Gateway URL: " AC_GATEWAY_URL
read -p "API Gateway ID (e.g. 2u8i08vno4): " API_GATEWAY_ID

echo ""
read -p "Do you want to test 'tools/list' call? (y/n, default: n): " TEST_TOOLS_LIST
TEST_TOOLS_LIST=${TEST_TOOLS_LIST:-n}

echo ""
read -p "Force re-authentication even if token is cached? (y/n, default: n): " FORCE_AUTHENTICATION
FORCE_AUTHENTICATION=${FORCE_AUTHENTICATION:-n}

echo ""
echo "Running the test..."
echo ""

# Pass variables as command-line arguments to Python script
python test_mcp_client_3lo_v2.py \
    --region "$REGION" \
    --ac-gateway-idp-client-id "$AC_GATEWAY_IDP_CLIENT_ID" \
    --ac-gateway-idp-client-secret "$AC_GATEWAY_IDP_CLIENT_SECRET" \
    --ac-gateway-idp-tenant-id "$AC_GATEWAY_IDP_TENANT_ID" \
    --ac-gateway-url "$AC_GATEWAY_URL" \
    --api-gateway-id "$API_GATEWAY_ID" \
    --test-tools-list "$TEST_TOOLS_LIST" \
    --force-authentication "$FORCE_AUTHENTICATION" 

# Check if Python script succeeded
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Test run failed"
    deactivate
    exit 1
fi

# Deactivate virtual environment
deactivate

echo ""
echo "=========================================="
echo "     Test run completed successfully!"
echo "=========================================="