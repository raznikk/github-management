"""Unit tests for GitHub Client, Manifests, State, and Providers."""

from pathlib import Path

import pytest
import respx
from gh_iac.core.client import GitHubAPIError, GitHubClient
from gh_iac.core.engine import Engine
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata
from gh_iac.core.state import ResourceState, StateManager
from gh_iac.core.target import TargetConfig, TargetEnvironment
from gh_iac.providers.base import ActionType


def test_target_config():
    ghec = TargetConfig.create_for_ghec(token="test-pat", enterprise_slug="octo")
    assert ghec.environment == TargetEnvironment.GHEC
    assert ghec.graphql_url == "https://api.github.com/graphql"

    emu = TargetConfig.create_for_emu(token="emu-token", enterprise_slug="octo-emu")
    assert emu.environment == TargetEnvironment.GHEC_EMU
    assert "octo-emu" in emu.scim_base_url

    ghes = TargetConfig.create_for_ghes(hostname="gh.internal.corp", token="ghes-pat")
    assert ghes.environment == TargetEnvironment.GHES
    assert ghes.base_url == "https://gh.internal.corp/api/v3"
    assert ghes.graphql_url == "https://gh.internal.corp/api/graphql"


@respx.mock
def test_graphql_client_success():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)

    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={"data": {"viewer": {"login": "octocat"}}},
    )

    data = client.graphql("query { viewer { login } }")
    assert data["viewer"]["login"] == "octocat"


@respx.mock
def test_graphql_client_error():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)

    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={"errors": [{"message": "Field 'invalid' does not exist"}]},
    )

    with pytest.raises(GitHubAPIError) as exc_info:
        client.graphql("query { invalid }")
    assert "Field 'invalid' does not exist" in str(exc_info.value)


@respx.mock
def test_rest_client_fallback():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)

    respx.get("https://api.github.com/orgs/octocorp/custom-repository-roles").respond(
        status_code=200,
        json={"total_count": 1, "custom_roles": [{"id": 42, "name": "security-auditor"}]},
    )

    data = client.rest("GET", "/orgs/octocorp/custom-repository-roles")
    assert data["total_count"] == 1
    assert data["custom_roles"][0]["name"] == "security-auditor"


def test_manifest_resource_id():
    m = GitHubManifest(
        kind="RepositoryRuleset",
        metadata=ManifestMetadata(
            name="protect-main",
            organization="my-org",
            repository="infra",
        ),
        spec={"enforcement": "active"},
    )
    assert m.resource_id == "RepositoryRuleset/org:my-org/repo:infra/protect-main"


def test_state_manager(tmp_path: Path):
    state_file = tmp_path / "state.json"
    mgr = StateManager(state_path=state_file)

    res = ResourceState(
        resource_id="Repository/org:test/repo:app",
        kind="Repository",
        node_id="MDEwOlJlcG9zaXRvcnkx",
        attributes={"name": "app"},
    )
    mgr.set_resource(res.resource_id, res)
    mgr.save()

    # Re-read
    mgr2 = StateManager(state_path=state_file)
    loaded = mgr2.get_resource(res.resource_id)
    assert loaded is not None
    assert loaded.node_id == "MDEwOlJlcG9zaXRvcnkx"


@respx.mock
def test_engine_plan_and_apply(tmp_path: Path):
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)
    state_file = tmp_path / "state.json"
    state_mgr = StateManager(state_path=state_file)
    engine = Engine(client=client, state_manager=state_mgr)

    # Mock GraphQL query: Repository not existing initially
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={"data": {"repository": None, "organization": {"id": "ORG_123"}}},
    )
    # Mock REST create repo fallback
    respx.post("https://api.github.com/orgs/my-org/repos").respond(
        status_code=201,
        json={"id": 101, "node_id": "REPO_NODE_101", "name": "test-repo"},
    )

    manifest = GitHubManifest(
        kind="Repository",
        metadata=ManifestMetadata(name="test-repo", organization="my-org"),
        spec={"description": "Test Repo", "visibility": "private"},
    )

    plans = engine.plan([manifest])
    assert len(plans) == 1
    assert plans[0].action == ActionType.CREATE

    states = engine.apply(plans, [manifest])
    assert len(states) == 1
    assert states[0].resource_id == manifest.resource_id
    assert state_mgr.get_resource(manifest.resource_id) is not None
