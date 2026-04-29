# Security Audit Findings - PII and Sensitive Information

## Summary
This document lists all Personally Identifiable Information (PII) and sensitive data found in the repository that must be removed before making the code publicly available.

---

## 🔴 CRITICAL - Must Remove Before Open Source

### 1. AWS Account ID
**Account ID**: `YOUR_ACCOUNT_ID`

**Locations** (15 files):
- `ai-agent/src/utils/agent-proxy.properties` - Line 19
- `ai-agent/src/utils/order-agent.properties` - Line 10
- `ai-agent/src/utils/deploy-order-agent-to-acr.sh` - Lines 68, 69
- `infrastructure/boto3-scripts/agent_runtime_details.json` - Multiple lines
- `infrastructure/boto3-scripts/agentcore_identity_details.json` - Lines 4, 7
- `infrastructure/boto3-scripts/agentcore_gateway_details.json` - Multiple lines
- `tests/utils/agentcore-gateway-config-v1.json` - Multiple lines
- `frontend/utils/deploy-ui.sh` - Line 6

**Action Required**: Replace with placeholder `123456789012` or environment variable

---

### 2. Personal Email Address (PII)
**Email**: `user@example.com`

**Locations** (100+ occurrences across 20+ files):
- Test files: `tests/unit/test_authorized_user_properties.py`, `tests/integration/test_authorizer_integration.py`, `tests/integration/test_api_with_authentication.py`
- Documentation: `DEPLOYMENT_GUIDE.md`, `tests/utils/API_TESTING_QUICK_REFERENCE.md`, `tests/utils/setup_test_env.sh`
- Design specs: `.kiro/specs/api-authentication-authorization/design.md`, `.kiro/specs/api-authentication-authorization/requirements.md`

**Action Required**: Replace with generic `user@example.com` or `test@example.com`

---

### 3. S3 Bucket with Personal Identifier
**Bucket Name**: `YOUR_S3_BUCKET_NAME`

**Locations** (7 files):
- `ai-agent/src/utils/order-agent.properties` - Line 11
- `ai-agent/src/utils/deploy-order-agent-to-acr.sh` - Lines 19, 69
- `infrastructure/boto3-scripts/agent_runtime_details.json` - Line 26
- `infrastructure/boto3-scripts/agentcore_gateway_details.json` - Line 60
- `tests/utils/agentcore-gateway-config-v1.json` - Line 82

**Action Required**: Replace with generic `my-app-resources` or environment variable

---

### 4. CloudFront Distribution ID
**Distribution ID**: `YOUR_CLOUDFRONT_DISTRIBUTION_ID`

**Location**:
- `frontend/utils/deploy-ui.sh` - Line 8

**Action Required**: Replace with placeholder or environment variable

---

### 5. UI Bucket with Account ID
**Bucket Name**: `agentcore-ui-YOUR_ACCOUNT_ID-YYYYMMDD`

**Location**:
- `frontend/utils/deploy-ui.sh` - Line 6

**Action Required**: Replace with generic name or environment variable

---

### 6. AWS Secrets Manager ARNs (Contain Account ID)
**Multiple Secret ARNs** containing account ID `YOUR_ACCOUNT_ID`

**Locations**:
- `infrastructure/boto3-scripts/agentcore_identity_details.json`
- `infrastructure/boto3-scripts/agentcore_gateway_details.json`
- `tests/utils/agentcore-gateway-config-v1.json`

**Action Required**: Replace with placeholder ARNs or remove these config files

---

### 7. Specific Runtime/Gateway IDs
**Runtime IDs and Gateway IDs** that may be environment-specific:
- `YOUR_RUNTIME_ID`
- `gateway-authcode-YYYYMMDD-HHMMSS-RANDOM`
- `gateway-authcode-YYYYMMDD-HHMMSS-RANDOM`

**Locations**: Multiple JSON configuration files

**Action Required**: Replace with generic placeholders or document as examples

---

