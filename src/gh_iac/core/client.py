"""Hybrid GitHub Client with GraphQL-first preference and REST fallback."""

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from gh_iac.core.target import TargetConfig

logger = logging.getLogger("gh_iac.client")


@dataclass
class RateLimitInfo:
    """GitHub API Rate Limit telemetry."""

    limit: int
    remaining: int
    reset_epoch: int
    used: Optional[int] = None
    resource: Optional[str] = None


class GitHubAPIError(Exception):
    """Exception raised when a GitHub GraphQL or REST request fails."""

    def __init__(
        self, message: str, status_code: Optional[int] = None, errors: Optional[Any] = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors


class GitHubClient:
    """
    Unified GitHub API client that prioritizes GraphQL and seamlessly falls back
    to REST v3 / SCIM endpoints where GraphQL is unavailable or unsuited.
    """

    def __init__(
        self,
        config: TargetConfig,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
    ):
        self.config = config
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.rate_limit_info: Optional[RateLimitInfo] = None
        self.last_graphql_cost: Optional[Dict[str, Any]] = None

        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "gh-iac/0.1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        verify_setting: Any = config.verify_ssl
        if config.ca_bundle:
            import ssl

            verify_setting = ssl.create_default_context(cafile=config.ca_bundle)

        self.http_client = httpx.Client(
            headers=self._headers,
            verify=verify_setting,
            proxy=config.proxy,
            timeout=30.0,
        )

    def close(self) -> None:
        self.http_client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _record_rate_limit(self, headers: httpx.Headers) -> None:
        limit_str = headers.get("x-ratelimit-limit")
        remaining_str = headers.get("x-ratelimit-remaining")
        reset_str = headers.get("x-ratelimit-reset")
        if limit_str and remaining_str and reset_str:
            try:
                self.rate_limit_info = RateLimitInfo(
                    limit=int(limit_str),
                    remaining=int(remaining_str),
                    reset_epoch=int(reset_str),
                    used=int(headers["x-ratelimit-used"])
                    if "x-ratelimit-used" in headers
                    else None,
                    resource=headers.get("x-ratelimit-resource"),
                )
            except ValueError:
                pass

    def _send_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send HTTP request with automatic rate-limit backoff and retries."""
        for attempt in range(self.max_retries + 1):
            response = self.http_client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                headers=headers,
            )
            self._record_rate_limit(response.headers)

            is_rate_limited = response.status_code == 429 or (
                response.status_code == 403
                and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "secondary rate limit" in response.text.lower()
                )
            )

            if is_rate_limited and attempt < self.max_retries:
                retry_after_str = response.headers.get("retry-after")
                if retry_after_str:
                    try:
                        sleep_time = float(retry_after_str)
                    except ValueError:
                        sleep_time = self.base_backoff_seconds * (2**attempt)
                else:
                    sleep_time = self.base_backoff_seconds * (2**attempt) + random.uniform(0, 0.05)

                logger.warning(
                    "Rate limit hit (%d) on %s %s. Sleeping %.2fs (attempt %d/%d)",
                    response.status_code,
                    method,
                    url,
                    sleep_time,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(sleep_time)
                continue

            return response

        return response

    # --- GraphQL Layer (Primary) ---

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query or mutation against GitHub GraphQL endpoint.
        Raises GitHubAPIError on errors.
        """
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self._send_request(
            method="POST",
            url=self.config.graphql_url,
            headers=self._headers,
            json_data=payload,
        )

        if response.status_code != 200:
            raise GitHubAPIError(
                f"GraphQL request failed with HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        if "extensions" in data and "cost" in data["extensions"]:
            self.last_graphql_cost = data["extensions"]["cost"]

        if "errors" in data and data["errors"]:
            error_msgs = "; ".join([e.get("message", "Unknown error") for e in data["errors"]])
            raise GitHubAPIError(
                f"GraphQL execution errors: {error_msgs}",
                status_code=200,
                errors=data["errors"],
            )

        res_data = data.get("data")
        return res_data if isinstance(res_data, dict) else {}

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

        response = self._send_request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json_data=json_data,
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
