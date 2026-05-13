#!/bin/bash

# Script to export API Gateway specification in OpenAPI 3.0 format
# This script uses AWS CLI to export the API definition from API Gateway

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="${1:-dev}"
OUTPUT_FILE="${2:-docs/orders-api-openapi-3.0-exported.yaml}"
EXPORT_TYPE="${3:-oas30}"  # oas30 for OpenAPI 3.0, swagger for OpenAPI 2.0

echo -e "${GREEN}=== API Gateway OpenAPI Export ===${NC}"
echo ""

# Get the stack name
STACK_NAME="${ENVIRONMENT}-secure-agentcore-app"

echo -e "${YELLOW}Environment:${NC} $ENVIRONMENT"
echo -e "${YELLOW}Stack Name:${NC} $STACK_NAME"
echo -e "${YELLOW}Export Type:${NC} $EXPORT_TYPE"
echo ""

# Get API Gateway ID from CloudFormation stack
echo -e "${YELLOW}Retrieving API Gateway ID from CloudFormation...${NC}"
API_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayId'].OutputValue" \
    --output text)

if [ -z "$API_ID" ] || [ "$API_ID" == "None" ]; then
    echo -e "${RED}Error: Could not retrieve API Gateway ID from stack${NC}"
    echo -e "${YELLOW}Make sure the stack '$STACK_NAME' exists and has been deployed${NC}"
    exit 1
fi

echo -e "${GREEN}API Gateway ID:${NC} $API_ID"
echo ""

# Get the stage name (same as environment)
STAGE_NAME="$ENVIRONMENT"

# Export the API specification
echo -e "${YELLOW}Exporting API specification in $EXPORT_TYPE format...${NC}"
aws apigateway get-export \
    --rest-api-id "$API_ID" \
    --stage-name "$STAGE_NAME" \
    --export-type "$EXPORT_TYPE" \
    --accepts "application/yaml" \
    "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ API specification exported successfully!${NC}"
    echo -e "${GREEN}Output file:${NC} $OUTPUT_FILE"
    echo ""
    
    # Display file size
    FILE_SIZE=$(wc -c < "$OUTPUT_FILE" | tr -d ' ')
    echo -e "${YELLOW}File size:${NC} $FILE_SIZE bytes"
    
    # Count number of paths
    PATH_COUNT=$(grep -c "^  /.*:" "$OUTPUT_FILE" || true)
    echo -e "${YELLOW}Number of paths:${NC} $PATH_COUNT"
    
    echo ""
    echo -e "${GREEN}You can now use this file to:${NC}"
    echo "  - Import into API documentation tools (Swagger UI, Postman, etc.)"
    echo "  - Generate client SDKs"
    echo "  - Share with API consumers"
    echo "  - Version control your API specification"
else
    echo -e "${RED}✗ Failed to export API specification${NC}"
    exit 1
fi
