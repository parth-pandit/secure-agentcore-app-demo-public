#!/usr/bin/env python3
"""
Comprehensive security scan for sensitive content before pushing to git.

Checks for:
- Hardcoded secrets, passwords, API keys
- AWS account IDs
- Azure tenant/client IDs with associated secrets
- Private keys, tokens
- Files that should be in .gitignore

Usage: python3 helper_scripts/scan_secrets.py
"""

import os
import re
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "node_modules", "lambda-packages", "__pycache__", ".lambda-build"}
SCAN_EXTENSIONS = {
    ".sh", ".json", ".py", ".yaml", ".yml", ".js", ".html",
    ".md", ".txt", ".template", ".properties", ".env", ".cfg",
}

# Patterns that indicate real secrets (not just variable names)
SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"(?i)(aws_secret_access_key|secret_key)\s*[=:]\s*[A-Za-z0-9/+=]{20,}", "AWS Secret Key"),
    (r"WdH8Q[A-Za-z0-9~_.]{20,}", "Known Azure client secret pattern"),
    (r"(?i)client.?secret[\"']?\s*[:=]\s*[\"'][A-Za-z0-9~_.!@#$%^&*]{8,}[\"']", "Hardcoded client secret value"),
    (r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "Private key"),
    (r"(?i)password\s*[=:]\s*[\"'][^\"']{4,}[\"']", "Hardcoded password"),
    (r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", "JWT token (hardcoded)"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"sk-[A-Za-z0-9]{20,}", "API secret key (OpenAI/Stripe pattern)"),
]

# AWS account IDs to flag (12-digit numbers in specific contexts)
ACCOUNT_ID_PATTERN = r"(?:account.?id|Account|arn:aws)[\"':\s]*(\d{12})"

# Files that MUST be in .gitignore (contain runtime secrets)
MUST_GITIGNORE = [
    "infrastructure/deploy-config-multi-region.sh",
    "infrastructure/cloudformation/parameters/dev-parameters-multi-region.json",
    "frontend/src/config.generated.js",
    ".env",
    "*.pem",
    "*.key",
]

# Files that are OK to have "secret" references (code that reads secrets at runtime)
KNOWN_SAFE_REFERENCES = {
    "infrastructure/scripts/deploy-stack-multi-region.sh",
    "infrastructure/scripts/cleanup-stack-multi-region.sh",
    "ai-agent/src/order_agent.py",
    "helper_scripts/test_gateway_mcp.py",
    "helper_scripts/scan_secrets.py",
    "helper_scripts/check_gateway_target.py",
    "docs/AUTHENTICATION_SETUP.md",
    "infrastructure/cloudformation/templates/README.md",
    "infrastructure/cloudformation/templates/agentcore-app-stack.yaml",
    "tests/integration/agentcore/test_mcp_client_3lo_v2.py",
    "tests/utils/generate_azure_token.sh",
    "DEPLOYMENT-redwood.md",
    "CHANGELOG-redwood.md",
}


def load_gitignore():
    path = os.path.join(PROJECT_ROOT, ".gitignore")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def is_in_gitignore(filepath, gitignore_entries):
    basename = os.path.basename(filepath)
    for entry in gitignore_entries:
        if entry == basename:
            return True
        if entry == filepath:
            return True
        if entry.startswith("*") and filepath.endswith(entry[1:]):
            return True
        if entry in filepath:
            return True
    return False


def scan_file(filepath, relpath):
    findings = []
    try:
        with open(filepath, errors="ignore") as f:
            content = f.read()

        for pattern, desc in SECRET_PATTERNS:
            matches = re.finditer(pattern, content)
            for match in matches:
                line_num = content[:match.start()].count("\n") + 1
                snippet = match.group(0)[:40]
                findings.append({
                    "file": relpath,
                    "line": line_num,
                    "type": desc,
                    "snippet": snippet + "..." if len(match.group(0)) > 40 else snippet,
                })

        # Check for hardcoded account IDs (only flag if not in ARN templates)
        for match in re.finditer(ACCOUNT_ID_PATTERN, content):
            acct = match.group(1) if match.lastindex else match.group(0)
            line_num = content[:match.start()].count("\n") + 1
            # Skip if it's in a CFN template reference like ${AWS::AccountId}
            line = content.split("\n")[line_num - 1]
            if "${AWS::AccountId}" in line or "AWS_ACCOUNT_ID" in line:
                continue
            findings.append({
                "file": relpath,
                "line": line_num,
                "type": "AWS Account ID (hardcoded)",
                "snippet": acct,
            })

    except Exception as e:
        pass

    return findings


def main():
    gitignore = load_gitignore()

    print("=" * 70)
    print("  COMPREHENSIVE SECURITY SCAN — Project Redwood")
    print("=" * 70)
    print()

    # [1] Check .gitignore coverage
    print("--- [1] Files that MUST be in .gitignore ---")
    gitignore_issues = []
    for f in MUST_GITIGNORE:
        full = os.path.join(PROJECT_ROOT, f)
        exists = os.path.exists(full) if not f.startswith("*") else False
        covered = is_in_gitignore(f, gitignore)
        status = "OK" if covered else "MISSING!"
        if exists and not covered:
            gitignore_issues.append(f)
        marker = "  [EXISTS]" if exists else "  [------]"
        print(f"  {marker} {f:60s} .gitignore: {status}")
    print()

    # [2] Scan all files for secrets
    print("--- [2] Scanning files for hardcoded secrets ---")
    all_findings = []
    files_scanned = 0

    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext not in SCAN_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, PROJECT_ROOT)

            # Skip files in .gitignore
            if is_in_gitignore(relpath, gitignore):
                continue

            files_scanned += 1
            findings = scan_file(fpath, relpath)

            # Filter out known-safe references
            for finding in findings:
                if finding["file"] in KNOWN_SAFE_REFERENCES:
                    finding["safe"] = True
                else:
                    finding["safe"] = False
                all_findings.append(finding)

    dangerous = [f for f in all_findings if not f["safe"]]
    safe_refs = [f for f in all_findings if f["safe"]]

    if dangerous:
        print(f"  ⚠️  FOUND {len(dangerous)} POTENTIAL SECRET(S):")
        print()
        for f in dangerous:
            print(f"  {f['file']}:{f['line']}")
            print(f"    Type: {f['type']}")
            print(f"    Value: {f['snippet']}")
            print()
    else:
        print(f"  ✅ No hardcoded secrets found ({files_scanned} files scanned)")
    print()

    if safe_refs:
        print(f"  ℹ️  {len(safe_refs)} known-safe reference(s) (variable names, not values):")
        for f in safe_refs:
            print(f"    {f['file']}:{f['line']} — {f['type']}")
        print()

    # [3] Summary
    print("--- [3] SUMMARY ---")
    if gitignore_issues:
        print(f"  ❌ {len(gitignore_issues)} file(s) need to be added to .gitignore:")
        for f in gitignore_issues:
            print(f"     - {f}")
    else:
        print("  ✅ All sensitive files are in .gitignore")

    if dangerous:
        print(f"  ❌ {len(dangerous)} potential secret(s) found — review before pushing!")
    else:
        print("  ✅ No hardcoded secrets detected")

    print()
    if not gitignore_issues and not dangerous:
        print("  🟢 SAFE TO PUSH")
    else:
        print("  🔴 FIX ISSUES BEFORE PUSHING")

    return 1 if (gitignore_issues or dangerous) else 0


if __name__ == "__main__":
    exit(main())
