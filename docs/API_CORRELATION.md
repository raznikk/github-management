# GitHub API Correlation: Manifest Specs to REST & GraphQL APIs

This document provides an exhaustive, field-by-field correlation between the declarative manifests in [`examples/full_stack.yaml`](file:///home/bbritt/Code/github-management/examples/full_stack.yaml) and the official GitHub REST v3, GraphQL v4, and SCIM 2.0 API surfaces implemented by `gh-iac`.

---

## Architecture Protocol Decision Matrix

| Construct Layer | Primary Protocol | Secondary / Fallback | Rationale |
| :--- | :--- | :--- | :--- |
| **Enterprise Identity & SCIM** | **SCIM 2.0** (`/scim/v2/...`) | N/A | GitHub EMU user & group provisioning adheres to RFC 7643/7644 SCIM protocols. |
| **Enterprise Policies & Runner Groups** | **REST v3** (`/enterprises/{ent}/...`) | GraphQL Query | Enterprise Actions policies, audit streams, and runner groups are currently REST-only in GitHub. |
| **Governance & Custom Roles** | **REST v3** (`/orgs/{org}/custom-repository-roles`) | GraphQL Query | Fine-grained custom repository and enterprise roles are managed via REST. |
| **Organizations & Teams** | **GraphQL v4** (`query GetOrg`, `createTeam`) | REST v3 (`PATCH /orgs/{org}`) | High performance atomic node reads with REST for administrative metadata updates. |
| **Repositories** | **GraphQL v4** (`createRepository`, `updateRepository`) | REST v3 (`PATCH /repos/{o}/{r}`) | GraphQL provides node ID resolution, mutation safety, and single-roundtrip queries. |
| **Repository Rulesets** | **REST v3** (`/repos/{o}/{r}/rulesets`) | N/A | Modern Rulesets API is exclusively available via REST in GitHub. |
| **Actions Secrets** | **REST v3** (`/actions/secrets/...`) | N/A | Client-side Libsodium public key retrieval and sealed-box payload delivery. |
| **GitHub Apps** | **REST v3** (`/enterprises/{ent}/apps`, `/orgs/{org}/apps`) | N/A | Programmatic app manifest registration and RSA private key generation. |

---

## Complete Construct Correlation Table

### 1. `EnterprisePolicy`
- **Example Manifest:** [lines 1–10](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L1-L10)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | GraphQL v4 / REST | `POST` / `GET` | `/graphql` + `/enterprises/{enterprise}/actions/permissions` | `query GetEnterpriseInfo` + actions policy |
| `enabled_repositories` | `str` | REST v3 | `PUT` | `/enterprises/{enterprise}/actions/permissions` | `{"enabled_repositories": "all"}` |
| `allowed_actions` | `str` | REST v3 | `PUT` | `/enterprises/{enterprise}/actions/permissions` | `{"allowed_actions": "selected"}` |
| `selected_actions` | `dict` | REST v3 | `PUT` | `/enterprises/{enterprise}/actions/permissions/selected-actions` | `{"github_owned_allowed": true, "verified_allowed": true, "patterns_allowed": ["actions/*"]}` |
| `members_can_fork_private_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}` | `{"members_can_fork_private_repositories": false}` |
| `two_factor_requirement` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}` | `{"two_factor_requirement": true}` |

- **Official GitHub Docs:** [GitHub Enterprise Actions Permissions](https://docs.github.com/en/enterprise-cloud@latest/rest/actions/permissions), [Enterprise Administration](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/admin-stats)

---

### 2. `EMUExternalGroup`
- **Example Manifest:** [lines 12–21](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L12-L21)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | SCIM 2.0 | `GET` | `/scim/v2/enterprises/{enterprise}/Groups?filter=displayName eq "..."` | Query parameter filter |
| `externalId` | `str` | SCIM 2.0 | `POST` | `/scim/v2/enterprises/{enterprise}/Groups` | `{"externalId": "okta-group-998822"}` |
| `displayName` | `str` | SCIM 2.0 | `POST` | `/scim/v2/enterprises/{enterprise}/Groups` | `{"displayName": "SecOps-Global-Engineering"}` |

- **Official GitHub Docs:** [SCIM External Groups API](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/scim#provision-an-enterprise-group)

---

### 3. `EnterpriseSecuritySetting`
- **Example Manifest:** [lines 23–33](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L23-L33)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/enterprises/{enterprise}/settings/security_analysis` | N/A |
| `advanced_security_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"advanced_security_enabled_for_new_repositories": true}` |
| `secret_scanning_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"secret_scanning_enabled_for_new_repositories": true}` |
| `secret_scanning_push_protection_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"secret_scanning_push_protection_enabled_for_new_repositories": true}` |
| `secret_scanning_validity_checks_enabled` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"secret_scanning_validity_checks_enabled": true}` |
| `dependabot_alerts_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"dependabot_alerts_enabled_for_new_repositories": true}` |
| `dependabot_security_updates_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"dependabot_security_updates_enabled_for_new_repositories": true}` |
| `dependency_graph_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"dependency_graph_enabled_for_new_repositories": true}` |
| `code_scanning_default_setup_enabled_for_new_repositories` | `bool` | REST v3 | `PATCH` | `/enterprises/{enterprise}/settings/security_analysis` | `{"code_scanning_default_setup_enabled_for_new_repositories": true}` |

- **Official GitHub Docs:** [Enterprise Code Security and Analysis](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/code-security-and-analysis)

---

### 4. `CustomRepositoryRole`
- **Example Manifest:** [lines 35–47](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L35-L47)
- **Scope:** Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/custom-repository-roles` | Filter by `r.name == metadata.name` |
| `metadata.name` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/custom-repository-roles` | `{"name": "security-auditor"}` |
| `description` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/custom-repository-roles` | `{"description": "Custom role allowing security team read access..."}` |
| `base_role` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/custom-repository-roles` | `{"base_role": "read"}` |
| `permissions` | `list[str]` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/custom-repository-roles` | `{"permissions": ["triage", "view_secret_scanning_alerts"]}` |

