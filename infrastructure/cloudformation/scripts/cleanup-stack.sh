#!/bin/bash

################################################################################
# CloudFormation Stack Cleanup Script
#
# This script safely deletes a CloudFormation parent stack and all its nested
# child stacks. It includes safety checks for production environments and
# handles S3 bucket cleanup to prevent deletion failures.
#
# Usage:
#   ./cleanup-stack.sh <stack-name> [--force] [--profile <name>] [--region <region>]
#
# Arguments:
#   stack-name    Name of the parent CloudFormation stack to delete
#
# Options:
#   --force           Skip confirmation prompt (use with caution!)
#   --profile <name>  AWS CLI profile to use (default: AWS_PROFILE env var or "default")
#   --region <region> AWS region (default: profile's configured region)
#
# Examples:
#   ./cleanup-stack.sh my-dev-stack
#   ./cleanup-stack.sh my-dev-stack --profile unicorn --region us-west-2
#   ./cleanup-stack.sh my-prod-stack --force --profile unicorn --region us-west-2
#
# Requirements:
#   - AWS CLI configured with appropriate credentials
#   - IAM permissions: cloudformation:*, s3:*, logs:DescribeLogGroups
#
# Exit Codes:
#   0 - Success
#   1 - Invalid arguments or user cancelled
#   2 - Stack not found
#   3 - Deletion failed
################################################################################

set -e  # Exit on error
set -o pipefail  # Catch errors in pipes

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

################################################################################
# Function: print_usage
# Description: Display usage information and exit
################################################################################
print_usage() {
    echo "Usage: $0 <stack-name> [--force] [--profile <name>] [--region <region>]"
    echo ""
    echo "Arguments:"
    echo "  stack-name    Name of the parent CloudFormation stack to delete"
    echo ""
    echo "Options:"
    echo "  --force           Skip confirmation prompt"
    echo "  --profile <name>  AWS CLI profile to use"
    echo "  --region <region> AWS region (e.g. us-west-2)"
    echo ""
    echo "Examples:"
    echo "  $0 my-dev-stack"
    echo "  $0 my-dev-stack --profile unicorn --region us-west-2"
    echo "  $0 my-prod-stack --force --profile unicorn --region us-west-2"
    exit 1
}

################################################################################
# Function: log_info
# Description: Print informational message in blue
################################################################################
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

################################################################################
# Function: log_success
# Description: Print success message in green
################################################################################
log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

################################################################################
# Function: log_warning
# Description: Print warning message in yellow
################################################################################
log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

################################################################################
# Function: log_error
# Description: Print error message in red
################################################################################
log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

################################################################################
# Function: check_stack_exists
# Description: Verify that the CloudFormation stack exists
# Arguments:
#   $1 - Stack name
# Returns:
#   0 if stack exists, 1 otherwise
################################################################################
check_stack_exists() {
    local stack_name=$1
    
    if aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --no-cli-pager \
        --output json \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

################################################################################
# Function: get_stack_environment
# Description: Extract environment tag from stack to detect production
# Arguments:
#   $1 - Stack name
# Returns:
#   Environment value (dev/staging/prod) or "unknown"
################################################################################
get_stack_environment() {
    local stack_name=$1
    
    # Get Environment tag from stack
    local environment=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query 'Stacks[0].Tags[?Key==`Environment`].Value' \
        --output text \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null || echo "unknown")
    
    echo "$environment"
}

################################################################################
# Function: get_s3_bucket_from_outputs
# Description: Retrieve Frontend S3 bucket name from stack outputs
# Arguments:
#   $1 - Stack name
# Returns:
#   S3 bucket name or empty string if not found
################################################################################
get_s3_bucket_from_outputs() {
    local stack_name=$1
    
    # Try to get S3BucketName from stack outputs
    local bucket_name=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
        --output text \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null || echo "")
    
    echo "$bucket_name"
}

