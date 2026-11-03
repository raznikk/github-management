"""CLI for GitHub IaC."""

import os
from pathlib import Path
from typing import Optional

import typer
from gh_iac.cli.formatters import (
    format_plan_human,
    format_plan_json,
    format_plan_markdown,
)
from gh_iac.core.client import GitHubClient
from gh_iac.core.engine import Engine
from gh_iac.core.linter import Linter, LintLevel
from gh_iac.core.state import LocalStateBackend, StateManager
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="gh-iac",
    help="Infrastructure as Code (IaC) management for GitHub (GHEC, GHES, EMU).",
    add_completion=False,
)
console = Console()


def get_state_manager(
    state_file: Optional[Path] = None,
    passphrase: Optional[str] = None,
) -> StateManager:
    path = state_file or Path(os.environ.get("GITHUB_IAC_STATE_FILE", "gh-iac.state.json"))
    secret = passphrase or os.environ.get("GITHUB_IAC_STATE_PASSPHRASE")
    backend = LocalStateBackend(state_path=path, passphrase=secret)
    return StateManager(backend=backend)


def get_client(
    target: str,
    token: Optional[str] = None,
    enterprise: Optional[str] = None,
    hostname: Optional[str] = None,
) -> GitHubClient:
    auth_token = token or os.environ.get("GITHUB_TOKEN", "")
    if not auth_token:
        console.print(
            "[red]Error: GITHUB_TOKEN environment variable or --token option is required.[/red]"
        )
        raise typer.Exit(code=1)

    ent_slug = enterprise or os.environ.get("GITHUB_ENTERPRISE")

    if target.lower() == "ghec":
        config = TargetConfig.create_for_ghec(token=auth_token, enterprise_slug=ent_slug)
    elif target.lower() in ["emu", "ghec_emu"]:
        if not ent_slug:
            console.print("[red]Error: --enterprise is required for GHEC EMU target.[/red]")
            raise typer.Exit(code=1)
        config = TargetConfig.create_for_emu(token=auth_token, enterprise_slug=ent_slug)
    elif target.lower() == "ghes":
        host = hostname or os.environ.get("GITHUB_HOSTNAME")
        if not host:
            console.print("[red]Error: --hostname is required for GHES target.[/red]")
            raise typer.Exit(code=1)
        config = TargetConfig.create_for_ghes(
            hostname=host, token=auth_token, enterprise_slug=ent_slug
        )
    else:
        console.print(
            f"[red]Error: Unsupported target environment '{target}'. Choose ghec, ghes, or emu.[/red]"
        )
        raise typer.Exit(code=1)

    return GitHubClient(config)


@app.command()
def validate(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
) -> None:
    """Validate syntax and schema of declarative manifests."""
    if not path.exists():
        console.print(f"[red]Path '{path}' does not exist.[/red]")
        raise typer.Exit(code=1)

    try:
        manifests = Engine.load_manifests(path)
        console.print(
            f"[green]✓ Successfully parsed and validated schema of {len(manifests)} manifests![/green]"
        )
        table = Table(title="Validated GitHub Constructs")
        table.add_column("Kind", style="cyan")
        table.add_column("Resource ID", style="magenta")
        for m in manifests:
            table.add_row(m.kind, m.resource_id)
        console.print(table)

        # Pre-flight lint check
        linter = Linter()
        diagnostics = linter.lint(manifests)
        errors = [d for d in diagnostics if d.level == LintLevel.ERROR]
        warnings = [d for d in diagnostics if d.level == LintLevel.WARNING]
        if warnings:
            console.print(
                f"[yellow]Found {len(warnings)} security/governance lint warning(s). Run 'gh-iac lint' for full audit.[/yellow]"
            )
        if errors:
            console.print(f"[bold red]Found {len(errors)} syntax/naming error(s)![/bold red]")
            for err in errors:
                console.print(f"  [red]✗ [{err.rule_id}] {err.resource_id}: {err.message}[/red]")
            raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Validation failed: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def lint(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
    strict: bool = typer.Option(
        False, "--strict", help="Fail with exit code 1 on warnings as well as errors"
    ),
) -> None:
    """Run pre-flight security, governance, and naming linter on manifests."""
    if not path.exists():
        console.print(f"[red]Path '{path}' does not exist.[/red]")
        raise typer.Exit(code=1)

    manifests = Engine.load_manifests(path)
    linter = Linter()
    diagnostics = linter.lint(manifests)

    if not diagnostics:
        console.print(
            "[bold green]✓ All manifests passed linting checks with 0 issues![/bold green]"
        )
        return

    table = Table(title="GitHub IaC Lint Diagnostics")
    table.add_column("Level", style="bold")
    table.add_column("Rule", style="cyan")
    table.add_column("Resource", style="magenta")
    table.add_column("Message", style="yellow")

    errors = 0
    warnings = 0

    for d in diagnostics:
        if d.level == LintLevel.ERROR:
            lvl_str = "[bold red]ERROR[/bold red]"
            errors += 1
        elif d.level == LintLevel.WARNING:
            lvl_str = "[yellow]WARN[/yellow]"
            warnings += 1
        else:
            lvl_str = "[cyan]INFO[/cyan]"

        table.add_row(lvl_str, d.rule_id, d.resource_id, d.message)

    console.print(table)
    console.print(
        f"\nAudit complete: [red]{errors} error(s)[/red], [yellow]{warnings} warning(s)[/yellow]."
    )

    if errors > 0 or (strict and warnings > 0):
        raise typer.Exit(code=1)


