"""
Lambda: Short-Term Memory Cross-Region Replicator

Triggered by SQS (subscribed to SNS) when the self-managed strategy fires.
Reads the conversation payload from S3 and replays the events into the DR
memory using create_event().

Environment Variables:
  DR_REGION:     Target DR region (e.g., us-east-2)
  DR_MEMORY_ID:  Memory ID in the DR region
  S3_BUCKET:     Bucket where AgentCore delivers payloads
  DLQ_URL:       SQS DLQ URL for failed records (optional)
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DR_REGION = os.environ.get("DR_REGION", "us-east-2")
DR_MEMORY_ID = os.environ["DR_MEMORY_ID"]
S3_BUCKET = os.environ.get("S3_BUCKET", "")
DLQ_URL = os.environ.get("DLQ_URL", "")

# Clients
s3 = boto3.client("s3")
dr_data = boto3.client("bedrock-agentcore", region_name=DR_REGION)
sqs = boto3.client("sqs") if DLQ_URL else None


def send_to_dlq(record, error):
    if not sqs or not DLQ_URL:
        return
    try:
        sqs.send_message(
            QueueUrl=DLQ_URL,
            MessageBody=json.dumps({"record": record, "error": str(error),
                                     "ts": datetime.now(timezone.utc).isoformat()}),
        )
    except Exception as e:
        logger.error(f"DLQ send failed: {e}")


def process_payload(payload: dict) -> dict:
    """
    Process a self-managed strategy payload and replay events to DR.

    Payload structure (from AgentCore):
    {
      "requestId": "...",
      "accountId": "...",
      "memoryId": "...",
      "actorId": "...",
      "sessionId": "...",
      "strategyId": "...",
      "startingTimestamp": epoch_ms,
      "endingTimestamp": epoch_ms,
      "currentContext": [
        {"role": "USER", "content": {"text": "..."}},
        {"role": "ASSISTANT", "content": {"text": "..."}},
      ],
      "historicalContext": [...]
    }
    """
    actor_id = payload.get("actorId", "")
    session_id = payload.get("sessionId", "")
    current_context = payload.get("currentContext", [])

    if not actor_id or not session_id:
        logger.warning("Missing actorId or sessionId in payload")
        return {"status": "skipped", "reason": "missing_ids"}

    if not current_context:
        logger.info(f"Empty currentContext for {actor_id}/{session_id}")
        return {"status": "skipped", "reason": "empty_context"}

    # Build the event payload in the format create_event expects
    event_payload = []
    for msg in current_context:
        role = msg.get("role", "USER")
        content = msg.get("content", {})
        text = content.get("text", "")
        if text:
            event_payload.append({
                "conversational": {
                    "content": {"text": text},
                    "role": role,
                }
            })

    if not event_payload:
        return {"status": "skipped", "reason": "no_text_content"}

    # Replay to DR memory
    try:
        ending_ts = payload.get("endingTimestamp")
        event_ts = datetime.fromtimestamp(ending_ts / 1000, tz=timezone.utc) if ending_ts else datetime.now(timezone.utc)

        dr_data.create_event(
            memoryId=DR_MEMORY_ID,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=event_ts,
            payload=event_payload,
        )
        logger.info(f"✓ Replicated {len(event_payload)} messages for {actor_id}/{session_id} to DR")
        return {"status": "success", "messages": len(event_payload), "actor": actor_id, "session": session_id}

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "ConflictException":
            logger.info(f"Event already exists in DR for {actor_id}/{session_id} — skipping")
            return {"status": "skipped", "reason": "conflict/duplicate"}
        logger.error(f"Failed to replicate to DR: {e}")
        return {"status": "error", "error": str(e)}


def handler(event, context):
    """
    Lambda handler — triggered by SQS (subscribed to SNS topic).

    Each SQS message wraps an SNS notification containing:
    {
      "jobId": "...",
      "s3PayloadLocation": "s3://bucket/path/to/payload.json",
      "memoryId": "...",
      "strategyId": "..."
    }
    """
    records = event.get("Records", [])
    logger.info(f"Processing {len(records)} SQS record(s)")

    results = {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    for record in records:
        try:
            # Unwrap SQS → SNS → actual message
            body = json.loads(record.get("body", "{}"))
            sns_message = body.get("Message", body)
            if isinstance(sns_message, str):
                sns_message = json.loads(sns_message)

            s3_location = sns_message.get("s3PayloadLocation", "")
            if not s3_location:
                logger.warning("No s3PayloadLocation in message")
                results["skipped"] += 1
                continue

            # Parse s3://bucket/key
            s3_path = s3_location.replace("s3://", "")
            bucket = s3_path.split("/", 1)[0]
            key = s3_path.split("/", 1)[1] if "/" in s3_path else ""

            if not key:
                logger.warning(f"Could not parse S3 key from: {s3_location}")
                results["skipped"] += 1
                continue

            # Download payload from S3
            logger.info(f"Downloading payload: s3://{bucket}/{key}")
            resp = s3.get_object(Bucket=bucket, Key=key)
            payload = json.loads(resp["Body"].read().decode("utf-8"))

            results["processed"] += 1

            # Process and replicate
            result = process_payload(payload)
            if result["status"] == "success":
                results["succeeded"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["failed"] += 1
                send_to_dlq(payload, result.get("error", "unknown"))

        except Exception as e:
            logger.error(f"Error processing record: {e}", exc_info=True)
            results["failed"] += 1
            send_to_dlq(record, str(e))

    logger.info(f"Results: {json.dumps(results)}")
    return results
