"""Hybrid GitHub Client with GraphQL-first preference and REST fallback."""

import logging
from typing import Any, Dict, Optional

import httpx

from gh_iac.core.target import TargetConfig

logger = logging.getLogger("gh_iac.client")


class GitHubAPIError(Exception):
    """Exception raised when a GitHub GraphQL or REST request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None, errors: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors


class GitHubClient:
    """
    Unified GitHub API client that prioritizes GraphQL and seamlessly falls back
    to REST v3 / SCIM endpoints where GraphQL is unavailable or unsuited.
    """

    def __init__(self, config: TargetConfig):
        self.config = config
        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "gh-iac/0.1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.http_client = httpx.Client(
            headers=self._headers,
            verify=config.verify_ssl,
            timeout=30.0,
        )

    def close(self) -> None:
        self.http_client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # --- GraphQL Layer (Primary) ---

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query or mutation against GitHub GraphQL endpoint.
        Raises GitHubAPIError on errors.
        """
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self.http_client.post(self.config.graphql_url, json=payload)

        if response.status_code != 200:
            raise GitHubAPIError(
                f"GraphQL request failed with HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        if "errors" in data and data["errors"]:
            error_msgs = "; ".join([e.get("message", "Unknown error") for e in data["errors"]])
            raise GitHubAPIError(
                f"GraphQL execution errors: {error_msgs}",
                status_code=200,
                errors=data["errors"],
            )

        return data.get("data", {})

    # --- REST & SCIM Layer (Fallback & Specialized) ---

    def rest(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        custom_base_url: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """
        Execute a REST request against GitHub REST or SCIM API endpoints.
        """
        base = custom_base_url or self.config.base_url
        if path.startswith("/"):
            url = f"{base}{path}"
        else:
            url = f"{base}/{path}"

        headers = dict(self._headers)
        if extra_headers:
            headers.update(extra_headers)

        response = self.http_client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_data,
            headers=headers,
        )

        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            raise GitHubAPIError(
                f"REST {method} {url} failed with HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
                errors=response.text,
            )

        try:
            return response.json()
        except Exception:
            return response.text

    def scim_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        EMU SCIM v2 request for Enterprise Managed Users groups and provisioning.
        """
        if not self.config.scim_base_url:
            if not self.config.enterprise_slug:
                raise ValueError("EMU SCIM operations require an enterprise_slug configured.")
            scim_base = f"https://api.github.com/scim/v2/enterprises/{self.config.enterprise_slug}"
        else:
            scim_base = self.config.scim_base_url

        headers = {
            "Accept": "application/scim+json",
        }
        return self.rest(
            method=method,
            path=path,
            params=params,
            json_data=json_data,
            custom_base_url=scim_base,
            extra_headers=headers,
        )
