# Import required libraries and generate a unique timestamp for naming resources.

import boto3
import json
import time
import zipfile
import io
import os
import sys
import requests
import argparse
from botocore.exceptions import ClientError
from datetime import datetime

print("✓ Libraries imported")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Deploy AgentCore components')
parser.add_argument('--region', required=True, help='AWS Region')
parser.add_argument('--idp-discovery-url', required=True, help='Identity Provider Discovery URL')
parser.add_argument('--agent-idp-client-id', required=True, help='Access requesting client ID from the identity provider config - e.g. AgentCore Runtime app requesting inbound access to the AgentCore Gateway')
parser.add_argument('--gateway-idp-client-id', required=True, help='The client ID from the identity provider config for the gateway app - e.g. The client ID of the AgentCore Gateway from the identity provider app config')
parser.add_argument('--target-idp-client-id', required=True, help='Target resource client ID from the identity provider config - e.g. Orders API target for the outbound access from the AgentCore Gateway')
parser.add_argument('--target-idp-client-secret', required=True, help='Client secret to access the target resource from the identity provider config - e.g. The client secret generated in the Orders API app in the identity provider that can be used by AgentCore Gateway for outbound access of the target resources')
parser.add_argument('--target-idp-tenant-id', required=True, help='Target tenant ID from the identity provider config - e.g. the common tenant ID at the domain level in the identity provider config')
parser.add_argument('--oauth2-callback-server-endpoint', required=True, help='Configures default return URL for the credential provider configuration in AgentCore Gateway target')
parser.add_argument('--s3-account', required=True, help='AWS account of the S3 OpenAPI schema object')
parser.add_argument('--s3-uri', required=True, help='S3 object URI for the OpenAPI schema file')

args = parser.parse_args()

# Assign variables from arguments
REGION = args.region
IDP_DISCOVERY_URL = args.idp_discovery_url
AGENT_IDP_CLIENT_ID = args.agent_idp_client_id
GATEWAY_IDP_CLIENT_ID = args.gateway_idp_client_id
TARGET_IDP_CLIENT_ID = args.target_idp_client_id
TARGET_IDP_CLIENT_SECRET = args.target_idp_client_secret
TARGET_IDP_TENANT_ID = args.target_idp_tenant_id
OAUTH2_CALLBACK_SERVER_ENDPOINT = args.oauth2-callback-server-endpoint
S3_ACCOUNT = args.s3_account
S3_URI_OPEN_API_SCHEMA = args.s3_uri

print("✓ Configuration loaded from command-line arguments")

# Generate timestamp for unique naming
timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
print(f"Using timestamp: {timestamp}")

gateway_target_name = f"mcp-target-{timestamp}"

# Now import utils
import utils

# Setup logging 
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

logging.getLogger("strands").setLevel(logging.INFO)

print("✓ Logging configured, utils imported")

target_cred_provider_name = f"ac-gateway-mcp-server-identity-authcode-{timestamp}"

identity_client = boto3.client('bedrock-agentcore-control', region_name=REGION)

print(f"Deleting the credential provider with name {target_cred_provider_name} if it exists already")
try:
    delete_resp = identity_client.delete_oauth2_credential_provider(name=target_cred_provider_name)
    print("Existing credential provider found and deleted. Proceeding with re-creation")
except ClientError as e:
    if e.response['Error']['Code'] == 'ResourceNotFound':
        print("Existing credential provider with same name does not exist. Proceeding with creation")
    else:
        raise Exception(f"Credential provider deletion failed: {e.response['Error']['Message']}")

microsoft_cred_provider = identity_client.create_oauth2_credential_provider(
    name=target_cred_provider_name,
    credentialProviderVendor="MicrosoftOauth2",
    oauth2ProviderConfigInput={
        'microsoftOauth2ProviderConfig': {
            'clientId': TARGET_IDP_CLIENT_ID,
            'clientSecret': TARGET_IDP_CLIENT_SECRET,
            'tenantId': TARGET_IDP_TENANT_ID
        }
    }
)

target_cred_provider_arn = microsoft_cred_provider['credentialProviderArn']
target_callback_url = microsoft_cred_provider['callbackUrl']
print("Outbound OAuth2 Credential Provider ARN:", target_cred_provider_arn)
print("Please register the following callback URL with your external identity provider:", target_callback_url)

