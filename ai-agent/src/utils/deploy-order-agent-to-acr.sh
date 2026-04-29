#!/usr/bin/env bash
#
# Deploy Order Agent to Amazon Bedrock AgentCore Runtime (Direct Code Deployment)
#
# This script packages the Strands-based order agent and deploys it to AgentCore Runtime
# using direct code deployment (zip archive method) with CloudWatch logging and OpenTelemetry enabled.
#
# Prerequisites:
#   - AWS CLI v2 with bedrock-agentcore-control commands
#   - Python 3.12+ with uv package manager installed
#   - AWS credentials configured with appropriate permissions
#   - S3 bucket for deployment artifacts
#   - IAM execution role for AgentCore Runtime
#
# Usage:
#   AGENT_NAME=order-agent \
#   REGION=us-east-1 \
#   RUNTIME_ROLE_ARN=arn:aws:iam::123456789012:role/AgentCoreRuntimeRole \
#   S3_BUCKET=my-app-resources-bucket \
#   ./deploy-order-agent-to-acr.sh
#
# Optional Environment Variables:
#   AGENT_RUNTIME_ID - Existing runtime ID for updates (creates new if not set)
#   PYTHON_VERSION - Python runtime version (default: PYTHON_3_12)
#   GATEWAY_SECRET_NAME - Secrets Manager secret name (default: agentcore/gateway-authcode)
#   MODEL_ID - Bedrock model ID (default: us.anthropic.claude-sonnet-4-5-20250929-v1:0)
#   DISABLE_OTEL - Disable OpenTelemetry observability (default: false, OTEL enabled by default)

set -euo pipefail

# Disable AWS CLI pager to prevent output from opening in editor
export AWS_PAGER=""

# ============================================================================
# Configuration
# ============================================================================

# Load configuration from properties file
SCRIPT_DIR_TEMP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROPERTIES_FILE="$SCRIPT_DIR_TEMP/order-agent.properties"

if [ -f "$PROPERTIES_FILE" ]; then
    log_info() { echo -e "\033[0;34m[INFO]\033[0m $1"; }
    log_info "Loading configuration from $PROPERTIES_FILE"
    
    # Source the properties file, ignoring comments and empty lines
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        
        # Trim whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        
        # Export the variable
        export "$key=$value"
    done < "$PROPERTIES_FILE"
else
    log_warning() { echo -e "\033[1;33m[WARNING]\033[0m $1"; }
    log_warning "Properties file not found: $PROPERTIES_FILE"
    log_warning "Using environment variables or defaults"
fi

# Configuration with fallback to defaults (for backward compatibility)
AGENT_NAME=${AGENT_NAME:-order-agent}
# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION or REGION environment variable to use a different region
REGION=${REGION:-${AWS_REGION:-us-west-2}}
RUNTIME_ROLE_ARN=${RUNTIME_ROLE_ARN:-}
S3_BUCKET=${S3_BUCKET:-}
AGENT_RUNTIME_ID=${AGENT_RUNTIME_ID:-}
PYTHON_VERSION=${PYTHON_VERSION:-PYTHON_3_12}
GATEWAY_SECRET_NAME=${GATEWAY_SECRET_NAME:-agentcore/gateway-authcode}
MODEL_ID=${MODEL_ID:-us.anthropic.claude-sonnet-4-5-20250929-v1:0}
ENABLE_OTEL=${ENABLE_OTEL:-true}
OAUTH_CALLBACK_SERVER_URL=${OAUTH_CALLBACK_SERVER_URL:-}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Derived configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOYMENT_DIR="$PROJECT_ROOT/build/deployment"
PACKAGE_NAME="order_agent_deployment.zip"
S3_KEY="${AGENT_NAME}/${PACKAGE_NAME}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install AWS CLI v2."
        exit 1
    fi
    
    # Check uv
    if ! command -v uv &> /dev/null; then
        log_error "uv is not installed. Install from: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials are not configured or invalid."
        exit 1
    fi
    
    # Check S3 bucket exists
    if ! aws s3 ls "s3://${S3_BUCKET}" --region "$REGION" &> /dev/null; then
        log_error "S3 bucket '${S3_BUCKET}' does not exist or is not accessible."
        exit 1
    fi
    
    log_success "All prerequisites met"
}