@app.command()
def plan(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
    target: str = typer.Option("ghec", "--target", "-t", help="Target: ghec, ghes, or emu"),
    token: Optional[str] = typer.Option(None, "--token", help="GitHub Token"),
    enterprise: Optional[str] = typer.Option(None, "--enterprise", "-e", help="Enterprise slug"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="GHES hostname"),
    state_file: Optional[Path] = typer.Option(
        None, "--state-file", help="Path to local state file"
    ),
    state_passphrase: Optional[str] = typer.Option(
        None, "--state-passphrase", help="Passphrase for state encryption"
    ),
    concurrency: int = typer.Option(
        5, "--concurrency", "-c", help="Number of concurrent DAG workers"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output execution plan as JSON for CI/CD pipelines"
    ),
    markdown_output: bool = typer.Option(
        False, "--markdown", help="Output execution plan as GitHub Markdown for PR comments"
    ),
) -> None:
    """Preview actions (Create, Update, NoOp) against GitHub."""
    client = get_client(target, token, enterprise, hostname)
    state_mgr = get_state_manager(state_file, state_passphrase)
    engine = Engine(client, state_manager=state_mgr, concurrency=concurrency)
    manifests = Engine.load_manifests(path)
    plans = engine.plan(manifests)

    if json_output:
        typer.echo(format_plan_json(plans))
        return

    if markdown_output:
        typer.echo(format_plan_markdown(plans))
        return

    format_plan_human(plans, console)


@app.command()
def apply(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
    target: str = typer.Option("ghec", "--target", "-t", help="Target: ghec, ghes, or emu"),
    token: Optional[str] = typer.Option(None, "--token", help="GitHub Token"),
    enterprise: Optional[str] = typer.Option(None, "--enterprise", "-e", help="Enterprise slug"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="GHES hostname"),
    state_file: Optional[Path] = typer.Option(
        None, "--state-file", help="Path to local state file"
    ),
    state_passphrase: Optional[str] = typer.Option(
        None, "--state-passphrase", help="Passphrase for state encryption"
    ),
    concurrency: int = typer.Option(
        5, "--concurrency", "-c", help="Number of concurrent DAG workers"
    ),
    auto_approve: bool = typer.Option(
        False, "--auto-approve", "-y", help="Skip interactive approval"
    ),
) -> None:
    """Apply declarative configuration to GitHub."""
    client = get_client(target, token, enterprise, hostname)
    state_mgr = get_state_manager(state_file, state_passphrase)
    engine = Engine(client, state_manager=state_mgr, concurrency=concurrency)
    manifests = engine.load_manifests(path)
    plans = engine.plan(manifests)

    actions = [p for p in plans if p.action != ActionType.NOOP]
    if not actions:
        console.print("[green]No changes needed. Infrastructure is up to date.[/green]")
        return

    console.print(
        f"Plan: {len([p for p in plans if p.action == ActionType.CREATE])} to create, {len([p for p in plans if p.action == ActionType.UPDATE])} to update."
    )
    if not auto_approve:
        confirmed = typer.confirm("Do you want to apply these changes?")
        if not confirmed:
            console.print("[yellow]Apply cancelled.[/yellow]")
            return

    engine.apply(plans, manifests)
    console.print("[bold green]✓ Apply complete![/bold green]")


