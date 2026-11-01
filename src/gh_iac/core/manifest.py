"""Base declarative manifest models for GitHub constructs."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ManifestMetadata(BaseModel):
    """Metadata identifying the construct in the IaC hierarchy."""
    name: str = Field(..., description="Unique name/identifier for the resource")
    enterprise: Optional[str] = Field(None, description="Enterprise slug if enterprise-scoped")
    organization: Optional[str] = Field(None, description="Organization login if org-scoped")
    repository: Optional[str] = Field(None, description="Repository name if repo-scoped")
    labels: Dict[str, str] = Field(default_factory=dict, description="Metadata labels/tags")


class GitHubManifest(BaseModel):
    """
    Standard declarative resource manifest, modeled after cloud native / CRD patterns.
    """
    apiVersion: str = Field(
        default="github.iac/v1alpha1",
        description="API schema version",
    )
    kind: str = Field(
        ...,
        description="Construct Kind (e.g. EnterpriseAccount, CustomRole, Team, Repository)",
    )
    metadata: ManifestMetadata = Field(..., description="Resource metadata")
    spec: Dict[str, Any] = Field(..., description="Construct specific configuration desired state")

    @property
    def resource_id(self) -> str:
        """Returns unique resource key in the format: Kind/enterprise/org/repo/name."""
        parts = [self.kind]
        if self.metadata.enterprise:
            parts.append(f"ent:{self.metadata.enterprise}")
        if self.metadata.organization:
            parts.append(f"org:{self.metadata.organization}")
        if self.metadata.repository:
            parts.append(f"repo:{self.metadata.repository}")
        parts.append(self.metadata.name)
        return "/".join(parts)
