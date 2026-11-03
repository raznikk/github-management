---
layout: default
title: GitHub IaC Manifest Reference
---

# GitHub IaC Manifest Reference

This document provides a comprehensive specification reference for all declarative constructs supported by `gh-iac` across GitHub Enterprise Cloud (GHEC), GitHub Enterprise Server (GHES), and GHEC Enterprise Managed Users (EMU).

---

## Document Schema Anatomy

Every manifest conforms to the `github.iac/v1alpha1` API schema:

```yaml
apiVersion: github.iac/v1alpha1
kind: <ConstructKind>
metadata:
  name: <identifier>
  enterprise: <optional-enterprise-slug>
  organization: <optional-organization-login>
  repository: <optional-repository-name>
  labels:
    env: production
spec:
  # Construct-specific configuration properties
```

---

## 1. Enterprise Constructs (GHEC, GHES, EMU)

### `EnterprisePolicy`
Configures enterprise-wide policies for GitHub Actions execution permissions, trusted action filters, repository creation limits, forking permissions, and mandatory 2FA.

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `enabled_repositories` (str): `"all"`, `"none"`, or `"selected"`.
  - `allowed_actions` (str): `"all"`, `"local_only"`, or `"selected"`.
  - `selected_actions` (dict):
    - `github_owned_allowed` (bool): Allow actions created by GitHub.
    - `verified_allowed` (bool): Allow actions by verified marketplace creators.
    - `patterns_allowed` (list[str]): Allowed action creator patterns (e.g. `["actions/*", "octocorp/*"]`).
  - `members_can_fork_private_repositories` (bool): Prevent exfiltration via private forks.
  - `two_factor_requirement` (bool): Enforce mandatory two-factor authentication across all member organizations.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterprisePolicy
metadata:
  name: enterprise-actions-policy
  enterprise: octocorp
spec:
  enabled_repositories: all
  allowed_actions: selected
  selected_actions:
    github_owned_allowed: true
    verified_allowed: true
    patterns_allowed:
      - "actions/*"
      - "octocorp/*"
  members_can_fork_private_repositories: false
  two_factor_requirement: true
```

---

### `EnterpriseAuditStream`
Configures high-throughput audit log streaming to enterprise SIEM platforms (Splunk, AWS S3, Azure Event Hubs, Datadog, Google Cloud Storage).

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `stream_type` (str): `"Splunk"`, `"AzureEventHub"`, `"AmazonS3"`, `"GoogleCloudStorage"`, `"Datadog"`.
  - `settings` (dict): Stream-specific connection parameters and credentials (resolves `env:VAR`).
  - `enabled` (bool): Whether streaming is active.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseAuditStream
metadata:
  name: splunk-audit-stream
  enterprise: octocorp
spec:
  stream_type: Splunk
  settings:
    domain: https://splunk.internal:8088
    token: env:SPLUNK_HEC_TOKEN
  enabled: true
```

---

### `EnterpriseIPAllowList`
Configures enterprise-level IP allow lists and CIDR blocks to restrict access to trusted corporate networks.

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `cidr` (str): IPv4 or IPv6 CIDR block.
  - `name` (str): Human-readable entry name.
  - `is_active` (bool): Whether the entry is enforced.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseIPAllowList
metadata:
  name: corporate-hq-vpn
  enterprise: octocorp
spec:
  cidr: 198.51.100.0/24
  name: Corporate HQ VPN Gateway
  is_active: true
```

---

### `EnterpriseRunnerGroup`
Manages enterprise-wide self-hosted runner groups, isolation boundaries, and organization access.

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `visibility` (str): `"all"` or `"selected"`.
  - `selected_organization_ids` (list[int]): Organization numeric IDs allowed access.
  - `allows_public_repositories` (bool): Security safeguard preventing runners on public repos.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseRunnerGroup
metadata:
  name: pci-isolated-runners
  enterprise: octocorp
spec:
  visibility: selected
  selected_organization_ids: [10101]
  allows_public_repositories: false
```

---

