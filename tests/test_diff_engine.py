"""Unit tests for the Robust Diff Engine."""

from gh_iac.core.diff import compute_diff


def test_diff_identical_dicts():
    d1 = {"name": "repo1", "visibility": "private"}
    d2 = {"name": "repo1", "visibility": "private"}
    diff = compute_diff(current=d1, desired=d2)
    assert diff.is_empty
    assert diff.changes == {}


def test_diff_ignores_list_ordering():
    current = {"permissions": ["pull", "triage", "push"]}
    desired = {"permissions": ["push", "pull", "triage"]}
    diff = compute_diff(current=current, desired=desired)
    assert diff.is_empty


def test_diff_detects_list_element_changes():
    current = {"permissions": ["pull", "push"]}
    desired = {"permissions": ["pull", "admin"]}
    diff = compute_diff(current=current, desired=desired)
    assert not diff.is_empty
    assert "permissions" in diff.changes
    assert diff.changes["permissions"]["old"] == ["pull", "push"]
    assert diff.changes["permissions"]["new"] == ["pull", "admin"]


def test_diff_nested_dict_changes():
    current = {
        "settings": {"domain": "https://splunk-a.internal", "enabled": True},
        "name": "audit-sink",
    }
    desired = {
        "settings": {"domain": "https://splunk-b.internal", "enabled": True},
        "name": "audit-sink",
    }
    diff = compute_diff(current=current, desired=desired)
    assert not diff.is_empty
    assert "settings.domain" in diff.changes
    assert diff.changes["settings.domain"]["old"] == "https://splunk-a.internal"
    assert diff.changes["settings.domain"]["new"] == "https://splunk-b.internal"


def test_diff_masks_sensitive_fields():
    current = {"token": "secret-12345", "url": "https://app.internal"}
    desired = {"token": "secret-67890", "url": "https://app.internal"}
    diff = compute_diff(current=current, desired=desired)
    assert not diff.is_empty
    assert diff.changes["token"]["old"] == "******"
    assert diff.changes["token"]["new"] == "******"


def test_diff_ignores_none_and_empty_defaults():
    current = {"description": None, "has_wiki": False}
    desired = {"description": "", "has_wiki": False}
    diff = compute_diff(current=current, desired=desired, ignore_empty_defaults=True)
    assert diff.is_empty
