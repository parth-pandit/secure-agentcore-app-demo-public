import subprocess
import argparse
import requests
import sys
import json
import base64
import boto3
from datetime import datetime
from oauth2_callback_server import store_token_in_oauth2_callback_server, wait_for_oauth2_server_to_be_ready, get_oauth2_callback_base_url

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Test MCP Client with 3-Legged OAuth')
parser.add_argument('--region', required=True, help='AWS Region')
parser.add_argument('--ac-gateway-idp-client-id', required=True, help='The client ID from the identity provider config for AgentCore Gateway')
parser.add_argument('--ac-gateway-idp-client-secret', required=True, help='The client secret from the identity provider config for AgentCore Gateway that will be used by the agent')
parser.add_argument('--ac-gateway-idp-tenant-id', required=True, help='The tenant ID from the identity provider config for AgentCore Gateway')
parser.add_argument('--ac-gateway-url', required=True, help='The URL for AgentCore Gateway')
parser.add_argument('--api-gateway-id', required=True, help='API Gateway ID')
parser.add_argument('--test-tools-list', default='n', help="Test 'tools/list' call (y/n, default: n)")
parser.add_argument('--force-authentication', default='n', help="Force re-authentication even if token is cached (y/n, default: n)")

args = parser.parse_args()

# Assign variables from arguments
REGION = args.region
AC_GATEWAY_IDP_CLIENT_ID = args.ac_gateway_idp_client_id
AC_GATEWAY_IDP_CLIENT_SECRET = args.ac_gateway_idp_client_secret
AC_GATEWAY_IDP_TENANT_ID = args.ac_gateway_idp_tenant_id
AC_GATEWAY_URL = args.ac_gateway_url
API_GATEWAY_ID = args.api_gateway_id


# Helper function to get token from Entra ID
def get_token(tenant_id: str, client_id: str, client_secret: str, scope_string: str, REGION: str) -> dict:
    try:
        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope_string,

        }
        print(client_id)
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as err:
        return {"error": str(err)}
 
