#!/usr/bin/env python3
"""Enable log delivery for Gateway and Runtime."""

import boto3
import json

REGION = "us-east-1"
GATEWAY_ID = "dev-orders-gateway-redwood-syqyhqe3u0"
RUNTIME_ID = "dev_order_agent_runtime_redwood-r2Nu9HDiSB"

ac = boto3.client("bedrock-agentcore-control", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)

# Create log groups if they don't exist
for lg in [
    "/aws/bedrock-agentcore/gateway/dev-orders-gateway-redwood",
    "/aws/bedrock-agentcore/runtime/dev-order-agent-redwood",
]:
    try:
        logs.create_log_group(logGroupName=lg)
        print(f"Created log group: {lg}")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"Log group exists: {lg}")

# Enable Gateway log delivery
print("\n=== Enabling Gateway Log Delivery ===")
try:
    gw = ac.get_gateway(gatewayId=GATEWAY_ID)
    print(f"Gateway status: {gw['status']}")
    print(f"Gateway has logDelivery: {'logDeliveryConfig' in gw}")
    
    # Try update with log delivery
    # Check what params update_gateway accepts
    import inspect
    # Just try it
    resp = ac.update_gateway(
        gatewayId=GATEWAY_ID,
        logDeliveryConfig={
            "logConfigs": [
                {
                    "logType": "APPLICATION",
                    "destination": {
                        "cloudWatchLogGroup": {
                            "logGroupName": "/aws/bedrock-agentcore/gateway/dev-orders-gateway-redwood"
                        }
                    }
                }
            ]
        }
    )
    print(f"Gateway log delivery enabled: {resp.get('status', 'OK')}")
except Exception as e:
    print(f"Gateway log delivery failed: {e}")
    # Try alternative approach
    print("Trying alternative...")
    try:
        # Check available methods
        methods = [m for m in dir(ac) if "gateway" in m.lower() and "log" not in m.lower()]
        print(f"Available gateway methods: {methods}")
    except:
        pass

# Check runtime update params
print("\n=== Checking Runtime Update Params ===")
try:
    rt = ac.get_agent_runtime(agentRuntimeId=RUNTIME_ID)
    print(f"Runtime status: {rt['status']}")
    print(f"Runtime keys: {list(rt.keys())}")
    if "logDeliveryConfig" in rt:
        print(f"Current log config: {rt['logDeliveryConfig']}")
    else:
        print("No logDeliveryConfig in runtime response")
except Exception as e:
    print(f"Error: {e}")