print_configuration() {
    log_info "Deployment Configuration:"
    echo "  Agent Name:                 $AGENT_NAME"
    echo "  Region:                     $REGION"
    echo "  Account ID:                 $ACCOUNT_ID"
    echo "  S3 Bucket:                  $S3_BUCKET"
    echo "  S3 Key:                     $S3_KEY"
    echo "  Python Version:             $PYTHON_VERSION"
    echo "  Runtime Role:               $RUNTIME_ROLE_ARN"
    echo "  Gateway Secret:             $GATEWAY_SECRET_NAME"
    echo "  Model ID:                   $MODEL_ID"
    echo "  OAuth2 Callback Server URL: $OAUTH_CALLBACK_SERVER_URL"
    echo "  Log Level:                  $LOG_LEVEL"
    echo "  CloudWatch Logs:            ENABLED"
    echo "  OpenTelemetry:     $([ "$ENABLE_OTEL" = "true" ] && echo "ENABLED" || echo "DISABLED")"
    if [ -n "$AGENT_RUNTIME_ID" ]; then
        echo "  Runtime ID:             $AGENT_RUNTIME_ID (UPDATE MODE)"
    else
        echo "  Runtime ID:             <will be created>"
    fi
    echo ""
}

# ============================================================================
# Build Deployment Package
# ============================================================================

build_deployment_package() {
    log_info "Building deployment package with observability enabled..."
    
    # Clean and create deployment directory
    rm -rf "$DEPLOYMENT_DIR"
    mkdir -p "$DEPLOYMENT_DIR"
    
    # Install core dependencies for ARM64 architecture (AgentCore Runtime requirement)
    log_info "Installing core dependencies for ARM64 architecture..."
    cd "$PROJECT_ROOT"
    
    uv pip install \
        --python-platform aarch64-manylinux2014 \
        --python-version 3.12 \
        --target="$DEPLOYMENT_DIR" \
        --only-binary=:all: \
        bedrock-agentcore \
        strands-agents \
        boto3 \
        httpx
    
    # Add OpenTelemetry instrumentation (enabled by default)
    if [ "$ENABLE_OTEL" = "true" ]; then
        log_info "Adding OpenTelemetry instrumentation for CloudWatch and X-Ray..."
        uv pip install \
            --python-platform aarch64-manylinux2014 \
            --python-version 3.12 \
            --target="$DEPLOYMENT_DIR" \
            --only-binary=:all: \
            aws-opentelemetry-distro \
            opentelemetry-api \
            opentelemetry-sdk \
            opentelemetry-instrumentation
        
        log_success "OpenTelemetry instrumentation added for enhanced observability"
    else
        log_warning "OpenTelemetry is disabled. CloudWatch logs will still be available but without detailed traces."
    fi
    
    # Copy agent code
    log_info "Copying agent code..."
    cp "$PROJECT_ROOT/order_agent.py" "$DEPLOYMENT_DIR/"
    
    # Copy lambda functions (if needed by the agent)
    if [ -d "$PROJECT_ROOT/lambdas" ]; then
        log_info "Copying lambda functions..."
        cp -r "$PROJECT_ROOT/lambdas" "$DEPLOYMENT_DIR/"
    fi
    
    # Set correct permissions (AgentCore Runtime requirement)
    log_info "Setting file permissions..."
    find "$DEPLOYMENT_DIR" -type f -exec chmod 644 {} \;
    find "$DEPLOYMENT_DIR" -type d -exec chmod 755 {} \;
    chmod 755 "$DEPLOYMENT_DIR/order_agent.py"
    
    # Create zip archive
    log_info "Creating deployment package..."
    cd "$DEPLOYMENT_DIR"
    zip -r "../${PACKAGE_NAME}" . -q
    
    local package_size=$(du -h "$PROJECT_ROOT/build/${PACKAGE_NAME}" | cut -f1)
    log_success "Deployment package created: ${PACKAGE_NAME} (${package_size})"
    
    # Verify package size (250 MB limit for zipped)
    local size_bytes=$(stat -f%z "$PROJECT_ROOT/build/${PACKAGE_NAME}" 2>/dev/null || stat -c%s "$PROJECT_ROOT/build/${PACKAGE_NAME}")
    local max_size=$((250 * 1024 * 1024))
    if [ "$size_bytes" -gt "$max_size" ]; then
        log_error "Deployment package exceeds 250 MB limit (${package_size})"
        exit 1
    fi
}

# ============================================================================
# Upload to S3
# ============================================================================

upload_to_s3() {
    log_info "Uploading deployment package to S3..."
    
    aws s3 cp \
        "$PROJECT_ROOT/build/${PACKAGE_NAME}" \
        "s3://${S3_BUCKET}/${S3_KEY}" \
        --region "$REGION"
    
    log_success "Uploaded to s3://${S3_BUCKET}/${S3_KEY}"
}

# ============================================================================
# Deploy to AgentCore Runtime
# ============================================================================

