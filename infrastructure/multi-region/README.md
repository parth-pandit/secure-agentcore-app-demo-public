# Multi-Region Infrastructure (acore-redwood)

Multi-region active/standby components for Project Redwood.
Primary: us-east-1, DR/Standby: us-east-2.

---

## Memory (Short-Term with Cross-Region Replication)

### Architecture

```
Primary (us-east-1)                          DR (us-east-2)
┌─────────────────────┐                     ┌─────────────────────┐
│  AgentCore Memory   │                     │  AgentCore Memory   │
│  (self-managed      │                     │  (plain STM,        │
│   strategy)         │                     │   receives events)  │
└────────┬────────────┘                     └─────────────────────┘
         │ triggers after 4 msgs                       ▲
         │ or 30s idle                                 │
         ▼                                             │
┌─────────────────────┐                                │
│  S3 Payload Bucket  │                                │
│  (7-day lifecycle)  │                                │
└────────┬────────────┘                                │
         │                                             │
         ▼                                             │
┌─────────────────────┐                                │
│  SNS Topic          │                                │
└────────┬────────────┘                                │
         │                                             │
         ▼                                             │
┌─────────────────────┐                                │
│  SQS Queue          │──── DLQ (3 retries) ──→ DLQ   │
└────────┬────────────┘                                │
         │ batch: 5, window: 10s                       │
         ▼                                             │
┌─────────────────────┐                                │
│  Replicator Lambda  │────── create_event() ──────────┘
│  (reads S3 payload, │
│   replays to DR)    │
└─────────────────────┘
```

### Deploy Order

```bash
cd infrastructure/multi-region/memory

# 1. Deploy DR first (plain memory, no replication)
./deploy.sh us-east-2

# 2. Deploy Primary (memory + replication pipeline)
./deploy.sh us-east-1
```

DR must be deployed first because the primary's replication Lambda needs
the DR memory ID as a target.

### Files

| File | Purpose |
|------|---------|
| `cfn-memory.yaml` | Memory resource (primary w/ strategy, or DR plain) |
| `cfn-memory-replication.yaml` | Replication pipeline (S3 + SNS + SQS + Lambda) |
| `lambda/handler.py` | Replicator Lambda (reads S3, replays to DR) |
| `deploy.sh` | Region-aware deploy script |

### How It Works

1. Agent conversations are stored in primary memory (us-east-1)
2. After 4 messages or 30s idle, the self-managed strategy triggers
3. AgentCore exports conversation context to S3 as JSON
4. AgentCore publishes SNS notification with S3 location
5. SQS buffers the notification → Lambda processes in batches
6. Lambda downloads payload from S3, parses conversation
7. Lambda calls `create_event()` on DR memory (us-east-2)
8. Duplicate events are skipped (idempotent via ConflictException)
