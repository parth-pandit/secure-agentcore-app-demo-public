#!/usr/bin/env python3
"""
Test AgentCore Memory — list sessions and events in us-east-1 and/or us-east-2.

Automatically discovers memory IDs from CloudFormation stack outputs.

Usage:
    python3 helper_scripts/test-memory.py                  # Both regions
    python3 helper_scripts/test-memory.py us-east-1        # Primary only
    python3 helper_scripts/test-memory.py us-east-2        # DR only
"""

import os
import sys

import boto3

SUFFIX = os.environ.get("SUFFIX", "redwood02")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PRIMARY_REGION = "us-east-1"
DR_REGION = "us-east-2"
STACK_NAME = f"{ENVIRONMENT}-agentcore-memory-{SUFFIX}"
DEFAULT_ACTOR = "ParthSalesUser-sevrenawsgmail-onmicrosoft-com"


def get_memory_id(region):
    cfn = boto3.client("cloudformation", region_name=region)
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        for output in resp["Stacks"][0].get("Outputs", []):
            if output["OutputKey"] == "MemoryId":
                # Extract just the ID from the ARN
                return output["OutputValue"].split("/")[-1]
    except Exception as e:
        print(f"  Could not get memory ID for {region}: {e}")
    return None


def list_memory(region, memory_id):
    client = boto3.client("bedrock-agentcore", region_name=region)

    print(f"\n{'='*60}")
    print(f"  Memory: {memory_id}")
    print(f"  Region: {region}")
    print(f"{'='*60}")

    for actor_id in [DEFAULT_ACTOR]:
        try:
            resp = client.list_sessions(
                memoryId=memory_id,
                actorId=actor_id,
                maxResults=10,
            )
            sessions = resp.get("sessionSummaries", [])
            print(f"\n  Actor: {actor_id}")
            print(f"  Sessions: {len(sessions)}")

            if not sessions:
                print("  (no sessions found)")
                continue

            for sess in sessions:
                sid = sess.get("sessionId", "?")
                created = str(sess.get("createdAt", ""))[:19]
                print(f"\n    Session: {sid}")
                print(f"    Created: {created}")

                try:
                    ev_resp = client.list_events(
                        memoryId=memory_id,
                        actorId=actor_id,
                        sessionId=sid,
                        includePayloads=True,
                        maxResults=5,
                    )
                    events = ev_resp.get("events", [])
                    print(f"    Events: {len(events)}")
                    for ev in events[:3]:
                        for msg in ev.get("payload", []):
                            conv = msg.get("conversational", {})
                            role = conv.get("role", "")
                            text = conv.get("content", {}).get("text", "")[:120]
                            if text:
                                prefix = "U" if role == "USER" else "A"
                                print(f"      [{prefix}] {text}")
                except Exception as e:
                    print(f"    Error listing events: {e}")

        except Exception as e:
            print(f"  Error for actor {actor_id}: {e}")

    print()


def main():
    regions = [PRIMARY_REGION, DR_REGION]

    if len(sys.argv) > 1:
        if sys.argv[1] in (PRIMARY_REGION, DR_REGION):
            regions = [sys.argv[1]]
        else:
            print(f"Unknown region: {sys.argv[1]}. Use: {PRIMARY_REGION} or {DR_REGION}")
            sys.exit(1)

    print(f"\n  AgentCore Memory Test (suffix={SUFFIX})")
    print(f"  Stack: {STACK_NAME}")

    for region in regions:
        memory_id = get_memory_id(region)
        if memory_id:
            list_memory(region, memory_id)
        else:
            print(f"\n  No memory found in {region}")

    print("Done.\n")


if __name__ == "__main__":
    main()