@app.command()
def drift(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
    target: str = typer.Option("ghec", "--target", "-t", help="Target: ghec, ghes, or emu"),
    token: Optional[str] = typer.Option(None, "--token", help="GitHub Token"),
    enterprise: Optional[str] = typer.Option(None, "--enterprise", "-e", help="Enterprise slug"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="GHES hostname"),
    state_file: Optional[Path] = typer.Option(
        None, "--state-file", help="Path to local state file"
    ),
    state_passphrase: Optional[str] = typer.Option(
        None, "--state-passphrase", help="Passphrase for state encryption"
    ),
    concurrency: int = typer.Option(
        5, "--concurrency", "-c", help="Number of concurrent DAG workers"
    ),
) -> None:
    """Detect configuration drift between declared manifests and live GitHub environment."""
    from gh_iac.core.diff import compute_diff

    client = get_client(target, token, enterprise, hostname)
    state_mgr = get_state_manager(state_file, state_passphrase)
    engine = Engine(client, state_manager=state_mgr, concurrency=concurrency)
    manifests = engine.load_manifests(path)

    drift_detected = False
    table = Table(title="GitHub IaC Drift Detection Report")
    table.add_column("Kind", style="cyan")
    table.add_column("Resource ID", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Drift Details", style="yellow")

    for m in manifests:
        provider = engine.get_provider(m.kind)
        current = provider.read(m)
        if not current:
            table.add_row(
                m.kind, m.resource_id, "[red]MISSING[/red]", "Resource does not exist on remote"
            )
            drift_detected = True
            continue

        diff = compute_diff(
            current.attributes, m.spec, ignore_empty_defaults=True, ignore_masked_secrets=True
        )
        if not diff.is_empty:
            drift_details = ", ".join(
                [f"{k}: '{v['old']}' -> '{v['new']}'" for k, v in diff.changes.items()]
            )
            table.add_row(
                m.kind, m.resource_id, "[bold red]DRIFT DETECTED[/bold red]", drift_details
            )
            drift_detected = True
        else:
            table.add_row(m.kind, m.resource_id, "[green]IN SYNC[/green]", "Matches desired state")

    console.print(table)
    if drift_detected:
        console.print(
            "[bold red]⚠ Drift detected between desired state and remote GitHub environment.[/bold red]"
        )
        raise typer.Exit(code=2)
    else:
        console.print("[bold green]✓ All resources are in sync with desired state.[/bold green]")


@app.command(name="import")
def import_resource(
    kind: str = typer.Argument(..., help="Construct Kind (e.g. Repository, Organization, Team)"),
    identifier: str = typer.Argument(
        ..., help="Identifier (e.g. 'octocorp/core-infra' or 'octocorp')"
    ),
    target: str = typer.Option("ghec", "--target", "-t", help="Target: ghec, ghes, or emu"),
    token: Optional[str] = typer.Option(None, "--token", help="GitHub Token"),
    enterprise: Optional[str] = typer.Option(None, "--enterprise", "-e", help="Enterprise slug"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="GHES hostname"),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="File to write generated YAML manifest to"
    ),
) -> None:
    """Import pre-existing GitHub resources into declarative YAML manifests."""
    import yaml
    from gh_iac.core.manifest import GitHubManifest, ManifestMetadata

    client = get_client(target, token, enterprise, hostname)
    engine = Engine(client)
    provider = engine.get_provider(kind)

    # Parse metadata based on kind & identifier
    if "/" in identifier:
        parts = identifier.split("/")
        if kind == "Repository":
            metadata = ManifestMetadata(name=parts[1], organization=parts[0])
        elif kind == "Team":
            metadata = ManifestMetadata(name=parts[1], organization=parts[0])
        else:
            metadata = ManifestMetadata(name=parts[-1], organization=parts[0])
    else:
        if kind in ("Organization",):
            metadata = ManifestMetadata(name=identifier)
        elif kind in ("EnterprisePolicy", "EnterpriseSecuritySetting", "EnterpriseCustomRole"):
            metadata = ManifestMetadata(name=identifier, enterprise=enterprise or identifier)
        else:
            metadata = ManifestMetadata(name=identifier)

    dummy_manifest = GitHubManifest(kind=kind, metadata=metadata, spec={})
    current = provider.read(dummy_manifest)

    if not current:
        console.print(
            f"[red]Error: Resource '{identifier}' of kind '{kind}' was not found on remote GitHub target.[/red]"
        )
        raise typer.Exit(code=1)

    # Filter out read-only identifiers from spec
    filtered_spec = {
        k: v
        for k, v in current.attributes.items()
        if k not in ("id", "node_id", "numeric_id", "url") and v is not None
    }

    manifest_obj = {
        "apiVersion": "github.iac/v1alpha1",
        "kind": kind,
        "metadata": {k: v for k, v in metadata.model_dump().items() if v},
        "spec": filtered_spec,
    }

    yaml_str = yaml.dump(manifest_obj, sort_keys=False, default_flow_style=False)
    if output_file:
        output_file.write_text(yaml_str, encoding="utf-8")
        console.print(f"[green]✓ Successfully imported {kind} into '{output_file}'[/green]")
    else:
        console.print(yaml_str)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
