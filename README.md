# GitHub IaC Management Engine

A declarative Infrastructure-as-Code (IaC) management system for GitHub, supporting **GitHub Enterprise Cloud (GHEC)**, **GitHub Enterprise Server (GHES)**, and **GHEC Enterprise Managed Users (EMU)**.

---

## Documentation Index

- 📖 [**Manifest Reference Guide**](docs/MANIFEST_REFERENCE.md): Detailed specifications for all 17 supported construct Kinds and spec schemas.
- 🤖 [**GitHub Apps Management**](docs/GITHUB_APPS.md): Declarative provisioning of Enterprise- and Org-scoped GitHub Apps with automated RSA key generation and ruleset bypass.
- 👥 [**EMU Identity Synchronization Guide**](docs/EMU_GUIDE.md): Architecture, Okta/Entra ID SCIM 2.0 provisioning, and IdP-to-Team mapping best practices.
- 🏢 [**GHES Compatibility Matrix**](docs/GHES_COMPATIBILITY.md): Compatibility across GHES 3.10–3.14+, air-gapped TLS custom CA bundles, and corporate HTTP proxy setup.
- 📐 [**Architecture Specification**](ARCHITECTURE.md): Deep-dive into GraphQL-first design, DAG concurrency engine, and Libsodium encryption.

---

## Key Capabilities

1. **GraphQL-First Engine**: GitHub GraphQL API v4 as primary communication layer with automatic fallback to REST v3 for endpoints not yet available in GraphQL (e.g. SCIM APIs, EMU team links).
2. **Pluggable State Backends & AES-GCM Encryption**: Distributed state locking and client-side AES-256-GCM encryption at rest across S3, GCS, Azure Blob, HTTP, and Local backends.
3. **Directed Acyclic Graph (DAG) Concurrency**: Parallel execution of independent resources sorted topologically with cyclic dependency protection.
4. **Drift Detection & Reverse-Engineering Import**: Detect out-of-band drifts (`gh-iac drift`) and import pre-existing infrastructure into clean declarative manifests (`gh-iac import`).
5. **Zero-Leak Secret Management**: Client-side Libsodium (`pynacl` sealed-box) public-key encryption before transmitting secrets to GitHub. Resolves references via `env:VAR` and `${VAR}`.
6. **Pre-Flight Linter**: Automated security and governance checks (`gh-iac lint`) enforcing 2FA, branch ruleset coverage, and secret scanning push protection.

---

## Installation

Using `uv` (recommended):

```bash
uv pip install -e ".[dev]"
```

Or standard `pip`:

```bash
pip install -e .
```

---

## CLI Reference

### 1. Validate Manifest Schema
```bash
gh-iac validate examples/full_stack.yaml
```

### 2. Lint Security & Governance
```bash
gh-iac lint examples/full_stack.yaml --strict
```

### 3. Dry-Run Plan
```bash
# Colorized Terraform-style terminal diff
gh-iac plan examples/full_stack.yaml --target ghec

# Machine-readable JSON output for CI/CD pipelines
gh-iac plan examples/full_stack.yaml --target ghec --json

# GitHub Flavored Markdown for Pull Request comments
gh-iac plan examples/full_stack.yaml --target ghec --markdown
```

### 4. Apply Configuration
```bash
gh-iac apply examples/full_stack.yaml --target ghec --auto-approve
```

### 5. Detect Configuration Drift
```bash
# Returns exit code 2 if remote environment has drifted from declared manifests
gh-iac drift examples/full_stack.yaml --target ghec
```

### 6. Import Existing Resources
```bash
# Reverse-engineer an existing repo or organization into a declarative manifest
gh-iac import Repository octocorp-cloud/core-infra -o manifests/core-infra.yaml
```

---

## GitHub Actions CI/CD Integration

Use the included composite action in your workflows:

```yaml
- name: Run GitHub IaC Plan
  uses: raznikk/github-management@main
  with:
    command: plan
    path: examples/full_stack.yaml
    target: ghec
    token: ${{ secrets.GH_IAC_ADMIN_TOKEN }}
    output-format: markdown
```

See [.github/workflows/gh-iac.yml](.github/workflows/gh-iac.yml) for a complete pull-request planning, merge-apply, and daily drift-monitoring workflow.
