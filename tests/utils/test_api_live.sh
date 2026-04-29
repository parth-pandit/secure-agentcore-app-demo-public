#!/bin/bash
# test_api_live.sh - Test Orders API with real Azure Entra ID authentication
# This script helps you test your deployed API using curl with real Azure tokens
#
# Prerequisites:
# - Azure Entra ID token (use generate_azure_token.sh or set AZURE_TOKEN env var)
# - Deployed API stack in AWS
#
# Usage:
#   export AZURE_TOKEN="<your-azure-token>"
#   ./tests/utils/test_api_live.sh

# Note: Not using 'set -e' because we want to continue running tests even if some fail

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Orders API Live Testing Script         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Get API URL from CloudFormation
echo -e "${YELLOW}Step 1: Getting API URL from CloudFormation...${NC}"
echo ""
echo "Available stacks:"
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `orders`) || contains(StackName, `agentcore`)].StackName' \
  --output table

echo ""
read -p "Enter your stack name (e.g., secure-agentcore-app): " STACK_NAME

if [ -z "$STACK_NAME" ]; then
    echo -e "${RED}Error: Stack name is required${NC}"
    exit 1
fi

# Get API URL
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text 2>/dev/null)

if [ -z "$API_URL" ] || [ "$API_URL" == "None" ]; then
    echo -e "${RED}Error: Could not find API URL in stack outputs${NC}"
    echo "Make sure your stack has an 'ApiUrl' output"
    exit 1
fi

echo -e "${GREEN}✓ API URL found: $API_URL${NC}"
echo ""

# Step 2: Get or generate Azure tokens
echo -e "${YELLOW}Step 2: Getting Azure authentication tokens...${NC}"
echo ""

# Check if user already has a token
if [ -n "$AZURE_TOKEN" ]; then
    echo -e "${GREEN}✓ Using AZURE_TOKEN from environment${NC}"
    
    # Clean the token - JWT tokens should have no whitespace at all
    AZURE_TOKEN=$(echo -n "$AZURE_TOKEN" | tr -d '[:space:]')
    
    echo "  Token length: ${#AZURE_TOKEN} characters"
    echo "  Token prefix: ${AZURE_TOKEN:0:20}..."
    
    # Verify token format (JWT should have 3 parts separated by dots)
    TOKEN_PARTS=$(echo "$AZURE_TOKEN" | tr '.' '\n' | wc -l)
    echo "  Token parts (should be 3 for JWT): $TOKEN_PARTS"
    
    VALID_TOKEN="$AZURE_TOKEN"
    #echo "VALID_TOKEN=$VALID_TOKEN"
else
    echo "No AZURE_TOKEN found in environment."
    echo ""
    echo "You need a real Azure Entra ID token to test the API."
    echo ""
    echo "Options:"
    echo "1. Generate a new token using generate_azure_token.sh"
    echo "2. Use an existing token (paste it manually)"
    echo "3. Exit and set AZURE_TOKEN environment variable"
    echo ""
    read -p "Choose an option (1, 2, or 3): " TOKEN_OPTION
    
    case $TOKEN_OPTION in
        1)
            echo ""
            echo "Running Azure token generator..."
            if [ ! -f "tests/utils/generate_azure_token.sh" ]; then
                echo -e "${RED}Error: tests/utils/generate_azure_token.sh not found${NC}"
                exit 1
            fi
            
            # Run the token generator and capture output
            bash tests/utils/generate_azure_token.sh
            
            echo ""
            echo "After generating the token, please run this script again with:"
            echo "export AZURE_TOKEN=\"<your-token>\""
            echo "./tests/utils/test_api_live.sh"
            exit 0
            ;;
        2)
            echo ""
            read -p "Paste your Azure token: " VALID_TOKEN
            if [ -z "$VALID_TOKEN" ]; then
                echo -e "${RED}Error: Token cannot be empty${NC}"
                exit 1
            fi
            ;;
        3)
            echo ""
            echo "Please set your Azure token and run again:"
            echo "export AZURE_TOKEN=\"<your-token>\""
            echo "./tests/utils/test_api_live.sh"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            exit 1
            ;;
    esac
fi

# For testing unauthorized access, we'll use an invalid token
# In a real scenario, you'd need a token from a different user without permissions
UNAUTHORIZED_TOKEN="invalid-token-for-unauthorized-test"
EXPIRED_TOKEN="***REMOVED-FROM-HISTORY***"

echo -e "${GREEN}✓ Tokens ready for testing${NC}"
echo ""

