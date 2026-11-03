"""Deep structural diff engine for GitHub IaC."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

SENSITIVE_KEYWORDS = {
    "token",
    "secret",
    "password",
    "pem",
    "client_secret",
    "private_key",
    "key_id",
    "value",
}


def is_sensitive(key_path: str) -> bool:
    """Check if the field name or path implies a sensitive secret."""
    last_key = key_path.split(".")[-1].lower()
    return any(keyword in last_key for keyword in SENSITIVE_KEYWORDS)


@dataclass
class StructuralDiff:
    """Represents structural differences between current and desired state."""

    changes: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return len(self.changes) == 0


def _values_are_equivalent(old: Any, new: Any, ignore_empty_defaults: bool) -> bool:
    """Determine if old and new values are semantically identical."""
    if old == new:
        return True

    if ignore_empty_defaults:
        if old in (None, "", [], {}) and new in (None, "", [], {}):
            return True

    # If both are lists, compare as unordered sets if items are hashable
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return False
        try:
            return set(old) == set(new)
        except TypeError:
            # Unhashable list elements (e.g. dicts)
            return old == new

    return False


def compute_diff(
    current: Optional[Dict[str, Any]],
    desired: Dict[str, Any],
    ignore_empty_defaults: bool = False,
    ignore_masked_secrets: bool = False,
    sensitive_keys: Optional[Set[str]] = None,
    prefix: str = "",
) -> StructuralDiff:
    """
    Recursively compute structural differences between current and desired state.
    Masks sensitive values and ignores server-assigned default nuances.
    """
    changes: Dict[str, Dict[str, Any]] = {}
    current_dict = current or {}

    for key, desired_val in desired.items():
        key_path = f"{prefix}.{key}" if prefix else key
        current_val = current_dict.get(key)

        # Recurse for nested dictionaries
        if isinstance(desired_val, dict) and isinstance(current_val, dict):
            nested_diff = compute_diff(
                current=current_val,
                desired=desired_val,
                ignore_empty_defaults=ignore_empty_defaults,
                ignore_masked_secrets=ignore_masked_secrets,
                sensitive_keys=sensitive_keys,
                prefix=key_path,
            )
            changes.update(nested_diff.changes)
            continue

        if not _values_are_equivalent(current_val, desired_val, ignore_empty_defaults):
            is_sec = is_sensitive(key_path) or (sensitive_keys and key_path in sensitive_keys)
            if is_sec and ignore_masked_secrets:
                if current_val in ("******", "[MASKED]") and desired_val:
                    continue

            old_masked = "******" if is_sec and current_val is not None else current_val
            new_masked = "******" if is_sec and desired_val is not None else desired_val

            changes[key_path] = {"old": old_masked, "new": new_masked}

    return StructuralDiff(changes=changes)