### `EnterpriseSecuritySetting`
Configures enterprise-wide automated security analysis baselines across all member repositories (GitHub Advanced Security, Secret Scanning, Push Protection, and Dependabot).

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `advanced_security_enabled_for_new_repositories` (bool): Enable GitHub Advanced Security (GHAS) licensing baseline.
  - `secret_scanning_enabled_for_new_repositories` (bool): Enable automated secret scanning on commit pushes.
  - `secret_scanning_push_protection_enabled_for_new_repositories` (bool): Block developer pushes containing unencrypted API tokens.
  - `secret_scanning_validity_checks_enabled` (bool): Perform live token verification with partner token issuers.
  - `dependabot_alerts_enabled_for_new_repositories` (bool): Enable CVE vulnerability alerts for repository dependencies.
  - `dependabot_security_updates_enabled_for_new_repositories` (bool): Automatically submit automated pull requests to patch known CVEs.
  - `dependency_graph_enabled_for_new_repositories` (bool): Maintain continuous Software Bill of Materials (SBOM).
  - `code_scanning_default_setup_enabled_for_new_repositories` (bool): Activate automated zero-configuration CodeQL code scanning.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseSecuritySetting
metadata:
  name: enterprise-security-baseline
  enterprise: octocorp
spec:
  advanced_security_enabled_for_new_repositories: true
  secret_scanning_enabled_for_new_repositories: true
  secret_scanning_push_protection_enabled_for_new_repositories: true
  secret_scanning_validity_checks_enabled: true
  dependabot_alerts_enabled_for_new_repositories: true
  dependabot_security_updates_enabled_for_new_repositories: true
  dependency_graph_enabled_for_new_repositories: true
  code_scanning_default_setup_enabled_for_new_repositories: true
```

---

### `EnterpriseSecurityConfiguration`
Declares enterprise Code Security Configurations for repositories. Enables security architects to define standardized GHAS profiles, lock configurations to prevent organization/repository administrators from disabling protection, set enterprise-wide defaults for new repositories, and bind configurations to specific repositories.

- **Metadata Scopes:** `enterprise` (required), `name` (configuration name)
- **Key Spec Properties:**
  - `advanced_security` (str): `"enabled"` or `"disabled"`.
  - `secret_scanning` (str): `"enabled"` or `"disabled"`.
  - `secret_scanning_push_protection` (str): `"enabled"` or `"disabled"`.
  - `secret_scanning_validity_checks` (str): `"enabled"` or `"disabled"`.
  - `code_scanning_default_setup` (str): `"enabled"` or `"disabled"`.
  - `dependabot_alerts` (str): `"enabled"` or `"disabled"`.
  - `dependabot_security_updates` (str): `"enabled"` or `"disabled"`.
  - `private_vulnerability_reporting` (str): `"enabled"` or `"disabled"`.
  - `enforcement` (str): `"enforced"` (locks settings against repo admin override) or `"unenforced"`.
  - `default_for_new_repos` (optional str): `"all"`, `"none"`, or `"eligible"`.
  - `repositories` (optional list[int]): List of repository numeric IDs attached to this configuration.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseSecurityConfiguration
metadata:
  name: strict-tier1-ghas-profile
  enterprise: octocorp
spec:
  name: strict-tier1-ghas-profile
  description: Strict GHAS enforcement for mission-critical repositories
  advanced_security: enabled
  secret_scanning: enabled
  secret_scanning_push_protection: enabled
  secret_scanning_validity_checks: enabled
  code_scanning_default_setup: enabled
  dependabot_alerts: enabled
  dependabot_security_updates: enabled
  private_vulnerability_reporting: enabled
  enforcement: enforced
  default_for_new_repos: all
```

---

### `EnterpriseRuleset`
Declares enterprise-wide repository rulesets that enforce governance (mandatory branch protections, code reviews, status checks, commit signatures, linear history) across all organizations and repositories in the enterprise.

- **Metadata Scopes:** `enterprise` (required), `name` (ruleset name)
- **Key Spec Properties:**
  - `target` (str): `"branch"` or `"tag"`.
  - `enforcement` (str): `"active"`, `"evaluate"`, or `"disabled"`.
  - `conditions` (dict): Target branch ref inclusions (`ref_name`) and repository selection filter.
  - `rules` (list[dict]): Rules definitions (`pull_request`, `required_status_checks`, `required_signatures`, etc.).
  - `bypass_actors` (optional list[dict]): Enterprise administrative actors exempted from ruleset enforcement.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseRuleset
metadata:
  name: enterprise-global-branch-policy
  enterprise: octocorp