# Helper function to run test
run_test() {
    local test_name="$1"
    local expected_code="$2"
    shift 2
    
    echo -n "Testing: $test_name ... "
    
    # Print the curl command for debugging (mask the token)
    # if [[ "$*" == *"Authorization"* ]]; then
    #     echo ""
    #     echo "  Command: curl -s -w \"\\n%{http_code}\" $@" | sed "s/${VALID_TOKEN}/[TOKEN-MASKED]/g"
    # fi
    
    # Run curl and capture response
    response=$(curl -s -w "\n%{http_code}" "$@" 2>/dev/null)
    code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$code" == "$expected_code" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $code)"
        ((PASSED++))
        if [ ! -z "$body" ] && [ "$body" != "{}" ]; then
            echo "  Response: $(echo "$body" | cut -c 1-100)..."
        fi
    else
        echo -e "${RED}✗ FAIL${NC} (Expected $expected_code, got $code)"
        ((FAILED++))
        if [ ! -z "$body" ]; then
            echo "  Response: $body"
        fi
        
        # For debugging: show the curl command (without full token)
        # if [[ "$*" == *"$VALID_TOKEN"* ]]; then
        #     echo "  Debug: Using valid token (length: ${#VALID_TOKEN})"
        #     echo "  Debug: Token first 50 chars: ${VALID_TOKEN:0:50}"
        #     echo "  Debug: Token last 50 chars: ${VALID_TOKEN: -50}"
        # fi
    fi
    echo ""
}

# Step 3: Run tests
echo -e "${YELLOW}Step 3: Running API tests...${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Debug: Show what we're sending
# echo -e "${BLUE}Debug: Testing Authorization header format${NC}"
# echo "Authorization header will be: Authorization: Bearer [token]"
# echo "Token starts with: ${VALID_TOKEN:0:30}..."
# echo ""

# Test 1: No authentication token 
run_test "No authentication token" "401" \
    -X GET "$API_URL"

# Test 2: Invalid token format
run_test "Invalid token format" "403" \
    -X GET "$API_URL" \
    -H "Authorization: Bearer invalid-token-12345"

# Test 3: Expired token
run_test "Expired token" "403" \
    -X GET "$API_URL" \
    -H "Authorization: Bearer $EXPIRED_TOKEN"

# Test 4: Unauthorized user (valid token, no permissions)
run_test "Unauthorized user" "403" \
    -X GET "$API_URL" \
    -H "Authorization: Bearer $UNAUTHORIZED_TOKEN"

# Test 5: Valid GET request
run_test "GET /orders (authorized)" "200" \
    -X GET "$API_URL" \
    -H "Authorization: Bearer ${VALID_TOKEN}"

# Test 6: Valid POST request
ORDER_ID="test-$(date +%s)"
run_test "POST /orders (authorized)" "201" \
    -X POST "$API_URL" \
    -H "Authorization: Bearer ${VALID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
        \"order_id\": \"$ORDER_ID\",
        \"order_date\": \"$(date +%Y-%m-%d)\",
        \"item_name\": \"Test Widget\",
        \"qty\": 10,
        \"status\": \"pending\"
    }"

# Test 7: Valid PUT request
run_test "PUT /orders (authorized)" "200" \
    -X PUT "$API_URL" \
    -H "Authorization: Bearer ${VALID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
        \"order_id\": \"$ORDER_ID\",
        \"status\": \"completed\"
    }"

# Test 8: GET specific order
run_test "GET /orders (verify created order)" "200" \
    -X GET "$API_URL" \
    -H "Authorization: Bearer $VALID_TOKEN"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    Test Results                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Total Tests: $((PASSED + FAILED))"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed! Your API is working correctly.${NC}"
    EXIT_CODE=0
else
    echo -e "${RED}✗ Some tests failed. Check the output above for details.${NC}"
    EXIT_CODE=1
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Manual Testing Commands               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo "You can now test manually using these commands:"
echo ""
echo -e "${YELLOW}# Set environment variables:${NC}"
echo "export API_URL=\"$API_URL\""
echo "export AZURE_TOKEN=\"$VALID_TOKEN\""
echo ""
echo -e "${YELLOW}# GET all orders:${NC}"
echo "curl -X GET \"\$API_URL/orders\" -H \"Authorization: Bearer \$AZURE_TOKEN\" | jq"
echo ""
echo -e "${YELLOW}# POST new order:${NC}"
echo "curl -X POST \"\$API_URL/orders\" \\"
echo "  -H \"Authorization: Bearer \$AZURE_TOKEN\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"order_id\":\"ORD-001\",\"order_date\":\"2025-01-05\",\"item_name\":\"Widget\",\"qty\":5,\"status\":\"pending\"}' | jq"
echo ""
echo -e "${YELLOW}# PUT update order:${NC}"
echo "curl -X PUT \"\$API_URL/orders\" \\"
echo "  -H \"Authorization: Bearer \$AZURE_TOKEN\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"order_id\":\"ORD-001\",\"status\":\"completed\"}' | jq"
echo ""
echo -e "${YELLOW}# Generate a new Azure token:${NC}"
echo "./tests/utils/generate_azure_token.sh"
echo ""
echo -e "${YELLOW}# View CloudWatch logs:${NC}"
echo "aws logs tail /aws/lambda/\$(aws cloudformation describe-stack-resources --stack-name $STACK_NAME --logical-resource-id LambdaAuthorizer --query 'StackResources[0].PhysicalResourceId' --output text) --follow"
echo ""

exit $EXIT_CODE
