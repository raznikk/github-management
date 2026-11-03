"""Unit tests for Phase 2.1 Enterprise Constructs."""

import respx
from gh_iac.core.client import GitHubClient
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType
from gh_iac.providers.enterprise import (
    EMUSCIMUserProvider,
    EMUTeamMappingProvider,
    EnterpriseAuditStreamProvider,
    EnterpriseCustomRoleProvider,
    EnterpriseIPAllowListProvider,
    EnterprisePolicyProvider,
    EnterpriseRulesetProvider,
    EnterpriseRunnerGroupProvider,
)
from gh_iac.providers.governance import EnterpriseSecurityConfigurationProvider


@respx.mock
def test_emu_team_mapping_plan_and_apply():
    config = TargetConfig.create_for_emu(token="emu-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EMUTeamMappingProvider(client)

    manifest = GitHubManifest(
        kind="EMUTeamMapping",
        metadata=ManifestMetadata(
            name="cloud-eng-idp-link",
            organization="octocorp-cloud",
            enterprise="octocorp",
        ),
        spec={
            "team_slug": "cloud-platform-team",
            "group_id": 98765,
        },
    )

    # 1. Read: Initially no external group linked
    respx.get(
        "https://api.github.com/orgs/octocorp-cloud/teams/cloud-platform-team/external-groups"
    ).respond(
        status_code=200,
        json={"groups": []},
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: Expect CREATE action
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE
    assert plan.desired_state["group_id"] == 98765

    # 3. Apply: POST to link external group to team
    respx.patch(
        "https://api.github.com/orgs/octocorp-cloud/teams/cloud-platform-team/external-groups"
    ).respond(
        status_code=200,
        json={"group_id": 98765, "group_name": "Cloud-Platform-Engineers"},
    )

    result_state = provider.apply(plan, manifest)
    assert result_state.resource_id == manifest.resource_id
    assert result_state.attributes["group_id"] == 98765


@respx.mock
def test_enterprise_audit_stream_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseAuditStreamProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseAuditStream",
        metadata=ManifestMetadata(
            name="splunk-audit-sink",
            enterprise="octocorp",
        ),
        spec={
            "stream_type": "Splunk",
            "settings": {
                "domain": "https://splunk.internal:8088",
                "token": "splunk-hec-token",
            },
            "enabled": True,
        },
    )

    # Read: initially empty
    respx.get("https://api.github.com/enterprises/octocorp/audit-log/streams").respond(
        status_code=200,
        json=[],
    )

    current = provider.read(manifest)
    assert current is None

    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # Apply: create stream
    respx.post("https://api.github.com/enterprises/octocorp/audit-log/streams").respond(
        status_code=201,
        json={"id": 4321, "stream_type": "Splunk", "enabled": True},
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 4321
    assert state.attributes["stream_type"] == "Splunk"


@respx.mock
def test_enterprise_ip_allow_list_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseIPAllowListProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseIPAllowList",
        metadata=ManifestMetadata(
            name="corp-vpn-cidr",
            enterprise="octocorp",
        ),
        spec={
            "allow_list_value": "198.51.100.0/24",
            "name": "Corporate VPN Egress",
            "is_active": True,
        },
    )

    # Read: GraphQL query for enterprise ipAllowListEntries
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {
                "enterprise": {"id": "ENT_123", "ownerInfo": {"ipAllowListEntries": {"nodes": []}}}
            }
        },
    )

    current = provider.read(manifest)
    assert current is None

    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # Apply: GraphQL mutation createIpAllowListEntry
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {
                "createIpAllowListEntry": {
                    "ipAllowListEntry": {
                        "id": "IP_ENTRY_999",
                        "allowListValue": "198.51.100.0/24",
                        "name": "Corporate VPN Egress",
                        "isActive": True,
                    }
                }
            }
        },
    )

    state = provider.apply(plan, manifest)
    assert state.node_id == "IP_ENTRY_999"
    assert state.attributes["allowListValue"] == "198.51.100.0/24"


