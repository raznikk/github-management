---
layout: default
title: GHES Compatibility Matrix
---

# GitHub Enterprise Server (GHES) Compatibility Matrix & Operations Guide

This document details compatibility, networking requirements, TLS/custom CA bundles, and corporate proxy support when running `gh-iac` against self-hosted **GitHub Enterprise Server (GHES)** instances.

---

## 1. Supported GHES Versions

`gh-iac` is tested and verified against the following GitHub Enterprise Server release trains:

| GHES Version | Support Status | API Base Path | Rulesets Support | Fine-Grained Permissions | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GHES 3.14+** | Full Support | `/api/v3` & `/api/graphql` | ✅ Full | ✅ Full | Recommended release |
| **GHES 3.13** | Full Support | `/api/v3` & `/api/graphql` | ✅ Full | ✅ Full | Supported |
| **GHES 3.12** | Full Support | `/api/v3` & `/api/graphql` | ✅ Full | ✅ Full | Supported |
| **GHES 3.11** | Full Support | `/api/v3` & `/api/graphql` | ⚠️ Preview | ⚠️ Partial | Rulesets require feature flag |
| **GHES 3.10** | Maintenance | `/api/v3` & `/api/graphql` | ❌ Branch Prot. Only | ⚠️ Partial | Use legacy branch protections |
| **GHES < 3.10** | Unsupported | N/A | N/A | N/A | Upgrade recommended |

---

## 2. Air-Gapped & Custom CA Bundle Configuration

Enterprise GHES instances frequently use internal private Public Key Infrastructure (PKI) root CAs or self-signed TLS certificates.

`gh-iac` natively supports passing custom Certificate Authority (CA) bundles without requiring OS-level trust store modifications:

### Option A: Environment Variable
```bash
export SSL_CERT_FILE="/etc/ssl/certs/corporate-internal-ca.pem"
# or
export REQUESTS_CA_BUNDLE="/etc/ssl/certs/corporate-internal-ca.pem"
```

### Option B: Target Configuration / CLI Parameter
When constructing `TargetConfig.create_for_ghes(...)`:
```python
config = TargetConfig.create_for_ghes(
    hostname="github.corp.internal",
    token=token,
    ca_bundle="/etc/ssl/certs/corporate-internal-ca.pem",
    proxy="http://proxy.corp.internal:8080",
)
```

---

## 3. Corporate HTTP/HTTPS Proxy Support

In isolated VPCs or perimeter networks where outbound egress must traverse an explicit HTTP/HTTPS proxy:

```bash
export HTTP_PROXY="http://proxy.corp.internal:8080"
export HTTPS_PROXY="http://proxy.corp.internal:8080"
export NO_PROXY="localhost,127.0.0.1,.corp.internal"
```

`gh-iac` uses `httpx.Client` which automatically detects standard `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` environment variables and routes GHES requests accordingly.

---

## 4. CLI Execution against GHES

Run `gh-iac` commands against GHES by passing `--target ghes` and `--hostname`:

```bash
# Preview plan against on-premise GHES
gh-iac plan examples/full_stack.yaml \
  --target ghes \
  --hostname "github.corp.internal" \
  --token "ghp_ghes_admin_token..."

# Apply changes
gh-iac apply examples/full_stack.yaml \
  --target ghes \
  --hostname "github.corp.internal" \
  --token "ghp_ghes_admin_token..." \
  --auto-approve
```
