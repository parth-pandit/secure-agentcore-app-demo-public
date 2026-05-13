#!/bin/bash
################################################################################
# Multi-Region Cleanup Script — Project Redwood
#
# Deletes ALL stacks and resources in both regions.
# Always prompts for confirmation before proceeding.
#
# Usage:
#   ./cleanup-stack-multi-region.sh
################################################################################

set -e
export AWS_PAGER=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/infrastructure/deploy-config-multi-region.sh"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Project Redwood — Multi-Region CLEANUP                       ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
log_warning "This will DELETE all resources in BOTH regions:"
echo ""
echo "  Stacks to delete:"
echo "    • secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}        (${PRIMARY_REGION}) [regional]"
echo "    • secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-dr     (${DR_REGION}) [regional]"
echo "    • secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global (${PRIMARY_REGION}) [global]"
echo "    • ${ENVIRONMENT}-lambda-edge-${SUFFIX}                 (us-east-1)"
echo "    • ${ENVIRONMENT}-agentcore-memory-${SUFFIX}            (${PRIMARY_REGION})"
echo "    • ${ENVIRONMENT}-agentcore-memory-${SUFFIX}            (${DR_REGION})"
echo "    • ${ENVIRONMENT}-agentcore-memory-replication-${SUFFIX} (${PRIMARY_REGION})"
echo ""
echo "  S3 buckets:"
echo "    • ${CFN_TEMPLATES_BUCKET}"
echo "    • ${CFN_TEMPLATES_BUCKET_DR}"
echo "    • ${LAMBDA_BUCKET_PRIMARY}"
echo "    • ${LAMBDA_BUCKET_DR}"
echo ""

log_error "⚠️  THIS ACTION CANNOT BE UNDONE!"
echo ""
read -p "  Are you sure you want to delete? Type 'DELETE' to confirm: " CONFIRM
if [ "$CONFIRM" != "DELETE" ]; then
    log_info "Cancelled."
    exit 0
fi

echo ""
log_info "Starting cleanup..."

# Helper: empty a versioned S3 bucket
empty_bucket() {
    local bucket="$1"
    python3 -c "
import boto3
s3 = boto3.resource('s3')
try:
    b = s3.Bucket('${bucket}')
    b.object_versions.all().delete()
    b.objects.all().delete()
    print(f'  Emptied: ${bucket}')
except Exception as e:
    print(f'  Skip: ${bucket} ({e})')
" 2>/dev/null
}

# [1] Empty frontend bucket
log_info "[1/8] Emptying frontend bucket..."
empty_bucket "${ENVIRONMENT}-frontend-${AWS_ACCOUNT_ID}-${SUFFIX}"

# [2] Delete global stack (CloudFront) — must go first so Lambda@Edge replicas start cleanup
log_info "[2/8] Deleting global stack (CloudFront)..."
aws cloudformation delete-stack --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true

# [3] Delete regional stacks
log_info "[3/8] Deleting regional stacks..."
aws cloudformation delete-stack --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation delete-stack --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-dr" \
    --region "${DR_REGION}" 2>/dev/null || true

# [4] Wait for global + regional stacks
log_info "[4/8] Waiting for stack deletions..."
aws cloudformation wait stack-delete-complete \
    --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-global" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation wait stack-delete-complete \
    --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation wait stack-delete-complete \
    --stack-name "secure-agentcore-app-${ENVIRONMENT}-${SUFFIX}-dr" \
    --region "${DR_REGION}" 2>/dev/null || true

# [5] Delete Lambda@Edge (after CloudFront is gone)
log_info "[5/8] Deleting Lambda@Edge stack..."
local EDGE_STACK_NAME="${ENVIRONMENT}-lambda-edge-${SUFFIX}"

aws cloudformation delete-stack --stack-name "${EDGE_STACK_NAME}" \
    --region us-east-1 2>/dev/null || true

if ! aws cloudformation wait stack-delete-complete \
    --stack-name "${EDGE_STACK_NAME}" \
    --region us-east-1 2>/dev/null; then
    log_warning "Lambda@Edge CFN delete failed (replicas still active) — retaining function in CFN"
    aws cloudformation delete-stack --stack-name "${EDGE_STACK_NAME}" \
        --region us-east-1 --retain-resources OriginRouterFunction 2>/dev/null || true
    aws cloudformation wait stack-delete-complete \
        --stack-name "${EDGE_STACK_NAME}" \
        --region us-east-1 2>/dev/null || true
