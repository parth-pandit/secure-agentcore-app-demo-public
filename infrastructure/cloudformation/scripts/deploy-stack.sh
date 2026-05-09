#!/bin/bash

################################################################################
# CloudFormation Stack Deployment Script
#
# This script deploys the parent CloudFormation template with all nested child
# stacks. It handles template validation, S3 uploads, Lambda packaging, and
# stack deployment with proper error handling.
#
# Usage:
#   ./deploy-stack.sh <stack-name> <templates-bucket> <lambda-bucket> [options]
#
# Arguments:
#   stack-name         Name of the CloudFormation stack to create/update
#   templates-bucket   S3 bucket name for storing CloudFormation templates
#   lambda-bucket      S3 bucket name for storing Lambda deployment packages
#
# Options:
#   --dry-run         Create changeset without executing (for review)
#   --environment     Environment name (dev|staging|prod, default: dev)
#   --profile         AWS CLI profile to use (default: uses AWS_PROFILE env var or "default")
#   --region          AWS region to deploy into (e.g. us-west-2, default: profile/env default)
#   --help            Display this help message
#   --suffix          Timestamp in yyyymmddHHMM format to maintain uniqueness
#
# Examples:
#   # Deploy to dev environment using default profile
#   ./deploy-stack.sh my-app-stack cfn-templates-dev lambda-code-dev
#
#   # Deploy using a specific AWS CLI profile and region
#   ./deploy-stack.sh my-app-stack cfn-templates-dev lambda-code-dev --profile my-profile --region us-west-2
#
#   # Deploy to production with dry-run
#   ./deploy-stack.sh my-app-stack cfn-templates-prod lambda-code-prod \
#     --dry-run --environment prod --profile prod-profile --region us-west-2
#
# Required IAM Permissions:
#   - cloudformation:CreateStack, UpdateStack, DescribeStacks
#   - s3:PutObject, s3:GetObject (on template and Lambda buckets)
#   - iam:CreateRole, PassRole (for stack resources)
#
# Exit Codes:
#   0 - Success
#   1 - Invalid arguments or usage error
#   2 - Template validation failed
#   3 - S3 upload failed
#   4 - Lambda packaging failed
#   5 - Stack deployment failed
################################################################################

set -e  # Exit on any error
set -o pipefail  # Catch errors in pipes

# Color codes for output formatting
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Script directory and project root
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly CFN_DIR="${PROJECT_ROOT}/infrastructure/cloudformation"
readonly TEMPLATES_DIR="${CFN_DIR}/templates"
readonly PARAMETERS_DIR="${CFN_DIR}/parameters"
readonly SCRIPTS_DIR="${CFN_DIR}/scripts"

################################################################################
# Logging Functions
################################################################################

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
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

################################################################################
# Usage and Help
################################################################################

usage() {
    cat << EOF
Usage: $0 <stack-name> <templates-bucket> <lambda-bucket> [options]

Arguments:
  stack-name         Name of the CloudFormation stack to create/update
  templates-bucket   S3 bucket name for storing CloudFormation templates
  lambda-bucket      S3 bucket name for storing Lambda deployment packages

Options:
  --dry-run         Create changeset without executing (for review)
  --environment     Environment name (dev|staging|prod, default: dev)
  --profile         AWS CLI profile to use (default: AWS_PROFILE env var or "default")
  --region          AWS region to deploy into (e.g. us-west-2, default: profile/env default)
  --help            Display this help message
  --suffix          Timestamp in yyyymmddHHMM format to maintain uniqueness

Examples:
  # Deploy to dev environment using default profile
  $0 my-app-stack cfn-templates-dev lambda-code-dev

  # Deploy using a specific AWS CLI profile and region
  $0 my-app-stack cfn-templates-dev lambda-code-dev --profile my-profile --region us-west-2

  # Deploy to production with dry-run
  $0 my-app-stack cfn-templates-prod lambda-code-prod --dry-run --environment prod --profile prod-profile --region us-west-2

EOF
    exit 1
}

################################################################################
# Argument Parsing
################################################################################

