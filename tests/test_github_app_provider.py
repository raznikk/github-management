"""Unit tests for GitHubAppProvider (Enterprise and Organization Apps)."""

from pathlib import Path

import respx

from gh_iac.core.client import GitHubClient
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType
from gh_iac.providers.enterprise import GitHubAppProvider


@respx.mock
def test_create_organization_app(tmp_path: Path):
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)
    provider = GitHubAppProvider(client)

    key_output_file = tmp_path / "release-bot.pem"

    manifest = GitHubManifest(
        kind="GitHubApp",
        metadata=ManifestMetadata(
            name="octocorp-release-bot",
            organization="octocorp-cloud",
        ),
        spec={
            "url": "https://release-bot.internal",
            "description": "Automated release bot",
            "default_permissions": {
                "contents": "write",
                "pull_requests": "write",
            },
            "default_events": ["push", "pull_request"],
            "output_credentials": {
                "private_key_file": str(key_output_file),
            },
        },
    )

    # 1. Read: app does not exist initially
    respx.get("https://api.github.com/orgs/octocorp-cloud/apps").respond(
        status_code=200,
        json=[],
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST /orgs/octocorp-cloud/apps
    dummy_pem = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    )
    respx.post("https://api.github.com/orgs/octocorp-cloud/apps").respond(
        status_code=201,
        json={
            "id": 123456,
            "slug": "octocorp-release-bot",
            "node_id": "APP_123456",
            "client_id": "Iv1.abcdef123456",
            "client_secret": "secret_abc123",
            "pem": dummy_pem,
        },
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 123456
    assert state.attributes["slug"] == "octocorp-release-bot"

    # Verify PEM was written securely to file
    assert key_output_file.exists()
    assert key_output_file.read_text(encoding="utf-8") == dummy_pem

    # Verify sensitive attributes are masked in state
    assert state.attributes.get("client_secret") == "******"
    assert state.attributes.get("pem") is None or state.attributes.get("pem") == "******"


@respx.mock
def test_create_enterprise_app(tmp_path: Path):
    config = TargetConfig.create_for_ghec(token="test-pat", enterprise_slug="octocorp")
    client = GitHubClient(config)
    provider = GitHubAppProvider(client)

    key_output_file = tmp_path / "compliance-bot.pem"

    manifest = GitHubManifest(
        kind="GitHubApp",
        metadata=ManifestMetadata(
            name="enterprise-compliance-bot",
            enterprise="octocorp",
        ),
        spec={
            "url": "https://compliance.internal",
            "description": "Global compliance audit bot",
            "default_permissions": {
                "enterprise_administration": "read",
                "enterprise_audit_log": "read",
            },
            "default_events": ["audit_log_entry"],
            "output_credentials": {
                "private_key_file": str(key_output_file),
            },
        },
    )

    # 1. Read: app does not exist initially
    respx.get("https://api.github.com/enterprises/octocorp/apps").respond(
        status_code=200,
        json=[],
    )

    current = provider.read(manifest)
    assert current is None

    # 2. Plan: CREATE
    plan = provider.plan(manifest, current)
    assert plan.action == ActionType.CREATE

    # 3. Apply: POST /enterprises/octocorp/apps
    dummy_pem = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA_ENT...\n-----END RSA PRIVATE KEY-----"
    )
    respx.post("https://api.github.com/enterprises/octocorp/apps").respond(
        status_code=201,
        json={
            "id": 999888,
            "slug": "enterprise-compliance-bot",
            "node_id": "APP_999888",
            "client_id": "Iv1.ent999888",
            "client_secret": "secret_ent_xyz",
            "pem": dummy_pem,
        },
    )

    state = provider.apply(plan, manifest)
    assert state.numeric_id == 999888
    assert state.attributes["slug"] == "enterprise-compliance-bot"
    assert key_output_file.exists()
    assert key_output_file.read_text(encoding="utf-8") == dummy_pem
