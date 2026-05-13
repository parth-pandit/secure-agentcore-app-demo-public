# CHANGELOG — Project Redwood (Multi-Region)

Changes from the original `parth-pandit/secure-agentcore-app-demo-public` repo.

---

## Deployment System

### Deploy script (`deploy-stack-multi-region.sh`)
Single entry point at `infrastructure/scripts/`. Two modes:
- **Default** (no flags): Create-if-missing + verify. Fast (~2-3 min). Skips packaging/uploads if resources exist.
- **`--update`**: Full rebuild + redeploy all artifacts (~15-20 min).

Component modes: `--infra`, `--runtime`, `--frontend`, `--memory`.
Region control: `--primary-only`, `--dr-only`.
Both regions deployed by default for all modes.

### Config (`deploy-config-multi-region.sh`)
All values in one file. `SUFFIX` must be lowercase alphanumeric only (no hyphens).
`AWS_PROFILE` field at the top for multi-account deployments (empty = default profile).
Account ID safety check in deploy script prevents cross-account mistakes.
Current: `redwood`.

### Parameters (`dev-parameters-multi-region.json`)
IDP/auth config only. Deployment-derived values (buckets, suffix, regions)
injected by the script.

### Cleanup (`cleanup-stack-multi-region.sh`)
At `infrastructure/scripts/`. Always prompts for confirmation (type `DELETE`). Handles Lambda@Edge replica
cleanup with retry loop. Cleans all stacks, S3 buckets, and secrets in both regions.

---

## Multi-Region Architecture

| Component | us-east-1 (Primary) | us-east-2 (DR) |
|-----------|:---:|:---:|
| Backend API (APIGW + Lambda) | ✅ | ✅ |
| DDB Global Table | ✅ (creates + replica) | ✅ (uses replica) |
| AgentCore Gateway + Policy | ✅ | ✅ |
| AgentCore Runtime | ✅ | ✅ |
| Agent Proxy Lambda | ✅ | ✅ |
| Memory (STM) | ✅ (+ replication) | ✅ (receives) |
| CloudFront + S3 (Global) | ✅ | — |
| Lambda@Edge (ARC router) | ✅ | — |

### Stack Architecture
```
parent-regional.yaml  → Backend API + AgentCore (deploy per-region)
parent-global.yaml    → CloudFront + S3 + Lambda@Edge (deploy once, us-east-1)
```

### Traffic Flow
```
Browser → CloudFront → /api/* → Lambda@Edge → ARC check
                                  ├── On  → us-east-1 API GW → Runtime
                                  └── Off → us-east-2 API GW → Runtime
```

### Failover: ~10 seconds (Lambda@Edge cache TTL)

---

## Key Changes from Original

### Infrastructure
- Refactored into `parent-regional.yaml` (per-region) + `parent-global.yaml` (global)
- DDB `Table` → `GlobalTable` with DR replica (conditional `CreateDDBTable` param)
- IAM role names include `${AWS::Region}` suffix (multi-region safe)
- CloudFront `/api/*` behavior with Lambda@Edge (conditional on `LambdaEdgeArn`)
- Lambda@Edge managed directly via CLI (no CFN stack). Function is created once,
  then updated in-place with new code + new version published on each `--update`.
  Eliminates replica cleanup issues entirely.
- Cedar policy names use suffix without hyphens
- Gateway Target auto-refreshed after schema update (prevents stale API ID)
- Gateway secret created per-region (for runtime to call Gateway MCP)

### Agent Code
- Memory integration (save/recall/history seeding into Strands Agent messages)
- Memory recall only on first invocation per microVM (not every request)
- OTEL packages in requirements.txt
- Response metadata (tools used, region) prepended to agent response
- Actor ID sanitization for memory API
- `OAUTH_FORCE_AUTH` reads from env var (default `false`), toggled by frontend
  "Force Reauth" button via `force_reauth` prompt
- Removed false-positive payload error detection (was blocking valid tool responses)

### Frontend
- Relative `/api/invoke` endpoint (through CloudFront → Lambda@Edge)
- Full-width layout, fills viewport height
- Version badge (`v1.2.0`) next to title
- "⟳ New Session" button (resets runtime session cookie)
- "🔐 Force Reauth" button (invalidates Gateway 3LO token vault)
- Arrow up/down prompt history
- Meta info box (tools used, region, session ID)
- Memory load indicator only on first message of new microVM

### Packaging
- `uv pip` with correct `--python-version` per target (3.9 for backend, 3.12 for runtime)
- `requests<2.32.0` + `urllib3<2.0.0` for Python 3.9 Lambdas
- Always `--clean` to avoid stale packages
- bash 3.2 compatible (no `declare -A`)

---

## Bug Fixes (This Deployment Cycle)

1. **`LambdaCodeBucket` parameter error** — parent-regional.yaml passed duplicate
   parameter to AgentCoreAppStack. Removed.
2. **`AgentProxyFunctionUrl` output mismatch** — child template output key is
   `AgentProxyUrl`. Fixed `!GetAtt` reference.
3. **bash 3.2 compatibility** — replaced `declare -A` with parallel indexed arrays.
4. **`--dr-only` / `--primary-only` flags** — `--infra` mode now respects region flags.
5. **`OAUTH_FORCE_AUTH` global bug** — `global` declaration must precede any use
   in the same scope. Moved to top of `_tool_func`.
6. **Lambda@Edge update-in-place** — Replaced CFN-based approach (which created new
   functions each deploy and had replica cleanup issues) with direct CLI management:
   create once, update code in-place, publish new version, update CloudFront.
7. **Frontend deploy fallback** — falls back to primary stack if global stack missing.
8. **Gateway Target stale schema** — deploy script forces target re-read after
   schema update via `update-gateway-target`.
9. **False-positive tool error detection** — removed overly broad payload scanning
   that flagged valid responses containing common words like "error".
10. **Memory indicator spam** — `memory_loaded` now only sent on first invocation
    per microVM, not every request.

---

## Deprecated Files

Original single-region scripts and utilities renamed with `deprecated-` prefix.
See file tree for full list. Active deployment uses only:
- `infrastructure/scripts/deploy-stack-multi-region.sh`
- `infrastructure/scripts/cleanup-stack-multi-region.sh`
- `infrastructure/cloudformation/scripts/package-lambdas.sh`
- `infrastructure/deploy-config-multi-region.sh`
- `infrastructure/cloudformation/parameters/dev-parameters-multi-region.json`

---

## Files Added/Modified

```
infrastructure/
├── deploy-config-multi-region.sh(.template)
├── scripts/
│   ├── deploy-stack-multi-region.sh
│   └── cleanup-stack-multi-region.sh
├── cloudformation/
│   ├── scripts/package-lambdas.sh
│   ├── templates/
│   │   ├── parent-regional.yaml
│   │   ├── parent-global.yaml
│   │   ├── agentcore-app-stack.yaml
│   │   ├── backend-api-stack.yaml
│   │   └── frontend-stack.yaml
│   └── parameters/dev-parameters-multi-region.json(.template)
└── multi-region/
    ├── memory/{cfn-memory.yaml, cfn-memory-replication.yaml, lambda/, deploy.sh}
    └── lambda-edge/{origin_router.js, cfn-lambda-edge.yaml}

ai-agent/src/order_agent.py
frontend/src/{app.js, index.html, styles.css, auth.js, authConfig.js, config.js, configAccessor.js}
helper_scripts/{check_gateway_target.py, enable_logs.py, test_gateway_mcp.py, test-memory.py, scan_secrets.py}
CHANGELOG-redwood.md
DEPLOYMENT-redwood.md
```
