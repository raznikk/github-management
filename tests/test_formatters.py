"""Unit tests for CLI plan formatters (human Terraform-style, JSON, Markdown)."""

import json
from io import StringIO

from rich.console import Console

from gh_iac.cli.formatters import (
    format_plan_human,
    format_plan_json,
    format_plan_markdown,
)
from gh_iac.providers.base import ActionType, ResourcePlan


def test_format_plan_json():
    plans = [
        ResourcePlan(
            resource_id="Repository/octo/app",
            kind="Repository",
            action=ActionType.CREATE,
            diff={"name": {"old": None, "new": "app"}},
            desired_state={"name": "app", "private": True},
        ),
        ResourcePlan(
            resource_id="Team/octo/devs",
            kind="Team",
            action=ActionType.UPDATE,
            diff={"description": {"old": "Old", "new": "New"}},
            desired_state={"description": "New"},
        ),
        ResourcePlan(
            resource_id="Org/octo",
            kind="Organization",
            action=ActionType.NOOP,
            diff={},
            desired_state={},
        ),
    ]

    json_str = format_plan_json(plans)
    data = json.loads(json_str)

    assert data["summary"]["create"] == 1
    assert data["summary"]["update"] == 1
    assert data["summary"]["noop"] == 1
    assert data["summary"]["total"] == 3
    assert len(data["plans"]) == 3
    assert data["plans"][0]["action"] == "CREATE"


def test_format_plan_human():
    plans = [
        ResourcePlan(
            resource_id="Repository/octo/app",
            kind="Repository",
            action=ActionType.CREATE,
            diff={"name": {"old": None, "new": "app"}, "private": {"old": None, "new": True}},
            desired_state={"name": "app", "private": True},
        ),
        ResourcePlan(
            resource_id="EnterpriseSecuritySetting/octo",
            kind="EnterpriseSecuritySetting",
            action=ActionType.UPDATE,
            diff={"push_protection": {"old": False, "new": True}},
            desired_state={"push_protection": True},
        ),
    ]

    string_io = StringIO()
    console = Console(file=string_io, force_terminal=False, color_system=None)
    format_plan_human(plans, console)
    output = string_io.getvalue()

    assert 'will be created' in output
    assert '+ resource "Repository"' in output
    assert 'will be updated in-place' in output
    assert '~ resource "EnterpriseSecuritySetting"' in output
    assert "push_protection = False -> True" in output
    assert "Plan: 1 to add, 1 to change, 0 to destroy" in output


def test_format_plan_markdown():
    plans = [
        ResourcePlan(
            resource_id="Repository/octo/app",
            kind="Repository",
            action=ActionType.CREATE,
            diff={"name": "app"},
            desired_state={"name": "app"},
        ),
        ResourcePlan(
            resource_id="Team/octo/devs",
            kind="Team",
            action=ActionType.UPDATE,
            diff={"description": {"old": "A", "new": "B"}},
            desired_state={"description": "B"},
        ),
    ]

    md = format_plan_markdown(plans)
    assert "### GitHub IaC Execution Plan" in md
    assert "🟢 CREATE" in md
    assert "🟡 UPDATE" in md
    assert "1 to add, 1 to change, 0 to destroy" in md
