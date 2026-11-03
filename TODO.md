# GitHub IaC Management Engine: Functional Roadmap & TODO

This document details the functional roadmap required to bring the GitHub IaC system from foundation to production-grade enterprise deployment across GHEC, GHES, and GHEC EMU.

---

## 0. Key Architectural Decisions (Settled via Grilling)

1. **Authentication:**
   - **GitHub App** is the primary enterprise credential model with RSA private key JWT signing and automatic installation token rotation. Fine-grained PAT is supported as a fallback for local developers.
2. **State Storage & Locking:**
   - Cloud object storage (**S3 / GCS / Azure Blob**) with distributed locking for multi-operator CI/CD pipelines, alongside local JSON file storage for testing.
3. **Deletion & Drift Safety:**
   - **Non-destructive by default**: unmanaged resources or removals generate drift reports without destructive deletion unless `--prune` / `--destroy-unmanaged` is explicitly provided with safeguard checks.
4. **Adoption & Reverse Engineering:**
   - First-class **`gh-iac import <kind> <identifier>`** command that queries GraphQL/REST remote state and automatically generates declarative YAML manifests.
5. **Secret Encryption & Resolution:**
   - **Libsodium public-key encryption** executed locally (`pynacl` / `cryptography`) before sending secrets to GitHub. Secret payloads in manifests resolve references from HashiCorp Vault, AWS Secrets Manager, 1Password CLI, or environment variables.
6. **Scale & Concurrency:**
   - **DAG Concurrency Worker Pool** (configurable concurrency, e.g., 10 parallel workers) bounded by real-time GraphQL cost and rate limit budget tracking with automatic backoff on 403/429.

---

## Phase 1: Authentication & Connection Resilience

- [x] **GitHub App Authentication (First-Class Enterprise Integration)**
  - [x] Implement Private Key PEM signing (JWT generation) with automatic installation token generation & rotation.
  - [x] Support enterprise-level GitHub App installations (GHEC & GHES).
- [x] **Credential Providers & Secret Management**
  - [x] Support reading secrets/tokens from environment variables (`env:` and `${VAR}`).
  - [x] Avoid logging or persisting sensitive credentials in plain state files (`SecretString`, `mask_secret`).
