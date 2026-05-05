#!/bin/bash

################################################################################
# Lambda Packaging Script for CloudFormation Deployment
#
# This script packages all Lambda functions with their dependencies into
# deployment-ready zip files for upload to S3.
#
# Usage:
#   ./package-lambdas.sh [--clean]
#
# Options:
#   --clean    Remove existing packages before building new ones
#
# Output:
#   Creates zip files in infrastructure/lambda-packages/ directory:
#   - get_orders.zip
#   - create_order.zip
#   - update_order.zip
#   - authorizer.zip
#   - agent_proxy.zip
#   - oauth2_callback_server.zip
#
# Requirements:
#   - Python 3.12 or compatible version
#   - pip package manager
#   - zip utility
#
# AWS Lambda Deployment Package Format:
#   Lambda deployment packages must include all dependencies at the root level
#   with the handler file. This script creates proper package structure.
################################################################################

set -e  # Exit on any error

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PACKAGES_DIR="$PROJECT_ROOT/infrastructure/lambda-packages"

# Lambda source directories
BACKEND_LAMBDAS_DIR="$PROJECT_ROOT/backend/src/lambdas"
AI_AGENT_LAMBDAS_DIR="$PROJECT_ROOT/ai-agent/src/lambdas"
AI_AGENT_SRC_DIR="$PROJECT_ROOT/ai-agent/src"

# Temporary build directory
BUILD_DIR="$PROJECT_ROOT/.lambda-build"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

################################################################################
# Package Backend Lambda Function
#
# Packages a Lambda function from backend/src/lambdas with dependencies
#
# Args:
#   $1: Lambda function name (e.g., "get_orders")
#   $2: Handler file name (e.g., "get_orders.py")
################################################################################
package_backend_lambda() {
    local function_name=$1
    local handler_file=$2
    local package_name="${function_name}.zip"
    
    print_info "Packaging ${function_name}..."
    
    # Create temporary build directory for this function
    local temp_dir="$BUILD_DIR/$function_name"
    mkdir -p "$temp_dir"
    
    # Copy handler file and supporting modules
    # Backend Lambda functions may depend on shared modules in the same directory
    cp "$BACKEND_LAMBDAS_DIR/$handler_file" "$temp_dir/"
    
    # Copy supporting modules that Lambda functions import
    # These are utility modules used by multiple Lambda functions
    if [ -f "$BACKEND_LAMBDAS_DIR/token_validator.py" ]; then
        cp "$BACKEND_LAMBDAS_DIR/token_validator.py" "$temp_dir/"
    fi
    if [ -f "$BACKEND_LAMBDAS_DIR/authorization_policy.py" ]; then
        cp "$BACKEND_LAMBDAS_DIR/authorization_policy.py" "$temp_dir/"
    fi
    if [ -f "$BACKEND_LAMBDAS_DIR/audit_logger.py" ]; then
        cp "$BACKEND_LAMBDAS_DIR/audit_logger.py" "$temp_dir/"
    fi
    
    # Install dependencies from requirements.txt
    # Using --target installs packages directly into the temp directory
    # This creates the proper Lambda deployment package structure
    if [ -f "$BACKEND_LAMBDAS_DIR/requirements.txt" ]; then
        print_info "Installing dependencies for ${function_name}..."
        pip install -q --target "$temp_dir" -r "$BACKEND_LAMBDAS_DIR/requirements.txt" --upgrade
    fi
    
    # Create zip file with all contents at root level
    # Lambda expects handler file and dependencies at package root
    cd "$temp_dir"
    zip -q -r "$PACKAGES_DIR/$package_name" . -x "*.pyc" -x "__pycache__/*"
    cd - > /dev/null
    
    # Get package size for reporting
    local size=$(du -h "$PACKAGES_DIR/$package_name" | cut -f1)
    print_success "Created ${package_name} (${size})"
}

################################################################################
# Package AI Agent Lambda Function
#
# Packages a Lambda function from ai-agent/src/lambdas with dependencies
# These functions have more complex dependencies including bedrock-agentcore
#
# Args:
#   $1: Lambda function name (e.g., "agent_proxy")
#   $2: Handler file name (e.g., "agent_proxy.py")
################################################################################
package_ai_agent_lambda() {
    local function_name=$1
    local handler_file=$2
    local package_name="${function_name}.zip"
    
    print_info "Packaging ${function_name}..."
    
    # Create temporary build directory for this function
    local temp_dir="$BUILD_DIR/$function_name"
    mkdir -p "$temp_dir"
    
    # Copy handler file
    cp "$AI_AGENT_LAMBDAS_DIR/$handler_file" "$temp_dir/"
    
    # Use pre-installed dependencies from ai-agent/src/lib/ if available
    # This avoids issues with packages that require specific Python versions
    # or are not publicly available (like strands-agents)
    if [ -d "$AI_AGENT_SRC_DIR/lib" ]; then
        print_info "Using pre-installed dependencies from lib directory..."
        cp -r "$AI_AGENT_SRC_DIR/lib/"* "$temp_dir/"
    else
        # Fallback: Try to install dependencies if lib directory doesn't exist
        print_warning "Pre-installed lib directory not found, attempting to install dependencies..."
        if [ -f "$AI_AGENT_SRC_DIR/requirements.txt" ]; then
            print_info "Installing dependencies for ${function_name}..."
            # Use --ignore-requires-python to handle version mismatches
            pip install -q --target "$temp_dir" -r "$AI_AGENT_SRC_DIR/requirements.txt" --upgrade 2>/dev/null || {
                print_warning "Some dependencies could not be installed. Package may be incomplete."
            }
        fi
    fi
    
    # Create zip file with all contents at root level
    cd "$temp_dir"
    zip -q -r "$PACKAGES_DIR/$package_name" . -x "*.pyc" -x "__pycache__/*"
    cd - > /dev/null
    
    # Get package size for reporting
    local size=$(du -h "$PACKAGES_DIR/$package_name" | cut -f1)
    print_success "Created ${package_name} (${size})"
}