@respx.mock
def test_scim_user_plan_and_apply():
    config = TargetConfig.create_for_emu(token="emu-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EMUSCIMUserProvider(client)

    manifest = GitHubManifest(
        kind="EMUSCIMUser",
        metadata=ManifestMetadata(
            name="jdoe_octocorp",
            enterprise="octocorp",
        ),
        spec={
            "userName": "jdoe_octocorp",
            "name": {"givenName": "Jane", "familyName": "Doe"},
            "emails": [{"value": "jdoe@octocorp.com", "primary": True}],
            "roles": [{"value": "enterprise_owner"}],
            "active": True,
        },
    )

    # 1. Read: user not found initially
    respx.get("https://api.github.com/scim/v2/enterprises/octocorp/Users").respond(
        status_code=200,
        json={"totalResults": 0, "Resources": []},
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST /Users
    respx.post("https://api.github.com/scim/v2/enterprises/octocorp/Users").respond(
        status_code=201,
        json={"id": "scim-usr-1122", "userName": "jdoe_octocorp", "active": True},
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == "scim-usr-1122"
    assert state.attributes["userName"] == "jdoe_octocorp"


@respx.mock
def test_enterprise_custom_role_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseCustomRoleProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseCustomRole",
        metadata=ManifestMetadata(
            name="enterprise-compliance-auditor",
            enterprise="octocorp",
        ),
        spec={
            "description": "Enterprise wide compliance audit permissions",
            "base_role": "read",
            "permissions": ["view_audit_log", "view_enterprise_policies"],
        },
    )

    # 1. Read: no custom roles
    respx.get("https://api.github.com/enterprises/octocorp/custom-roles").respond(
        status_code=200,
        json={"total_count": 0, "custom_roles": []},
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST /custom-roles
    respx.post("https://api.github.com/enterprises/octocorp/custom-roles").respond(
        status_code=201,
        json={"id": 888, "name": "enterprise-compliance-auditor"},
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 888
    assert state.attributes["name"] == "enterprise-compliance-auditor"


@respx.mock
def test_enterprise_runner_group_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseRunnerGroupProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseRunnerGroup",
        metadata=ManifestMetadata(
            name="pci-isolated-runners",
            enterprise="octocorp",
        ),
        spec={
            "visibility": "selected",
            "selected_organization_ids": [101, 102],
            "allows_public_repositories": False,
        },
    )

    # 1. Read: empty runner groups
    respx.get("https://api.github.com/enterprises/octocorp/actions/runner-groups").respond(
        status_code=200,
        json={"total_count": 0, "runner_groups": []},
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST
    respx.post("https://api.github.com/enterprises/octocorp/actions/runner-groups").respond(
        status_code=201,
        json={"id": 555, "name": "pci-isolated-runners", "visibility": "selected"},
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 555
    assert state.attributes["name"] == "pci-isolated-runners"


@respx.mock
def test_enterprise_ip_allow_list_update():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseIPAllowListProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseIPAllowList",
        metadata=ManifestMetadata(
            name="corp-vpn-cidr",
            enterprise="octocorp",
        ),
        spec={
            "allow_list_value": "198.51.100.0/24",
            "name": "Corporate VPN Egress - Updated",
            "is_active": True,
        },
    )

    # Current state exists with node ID
    from gh_iac.core.state import ResourceState

    current = ResourceState(
        resource_id=manifest.resource_id,
        kind=manifest.kind,
        node_id="IP_ENTRY_999",
        attributes={
            "name": "Corporate VPN Egress",
            "allow_list_value": "198.51.100.0/24",
            "is_active": True,
        },
        applied_spec={
            "name": "Corporate VPN Egress",
            "allow_list_value": "198.51.100.0/24",
            "is_active": True,
        },
    )

    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.UPDATE

    # Update mutation
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {
                "updateIpAllowListEntry": {
                    "ipAllowListEntry": {
                        "id": "IP_ENTRY_999",
                        "allowListValue": "198.51.100.0/24",
                        "name": "Corporate VPN Egress - Updated",
                        "isActive": True,
                    }
                }
            }
        },
    )

    state = provider.apply(plan, manifest)
    assert state.node_id == "IP_ENTRY_999"
    assert state.attributes["name"] == "Corporate VPN Egress - Updated"


@respx.mock
def test_enterprise_policy_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterprisePolicyProvider(client)

    manifest = GitHubManifest(
        kind="EnterprisePolicy",
        metadata=ManifestMetadata(
            name="global-actions-policy",
            enterprise="octocorp",
        ),
        spec={
            "enabled_repositories": "all",
            "allowed_actions": "selected",
            "selected_actions": {
                "github_owned_allowed": True,
                "verified_allowed": True,
                "patterns_allowed": ["actions/*"],
            },
            "members_can_fork_private_repositories": False,
            "two_factor_requirement": True,
        },
    )

    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {
                "enterprise": {
                    "id": "ENT_001",
                    "slug": "octocorp",
                    "name": "OctoCorp Enterprise",
                    "description": "Global enterprise",
                    "url": "https://github.com/enterprises/octocorp",
                }
            }
        },
    )
    respx.get("https://api.github.com/enterprises/octocorp/actions/permissions").respond(
        status_code=200,
        json={"enabled_repositories": "all", "allowed_actions": "all"},
    )
    respx.get(
        "https://api.github.com/enterprises/octocorp/actions/permissions/selected-actions"
    ).respond(
        status_code=200,
        json={},
    )

    current = provider.read(manifest)
    assert current is not None

    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.UPDATE

    respx.put("https://api.github.com/enterprises/octocorp/actions/permissions").respond(
        status_code=200,
        json={"enabled_repositories": "all", "allowed_actions": "selected"},
    )
    respx.put(
        "https://api.github.com/enterprises/octocorp/actions/permissions/selected-actions"
    ).respond(
        status_code=200,
        json={"github_owned_allowed": True, "verified_allowed": True},
    )
    respx.patch("https://api.github.com/enterprises/octocorp").respond(
        status_code=200,
        json={"two_factor_requirement": True},
    )

    state = provider.apply(plan, manifest)
    assert state.resource_id == manifest.resource_id
    assert state.attributes["allowed_actions"] == "selected"


