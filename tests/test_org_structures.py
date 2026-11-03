"""Unit tests for extended Organization structures (Rulesets, Variables, Webhooks, Runner Groups)."""

import respx

from gh_iac.core.client import GitHubClient
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType
from gh_iac.providers.organization import (
    OrganizationRulesetProvider,
    OrganizationRunnerGroupProvider,
    OrganizationVariableProvider,
    OrganizationWebhookProvider,
)
from gh_iac.providers.repository import RepositoryPagesProvider


def get_test_client():
    config = TargetConfig.create_for_ghec(token="test-token", enterprise_slug="octocorp")
    return GitHubClient(config)


@respx.mock
def test_organization_ruleset_provider_lifecycle():
    client = get_test_client()
    provider = OrganizationRulesetProvider(client)

    manifest = GitHubManifest(
        kind="OrganizationRuleset",
        metadata=ManifestMetadata(name="org-wide-protection", organization="octocorp-cloud"),
        spec={
            "name": "org-wide-protection",
            "target": "branch",
            "enforcement": "active",
            "conditions": {
                "ref_name": {"include": ["refs/heads/main"]},
            },
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {"required_approving_review_count": 2},
                }
            ],
        },
    )

    # 1. Read when non-existent
    respx.get("https://api.github.com/orgs/octocorp-cloud/rulesets").respond(
        status_code=200,
        json=[],
    )
    current = provider.read(manifest)
    assert current is None

    # 2. Plan CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply CREATE
    respx.post("https://api.github.com/orgs/octocorp-cloud/rulesets").respond(
        status_code=201,
        json={"id": 12345, "name": "org-wide-protection", "enforcement": "active"},
    )
    new_state = provider.apply(plan, manifest)
    assert new_state.numeric_id == 12345

    # 4. Read existing
    respx.get("https://api.github.com/orgs/octocorp-cloud/rulesets").respond(
        status_code=200,
        json=[{"id": 12345, "name": "org-wide-protection"}],
    )
    respx.get("https://api.github.com/orgs/octocorp-cloud/rulesets/12345").respond(
        status_code=200,
        json={"id": 12345, "name": "org-wide-protection", "enforcement": "active"},
    )
    existing = provider.read(manifest)
    assert existing is not None
    assert existing.numeric_id == 12345


@respx.mock
def test_organization_variable_provider_lifecycle():
    client = get_test_client()
    provider = OrganizationVariableProvider(client)

    manifest = GitHubManifest(
        kind="OrganizationVariable",
        metadata=ManifestMetadata(name="REGISTRY_URL", organization="octocorp-cloud"),
        spec={
            "value": "ghcr.io/octocorp",
            "visibility": "all",
        },
    )

    # 1. Read non-existent
    respx.get("https://api.github.com/orgs/octocorp-cloud/actions/variables/REGISTRY_URL").respond(
        status_code=404,
    )
    current = provider.read(manifest)
    assert current is None

    # 2. Plan CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply CREATE
    respx.post("https://api.github.com/orgs/octocorp-cloud/actions/variables").respond(
        status_code=201,
        json={"name": "REGISTRY_URL", "value": "ghcr.io/octocorp", "visibility": "all"},
    )
    new_state = provider.apply(plan, manifest)
    assert new_state.attributes["value"] == "ghcr.io/octocorp"


@respx.mock
def test_organization_webhook_provider_lifecycle():
    client = get_test_client()
    provider = OrganizationWebhookProvider(client)

    manifest = GitHubManifest(
        kind="OrganizationWebhook",
        metadata=ManifestMetadata(name="siem-audit-hook", organization="octocorp-cloud"),
        spec={
            "config": {
                "url": "https://siem.octocorp.internal/events",
                "content_type": "json",
                "secret": "hook-secret-123",
            },
            "events": ["repository", "member", "team"],
            "active": True,
        },
    )

    # 1. Read non-existent
    respx.get("https://api.github.com/orgs/octocorp-cloud/hooks").respond(
        status_code=200,
        json=[],
    )
    current = provider.read(manifest)
    assert current is None

    # 2. Plan CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply CREATE
    respx.post("https://api.github.com/orgs/octocorp-cloud/hooks").respond(
        status_code=201,
        json={"id": 88811, "name": "web", "active": True},
    )
    new_state = provider.apply(plan, manifest)
    assert new_state.numeric_id == 88811


@respx.mock
def test_organization_runner_group_provider_lifecycle():
    client = get_test_client()
    provider = OrganizationRunnerGroupProvider(client)

    manifest = GitHubManifest(
        kind="OrganizationRunnerGroup",
        metadata=ManifestMetadata(name="k8s-platform-runners", organization="octocorp-cloud"),
        spec={
            "visibility": "selected",
            "selected_repository_ids": [554433],
            "allows_public_repositories": False,
        },
    )

    # 1. Read non-existent
    respx.get("https://api.github.com/orgs/octocorp-cloud/actions/runner-groups").respond(
        status_code=200,
        json={"runner_groups": []},
    )
    current = provider.read(manifest)
    assert current is None

    # 2. Plan CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply CREATE
    respx.post("https://api.github.com/orgs/octocorp-cloud/actions/runner-groups").respond(
        status_code=201,
        json={"id": 9911, "name": "k8s-platform-runners", "visibility": "selected"},
    )
    new_state = provider.apply(plan, manifest)
    assert new_state.numeric_id == 9911


@respx.mock
def test_repository_pages_provider_lifecycle():
    client = get_test_client()
    provider = RepositoryPagesProvider(client)

    manifest = GitHubManifest(
        kind="RepositoryPages",
        metadata=ManifestMetadata(
            name="developer-portal-docs",
            organization="octocorp-cloud",
            repository="developer-service-catalog",
        ),
        spec={
            "build_type": "workflow",
            "source": {
                "branch": "main",
                "path": "/docs",
            },
            "cname": "docs.octocorp.internal",
            "https_enforced": True,
            "public": False,
        },
    )

    # 1. Read non-existent
    respx.get(
        "https://api.github.com/repos/octocorp-cloud/developer-service-catalog/pages"
    ).respond(status_code=404)
    current = provider.read(manifest)
    assert current is None

    # 2. Plan CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply CREATE
    respx.post(
        "https://api.github.com/repos/octocorp-cloud/developer-service-catalog/pages"
    ).respond(
        status_code=201,
        json={
            "status": "built",
            "html_url": "https://octocorp-cloud.github.io/developer-service-catalog",
            "build_type": "workflow",
        },
    )
    respx.put(
        "https://api.github.com/repos/octocorp-cloud/developer-service-catalog/pages"
    ).respond(
        status_code=200,
        json={
            "status": "built",
            "cname": "docs.octocorp.internal",
            "https_enforced": True,
        },
    )

    state = provider.apply(plan, manifest)
    assert state.resource_id == manifest.resource_id
    assert state.url == "https://octocorp-cloud.github.io/developer-service-catalog"
