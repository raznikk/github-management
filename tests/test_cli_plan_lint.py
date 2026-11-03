"""Unit tests for gh-iac plan formatting options and lint command."""

import json
from pathlib import Path

import respx
from gh_iac.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@respx.mock
def test_cli_plan_json_output(tmp_path: Path):
    manifest_file = tmp_path / "repo.yaml"
    manifest_file.write_text(
        """apiVersion: github.iac/v1alpha1
kind: Repository
metadata:
  name: api-service
  organization: octocorp
spec:
  description: API Gateway
  visibility: private
""",
        encoding="utf-8",
    )

    # 404 remote GraphQL (resource needs creation)
    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={"data": {"repository": None}},
    )

    result = runner.invoke(app, ["plan", str(manifest_file), "--token", "fake-token", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["summary"]["create"] == 1
    assert data["plans"][0]["action"] == "CREATE"


@respx.mock
def test_cli_plan_markdown_output(tmp_path: Path):
    manifest_file = tmp_path / "repo.yaml"
    manifest_file.write_text(
        """apiVersion: github.iac/v1alpha1
kind: Repository
metadata:
  name: api-service
  organization: octocorp
spec:
  description: API Gateway
  visibility: private
""",
        encoding="utf-8",
    )

    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={"data": {"repository": None}},
    )

    result = runner.invoke(app, ["plan", str(manifest_file), "--token", "fake-token", "--markdown"])
    assert result.exit_code == 0
    assert "### GitHub IaC Execution Plan" in result.output
    assert "🟢 CREATE" in result.output


def test_cli_lint_command(tmp_path: Path):
    manifest_file = tmp_path / "bad_repo.yaml"
    manifest_file.write_text(
        """apiVersion: github.iac/v1alpha1
kind: Repository
metadata:
  name: "invalid name with space"
  organization: octocorp
spec:
  visibility: private
""",
        encoding="utf-8",
    )

    # Lint should exit with code 1 due to error
    result = runner.invoke(app, ["lint", str(manifest_file)])
    assert result.exit_code == 1
    assert "NAM001" in result.output
