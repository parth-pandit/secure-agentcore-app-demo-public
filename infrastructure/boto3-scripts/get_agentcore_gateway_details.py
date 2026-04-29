import subprocess
import json
import os

# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION environment variable to use a different region
region = os.getenv('AWS_REGION', 'us-west-2')
gateway_id = 'gateway-authcode-20260214-185600-kcstiheexs'

def run_aws_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {'error': result.stderr.strip()}

gateway_details = {}

# Get gateway
gateway_details['gateway'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'get-gateway',
    '--gateway-id', gateway_id, '--region', region, '--output', 'json'
])

# Get gateway targets
targets_response = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'list-gateway-targets',
    '--gateway-id', gateway_id, '--region', region, '--output', 'json'
])
gateway_details['gateway_targets'] = targets_response

# Get detailed info for each target
if 'items' in targets_response:
    gateway_details['gateway_targets_details'] = []
    for target in targets_response['items']:
        target_detail = run_aws_command([
            'aws', 'bedrock-agentcore-control', 'get-gateway-target',
            '--gateway-id', gateway_id,
            '--target-id', target['targetId'],
            '--region', region, '--output', 'json'
        ])
        gateway_details['gateway_targets_details'].append(target_detail)

# Get workload identity
if 'workloadIdentityDetails' in gateway_details['gateway']:
    workload_id = gateway_details['gateway']['workloadIdentityDetails']['workloadIdentityArn'].split('/')[-1]
    gateway_details['workload_identity'] = run_aws_command([
        'aws', 'bedrock-agentcore-control', 'get-workload-identity',
        '--name', workload_id, '--region', region, '--output', 'json'
    ])

print(json.dumps(gateway_details, indent=2, default=str))