## 🟡 MEDIUM PRIORITY - Should Review

### 8. Hardcoded Test Data
- Test order IDs, dates, and other test data are acceptable but should be clearly marked as examples
- Mock JWT tokens in tests are fine (they're for testing only)

### 9. Configuration Files
The following files contain environment-specific configuration and should either be:
- Removed (if they're runtime artifacts)
- Converted to templates with placeholders
- Documented as examples only

**Files to review**:
- `infrastructure/boto3-scripts/agent_runtime_details.json`
- `infrastructure/boto3-scripts/agentcore_gateway_details.json`
- `infrastructure/boto3-scripts/agentcore_identity_details.json`
- `tests/utils/agentcore-gateway-config-v1.json`
- `ai-agent/src/utils/agent-proxy.properties`
- `ai-agent/src/utils/order-agent.properties`

---

## ✅ SAFE - No Action Needed

### Generic Test Data
- `user@yourdomain.com` - Generic placeholder (already updated in most places)
- `test@example.com` - Generic test email
- `unauthorized@example.com` - Generic test email
- Mock tokens and test secrets (clearly marked as test-only)

### Documentation Examples
- Generic AWS account IDs like `123456789012` in examples
- Generic region names like `us-west-2`, `us-east-1`
- Generic API Gateway IDs in documentation

---

## Recommended Actions

### Immediate (Before Open Source Release):

1. **Replace AWS Account ID** everywhere with:
   ```bash
   find . -type f -name "*.py" -o -name "*.sh" -o -name "*.json" -o -name "*.properties" -o -name "*.md" | \
   xargs sed -i '' 's/YOUR_ACCOUNT_ID/123456789012/g'
   ```

2. **Replace Personal Email** everywhere with:
   ```bash
   find . -type f -name "*.py" -o -name "*.md" | \
   xargs sed -i '' 's/parthpg@amazon\.com/user@example.com/g'
   ```

3. **Replace Personal S3 Bucket** with:
   ```bash
   find . -type f | \
   xargs sed -i '' 's/YOUR_S3_BUCKET_NAME/my-app-resources-bucket/g'
   ```

4. **Remove or Template Configuration Files**:
   - Delete runtime artifacts: `infrastructure/boto3-scripts/*.json`
   - Convert properties files to `.example` templates
   - Add to `.gitignore`: `*.properties`, `*_details.json`

5. **Update Documentation**:
   - Add clear warnings that example values must be replaced
   - Create a "Configuration" section explaining what needs to be customized
   - Add environment variable examples

### Create Template Files:

Create `.example` versions of configuration files:
- `ai-agent/src/utils/agent-proxy.properties.example`
- `ai-agent/src/utils/order-agent.properties.example`

With placeholders like:
```properties
RUNTIME_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/YourRoleName
S3_BUCKET=your-bucket-name
```

### Update .gitignore:

Add to `.gitignore`:
```
# Sensitive configuration
*.properties
*_details.json
agent_runtime_details.json
agentcore_gateway_details.json
agentcore_identity_details.json

# Environment-specific
.env
.env.local
```

---

## Verification Checklist

Before making repository public:

- [ ] All instances of AWS account ID `YOUR_ACCOUNT_ID` replaced
- [ ] All instances of `user@example.com` replaced
- [ ] All instances of personal S3 bucket name replaced
- [ ] CloudFront distribution ID replaced or removed
- [ ] Configuration files converted to templates or removed
- [ ] `.gitignore` updated to prevent future leaks
- [ ] README updated with configuration instructions
- [ ] All ARNs reviewed and sanitized
- [ ] Test files reviewed for any remaining PII
- [ ] Documentation reviewed for sensitive information

---

## Notes

- Mock tokens and test secrets in test files are acceptable (they're not real credentials)
- Generic placeholder emails like `user@example.com` are fine
- Example AWS resource names in documentation are acceptable if clearly marked as examples
- Environment variables should be used for all deployment-specific values

