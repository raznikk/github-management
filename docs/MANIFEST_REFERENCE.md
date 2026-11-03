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
Configures enterprise-wide policies for GitHub Actions, fork permissions, repository creation, etc.

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `enabled_repositories` (str): `"all"`, `"none"`, or `"selected"`.
  - `allowed_actions` (str): `"all"`, `"local_only"`, or `"selected"`.

```yaml
apiVersion: github.iac/v1alpha1
kind: EnterprisePolicy
metadata:
  name: enterprise-actions-policy
  enterprise: octocorp
spec:
  enabled_repositories: all
  allowed_actions: selected
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
Configures enterprise automated security analysis baselines across all member repositories.

- **Metadata Scopes:** `enterprise` (required)
- **Key Spec Properties:**
  - `advanced_security_enabled_for_new_repositories` (bool)
  - `secret_scanning_enabled_for_new_repositories` (bool)
  - `secret_scanning_push_protection_enabled_for_new_repositories` (bool)

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
  visibility: all
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
