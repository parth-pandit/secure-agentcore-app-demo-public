#!/usr/bin/env python3
"""Check Gateway target configuration and test connectivity."""

import boto3
import json

REGION = "us-east-1"
SUFFIX = "redwood"

ac = boto3.client("bedrock-agentcore-control", region_name=REGION)

# List gateways
print("=== Gateways ===")
gws = ac.list_gateways()
for gw in gws.get("gateways", []):
    gw_id = gw.get("gatewayId", "")
    print(f"  Gateway: {gw_id} | Status: {gw.get('status', '?')}")

print()
# Find our gateway
for gw in gws.get("gateways", []):
    gw_id = gw.get("gatewayId", "")
    if SUFFIX in gw_id or "orders" in gw_id:
        print(f"=== Target Details for {gw_id} ===")

        # List targets
        targets = ac.list_gateway_targets(gatewayId=gw_id)
        for t in targets.get("targets", []):
            t_id = t.get("targetId", "")
            print(f"  Target: {t_id}")
            print(f"  Status: {t.get('status', 'unknown')}")

            # Get target details
            td = ac.get_gateway_target(gatewayId=gw_id, targetId=t_id)
            print(f"  Endpoint Config:")
            print(f"    {json.dumps(td.get('endpointConfig', {}), indent=4)}")
            print(f"  Credential Providers:")
            creds = td.get("credentialProviderConfigurations", [])
            for c in creds:
                print(f"    {json.dumps(c, indent=4)}")
            print()

        # List credential providers
        print("=== OAuth2 Credential Providers ===")
        try:
            providers = ac.list_oauth2_credential_providers()
            for p in providers.get("oauth2CredentialProviders", []):
                if SUFFIX in p.get("name", ""):
                    print(f"  Name: {p['name']}")
                    print(f"  Status: {p.get('status', 'unknown')}")
                    detail = ac.get_oauth2_credential_provider(name=p["name"])
                    print(f"  Callback URL: {detail.get('callbackUrl', 'N/A')}")
                    print(f"  OAuth2 Type: {detail.get('oauth2Type', 'N/A')}")
                    print(f"  Token URL: {detail.get('tokenUrl', 'N/A')}")
                    print(f"  Auth URL: {detail.get('authorizationUrl', 'N/A')}")
                    print(f"  Scopes: {detail.get('scopes', [])}")
                    print()
        except Exception as e:
            print(f"  Error listing providers: {e}")
