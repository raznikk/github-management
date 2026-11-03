---
layout: default
title: GitHub IaC Documentation Portal
---

# GitHub IaC Management Engine

A declarative Infrastructure-as-Code (IaC) management system for GitHub, supporting **GitHub Enterprise Cloud (GHEC)**, **GitHub Enterprise Server (GHES)**, and **GHEC Enterprise Managed Users (EMU)**.

---

## Documentation Guides

| Guide | Description |
| :--- | :--- |
| 📖 [**Manifest Reference Guide**]({{ '/docs/MANIFEST_REFERENCE.html' | relative_url }}) | Comprehensive specifications for all 24 declarative construct Kinds. |
| 🔗 [**API Correlation Matrix**]({{ '/docs/API_CORRELATION.html' | relative_url }}) | Field-by-field mapping between manifests and GitHub REST v3, GraphQL v4, and SCIM 2.0. |
| 🤖 [**GitHub Apps Management**]({{ '/docs/GITHUB_APPS.html' | relative_url }}) | Declarative provisioning of Enterprise & Org GitHub Apps with automated RSA key generation and ruleset bypass. |
| 👥 [**EMU Identity Synchronization**]({{ '/docs/EMU_GUIDE.html' | relative_url }}) | Okta/Entra ID SCIM 2.0 provisioning architecture and IdP-to-Team group mapping. |
| 🏢 [**GHES Compatibility Matrix**]({{ '/docs/GHES_COMPATIBILITY.html' | relative_url }}) | Compatibility across GHES 3.10–3.14+, air-gapped TLS custom CA certificates, and corporate HTTP proxy setup. |
| 📐 [**Architecture Deep Dive**]({{ '/ARCHITECTURE.html' | relative_url }}) | GraphQL-first engine, DAG topological concurrency, and AES-256-GCM encrypted state backends. |
| 📋 [**Roadmap & Implementation Tracker**]({{ '/TODO.html' | relative_url }}) | Production hardening checklist, provider coverage, and implementation status. |

---

## Core Capabilities

1. **GraphQL-First Engine**: Primary communication via GraphQL API v4 with automated REST fallback for endpoints not exposed in GraphQL.
2. **Pluggable Encrypted State**: Client-side AES-256-GCM encrypted state persistence across S3, Azure Blob, GCS, HTTP, and Local backends.
3. **Directed Acyclic Graph (DAG) Concurrency**: Parallel execution of independent resources sorted topologically across execution tiers.
4. **Drift Detection & Reverse-Engineering Import**: Detect out-of-band drifts (`gh-iac drift`) and import existing infrastructure (`gh-iac import`).
5. **Zero-Leak Secret Management**: Client-side Libsodium (`pynacl` sealed-box) encryption before sending credentials to GitHub.
6. **Security & Governance Linter**: Pre-flight audit rules (`gh-iac lint --strict`) enforcing 2FA, ruleset coverage, and push protection.

---

## Quickstart

```bash
# Validate manifests
gh-iac validate examples/multi_org/

# Audit security baseline
gh-iac lint examples/multi_org/ --strict

# Plan changes (colorized diff)
gh-iac plan examples/multi_org/ --target ghec

# Apply configuration
gh-iac apply examples/multi_org/ --target ghec --auto-approve
```