################################################################################
# Function: empty_s3_bucket
# Description: Remove all objects and versions from an S3 bucket
# Arguments:
#   $1 - S3 bucket name
# Returns:
#   0 on success, 1 on failure
# Note:
#   S3 buckets must be empty before CloudFormation can delete them.
#   This function handles both versioned and non-versioned buckets.
################################################################################
empty_s3_bucket() {
    local bucket_name=$1
    
    log_info "Checking if bucket '$bucket_name' exists..."
    
    # Check if bucket exists
    if ! aws s3 ls "s3://$bucket_name" --no-cli-pager ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} > /dev/null 2>&1; then
        log_warning "Bucket '$bucket_name' does not exist or is not accessible"
        return 0
    fi
    
    log_info "Emptying S3 bucket: $bucket_name"
    
    # Remove all object versions (for versioned buckets)
    log_info "Removing all object versions..."
    aws s3api list-object-versions \
        --bucket "$bucket_name" \
        --output json \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null | \
    jq -r '.Versions[]? | "--key \"\(.Key)\" --version-id \"\(.VersionId)\""' | \
    while read -r args; do
        if [ -n "$args" ]; then
            eval aws s3api delete-object \
                --bucket "$bucket_name" \
                $args \
                --no-cli-pager ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} > /dev/null 2>&1 || true
        fi
    done
    
    # Remove all delete markers (for versioned buckets)
    log_info "Removing all delete markers..."
    aws s3api list-object-versions \
        --bucket "$bucket_name" \
        --output json \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null | \
    jq -r '.DeleteMarkers[]? | "--key \"\(.Key)\" --version-id \"\(.VersionId)\""' | \
    while read -r args; do
        if [ -n "$args" ]; then
            eval aws s3api delete-object \
                --bucket "$bucket_name" \
                $args \
                --no-cli-pager ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} > /dev/null 2>&1 || true
        fi
    done
    
    # Remove all objects (for non-versioned buckets or remaining objects)
    log_info "Removing all remaining objects..."
    aws s3 rm "s3://$bucket_name" \
        --recursive \
        --no-cli-pager \
        ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>/dev/null || true
    
    log_success "S3 bucket '$bucket_name' emptied successfully"
    return 0
}

################################################################################
# Function: confirm_deletion
# Description: Prompt user for confirmation before deleting stack
# Arguments:
#   $1 - Stack name
#   $2 - Environment (dev/staging/prod)
# Returns:
#   0 if user confirms, 1 if user cancels
################################################################################
confirm_deletion() {
    local stack_name=$1
    local environment=$2
    
    echo ""
    log_warning "═══════════════════════════════════════════════════════════"
    log_warning "  STACK DELETION CONFIRMATION"
    log_warning "═══════════════════════════════════════════════════════════"
    echo ""
    echo "  Stack Name:    $stack_name"
    echo "  Environment:   $environment"
    echo ""
    
    # Extra warning for production environments
    if [[ "$environment" == "prod" ]] || [[ "$environment" == "production" ]]; then
        log_error "⚠️  WARNING: This is a PRODUCTION stack!"
        log_error "⚠️  Deletion will remove all resources and data!"
        echo ""
    fi
    
    log_warning "This action will:"
    echo "  • Delete the parent CloudFormation stack"
    echo "  • Delete all nested child stacks"
    echo "  • Remove all AWS resources (Lambda, DynamoDB, API Gateway, etc.)"
    echo "  • Empty and delete S3 buckets"
    echo "  • Delete CloudWatch logs and alarms"
    echo ""
    log_error "⚠️  THIS ACTION CANNOT BE UNDONE!"
    echo ""
    
    # Prompt for confirmation
    read -p "Type 'DELETE' to confirm deletion: " confirmation
    
    if [[ "$confirmation" == "DELETE" ]]; then
        return 0
    else
        log_info "Deletion cancelled by user"
        return 1
    fi
}

################################################################################
# Main Script
################################################################################

# Parse command-line arguments
if [ $# -lt 1 ]; then
    log_error "Invalid number of arguments"
    print_usage
fi

STACK_NAME=$1
shift

FORCE_FLAG=false
AWS_PROFILE_ARG="${AWS_PROFILE:-}"
AWS_REGION_ARG="${AWS_DEFAULT_REGION:-}"

while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE_FLAG=true
            shift
            ;;
        --profile)
            AWS_PROFILE_ARG="$2"
            shift 2
            ;;
        --region)
            AWS_REGION_ARG="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            ;;
    esac
done

