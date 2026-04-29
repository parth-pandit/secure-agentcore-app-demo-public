import subprocess
import json
import os

# AWS Region - defaults to us-west-2 if not set
# Set AWS_REGION environment variable to use a different region
region = os.getenv('AWS_REGION', 'us-west-2')
runtime_id = 'strands_sonnet45_west2-orA4CSAzQ0'

def run_aws_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {'error': result.stderr.strip()}

agent_details = {}

# Get agent runtime
agent_details['agent_runtime'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'get-agent-runtime',
    '--agent-runtime-id', runtime_id, '--region', region, '--output', 'json'
])

# Get agent runtime endpoints
agent_details['agent_runtime_endpoints'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'list-agent-runtime-endpoints',
    '--agent-runtime-id', runtime_id, '--region', region, '--output', 'json'
])

# Get workload identity if available
if 'workloadIdentityDetails' in agent_details['agent_runtime']:
    workload_id = agent_details['agent_runtime']['workloadIdentityDetails']['workloadIdentityArn'].split('/')[-1]
    agent_details['workload_identity'] = run_aws_command([
        'aws', 'bedrock-agentcore-control', 'get-workload-identity',
        '--workload-identity-id', workload_id, '--region', region, '--output', 'json'
    ])

# Get memory if configured
agent_details['memories'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'list-memories',
    '--agent-runtime-id', runtime_id, '--region', region, '--output', 'json'
])

# Get browsers if configured
agent_details['browsers'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'list-browsers',
    '--agent-runtime-id', runtime_id, '--region', region, '--output', 'json'
])

# Get code interpreters if configured
agent_details['code_interpreters'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'list-code-interpreters',
    '--agent-runtime-id', runtime_id, '--region', region, '--output', 'json'
])

# Get gateways if configured
agent_details['gateways'] = run_aws_command([
    'aws', 'bedrock-agentcore-control', 'list-gateways',
    '--agent-runtime-id', runtime_id, '--region', region, '--output', 'json'
])

print(json.dumps(agent_details, indent=2, default=str))
