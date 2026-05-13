import json
import os

import boto3

# AWS Region - defaults to us-east-1 if not set
# Set AWS_REGION environment variable to use a different region
REGION = os.getenv("AWS_REGION", "us-west-2")
RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN", "")
PROMPT = os.getenv("PROMPT", "Give me a short test response.")

if not RUNTIME_ARN:
    raise SystemExit("AGENT_RUNTIME_ARN is required")

client = boto3.client("bedrock-agentcore", region_name=REGION)

payload = json.dumps({"prompt": PROMPT}).encode("utf-8")

response = client.invoke_agent_runtime(
    agentRuntimeArn=RUNTIME_ARN,
    payload=payload,
    qualifier="DEFAULT",
)

body = response.get("response")
if hasattr(body, "read"):
    text = body.read().decode("utf-8")
else:
    text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)

try:
    parsed = json.loads(text)
    print(parsed.get("result") or parsed)
except json.JSONDecodeError:
    print(text)
