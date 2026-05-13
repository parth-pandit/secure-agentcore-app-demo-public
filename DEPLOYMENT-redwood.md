# Deployment Guide — Project Redwood (Multi-Region)

---

## Prerequisites

- AWS CLI v2.34+ (`aws --version`)
- Python 3.9+ (system) and `uv` (`pip install uv`)
- Node.js 18+ (`node --version`)
- `zip` utility
- bash 3.2+ (macOS default is fine)
- AWS account with Bedrock AgentCore access in us-east-1 and us-east-2
- Azure Entra ID tenant with 3 app registrations (see original README)
- ARC routing control created (pre-requisite)

---

## Step 1: Configure

### 1a. Deployment config

```bash
cp infrastructure/deploy-config-multi-region.sh.template \
   infrastructure/deploy-config-multi-region.sh
```

Edit and set:
- `SUFFIX` — unique lowercase alphanumeric string (e.g., `redwood`). No hyphens, underscores, or special chars.
- `ARC_ROUTING_CONTROL_ARN` and `ARC_CLUSTER_ENDPOINTS`

### 1b. Parameters file

```bash
cp infrastructure/cloudformation/parameters/dev-parameters-multi-region.json.template \
   infrastructure/cloudformation/parameters/dev-parameters-multi-region.json
```

Fill in Azure Entra ID values (tenant ID, client IDs, secret, authorized users).

---

## Step 2: Deploy (Full — First Time)

```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh --update
```

The `--update` flag is required on first deploy to package and upload all artifacts.

Deploys everything in order:
1. S3 buckets (4 per-region, auto-created)
2. Memory DR (us-east-2) + Primary (us-east-1) + replication pipeline
3. Primary infrastructure (CFN: Backend API + DDB Global Table + AgentCore)
4. DR infrastructure (CFN: Backend API + AgentCore, no DDB create)
5. Lambda@Edge (ARC-based origin router, us-east-1, unique name per deploy)
6. Global stack (CloudFront + S3 frontend bucket)
7. Agent Runtime update (code + env vars, `OAUTH_FORCE_AUTH=false`)
8. Frontend deploy (builds config with `/api/invoke`, uploads to S3, invalidates CF)
9. Post-deploy: seeds DDB if empty, prints Azure Entra ID instructions

**Duration:** ~20-25 minutes first time.

---

## Step 3: Post-Deploy (One-Time)

The script prints these instructions after deploy:

1. **Gateway App Registration** → Authentication → Add Redirect URI:
   ```
   https://<cloudfront-domain>
   ```

2. **Orders API App Registration** → Authentication → Add BOTH Redirect URIs:
   ```
   https://bedrock-agentcore.us-east-1.amazonaws.com/identities/oauth2/callback/<provider-id>
   https://bedrock-agentcore.us-east-2.amazonaws.com/identities/oauth2/callback/<provider-id>
   ```

These callback URLs are fetched programmatically from the `get-oauth2-credential-provider` API.

---

## Deploy Modes

### Default (no `--update`): Create-if-missing — fast verification

```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh
```

- Checks all resources exist
- Runs CFN deploy (instant no-op if no template changes)
- Skips Lambda packaging, S3 uploads, code refreshes
- **Duration: ~2-3 minutes**

### With `--update`: Full rebuild + redeploy

```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh --update
```

- Repackages all Lambda functions
- Uploads to S3 (both regions)
- Force-updates Lambda function code
- Updates agent runtime (new version)
- Refreshes Gateway Target schema
- Rebuilds + redeploys frontend
- **Duration: ~15-20 minutes**

---

## Day-to-Day Updates

### Update agent runtime only (both regions, ~60s)
```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh --runtime --update
```

### Update frontend only (~30s)
```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh --frontend --update
```

### Update infrastructure (both regions, ~15 min)
```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh --infra --update
```

### Update memory only (~3 min)
```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh --memory
```

### Verify everything is healthy (fast, no changes)
```bash
bash infrastructure/scripts/deploy-stack-multi-region.sh
```

---

## Cleanup (Delete Everything)

```bash
bash infrastructure/scripts/cleanup-stack-multi-region.sh
```

- Always prompts for confirmation (type `DELETE`)
- Handles Lambda@Edge replica cleanup with retry loop (up to 5 min)
- Deletes all stacks, S3 buckets, and secrets in both regions
- If Lambda@Edge replicas haven't cleared, prints manual cleanup command

