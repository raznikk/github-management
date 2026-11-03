"""Unit tests for gh-iac drift and import commands."""

from pathlib import Path

import respx
from gh_iac.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@respx.mock
def test_cli_drift_detected(tmp_path: Path):
    manifest_file = tmp_path / "repo.yaml"
    manifest_file.write_text(
        """apiVersion: github.iac/v1alpha1
kind: Repository
metadata:
  name: test-repo
  organization: octocorp
spec:
  description: Desired description
  visibility: private
""",
        encoding="utf-8",
    )

    # Remote GraphQL response with drifted description
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {
                "repository": {
                    "id": "REPO_123",
                    "name": "test-repo",
                    "description": "Remote drifted description",
                    "isPrivate": True,
                    "hasWikiEnabled": False,
                    "hasIssuesEnabled": True,
                    "hasProjectsEnabled": False,
                    "deleteBranchOnMerge": True,
                    "defaultBranchRef": {"name": "main"},
                }
            }
        },
    )

    result = runner.invoke(app, ["drift", str(manifest_file), "--token", "test-token"])
    assert result.exit_code == 2
    assert "DRIFT DETECTED" in result.output or "description" in result.output


@respx.mock
def test_cli_import_repository():
    # Mock remote repository
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {
                "repository": {
                    "id": "REPO_999",
                    "name": "imported-repo",
                    "description": "Legacy existing repo",
                    "isPrivate": True,
                    "hasWikiEnabled": False,
                    "hasIssuesEnabled": True,
                    "hasProjectsEnabled": False,
                    "deleteBranchOnMerge": True,
                    "defaultBranchRef": {"name": "main"},
                }
            }
        },
    )

    result = runner.invoke(
        app,
        ["import", "Repository", "octocorp/imported-repo", "--token", "test-token"],
    )
    assert result.exit_code == 0
    assert "apiVersion: github.iac/v1alpha1" in result.output
    assert "kind: Repository" in result.output
    assert "imported-repo" in result.output
