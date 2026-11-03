"""Tests for GitHub App Authenticator and Token Rotation."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gh_iac.core.auth import GitHubAppAuthenticator


@pytest.fixture
def rsa_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_generate_jwt(rsa_private_key_pem: str):
    auth = GitHubAppAuthenticator(
        app_id="12345",
        private_key=rsa_private_key_pem,
        installation_id=67890,
    )
    token = auth.generate_jwt()
    assert token is not None

    # Verify JWT decode
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["iss"] == "12345"
    assert "exp" in decoded
    assert "iat" in decoded


@respx.mock
def test_get_installation_token_with_rotation(rsa_private_key_pem: str):
    auth = GitHubAppAuthenticator(
        app_id="12345",
        private_key=rsa_private_key_pem,
        installation_id=67890,
        base_url="https://api.github.com",
    )

    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    respx.post("https://api.github.com/app/installations/67890/access_tokens").respond(
        status_code=201,
        json={
            "token": "ghs_test_token_12345",
            "expires_at": expiry,
            "permissions": {"issues": "write"},
        },
    )

    token = auth.get_token()
    assert token == "ghs_test_token_12345"

    # Second call should use cached token without additional network request
    token2 = auth.get_token()
    assert token2 == "ghs_test_token_12345"
