"""Plan output formatters: colorized Terraform-style terminal, JSON, and PR Markdown."""

import json
from typing import List

from rich.console import Console

from gh_iac.providers.base import ActionType, ResourcePlan


def format_plan_json(plans: List[ResourcePlan]) -> str:
    """Format execution plan as machine-readable JSON for CI/CD."""
    creates = sum(1 for p in plans if p.action == ActionType.CREATE)
    updates = sum(1 for p in plans if p.action == ActionType.UPDATE)
    deletes = sum(1 for p in plans if p.action == ActionType.DELETE)
    noops = sum(1 for p in plans if p.action == ActionType.NOOP)

    payload = {
        "summary": {
            "create": creates,
            "update": updates,
            "delete": deletes,
            "noop": noops,
            "total": len(plans),
        },
        "plans": [
            {
                "resource_id": p.resource_id,
                "kind": p.kind,
                "action": p.action.value,
                "desired_state": p.desired_state,
                "diff": p.diff,
            }
            for p in plans
        ],
    }
    return json.dumps(payload, indent=2)


def format_plan_human(plans: List[ResourcePlan], console: Console) -> None:
    """Format execution plan in colorized Terraform-style terminal blocks."""
    creates = sum(1 for p in plans if p.action == ActionType.CREATE)
    updates = sum(1 for p in plans if p.action == ActionType.UPDATE)
    deletes = sum(1 for p in plans if p.action == ActionType.DELETE)

    active_plans = [p for p in plans if p.action != ActionType.NOOP]

    if not active_plans:
        console.print(
            "[bold green]No changes. Your infrastructure matches the configuration.[/bold green]"
        )
        return

    console.print("\n[bold]GitHub IaC will perform the following actions:[/bold]\n")

    for p in active_plans:
        clean_id = p.resource_id.split("/", 1)[-1] if "/" in p.resource_id else p.resource_id

        if p.action == ActionType.CREATE:
            console.print(f"  [bold green]# {p.kind}.{clean_id} will be created:[/bold green]")
            console.print(f'  [green]+ resource "{p.kind}" "{clean_id}" {{[/green]')
            for k, v in sorted(p.desired_state.items()):
                if v is not None and v != "":
                    console.print(
                        f"  [green]+   {k} = {json.dumps(v) if isinstance(v, (dict, list)) else v}[/green]"
                    )
            console.print("  [green]+ }[/green]\n")

        elif p.action == ActionType.UPDATE:
            console.print(
                f"  [bold yellow]# {p.kind}.{clean_id} will be updated in-place:[/bold yellow]"
            )
            console.print(f'  [yellow]~ resource "{p.kind}" "{clean_id}" {{[/yellow]')
            for k, change in sorted(p.diff.items()):
                if isinstance(change, dict) and "old" in change and "new" in change:
                    old_v = change["old"]
                    new_v = change["new"]
                    console.print(f"  [yellow]~   {k} = {old_v} -> {new_v}[/yellow]")
                else:
                    console.print(f"  [yellow]~   {k} = {change}[/yellow]")
            console.print("  [yellow]~ }[/yellow]\n")

        elif p.action == ActionType.DELETE:
            console.print(f"  [bold red]# {p.kind}.{clean_id} will be destroyed:[/bold red]")
            console.print(f'  [red]- resource "{p.kind}" "{clean_id}" {{[/red]')
            for k, v in sorted(p.desired_state.items()):
                console.print(f"  [red]-   {k} = {v}[/red]")
            console.print("  [red]- }[/red]\n")

    console.print(
        f"[bold]Plan:[/bold] [green]{creates} to add[/green], "
        f"[yellow]{updates} to change[/yellow], "
        f"[red]{deletes} to destroy[/red].\n"
    )


def format_plan_markdown(plans: List[ResourcePlan]) -> str:
    """Format execution plan as GitHub Flavored Markdown for Pull Request comments."""
    creates = sum(1 for p in plans if p.action == ActionType.CREATE)
    updates = sum(1 for p in plans if p.action == ActionType.UPDATE)
    deletes = sum(1 for p in plans if p.action == ActionType.DELETE)
    noops = sum(1 for p in plans if p.action == ActionType.NOOP)

    md: List[str] = []
    md.append("### GitHub IaC Execution Plan")
    md.append("")
    md.append(
        f"**Plan:** {creates} to add, {updates} to change, {deletes} to destroy, {noops} unchanged."
    )
    md.append("")

    active = [p for p in plans if p.action != ActionType.NOOP]
    if not active:
        md.append("> ✨ **No changes.** Remote infrastructure matches declarative manifests.")
        return "\n".join(md)

    md.append("| Action | Kind | Resource Identifier | Changes |")
    md.append("| :--- | :--- | :--- | :--- |")

    for p in active:
        clean_id = p.resource_id.split("/", 1)[-1] if "/" in p.resource_id else p.resource_id
        if p.action == ActionType.CREATE:
            badge = "🟢 CREATE"
            diff_summary = f"{len(p.desired_state)} attributes"
        elif p.action == ActionType.UPDATE:
            badge = "🟡 UPDATE"
            diff_summary = ", ".join(f"`{k}`" for k in list(p.diff.keys())[:5])
        elif p.action == ActionType.DELETE:
            badge = "🔴 DELETE"
            diff_summary = "Resource unmanaged/pruned"
        else:
            badge = "⚪ NOOP"
            diff_summary = "In sync"

        md.append(f"| {badge} | `{p.kind}` | `{clean_id}` | {diff_summary} |")

    md.append("")
    md.append("<details><summary>📋 View Detailed Plan Diff</summary>")
    md.append("")
    md.append("```diff")
    for p in active:
        clean_id = p.resource_id.split("/", 1)[-1] if "/" in p.resource_id else p.resource_id
        if p.action == ActionType.CREATE:
            md.append(f'+ resource "{p.kind}" "{clean_id}" {{')
            for k, v in sorted(p.desired_state.items()):
                if v is not None and v != "":
                    md.append(f"+   {k} = {v}")
            md.append("+ }")
        elif p.action == ActionType.UPDATE:
            md.append(f'! resource "{p.kind}" "{clean_id}" {{')
            for k, change in sorted(p.diff.items()):
                if isinstance(change, dict) and "old" in change and "new" in change:
                    md.append(f"!   {k}: {change['old']} => {change['new']}")
                else:
                    md.append(f"!   {k}: {change}")
            md.append("! }")
    md.append("```")
    md.append("</details>")

    return "\n".join(md)