deploy_to_agentcore() {
    log_info "Deploying to AgentCore Runtime with observability enabled..."
    
    # Build entrypoint array with OpenTelemetry instrumentation
    local entrypoint='["order_agent.py"]'
    if [ "$ENABLE_OTEL" = "true" ]; then
        entrypoint='["opentelemetry-instrument", "order_agent.py"]'
        log_info "Using OpenTelemetry-instrumented entrypoint for enhanced tracing"
    fi
    
    # Build environment variables as key-value pairs
    local env_vars="{\"AWS_REGION\":\"${REGION}\""
    env_vars="${env_vars},\"GATEWAY_SECRET_NAME\":\"${GATEWAY_SECRET_NAME}\""
    env_vars="${env_vars},\"BEDROCK_MODEL_ID\":\"${MODEL_ID}\""
    env_vars="${env_vars},\"GATEWAY_TOOLS_ENABLED\":\"true\""
    env_vars="${env_vars},\"OAUTH_FORCE_AUTH\":\"true\""
    env_vars="${env_vars},\"OAUTH_CALLBACK_SERVER_URL\":\"${OAUTH_CALLBACK_SERVER_URL}\""
    env_vars="${env_vars},\"LOG_LEVEL\":\"${LOG_LEVEL}\""
    
    # Add OpenTelemetry configuration for CloudWatch and X-Ray
    if [ "$ENABLE_OTEL" = "true" ]; then
        env_vars="${env_vars},\"OTEL_SERVICE_NAME\":\"${AGENT_NAME}\""
        env_vars="${env_vars},\"OTEL_TRACES_EXPORTER\":\"otlp\""
        env_vars="${env_vars},\"OTEL_METRICS_EXPORTER\":\"otlp\""
        env_vars="${env_vars},\"OTEL_LOGS_EXPORTER\":\"otlp\""
        env_vars="${env_vars},\"OTEL_PROPAGATORS\":\"tracecontext,baggage,xray\""
        env_vars="${env_vars},\"OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED\":\"true\""
    fi
    
    env_vars="${env_vars}}"
    
    if [ -n "$AGENT_RUNTIME_ID" ]; then
        # Update existing runtime
        log_info "Updating existing AgentCore Runtime: $AGENT_RUNTIME_ID"
        
        aws bedrock-agentcore-control update-agent-runtime \
            --region "$REGION" \
            --agent-runtime-id "$AGENT_RUNTIME_ID" \
            --description "Order Agent - Strands-based AI agent with MCP Gateway integration and CloudWatch observability" \
            --agent-runtime-artifact "{
                \"codeConfiguration\": {
                    \"code\": {
                        \"s3\": {
                            \"bucket\": \"${S3_BUCKET}\",
                            \"prefix\": \"${S3_KEY}\"
                        }
                    },
                    \"runtime\": \"${PYTHON_VERSION}\",
                    \"entryPoint\": ${entrypoint}
                }
            }" \
            --role-arn "$RUNTIME_ROLE_ARN" \
            --network-configuration "networkMode=PUBLIC" \
            --protocol-configuration "serverProtocol=HTTP" \
            --environment-variables "$env_vars"
        
        log_success "AgentCore Runtime updated: $AGENT_RUNTIME_ID"
    else
        # Create new runtime
        log_info "Creating new AgentCore Runtime with observability..."
        
        local response=$(aws bedrock-agentcore-control create-agent-runtime \
            --region "$REGION" \
            --agent-runtime-name "$AGENT_NAME" \
            --description "Order Agent - Strands-based AI agent with MCP Gateway integration and CloudWatch observability" \
            --agent-runtime-artifact "{
                \"codeConfiguration\": {
                    \"code\": {
                        \"s3\": {
                            \"bucket\": \"${S3_BUCKET}\",
                            \"prefix\": \"${S3_KEY}\"
                        }
                    },
                    \"runtime\": \"${PYTHON_VERSION}\",
                    \"entryPoint\": ${entrypoint}
                }
            }" \
            --role-arn "$RUNTIME_ROLE_ARN" \
            --network-configuration "networkMode=PUBLIC" \
            --protocol-configuration "serverProtocol=HTTP" \
            --environment-variables "$env_vars" \
            --output json)
        
        AGENT_RUNTIME_ID=$(echo "$response" | jq -r '.agentRuntimeId')
        local runtime_arn=$(echo "$response" | jq -r '.agentRuntimeArn')
        local status=$(echo "$response" | jq -r '.status')
        
        log_success "AgentCore Runtime created successfully!"
        echo "  Runtime ID:  $AGENT_RUNTIME_ID"
        echo "  Runtime ARN: $runtime_arn"
        echo "  Status:      $status"
    fi
}

