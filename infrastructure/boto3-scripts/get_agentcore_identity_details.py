import subprocess
import json
import os

# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION environment variable to use a different region
region = os.getenv('AWS_REGION', 'us-west-2')
provider_name = 'ac-gateway-mcp-server-identity-authcode-20260121-152301'

def run_aws_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {'error': result.stderr.strip()}

identity_details = {}

# Get OAuth2 credential provider
identity_details['oauth2_credential_provider'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'get-oauth2-credential-provider',
    '--name', provider_name, '--region', region, '--output', 'json'
])

print(json.dumps(identity_details, indent=2, default=str))