# Check minimum arguments
if [ $# -lt 3 ]; then
    log_error "Insufficient arguments provided"
    usage
fi

# Parse positional arguments
STACK_NAME="$1"
TEMPLATES_BUCKET="$2"
LAMBDA_BUCKET="$3"
shift 3

# Parse optional arguments
DRY_RUN=false
ENVIRONMENT="dev"
DEPLOY_SUFFIX=""
NO_ROLLBACK=false
AWS_PROFILE_ARG="${AWS_PROFILE:-}"  # Inherit from environment if set
AWS_REGION_ARG="${AWS_DEFAULT_REGION:-}"  # Inherit from environment if set

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-rollback)
            NO_ROLLBACK=true
            shift
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --profile)
            AWS_PROFILE_ARG="$2"
            shift 2
            ;;
        --region)
            AWS_REGION_ARG="$2"
            shift 2
            ;;
        --suffix)
            DEPLOY_SUFFIX="$2"
            shift 2
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Generate deployment suffix if not provided (yyyymmddHHMM format)
if [ -z "${DEPLOY_SUFFIX}" ]; then
    DEPLOY_SUFFIX=$(date -u +"%Y%m%d%H%M")
fi
log_info "  Deployment Suffix: ${DEPLOY_SUFFIX}"

# Build the AWS CLI profile flag — used in every aws command below
# If no profile specified and AWS_PROFILE env var is not set, AWS CLI uses "default"
if [ -n "${AWS_PROFILE_ARG}" ]; then
    AWS_PROFILE_FLAG="--profile ${AWS_PROFILE_ARG}"
    PROFILE_DISPLAY="${AWS_PROFILE_ARG}"
else
    AWS_PROFILE_FLAG=""
    PROFILE_DISPLAY="default"
fi

# Build the AWS CLI region flag
if [ -n "${AWS_REGION_ARG:-}" ]; then
    AWS_REGION_FLAG="--region ${AWS_REGION_ARG}"
    REGION_DISPLAY="${AWS_REGION_ARG}"
else
    AWS_REGION_FLAG=""
    REGION_DISPLAY="(profile default)"
fi

# Build the AWS CLI region flag — used in every aws command below
# If no region specified, AWS CLI uses the profile's configured region
if [ -n "${AWS_REGION_ARG}" ]; then
    AWS_REGION_FLAG="--region ${AWS_REGION_ARG}"
    REGION_DISPLAY="${AWS_REGION_ARG}"
else
    AWS_REGION_FLAG=""
    REGION_DISPLAY="(profile default)"
fi

# Validate environment value
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    log_error "Invalid environment: $ENVIRONMENT (must be dev, staging, or prod)"
    exit 1
fi

# Display deployment configuration
log_info "Deployment Configuration:"
log_info "  Stack Name:        ${STACK_NAME}"
log_info "  Environment:       ${ENVIRONMENT}"
log_info "  Templates Bucket:  ${TEMPLATES_BUCKET}"
log_info "  Lambda Bucket:     ${LAMBDA_BUCKET}"
log_info "  AWS Profile:       ${PROFILE_DISPLAY}"
log_info "  AWS Region:        ${REGION_DISPLAY}"
log_info "  Dry Run:           ${DRY_RUN}"
echo ""

################################################################################
# Pre-flight Checks
################################################################################

log_info "Running pre-flight checks..."

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if templates directory exists
if [ ! -d "${TEMPLATES_DIR}" ]; then
    log_error "Templates directory not found: ${TEMPLATES_DIR}"
    exit 1
fi

# Check if parent template exists
if [ ! -f "${TEMPLATES_DIR}/parent.yaml" ]; then
    log_error "Parent template not found: ${TEMPLATES_DIR}/parent.yaml"
    exit 1
fi

# Check if parameter file exists for the environment
PARAMETER_FILE="${PARAMETERS_DIR}/${ENVIRONMENT}-parameters.json"
if [ ! -f "${PARAMETER_FILE}" ]; then
    log_error "Parameter file not found: ${PARAMETER_FILE}"
    exit 1
fi

# Check if package-lambdas.sh script exists
if [ ! -f "${SCRIPTS_DIR}/package-lambdas.sh" ]; then
    log_error "Lambda packaging script not found: ${SCRIPTS_DIR}/package-lambdas.sh"
    exit 1
fi

log_success "Pre-flight checks passed"
echo ""

################################################################################
# Template Validation
################################################################################