- **Official GitHub Docs:** [Custom Repository Roles API](https://docs.github.com/en/enterprise-cloud@latest/rest/orgs/custom-roles)

---

### 5. `Organization`
- **Example Manifest:** [lines 49–58](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L49-L58)
- **Scope:** Organization (`metadata.name`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | GraphQL v4 | `POST` | `/graphql` -> `query GetOrg($login: String!)` | Returns `id`, `name`, `description`, `email`, `requiresTwoFactorAuthentication` |
| `metadata.name` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/orgs` | `{"login": "octocorp-cloud", "admin": "admin"}` *(When creating under enterprise)* |
| `description` | `str` | REST v3 | `PATCH` | `/orgs/{org}` | `{"description": "OctoCorp Cloud Engineering Platform"}` |
| `email` | `str` | REST v3 | `PATCH` | `/orgs/{org}` | `{"email": "cloud-admin@octocorp.internal"}` |
| `requiresTwoFactorAuthentication` | `bool` | REST v3 | `PATCH` | `/orgs/{org}` | `{"two_factor_requirement_enabled": true}` |

- **Official GitHub Docs:** [Organizations API](https://docs.github.com/en/enterprise-cloud@latest/rest/orgs/orgs)

---

### 6. `Team`
- **Example Manifest:** [lines 60–69](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L60-L69)
- **Scope:** Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | GraphQL v4 | `POST` | `/graphql` -> `query GetTeam($org: String!, $slug: String!)` | Query team by slug |
| `spec.name` | `str` | REST v3 / GraphQL | `POST`/`PATCH` | `/orgs/{org}/teams` or mutation `createTeam` | `{"name": "Cloud Platform Team"}` |
| `description` | `str` | REST v3 / GraphQL | `POST`/`PATCH` | `/orgs/{org}/teams` or mutation `updateTeam` | `{"description": "Platform engineers managing cloud infrastructure"}` |
| `privacy` | `str` | REST v3 / GraphQL | `POST`/`PATCH` | `/orgs/{org}/teams` | `{"privacy": "closed"}` |

- **Official GitHub Docs:** [Teams API](https://docs.github.com/en/enterprise-cloud@latest/rest/teams/teams)

---

### 7. `OrganizationRuleset`
- **Example Manifest:** [lines 71–94](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L71-L94)
- **Scope:** Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/rulesets` & `/rulesets/{id}` | Fetches organization-wide rulesets |
| `name` | `str` | REST v3 | `POST`/`PUT` | `/orgs/{org}/rulesets` | `{"name": "org-default-protection"}` |
| `target` | `str` | REST v3 | `POST`/`PUT` | `/orgs/{org}/rulesets` | `{"target": "branch"}` |
| `enforcement` | `str` | REST v3 | `POST`/`PUT` | `/orgs/{org}/rulesets` | `{"enforcement": "active"}` |
| `conditions` | `dict` | REST v3 | `POST`/`PUT` | `/orgs/{org}/rulesets` | `{"conditions": {"ref_name": {"include": ["refs/heads/main"]}}}` |
| `rules` | `list[dict]` | REST v3 | `POST`/`PUT` | `/orgs/{org}/rulesets` | `[{"type": "pull_request", ...}, {"type": "non_fast_forward"}]` |

- **Official GitHub Docs:** [Organization Repository Rulesets API](https://docs.github.com/en/enterprise-cloud@latest/rest/orgs/rules)

---

### 8. `OrganizationVariable`
- **Example Manifest:** [lines 96–105](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L96-L105)
- **Scope:** Organization (`metadata.organization`), Name (`metadata.name`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/actions/variables/{name}` | Fetches org actions variable |
| `metadata.name` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/actions/variables` | `{"name": "DOCKER_REGISTRY_URL"}` |
| `value` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/actions/variables` | `{"value": "ghcr.io/octocorp-cloud"}` |
| `visibility` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/actions/variables` | `{"visibility": "all"}` |

- **Official GitHub Docs:** [Organization Actions Variables API](https://docs.github.com/en/enterprise-cloud@latest/rest/actions/variables#organization-variables)

---

### 9. `OrganizationRunnerGroup`
- **Example Manifest:** [lines 107–117](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L107-L117)
- **Scope:** Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/actions/runner-groups` | Fetches organization runner groups |
| `metadata.name` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/actions/runner-groups` | `{"name": "k8s-build-runners"}` |
| `visibility` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/actions/runner-groups` | `{"visibility": "all"}` |
| `allows_public_repositories` | `bool` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/actions/runner-groups` | `{"allows_public_repositories": false}` |

- **Official GitHub Docs:** [Organization Self-Hosted Runner Groups API](https://docs.github.com/en/enterprise-cloud@latest/rest/actions/self-hosted-runner-groups#create-a-self-hosted-runner-group-for-an-organization)

---

### 10. `OrganizationWebhook`
- **Example Manifest:** [lines 119–137](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L119-L137)
- **Scope:** Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/hooks` | Fetches organization webhooks |
| `name` | `str` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/hooks` | `{"name": "web"}` |
| `config` | `dict` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/hooks` | `{"config": {"url": "https://siem...", "content_type": "json", "secret": "***"}}` |
| `events` | `list[str]` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/hooks` | `{"events": ["repository", "member", "team"]}` |
| `active` | `bool` | REST v3 | `POST`/`PATCH` | `/orgs/{org}/hooks` | `{"active": true}` |

- **Official GitHub Docs:** [Organization Webhooks API](https://docs.github.com/en/enterprise-cloud@latest/rest/orgs/webhooks)

---

### 11. `Repository`
- **Example Manifest:** [lines 71–83](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L71-L83)
- **Scope:** Organization (`metadata.organization`), Repository (`metadata.name`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | GraphQL v4 | `POST` | `/graphql` -> `query GetRepo($owner: String!, $name: String!)` | Returns `id`, `name`, `isPrivate`, `hasWikiEnabled`, etc. |
| `metadata.name` | `str` | GraphQL v4 | `POST` | `/graphql` -> `mutation CreateRepo($input: CreateRepositoryInput!)` | `{"name": "core-infrastructure", "ownerId": "$org_id"}` |
| `description` | `str` | GraphQL / REST | `POST`/`PATCH` | `mutation UpdateRepository` / `PATCH /repos/{o}/{r}` | `{"description": "Core Terraform & Kubernetes manifests"}` |
| `visibility` | `str` | GraphQL / REST | `POST`/`PATCH` | `visibility: PRIVATE` / `{"private": true}` | Visibility mapping |
| `has_issues` | `bool` | GraphQL / REST | `POST`/`PATCH` | `hasIssuesEnabled: true` / `{"has_issues": true}` | Feature toggle |
| `has_wiki` | `bool` | GraphQL / REST | `POST`/`PATCH` | `hasWikiEnabled: false` / `{"has_wiki": false}` | Feature toggle |
| `delete_branch_on_merge` | `bool` | GraphQL / REST | `POST`/`PATCH` | `deleteBranchOnMerge: true` / `{"delete_branch_on_merge": true}` | Auto branch pruning |

- **Official GitHub Docs:** [Repositories API](https://docs.github.com/en/enterprise-cloud@latest/rest/repos/repos)

---

### 12. `RepositoryRuleset`
- **Example Manifest:** [lines 85–108](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L85-L108)
- **Scope:** Organization (`metadata.organization`), Repository (`metadata.repository`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/repos/{org}/{repo}/rulesets` & `/rulesets/{id}` | Fetches ruleset configuration |
| `name` | `str` | REST v3 | `POST`/`PUT` | `/repos/{org}/{repo}/rulesets` | `{"name": "protect-main"}` |
| `target` | `str` | REST v3 | `POST`/`PUT` | `/repos/{org}/{repo}/rulesets` | `{"target": "branch"}` |
| `enforcement` | `str` | REST v3 | `POST`/`PUT` | `/repos/{org}/{repo}/rulesets` | `{"enforcement": "active"}` |
| `conditions` | `dict` | REST v3 | `POST`/`PUT` | `/repos/{org}/{repo}/rulesets` | `{"conditions": {"ref_name": {"include": ["refs/heads/main"]}}}` |
| `rules` | `list[dict]` | REST v3 | `POST`/`PUT` | `/repos/{org}/{repo}/rulesets` | `[{"type": "pull_request", "parameters": {...}}, {"type": "required_status_checks", ...}]` |

- **Official GitHub Docs:** [Repository Rulesets API](https://docs.github.com/en/enterprise-cloud@latest/rest/repos/rules)

---

### 13. `EnterpriseAuditStream`
- **Example Manifest:** [lines 110–122](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L110-L122)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/enterprises/{enterprise}/audit-log/streams` | List active audit streams |
| `stream_type` | `str` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/audit-log/streams` | `{"stream_type": "Splunk"}` |
| `settings` | `dict` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/audit-log/streams` | `{"settings": {"domain": "https://splunk.internal:8088", "token": "***"}}` |
| `enabled` | `bool` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/audit-log/streams` | `{"enabled": true}` |

- **Official GitHub Docs:** [Enterprise Audit Log Streaming API](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/audit-log#audit-log-stream-configurations)

---

### 14. `EMUTeamMapping`
- **Example Manifest:** [lines 124–134](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L124-L134)
- **Scope:** Enterprise (`metadata.enterprise`), Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/teams/{team_slug}/external-groups` | Checks connected IdP group |
| `group_id` | `int` | REST v3 | `PATCH` | `/orgs/{org}/teams/{team_slug}/external-groups` | `{"group_id": 998822}` |

- **Official GitHub Docs:** [Team External Groups API](https://docs.github.com/en/enterprise-cloud@latest/rest/teams/external-groups#connect-an-external-group-to-a-team)

---

### 15. `OrganizationSecret`
- **Example Manifest:** [lines 136–145](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L136-L145)
- **Scope:** Organization (`metadata.organization`), Secret Name (`metadata.name`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Public Key Fetch)* | - | REST v3 | `GET` | `/orgs/{org}/actions/secrets/public-key` | Retrieves 32-byte Libsodium public key & `key_id` |
| `value` | `str` (masked) | REST v3 | `PUT` | `/orgs/{org}/actions/secrets/{secret_name}` | `{"encrypted_value": "<base64_sealed_box>", "key_id": "KEY_123"}` |
| `visibility` | `str` | REST v3 | `PUT` | `/orgs/{org}/actions/secrets/{secret_name}` | `{"visibility": "all"}` |

- **Official GitHub Docs:** [Create or update an organization secret](https://docs.github.com/en/enterprise-cloud@latest/rest/actions/secrets#create-or-update-an-organization-secret)

---

### 16. `RepositorySecret`
- **Example Manifest:** [lines 147–156](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L147-L156)
- **Scope:** Organization (`metadata.organization`), Repository (`metadata.repository`), Secret Name (`metadata.name`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Public Key Fetch)* | - | REST v3 | `GET` | `/repos/{org}/{repo}/actions/secrets/public-key` | Retrieves Libsodium public key & `key_id` |
| `value` | `str` (masked) | REST v3 | `PUT` | `/repos/{org}/{repo}/actions/secrets/{secret_name}` | `{"encrypted_value": "<base64_sealed_box>", "key_id": "KEY_456"}` |

- **Official GitHub Docs:** [Create or update a repository secret](https://docs.github.com/en/enterprise-cloud@latest/rest/actions/secrets#create-or-update-a-repository-secret)

---

### 17. `EMUSCIMUser`
- **Example Manifest:** [lines 158–175](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L158-L175)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | SCIM 2.0 | `GET` | `/scim/v2/enterprises/{enterprise}/Users?filter=userName eq "..."` | Queries existing user by username |
| `userName` | `str` | SCIM 2.0 | `POST`/`PUT` | `/scim/v2/enterprises/{enterprise}/Users` | `{"userName": "jdoe_octocorp"}` |
| `name` | `dict` | SCIM 2.0 | `POST`/`PUT` | `/scim/v2/enterprises/{enterprise}/Users` | `{"name": {"givenName": "Jane", "familyName": "Doe"}}` |
| `emails` | `list[dict]` | SCIM 2.0 | `POST`/`PUT` | `/scim/v2/enterprises/{enterprise}/Users` | `{"emails": [{"value": "jdoe@octocorp.com", "primary": true}]}` |
| `roles` | `list[dict]` | SCIM 2.0 | `POST`/`PUT` | `/scim/v2/enterprises/{enterprise}/Users` | `{"roles": [{"value": "enterprise_owner"}]}` |
| `active` | `bool` | SCIM 2.0 | `POST`/`PUT` | `/scim/v2/enterprises/{enterprise}/Users` | `{"active": true}` |

- **Official GitHub Docs:** [SCIM Enterprise Users API](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/scim#provision-and-invite-an-enterprise-user)

---

### 18. `EnterpriseCustomRole`
- **Example Manifest:** [lines 177–189](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L177-L189)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/enterprises/{enterprise}/custom-roles` | List enterprise custom roles |
| `metadata.name` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/custom-roles` | `{"name": "enterprise-compliance-auditor"}` |
| `description` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/custom-roles` | `{"description": "Enterprise-wide compliance auditor..."}` |
| `base_role` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/custom-roles` | `{"base_role": "read"}` |
| `permissions` | `list[str]` | REST v3 | `POST` | `/enterprises/{enterprise}/custom-roles` | `{"permissions": ["view_audit_log", "view_enterprise_policies"]}` |

- **Official GitHub Docs:** [Enterprise Custom Roles API](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/custom-roles)

---

### 19. `EnterpriseRunnerGroup`
- **Example Manifest:** [lines 191–202](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L191-L202)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/enterprises/{enterprise}/actions/runner-groups` | Fetches runner groups |
| `metadata.name` | `str` | REST v3 | `POST`/`PATCH` | `/enterprises/{enterprise}/actions/runner-groups` | `{"name": "pci-isolated-runners"}` |
| `visibility` | `str` | REST v3 | `POST`/`PATCH` | `/enterprises/{enterprise}/actions/runner-groups` | `{"visibility": "selected"}` |
| `selected_organization_ids` | `list[int]` | REST v3 | `POST`/`PATCH` | `/enterprises/{enterprise}/actions/runner-groups` | `{"selected_organization_ids": [10101]}` |
| `allows_public_repositories` | `bool` | REST v3 | `POST`/`PATCH` | `/enterprises/{enterprise}/actions/runner-groups` | `{"allows_public_repositories": false}` |

- **Official GitHub Docs:** [Enterprise Actions Runner Groups](https://docs.github.com/en/enterprise-cloud@latest/rest/actions/self-hosted-runner-groups#create-a-self-hosted-runner-group-for-an-enterprise)

---

### 20. `GitHubApp` (Enterprise-Scoped)
- **Example Manifest:** [lines 204–221](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L204-L221)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/enterprises/{enterprise}/apps` | Queries existing enterprise apps |
| `metadata.name` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/apps` | `{"name": "enterprise-compliance-daemon"}` |
| `url` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/apps` | `{"url": "https://compliance.octocorp.internal"}` |
| `description` | `str` | REST v3 | `POST` | `/enterprises/{enterprise}/apps` | `{"description": "Enterprise compliance and audit daemon"}` |
| `public` | `bool` | REST v3 | `POST` | `/enterprises/{enterprise}/apps` | `{"public": false}` |
| `default_permissions` | `dict` | REST v3 | `POST` | `/enterprises/{enterprise}/apps` | `{"default_permissions": {"enterprise_administration": "read", ...}}` |
| `default_events` | `list[str]` | REST v3 | `POST` | `/enterprises/{enterprise}/apps` | `{"default_events": ["audit_log_entry"]}` |
| `output_credentials` | `dict` | Client Engine | N/A | Local secure output | Saves issued RSA private key PEM (`chmod 0600`) |

- **Official GitHub Docs:** [GitHub Apps Enterprise Endpoints](https://docs.github.com/en/enterprise-cloud@latest/rest/apps)

---

### 21. `GitHubApp` (Organization-Scoped)
- **Example Manifest:** [lines 223–244](file:///home/bbritt/Code/github-management/examples/full_stack.yaml#L223-L244)
- **Scope:** Organization (`metadata.organization`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/orgs/{org}/apps` | Queries organization apps |
| `metadata.name` | `str` | REST v3 | `POST` | `/orgs/{org}/apps` | `{"name": "release-orchestrator-bot"}` |
| `url` | `str` | REST v3 | `POST` | `/orgs/{org}/apps` | `{"url": "https://release.octocorp.internal"}` |
| `description` | `str` | REST v3 | `POST` | `/orgs/{org}/apps` | `{"description": "CI/CD release orchestrator"}` |
| `public` | `bool` | REST v3 | `POST` | `/orgs/{org}/apps` | `{"public": false}` |
| `default_permissions` | `dict` | REST v3 | `POST` | `/orgs/{org}/apps` | `{"default_permissions": {"contents": "write", "pull_requests": "write", ...}}` |
| `default_events` | `list[str]` | REST v3 | `POST` | `/orgs/{org}/apps` | `{"default_events": ["push", "pull_request", "release"]}` |
| `output_credentials` | `dict` | Client Engine | N/A | Local secure output | Saves issued RSA private key PEM (`chmod 0600`) |

- **Official GitHub Docs:** [Create a GitHub App from a manifest](https://docs.github.com/en/enterprise-cloud@latest/rest/apps/apps#create-a-github-app-from-a-manifest)

---

### 22. `EnterpriseRuleset`
- **Example Manifest:** [examples/multi_org/enterprise/enterprise.yaml](file:///home/bbritt/Code/github-management/examples/multi_org/enterprise/enterprise.yaml)
- **Scope:** Enterprise (`metadata.enterprise`)

| Manifest Spec Field | Type | GitHub API Target | Method | Path / Operation | Payload Mapping |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *(Read Operation)* | - | REST v3 | `GET` | `/enterprises/{enterprise}/rulesets` | Query enterprise rulesets |
| `name` | `str` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/rulesets` | `{"name": "enterprise-global-branch-policy"}` |
| `target` | `str` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/rulesets` | `{"target": "branch"}` |
| `enforcement` | `str` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/rulesets` | `{"enforcement": "active"}` |
| `conditions` | `dict` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/rulesets` | Target refs and repository criteria |
| `rules` | `list[dict]` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/rulesets` | `pull_request`, `required_signatures`, status checks |
| `bypass_actors` | `list[dict]` | REST v3 | `POST`/`PUT` | `/enterprises/{enterprise}/rulesets` | Enterprise-wide bypass actors |

- **Official GitHub Docs:** [Enterprise Repository Rulesets](https://docs.github.com/en/enterprise-cloud@latest/rest/enterprise-admin/rules#create-an-enterprise-ruleset)

