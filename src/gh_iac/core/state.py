"""State storage and tracking for GitHub IaC."""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class ResourceState(BaseModel):
    """Recorded state for an individual GitHub resource."""
    resource_id: str
    kind: str
    node_id: Optional[str] = None  # GitHub GraphQL Global Node ID
    numeric_id: Optional[Union[int, str]] = None

    url: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    applied_spec: Dict[str, Any] = Field(default_factory=dict)
    last_updated: Optional[str] = None


class StateFile(BaseModel):
    version: str = "1"
    environment: str
    resources: Dict[str, ResourceState] = Field(default_factory=dict)


class StateManager:
    """Manages reading and persisting IaC resource state."""

    def __init__(self, state_path: Union[str, Path] = "gh-iac.state.json"):
        self.state_path = Path(state_path)
        self.state = StateFile(environment="default")
        self.load()

    def load(self) -> None:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.state = StateFile.model_validate(data)

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            self.state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def get_resource(self, resource_id: str) -> Optional[ResourceState]:
        return self.state.resources.get(resource_id)

    def set_resource(self, resource_id: str, state: ResourceState) -> None:
        self.state.resources[resource_id] = state

    def remove_resource(self, resource_id: str) -> None:
        if resource_id in self.state.resources:
            del self.state.resources[resource_id]
