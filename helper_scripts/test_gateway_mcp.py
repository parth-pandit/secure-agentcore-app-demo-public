#!/usr/bin/env python3
"""Test Gateway MCP tool call directly to diagnose tool failures."""

import boto3
import json
import httpx

REGION = "us-east-1"
SUFFIX = "redwood"
ENVIRONMENT = "dev"

# Get gateway secret
sm = boto3.client("secretsmanager", region_name=REGION)
secret = json.loads(sm.get_secret_value(SecretId=f"{ENVIRONMENT}-gateway-secret-{SUFFIX}")["SecretString"])

gateway_url = secret["gateway_mcp_url"]
tenant_id = secret["tenant_id"]
client_id = secret["client_id"]
client_secret = secret["client_secret"]

print(f"Gateway URL: {gateway_url}")
print(f"Tenant: {tenant_id}")
print(f"Client: {client_id}")
print()

# Get OAuth token (client credentials flow — for Gateway auth, not 3LO)
token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
token_resp = httpx.post(token_url, data={
    "grant_type": "client_credentials",
    "client_id": client_id,
    "client_secret": client_secret,
    "scope": f"{client_id}/.default",
}, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
token_resp.raise_for_status()
access_token = token_resp.json()["access_token"]
print(f"Got access token (first 20): {access_token[:20]}...")
print()

# Call tools/list
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-11-25",
}

print("=== tools/list ===")
list_resp = httpx.post(gateway_url, headers=headers, json={
    "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
}, timeout=15)
print(f"Status: {list_resp.status_code}")
list_data = list_resp.json()
tools = (list_data.get("result") or {}).get("tools") or []
print(f"Tools found: {len(tools)}")
for t in tools:
    print(f"  - {t['name']}")
print()

# Call getOrders (will likely need 3LO — expect elicitation error)
print("=== tools/call getOrders ===")
call_resp = httpx.post(gateway_url, headers=headers, json={
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {
        "name": f"{ENVIRONMENT}-orders-api-target-{SUFFIX}___getOrders",
        "arguments": {},
    }
}, timeout=20)
print(f"Status: {call_resp.status_code}")
print(f"Response: {json.dumps(call_resp.json(), indent=2)}")
