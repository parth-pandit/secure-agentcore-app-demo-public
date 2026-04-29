#!/bin/bash

# Script to generate Azure Entra ID access token for testing
# Usage: ./generate_azure_token.sh

set -e

# Token cache file location
TOKEN_CACHE_FILE="${HOME}/.azure_token_cache"

echo "=========================================="
echo "Azure Entra ID Token Generator"
echo "=========================================="
echo ""

# Function to save token to cache file
save_token_to_cache() {
    local token="$1"
    # Remove any whitespace/newlines (JWT tokens should not have spaces)
    token=$(echo -n "$token" | tr -d '[:space:]')
    echo "export AZURE_TOKEN=\"$token\"" > "$TOKEN_CACHE_FILE"
    chmod 600 "$TOKEN_CACHE_FILE"  # Secure the file
}

# Function to load token from cache file
load_token_from_cache() {
    if [ -f "$TOKEN_CACHE_FILE" ]; then
        source "$TOKEN_CACHE_FILE"
        # Trim any whitespace from the loaded token (JWT should have no spaces)
        AZURE_TOKEN=$(echo -n "$AZURE_TOKEN" | tr -d '[:space:]')
        export AZURE_TOKEN
    fi
}

# Function to decode JWT token and extract principal
extract_principal_from_token() {
    local token="$1"
    
    # Extract payload (second part of JWT)
    local payload=$(echo "$token" | cut -d'.' -f2)
    
    # Add padding if needed for base64 decoding
    local padded_payload="$payload"
    while [ $((${#padded_payload} % 4)) -ne 0 ]; do
        padded_payload="${padded_payload}="
    done
    
    # Decode base64 and extract principal fields
    local decoded=$(echo "$padded_payload" | base64 -d 2>/dev/null || echo "{}")
    
    # Try to extract various principal identifiers
    local upn=$(echo "$decoded" | jq -r '.upn // empty' 2>/dev/null)
    local email=$(echo "$decoded" | jq -r '.email // empty' 2>/dev/null)
    local name=$(echo "$decoded" | jq -r '.name // empty' 2>/dev/null)
    local appid=$(echo "$decoded" | jq -r '.appid // empty' 2>/dev/null)
    local oid=$(echo "$decoded" | jq -r '.oid // empty' 2>/dev/null)
    
    # Return the first available identifier
    if [ -n "$upn" ]; then
        echo "$upn"
    elif [ -n "$email" ]; then
        echo "$email"
    elif [ -n "$name" ]; then
        echo "$name"
    elif [ -n "$appid" ]; then
        echo "App ID: $appid"
    elif [ -n "$oid" ]; then
        echo "Object ID: $oid"
    else
        echo "Unknown principal"
    fi
}

# Function to check if token is expired
is_token_valid() {
    local token="$1"
    
    # Extract payload (second part of JWT)
    local payload=$(echo "$token" | cut -d'.' -f2)
    
    # Add padding if needed for base64 decoding
    local padded_payload="$payload"
    while [ $((${#padded_payload} % 4)) -ne 0 ]; do
        padded_payload="${padded_payload}="
    done
    
    # Decode base64 and extract expiration
    local decoded=$(echo "$padded_payload" | base64 -d 2>/dev/null || echo "{}")
    local exp=$(echo "$decoded" | jq -r '.exp // empty' 2>/dev/null)
    
    if [ -z "$exp" ] || [ "$exp" == "null" ]; then
        return 1
    fi
    
    # Get current timestamp
    local now=$(date +%s)
    
    # Check if token is still valid (with 5 minute buffer)
    if [ "$exp" -gt $((now + 300)) ]; then
        return 0
    else
        return 1
    fi
}

# Check if there's an existing token in the environment or cache
load_token_from_cache

if [ -n "$AZURE_TOKEN" ]; then
    echo "Found existing AZURE_TOKEN"
    echo ""
    
    # Check if token is valid
    if is_token_valid "$AZURE_TOKEN"; then
        # Extract principal
        PRINCIPAL=$(extract_principal_from_token "$AZURE_TOKEN")
        
        echo "✅ Token is still valid"
        echo "Principal: $PRINCIPAL"
        echo ""
        
        read -p "Do you want to use the existing valid token? (y/n): " USE_EXISTING
        
        if [[ "$USE_EXISTING" =~ ^[Yy]$ ]]; then
            echo ""
            echo "Using existing token..."
            echo ""
            
            # Ensure token is exported for child process
            export AZURE_TOKEN
            
            # Check if test script exists
            if [ -f "tests/utils/test_api_live.sh" ]; then
                bash tests/utils/test_api_live.sh
                exit 0
            else
                echo "❌ Error: tests/utils/test_api_live.sh not found"
                echo "Please make sure you're running this script from the project root directory"
                exit 1
            fi
        else
            echo ""
            echo "Generating a new token..."
            echo ""
        fi
    else
        echo "⚠️  Existing token has expired or is invalid"
        echo "Generating a new token..."
        echo ""
    fi
fi

# Azure configuration from the diagnostic results
read -p "Enter your Azure Tenant ID: " TENANT_ID

if [ -z "$TENANT_ID" ]; then
    echo "❌ Tenant ID is required"
    exit 1
fi

echo "This script will help you generate an Azure Entra ID access token."
echo "You have several options:"
echo ""
echo "1. Client Credentials Flow (requires client secret)"
echo "2. Device Code Flow (interactive browser authentication)"
echo "3. Azure CLI (if you have Azure CLI installed)"
echo ""

read -p "Choose an option (1, 2, or 3): " OPTION

case $OPTION in
    1)
        echo ""
        echo "Client Credentials Flow"
        echo "======================="
        echo ""
        echo "You need:"
        echo "- Azure Application (Client) ID"
        echo "- Azure Client Secret"
        echo ""
        
        read -p "Enter your Azure Application ID: " CLIENT_ID
        read -s -p "Enter your Azure Client Secret: " CLIENT_SECRET
        echo ""
        
        if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
            echo "❌ Both Client ID and Client Secret are required"
            exit 1
        fi
        
        echo ""
        echo "Getting token using client credentials..."
        
        RESPONSE=$(curl -s -X POST "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "grant_type=client_credentials" \
            -d "client_id=$CLIENT_ID" \
            -d "client_secret=$CLIENT_SECRET" \
            -d "scope=$CLIENT_ID/.default")
        
        ACCESS_TOKEN=$(echo $RESPONSE | jq -r '.access_token // empty')
        
        if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
            echo "✅ Token obtained successfully!"
            echo ""
            echo "Azure Access Token:"
            echo "$ACCESS_TOKEN"
            echo ""
            
            # Save token to cache file
            save_token_to_cache "$ACCESS_TOKEN"
            echo "✅ Token saved to cache file: $TOKEN_CACHE_FILE"
            echo ""
            echo "Export command:"
            echo "export AZURE_TOKEN=\"$ACCESS_TOKEN\""
        else
            echo "❌ Failed to get token"
            echo "Response: $RESPONSE"
            exit 1
        fi
        ;;
        
    2)
        echo ""
        echo "Device Code Flow"
        echo "================"
        echo ""
        
        read -p "Enter your Azure Application ID: " CLIENT_ID
        
        if [ -z "$CLIENT_ID" ]; then
            echo "❌ Application ID is required"
            exit 1
        fi
        
        echo ""
        echo "Starting device code flow..."
        
        # Request device code
        DEVICE_RESPONSE=$(curl -s -X POST "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/devicecode" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "client_id=$CLIENT_ID" \
            -d "scope=$CLIENT_ID/.default")
        
        USER_CODE=$(echo $DEVICE_RESPONSE | jq -r '.user_code')
        DEVICE_CODE=$(echo $DEVICE_RESPONSE | jq -r '.device_code')
        VERIFICATION_URI=$(echo $DEVICE_RESPONSE | jq -r '.verification_uri')
        
        if [ -z "$USER_CODE" ] || [ "$USER_CODE" == "null" ]; then
            echo "❌ Failed to get device code"
            echo "Response: $DEVICE_RESPONSE"
            exit 1
        fi
        
        echo ""
        echo "=========================================="
        echo "USER ACTION REQUIRED"
        echo "=========================================="
        echo ""
        echo "1. Open this URL in your browser:"
        echo "   $VERIFICATION_URI"
        echo ""
        echo "2. Enter this code:"
        echo "   $USER_CODE"
        echo ""
        echo "3. Sign in with your Azure account"
        echo ""
        echo "Waiting for authentication..."
        
        # Poll for token
        for i in {1..30}; do
            sleep 5
            
            TOKEN_RESPONSE=$(curl -s -X POST "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" \
                -H "Content-Type: application/x-www-form-urlencoded" \
                -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
                -d "client_id=$CLIENT_ID" \
                -d "device_code=$DEVICE_CODE")
            
            ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token // empty')
            
            if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
                echo ""
                echo "✅ Authentication successful!"
                echo ""
                echo "Azure Access Token:"
                echo "$ACCESS_TOKEN"
                echo ""
                
                # Save token to cache file
                save_token_to_cache "$ACCESS_TOKEN"
                echo "✅ Token saved to cache file: $TOKEN_CACHE_FILE"
                echo ""
                echo "Export command:"
                echo "export AZURE_TOKEN=\"$ACCESS_TOKEN\""
                break
            fi
            
            ERROR=$(echo $TOKEN_RESPONSE | jq -r '.error // empty')
            if [ "$ERROR" != "authorization_pending" ] && [ -n "$ERROR" ]; then
                echo ""
                echo "❌ Authentication failed: $ERROR"
                echo "Response: $TOKEN_RESPONSE"
                exit 1
            fi
            
            echo -n "."
        done
        
        if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" == "null" ]; then
            echo ""
            echo "❌ Authentication timed out"
            exit 1
        fi
        ;;
        
    3)
        echo ""
        echo "Azure CLI Method"
        echo "================"
        echo ""
        
        if ! command -v az &> /dev/null; then
            echo "❌ Azure CLI is not installed"
            echo "Install it from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
            exit 1
        fi
        
        read -p "Enter your Azure Application ID: " CLIENT_ID
        
        if [ -z "$CLIENT_ID" ]; then
            echo "❌ Application ID is required"
            exit 1
        fi
        
        echo ""
        echo "Getting token using Azure CLI..."
        
        # Login if not already logged in
        if ! az account show &> /dev/null; then
            echo "Please login to Azure CLI first:"
            az login
        fi
        
        ACCESS_TOKEN=$(az account get-access-token --resource "$CLIENT_ID" --query accessToken --output tsv)
        
        if [ -n "$ACCESS_TOKEN" ]; then
            echo "✅ Token obtained successfully!"
            echo ""
            echo "Azure Access Token:"
            echo "$ACCESS_TOKEN"
            echo ""
            
            # Save token to cache file
            save_token_to_cache "$ACCESS_TOKEN"
            echo "✅ Token saved to cache file: $TOKEN_CACHE_FILE"
            echo ""
            echo "Export command:"
            echo "export AZURE_TOKEN=\"$ACCESS_TOKEN\""
        else
            echo "❌ Failed to get token using Azure CLI"
            exit 1
        fi
        ;;
        
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "1. Export the token:"
echo "   export AZURE_TOKEN=\"[token-from-above]\""
echo ""
echo "2. Test API with the token:"
echo "   curl -X GET \\"
echo "     'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders' \\"
echo "     -H 'Authorization: Bearer \$AZURE_TOKEN'"
echo ""
echo "3. Use in tests:"
echo "   export TEST_TOKEN=\"\$AZURE_TOKEN\""
echo "   ./tests/utils/test_api_live.sh"
echo ""
echo "=========================================="
echo ""
read -p "Do you want to run test_api_live.sh now? (y/n): " RUN_TESTS

if [[ "$RUN_TESTS" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Exporting token and running test_api_live.sh..."
    echo ""
    
    # Export the token (load from cache to ensure it's available)
    export AZURE_TOKEN="$ACCESS_TOKEN"
    
    # Also save to cache if not already saved
    save_token_to_cache "$ACCESS_TOKEN"
    
    # Check if test script exists
    if [ -f "tests/utils/test_api_live.sh" ]; then
        bash tests/utils/test_api_live.sh
    else
        echo "❌ Error: tests/utils/test_api_live.sh not found"
        echo "Please make sure you're running this script from the project root directory"
        exit 1
    fi
else
    echo ""
    echo "Skipping test execution."
    echo ""
    echo "The token has been saved to: $TOKEN_CACHE_FILE"
    echo "It will be automatically loaded on the next run of this script."
    echo ""
    echo "To use the token in your current shell, run:"
    echo "source $TOKEN_CACHE_FILE"
    echo ""
    echo "Or manually export it:"
    echo "export AZURE_TOKEN=\"$ACCESS_TOKEN\""
    echo ""
    echo "Then run tests with:"
    echo "./tests/utils/test_api_live.sh"
fi