# Build AWS CLI flags
if [ -n "${AWS_PROFILE_ARG}" ]; then
    AWS_PROFILE_FLAG="--profile ${AWS_PROFILE_ARG}"
    PROFILE_DISPLAY="${AWS_PROFILE_ARG}"
else
    AWS_PROFILE_FLAG=""
    PROFILE_DISPLAY="default"
fi

if [ -n "${AWS_REGION_ARG}" ]; then
    AWS_REGION_FLAG="--region ${AWS_REGION_ARG}"
    REGION_DISPLAY="${AWS_REGION_ARG}"
else
    AWS_REGION_FLAG=""
    REGION_DISPLAY="(profile default)"
fi

log_info "Starting cleanup process for stack: $STACK_NAME"
log_info "  AWS Profile: ${PROFILE_DISPLAY}"
log_info "  AWS Region:  ${REGION_DISPLAY}"

# Check if stack exists
if ! check_stack_exists "$STACK_NAME"; then
    log_error "Stack '$STACK_NAME' does not exist or is not accessible"
    exit 2
fi

log_success "Stack '$STACK_NAME' found"

# Get stack environment
ENVIRONMENT=$(get_stack_environment "$STACK_NAME")
log_info "Stack environment: $ENVIRONMENT"

# Require confirmation unless --force flag is provided
if [ "$FORCE_FLAG" != true ]; then
    if ! confirm_deletion "$STACK_NAME" "$ENVIRONMENT"; then
        log_info "Cleanup cancelled"
        exit 1
    fi
else
    log_warning "Skipping confirmation (--force flag provided)"
fi

echo ""
log_info "═══════════════════════════════════════════════════════════"
log_info "  STARTING STACK CLEANUP"
log_info "═══════════════════════════════════════════════════════════"
echo ""

# Step 1: Empty S3 buckets
log_info "Step 1/2: Emptying S3 buckets..."
S3_BUCKET=$(get_s3_bucket_from_outputs "$STACK_NAME")

if [ -n "$S3_BUCKET" ]; then
    log_info "Found Frontend S3 bucket: $S3_BUCKET"
    if empty_s3_bucket "$S3_BUCKET"; then
        log_success "S3 bucket cleanup completed"
    else
        log_warning "S3 bucket cleanup encountered issues (continuing anyway)"
    fi
else
    log_info "No S3 bucket found in stack outputs (skipping S3 cleanup)"
fi

echo ""

# Step 2: Delete CloudFormation stack
log_info "Step 2/2: Deleting CloudFormation stack..."
log_info "Initiating stack deletion: $STACK_NAME"

if aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG}; then
    log_success "Stack deletion initiated"
else
    log_error "Failed to initiate stack deletion"
    exit 3
fi

# Wait for stack deletion to complete
log_info "Waiting for stack deletion to complete (this may take several minutes)..."
log_info "You can monitor progress in the AWS Console or press Ctrl+C to stop waiting"
echo ""

# Note: aws cloudformation wait has a default timeout of 120 attempts * 30 seconds = 1 hour
if aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --no-cli-pager \
    ${AWS_PROFILE_FLAG} ${AWS_REGION_FLAG} 2>&1; then
    echo ""
    log_success "═══════════════════════════════════════════════════════════"
    log_success "  STACK DELETION COMPLETED SUCCESSFULLY"
    log_success "═══════════════════════════════════════════════════════════"
    echo ""
    log_success "Stack '$STACK_NAME' has been deleted"
    log_info "All nested stacks and resources have been removed"
    exit 0
else
    echo ""
    log_error "═══════════════════════════════════════════════════════════"
    log_error "  STACK DELETION FAILED"
    log_error "═══════════════════════════════════════════════════════════"
    echo ""
    log_error "Stack deletion did not complete successfully"
    log_info "Check the CloudFormation console for detailed error messages"
    log_info "Common issues:"
    echo "  • S3 buckets not empty (try running this script again)"
    echo "  • Resources with deletion protection enabled"
    echo "  • Resources in use by other services"
    echo "  • IAM permission issues"
    echo ""
    log_info "To retry deletion after fixing issues:"
    echo "  $0 $STACK_NAME"
    exit 3
fi
