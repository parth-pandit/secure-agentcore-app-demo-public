#!/bin/bash
################################################################################
# Multi-Region Deployment Script — Project Redwood
#
# Single entry point for all deployments: infrastructure, memory, frontend,
# and agent runtime. Idempotent — safe to re-run.
#
# Usage:
#   ./deploy-stack-multi-region.sh [options]
#
# Options:
#   --frontend        Update frontend only (S3 + CloudFront invalidation)
#   --runtime         Update agent runtime only (package + upload + update)
#   --memory          Deploy memory stacks only (both regions)
#   --infra           Deploy CFN infrastructure only (no code updates)
#   --primary-only    Deploy only primary region (us-east-1)
#   --dr-only         Deploy only DR region (us-east-2)
#   --skip-memory     Skip memory deployment (in full mode)
#   --suffix SUFFIX   Deployment suffix (default: 202605110202)
#   --help            Show this help
#
# Examples:
#   ./deploy-stack-multi-region.sh                    # Full deploy (all components)
#   ./deploy-stack-multi-region.sh --frontend         # Frontend update only
#   ./deploy-stack-multi-region.sh --runtime          # Agent runtime update only
#   ./deploy-stack-multi-region.sh --memory           # Memory stacks only
################################################################################

set -e
export AWS_PAGER=""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CFN_SCRIPTS_DIR="${PROJECT_ROOT}/infrastructure/cloudformation/scripts"
TEMPLATES_DIR="${PROJECT_ROOT}/infrastructure/cloudformation/templates"
MULTI_REGION_DIR="${PROJECT_ROOT}/infrastructure/multi-region"
MEMORY_DIR="${MULTI_REGION_DIR}/memory"
PARAMETERS_DIR="${PROJECT_ROOT}/infrastructure/cloudformation/parameters"
AGENT_SRC="${PROJECT_ROOT}/ai-agent/src"

# Source deployment configuration
source "${PROJECT_ROOT}/infrastructure/deploy-config-multi-region.sh"

# Safety check: verify the resolved AWS account matches expectations
ACTUAL_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "${ACTUAL_ACCOUNT}" ]; then
    log_error "Cannot resolve AWS account. Check credentials/profile."
    exit 1
fi
if [ -n "${AWS_ACCOUNT_ID}" ] && [ "${ACTUAL_ACCOUNT}" != "${AWS_ACCOUNT_ID}" ]; then
    log_error "ACCOUNT MISMATCH! Config expects ${AWS_ACCOUNT_ID} but CLI resolves to ${ACTUAL_ACCOUNT}"
    log_error "Check AWS_PROFILE in deploy-config-multi-region.sh"
    exit 1
fi
export AWS_ACCOUNT_ID="${ACTUAL_ACCOUNT}"

# Parameter file (must be after sourcing config for ENVIRONMENT variable)
PARAMETER_FILE="${PARAMETERS_DIR}/${ENVIRONMENT}-parameters-multi-region.json"

# Overridable via CLI (parsed below)
TEMPLATES_BUCKET="${CFN_TEMPLATES_BUCKET}"

# Ensure S3 buckets exist (auto-create if missing)
ensure_bucket "${CFN_TEMPLATES_BUCKET}" "${PRIMARY_REGION}"
ensure_bucket "${CFN_TEMPLATES_BUCKET_DR}" "${DR_REGION}"
ensure_bucket "${LAMBDA_BUCKET_PRIMARY}" "${PRIMARY_REGION}"
ensure_bucket "${LAMBDA_BUCKET_DR}" "${DR_REGION}"
PROFILE=""

# Parse options FIRST (before derived config)
MODE="full"  # full | frontend | runtime | memory | infra
DEPLOY_PRIMARY=true
DEPLOY_DR=true
DEPLOY_MEMORY=true
UPDATE_MODE=false  # When true: repackage + force-update all artifacts

while [ $# -gt 0 ]; do
    case "$1" in
        --frontend)              MODE="frontend"; shift ;;
        --runtime)               MODE="runtime"; shift ;;
        --memory)                MODE="memory"; shift ;;
        --infra)                 MODE="infra"; shift ;;
        --update)                UPDATE_MODE=true; shift ;;
        --primary-only)          DEPLOY_DR=false; shift ;;
        --dr-only)               DEPLOY_PRIMARY=false; shift ;;
        --skip-memory)           DEPLOY_MEMORY=false; shift ;;
        --suffix)                SUFFIX="$2"; shift 2 ;;
        --environment)           ENVIRONMENT="$2"; shift 2 ;;
        --profile)               PROFILE="$2"; shift 2 ;;
        --region)                PRIMARY_REGION="$2"; shift 2 ;;
        --dr-region)             DR_REGION="$2"; shift 2 ;;
        --stack-name)            STACK_NAME_OVERRIDE="$2"; shift 2 ;;
        --cfn-templates-bucket)  TEMPLATES_BUCKET="$2"; shift 2 ;;
        --lambda-code-bucket)    LAMBDA_BUCKET_PRIMARY="$2"; shift 2 ;;
        --help)
            echo ""
            echo "Usage: $(basename $0) [options]"
            echo ""
            echo "Deploy Modes (pick one, default: full):"
            echo "  --frontend              Update frontend only (S3 + CloudFront)"
            echo "  --runtime               Update agent runtime (both regions)"
            echo "  --memory                Deploy memory stacks (both regions)"
            echo "  --infra                 Deploy CFN infrastructure (both regions)"
            echo ""
            echo "Behavior:"
            echo "  (default)               Create-if-missing + verify (fast, idempotent)"
            echo "  --update                Force repackage + redeploy all artifacts (full rebuild)"
            echo ""
            echo "Region Control (optional — both regions by default):"
            echo "  --primary-only          Restrict to primary region only"
            echo "  --dr-only               Restrict to DR region only"
            echo "  --skip-memory           Skip memory in full deploy mode"
            echo ""
            echo "Examples:"
            echo "  $(basename $0)                              # Create-if-missing (fast)"
            echo "  $(basename $0) --update                     # Full rebuild + redeploy"
            echo "  $(basename $0) --runtime --update           # Rebuild + redeploy runtime only"
            echo "  $(basename $0) --frontend --update          # Rebuild + redeploy frontend only"
            echo "  $(basename $0) --infra --primary-only       # Infra, primary only"
            echo ""
            exit 0
            ;;
        *)  log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# Derived config (after options parsed)
STACK_NAME="${STACK_NAME_OVERRIDE:-${STACK_NAME_PRIMARY}}"
AWS_PROFILE_FLAG=""
[ -n "${PROFILE}" ] && AWS_PROFILE_FLAG="--profile ${PROFILE}"

# Look up actual runtime ID (CFN appends a random suffix)
RUNTIME_ID="${ENVIRONMENT}_order_agent_runtime_${SUFFIX}"
FULL_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
    --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
    --query "agentRuntimes[?starts_with(agentRuntimeName, '${RUNTIME_ID}')].agentRuntimeId" \
    --output text 2>/dev/null || echo "")

# Memory IDs (look up from stacks if they exist)
MEMORY_ID_PRIMARY=$(aws cloudformation describe-stacks \
    --stack-name "$(get_memory_stack_name)" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
    --query 'Stacks[0].Outputs[?OutputKey==`MemoryId`].OutputValue' --output text 2>/dev/null || echo "")
MEMORY_ID_PRIMARY="${MEMORY_ID_PRIMARY##*/}"

MEMORY_ID_DR=$(aws cloudformation describe-stacks \
    --stack-name "$(get_memory_stack_name)" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
    --query 'Stacks[0].Outputs[?OutputKey==`MemoryId`].OutputValue' --output text 2>/dev/null || echo "")
MEMORY_ID_DR="${MEMORY_ID_DR##*/}"

# Lambda@Edge ARN (look up from stack if it exists)
LAMBDA_EDGE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${ENVIRONMENT}-lambda-edge-${SUFFIX}" --region us-east-1 ${AWS_PROFILE_FLAG} \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaEdgeArn`].OutputValue' --output text 2>/dev/null || echo "")