spec:
  name: enterprise-global-branch-policy
  target: branch
  enforcement: active
  conditions:
    ref_name:
      include:
        - refs/heads/main
        - refs/heads/release/*
  rules:
    - type: pull_request
      parameters:
        required_approving_review_count: 2
        dismiss_stale_reviews_on_push: true
    - type: required_signatures
```

---

### `EnterpriseCustomRole`
Creates and manages fine-grained enterprise-level custom administrative roles.

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `name` (str): Role display name.
  - `description` (str): Role description.
  - `permissions` (list[str]): List of granular permissions (e.g. `manage_enterprise_audit_log`, `view_all_orgs`).

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterpriseCustomRole
metadata:
  name: enterprise-compliance-auditor
  enterprise: octocorp
spec:
  name: Enterprise Compliance Auditor
  description: Grants read access to enterprise logs and policies
  permissions:
    - view_enterprise_audit_log
    - view_all_organizations
```

---

### `EMUSCIMUser` & `EMUExternalGroup`
Manages Enterprise Managed Users identity records and IdP group definitions provisioned via SCIM 2.0.

```yaml
apiVersion: github.iac/v1alpha1
kind: EMUExternalGroup
metadata:
  name: SecOps-Global-Engineering
  enterprise: octocorp
spec:
  externalId: okta-group-998822
  displayName: SecOps-Global-Engineering
```

---

### `EMUTeamMapping`
Links an enterprise Identity Provider external group directly to an organization team for automated IdP group synchronization.

- **Metadata Scopes:** `enterprise`, `organization` (required)
- **Key Spec Properties:**
  - `team_slug` (str): Target team slug within the organization.
  - `group_id` (int): SCIM external group ID.

```yaml
apiVersion: github.iac/v1alpha1
kind: EMUTeamMapping
metadata:
  name: cloud-platform-idp-link
  enterprise: octocorp
  organization: octocorp-cloud
spec:
  team_slug: cloud-platform-team
  group_id: 998822
```

---

### `GitHubApp`
Programmatically registers and provisions GitHub Apps at Enterprise or Organization scope with automated PEM private key issuance and credential output (`chmod 0600`). See [GITHUB_APPS.md](file:///home/bbritt/Code/github-management/docs/GITHUB_APPS.md) for detailed guide.

---

## 2. Organization Constructs

### `Organization`
Manages organization settings, security policies, and 2FA enforcement.

- **Metadata Scopes:** `name` (required, organization login)
- **Key Spec Properties:**
  - `description` (str): Organization description.
  - `email` (str): Administrative contact email.
  - `requiresTwoFactorAuthentication` (bool): Mandatory two-factor authentication toggle.

```yaml
apiVersion: github.iac/v1alpha1
kind: Organization
metadata:
  name: octocorp-cloud
spec:
  description: OctoCorp Cloud Engineering Platform
  email: cloud-admin@octocorp.internal
  requiresTwoFactorAuthentication: true
```

---

### `CustomRepositoryRole`
Defines organization-level custom repository roles for fine-grained repo permission delegation.

- **Metadata Scopes:** `organization` (required)
- **Key Spec Properties:**
  - `base_role` (str): `"read"`, `"triage"`, `"write"`, or `"maintain"`.
  - `permissions` (list[str]): Custom permissions granted on top of the base role.

```yaml
apiVersion: github.iac/v1alpha1
kind: CustomRepositoryRole
metadata:
  name: security-auditor
  organization: octocorp-cloud
spec:
  description: Custom role allowing security team read access and triage rights
  base_role: read
  permissions:
    - triage
    - view_secret_scanning_alerts
```

---

### `Team`
Manages organizational team hierarchies and membership settings.

- **Metadata Scopes:** `organization` (required)
- **Key Spec Properties:**
  - `name` (str): Team display name.
  - `description` (str): Team description.
  - `privacy` (str): `"closed"` or `"secret"`.
  - `parent_team_id` (optional int): Parent team numeric ID for nested hierarchies.

```yaml
apiVersion: github.iac/v1alpha1
kind: Team
metadata:
  name: cloud-platform-team
  organization: octocorp-cloud
spec:
  name: Cloud Platform Team
  description: Platform engineers managing cloud infrastructure
  privacy: closed
```

---

### `OrganizationSecret`
Provisions encrypted Organization-level GitHub Actions secrets. Payloads are encrypted client-side using Libsodium (`pynacl` sealed-box) with the organization's public key before transmission.

- **Metadata Scopes:** `organization` (required), `name` (secret name)
- **Key Spec Properties:**
  - `value` (str): Secret plaintext or reference (`env:VAR` / `${VAR}`).
  - `visibility` (str): `"all"`, `"private"`, or `"selected"`.
  - `selected_repository_ids` (optional list[int]): List of repository IDs when visibility is `"selected"`.

```yaml
apiVersion: github.iac/v1alpha1
kind: OrganizationSecret
metadata:
  name: DATADOG_API_KEY
  organization: octocorp-cloud
spec:
  value: env:DD_SECRET_VAL
  visibility: selected
  selected_repository_ids:
    - 554433
```

---

### `OrganizationVariable`
Manages organization-wide plain-text GitHub Actions configuration variables and visibility scoping.

- **Metadata Scopes:** `organization` (required), `name` (variable name)
- **Key Spec Properties:**
  - `value` (str): Plain-text variable value or reference.
  - `visibility` (str): `"all"`, `"private"`, or `"selected"`.
  - `selected_repository_ids` (optional list[int]): List of repository IDs when visibility is `"selected"`.

```yaml
apiVersion: github.iac/v1alpha1
kind: OrganizationVariable
metadata:
  name: CI_CLUSTER_ENDPOINT
  organization: octocorp-cloud
spec:
  value: https://k8s-prod.octocorp.internal
  visibility: all
```

---

### `OrganizationRuleset`
Declares organization-wide repository and branch rulesets enforcing governance, commit signatures, code reviews, and status checks across all or selected organization repositories.

- **Metadata Scopes:** `organization` (required), `name` (ruleset name)
- **Key Spec Properties:**
  - `target` (str): `"branch"` or `"tag"`.
  - `enforcement` (str): `"active"`, `"evaluate"`, or `"disabled"`.
  - `conditions` (dict): Target branch ref inclusions (`ref_name`) and repository selection filter (`repository_name` or `repository_id`).
  - `rules` (list[dict]): Organization-wide governance rules (`pull_request`, `required_status_checks`, `required_signatures`, etc.).
  - `bypass_actors` (optional list[dict]): Actors exempted from the ruleset (e.g. GitHub App integration or organization admin team).

```yaml
apiVersion: github.iac/v1alpha1
kind: OrganizationRuleset
metadata:
  name: org-wide-branch-governance
  organization: octocorp-cloud
spec:
  name: org-wide-branch-governance
  target: branch
  enforcement: active
  conditions:
    ref_name:
      include:
        - refs/heads/main
        - refs/heads/release/*
  rules:
    - type: pull_request
      parameters:
        required_approving_review_count: 2
        dismiss_stale_reviews_on_push: true
        require_code_owner_review: true
    - type: required_signatures
```

---

### `OrganizationRunnerGroup`
Configures organization-level self-hosted runner groups, repository access boundaries, and public repository execution safeguards.

- **Metadata Scopes:** `organization` (required), `name` (runner group name)
- **Key Spec Properties:**
  - `visibility` (str): `"all"`, `"selected"`, or `"private"`.
  - `selected_repository_ids` (optional list[int]): Specific repository IDs allowed access when visibility is `"selected"`.
  - `allows_public_repositories` (bool): Security safeguard preventing runners on public repositories (default `false`).

```yaml
apiVersion: github.iac/v1alpha1
kind: OrganizationRunnerGroup
metadata:
  name: platform-gpu-runners
  organization: octocorp-cloud
spec:
  visibility: selected
  selected_repository_ids:
    - 554433
  allows_public_repositories: false
```

---

### `OrganizationWebhook`
Configures organization-level event webhooks for enterprise integrations, CI/CD event bridges, and audit logging sinks.

- **Metadata Scopes:** `organization` (required), `name` (webhook identifier)
- **Key Spec Properties:**
  - `config` (dict):
    - `url` (str): Target webhook endpoint URL.
    - `content_type` (str): `"json"` or `"form"`.
    - `secret` (str): Shared secret payload signature (supports `env:VAR`).
    - `insecure_ssl` (str): `"0"` (enforced) or `"1"` (insecure).
  - `events` (list[str]): List of subscribed GitHub events (e.g. `push`, `pull_request`, `repository`, `member`).
  - `active` (bool): Whether webhook deliveries are enabled.

```yaml
apiVersion: github.iac/v1alpha1
kind: OrganizationWebhook
metadata:
  name: org-ops-webhook
  organization: octocorp-cloud
spec:
  config:
    url: https://events.octocorp.internal/github-webhook
    content_type: json
    secret: env:ORG_WEBHOOK_SECRET
    insecure_ssl: "0"
  events:
    - push
    - pull_request
    - repository
  active: true
```

---

## 3. Repository Constructs

### `Repository`
Manages repository lifecycle, metadata, features, and merge strategies.

- **Metadata Scopes:** `organization` (required), `name` (repo name)
- **Key Spec Properties:**
  - `description` (str)
  - `visibility` (str): `"private"`, `"internal"`, or `"public"`.
  - `has_issues` (bool)
  - `has_wiki` (bool)
  - `has_projects` (bool)
  - `delete_branch_on_merge` (bool)
  - `allow_squash_merge` (bool)
  - `allow_merge_commit` (bool)
  - `allow_rebase_merge` (bool)

```yaml
apiVersion: github.iac/v1alpha1
kind: Repository
metadata:
  name: core-infrastructure
  organization: octocorp-cloud
spec:
  description: Core Terraform & Kubernetes manifests
  visibility: private
  has_issues: true
  has_wiki: false
  delete_branch_on_merge: true
```

---

### `RepositorySecret`
Provisions encrypted Repository-level GitHub Actions secrets via Libsodium public-key encryption.

```yaml
apiVersion: github.iac/v1alpha1
kind: RepositorySecret
metadata:
  name: AWS_DEPLOY_KEY
  organization: octocorp-cloud
  repository: core-infrastructure
spec:
  value: env:AWS_PROD_DEPLOY_KEY
```

---

### `RepositoryRuleset`
Declares modern GitHub Repository Rulesets for branch protections, status check enforcement, and commit signature requirements.

- **Metadata Scopes:** `organization`, `repository` (required)
- **Key Spec Properties:**
  - `target` (str): `"branch"` or `"tag"`.
  - `enforcement` (str): `"active"`, `"evaluate"`, or `"disabled"`.
  - `conditions` (dict): Ref pattern inclusions (e.g. `refs/heads/main`).
  - `rules` (list[dict]): Rules definitions (`pull_request`, `required_status_checks`, `required_signatures`, etc.).

```yaml
apiVersion: github.iac/v1alpha1
kind: RepositoryRuleset
metadata:
  name: protect-main
  organization: octocorp-cloud
  repository: core-infrastructure
spec:
  name: protect-main
  target: branch
  enforcement: active
  conditions:
    ref_name:
      include:
        - refs/heads/main
  rules:
    - type: pull_request
      parameters:
        required_approving_review_count: 2
        dismiss_stale_reviews_on_push: true
        require_code_owner_review: true
    - type: required_status_checks
      parameters:
        strict_required_status_checks_policy: true
```

---

### `RepositoryPages`
Configures GitHub Pages publishing sites for repositories. Supports deploying from GitHub Actions workflows, branch/directory sources, custom domains (`cname`), HTTPS enforcement, and private Pages access control on Enterprise Cloud / Server.

- **Metadata Scopes:** `organization`, `repository` (required)
- **Key Spec Properties:**
  - `build_type` (str): `"workflow"` (modern Actions artifact deployment) or `"legacy"` (deploy from branch).
  - `source` (dict):
    - `branch` (str): Source branch (e.g. `"main"`, `"gh-pages"`).
    - `path` (str): Source directory (`"/"` or `"/docs"`).
  - `cname` (optional str): Custom domain name (e.g. `"docs.octocorp.internal"`).
  - `https_enforced` (bool): Require HTTPS for all requests.
  - `public` (bool): Whether the Pages site is publicly accessible or restricted to organization members (Enterprise Cloud / Server).

```yaml
apiVersion: github.iac/v1alpha1
kind: RepositoryPages
metadata:
  name: developer-portal-pages
  organization: octocorp-cloud
  repository: core-infrastructure
spec:
  build_type: workflow
  source:
    branch: main
    path: /docs
  cname: docs.octocorp.internal
  https_enforced: true
  public: false
```