---

## Failover

### Failover to us-east-2
```bash
aws route53-recovery-cluster update-routing-control-state \
  --routing-control-arn <ARC_ROUTING_CONTROL_ARN> \
  --routing-control-state Off \
  --endpoint-url <any-arc-cluster-endpoint>
```

### Failback to us-east-1
```bash
aws route53-recovery-cluster update-routing-control-state \
  --routing-control-arn <ARC_ROUTING_CONTROL_ARN> \
  --routing-control-state On \
  --endpoint-url <any-arc-cluster-endpoint>
```

### Simulate failure (for demo)
```bash
# Break us-east-1 (instant 503)
aws lambda put-function-concurrency \
  --function-name dev-agent-proxy-redwood \
  --reserved-concurrent-executions 0 --region us-east-1

# Failover to us-east-2
aws route53-recovery-cluster update-routing-control-state \
  --routing-control-arn <ARC_ROUTING_CONTROL_ARN> \
  --routing-control-state Off \
  --endpoint-url <any-arc-cluster-endpoint>

# Restore after demo
aws lambda delete-function-concurrency \
  --function-name dev-agent-proxy-redwood --region us-east-1
aws route53-recovery-cluster update-routing-control-state \
  --routing-control-arn <ARC_ROUTING_CONTROL_ARN> \
  --routing-control-state On \
  --endpoint-url <any-arc-cluster-endpoint>
```

Failover takes ~10 seconds (Lambda@Edge cache TTL).

---

## All Options

```
bash infrastructure/scripts/deploy-stack-multi-region.sh --help
```

---

## Multi-Account Deployment

To deploy to a different AWS account:

1. Edit `infrastructure/deploy-config-multi-region.sh`:
   ```bash
   AWS_PROFILE="unicorn"   # Your AWS CLI profile name
   ```
2. Change `SUFFIX` to something unique for that account (e.g., `redwood02`)
3. Update `infrastructure/cloudformation/parameters/dev-parameters-multi-region.json` with account-specific Entra ID values
4. Run the deploy as normal

The script validates the resolved account ID — if credentials are wrong or profile is misconfigured, it fails fast with a clear error.

---

## Current Deployment

| Resource | Value |
|----------|-------|
| Suffix | `redwood` |
| Primary Stack | `secure-agentcore-app-dev-redwood` (us-east-1) |
| DR Stack | `secure-agentcore-app-dev-redwood-dr` (us-east-2) |
| Global Stack | `secure-agentcore-app-dev-redwood-global` (us-east-1) |
| Frontend | `https://dom3dptlu0xg4.cloudfront.net` |
| Endpoint | `/api/invoke` (via CloudFront → Lambda@Edge → active region) |
| Memory (Primary) | `dev_memory_us_east_1_redwood-1Folr0B81r` |
| Memory (DR) | `dev_memory_us_east_2_redwood-PCgTw4FgCH` |
| Lambda@Edge | `dev-origin-router-redwood:v10` (us-east-1, updated in-place) |
| ARC Control | `acore-redwood-ue1-active` (On = us-east-1) |
| Callback (us-east-1) | `https://bedrock-agentcore.us-east-1.amazonaws.com/identities/oauth2/callback/4ab6e37b-3eb4-4a02-9624-ddf443b8d89d` |
| Callback (us-east-2) | `https://bedrock-agentcore.us-east-2.amazonaws.com/identities/oauth2/callback/1df11691-1bbf-43db-be22-9cf52ce40d1d` |

---

## Known Behaviors

1. **Lambda@Edge replicas**: No longer an issue. Function is updated in-place and a new
   version is published. Old versions are retained by AWS but don't block new deployments.
2. **bash 3.2**: macOS ships bash 3.2 (no associative arrays). Scripts use indexed arrays.
3. **OAUTH_FORCE_AUTH**: Default `false`. Frontend "Force Reauth" button triggers fresh OAuth.
4. **Memory recall**: On first invocation of a new microVM, agent auto-recalls from STM.
5. **Memory replication**: Event-driven, ~10-15 seconds from primary to DR.
6. **Gateway Target schema**: Deploy script forces target re-read after schema update (prevents stale API ID).