# ============================================================================
# Create or Update Endpoint
# ============================================================================

manage_endpoint() {
    log_info "Managing endpoint for AgentCore Runtime..."
    
    # Check if default endpoint exists
    local endpoints=$(aws bedrock-agentcore-control list-agent-runtime-endpoints \
        --region "$REGION" \
        --agent-runtime-id "$AGENT_RUNTIME_ID" \
        --output json)
    
    local endpoint_count=$(echo "$endpoints" | jq '.agentRuntimeEndpointSummaries | length')
    
    if [ "$endpoint_count" -eq 0 ]; then
        log_info "Creating default endpoint..."
        
        local endpoint_response=$(aws bedrock-agentcore-control create-agent-runtime-endpoint \
            --region "$REGION" \
            --agent-runtime-id "$AGENT_RUNTIME_ID" \
            --name "${AGENT_NAME}-endpoint" \
            --description "Default endpoint for ${AGENT_NAME}" \
            --output json)
        
        local endpoint_id=$(echo "$endpoint_response" | jq -r '.agentRuntimeEndpointId')
        local endpoint_arn=$(echo "$endpoint_response" | jq -r '.agentRuntimeEndpointArn')
        
        log_success "Endpoint created successfully!"
        echo "  Endpoint ID:  $endpoint_id"
        echo "  Endpoint ARN: $endpoint_arn"
    else
        log_info "Endpoint already exists (count: $endpoint_count)"
        echo "$endpoints" | jq -r '.agentRuntimeEndpointSummaries[] | "  - \(.name) (\(.agentRuntimeEndpointId))"'
    fi
}

# ============================================================================
# Display Observability Information
# ============================================================================

show_observability_info() {
    log_info "Observability Configuration:"
    echo ""
    echo "CloudWatch Logs:"
    echo "  Log Group: /aws/bedrock/agentcore/runtime/${AGENT_RUNTIME_ID}"
    echo "  View logs: https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups/log-group/\$252Faws\$252Fbedrock\$252Fagentcore\$252Fruntime\$252F${AGENT_RUNTIME_ID}"
    echo ""
    
    if [ "$ENABLE_OTEL" = "true" ]; then
        echo "AWS X-Ray Traces:"
        echo "  Service Map: https://console.aws.amazon.com/xray/home?region=${REGION}#/service-map"
        echo "  Traces: https://console.aws.amazon.com/xray/home?region=${REGION}#/traces"
        echo "  Service: ${AGENT_NAME}"
        echo ""
        echo "CloudWatch Transaction Search:"
        echo "  View traces: https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#transaction-search:"
        echo ""
    fi
}

# ============================================================================
# Display Invocation Instructions
# ============================================================================

show_invocation_instructions() {
    log_success "Deployment completed successfully!"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  INVOCATION INSTRUCTIONS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "To invoke your agent programmatically using boto3:"
    echo ""
    echo "import boto3"
    echo ""
    echo "client = boto3.client('bedrock-agentcore-runtime', region_name='${REGION}')"
    echo "response = client.invoke_agent("
    echo "    agentRuntimeId='${AGENT_RUNTIME_ID}',"
    echo "    prompt='Create an order for 5 widgets'"
    echo ")"
    echo "print(response['result'])"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "To test via AWS CLI:"
    echo ""
    echo "aws bedrock-agentcore-runtime invoke-agent \\"
    echo "  --region ${REGION} \\"
    echo "  --agent-runtime-id ${AGENT_RUNTIME_ID} \\"
    echo "  --prompt 'Create an order for 5 widgets'"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    show_observability_info
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Resources:"
    echo "  - Runtime ID: ${AGENT_RUNTIME_ID}"
    echo "  - S3 Package: s3://${S3_BUCKET}/${S3_KEY}"
    echo "  - Region:     ${REGION}"
    echo ""
}

# ============================================================================
# Cleanup Function
# ============================================================================

cleanup() {
    if [ -d "$DEPLOYMENT_DIR" ]; then
        log_info "Cleaning up temporary files..."
        rm -rf "$PROJECT_ROOT/build"
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  AgentCore Runtime Direct Code Deployment                     ║"
    echo "║  Order Agent - Strands Framework                              ║"
    echo "║  CloudWatch Logs & OpenTelemetry Enabled                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Trap cleanup on exit
    trap cleanup EXIT
    
    # Execute deployment steps
    check_prerequisites
    print_configuration
    build_deployment_package
    upload_to_s3
    deploy_to_agentcore
    manage_endpoint
    show_invocation_instructions
}

# Run main function
main "$@"
