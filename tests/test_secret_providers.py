"""Unit tests for Organization and Repository Secret Providers with Libsodium Encryption."""

import base64

import pytest
import respx
from nacl import public

from gh_iac.core.client import GitHubClient
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType
from gh_iac.providers.organization import OrganizationSecretProvider
from gh_iac.providers.repository import RepositorySecretProvider


@respx.mock
def test_org_secret_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)
    provider = OrganizationSecretProvider(client)

    # Generate a dummy receiver public key
    keypair = public.PrivateKey.generate()
    pub_key_b64 = base64.b64encode(bytes(keypair.public_key)).decode("utf-8")

    manifest = GitHubManifest(
        kind="OrganizationSecret",
        metadata=ManifestMetadata(name="DATADOG_API_KEY", organization="octocorp"),
        spec={
            "value": "super-secret-dd-token",
            "visibility": "all",
        },
    )

    # 1. Read: secret does not exist yet (404)
    respx.get("https://api.github.com/orgs/octocorp/actions/secrets/DATADOG_API_KEY").respond(
        status_code=404,
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: Expect CREATE action
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: fetch public key, then PUT encrypted secret
    respx.get("https://api.github.com/orgs/octocorp/actions/secrets/public-key").respond(
        status_code=200,
        json={"key_id": "KEY_ORG_123", "key": pub_key_b64},
    )
    put_route = respx.put(
        "https://api.github.com/orgs/octocorp/actions/secrets/DATADOG_API_KEY"
    ).respond(
        status_code=201,
    )

    state = provider.apply(plan, manifest)
    assert state.resource_id == manifest.resource_id
    assert put_route.called

    # Ensure payload contains encrypted_value and key_id
    sent_json = put_route.calls.last.request.read().decode("utf-8")
    assert "KEY_ORG_123" in sent_json
    assert "encrypted_value" in sent_json
    # Plaintext must NOT appear in request payload or state attributes
    assert "super-secret-dd-token" not in sent_json
    assert state.attributes.get("value") is None or state.attributes.get("value") == "******"


@respx.mock
def test_repo_secret_plan_and_apply():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)
    provider = RepositorySecretProvider(client)

    keypair = public.PrivateKey.generate()
    pub_key_b64 = base64.b64encode(bytes(keypair.public_key)).decode("utf-8")

    manifest = GitHubManifest(
        kind="RepositorySecret",
        metadata=ManifestMetadata(
            name="DEPLOY_TOKEN",
            organization="octocorp",
            repository="infra-app",
        ),
        spec={
            "value": "env:MY_DEPLOY_SECRET",
        },
    )

    # 1. Read: 404
    respx.get(
        "https://api.github.com/repos/octocorp/infra-app/actions/secrets/DEPLOY_TOKEN"
    ).respond(
        status_code=404,
    )
    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply
    respx.get("https://api.github.com/repos/octocorp/infra-app/actions/secrets/public-key").respond(
        status_code=200,
        json={"key_id": "KEY_REPO_456", "key": pub_key_b64},
    )
    put_route = respx.put(
        "https://api.github.com/repos/octocorp/infra-app/actions/secrets/DEPLOY_TOKEN"
    ).respond(
        status_code=204,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MY_DEPLOY_SECRET", "resolved-deploy-token-xyz")
        state = provider.apply(plan, manifest)

    assert state.resource_id == manifest.resource_id
    assert put_route.called
    sent_json = put_route.calls.last.request.read().decode("utf-8")
    assert "KEY_REPO_456" in sent_json
    assert "resolved-deploy-token-xyz" not in sent_json
