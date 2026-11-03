"""Unit tests for the Pre-flight Linter and Schema Validation engine."""

from gh_iac.core.linter import Linter, LintLevel
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata


def test_linter_warns_on_disabled_push_protection():
    manifests = [
        GitHubManifest(
            kind="Repository",
            metadata=ManifestMetadata(name="public-repo", organization="octocorp"),
            spec={
                "visibility": "public",
                "secret_scanning_push_protection": False,
            },
        )
    ]
    linter = Linter()
    diagnostics = linter.lint(manifests)

    rule_ids = [d.rule_id for d in diagnostics]
    assert "SEC001" in rule_ids or "SEC002" in rule_ids
    sec_diag = next(d for d in diagnostics if d.rule_id in ("SEC001", "SEC002"))
    assert sec_diag.level == LintLevel.WARNING


def test_linter_warns_on_org_without_2fa():
    manifests = [
        GitHubManifest(
            kind="Organization",
            metadata=ManifestMetadata(name="octocorp"),
            spec={"requiresTwoFactorAuthentication": False},
        )
    ]
    linter = Linter()
    diagnostics = linter.lint(manifests)

    gov2 = next(d for d in diagnostics if d.rule_id == "GOV002")
    assert gov2.level == LintLevel.WARNING
    assert "Two-factor authentication" in gov2.message


def test_linter_errors_on_invalid_repo_name():
    manifests = [
        GitHubManifest(
            kind="Repository",
            metadata=ManifestMetadata(name="invalid name with spaces!", organization="octocorp"),
            spec={"visibility": "private"},
        )
    ]
    linter = Linter()
    diagnostics = linter.lint(manifests)

    nam1 = next(d for d in diagnostics if d.rule_id == "NAM001")
    assert nam1.level == LintLevel.ERROR
    assert "Invalid repository name" in nam1.message


def test_linter_warns_when_repo_lacks_branch_protection():
    # Repository without matching RepositoryRuleset
    manifests = [
        GitHubManifest(
            kind="Repository",
            metadata=ManifestMetadata(name="backend-api", organization="octocorp"),
            spec={"visibility": "private"},
        )
    ]
    linter = Linter()
    diagnostics = linter.lint(manifests)

    gov1 = next(d for d in diagnostics if d.rule_id == "GOV001")
    assert gov1.level == LintLevel.WARNING
    assert "No branch protection ruleset" in gov1.message