@respx.mock
def test_enterprise_ruleset_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseRulesetProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseRuleset",
        metadata=ManifestMetadata(
            name="ent-branch-governance",
            enterprise="octocorp",
        ),
        spec={
            "name": "ent-branch-governance",
            "target": "branch",
            "enforcement": "active",
            "conditions": {
                "ref_name": {
                    "include": ["refs/heads/main"],
                }
            },
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {"required_approving_review_count": 2},
                }
            ],
        },
    )

    # 1. Read: none
    respx.get("https://api.github.com/enterprises/octocorp/rulesets").respond(
        status_code=200,
        json=[],
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST
    respx.post("https://api.github.com/enterprises/octocorp/rulesets").respond(
        status_code=201,
        json={"id": 77711, "name": "ent-branch-governance", "enforcement": "active"},
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 77711
    assert state.attributes["name"] == "ent-branch-governance"


@respx.mock
def test_enterprise_security_configuration_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = EnterpriseSecurityConfigurationProvider(client)

    manifest = GitHubManifest(
        kind="EnterpriseSecurityConfiguration",
        metadata=ManifestMetadata(
            name="strict-ghas-profile",
            enterprise="octocorp",
        ),
        spec={
            "name": "strict-ghas-profile",
            "description": "Strict GHAS enforcement for repositories",
            "advanced_security": "enabled",
            "secret_scanning": "enabled",
            "secret_scanning_push_protection": "enabled",
            "code_scanning_default_setup": "enabled",
            "dependabot_alerts": "enabled",
            "dependabot_security_updates": "enabled",
            "enforcement": "enforced",
            "default_for_new_repos": "all",
            "repositories": [554433, 998811],
        },
    )

    # 1. Read: initially empty
    respx.get("https://api.github.com/enterprises/octocorp/code-security/configurations").respond(
        status_code=200,
        json=[],
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST configuration, PUT default, POST repositories
    respx.post("https://api.github.com/enterprises/octocorp/code-security/configurations").respond(
        status_code=201,
        json={"id": 1234, "name": "strict-ghas-profile", "enforcement": "enforced"},
    )
    respx.put(
        "https://api.github.com/enterprises/octocorp/code-security/configurations/1234/defaults"
    ).respond(
        status_code=200,
        json={"default_for_new_repos": "all"},
    )
    respx.post(
        "https://api.github.com/enterprises/octocorp/code-security/configurations/1234/repositories"
    ).respond(
        status_code=200,
        json={"attached": 2},
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 1234
    assert state.attributes["enforcement"] == "enforced"
