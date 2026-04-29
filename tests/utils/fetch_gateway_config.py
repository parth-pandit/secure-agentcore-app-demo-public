#!/usr/bin/env python3
import boto3
import json
import sys

import os

gateway_id = 'gateway-authcode-20260121-152301-agcq9jti7p'
# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION environment variable to use a different region
region = os.getenv('AWS_REGION', 'us-west-2')
known_target_id = 'T2AJMK3VHE'  # From previous configuration

try:
    client = boto3.client('bedrock-agentcore-control', region_name=region)
    
    # Get gateway configuration
    gateway_response = client.get_gateway(gatewayIdentifier=gateway_id)
    print(f"✓ Gateway configuration fetched")
    
    # List all targets for this gateway
    try:
        targets_response = client.list_gateway_targets(gatewayIdentifier=gateway_id)
        print(f"DEBUG: list_gateway_targets response: {json.dumps(targets_response, indent=2, default=str)}")
        
        targets_list = targets_response.get('targets', [])
        print(f"✓ Found {len(targets_list)} target(s) from list")
        
        # Fetch detailed configuration for each target
        targets_details = []
        for target_summary in targets_list:
            target_id = target_summary.get('targetId')
            if target_id:
                print(f"  Fetching details for target: {target_id}")
                target_detail = client.get_gateway_target(
                    gatewayIdentifier=gateway_id,
                    targetId=target_id
                )
                targets_details.append(target_detail)
        
        # If no targets found in list, try the known target ID directly
        if not targets_details and known_target_id:
            print(f"\n  Trying known target ID: {known_target_id}")
            try:
                target_detail = client.get_gateway_target(
                    gatewayIdentifier=gateway_id,
                    targetId=known_target_id
                )
                targets_details.append(target_detail)
                print(f"✓ Successfully fetched known target")
            except Exception as e:
                print(f"⚠ Could not fetch known target: {e}")
        
        if targets_details:
            gateway_response['targets'] = targets_details
            print(f"✓ Total {len(targets_details)} target configuration(s) fetched")
        
    except Exception as e:
        print(f"⚠ Warning: Could not fetch target details: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    
    # Write to file
    with open('tests/integration/agentcore/temp/agentcore-gateway-config.json', 'w') as f:
        json.dump(gateway_response, f, indent=2, default=str)
    
    print(f"\n✓ Configuration saved to agentcore-gateway-config.json")
    
except Exception as e:
    print(f"✗ Error fetching gateway configuration: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
