"""Target environment definitions for GitHub."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TargetEnvironment(str, Enum):
    """Supported GitHub hosting flavors."""
    GHEC = "ghec"          # GitHub Enterprise Cloud
    GHES = "ghes"          # GitHub Enterprise Server
    GHEC_EMU = "ghec_emu"  # GHEC Enterprise Managed Users


class TargetConfig(BaseModel):
    """Configuration for target GitHub environment."""
    environment: TargetEnvironment = Field(
        default=TargetEnvironment.GHEC,
        description="The flavor of GitHub being targeted",
    )
    base_url: str = Field(
        default="https://api.github.com",
        description="REST API base URL (e.g., https://github.corp.com/api/v3 for GHES)",
    )
    graphql_url: str = Field(
        default="https://api.github.com/graphql",
        description="GraphQL API URL (e.g., https://github.corp.com/api/graphql for GHES)",
    )
    token: str = Field(
        ...,
        description="GitHub Authentication Token (PAT, Installation Token, or SCIM token)",
    )
    enterprise_slug: Optional[str] = Field(
        default=None,
        description="Slug of the GitHub Enterprise (required for enterprise-scoped constructs)",
    )
    scim_base_url: Optional[str] = Field(
        default=None,
        description="EMU SCIM API endpoint base URL (default derived from enterprise or base_url)",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Whether to verify SSL certificates (useful for self-signed GHES)",
    )
    ca_bundle: Optional[str] = Field(
        default=None,
        description="Path to custom CA bundle certificate file for air-gapped or internal TLS",
    )
    proxy: Optional[str] = Field(
        default=None,
        description="HTTP or HTTPS proxy URL (e.g. http://proxy.internal:8080)",
    )

    @classmethod
    def create_for_ghec(
        cls,
        token: str,
        enterprise_slug: Optional[str] = None,
        ca_bundle: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> "TargetConfig":
        return cls(
            environment=TargetEnvironment.GHEC,
            base_url="https://api.github.com",
            graphql_url="https://api.github.com/graphql",
            token=token,
            enterprise_slug=enterprise_slug,
            ca_bundle=ca_bundle,
            proxy=proxy,
        )

    @classmethod
    def create_for_emu(
        cls,
        token: str,
        enterprise_slug: str,
        ca_bundle: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> "TargetConfig":
        return cls(
            environment=TargetEnvironment.GHEC_EMU,
            base_url="https://api.github.com",
            graphql_url="https://api.github.com/graphql",
            token=token,
            enterprise_slug=enterprise_slug,
            scim_base_url=f"https://api.github.com/scim/v2/enterprises/{enterprise_slug}",
            ca_bundle=ca_bundle,
            proxy=proxy,
        )

    @classmethod
    def create_for_ghes(
        cls,
        hostname: str,
        token: str,
        enterprise_slug: Optional[str] = None,
        verify_ssl: bool = True,
        ca_bundle: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> "TargetConfig":
        clean_host = hostname.rstrip("/")
        if not clean_host.startswith("http://") and not clean_host.startswith("https://"):
            clean_host = f"https://{clean_host}"
        return cls(
            environment=TargetEnvironment.GHES,
            base_url=f"{clean_host}/api/v3",
            graphql_url=f"{clean_host}/api/graphql",
            token=token,
            enterprise_slug=enterprise_slug,
            verify_ssl=verify_ssl,
            ca_bundle=ca_bundle,
            proxy=proxy,
        )