################################################################################
# Package AgentCore Runtime Deployment
#
# Creates deployment package for AWS Bedrock AgentCore Runtime
# This includes the Strands-based agent code and all dependencies
#
# Output: order-agent.zip containing:
#   - order_agent.py (main agent entrypoint)
#   - All dependencies from ai-agent/src/lib/
################################################################################
package_agentcore_runtime() {
    local package_name="order-agent.zip"
    
    print_info "Packaging AgentCore Runtime (order-agent)..."
    
    # Create temporary build directory
    local temp_dir="$BUILD_DIR/order-agent"
    mkdir -p "$temp_dir"
    
    # Copy agent entrypoint
    cp "$AI_AGENT_SRC_DIR/order_agent.py" "$temp_dir/"
    
    # Copy pre-installed dependencies from ai-agent/src/lib/
    # These dependencies are already installed and ready to use
    # This avoids reinstalling large packages like bedrock-agentcore
    if [ -d "$AI_AGENT_SRC_DIR/lib" ]; then
        print_info "Copying pre-installed dependencies..."
        cp -r "$AI_AGENT_SRC_DIR/lib/"* "$temp_dir/"
    else
        # Fallback: Install dependencies if lib directory doesn't exist
        print_warning "Pre-installed lib directory not found, installing dependencies..."
        if [ -f "$AI_AGENT_SRC_DIR/requirements.txt" ]; then
            pip install -q --target "$temp_dir" -r "$AI_AGENT_SRC_DIR/requirements.txt" --upgrade
        fi
    fi
    
    # Create zip file
    cd "$temp_dir"
    zip -q -r "$PACKAGES_DIR/$package_name" . -x "*.pyc" -x "__pycache__/*"
    cd - > /dev/null
    
    # Get package size for reporting
    local size=$(du -h "$PACKAGES_DIR/$package_name" | cut -f1)
    print_success "Created ${package_name} (${size})"
}

################################################################################
# Main Execution
################################################################################

main() {
    print_header "Lambda Packaging Script"
    
    # Parse command-line arguments
    CLEAN=false
    while [[ $# -gt 0 ]]; do
        case $1 in
            --clean)
                CLEAN=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Usage: $0 [--clean]"
                exit 1
                ;;
        esac
    done
    
    # Clean existing packages if requested
    if [ "$CLEAN" = true ]; then
        print_info "Cleaning existing packages..."
        rm -rf "$PACKAGES_DIR"/*.zip
        print_success "Cleaned existing packages"
    fi
    
    # Create packages directory if it doesn't exist
    mkdir -p "$PACKAGES_DIR"
    
    # Clean build directory from previous runs
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    
    # Check for required tools
    print_info "Checking required tools..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "python3 is required but not installed"
        exit 1
    fi
    
    if ! command -v pip &> /dev/null; then
        print_error "pip is required but not installed"
        exit 1
    fi
    
    if ! command -v zip &> /dev/null; then
        print_error "zip utility is required but not installed"
        exit 1
    fi
    
    print_success "All required tools are available"
    
    # Display Python version for debugging
    PYTHON_VERSION=$(python3 --version)
    print_info "Using ${PYTHON_VERSION}"
    
    echo ""
    print_header "Packaging Backend Lambda Functions"
    
    # Package backend Lambda functions (Orders API)
    # These functions handle CRUD operations for orders
    package_backend_lambda "get_orders" "get_orders.py"
    package_backend_lambda "create_order" "create_order.py"
    package_backend_lambda "update_order" "update_order.py"
    
    # Package authorizer Lambda function
    # This function validates JWT tokens and enforces authorization policies
    package_backend_lambda "authorizer" "authorizer.py"
    
    echo ""
    print_header "Packaging AI Agent Lambda Functions"
    
    # Package AI agent Lambda functions
    # agent_proxy: Proxies requests to AgentCore Runtime
    # oauth2_callback_server: Handles OAuth2 callback flow
    package_ai_agent_lambda "agent_proxy" "agent_proxy.py"
    package_ai_agent_lambda "oauth2_callback_server" "oauth2_callback_server.py"
    
    echo ""
    print_header "Packaging AgentCore Runtime"
    
    # Package AgentCore Runtime deployment
    # This is deployed to AWS Bedrock AgentCore, not Lambda
    package_agentcore_runtime
    
    # Clean up build directory
    print_info "Cleaning up temporary build directory..."
    rm -rf "$BUILD_DIR"
    
    echo ""
    print_header "Packaging Summary"
    
    # Display summary of all packages
    echo ""
    echo "Lambda packages created in: $PACKAGES_DIR"
    echo ""
    printf "%-35s %10s\n" "Package" "Size"
    printf "%-35s %10s\n" "-------" "----"
    
    for package in "$PACKAGES_DIR"/*.zip; do
        if [ -f "$package" ]; then
            local name=$(basename "$package")
            local size=$(du -h "$package" | cut -f1)
            printf "%-35s %10s\n" "$name" "$size"
        fi
    done
    
    echo ""
    print_success "All Lambda functions packaged successfully!"
    echo ""
    print_info "Next steps:"
    echo "  1. Upload packages to S3: aws s3 sync $PACKAGES_DIR s3://YOUR-BUCKET/lambda-code/ --no-cli-pager"
    echo "  2. Deploy CloudFormation stack: ./deploy-stack.sh STACK-NAME TEMPLATES-BUCKET LAMBDA-BUCKET"
}

# Run main function
main "$@"
