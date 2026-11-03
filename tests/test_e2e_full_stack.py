"""End-to-end integration test validating the entire full-stack lifecycle."""

from pathlib import Path

import pytest

from gh_iac.core.client import GitHubClient
from gh_iac.core.dag import DependencyGraph
from gh_iac.core.diff import compute_diff
from gh_iac.core.engine import Engine
from gh_iac.core.linter import Linter
from gh_iac.core.state import LocalStateBackend, ResourceState, StateManager
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType


def test_full_stack_e2e_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SPLUNK_HEC_TOKEN", "splunk-secret-12345")
    monkeypatch.setenv("DD_SECRET_VAL", "datadog-key-xyz")
    monkeypatch.setenv("SNYK_API_TOKEN", "snyk-token-abc")
    monkeypatch.setenv("ORG_WEBHOOK_SECRET", "webhook-secret-999")
    monkeypatch.setenv("AWS_PROD_DEPLOY_KEY", "aws-super-secret-key")

    examples_path = Path(__file__).parent.parent / "examples" / "full_stack.yaml"
    assert examples_path.exists()

    # 1. Load manifests
    manifests = Engine.load_manifests(examples_path)
    assert len(manifests) == 22

    # 2. Pre-flight linting
    linter = Linter()
    diagnostics = linter.lint(manifests)
    errors = [d for d in diagnostics if d.level == "ERROR"]
    assert len(errors) == 0, f"Expected 0 errors, got: {errors}"

    # 3. DAG Topological tiering & Cycle validation
    dag = DependencyGraph(manifests)
    tiers = dag.get_execution_tiers()
    assert len(tiers) >= 3

    # Organization must precede Repository and Team
    all_kinds_in_order = [m.kind for tier in tiers for m in tier]
    assert all_kinds_in_order.index("Organization") < all_kinds_in_order.index("Repository")
    assert all_kinds_in_order.index("Organization") < all_kinds_in_order.index("Team")
    assert all_kinds_in_order.index("Repository") < all_kinds_in_order.index("RepositoryRuleset")

    # 4. State Management with AES-GCM Encryption
    state_file = tmp_path / "prod.state.bin"
    passphrase = "enterprise-vault-passphrase-2026"
    backend = LocalStateBackend(state_path=state_file, passphrase=passphrase)
    state_mgr = StateManager(backend=backend)

    # 5. Mock Client and Engine
    config = TargetConfig.create_for_ghec(token="test-pat-token", enterprise_slug="octocorp")
    client = GitHubClient(config)
    engine = Engine(client, state_manager=state_mgr, concurrency=4)

    # Mock provider read to return None (all 22 resources need creation)
    for m in manifests:
        provider = engine.get_provider(m.kind)
        monkeypatch.setattr(provider, "read", lambda manifest: None)
        monkeypatch.setattr(
            provider,
            "apply",
            lambda plan, manifest: ResourceState(
                resource_id=plan.resource_id,
                kind=plan.kind,
                node_id=f"NODE_{plan.resource_id}",
                attributes=plan.desired_state,
                applied_spec=manifest.spec,
            ),
        )

    # 6. Plan execution
    plans = engine.plan(manifests)
    assert len(plans) == 22
    assert all(p.action == ActionType.CREATE for p in plans)

    # 7. Apply execution
    applied = engine.apply(plans, manifests)
    assert len(applied) == 22

    # 8. Verify state was persisted encrypted to disk
    raw_disk_bytes = state_file.read_bytes()
    assert b"octocorp" not in raw_disk_bytes  # Encrypted with AES-GCM!

    # 9. Reload state and verify all resources recorded
    new_state_mgr = StateManager(backend=LocalStateBackend(state_path=state_file, passphrase=passphrase))
    assert len(new_state_mgr.state.resources) == 22
    assert "Repository/org:octocorp-cloud/core-infrastructure" in new_state_mgr.state.resources
    assert "OrganizationRuleset/org:octocorp-cloud/org-default-protection" in new_state_mgr.state.resources
    assert "OrganizationVariable/org:octocorp-cloud/DOCKER_REGISTRY_URL" in new_state_mgr.state.resources

    # 10. Drift check: With remote matching state, diff is empty
    for m in manifests:
        recorded = new_state_mgr.get_resource(m.resource_id)
        assert recorded is not None
        diff = compute_diff(recorded.attributes, m.spec, ignore_empty_defaults=True, ignore_masked_secrets=True)
        assert diff.is_empty
