"""Unit tests for GitHubClient rate limiting, retries, and resilience."""

import httpx
import pytest
import respx

from gh_iac.core.client import GitHubAPIError, GitHubClient
from gh_iac.core.target import TargetConfig


@respx.mock
def test_rest_retry_on_429_success():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config, max_retries=2, base_backoff_seconds=0.01)

    route = respx.get("https://api.github.com/orgs/octocorp")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}, text="rate limit exceeded"),
        httpx.Response(200, json={"login": "octocorp"}),
    ]

    data = client.rest("GET", "/orgs/octocorp")
    assert data["login"] == "octocorp"
    assert route.call_count == 2


@respx.mock
def test_rest_retry_on_403_secondary_rate_limit():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config, max_retries=2, base_backoff_seconds=0.01)

    route = respx.get("https://api.github.com/orgs/octocorp")
    route.side_effect = [
        httpx.Response(
            403,
            headers={"Retry-After": "0"},
            text="You have exceeded a secondary rate limit. Please wait a few minutes before you try again.",
        ),
        httpx.Response(200, json={"login": "octocorp"}),
    ]

    data = client.rest("GET", "/orgs/octocorp")
    assert data["login"] == "octocorp"
    assert route.call_count == 2


@respx.mock
def test_rest_retries_exhausted_raises():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config, max_retries=1, base_backoff_seconds=0.01)

    respx.get("https://api.github.com/orgs/octocorp").respond(
        status_code=429,
        headers={"Retry-After": "0"},
        text="Too Many Requests",
    )

    with pytest.raises(GitHubAPIError) as exc_info:
        client.rest("GET", "/orgs/octocorp")
    assert exc_info.value.status_code == 429


@respx.mock
def test_rate_limit_headers_tracked():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)

    respx.get("https://api.github.com/orgs/octocorp").respond(
        status_code=200,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4950",
            "X-RateLimit-Reset": "1700000000",
            "X-RateLimit-Used": "50",
            "X-RateLimit-Resource": "core",
        },
        json={"login": "octocorp"},
    )

    client.rest("GET", "/orgs/octocorp")
    info = client.rate_limit_info
    assert info is not None
    assert info.remaining == 4950
    assert info.limit == 5000
    assert info.reset_epoch == 1700000000


@respx.mock
def test_graphql_cost_and_throttle_tracked():
    config = TargetConfig.create_for_ghec(token="test-pat")
    client = GitHubClient(config)

    respx.post("https://api.github.com/graphql").respond(
        status_code=200,
        json={
            "data": {"viewer": {"login": "octocat"}},
            "extensions": {
                "cost": {
                    "actualQueryCost": 5,
                    "throttleStatus": {
                        "maximumAvailable": 50000,
                        "currentlyAvailable": 49950,
                        "restoreRate": 500,
                    },
                }
            },
        },
    )

    client.graphql("query { viewer { login } }")
    cost_info = client.last_graphql_cost
    assert cost_info is not None
    assert cost_info["actualQueryCost"] == 5
    assert cost_info["throttleStatus"]["currentlyAvailable"] == 49950


def test_client_proxy_and_ca_bundle():
    ca_path = "/usr/lib/ssl/cert.pem"
    config = TargetConfig.create_for_ghes(
        hostname="ghes.corp.internal",
        token="test-token",
        ca_bundle=ca_path,
        proxy="http://proxy.corp.internal:8080",
    )
    assert config.ca_bundle == ca_path
    assert config.proxy == "http://proxy.corp.internal:8080"
    client = GitHubClient(config)
    assert client.http_client._transport is not None