log_info "Validating CloudFormation templates..."

VALIDATION_ERRORS=0

# Validate each template file
for template in "${TEMPLATES_DIR}"/*.yaml; do
    template_name=$(basename "$template")
    log_info "  Validating ${template_name}..."
    
    # Use AWS CLI to validate template syntax and structure
    # The --no-cli-pager flag prevents interactive paging
    if aws cloudformation validate-template \
        --template-body "file://${template}" \
        --no-cli-pager \
        --output json \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} > /dev/null 2>&1; then
        log_success "    ✓ ${template_name} is valid"
    else
        log_error "    ✗ ${template_name} validation failed"
        ((VALIDATION_ERRORS++))
    fi
done

if [ $VALIDATION_ERRORS -gt 0 ]; then
    log_error "Template validation failed with ${VALIDATION_ERRORS} error(s)"
    exit 2
fi

log_success "All templates validated successfully"
echo ""

################################################################################
# Upload Child Templates to S3
################################################################################

log_info "Uploading child templates to S3..."

# Create templates/ prefix in S3 bucket for organization
# Exclude parent.yaml as it will be used locally for deployment
# The --no-cli-pager flag prevents interactive paging
if aws s3 sync "${TEMPLATES_DIR}/" "s3://${TEMPLATES_BUCKET}/templates/" \
    --exclude "parent.yaml" \
    --exclude "README.md" \
    --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
    log_success "Child templates uploaded to s3://${TEMPLATES_BUCKET}/templates/"
else
    log_error "Failed to upload templates to S3"
    exit 3
fi

echo ""

################################################################################
# Package and Upload Lambda Functions
################################################################################

log_info "Packaging Lambda functions..."

# Make the packaging script executable
chmod +x "${SCRIPTS_DIR}/package-lambdas.sh"

# Execute Lambda packaging script
# This creates deployment packages in lambda-packages/ directory
if "${SCRIPTS_DIR}/package-lambdas.sh"; then
    log_success "Lambda functions packaged successfully"
else
    log_error "Lambda packaging failed"
    exit 4
fi

echo ""

log_info "Uploading Lambda packages to S3..."

# Upload Lambda deployment packages to S3
# The lambda-code/ prefix organizes Lambda artifacts
if aws s3 sync "${PROJECT_ROOT}/infrastructure/lambda-packages/" "s3://${LAMBDA_BUCKET}/lambda-code/" \
    --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
    log_success "Lambda packages uploaded to s3://${LAMBDA_BUCKET}/lambda-code/"
else
    log_error "Failed to upload Lambda packages to S3"
    exit 3
fi

echo ""

log_info "Uploading OpenAPI schema to S3..."

# Upload the OpenAPI schema required by AgentCore GatewayTarget.
# The API Gateway ID in the schema is substituted with the actual value
# from the BackendAPIStack output so the Gateway Target points to the
# correct account's Orders API.
OPENAPI_SCHEMA="${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml"
if [ ! -f "${OPENAPI_SCHEMA}" ]; then
    log_error "OpenAPI schema not found: ${OPENAPI_SCHEMA}"
    exit 3
fi

# Get the API Gateway ID from the existing stack if it's already deployed,
# otherwise use a placeholder — it will be corrected after the stack deploys.
EXISTING_API_GW_ID=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' \
    --output text --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null || echo "")

if [ -n "${EXISTING_API_GW_ID}" ] && [ "${EXISTING_API_GW_ID}" != "None" ]; then
    log_info "Substituting API Gateway ID in OpenAPI schema: ${EXISTING_API_GW_ID}"
    OPENAPI_SCHEMA_TMP=$(mktemp /tmp/openapi-schema-XXXXXX.yaml)
    python3 -c "
import re, sys
with open('${OPENAPI_SCHEMA}') as f:
    content = f.read()
api_gw_id = '${EXISTING_API_GW_ID}'
fixed = re.sub(r'(apiId:\s*\n\s*default: )[a-z0-9]+', lambda m: m.group(1) + api_gw_id, content)
with open(sys.argv[1], 'w') as f:
    f.write(fixed)
" "${OPENAPI_SCHEMA_TMP}"
    UPLOAD_SCHEMA="${OPENAPI_SCHEMA_TMP}"
else
    log_warning "Stack not yet deployed — uploading schema with placeholder API ID (will be corrected post-deploy)"
    UPLOAD_SCHEMA="${OPENAPI_SCHEMA}"
fi

if aws s3 cp "${UPLOAD_SCHEMA}" "s3://${LAMBDA_BUCKET}/openapi-schema.yaml" \
    --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
    log_success "OpenAPI schema uploaded to s3://${LAMBDA_BUCKET}/openapi-schema.yaml"
else
    log_error "Failed to upload OpenAPI schema to S3"
    exit 3
fi
[ -n "${OPENAPI_SCHEMA_TMP:-}" ] && rm -f "${OPENAPI_SCHEMA_TMP}"

echo ""

################################################################################
# Deploy CloudFormation Stack
################################################################################

log_info "Deploying CloudFormation stack..."

# Check if stack exists in ROLLBACK_COMPLETE state — must be deleted before redeploying
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

if [ "${STACK_STATUS}" = "ROLLBACK_COMPLETE" ]; then
    log_warning "Stack is in ROLLBACK_COMPLETE state. Deleting before redeploying..."
    aws cloudformation delete-stack \
        --stack-name "${STACK_NAME}" \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}
    log_info "Waiting for stack deletion to complete..."
    aws cloudformation wait stack-delete-complete \
        --stack-name "${STACK_NAME}" \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}
    log_success "Stack deleted. Proceeding with fresh deployment."
fi

# Convert parameter file to "Key=Value" pairs for --parameter-overrides.
# aws cloudformation deploy does not support _comment fields or the file://
# shorthand that create-stack accepts, so we strip comments and reformat here.
PARAM_OVERRIDES=()
while IFS= read -r line; do
    PARAM_OVERRIDES+=("$line")
done < <(python3 - "${PARAMETER_FILE}" << 'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    params = json.load(f)
for p in params:
    # Skip entries that are comments (no ParameterKey) or have placeholder values
    if "ParameterKey" in p and "ParameterValue" in p:
        # Wrap value in quotes to handle spaces and special characters
        print(f"{p['ParameterKey']}={p['ParameterValue']}")
PYEOF
)

if [ ${#PARAM_OVERRIDES[@]} -eq 0 ]; then
    log_error "No parameters parsed from ${PARAMETER_FILE}. Check the file format."
    exit 1
fi

log_info "Parsed ${#PARAM_OVERRIDES[@]} parameter(s) from ${PARAMETER_FILE}"
# Append the deployment suffix so all templates can use it for resource naming
PARAM_OVERRIDES+=("DeploymentSuffix=${DEPLOY_SUFFIX}")

# Build deployment command with required parameters
DEPLOY_CMD=(
    aws cloudformation deploy
    --template-file "${TEMPLATES_DIR}/parent.yaml"
    --stack-name "${STACK_NAME}"
    --parameter-overrides "${PARAM_OVERRIDES[@]}"
    --capabilities CAPABILITY_NAMED_IAM  # Required for IAM role creation
    --no-cli-pager
    --tags "Environment=${ENVIRONMENT}" "ManagedBy=CloudFormation"
)

# Append profile and region flags if specified
if [ -n "${AWS_PROFILE_FLAG}" ]; then
    DEPLOY_CMD+=(${AWS_PROFILE_FLAG})
fi
if [ -n "${AWS_REGION_FLAG}" ]; then
    DEPLOY_CMD+=(${AWS_REGION_FLAG})
fi

# Add --no-execute-changeset flag for dry-run mode
# This creates a changeset but doesn't execute it, allowing review
if [ "$DRY_RUN" = true ]; then
    DEPLOY_CMD+=(--no-execute-changeset)
    log_warning "Dry-run mode: Changeset will be created but not executed"
fi

# Add --disable-rollback flag to preserve failed stacks for debugging
if [ "$NO_ROLLBACK" = true ]; then
    DEPLOY_CMD+=(--disable-rollback)
    log_warning "No-rollback mode: Failed stacks will NOT be rolled back — inspect events then delete manually"
fi

# Execute deployment command
# CloudFormation will automatically handle create vs update operations
if "${DEPLOY_CMD[@]}"; then
    if [ "$DRY_RUN" = true ]; then
        log_success "Changeset created successfully (not executed)"
        log_info "Review the changeset in AWS Console or use:"
        log_info "  aws cloudformation describe-change-set --stack-name ${STACK_NAME} --change-set-name <changeset-name> --no-cli-pager"
    else
        log_success "Stack deployment completed successfully"
    fi
else
    log_error "Stack deployment failed"
    log_info "Check CloudFormation events for details:"
    log_info "  aws cloudformation describe-stack-events --stack-name ${STACK_NAME} --no-cli-pager"
    exit 5
fi

echo ""

    # Post-deploy: re-upload OpenAPI schema with the actual API Gateway ID from the new stack,
    # then refresh the Gateway Target to pick it up.
    if [ "$DRY_RUN" = false ]; then
        log_info "Updating OpenAPI schema with deployed API Gateway ID..."
        ACTUAL_API_GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' \
            --output text --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)

        if [ -n "${ACTUAL_API_GW_ID}" ] && [ "${ACTUAL_API_GW_ID}" != "None" ]; then
            OPENAPI_SCHEMA_POST=$(mktemp /tmp/openapi-schema-post-XXXXXX.yaml)
            # Use Python for precise replacement of only the apiId default value
            python3 -c "
import re, sys
with open('${PROJECT_ROOT}/docs/orders-api-openapi-3.0.yaml') as f:
    content = f.read()
api_gw_id = '${ACTUAL_API_GW_ID}'
fixed = re.sub(r'(apiId:\s*\n\s*default: )[a-z0-9]+', lambda m: m.group(1) + api_gw_id, content)
with open(sys.argv[1], 'w') as f:
    f.write(fixed)
" "${OPENAPI_SCHEMA_POST}"
            if aws s3 cp "${OPENAPI_SCHEMA_POST}" "s3://${LAMBDA_BUCKET}/openapi-schema.yaml" \
                --no-cli-pager ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
                log_success "OpenAPI schema updated with API Gateway ID: ${ACTUAL_API_GW_ID}"
            else
                log_warning "Failed to update OpenAPI schema post-deploy"
            fi
            rm -f "${OPENAPI_SCHEMA_POST}"
        else
            log_warning "Could not retrieve API Gateway ID — OpenAPI schema may point to wrong account"
        fi
    fi

    # Post-deploy: refresh Gateway Target to pick up the updated OpenAPI schema
    # The schema was uploaded with the correct API Gateway ID before deployment
    if [ "$DRY_RUN" = false ]; then
        log_info "Refreshing AgentCore Gateway Target with updated OpenAPI schema..."
        GATEWAY_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' \
            --output text --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)
        
        TARGET_ID=$(aws bedrock-agentcore-control list-gateway-targets \
            --gateway-identifier "${GATEWAY_ID}" \
            --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} \
            --query 'items[0].targetId' \
            --output text 2>/dev/null)
        
        if [ -n "${GATEWAY_ID}" ] && [ -n "${TARGET_ID}" ] && [ "${TARGET_ID}" != "None" ]; then
            OAUTH_PROVIDER_ARN=$(aws cloudformation describe-stacks \
                --stack-name "${STACK_NAME}" \
                --query 'Stacks[0].Outputs[?OutputKey==`CredentialProviderArn`].OutputValue' \
                --output text --no-cli-pager \
                ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)
            OAUTH_CALLBACK_URL=$(aws cloudformation describe-stacks \
                --stack-name "${STACK_NAME}" \
                --query 'Stacks[0].Outputs[?OutputKey==`OAuthCallbackUrl`].OutputValue' \
                --output text --no-cli-pager \
                ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)
            TARGET_IDP_CLIENT_ID=$(python3 -c "
import json
with open('${PARAMETERS_DIR}/${ENVIRONMENT}-parameters.json') as f:
    params = {p['ParameterKey']: p['ParameterValue'] for p in json.load(f) if 'ParameterKey' in p}
print(params.get('TargetIdpClientId',''))
" 2>/dev/null)
            
            aws bedrock-agentcore-control update-gateway-target \
                --gateway-identifier "${GATEWAY_ID}" \
                --target-id "${TARGET_ID}" \
                --name "${ENVIRONMENT}-orders-api-target-${DEPLOY_SUFFIX}" \
                --target-configuration "{\"mcp\":{\"openApiSchema\":{\"s3\":{\"uri\":\"s3://${LAMBDA_BUCKET}/openapi-schema.yaml\"}}}}" \
                --credential-provider-configurations "[{\"credentialProviderType\":\"OAUTH\",\"credentialProvider\":{\"oauthCredentialProvider\":{\"providerArn\":\"${OAUTH_PROVIDER_ARN}\",\"grantType\":\"AUTHORIZATION_CODE\",\"defaultReturnUrl\":\"${OAUTH_CALLBACK_URL}\",\"scopes\":[\"${TARGET_IDP_CLIENT_ID}/.default\"]}}}]" \
                --no-cli-pager \
                ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>&1 \
                && log_success "Gateway Target refreshed with updated OpenAPI schema" \
                || log_warning "Could not refresh Gateway Target — check errors above"
        else
            log_warning "Could not find Gateway ID or Target ID — skipping Gateway Target refresh"
        fi
    fi

    # Create gateway secret if it doesn't exist
    if [ "$DRY_RUN" = false ]; then
        GATEWAY_SECRET_NAME="${ENVIRONMENT}-gateway-secret-${DEPLOY_SUFFIX}"
        GATEWAY_URL=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' \
            --output text --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)
        API_GW_ID=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' \
            --output text --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)
        
        SECRET_EXISTS=$(aws secretsmanager describe-secret \
            --secret-id "${GATEWAY_SECRET_NAME}" \
            --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} \
            --query 'Name' --output text 2>/dev/null || echo "")
        
        if [ -z "${SECRET_EXISTS}" ]; then
            log_info "Creating gateway secret: ${GATEWAY_SECRET_NAME}..."
            SECRET_VALUE=$(python3 -c "
import json
with open('${PARAMETERS_DIR}/${ENVIRONMENT}-parameters.json') as f:
    params = {p['ParameterKey']: p['ParameterValue'] for p in json.load(f) if 'ParameterKey' in p}
secret = {
    'tenant_id': params.get('TargetIdpTenantId',''),
    'client_id': params.get('GatewayIdpClientId',''),
    'client_secret': params.get('TargetIdpClientSecret',''),
    'gateway_mcp_url': '${GATEWAY_URL}',
    'orders_api_gateway_id': '${API_GW_ID}'
}
print(json.dumps(secret))
" 2>/dev/null)
            aws secretsmanager create-secret \
                --name "${GATEWAY_SECRET_NAME}" \
                --description "AgentCore gateway credentials for ${ENVIRONMENT} environment" \
                --secret-string "${SECRET_VALUE}" \
                --no-cli-pager \
                ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} > /dev/null 2>&1 \
                && log_success "Gateway secret created: ${GATEWAY_SECRET_NAME}" \
                || log_warning "Could not create gateway secret — create manually"
        else
            log_info "Gateway secret already exists: ${GATEWAY_SECRET_NAME}"
        fi
    fi

################################################################################
# Warm Up AgentCore Runtime
################################################################################
# The AgentCore Runtime requires an initial invocation to complete its
# initialization (loading dependencies, connecting to gateway, etc.).
# Without this warm-up, the first real user request will time out with:
# "Runtime initialization time exceeded. Please make sure that initialization completes in 30s."
################################################################################

if [ "$DRY_RUN" = false ]; then
    log_info "Warming up AgentCore Runtime (this may take up to 2 minutes)..."

    AGENT_RUNTIME_ARN=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentRuntimeArn`].OutputValue' \
        --output text --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)

    if [ -z "${AGENT_RUNTIME_ARN}" ] || [ "${AGENT_RUNTIME_ARN}" = "None" ]; then
        log_warning "Could not retrieve AgentRuntimeArn — skipping warm-up"
    else
        log_info "Sending warm-up invocation to: ${AGENT_RUNTIME_ARN}"

        # Send a lightweight warm-up prompt to initialize the runtime.
        # The response doesn't matter — we just need the runtime to start up.
        # Note: invoke-agent-runtime requires an outfile parameter.
        WARMUP_OUTFILE=$(mktemp /tmp/warmup-response-XXXXXX.json)
        WARMUP_RESPONSE=$(aws bedrock-agentcore invoke-agent-runtime \
            --agent-runtime-arn "${AGENT_RUNTIME_ARN}" \
            --qualifier DEFAULT \
            --payload "$(echo -n '{"prompt":"ping"}' | base64)" \
            --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} \
            "${WARMUP_OUTFILE}" 2>&1 || true)
        rm -f "${WARMUP_OUTFILE}"

        if echo "${WARMUP_RESPONSE}" | grep -q "initialization time exceeded\|ServiceUnavailable\|503"; then
            log_info "Runtime still initializing — waiting 60 seconds and retrying..."
            sleep 60
            WARMUP_OUTFILE2=$(mktemp /tmp/warmup-response-XXXXXX.json)
            aws bedrock-agentcore invoke-agent-runtime \
                --agent-runtime-arn "${AGENT_RUNTIME_ARN}" \
                --qualifier DEFAULT \
                --payload "$(echo -n '{"prompt":"ping"}' | base64)" \
                --no-cli-pager \
                ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} \
                "${WARMUP_OUTFILE2}" > /dev/null 2>&1 || true
            rm -f "${WARMUP_OUTFILE2}"
            log_success "AgentCore Runtime warm-up complete"
        else
            log_success "AgentCore Runtime warm-up complete"
        fi
    fi
    echo ""
fi

################################################################################
# Deploy Frontend to S3
################################################################################

# Only deploy frontend if not in dry-run mode
if [ "$DRY_RUN" = false ]; then
    log_info "Deploying frontend to S3..."

    FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
        --output text --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)

    CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
        --output text --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)

    AGENTCORE_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentProxyFunctionUrl`].OutputValue' \
        --output text --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)
    # Append /invoke — the API Gateway route for agent invocation is POST /invoke
    AGENTCORE_ENDPOINT="${AGENTCORE_ENDPOINT%/}/invoke"

    OAUTH_CALLBACK_URL=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --query 'Stacks[0].Outputs[?OutputKey==`OAuthCallbackUrl`].OutputValue' \
        --output text --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)

    if [ -z "${FRONTEND_BUCKET}" ]; then
        log_warning "Could not retrieve frontend S3 bucket — skipping frontend deploy"
    else
        FRONTEND_DIR="${PROJECT_ROOT}/frontend"

        # Export stack-derived values so build-config.js can substitute them
        export AGENTCORE_ENDPOINT="${AGENTCORE_ENDPOINT}"
        # WS_SIGN_ENDPOINT is intentionally empty — no WebSocket signer in this stack
        export WS_SIGN_ENDPOINT=""

        # Collect MSAL env vars interactively if not already set in the environment.
        # These are required by build-config.js to generate config.generated.js.
        # The CloudFront domain is used as the default redirect URI suggestion.
        CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" \
            --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' \
            --output text --no-cli-pager \
            ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null)

        if [ -z "${MSAL_CLIENT_ID:-}" ]; then
            echo ""
            log_info "Frontend configuration requires Azure AD (MSAL) settings."
            read -r -p "  Enter MSAL_CLIENT_ID (Azure App Registration Client ID): " MSAL_CLIENT_ID
            export MSAL_CLIENT_ID
        fi

        if [ -z "${MSAL_AUTHORITY:-}" ]; then
            TENANT_ID=$(python3 -c "
import json
with open('${PARAMETERS_DIR}/${ENVIRONMENT}-parameters.json') as f:
    params = json.load(f)
for p in params:
    if p.get('ParameterKey') == 'TargetIdpTenantId':
        print(p['ParameterValue'])
        break
" 2>/dev/null || echo "")
            DEFAULT_AUTHORITY="https://login.microsoftonline.com/${TENANT_ID}"
            read -r -p "  Enter MSAL_AUTHORITY [${DEFAULT_AUTHORITY}]: " INPUT_AUTHORITY
            MSAL_AUTHORITY="${INPUT_AUTHORITY:-${DEFAULT_AUTHORITY}}"
            export MSAL_AUTHORITY
        fi

        if [ -z "${REDIRECT_URI:-}" ]; then
            DEFAULT_REDIRECT="https://${CLOUDFRONT_DOMAIN}"
            read -r -p "  Enter REDIRECT_URI [${DEFAULT_REDIRECT}]: " INPUT_REDIRECT
            REDIRECT_URI="${INPUT_REDIRECT:-${DEFAULT_REDIRECT}}"
            export REDIRECT_URI
        fi

        log_info "Using frontend config:"
        log_info "  MSAL_CLIENT_ID:  ${MSAL_CLIENT_ID}"
        log_info "  MSAL_AUTHORITY:  ${MSAL_AUTHORITY}"
        log_info "  REDIRECT_URI:    ${REDIRECT_URI}"
        echo ""

        if [ -z "${MSAL_CLIENT_ID}" ] || [ -z "${MSAL_AUTHORITY}" ] || [ -z "${REDIRECT_URI}" ]; then
            log_error "One or more required frontend values are empty — skipping frontend deploy"
        else
            # Install npm deps if node_modules is missing
            if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
                log_info "Installing frontend dependencies..."
                npm install --prefix "${FRONTEND_DIR}" --silent
            fi

            # Generate config.generated.js from config.json + env vars
            log_info "Building frontend configuration..."
            node "${FRONTEND_DIR}/build-config.js"

            if [ ! -f "${FRONTEND_DIR}/src/config.generated.js" ]; then
                log_error "Frontend config build failed — config.generated.js not found"
            else
                log_success "Frontend config built"

                # Sync frontend/src to S3
                log_info "Uploading frontend to s3://${FRONTEND_BUCKET}/..."
                if aws s3 sync "${FRONTEND_DIR}/src/" "s3://${FRONTEND_BUCKET}/" \
                    --exclude "*.md" \
                    --exclude ".DS_Store" \
                    --no-cli-pager \
                    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
                    log_success "Frontend uploaded to s3://${FRONTEND_BUCKET}/"
                else
                    log_error "Frontend S3 upload failed"
                fi

                # Invalidate CloudFront cache
                if [ -n "${CLOUDFRONT_DIST_ID}" ]; then
                    log_info "Invalidating CloudFront cache..."
                    aws cloudfront create-invalidation \
                        --distribution-id "${CLOUDFRONT_DIST_ID}" \
                        --paths "/*" \
                        --no-cli-pager \
                        ${AWS_PROFILE_FLAG} > /dev/null 2>&1 \
                        && log_success "CloudFront cache invalidated" \
                        || log_warning "CloudFront invalidation failed (cache may be stale)"
                fi
            fi
        fi
    fi
    echo ""
fi

################################################################################
# Display Stack Outputs
################################################################################

# Only display outputs if not in dry-run mode and stack exists
if [ "$DRY_RUN" = false ]; then
    log_info "Retrieving stack outputs..."
    
    # Wait a moment for stack to stabilize
    sleep 2
    
    # Retrieve and display stack outputs in table format
    # Outputs include API URLs, resource ARNs, and other important values
    if aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --query 'Stacks[0].Outputs' \
        --output table \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
        echo ""
        log_success "Stack outputs displayed above"
    else
        log_warning "Could not retrieve stack outputs (stack may still be creating)"
    fi
fi

echo ""

################################################################################
# Deployment Summary
################################################################################

log_success "=========================================="
log_success "Deployment Summary"
log_success "=========================================="
log_success "Stack Name:    ${STACK_NAME}"
log_success "Environment:   ${ENVIRONMENT}"
log_success "AWS Profile:   ${PROFILE_DISPLAY}"
log_success "Status:        $([ "$DRY_RUN" = true ] && echo "Changeset Created" || echo "Deployed")"
log_success "=========================================="

if [ "$DRY_RUN" = false ]; then
    log_info ""
    log_info "Next steps:"
    log_info "  1. Verify stack resources in AWS Console"
    log_info "  2. Test API endpoints and application functionality"
    log_info "  3. Monitor CloudWatch dashboards and alarms"
    log_info ""
    log_info "To view stack details:"
    log_info "  aws cloudformation describe-stacks --stack-name ${STACK_NAME} --no-cli-pager"
    log_info ""
    log_info "To delete the stack:"
    log_info "  ./cleanup-stack.sh ${STACK_NAME}$([ -n "${AWS_PROFILE_ARG}" ] && echo " --profile ${AWS_PROFILE_ARG}")"
fi

exit 0
