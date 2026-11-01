"""CLI for GitHub IaC."""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from gh_iac.core.client import GitHubClient
from gh_iac.core.engine import Engine
from gh_iac.core.target import TargetConfig
from gh_iac.providers.base import ActionType

app = typer.Typer(
    name="gh-iac",
    help="Infrastructure as Code (IaC) management for GitHub (GHEC, GHES, EMU).",
    add_completion=False,
)
console = Console()


def get_client(
    target: str,
    token: Optional[str] = None,
    enterprise: Optional[str] = None,
    hostname: Optional[str] = None,
) -> GitHubClient:
    auth_token = token or os.environ.get("GITHUB_TOKEN", "")
    if not auth_token:
        console.print("[red]Error: GITHUB_TOKEN environment variable or --token option is required.[/red]")
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
        config = TargetConfig.create_for_ghes(hostname=host, token=auth_token, enterprise_slug=ent_slug)
    else:
        console.print(f"[red]Error: Unsupported target environment '{target}'. Choose ghec, ghes, or emu.[/red]")
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
        console.print(f"[green]✓ Successfully validated {len(manifests)} manifests![/green]")
        table = Table(title="Validated GitHub Constructs")
        table.add_column("Kind", style="cyan")
        table.add_column("Resource ID", style="magenta")
        for m in manifests:
            table.add_row(m.kind, m.resource_id)
        console.print(table)
    except Exception as e:
        console.print(f"[red]Validation failed: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def plan(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
    target: str = typer.Option("ghec", "--target", "-t", help="Target: ghec, ghes, or emu"),
    token: Optional[str] = typer.Option(None, "--token", help="GitHub Token"),
    enterprise: Optional[str] = typer.Option(None, "--enterprise", "-e", help="Enterprise slug"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="GHES hostname"),
) -> None:
    """Preview actions (Create, Update, NoOp) against GitHub."""
    client = get_client(target, token, enterprise, hostname)
    engine = Engine(client)
    manifests = Engine.load_manifests(path)
    plans = engine.plan(manifests)

    table = Table(title=f"IaC Execution Plan (Target: {target.upper()})")
    table.add_column("Action", style="bold")
    table.add_column("Kind", style="cyan")
    table.add_column("Resource ID", style="magenta")
    table.add_column("Diff Summary", style="yellow")

    for p in plans:
        color = "green" if p.action == ActionType.CREATE else "yellow" if p.action == ActionType.UPDATE else "white"
        diff_str = str(list(p.diff.keys())) if p.diff else "None"
        table.add_row(f"[{color}]{p.action.value}[/{color}]", p.kind, p.resource_id, diff_str)

    console.print(table)


@app.command()
def apply(
    path: Path = typer.Argument(..., help="Path to manifest file or directory"),
    target: str = typer.Option("ghec", "--target", "-t", help="Target: ghec, ghes, or emu"),
    token: Optional[str] = typer.Option(None, "--token", help="GitHub Token"),
    enterprise: Optional[str] = typer.Option(None, "--enterprise", "-e", help="Enterprise slug"),
    hostname: Optional[str] = typer.Option(None, "--hostname", help="GHES hostname"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip interactive approval"),
) -> None:
    """Apply declarative configuration to GitHub."""
    client = get_client(target, token, enterprise, hostname)
    engine = Engine(client)
    manifests = engine.load_manifests(path)
    plans = engine.plan(manifests)

    actions = [p for p in plans if p.action != ActionType.NOOP]
    if not actions:
        console.print("[green]No changes needed. Infrastructure is up to date.[/green]")
        return

    console.print(f"Plan: {len([p for p in plans if p.action == ActionType.CREATE])} to create, {len([p for p in plans if p.action == ActionType.UPDATE])} to update.")
    if not auto_approve:
        confirmed = typer.confirm("Do you want to apply these changes?")
        if not confirmed:
            console.print("[yellow]Apply cancelled.[/yellow]")
            return

    engine.apply(plans, manifests)
    console.print("[bold green]✓ Apply complete![/bold green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
