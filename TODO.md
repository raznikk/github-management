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

- [ ] **Robust Diff Engine**
  - [ ] Deep structural diffing ignoring server-assigned default values and ordering differences (e.g. lists of permissions).
  - [ ] Sensitive field masking in plans and output (e.g. webhook secrets, encrypted Actions secrets).
- [ ] **State Backends**
  - [ ] Remote state backend with state locking:
    - [ ] Amazon S3 + DynamoDB locking.
    - [ ] Google Cloud Storage (GCS) + locking.
    - [ ] Azure Blob Storage.
    - [ ] Local filesystem backend (existing baseline).
  - [ ] Encryption at rest for state files (AES-GCM via KMS or passphrase).
- [ ] **Dependency Graph & Concurrency**
  - [ ] Directed Acyclic Graph (DAG) using NetworkX or custom graph for parallel resolution of independent resources.
  - [ ] Cyclic dependency detection and topological batch execution.
  - [ ] Configurable worker threads/async tasks for high-speed synchronization across large enterprises (1,000+ repos).
- [ ] **Resource Drift Detection & Import**
  - [ ] `gh-iac drift`: Detect differences between state and actual GitHub reality.
  - [ ] `gh-iac import <kind> <remote-id>`: Import pre-existing GitHub resources into declarative manifests without downtime.

---

## Phase 4: CLI & Developer Experience

- [ ] **Interactive TUI / Rich Enhancements**
  - [ ] Detailed colorized diff output (similar to Terraform green `+` / red `-` / yellow `~`).
  - [ ] Non-interactive JSON output format (`gh-iac plan --json`) for CI/CD pipelines.
- [ ] **Validation & Linting**
  - [ ] Schema validation against GitHub API constraints before sending network requests.
  - [ ] Linter rules (e.g. warn if main branch is not protected, warn if GHAS is disabled for public repositories).
- [ ] **CI/CD Integration**
  - [ ] GitHub Actions workflow template for Pull Request planning and automated Merge apply (`gh-iac-action`).
  - [ ] PR commenting bot posting plan summaries.

---

## Phase 5: Testing, Documentation & Packaging

- [ ] **Automated Testing Suite**
  - [ ] Unit tests for all individual construct providers.
  - [ ] End-to-end integration tests using GitHub test organizations or mock GitHub enterprise servers (`wiremock` / `respx`).
- [ ] **Documentation**
  - [ ] Manifest reference documentation for all construct kinds and supported specs.
  - [ ] EMU identity synchronization guide and best practices.
  - [ ] GHES compatibility matrix.
- [ ] **Distribution**
  - [ ] Standalone compiled binaries via `uv run pyinstaller` or Docker container image for runner environments.