fi

# Delete all Lambda@Edge functions matching our prefix (handles DeploymentId suffix)
local EDGE_FUNCS=$(aws lambda list-functions --region us-east-1 \
    --query "Functions[?starts_with(FunctionName, '${ENVIRONMENT}-origin-router-${SUFFIX}')].FunctionName" \
    --output text 2>/dev/null || echo "")
if [ -n "${EDGE_FUNCS}" ]; then
    log_info "  Cleaning up Lambda@Edge functions..."
    local MAX_RETRIES=10
    local RETRY_INTERVAL=30
    local ALL_DELETED=true
    for func_name in ${EDGE_FUNCS}; do
        local DELETED=false
        for i in $(seq 1 ${MAX_RETRIES}); do
            if aws lambda delete-function --function-name "${func_name}" --region us-east-1 2>/dev/null; then
                DELETED=true
                log_success "  Deleted: ${func_name}"
                break
            fi
            log_info "  Retry ${i}/${MAX_RETRIES} for ${func_name} — replicas still active, waiting ${RETRY_INTERVAL}s..."
            sleep ${RETRY_INTERVAL}
        done
        if [ "${DELETED}" = false ]; then
            ALL_DELETED=false
            log_warning "  Could not delete ${func_name} — run manually later:"
            log_warning "    aws lambda delete-function --function-name ${func_name} --region us-east-1"
        fi
    done
fi

# [6] Delete memory stacks
log_info "[6/8] Deleting memory stacks..."
empty_bucket "${ENVIRONMENT}-${SUFFIX}-memory-payloads-${AWS_ACCOUNT_ID}"
aws cloudformation delete-stack --stack-name "${ENVIRONMENT}-agentcore-memory-replication-${SUFFIX}" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation delete-stack --stack-name "${ENVIRONMENT}-agentcore-memory-${SUFFIX}" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation delete-stack --stack-name "${ENVIRONMENT}-agentcore-memory-${SUFFIX}" \
    --region "${DR_REGION}" 2>/dev/null || true

aws cloudformation wait stack-delete-complete \
    --stack-name "${ENVIRONMENT}-agentcore-memory-replication-${SUFFIX}" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation wait stack-delete-complete \
    --stack-name "${ENVIRONMENT}-agentcore-memory-${SUFFIX}" \
    --region "${PRIMARY_REGION}" 2>/dev/null || true
aws cloudformation wait stack-delete-complete \
    --stack-name "${ENVIRONMENT}-agentcore-memory-${SUFFIX}" \
    --region "${DR_REGION}" 2>/dev/null || true

# [7] Delete S3 buckets
log_info "[7/8] Deleting S3 buckets..."
for bucket in "${CFN_TEMPLATES_BUCKET}" "${CFN_TEMPLATES_BUCKET_DR}" "${LAMBDA_BUCKET_PRIMARY}" "${LAMBDA_BUCKET_DR}"; do
    empty_bucket "${bucket}"
    aws s3 rb "s3://${bucket}" 2>/dev/null || true
done

# [8] Delete gateway secrets
log_info "[8/8] Deleting gateway secrets..."
aws secretsmanager delete-secret --secret-id "${GATEWAY_SECRET_NAME}" \
    --force-delete-without-recovery --region "${PRIMARY_REGION}" 2>/dev/null || true
aws secretsmanager delete-secret --secret-id "${GATEWAY_SECRET_NAME}" \
    --force-delete-without-recovery --region "${DR_REGION}" 2>/dev/null || true

echo ""
log_success "╔════════════════════════════════════════════════════════════════╗"
log_success "║  CLEANUP COMPLETE                                              ║"
log_success "╚════════════════════════════════════════════════════════════════╝"
echo ""
log_info "All stacks and resources deleted."
log_info "To redeploy: bash infrastructure/cloudformation/scripts/deploy-stack-multi-region.sh"
echo ""
