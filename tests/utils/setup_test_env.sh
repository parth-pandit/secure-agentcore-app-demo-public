#!/bin/bash
# setup_test_env.sh - Set up environment variables for API testing

set -e

echo "🔧 Setting up test environment..."
echo ""

# Step 1: Get API URL from CloudFormation
echo "Step 1: Finding your CloudFormation stack..."
echo ""
echo "Available stacks with 'orders' or 'api' in the name:"
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `orders`) || contains(StackName, `api`)].StackName' \
  --output table

echo ""
read -p "Enter your stack name: " STACK_NAME

if [ -z "$STACK_NAME" ]; then
    echo "❌ Error: Stack name is required"
    exit 1
fi

# Get API URL
echo ""
echo "Getting API URL from stack: $STACK_NAME"
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text 2>/dev/null)

if [ -z "$API_URL" ] || [ "$API_URL" == "None" ]; then
    echo "❌ Error: Could not find API URL in stack outputs"
    exit 1
fi

echo "✅ API URL: $API_URL"

# Step 2: Generate test token
echo ""
echo "Step 2: Generating test token..."

# Check if we're in the right directory
if [ ! -f "token_generator.py" ]; then
    echo "❌ Error: token_generator.py not found"
    echo "Please run this script from tests/utils directory"
    exit 1
fi

TOKEN=$(python3 -c "
from token_generator import MockTokenGenerator
gen = MockTokenGenerator()
print(gen.generate_token('user@example.com'))
" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Error: Failed to generate token"
    exit 1
fi

echo "✅ Token generated successfully"

# Step 3: Export variables
echo ""
echo "Step 3: Exporting environment variables..."
echo ""

# Create a file to source
cat > .test_env << EOF
# Source this file to set up your test environment
# Usage: source tests/utils/.test_env

export API_URL="$API_URL"
export TOKEN="$TOKEN"
export STACK_NAME="$STACK_NAME"

echo "✅ Environment variables set:"
echo "   API_URL: \$API_URL"
echo "   TOKEN: \${TOKEN:0:50}..."
echo "   STACK_NAME: \$STACK_NAME"
echo ""
echo "You can now run:"
echo "   curl -X GET \"\$API_URL/orders\" -H \"Authorization: Bearer \$TOKEN\" | jq"
EOF

echo "✅ Environment file created: tests/utils/.test_env"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "To use these variables in your current shell, run:"
echo ""
echo "    source tests/utils/.test_env"
echo ""
echo "Then you can test your API with:"
echo ""
echo "    curl -X GET \"\$API_URL/orders\" -H \"Authorization: Bearer \$TOKEN\" | jq"
echo ""
