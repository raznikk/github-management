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
- [ ] **Credential Providers & Secret Management**
  - [ ] Support reading secrets/tokens from environment variables, AWS Secrets Manager, HashiCorp Vault, and 1Password CLI.
  - [ ] Avoid logging or persisting sensitive credentials in plain state files.
- [ ] **Rate Limiting & Resiliency**
  - [ ] Implement exponential backoff with jitter on HTTP `429 Too Many Requests` and `403 Secondary Rate Limit Exceeded`.
  - [ ] Parse `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and GraphQL `cost` / `rateLimit` payload metadata.
  - [ ] Support custom CA bundles and proxy configurations (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`) for air-gapped GHES instances.

---

## Phase 2: Schema & Resource Provider Completeness

### 2.1 Enterprise Constructs (GHEC, GHES, EMU)
- [ ] **Enterprise Identity & EMU**
  - [ ] Full SCIM 2.0 implementation: Users, Groups, Enterprise Role Assignments.
  - [ ] IdP-to-Team external group links (`POST /orgs/{org}/teams/{team}/external-groups`).
  - [ ] SAML Single Sign-On (SSO) configuration and certificate rotation policies.
- [ ] **Enterprise Security & Compliance**
  - [ ] Audit log streaming configuration (S3, Splunk, Azure Event Hub, Datadog, Google Cloud Storage).
  - [ ] Enterprise-level IP allow lists and CIDR management.
  - [ ] Enterprise Actions policies (allowed runners, self-hosted runner groups, runner permissions).

### 2.2 Governance & Security Constructs
- [ ] **Custom Roles**
  - [ ] Organization custom roles (`/orgs/{org}/custom-repository-roles`).
  - [ ] Enterprise custom roles (`/enterprises/{enterprise}/custom-roles`).
- [ ] **GitHub Advanced Security (GHAS)**
  - [ ] Automated security analysis toggles across all org repos.
  - [ ] Code scanning default setup and workflow triggers.
  - [ ] Secret scanning custom patterns and dry-run testing.
  - [ ] Dependabot auto-triage rules and security update policies.

### 2.3 Organization & Team Constructs
- [ ] **Organization Management**
  - [ ] Organization member invitations and role management (`admin`, `member`, `security_manager`, `billing_manager`).
  - [ ] Organization secrets and variables (with libsodium encryption via `pynacl` / `cryptography`).
  - [ ] Organization-level webhooks with HMAC secret validation.
  - [ ] Organization repository creation templates and default branch policy.
- [ ] **Team Management**
  - [ ] Nested parent/child team hierarchies and maintainers.
  - [ ] Team repository permissions (explicit mapping to repos with custom roles or triage/push/maintain/admin).
  - [ ] Team sync with IdP groups.

### 2.4 Repository & Branch Constructs
- [ ] **Repositories**
  - [ ] Full repository attributes (template repos, auto-init, topics, license templates, merge strategies).
  - [ ] Repository secrets, variables, and environment secrets with libsodium public key encryption.
  - [ ] Repository webhooks, deploy keys, and deploy tokens.
- [ ] **Modern Rulesets & Protections**
  - [ ] Org-level rulesets (inherited by all or targeted repos).
  - [ ] Repository-level rulesets (branch & tag rulesets).
  - [ ] Bypass actors (teams, apps, enterprise roles).
- [ ] **Environments & Deployments**
  - [ ] Environment protection rules (required reviewers, wait timer, deployment branches).

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
