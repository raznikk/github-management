# GitHub IaC Management Engine

A declarative Infrastructure-as-Code (IaC) management system for GitHub, supporting **GitHub Enterprise Cloud (GHEC)**, **GitHub Enterprise Server (GHES)**, and **GHEC Enterprise Managed Users (EMU)**.

---

## Documentation Index

- 📖 [**Manifest Reference Guide**](docs/MANIFEST_REFERENCE.md): Detailed specifications for all 24 supported construct Kinds and spec schemas.
- 🔗 [**REST & GraphQL API Correlation**](docs/API_CORRELATION.md): Complete field-by-field mapping between declarative manifests and GitHub REST, GraphQL, and SCIM APIs.
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

## Configuration Architecture & Sizing

`gh-iac` natively supports loading manifests from either a **single multi-document YAML file** or a **modular directory tree**. When pointing the CLI to a directory (`gh-iac plan examples/multi_org/`), it recursively discovers all `**/*.yaml` and `**/*.yml` files. The topological DAG engine automatically resolves dependencies across all files into execution tiers (Enterprise $\rightarrow$ Organizations $\rightarrow$ Teams $\rightarrow$ Repositories), preventing ordering issues.

### 1. Recommended Enterprise Directory Structure

For multi-team enterprises, separating configurations by administrative and domain boundaries avoids Git merge conflicts and enables granular `CODEOWNERS` review policies:

```
examples/multi_org/
├── enterprise/
│   └── enterprise.yaml         # Policies, SIEM audit streams, EMU IdP external groups
├── org_platform/
│   ├── organization.yaml       # Org metadata, 2FA, Org Rulesets, Org Secrets/Variables
│   ├── teams.yaml              # 10 Platform teams + EMU IdP team sync mapping
│   └── repositories.yaml       # 10 Infrastructure repositories (GitOps, OPA, Terraform)
└── org_analytics/
    ├── organization.yaml       # Org metadata, Org Rulesets, GPU Runner Groups, Webhooks
    ├── teams.yaml              # 10 Data/ML teams + EMU IdP team sync mapping
    └── repositories.yaml       # 10 Data/ML repositories (Iceberg, DBT, Ray, Spark)
```

### 2. Configuration Sizing Benchmark

| Scenario Scope | Manifests | Approx. Lines of YAML | File Strategy |
| :--- | :--- | :--- | :--- |
| **Small Team / Sandbox** (1 Org, 1 Repo, 1 Team, Secrets) | ~10–15 | ~250–350 lines | Single file (`examples/full_stack.yaml`) |
| **Mid-Scale Platform** (1 Enterprise, 2 Orgs, 20 Teams, 20 Repos) | **55** | **~960 lines** | Modular directory (`examples/multi_org/`) |
| **Large Enterprise** (1 Enterprise, 10 Orgs, 100 Teams, 3,600 Repos) | ~3,800 | ~60,000 lines | Distributed Git repositories / sub-folders |

### 3. API Query Estimation & Rate Limit Optimization

For an enterprise with **10 organizations** and **3,600 repositories**:

* **Naive REST (Anti-pattern):** Querying every repo, ruleset, secret, and team individually requires **25,000+ API calls**, which exceeds GitHub's 5,000 req/hr rate limit and takes 3–5 hours.
* **`gh-iac` GraphQL-First Engine:** Batches 100 repositories with nested branch rulesets, default branch refs, and environments in single queries:
  $$\frac{3,600 \text{ repositories}}{100 \text{ per page}} = \mathbf{36 \text{ GraphQL queries}}$$
  Total discovery across the entire enterprise requires only **~130 to 150 API calls** (~100 GraphQL complexity points out of a 5,000-point hourly quota), completing in **under 30 seconds**.

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

### Development Task Automation (`just`)

This repository includes a [`Justfile`](Justfile) automating test, lint, format, coverage, and manifest workflows:

```bash
just                  # List all available recipes
just check            # Run Ruff linting and format checks
just format           # Format codebase with Ruff
just test             # Run all pytest suites
just cov-report       # Run line-by-line missing coverage report
just validate-all     # Validate both single-file and multi-org examples
just plan             # Run dry-run plan on examples/multi_org/
just apply            # Apply configuration to target
```

---

## CLI Reference

### 1. Validate Manifest Schema
```bash
# Validate a single file or an entire directory tree recursively
gh-iac validate examples/full_stack.yaml
gh-iac validate examples/multi_org/
```

### 2. Lint Security & Governance
```bash
# Audit 2FA enforcement, ruleset coverage, and secret scanning
gh-iac lint examples/multi_org/ --strict
```

### 3. Dry-Run Plan
```bash
# Colorized Terraform-style terminal diff across an entire directory
gh-iac plan examples/multi_org/ --target ghec

# Machine-readable JSON output for CI/CD pipelines
gh-iac plan examples/multi_org/ --target ghec --json

# GitHub Flavored Markdown for Pull Request comments
gh-iac plan examples/multi_org/ --target ghec --markdown
```

### 4. Apply Configuration
```bash
gh-iac apply examples/multi_org/ --target ghec --auto-approve
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

See [examples/workflows/gh-iac.yml](examples/workflows/gh-iac.yml) for a complete pull-request planning, merge-apply, and daily drift-monitoring workflow.