# Read MSAL config from parameters file (no interactive prompts)
MSAL_CLIENT_ID=$(python3 -c "
import json
with open('${PARAMETER_FILE}') as f:
    params = {p['ParameterKey']: p['ParameterValue'] for p in json.load(f) if 'ParameterKey' in p}
print(params.get('GatewayIdpClientId',''))
" 2>/dev/null)

MSAL_TENANT_ID=$(python3 -c "
import json
with open('${PARAMETER_FILE}') as f:
    params = {p['ParameterKey']: p['ParameterValue'] for p in json.load(f) if 'ParameterKey' in p}
print(params.get('TargetIdpTenantId',''))
" 2>/dev/null)

MSAL_AUTHORITY="https://login.microsoftonline.com/${MSAL_TENANT_ID}"

STACK_NAME="${STACK_NAME}"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Project Redwood — Multi-Region Deployment                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
log_info "Mode: ${MODE}$([ "${UPDATE_MODE}" = true ] && echo ' [--update: full rebuild]' || echo ' [create-if-missing]')"
log_info "Stack: ${STACK_NAME} | Suffix: ${SUFFIX}"
log_info "Regions: Primary=${PRIMARY_REGION}, DR=${DR_REGION}"
if [ -n "${FULL_RUNTIME_ID}" ]; then
    log_info "Runtime: ${FULL_RUNTIME_ID}"
fi
if [ -n "${MEMORY_ID_PRIMARY}" ]; then
    log_info "Memory Primary: ${MEMORY_ID_PRIMARY}"
fi
echo ""

################################################################################
# FRONTEND ONLY
################################################################################
deploy_frontend() {
    log_info "━━━ Frontend Update ━━━"

    # Get CloudFront info — try global stack first, fall back to primary regional stack
    local GLOBAL_STACK="secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global"
    FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name "${GLOBAL_STACK}" --region "${PRIMARY_REGION}" \
        --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' --output text 2>/dev/null)
    CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
        --stack-name "${GLOBAL_STACK}" --region "${PRIMARY_REGION}" \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' --output text 2>/dev/null)
    CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name "${GLOBAL_STACK}" --region "${PRIMARY_REGION}" \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' --output text 2>/dev/null)

    # Fallback: if global stack doesn't exist, try the primary regional stack (old architecture)
    if [ -z "${FRONTEND_BUCKET}" ] || [ "${FRONTEND_BUCKET}" = "None" ]; then
        log_info "  Global stack not found — using primary regional stack outputs"
        FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" \
            --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' --output text 2>/dev/null)
        CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" \
            --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' --output text 2>/dev/null)
        CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" \
            --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' --output text 2>/dev/null)
    fi

    AGENTCORE_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' --output text 2>/dev/null)
    # If Lambda@Edge is deployed, use relative path (goes through CloudFront)
    if [ -n "${LAMBDA_EDGE_ARN:-}" ] && [ "${LAMBDA_EDGE_ARN}" != "None" ]; then
        AGENTCORE_ENDPOINT="/api/invoke"
    else
        AGENTCORE_ENDPOINT="${AGENTCORE_ENDPOINT%/}/invoke"
    fi

    if [ -z "${FRONTEND_BUCKET}" ] || [ "${FRONTEND_BUCKET}" = "None" ]; then
        log_error "Could not find frontend bucket. Deploy infra first."
        return 1
    fi

    # Skip if already deployed and not in update mode
    if [ "${UPDATE_MODE}" = false ]; then
        if aws s3api head-object --bucket "${FRONTEND_BUCKET}" --key "index.html" \
            --region "${PRIMARY_REGION}" > /dev/null 2>&1; then
            log_success "Frontend already deployed (use --update to redeploy): https://${CLOUDFRONT_DOMAIN}"
            return 0
        fi
    fi

    # Set env vars for build-config.js (no interactive prompts)
    export MSAL_CLIENT_ID="${MSAL_CLIENT_ID}"
    export MSAL_AUTHORITY="${MSAL_AUTHORITY}"
    export REDIRECT_URI="https://${CLOUDFRONT_DOMAIN}"
    export AGENTCORE_ENDPOINT="${AGENTCORE_ENDPOINT}"
    export WS_SIGN_ENDPOINT=""

    log_info "  MSAL_CLIENT_ID: ${MSAL_CLIENT_ID}"
    log_info "  REDIRECT_URI:   https://${CLOUDFRONT_DOMAIN}"
    log_info "  ENDPOINT:       ${AGENTCORE_ENDPOINT}"

    # Install deps if needed
    FRONTEND_DIR="${PROJECT_ROOT}/frontend"
    if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
        npm install --prefix "${FRONTEND_DIR}" --silent
    fi

    # Build config
    node "${FRONTEND_DIR}/build-config.js"

    # Upload
    aws s3 sync "${FRONTEND_DIR}/src/" "s3://${FRONTEND_BUCKET}/" \
        --exclude "*.md" --exclude ".DS_Store" --exclude "__tests__/*" \
        --region "${PRIMARY_REGION}"

    # Invalidate
    aws cloudfront create-invalidation \
        --distribution-id "${CLOUDFRONT_DIST_ID}" \
        --paths "/*" > /dev/null 2>&1

    log_success "Frontend updated: https://${CLOUDFRONT_DOMAIN}"
}

################################################################################
# RUNTIME ONLY
################################################################################
deploy_runtime() {
    log_info "━━━ Agent Runtime Update ━━━"

    # Re-lookup runtime ID (may have been created during infra deploy)
    local RUNTIME_ID_NAME="${ENVIRONMENT}_order_agent_runtime_${SUFFIX}"
    FULL_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
        --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query "agentRuntimes[?starts_with(agentRuntimeName, '${RUNTIME_ID_NAME}')].agentRuntimeId" \
        --output text 2>/dev/null || echo "")
    if [ -z "${FULL_RUNTIME_ID}" ] || [ "${FULL_RUNTIME_ID}" = "None" ]; then
        log_warning "Runtime not found — skipping runtime update"
        return 0
    fi

    # Skip if runtime exists and not in update mode
    if [ "${UPDATE_MODE}" = false ]; then
        local RT_VERSION=$(aws bedrock-agentcore-control get-agent-runtime \
            --agent-runtime-id "${FULL_RUNTIME_ID}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query "agentRuntimeVersion" --output text 2>/dev/null || echo "")
        if [ -n "${RT_VERSION}" ] && [ "${RT_VERSION}" != "None" ] && [ "${RT_VERSION}" != "1" ]; then
            log_success "Runtime already deployed (v${RT_VERSION}, use --update to redeploy)"
            return 0
        fi
    fi
    # Also refresh role ARN
    RUNTIME_ROLE_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
        --agent-runtime-id "${FULL_RUNTIME_ID}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query "roleArn" --output text 2>/dev/null)
    log_info "  Runtime: ${FULL_RUNTIME_ID}"

    PACKAGES_DIR="${PROJECT_ROOT}/infrastructure/lambda-packages"
    ZIP_PATH="${PACKAGES_DIR}/order-agent.zip"
    BUILD_DIR="${PROJECT_ROOT}/.lambda-build/order-agent"

    # Package
    rm -rf "${BUILD_DIR}"
    mkdir -p "${BUILD_DIR}" "${PACKAGES_DIR}"

    uv pip install \
        --python-platform aarch64-manylinux2014 \
        --python-version 3.12 \
        --target="${BUILD_DIR}" \
        --only-binary=:all: \
        -r "${AGENT_SRC}/requirements.txt" \
        2>&1 | tail -3

    cp "${AGENT_SRC}/order_agent.py" "${BUILD_DIR}/"
    cd "${BUILD_DIR}"
    zip -qr "${ZIP_PATH}" . -x "*.pyc" -x "__pycache__/*"
    cd - > /dev/null
    rm -rf "${PROJECT_ROOT}/.lambda-build"

    ZIP_SIZE=$(du -h "${ZIP_PATH}" | cut -f1)
    log_info "  Package: ${ZIP_SIZE}"

    # Upload
    aws s3 cp "${ZIP_PATH}" "s3://${LAMBDA_BUCKET_PRIMARY}/${RUNTIME_S3_KEY}" --region "${PRIMARY_REGION}"

    # Update via boto3
    GATEWAY_SECRET_NAME="${ENVIRONMENT}-gateway-secret-${SUFFIX}"
    OAUTH_CALLBACK_URL=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' --output text 2>/dev/null)

    python3 -c "
import boto3, sys
ac = boto3.client('bedrock-agentcore-control', region_name='${PRIMARY_REGION}')
env_vars = {
    'AWS_REGION': '${PRIMARY_REGION}',
    'BEDROCK_MODEL_ID': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    'GATEWAY_SECRET_NAME': '${GATEWAY_SECRET_NAME}',
    'GATEWAY_TOOLS_ENABLED': 'true',
    'LOG_LEVEL': 'DEBUG',
    'OAUTH_CALLBACK_SERVER_URL': '${OAUTH_CALLBACK_URL}',
    'OAUTH_FORCE_AUTH': 'false',
    'MEMORY_ID': '${MEMORY_ID_PRIMARY}',
    'MEMORY_REGION': '${PRIMARY_REGION}',
    'MEMORY_RECALL_MAX_EVENTS': '10',
    'OTEL_SERVICE_NAME': 'order-agent',
    'OTEL_TRACES_EXPORTER': 'otlp',
    'OTEL_METRICS_EXPORTER': 'otlp',
    'OTEL_LOGS_EXPORTER': 'otlp',
    'OTEL_PROPAGATORS': 'tracecontext,baggage,xray',
    'OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED': 'true',
}
try:
    resp = ac.update_agent_runtime(
        agentRuntimeId='${FULL_RUNTIME_ID}',
        roleArn='${RUNTIME_ROLE_ARN}',
        agentRuntimeArtifact={
            'codeConfiguration': {
                'code': {'s3': {'bucket': '${LAMBDA_BUCKET_PRIMARY}', 'prefix': '${RUNTIME_S3_KEY}'}},
                'runtime': 'PYTHON_3_12',
                'entryPoint': ['opentelemetry-instrument', 'order_agent.py'],
            }
        },
        networkConfiguration={'networkMode': 'PUBLIC'},
        environmentVariables=env_vars,
    )
    print(f'  ✔ Runtime updated to version {resp.get(\"agentRuntimeVersion\", \"?\")}')
except Exception as e:
    print(f'  ✗ Update failed: {e}')
    sys.exit(1)
"
    log_success "Agent runtime updated"
}


################################################################################
# LAMBDA@EDGE — Update-in-place + publish new version
# Function is created once, then updated with new code on subsequent deploys.
# A new version is published each time and CloudFront is pointed to it.
################################################################################
deploy_lambda_edge() {
    log_info "━━━ Lambda@Edge Origin Router ━━━"

    local EDGE_DIR="${MULTI_REGION_DIR}/lambda-edge"
    local EDGE_ZIP="/tmp/origin-router-${SUFFIX}.zip"
    local EDGE_FUNCTION_NAME="${ENVIRONMENT}-origin-router-${SUFFIX}"
    local EDGE_ROLE_NAME="${ENVIRONMENT}-lambda-edge-role-${SUFFIX}"

    # Skip if function already exists and not in update mode
    if [ "${UPDATE_MODE}" = false ]; then
        if aws lambda get-function --function-name "${EDGE_FUNCTION_NAME}" \
            --region us-east-1 ${AWS_PROFILE_FLAG} > /dev/null 2>&1; then
            local LATEST_VER=$(aws lambda list-versions-by-function \
                --function-name "${EDGE_FUNCTION_NAME}" --region us-east-1 ${AWS_PROFILE_FLAG} \
                --query 'Versions[-1].Version' --output text 2>/dev/null || echo "1")
            LAMBDA_EDGE_ARN="arn:aws:lambda:us-east-1:${AWS_ACCOUNT_ID}:function:${EDGE_FUNCTION_NAME}:${LATEST_VER}"
            log_success "Lambda@Edge already deployed (use --update to redeploy): ${LAMBDA_EDGE_ARN}"
            return 0
        fi
    fi

    # [1] Ensure IAM role exists
    log_info "  Ensuring IAM role: ${EDGE_ROLE_NAME}..."
    if ! aws iam get-role --role-name "${EDGE_ROLE_NAME}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1; then
        log_info "  Creating Lambda@Edge IAM role..."
        aws iam create-role --role-name "${EDGE_ROLE_NAME}" \
            --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["lambda.amazonaws.com","edgelambda.amazonaws.com"]},"Action":"sts:AssumeRole"}]}' \
            ${AWS_PROFILE_FLAG} > /dev/null
        aws iam attach-role-policy --role-name "${EDGE_ROLE_NAME}" \
            --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
            ${AWS_PROFILE_FLAG}
        aws iam put-role-policy --role-name "${EDGE_ROLE_NAME}" --policy-name "ArcReadPolicy" \
            --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["route53-recovery-cluster:GetRoutingControlState"],"Resource":"*"}]}' \
            ${AWS_PROFILE_FLAG}
        log_info "  Waiting for IAM propagation..."
        sleep 10
    fi
    local EDGE_ROLE_ARN=$(aws iam get-role --role-name "${EDGE_ROLE_NAME}" ${AWS_PROFILE_FLAG} \
        --query 'Role.Arn' --output text)

    # [2] Package Lambda@Edge code
    log_info "  Packaging Lambda@Edge..."
    local EDGE_BUILD="/tmp/lambda-edge-build-${SUFFIX}"
    rm -rf "${EDGE_BUILD}"
    mkdir -p "${EDGE_BUILD}"

    local USE1_API_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME_PRIMARY}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' --output text 2>/dev/null || echo "placeholder.execute-api.us-east-1.amazonaws.com")
    USE1_API_DOMAIN=$(echo "${USE1_API_DOMAIN}" | sed 's|https://||' | sed 's|/$||')

    local USE2_API_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME_DR}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' --output text 2>/dev/null || echo "placeholder.execute-api.us-east-2.amazonaws.com")
    USE2_API_DOMAIN=$(echo "${USE2_API_DOMAIN}" | sed 's|https://||' | sed 's|/$||')

    sed -e "s|__ARC_ROUTING_CONTROL_ARN__|${ARC_ROUTING_CONTROL_ARN}|g" \
        -e "s|__ARC_ENDPOINT_USW2__|${ARC_CLUSTER_ENDPOINTS[0]}|g" \
        -e "s|__ARC_ENDPOINT_EUW1__|${ARC_CLUSTER_ENDPOINTS[1]}|g" \
        -e "s|__ARC_ENDPOINT_APNE1__|${ARC_CLUSTER_ENDPOINTS[2]}|g" \
        -e "s|__ARC_ENDPOINT_APSE2__|${ARC_CLUSTER_ENDPOINTS[3]}|g" \
        -e "s|__ARC_ENDPOINT_USE1__|${ARC_CLUSTER_ENDPOINTS[4]}|g" \
        -e "s|__USE1_API_DOMAIN__|${USE1_API_DOMAIN}|g" \
        -e "s|__USE2_API_DOMAIN__|${USE2_API_DOMAIN}|g" \
        "${EDGE_DIR}/origin_router.js" > "${EDGE_BUILD}/origin_router.js"

    cd "${EDGE_BUILD}"
    npm init -y > /dev/null 2>&1
    npm install --production @aws-sdk/client-route53-recovery-cluster > /dev/null 2>&1
    zip -qr "${EDGE_ZIP}" .
    cd - > /dev/null

    # [3] Create or update Lambda function
    if aws lambda get-function --function-name "${EDGE_FUNCTION_NAME}" \
        --region us-east-1 ${AWS_PROFILE_FLAG} > /dev/null 2>&1; then
        log_info "  Updating function code..."
        aws lambda update-function-code \
            --function-name "${EDGE_FUNCTION_NAME}" \
            --zip-file "fileb://${EDGE_ZIP}" \
            --region us-east-1 ${AWS_PROFILE_FLAG} > /dev/null
        sleep 3
    else
        log_info "  Creating Lambda@Edge function..."
        aws lambda create-function \
            --function-name "${EDGE_FUNCTION_NAME}" \
            --runtime nodejs20.x \
            --role "${EDGE_ROLE_ARN}" \
            --handler origin_router.handler \
            --zip-file "fileb://${EDGE_ZIP}" \
            --timeout 10 \
            --memory-size 128 \
            --description "Lambda@Edge origin router - ARC-based multi-region failover" \
            --region us-east-1 ${AWS_PROFILE_FLAG} > /dev/null
        sleep 5
    fi

    # [4] Publish new version
    log_info "  Publishing new version..."
    local NEW_VERSION=$(aws lambda publish-version \
        --function-name "${EDGE_FUNCTION_NAME}" \
        --region us-east-1 ${AWS_PROFILE_FLAG} \
        --query "Version" --output text 2>/dev/null || echo "")

    if [ -n "${NEW_VERSION}" ] && [ "${NEW_VERSION}" != "None" ]; then
        LAMBDA_EDGE_ARN="arn:aws:lambda:us-east-1:${AWS_ACCOUNT_ID}:function:${EDGE_FUNCTION_NAME}:${NEW_VERSION}"
        log_info "  Published version: ${NEW_VERSION}"

        # [5] Update CloudFront to use new version
        local GLOBAL_STACK="secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global"
        local CF_DIST_ID=$(aws cloudformation describe-stacks \
            --stack-name "${GLOBAL_STACK}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' --output text 2>/dev/null || echo "")
        if [ -z "${CF_DIST_ID}" ] || [ "${CF_DIST_ID}" = "None" ]; then
            CF_DIST_ID=$(aws cloudformation describe-stacks \
                --stack-name "${STACK_NAME_PRIMARY}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
                --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' --output text 2>/dev/null || echo "")
        fi

        if [ -n "${CF_DIST_ID}" ] && [ "${CF_DIST_ID}" != "None" ]; then
            log_info "  Updating CloudFront ${CF_DIST_ID} -> v${NEW_VERSION}..."
            python3 -c "
import boto3
cf = boto3.client('cloudfront')
resp = cf.get_distribution_config(Id='${CF_DIST_ID}')
config = resp['DistributionConfig']
etag = resp['ETag']
for behavior in config.get('CacheBehaviors', {}).get('Items', []):
    if behavior.get('PathPattern') == '/api/*':
        for assoc in behavior.get('LambdaFunctionAssociations', {}).get('Items', []):
            assoc['LambdaFunctionARN'] = '${LAMBDA_EDGE_ARN}'
cf.update_distribution(Id='${CF_DIST_ID}', DistributionConfig=config, IfMatch=etag)
print('  CloudFront updated')
" 2>/dev/null || log_warning "  Could not update CloudFront (will be updated on next global deploy)"
        fi
    fi

    rm -rf "${EDGE_BUILD}" "${EDGE_ZIP}"

    if [ -n "${LAMBDA_EDGE_ARN}" ] && [ "${LAMBDA_EDGE_ARN}" != "None" ]; then
        log_success "Lambda@Edge deployed: ${LAMBDA_EDGE_ARN}"
    else
        log_warning "Lambda@Edge ARN not found — CloudFront /api/* routing won't work"
    fi
}

################################################################################
# MEMORY
################################################################################
deploy_memory() {
    if [ "$DEPLOY_DR" = true ]; then
        log_info "━━━ Memory — DR (${DR_REGION}) ━━━"
        bash "${MEMORY_DIR}/deploy.sh" "${DR_REGION}" "${SUFFIX}"
    fi
    if [ "$DEPLOY_PRIMARY" = true ]; then
        log_info "━━━ Memory — Primary (${PRIMARY_REGION}) ━━━"
        bash "${MEMORY_DIR}/deploy.sh" "${PRIMARY_REGION}" "${SUFFIX}"
    fi
    log_success "Memory deployed"
}

################################################################################
# INFRASTRUCTURE (CFN stacks) — self-contained, no dependency on deploy-stack.sh
################################################################################
deploy_infra() {
    log_info "━━━ Infrastructure — Primary (${PRIMARY_REGION}) ━━━"

    local TEMPLATES_DIR="${PROJECT_ROOT}/infrastructure/cloudformation/templates"
    local PACKAGES_DIR="${PROJECT_ROOT}/infrastructure/lambda-packages"

    # Check if stack already exists — skip heavy packaging/uploads if not in update mode
    local PRIMARY_STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")

    local SKIP_UPLOADS=false
    if [ "${UPDATE_MODE}" = false ] && [ "${PRIMARY_STACK_STATUS}" = "CREATE_COMPLETE" -o "${PRIMARY_STACK_STATUS}" = "UPDATE_COMPLETE" ]; then
        SKIP_UPLOADS=true
        log_info "Stack exists (${PRIMARY_STACK_STATUS}) — skipping packaging/uploads (use --update to force)"
    fi

    # Fix OpenAPI schema region default
    python3 -c "
import re
with open('${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml') as f:
    content = f.read()
fixed = re.sub(r'(region:\s*\n\s*default: )[a-z0-9-]+', lambda m: m.group(1) + '${PRIMARY_REGION}', content)
with open('${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml', 'w') as f:
    f.write(fixed)
"

    # [1] Validate templates
    if [ "${SKIP_UPLOADS}" = false ]; then
        log_info "Validating CloudFormation templates..."
        for template in "${TEMPLATES_DIR}"/*.yaml; do
            aws cloudformation validate-template \
                --template-body "file://${template}" \
                --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 || {
                log_error "Template validation failed: $(basename $template)"
                return 1
            }
        done
        log_success "All templates valid"

        # [2] Upload child templates
        log_info "Uploading templates to S3..."
        aws s3 sync "${TEMPLATES_DIR}/" "s3://${TEMPLATES_BUCKET}/templates/" \
            --exclude "parent.yaml" --exclude "README.md" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG}

        # [3] Package Lambdas
        log_info "Packaging Lambda functions..."
        chmod +x "${CFN_SCRIPTS_DIR}/package-lambdas.sh"
        bash "${CFN_SCRIPTS_DIR}/package-lambdas.sh" --clean 2>&1 | grep -E "✓|Error|error" | tail -10

        # [4] Upload Lambda packages
        log_info "Uploading Lambda packages to S3..."
        aws s3 sync "${PACKAGES_DIR}/" "s3://${LAMBDA_BUCKET_PRIMARY}/lambda-code/" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG}

        # [5] Upload OpenAPI schema (with apiId + region substitution)
        log_info "Uploading OpenAPI schema..."
        local OPENAPI_SCHEMA="${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml"
        local EXISTING_API_GW_ID=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' --output text 2>/dev/null || echo "")

    if [ -n "${EXISTING_API_GW_ID}" ] && [ "${EXISTING_API_GW_ID}" != "None" ]; then
        local SCHEMA_TMP=$(mktemp)
        python3 -c "
import re, sys
with open('${OPENAPI_SCHEMA}') as f:
    content = f.read()
fixed = re.sub(r'(apiId:\s*\n\s*default: )[a-z0-9]+', lambda m: m.group(1) + '${EXISTING_API_GW_ID}', content)
with open(sys.argv[1], 'w') as f:
    f.write(fixed)
" "${SCHEMA_TMP}"
        aws s3 cp "${SCHEMA_TMP}" "s3://${LAMBDA_BUCKET_PRIMARY}/openapi-schema.yaml" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG}
        rm -f "${SCHEMA_TMP}"
    else
        aws s3 cp "${OPENAPI_SCHEMA}" "s3://${LAMBDA_BUCKET_PRIMARY}/openapi-schema.yaml" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG}
    fi
    fi  # end SKIP_UPLOADS

    # [6] Deploy CFN stack
    log_info "Deploying CloudFormation stack: ${STACK_NAME}..."

    # Handle ROLLBACK_COMPLETE state
    local STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")
    if [ "${STACK_STATUS}" = "ROLLBACK_COMPLETE" ]; then
        log_warning "Stack in ROLLBACK_COMPLETE — deleting first..."
        aws cloudformation delete-stack --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG}
        aws cloudformation wait stack-delete-complete --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG}
    fi

    # Build parameter overrides from JSON file + deployment-derived values
    local PARAM_OVERRIDES=()
    while IFS= read -r line; do
        PARAM_OVERRIDES+=("$line")
    done < <(python3 -c "
import json, sys
with open('${PARAMETER_FILE}') as f:
    params = json.load(f)
for p in params:
    if 'ParameterKey' in p and 'ParameterValue' in p:
        print(f\"{p['ParameterKey']}={p['ParameterValue']}\")
")
    # Inject deployment-derived parameters (not in JSON file)
    PARAM_OVERRIDES+=("TemplatesBucket=${TEMPLATES_BUCKET}")
    PARAM_OVERRIDES+=("LambdaCodeBucket=${LAMBDA_BUCKET_PRIMARY}")
    PARAM_OVERRIDES+=("DeploymentSuffix=${SUFFIX}")
    PARAM_OVERRIDES+=("CreateDDBTable=true")
    PARAM_OVERRIDES+=("DRRegion=${DR_REGION}")

    aws cloudformation deploy \
        --template-file "${TEMPLATES_DIR}/parent-regional.yaml" \
        --stack-name "${STACK_NAME}" \
        --parameter-overrides "${PARAM_OVERRIDES[@]}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --tags "Environment=${ENVIRONMENT}" "ManagedBy=CloudFormation" \
        --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --no-fail-on-empty-changeset

    log_success "Stack deployed: ${STACK_NAME}"

    # Force Lambda functions to pick up new code from S3
    # (CFN doesn't redeploy if S3 key is unchanged)
    if [ "${UPDATE_MODE}" = true ]; then
        log_info "Updating Lambda function code..."
        # Function-name → S3-key pairs (bash 3.2 compatible — no associative arrays)
        local FUNC_NAMES=(
            "${ENVIRONMENT}-orders-authorizer-${SUFFIX}"
            "${ENVIRONMENT}-get-orders-${SUFFIX}"
            "${ENVIRONMENT}-create-order-${SUFFIX}"
            "${ENVIRONMENT}-update-order-${SUFFIX}"
            "${ENVIRONMENT}-agent-proxy-${SUFFIX}"
            "${ENVIRONMENT}-oauth-callback-${SUFFIX}"
        )
        local FUNC_ZIPS=(
            "authorizer.zip"
            "get_orders.zip"
            "create_order.zip"
            "update_order.zip"
            "agent_proxy.zip"
            "oauth2_callback_server.zip"
        )
        for i in "${!FUNC_NAMES[@]}"; do
            aws lambda update-function-code \
                --function-name "${FUNC_NAMES[$i]}" \
                --s3-bucket "${LAMBDA_BUCKET_PRIMARY}" \
                --s3-key "lambda-code/${FUNC_ZIPS[$i]}" \
                --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 || true
        done
        log_success "Lambda functions updated"

        # Flush API Gateway authorizer cache
        local API_GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' --output text 2>/dev/null || echo "")
        if [ -n "${API_GW_ID}" ] && [ "${API_GW_ID}" != "None" ]; then
            aws apigateway flush-stage-authorizers-cache \
                --rest-api-id "${API_GW_ID}" --stage-name dev \
                --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} 2>/dev/null || true
        fi
    else
        log_info "Lambda functions exist (use --update to force code refresh)"
    fi

    # Flush API Gateway authorizer cache
    local API_GW_ID=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' --output text 2>/dev/null || echo "")
    if [ -n "${API_GW_ID}" ] && [ "${API_GW_ID}" != "None" ]; then
        aws apigateway flush-stage-authorizers-cache \
            --rest-api-id "${API_GW_ID}" --stage-name dev \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} 2>/dev/null || true
    fi

    # [7] Post-deploy: update OpenAPI schema with actual API Gateway ID
    if [ "${UPDATE_MODE}" = true ]; then
        local OPENAPI_SCHEMA="${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml"
        local ACTUAL_API_GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' --output text 2>/dev/null)
    if [ -n "${ACTUAL_API_GW_ID}" ] && [ "${ACTUAL_API_GW_ID}" != "None" ]; then
        local SCHEMA_POST=$(mktemp)
        python3 -c "
import re, sys
with open('${OPENAPI_SCHEMA}') as f:
    content = f.read()
fixed = re.sub(r'(apiId:\s*\n\s*default: )[a-z0-9]+', lambda m: m.group(1) + '${ACTUAL_API_GW_ID}', content)
with open(sys.argv[1], 'w') as f:
    f.write(fixed)
" "${SCHEMA_POST}"
        aws s3 cp "${SCHEMA_POST}" "s3://${LAMBDA_BUCKET_PRIMARY}/openapi-schema.yaml" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1
        rm -f "${SCHEMA_POST}"
        log_success "OpenAPI schema updated: apiId=${ACTUAL_API_GW_ID}, region=${PRIMARY_REGION}"

        # Force Gateway Target to re-read the updated schema from S3
        local GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' --output text 2>/dev/null || echo "")
        if [ -n "${GW_ID}" ] && [ "${GW_ID}" != "None" ]; then
            local TARGET_ID=$(aws bedrock-agentcore-control list-gateway-targets \
                --gateway-identifier "${GW_ID}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
                --query 'items[0].targetId' --output text 2>/dev/null || echo "")
            if [ -n "${TARGET_ID}" ] && [ "${TARGET_ID}" != "None" ]; then
                log_info "Refreshing Gateway Target schema (target=${TARGET_ID})..."
                local TARGET_DETAIL=$(aws bedrock-agentcore-control get-gateway-target \
                    --gateway-identifier "${GW_ID}" --target-id "${TARGET_ID}" \
                    --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} --output json 2>/dev/null)
                local TARGET_NAME=$(echo "${TARGET_DETAIL}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))")
                local TARGET_DESC=$(echo "${TARGET_DETAIL}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description',''))")
                local TARGET_CONFIG=$(echo "${TARGET_DETAIL}" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('targetConfiguration',{})))")
                local CRED_CONFIG=$(echo "${TARGET_DETAIL}" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('credentialProviderConfigurations',[])))")

                aws bedrock-agentcore-control update-gateway-target \
                    --gateway-identifier "${GW_ID}" \
                    --target-id "${TARGET_ID}" \
                    --name "${TARGET_NAME}" \
                    --description "${TARGET_DESC}" \
                    --target-configuration "${TARGET_CONFIG}" \
                    --credential-provider-configurations "${CRED_CONFIG}" \
                    --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 \
                    && log_success "Gateway Target refreshed — schema re-read from S3" \
                    || log_warning "Could not refresh Gateway Target (may need manual update)"
            fi
        fi
    fi
    fi  # end UPDATE_MODE gate for schema/target refresh

    # [8] Post-deploy: create gateway secret if needed
    local GATEWAY_SECRET_NAME="${ENVIRONMENT}-gateway-secret-${SUFFIX}"
    if ! aws secretsmanager describe-secret --secret-id "${GATEWAY_SECRET_NAME}" \
        --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1; then
        log_info "Creating gateway secret: ${GATEWAY_SECRET_NAME}"
        local GATEWAY_URL=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' --output text 2>/dev/null)
        local SECRET_VALUE=$(python3 -c "
import json
with open('${PARAMETER_FILE}') as f:
    params = {p['ParameterKey']: p['ParameterValue'] for p in json.load(f) if 'ParameterKey' in p}
print(json.dumps({
    'tenant_id': params.get('TargetIdpTenantId',''),
    'client_id': params.get('GatewayIdpClientId',''),
    'client_secret': params.get('TargetIdpClientSecret',''),
    'gateway_mcp_url': '${GATEWAY_URL}',
    'orders_api_gateway_id': '${ACTUAL_API_GW_ID}'
}))
")
        aws secretsmanager create-secret \
            --name "${GATEWAY_SECRET_NAME}" \
            --secret-string "${SECRET_VALUE}" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 \
            && log_success "Gateway secret created" \
            || log_warning "Could not create gateway secret"
    else
        log_info "Gateway secret exists: ${GATEWAY_SECRET_NAME}"
    fi

    # [9] Post-deploy: warm up runtime
    local AGENT_RUNTIME_ARN=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentRuntimeArn`].OutputValue' --output text 2>/dev/null)
    if [ -n "${AGENT_RUNTIME_ARN}" ] && [ "${AGENT_RUNTIME_ARN}" != "None" ]; then
        log_info "Warming up runtime..."
        aws bedrock-agentcore invoke-agent-runtime \
            --agent-runtime-arn "${AGENT_RUNTIME_ARN}" --qualifier DEFAULT \
            --payload "$(echo -n '{"prompt":"ping"}' | base64)" \
            --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            /tmp/warmup-$$.json > /dev/null 2>&1 || true
        rm -f /tmp/warmup-$$.json
        log_success "Runtime warm-up sent"
    fi

    log_success "Infrastructure deployed"
}

################################################################################
# INFRASTRUCTURE — DR REGION (us-east-2)
################################################################################
deploy_infra_dr() {
    log_info "━━━ Infrastructure — DR (${DR_REGION}) ━━━"

    local DR_STACK_NAME="secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-dr"
    local TEMPLATES_DIR="${PROJECT_ROOT}/infrastructure/cloudformation/templates"
    local PACKAGES_DIR="${PROJECT_ROOT}/infrastructure/lambda-packages"

    # Check if DR stack already exists — skip heavy uploads if not in update mode
    local DR_STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "${DR_STACK_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")

    if [ "${UPDATE_MODE}" = false ] && [ "${DR_STACK_STATUS}" = "CREATE_COMPLETE" -o "${DR_STACK_STATUS}" = "UPDATE_COMPLETE" ]; then
        log_info "DR stack exists (${DR_STACK_STATUS}) — skipping uploads (use --update to force)"
    else
        # Upload templates to DR region
        log_info "Uploading templates to DR S3..."
        aws s3 sync "${TEMPLATES_DIR}/" "s3://${CFN_TEMPLATES_BUCKET_DR}/templates/" \
            --exclude "parent.yaml" --exclude "README.md" \
            --region "${DR_REGION}" ${AWS_PROFILE_FLAG}

        # Upload Lambda packages to DR region
        log_info "Uploading Lambda packages to DR S3..."
        aws s3 sync "${PACKAGES_DIR}/" "s3://${LAMBDA_BUCKET_DR}/lambda-code/" \
            --region "${DR_REGION}" ${AWS_PROFILE_FLAG}

        # Upload OpenAPI schema to DR (with DR region)
        log_info "Uploading OpenAPI schema to DR..."
        local SCHEMA_TMP=$(mktemp)
        python3 -c "
import re, sys
with open('${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml') as f:
    content = f.read()
fixed = re.sub(r'(region:\s*\n\s*default: )[a-z0-9-]+', lambda m: m.group(1) + '${DR_REGION}', content)
with open(sys.argv[1], 'w') as f:
    f.write(fixed)
" "${SCHEMA_TMP}"
        aws s3 cp "${SCHEMA_TMP}" "s3://${LAMBDA_BUCKET_DR}/openapi-schema.yaml" \
            --region "${DR_REGION}" ${AWS_PROFILE_FLAG}
        rm -f "${SCHEMA_TMP}"
    fi

    # Build parameter overrides for DR
    local PARAM_OVERRIDES=()
    while IFS= read -r line; do
        PARAM_OVERRIDES+=("$line")
    done < <(python3 -c "
import json, sys
with open('${PARAMETER_FILE}') as f:
    params = json.load(f)
for p in params:
    if 'ParameterKey' in p and 'ParameterValue' in p:
        print(f\"{p['ParameterKey']}={p['ParameterValue']}\")
")
    # DR-specific overrides
    PARAM_OVERRIDES+=("TemplatesBucket=${CFN_TEMPLATES_BUCKET_DR}")
    PARAM_OVERRIDES+=("LambdaCodeBucket=${LAMBDA_BUCKET_DR}")
    PARAM_OVERRIDES+=("DeploymentSuffix=${SUFFIX}")
    PARAM_OVERRIDES+=("CreateDDBTable=false")
    PARAM_OVERRIDES+=("DRRegion=")

    # Deploy DR stack
    log_info "Deploying DR CloudFormation stack: ${DR_STACK_NAME}..."
    aws cloudformation deploy \
        --template-file "${TEMPLATES_DIR}/parent-regional.yaml" \
        --stack-name "${DR_STACK_NAME}" \
        --parameter-overrides "${PARAM_OVERRIDES[@]}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --tags "Environment=${ENVIRONMENT}" "ManagedBy=CloudFormation" "Region=DR" \
        --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
        --no-fail-on-empty-changeset

    log_success "DR stack deployed: ${DR_STACK_NAME}"

    # Post-deploy: update OpenAPI schema with actual DR API Gateway ID and refresh target
    if [ "${UPDATE_MODE}" = true ]; then
    local DR_API_GW_ID=$(aws cloudformation describe-stacks \
        --stack-name "${DR_STACK_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' --output text 2>/dev/null || echo "")
    if [ -n "${DR_API_GW_ID}" ] && [ "${DR_API_GW_ID}" != "None" ]; then
        local DR_SCHEMA_POST=$(mktemp)
        python3 -c "
import re, sys
with open('${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml') as f:
    content = f.read()
fixed = re.sub(r'(apiId:\s*\n\s*default: )[a-z0-9]+', lambda m: m.group(1) + '${DR_API_GW_ID}', content)
fixed = re.sub(r'(region:\s*\n\s*default: )[a-z0-9-]+', lambda m: m.group(1) + '${DR_REGION}', fixed)
with open(sys.argv[1], 'w') as f:
    f.write(fixed)
" "${DR_SCHEMA_POST}"
        aws s3 cp "${DR_SCHEMA_POST}" "s3://${LAMBDA_BUCKET_DR}/openapi-schema.yaml" \
            --region "${DR_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1
        rm -f "${DR_SCHEMA_POST}"
        log_success "DR OpenAPI schema updated: apiId=${DR_API_GW_ID}, region=${DR_REGION}"

        # Force DR Gateway Target to re-read the updated schema
        local DR_GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${DR_STACK_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' --output text 2>/dev/null || echo "")
        if [ -n "${DR_GW_ID}" ] && [ "${DR_GW_ID}" != "None" ]; then
            local DR_TARGET_ID=$(aws bedrock-agentcore-control list-gateway-targets \
                --gateway-identifier "${DR_GW_ID}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
                --query 'items[0].targetId' --output text 2>/dev/null || echo "")
            if [ -n "${DR_TARGET_ID}" ] && [ "${DR_TARGET_ID}" != "None" ]; then
                log_info "Refreshing DR Gateway Target schema (target=${DR_TARGET_ID})..."
                local DR_TARGET_DETAIL=$(aws bedrock-agentcore-control get-gateway-target \
                    --gateway-identifier "${DR_GW_ID}" --target-id "${DR_TARGET_ID}" \
                    --region "${DR_REGION}" ${AWS_PROFILE_FLAG} --output json 2>/dev/null)
                local DR_TARGET_NAME=$(echo "${DR_TARGET_DETAIL}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))")
                local DR_TARGET_DESC=$(echo "${DR_TARGET_DETAIL}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description',''))")
                local DR_TARGET_CONFIG=$(echo "${DR_TARGET_DETAIL}" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('targetConfiguration',{})))")
                local DR_CRED_CONFIG=$(echo "${DR_TARGET_DETAIL}" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('credentialProviderConfigurations',[])))")

                aws bedrock-agentcore-control update-gateway-target \
                    --gateway-identifier "${DR_GW_ID}" \
                    --target-id "${DR_TARGET_ID}" \
                    --name "${DR_TARGET_NAME}" \
                    --description "${DR_TARGET_DESC}" \
                    --target-configuration "${DR_TARGET_CONFIG}" \
                    --credential-provider-configurations "${DR_CRED_CONFIG}" \
                    --region "${DR_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 \
                    && log_success "DR Gateway Target refreshed — schema re-read from S3" \
                    || log_warning "Could not refresh DR Gateway Target"
            fi
        fi
    fi
    fi  # end UPDATE_MODE gate for DR schema/target refresh

    # Create gateway secret in DR region if needed
    if ! aws secretsmanager describe-secret --secret-id "${GATEWAY_SECRET_NAME}" \
        --region "${DR_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1; then
        log_info "Creating DR gateway secret: ${GATEWAY_SECRET_NAME}"
        local DR_GATEWAY_URL=$(aws cloudformation describe-stacks \
            --stack-name "${DR_STACK_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' --output text 2>/dev/null)
        local DR_API_GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${DR_STACK_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' --output text 2>/dev/null)
        local SECRET_VALUE=$(python3 -c "
import json
with open('${PARAMETER_FILE}') as f:
    params = {p['ParameterKey']: p['ParameterValue'] for p in json.load(f) if 'ParameterKey' in p}
print(json.dumps({
    'tenant_id': params.get('TargetIdpTenantId',''),
    'client_id': params.get('GatewayIdpClientId',''),
    'client_secret': params.get('TargetIdpClientSecret',''),
    'gateway_mcp_url': '${DR_GATEWAY_URL}',
    'orders_api_gateway_id': '${DR_API_GW_ID}'
}))
")
        aws secretsmanager create-secret \
            --name "${GATEWAY_SECRET_NAME}" \
            --secret-string "${SECRET_VALUE}" \
            --region "${DR_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 \
            && log_success "DR gateway secret created" \
            || log_warning "Could not create DR gateway secret"
    else
        log_info "DR gateway secret exists: ${GATEWAY_SECRET_NAME}"
    fi

    # Update Lambda function code in DR (only with --update)
    if [ "${UPDATE_MODE}" = true ]; then
        log_info "Updating DR Lambda function code..."
        local DR_FUNC_NAMES=(
            "${ENVIRONMENT}-orders-authorizer-${SUFFIX}"
            "${ENVIRONMENT}-get-orders-${SUFFIX}"
            "${ENVIRONMENT}-create-order-${SUFFIX}"
            "${ENVIRONMENT}-update-order-${SUFFIX}"
            "${ENVIRONMENT}-agent-proxy-${SUFFIX}"
            "${ENVIRONMENT}-oauth-callback-${SUFFIX}"
        )
        local DR_FUNC_ZIPS=(
            "authorizer.zip"
            "get_orders.zip"
            "create_order.zip"
            "update_order.zip"
            "agent_proxy.zip"
            "oauth2_callback_server.zip"
        )
        for i in "${!DR_FUNC_NAMES[@]}"; do
            aws lambda update-function-code \
                --function-name "${DR_FUNC_NAMES[$i]}" \
                --s3-bucket "${LAMBDA_BUCKET_DR}" \
                --s3-key "lambda-code/${DR_FUNC_ZIPS[$i]}" \
                --region "${DR_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1 || true
        done
        log_success "DR Lambda functions updated"
    else
        log_info "DR Lambda functions exist (use --update to force code refresh)"
    fi

    # Update DR runtime (only with --update)
    if [ "${UPDATE_MODE}" = true ]; then
        log_info "Updating DR agent runtime..."
    local DR_RUNTIME_ID_NAME="${ENVIRONMENT}_order_agent_runtime_${SUFFIX}"
    local DR_FULL_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
        --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
        --query "agentRuntimes[?starts_with(agentRuntimeName, '${DR_RUNTIME_ID_NAME}')].agentRuntimeId" \
        --output text 2>/dev/null || echo "")

    if [ -n "${DR_FULL_RUNTIME_ID}" ] && [ "${DR_FULL_RUNTIME_ID}" != "None" ]; then
        local DR_ROLE_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
            --agent-runtime-id "${DR_FULL_RUNTIME_ID}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
            --query "roleArn" --output text 2>/dev/null)

        local DR_MEMORY_ID=$(aws cloudformation describe-stacks \
            --stack-name "$(get_memory_stack_name)" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`MemoryId`].OutputValue' --output text 2>/dev/null || echo "")
        DR_MEMORY_ID="${DR_MEMORY_ID##*/}"

        local DR_OAUTH_URL=$(aws cloudformation describe-stacks \
            --stack-name "${DR_STACK_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' --output text 2>/dev/null || echo "")

        python3 -c "
import boto3, sys
ac = boto3.client('bedrock-agentcore-control', region_name='${DR_REGION}')
env_vars = {
    'AWS_REGION': '${DR_REGION}',
    'BEDROCK_MODEL_ID': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    'GATEWAY_SECRET_NAME': '${GATEWAY_SECRET_NAME}',
    'GATEWAY_TOOLS_ENABLED': 'true',
    'LOG_LEVEL': 'DEBUG',
    'OAUTH_CALLBACK_SERVER_URL': '${DR_OAUTH_URL}',
    'OAUTH_FORCE_AUTH': 'false',
    'MEMORY_ID': '${DR_MEMORY_ID}',
    'MEMORY_REGION': '${DR_REGION}',
    'MEMORY_RECALL_MAX_EVENTS': '10',
    'OTEL_SERVICE_NAME': 'order-agent',
    'OTEL_TRACES_EXPORTER': 'otlp',
    'OTEL_METRICS_EXPORTER': 'otlp',
    'OTEL_LOGS_EXPORTER': 'otlp',
    'OTEL_PROPAGATORS': 'tracecontext,baggage,xray',
    'OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED': 'true',
}
try:
    resp = ac.update_agent_runtime(
        agentRuntimeId='${DR_FULL_RUNTIME_ID}',
        roleArn='${DR_ROLE_ARN}',
        agentRuntimeArtifact={
            'codeConfiguration': {
                'code': {'s3': {'bucket': '${LAMBDA_BUCKET_DR}', 'prefix': '${RUNTIME_S3_KEY}'}},
                'runtime': 'PYTHON_3_12',
                'entryPoint': ['opentelemetry-instrument', 'order_agent.py'],
            }
        },
        networkConfiguration={'networkMode': 'PUBLIC'},
        environmentVariables=env_vars,
    )
    print(f'  ✔ DR Runtime updated to version {resp.get(\"agentRuntimeVersion\", \"?\")}')
except Exception as e:
    print(f'  ✗ DR Runtime update failed: {e}')
"
    else
        log_warning "DR Runtime not found — skipping runtime update"
    fi
    else
        log_info "DR Runtime exists (use --update to force code refresh)"
    fi

    log_success "DR region deployment complete"
}

################################################################################
# GLOBAL STACK (CloudFront + S3 — deploy after both regional stacks)
################################################################################
deploy_global() {
    log_info "━━━ Global Stack (CloudFront + S3 + Lambda@Edge) ━━━"

    local GLOBAL_STACK_NAME="secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global"
    local TEMPLATES_DIR="${PROJECT_ROOT}/infrastructure/cloudformation/templates"

    # Skip if stack exists and not in update mode
    if [ "${UPDATE_MODE}" = false ]; then
        local GLOBAL_STATUS=$(aws cloudformation describe-stacks \
            --stack-name "${GLOBAL_STACK_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
            --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")
        if [ "${GLOBAL_STATUS}" = "CREATE_COMPLETE" ] || [ "${GLOBAL_STATUS}" = "UPDATE_COMPLETE" ]; then
            log_success "Global stack already deployed (use --update to redeploy): ${GLOBAL_STACK_NAME}"
            return 0
        fi
    fi

    # Upload templates (global stack needs frontend-stack.yaml in S3)
    aws s3 sync "${TEMPLATES_DIR}/" "s3://${TEMPLATES_BUCKET}/templates/" \
        --exclude "parent.yaml" --exclude "parent-regional.yaml" --exclude "README.md" \
        --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1

    aws cloudformation deploy \
        --template-file "${TEMPLATES_DIR}/parent-global.yaml" \
        --stack-name "${GLOBAL_STACK_NAME}" \
        --parameter-overrides \
            Environment="${ENVIRONMENT}" \
            TemplatesBucket="${TEMPLATES_BUCKET}" \
            DeploymentSuffix="${SUFFIX}" \
            CloudFrontPriceClass="PriceClass_100" \
            SslCertificateArn="" \
            LambdaEdgeArn="${LAMBDA_EDGE_ARN:-}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --tags "Environment=${ENVIRONMENT}" "ManagedBy=CloudFormation" "Scope=Global" \
        --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --no-fail-on-empty-changeset

    log_success "Global stack deployed: ${GLOBAL_STACK_NAME}"
}

################################################################################
# POST-DEPLOY: Seed DDB + Show Azure Entra ID instructions
################################################################################
post_deploy() {
    local TABLE_NAME="${ENVIRONMENT}-orders-table-${SUFFIX}"

    log_info "━━━ Post-Deploy: Seed Data ━━━"
    local ITEM_COUNT=$(aws dynamodb scan --table-name "${TABLE_NAME}" --region "${PRIMARY_REGION}" \
        ${AWS_PROFILE_FLAG} --select COUNT --query "Count" --output text 2>/dev/null || echo "0")

    if [ "${ITEM_COUNT}" = "0" ]; then
        log_info "  DDB table empty — seeding sample orders..."
        local ITEMS=(
            '{"order_id":{"S":"ORD-001"},"item_name":{"S":"Macbook Pro"},"qty":{"N":"5"},"order_date":{"S":"2026-04-15"},"status":{"S":"pending"},"user_email":{"S":"ParthSalesUser@sevrenawsgmail.onmicrosoft.com"}}'
            '{"order_id":{"S":"ORD-002"},"item_name":{"S":"iPhone 17"},"qty":{"N":"2"},"order_date":{"S":"2026-05-01"},"status":{"S":"completed"},"user_email":{"S":"ParthSalesUser@sevrenawsgmail.onmicrosoft.com"}}'
            '{"order_id":{"S":"ORD-003"},"item_name":{"S":"USB-C Cable"},"qty":{"N":"10"},"order_date":{"S":"2026-05-05"},"status":{"S":"pending"},"user_email":{"S":"ParthSalesUser@sevrenawsgmail.onmicrosoft.com"}}'
            '{"order_id":{"S":"ORD-004"},"item_name":{"S":"Keyboard"},"qty":{"N":"3"},"order_date":{"S":"2026-04-20"},"status":{"S":"processing"},"user_email":{"S":"ParthSalesUser@sevrenawsgmail.onmicrosoft.com"}}'
            '{"order_id":{"S":"ORD-005"},"item_name":{"S":"Monitor 27 inch"},"qty":{"N":"1"},"order_date":{"S":"2026-03-10"},"status":{"S":"completed"},"user_email":{"S":"ParthSalesUser@sevrenawsgmail.onmicrosoft.com"}}'
            '{"order_id":{"S":"ORD-006"},"item_name":{"S":"Wireless Mouse"},"qty":{"N":"8"},"order_date":{"S":"2026-05-10"},"status":{"S":"pending"},"user_email":{"S":"ParthSalesUser@sevrenawsgmail.onmicrosoft.com"}}'
        )
        for item in "${ITEMS[@]}"; do
            aws dynamodb put-item --table-name "${TABLE_NAME}" --item "${item}" \
                --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1
        done
        log_success "  Seeded ${#ITEMS[@]} orders (will replicate to DR via Global Table)"
    else
        log_info "  DDB table has ${ITEM_COUNT} items — skipping seed"
    fi

    echo ""
    log_info "━━━ Post-Deploy: Deployment Summary ━━━"
    echo ""

    local CF_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' --output text 2>/dev/null || echo "N/A")

    # AgentCore Identity callback URLs (from credential provider API)
    local PROVIDER_NAME="${ENVIRONMENT}-ms-oauth2-provider-${SUFFIX}"
    local CALLBACK_URL_PRIMARY=$(aws bedrock-agentcore-control get-oauth2-credential-provider \
        --name "${PROVIDER_NAME}" --region "${PRIMARY_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'callbackUrl' --output text 2>/dev/null || echo "N/A")
    local CALLBACK_URL_DR=$(aws bedrock-agentcore-control get-oauth2-credential-provider \
        --name "${PROVIDER_NAME}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
        --query 'callbackUrl' --output text 2>/dev/null || echo "N/A")

    echo "  ┌─────────────────────────────────────────────────────────────┐"
    echo "  │  DEPLOYMENT SUMMARY                                         │"
    echo "  ├─────────────────────────────────────────────────────────────┤"
    echo "  │                                                             │"
    echo "  │  Frontend URL:                                              │"
    echo "  │    https://${CF_DOMAIN}"
    echo "  │                                                             │"
    echo "  │  AgentCore Identity Callback URLs:                          │"
    echo "  │    Primary (${PRIMARY_REGION}):                             │"
    echo "  │      ${CALLBACK_URL_PRIMARY}"
    echo "  │    DR (${DR_REGION}):                                       │"
    echo "  │      ${CALLBACK_URL_DR}"
    echo "  │                                                             │"
    echo "  ├─────────────────────────────────────────────────────────────┤"
    echo "  │  UPDATE AZURE ENTRA ID (one-time after first deploy)        │"
    echo "  ├─────────────────────────────────────────────────────────────┤"
    echo "  │                                                             │"
    echo "  │  1. Gateway App Registration → Authentication:              │"
    echo "  │     Add Redirect URI:                                       │"
    echo "  │       https://${CF_DOMAIN}"
    echo "  │                                                             │"
    echo "  │  2. Orders API App Registration → Authentication:           │"
    echo "  │     Add BOTH Redirect URIs (for multi-region failover):     │"
    echo "  │       ${CALLBACK_URL_PRIMARY}"
    echo "  │       ${CALLBACK_URL_DR}"
    echo "  │                                                             │"
    echo "  └─────────────────────────────────────────────────────────────┘"
    echo ""
}

################################################################################
# MAIN DISPATCH
################################################################################

case "${MODE}" in
    frontend)
        deploy_frontend
        ;;
    runtime)
        # Always update both regions (runtime code should be consistent)
        deploy_runtime
        # Also upload to DR and update DR runtime
        if [ "$DEPLOY_DR" = true ]; then
            log_info "━━━ DR Runtime Update ━━━"
            aws s3 cp "${PROJECT_ROOT}/infrastructure/lambda-packages/order-agent.zip" \
                "s3://${LAMBDA_BUCKET_DR}/${RUNTIME_S3_KEY}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} > /dev/null 2>&1
            # Trigger DR runtime update (reuse logic from deploy_infra_dr)
            DR_RUNTIME_ID_NAME="${ENVIRONMENT}_order_agent_runtime_${SUFFIX}"
            DR_FULL_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
                --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
                --query "agentRuntimes[?starts_with(agentRuntimeName, '${DR_RUNTIME_ID_NAME}')].agentRuntimeId" \
                --output text 2>/dev/null || echo "")
            if [ -n "${DR_FULL_RUNTIME_ID}" ] && [ "${DR_FULL_RUNTIME_ID}" != "None" ]; then
                DR_ROLE_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
                    --agent-runtime-id "${DR_FULL_RUNTIME_ID}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
                    --query "roleArn" --output text 2>/dev/null)
                DR_MEMORY_ID="${MEMORY_ID_DR}"
                DR_OAUTH_URL=$(aws cloudformation describe-stacks \
                    --stack-name "${STACK_NAME_DR}" --region "${DR_REGION}" ${AWS_PROFILE_FLAG} \
                    --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' --output text 2>/dev/null || echo "")
                python3 -c "
import boto3, sys
ac = boto3.client('bedrock-agentcore-control', region_name='${DR_REGION}')
env_vars = {
    'AWS_REGION': '${DR_REGION}',
    'BEDROCK_MODEL_ID': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    'GATEWAY_SECRET_NAME': '${GATEWAY_SECRET_NAME}',
    'GATEWAY_TOOLS_ENABLED': 'true',
    'LOG_LEVEL': 'DEBUG',
    'OAUTH_CALLBACK_SERVER_URL': '${DR_OAUTH_URL}',
    'OAUTH_FORCE_AUTH': 'false',
    'MEMORY_ID': '${DR_MEMORY_ID}',
    'MEMORY_REGION': '${DR_REGION}',
    'MEMORY_RECALL_MAX_EVENTS': '10',
    'OTEL_SERVICE_NAME': 'order-agent',
    'OTEL_TRACES_EXPORTER': 'otlp',
    'OTEL_METRICS_EXPORTER': 'otlp',
    'OTEL_LOGS_EXPORTER': 'otlp',
    'OTEL_PROPAGATORS': 'tracecontext,baggage,xray',
    'OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED': 'true',
}
try:
    resp = ac.update_agent_runtime(
        agentRuntimeId='${DR_FULL_RUNTIME_ID}',
        roleArn='${DR_ROLE_ARN}',
        agentRuntimeArtifact={
            'codeConfiguration': {
                'code': {'s3': {'bucket': '${LAMBDA_BUCKET_DR}', 'prefix': '${RUNTIME_S3_KEY}'}},
                'runtime': 'PYTHON_3_12',
                'entryPoint': ['opentelemetry-instrument', 'order_agent.py'],
            }
        },
        networkConfiguration={'networkMode': 'PUBLIC'},
        environmentVariables=env_vars,
    )
    print(f'  ✔ DR Runtime updated to version {resp.get(\"agentRuntimeVersion\", \"?\")}')
except Exception as e:
    print(f'  ✗ DR Runtime update failed: {e}')
"
                log_success "DR runtime updated"
            else
                log_warning "DR Runtime not found — skipping"
            fi
        fi
        ;;
    memory)
        deploy_memory
        ;;
    infra)
        if [ "$DEPLOY_PRIMARY" = true ]; then
            deploy_infra
        fi
        if [ "$DEPLOY_DR" = true ]; then
            deploy_infra_dr
        fi
        ;;
    full)
        if [ "$DEPLOY_MEMORY" = true ]; then
            deploy_memory
        fi
        if [ "$DEPLOY_PRIMARY" = true ]; then
            deploy_infra
        fi
        if [ "$DEPLOY_DR" = true ]; then
            deploy_infra_dr
        fi
        deploy_lambda_edge
        deploy_global
        deploy_runtime
        deploy_frontend
        ;;
esac

# Run post_deploy after dispatch
if [ "${MODE}" = "full" ] || [ "${MODE}" = "infra" ]; then
    post_deploy
fi

echo ""
log_success "Done!"
