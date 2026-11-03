"""Base interface for all GitHub Construct Providers."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional

from gh_iac.core.client import GitHubClient
from gh_iac.core.manifest import GitHubManifest
from gh_iac.core.state import ResourceState
from pydantic import BaseModel


class ActionType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class ResourcePlan(BaseModel):
    resource_id: str
    kind: str
    action: ActionType
    diff: Dict[str, Any]
    current_state: Optional[Dict[str, Any]] = None
    desired_state: Dict[str, Any]


class BaseProvider(ABC):
    """Abstract provider managing the lifecycle of a specific GitHub construct kind."""

    def __init__(self, client: GitHubClient):
        self.client = client

    @abstractmethod
    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        """Fetch remote resource status and return ResourceState or None if not found."""
        pass

    @abstractmethod
    def plan(self, manifest: GitHubManifest, current: Optional[ResourceState]) -> ResourcePlan:
        """Calculate diff between desired spec and current state."""
        pass

    @abstractmethod
    def apply(self, plan: ResourcePlan, manifest: GitHubManifest) -> ResourceState:
        """Execute changes using GraphQL (primary) or REST (fallback) and return updated state."""
        pass