# Helper function to make MCP calls
def invoke_mcp(gatewayUrl, access_token, tool_params, method = "tools/call", protocol_version = '2025-11-25'):

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'MCP-Protocol-Version': protocol_version
    }

    payload = {
        "jsonrpc": "2.0",
        "id": 24,
        "method": method,
        "params": tool_params
    }
    # print("------------- PAYLOAD --------------")
    # print(payload)
    try:
        response = requests.post(gatewayUrl, headers=headers, json=payload)
        request_id = response.headers.get('x-amzn-requestid') or response.headers.get('x-amz-request-id')
        print("\nAmazon Request ID:", request_id)
        response.raise_for_status()
        print(f"Invoke MCP Status Code: {response.status_code}")
        print("Response:")
        #if method != "tools/list":
        print(json.dumps(response.json(), indent=2))
        return response.json()

    except requests.exceptions.RequestException as e:
        print("Error:", e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                print("Error Response:", json.dumps(e.response.json(), indent=2))
            except:
                print("Error Response Text:", e.response.text)
        raise


# full_scope = f"{RESOURCE_SERVER_ID}/{gateway_target_name}"
full_scope = f"{AC_GATEWAY_IDP_CLIENT_ID}/.default"
print(f"\nRequesting token with scope: {full_scope}")
jwt_token = get_token(tenant_id=AC_GATEWAY_IDP_TENANT_ID, 
                            client_id=AC_GATEWAY_IDP_CLIENT_ID, 
                            client_secret=AC_GATEWAY_IDP_CLIENT_SECRET, 
                            scope_string=full_scope, 
                            REGION=REGION)

if 'error' in jwt_token:
    print(f"Error getting token: {jwt_token['error']}")
    sys.exit(1)

bearer_token = jwt_token['access_token']

# Decode and display token details for debugging
import base64
def decode_token(token):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        payload_encoded = parts[1]
        padding = 4 - (len(payload_encoded) % 4)
        if padding != 4:
            payload_encoded += '=' * padding
        payload_bytes = base64.urlsafe_b64decode(payload_encoded)
        return json.loads(payload_bytes.decode('utf-8'))
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None

# print("------------ BEARER TOKEN --------------")
# print(bearer_token)

# token_payload = decode_token(bearer_token)
# if token_payload:
#     print("\n=== Token Details ===")
#     print(f"Issuer (iss): {token_payload.get('iss', 'N/A')}")
#     print(f"Audience (aud): {token_payload.get('aud', 'N/A')}")
#     print(f"Subject (sub): {token_payload.get('sub', 'N/A')} [Service Principal Object ID]")
#     print(f"Object ID (oid): {token_payload.get('oid', 'N/A')} [Same as sub in v2.0]")
#     print(f"App ID (appid): {token_payload.get('appid', 'N/A')} [Client ID - USE FOR AUDIT]")
#     print(f"App ID (azp): {token_payload.get('azp', 'N/A')} [Alternative claim for Client ID]")
#     print(f"Tenant ID (tid): {token_payload.get('tid', 'N/A')}")
#     print(f"Token Version (ver): {token_payload.get('ver', 'N/A')}")
#     print(f"App Display Name (app_displayname): {token_payload.get('app_displayname', 'N/A')}")
#     print(f"Identity Provider (idp): {token_payload.get('idp', 'N/A')}")
#     print("=====================\n")
    
    # Audit logging example
    # print("=== Audit Information ===")
    # client_id = token_payload.get('appid') or token_payload.get('azp', 'Unknown')
    # service_principal_id = token_payload.get('sub') or token_payload.get('oid', 'Unknown')
    # tenant_id = token_payload.get('tid', 'Unknown')
    # app_name = token_payload.get('app_displayname', 'Unknown App')
    
    # print(f"Client Application: {app_name} (Client ID: {client_id})")
    # print(f"Service Principal: {service_principal_id}")
    # print(f"Tenant: {tenant_id}")
    # print("========================\n")

#Starting oAuth callback server
print("\n=== Starting OAuth2 Callback Server ===")

# Check if port 3021 is already in use
import socket
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

oauth2_callback_server_process = None

if is_port_in_use(3021):
    print("✓ OAuth2 callback server is already running on port 3021")
else:
    print("Starting new OAuth2 callback server on port 3021...")
    oauth2_callback_server_cmd = [sys.executable, "oauth2_callback_server.py", "--region", REGION]
    oauth2_callback_server_process = subprocess.Popen(oauth2_callback_server_cmd)
    
    successfully_started_oauth2_server = wait_for_oauth2_server_to_be_ready()
    if not successfully_started_oauth2_server:
        print("Failed to start OAuth2 callback server to handle session binding "
              "(https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/oauth2-authorization-url-session-binding.html)")
        if oauth2_callback_server_process:
            oauth2_callback_server_process.terminate()
        sys.exit(1)
    print("✓ OAuth2 callback server started successfully")

store_token_in_oauth2_callback_server(bearer_token)

# First, try listing tools to verify basic authentication works (optional)
test_tools_list = args.test_tools_list.lower() in ['y', 'yes']
if test_tools_list:
    print("\n=== TEST 1: List Tools (Basic Auth Check) ===")
    try:
        list_resp = invoke_mcp(gatewayUrl=AC_GATEWAY_URL, 
                    access_token=bearer_token,
                    tool_params={},
                    method="tools/list")
        print("✓ Basic authentication successful!")
    except Exception as e:
        print("✗ Basic authentication failed!")
        print("This suggests the token or gateway configuration has an issue.")
        raise
else:
    print("\n=== TEST 1: Skipped (tools/list) ===\n")

# Now try the actual tool call
print("\n=== TEST 2: Call Tool with OAuth ===")

CUSTOM_RETURN_URL = get_oauth2_callback_base_url() + "/oauth2/callback"
print(f"Using callback URL: {CUSTOM_RETURN_URL}")

# Convert y/n to boolean
force_auth = args.force_authentication.lower() in ['y', 'yes']

if force_auth:
    print("\nTesting with force authentication enabled")
else:
    print("\nTesting with force authentication disabled (will use cached token if available)")

_meta = {
    "aws.bedrock-agentcore.gateway/credentialProviderConfiguration": {
        "oauthCredentialProvider": {
            #"returnUrl": CUSTOM_RETURN_URL,
            "forceAuthentication": force_auth
        }
    }
}
# Invoking Get Order tool
resp = invoke_mcp(gatewayUrl=AC_GATEWAY_URL, 
            access_token=bearer_token,
            tool_params={
                "name": "OrderApiAuthCode___getOrders",
                "arguments": {
                    "environment": "dev",
                    "region": REGION,
                    "apiId": API_GATEWAY_ID
                },
                "_meta": _meta
            },
            method="tools/call")

# Invoking Update Order tool
new_order_date=str(int(datetime.now().timestamp()))
print(f"Updating the order for the new date value as {new_order_date}")
resp = invoke_mcp(gatewayUrl=AC_GATEWAY_URL, 
            access_token=bearer_token,
            tool_params={
                "name": "OrderApiAuthCode___updateOrder",
                "arguments": {
                    "environment": "dev",
                    "region":REGION,
                    "apiId": API_GATEWAY_ID,
                    "order_id": "order-123",
                    "order_date": new_order_date
                },
                "_meta": _meta
            },
            method="tools/call")

print("\n✓ Test completed successfully!")
print("Note: OAuth2 callback server is still running on port 3021")
print("To stop it, run: python stop_oauth2_server.py")