def create_gateway_with_authcode():
    iam_client = boto3.client('iam', region_name=REGION)
    gateway_client = boto3.client('bedrock-agentcore-control', region_name=REGION)
    
    role_name = f'BedrockAgentCoreGatewayRole-{timestamp}'
    gateway_name = f"gateway-authcode-{timestamp}"
    
    # Create IAM role for Gateway
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        iam_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='IAM role for Bedrock Agent Core Gateway with 3LO'
        )

        role_arn = iam_response['Role']['Arn']
        print(f"Gateway IAM role created: {role_arn}")

        # Attach admin policy to the role
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'
        )
        print("Admin policy attached to Gateway IAM role")
    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            iam_response = iam_client.get_role(RoleName=role_name)
            role_arn = iam_response['Role']['Arn']
            print(f"IAM role already exists with Arn: {role_arn}. Using the same")
        else:
            raise Exception(f"IAM Role creation failed: {e.response['Error']['Message']}")

    print("Creating gateway with Auth Code grant...")
    gateway_response = gateway_client.create_gateway(
        name=gateway_name,
        protocolType="MCP",
        protocolConfiguration={
            "mcp": {
                "supportedVersions": ["2025-11-25", "2025-03-26"],
                "searchType": "SEMANTIC"
            }
        },
       authorizerType="CUSTOM_JWT",
       authorizerConfiguration={
            "customJWTAuthorizer": {
                "discoveryUrl": IDP_DISCOVERY_URL,
                # Disabling allowedClient configuration to reduce complexity
                # "allowedClients": [AGENT_IDP_CLIENT_ID],
                "allowedAudience": [GATEWAY_IDP_CLIENT_ID]
            }
       },
       roleArn=role_arn,
       exceptionLevel="DEBUG",
       tags={
            "created-by": "secure-agentcore-app-demo/infrastructure/boto3-scripts/deploy-agentcore-components.py",
            "owner": "Parth Pandit"
       }
    )

    print("Gateway create response:", gateway_response)

    gateway_id = gateway_response['gatewayId']
    gateway_url = gateway_response['gatewayUrl']
    print(f"Gateway with Auth code grant created: {gateway_id}")

    # Wait for gateway to be ready
    print("Waiting for gateway to be ready...")
    while True:
        status_response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)

        current_status = status_response['status']
        print(f"Gateway status: {current_status}")
        if current_status == 'READY':
            print(f"Final gateway details: {status_response}")
            break

        time.sleep(10)

    print("Gateway is now ready")
    return gateway_id, gateway_url, role_name

gateway_id, gateway_url, gateway_role_name = create_gateway_with_authcode()
print(f"\n✅ Gateway creation completed: Gateway Id {gateway_id}")
print(f"Gateway Url: {gateway_url}")

def create_order_api_target(gatewayId, provider_arn):
    gateway_client = boto3.client('bedrock-agentcore-control', region_name=REGION)
    credentialProviderConfig = {
        "credentialProviderType": "OAUTH",
        "credentialProvider": {
            "oauthCredentialProvider": {
                "providerArn": provider_arn,
                "grantType": "AUTHORIZATION_CODE",
                "defaultReturnUrl": OAUTH2_CALLBACK_SERVER_ENDPOINT,
                "scopes": [f"{TARGET_IDP_CLIENT_ID}/.default"]
            }
        }
    }
    target_config = {
        "mcp": {
            "openApiSchema": {
                "s3": {
                    "uri": S3_URI_OPEN_API_SCHEMA,
                    "bucketOwnerAccountId": S3_ACCOUNT
                },
            }
        }
    }
    try:
        response = gateway_client.create_gateway_target(
            name = "OrderApiAuthCode",
            description = "Target created for testing",
            credentialProviderConfigurations = [credentialProviderConfig],
            targetConfiguration= target_config,
            gatewayIdentifier=gatewayId
        )
        targetId = response["targetId"]
        print(f"Created Order API target {targetId} for gateway {gatewayId}")
        return targetId
    except Exception as e:
        print(e)


gateway_target_id = create_order_api_target(gatewayId=gateway_id,
                                           provider_arn=target_cred_provider_arn)
print(f"Gateway Target ID: {gateway_target_id}")