- [x] **Rate Limiting & Resiliency**
  - [x] Implement exponential backoff with jitter on HTTP `429 Too Many Requests` and `403 Secondary Rate Limit Exceeded`.
  - [x] Parse `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and GraphQL `cost` / `rateLimit` payload metadata.
  - [x] Support custom CA bundles and proxy configurations (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, `ca_bundle`, `proxy`) for air-gapped GHES instances.

---

## Phase 2: Schema & Resource Provider Completeness

### 2.1 Enterprise Constructs (GHEC, GHES, EMU)
- [x] **Enterprise Identity & EMU**
  - [x] Full SCIM 2.0 implementation: Users (`EMUSCIMUser`), Groups (`EMUExternalGroup`).
  - [x] IdP-to-Team external group links (`EMUTeamMapping` -> `POST/PATCH /orgs/{org}/teams/{team}/external-groups`).
- [x] **Enterprise Security & Compliance**
  - [x] Audit log streaming configuration (`EnterpriseAuditStream` for S3, Splunk, Azure, Datadog, GCS).
  - [x] Enterprise-level IP allow lists and CIDR management (`EnterpriseIPAllowList` via GraphQL queries & mutations).
  - [x] Enterprise Actions policies and runner groups (`EnterprisePolicy`, `EnterpriseRunnerGroup` -> `/enterprises/{enterprise}/actions/runner-groups`).

### 2.2 Governance & Security Constructs
- [x] **Custom Roles**
  - [x] Organization custom roles (`CustomRepositoryRole` -> `/orgs/{org}/custom-repository-roles`).
  - [x] Enterprise custom roles (`EnterpriseCustomRole` -> `/enterprises/{enterprise}/custom-roles`).
- [x] **GitHub Advanced Security (GHAS)**
  - [x] Automated security analysis toggles across repos (`EnterpriseSecuritySetting` for GHAS, secret scanning, push protection).

### 2.3 Organization & Team Constructs
- [x] **Organization Management**
  - [x] Organization lifecycle and policies (`Organization` provider).
  - [x] Organization secrets (with libsodium encryption via `pynacl` / `cryptography`: `OrganizationSecret`).
- [x] **Team Management**
  - [x] Team management (`Team` provider).
  - [x] Team sync with IdP groups (`EMUTeamMapping`).

### 2.4 Repository & Branch Constructs
- [x] **Repositories**
  - [x] Repository lifecycle (`Repository` provider).
  - [x] Repository secrets with libsodium public key encryption (`RepositorySecret`).
- [x] **Modern Rulesets & Protections**
  - [x] Repository-level rulesets (`RepositoryRuleset` provider for branch protections and status checks).

---

## Phase 3: Core IaC Engine & State Management

- [x] **Robust Diff Engine**
  - [x] Deep structural diffing ignoring server-assigned default values and ordering differences (e.g. lists of permissions).
  - [x] Sensitive field masking in plans and output (e.g. webhook secrets, encrypted Actions secrets).
- [x] **State Backends**
  - [x] Remote state backend with state locking:
    - [x] Amazon S3 + object locking / DynamoDB locking (`S3StateBackend`).
    - [x] Google Cloud Storage (GCS) + locking (`GCSStateBackend`).
    - [x] Azure Blob Storage + lease/lockfile locking (`AzureBlobStateBackend`).
    - [x] HTTP REST state backend (`HttpRemoteBackend`).
    - [x] Local filesystem backend (`LocalStateBackend`).
  - [x] Encryption at rest for state files (AES-GCM via passphrase/KMS).
- [x] **Dependency Graph & Concurrency**
  - [x] Directed Acyclic Graph (DAG) for parallel resolution of independent resources (`DependencyGraph`).
  - [x] Cyclic dependency detection (`CyclicDependencyError`) and topological batch execution.
  - [x] Configurable worker pool (`ThreadPoolExecutor(concurrency)`) for high-speed synchronization across large enterprises (1,000+ repos).
- [x] **Resource Drift Detection & Import**
  - [x] `gh-iac drift`: Detect differences between state and actual GitHub reality.
  - [x] `gh-iac import <kind> <remote-id>`: Import pre-existing GitHub resources into declarative manifests without downtime.

---

## Phase 4: CLI & Developer Experience

- [x] **Interactive TUI / Rich Enhancements**
  - [x] Detailed colorized diff output (Terraform-style green `+` / red `-` / yellow `~` via `format_plan_human`).
  - [x] Non-interactive JSON output format (`gh-iac plan --json`) for CI/CD pipelines.
  - [x] PR Markdown output format (`gh-iac plan --markdown`) for automated PR comment bots.
- [x] **Validation & Linting**
  - [x] Schema validation against GitHub API constraints before sending network requests (`NAM001`, repo name constraints).
  - [x] Linter rules (`gh-iac lint [--strict]`):
    - [x] `SEC001`: Warn if GHAS is disabled on public repositories.
    - [x] `SEC002`: Warn if secret scanning push protection is disabled.
    - [x] `GOV001`: Warn if repository has no matching branch protection ruleset.
    - [x] `GOV002`: Warn if organization has two-factor authentication disabled.
    - [x] `NAM001`: Error if repository name contains invalid characters.
- [x] **CI/CD Integration**
  - [x] GitHub Actions workflow template for Pull Request planning and automated Merge apply ([examples/workflows/gh-iac.yml](file:///home/bbritt/Code/github-management/examples/workflows/gh-iac.yml)).
  - [x] PR commenting bot posting plan summaries with collapsible diffs.
  - [x] Composite GitHub Action definition in [action.yml](file:///home/bbritt/Code/github-management/action.yml).

---

## Phase 5: Testing, Documentation & Packaging

- [x] **Automated Testing Suite**
  - [x] Unit tests for all individual construct providers (enterprise, governance, secrets, apps, state, dag, linter, formatters).
  - [x] End-to-end integration tests using full-stack 17-manifest lifecycle ([tests/test_e2e_full_stack.py](file:///home/bbritt/Code/github-management/tests/test_e2e_full_stack.py)).
- [x] **Documentation**
  - [x] Manifest reference documentation for all 17 construct kinds ([docs/MANIFEST_REFERENCE.md](file:///home/bbritt/Code/github-management/docs/MANIFEST_REFERENCE.md)).
  - [x] EMU identity synchronization guide and best practices ([docs/EMU_GUIDE.md](file:///home/bbritt/Code/github-management/docs/EMU_GUIDE.md)).
  - [x] GHES compatibility matrix across versions 3.10–3.14+, air-gapped CA and proxy setup ([docs/GHES_COMPATIBILITY.md](file:///home/bbritt/Code/github-management/docs/GHES_COMPATIBILITY.md)).
  - [x] GitHub Apps creation, installation, and ruleset bypass guide ([docs/GITHUB_APPS.md](file:///home/bbritt/Code/github-management/docs/GITHUB_APPS.md)).
- [x] **Distribution**
  - [x] Production multi-stage Docker container image ([Dockerfile](file:///home/bbritt/Code/github-management/Dockerfile) & [.dockerignore](file:///home/bbritt/Code/github-management/.dockerignore)).
  - [x] GitHub Actions Composite Action definition ([action.yml](file:///home/bbritt/Code/github-management/action.yml)).
