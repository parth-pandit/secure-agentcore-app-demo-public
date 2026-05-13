#!/bin/bash
################################################################################
# Deploy AgentCore Memory (per-region) + Replication pipeline (primary only)
#
# Uses the same naming scheme as the main project:
#   Environment prefix (dev) + deployment suffix (yyyymmddHHMM)
#
# Usage:
#   ./deploy.sh us-east-1 [suffix]    # Primary: memory + replication pipeline
#   ./deploy.sh us-east-2 [suffix]    # DR: memory only (no replication)
#
# Deploy order:
#   1. Deploy DR first:      ./deploy.sh us-east-2 202605110202
#   2. Deploy Primary:       ./deploy.sh us-east-1 202605110202
################################################################################

set -e
export AWS_PAGER=""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Source deployment configuration
source "${PROJECT_ROOT}/infrastructure/deploy-config-multi-region.sh"

# Override from args
REGION=${1:-$PRIMARY_REGION}
SUFFIX_ARG=${2:-$SUFFIX}
IS_PRIMARY="false"
[ "$REGION" = "$PRIMARY_REGION" ] && IS_PRIMARY="true"

# Use SUFFIX from arg or config
SUFFIX="${SUFFIX_ARG}"
SECONDARY_REGION="${DR_REGION}"

# Memory name must match [a-zA-Z][a-zA-Z0-9_]{0,47}
MEMORY_NAME="${ENVIRONMENT}_memory_${REGION//-/_}_${SUFFIX//-/_}"
STACK_NAME="$(get_memory_stack_name)"

# S3 bucket for Lambda code (per-region)
BUCKET="$(get_lambda_bucket $REGION)"

echo "=== AgentCore Memory Deploy (${REGION}) ==="
echo "  Primary:      $IS_PRIMARY"
echo "  Memory name:  $MEMORY_NAME"
echo "  Stack name:   $STACK_NAME"
echo "  Code bucket:  $BUCKET"
echo "  Suffix:       $SUFFIX"
echo ""

# Ensure Lambda code bucket exists in this region
if ! aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
    echo "  Creating S3 bucket: $BUCKET"
    if [ "$REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
    else
        aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION"
    fi
fi

# --- Step 1: Deploy replication pipeline FIRST (primary only) ---
if [ "$IS_PRIMARY" = "true" ]; then
    echo "[1/2] Deploying replication pipeline (primary only)..."

    REPLICATION_STACK="$(get_replication_stack_name)"

    # Package replicator Lambda
    cd "$SCRIPT_DIR/lambda"
    zip -r /tmp/memory-replicator-lambda.zip handler.py
    cd "$SCRIPT_DIR"

    # Upload Lambda code
    aws s3 cp /tmp/memory-replicator-lambda.zip "s3://$BUCKET/memory-replicator/lambda.zip" --region "$REGION"

    # Get DR memory ID (must deploy DR memory first)
    DR_STACK_NAME="$(get_memory_stack_name)"
    DR_MEMORY_ID_RAW=$(aws cloudformation describe-stacks \
        --stack-name "${DR_STACK_NAME}" --region "$SECONDARY_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`MemoryId`].OutputValue' --output text 2>/dev/null || echo "PLACEHOLDER")
    DR_MEMORY_ID="${DR_MEMORY_ID_RAW##*/}"

    if [ "$DR_MEMORY_ID" = "PLACEHOLDER" ] || [ -z "$DR_MEMORY_ID" ]; then
        echo "  ⚠ WARNING: DR memory not found. Deploy DR first (./deploy.sh us-east-2 $SUFFIX)"
        echo "  Using PLACEHOLDER — replication won't work until you redeploy primary."
    fi

    echo "  DR Memory ID: $DR_MEMORY_ID"

    # Stack prefix for resource naming inside the replication CFN
    STACK_PREFIX="${ENVIRONMENT}-${SUFFIX}"

    aws cloudformation deploy \
        --template-file "$SCRIPT_DIR/cfn-memory-replication.yaml" \
        --stack-name "${REPLICATION_STACK}" \
        --region "$REGION" \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameter-overrides \
            StackPrefix="$STACK_PREFIX" \
            DrRegion="$SECONDARY_REGION" \
            DrMemoryId="$DR_MEMORY_ID" \
            LambdaCodeBucket="$BUCKET" \
            LambdaCodeKey="memory-replicator/lambda.zip" \
        --no-fail-on-empty-changeset

    # Get outputs
    PAYLOAD_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name "${REPLICATION_STACK}" --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`PayloadBucketName`].OutputValue' --output text)
    SNS_TOPIC_ARN=$(aws cloudformation describe-stacks \
        --stack-name "${REPLICATION_STACK}" --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ReplicationTopicArn`].OutputValue' --output text)

    echo "  ✔ Replication pipeline deployed"
    echo "    Payload bucket: $PAYLOAD_BUCKET"
    echo "    SNS topic: $SNS_TOPIC_ARN"
    echo ""
else
    PAYLOAD_BUCKET=""
    SNS_TOPIC_ARN=""
    echo "[1/2] Skipping replication pipeline (DR region)"
    echo ""
fi

# --- Step 2: Deploy Memory resource ---
echo "[2/2] Deploying Memory resource..."

# Stack prefix for resource naming inside the memory CFN
STACK_PREFIX="${ENVIRONMENT}-${SUFFIX}"

aws cloudformation deploy \
    --template-file "$SCRIPT_DIR/cfn-memory.yaml" \
    --stack-name "${STACK_NAME}" \
    --region "$REGION" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        StackPrefix="$STACK_PREFIX" \
        MemoryName="$MEMORY_NAME" \
        EventExpiryDays="$MEMORY_EXPIRY_DAYS" \
        IsPrimary="$IS_PRIMARY" \
        PayloadBucketName="$PAYLOAD_BUCKET" \
        SnsTopicArn="$SNS_TOPIC_ARN" \
    --no-fail-on-empty-changeset

echo ""
echo "✔ Memory deployed in ${REGION}. Outputs:"
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
if [ "$IS_PRIMARY" = "true" ]; then
    echo "Next: Connect memory to the runtime by updating MEMORY_ID env var."
else
    echo "Next: Deploy primary region: ./deploy.sh us-east-1 $SUFFIX"
fi
