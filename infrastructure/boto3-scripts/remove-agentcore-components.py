# Import required libraries and generate a unique timestamp for naming resources.

import boto3
import argparse
import utils

print("✓ Libraries imported")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Remove AgentCore components')
parser.add_argument('--region', required=True, help='AWS Region')
parser.add_argument('--gateway-id', required=True, help='The ID of the AgentCore Gateway - e.g. gateway-authcode-20260118-000533-uuwttvr1sy')
parser.add_argument('--timestamp', required=True, help='The timestamp value at the end of the object - e.g. in object name gateway-authcode-20260118-000533 the timestamp is 20260118-000533')

args = parser.parse_args()

# Assign variables from arguments
REGION = args.region
GATEWAY_ID = args.gateway_id
TIMESTAMP = args.timestamp

print("✓ Configuration loaded from command-line arguments")

# Delete AgentCore Gateway and all targets
print("Step 1: Cleaning up AgentCore Gateway resources...")
agentcore_client = boto3.client('bedrock-agentcore-control', region_name=REGION)
agentcore_cleanup = utils.delete_gateway(
    gateway_client=agentcore_client,
    gatewayId=GATEWAY_ID
)

# Delete AgentCore Identity Credential Provider
print("\nStep 2: Cleaning up AgentCore Identity Credential Provider...")
credential_cleanup = agentcore_client.delete_oauth2_credential_provider(
    name=f'ac-gateway-mcp-server-identity-authcode-{TIMESTAMP}'
)

# Delete IAM Role
print("\nStep 3: Cleaning up IAM Role...")
iam_cleanup = utils.delete_iam_role(
    role_name=f'BedrockAgentCoreGatewayRole-{TIMESTAMP}'
)