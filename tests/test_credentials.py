"""Unit tests for credential and secret resolution."""

import pytest

from gh_iac.core.credentials import (
    CredentialResolver,
    SecretString,
    encrypt_github_secret,
    mask_secret,
)


def test_resolve_literal_string():
    resolver = CredentialResolver()
    val = resolver.resolve("ghp_literal12345")
    assert val == "ghp_literal12345"


def test_resolve_env_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_TEST_SECRET", "super-secret-token")
    resolver = CredentialResolver()

    # Prefix syntax
    val1 = resolver.resolve("env:GITHUB_TEST_SECRET")
    assert val1 == "super-secret-token"

    # Template syntax
    val2 = resolver.resolve("${GITHUB_TEST_SECRET}")
    assert val2 == "super-secret-token"


def test_resolve_missing_env_raises():
    resolver = CredentialResolver()
    with pytest.raises(ValueError) as exc:
        resolver.resolve("env:NON_EXISTENT_VAR_12345")
    assert "NON_EXISTENT_VAR_12345" in str(exc.value)


def test_mask_secret():
    assert mask_secret("short") == "******"
    masked = mask_secret("ghp_1234567890abcdef")
    assert masked.startswith("ghp_")
    assert "1234567890" not in masked
    assert masked.endswith("cdef")


def test_secret_string_repr_does_not_leak():
    secret = SecretString("my-super-secret-key")
    assert str(secret) == "******"
    assert repr(secret) == "SecretString('******')"
    assert secret.get_secret_value() == "my-super-secret-key"


def test_encrypt_github_secret_roundtrip():
    import base64

    from nacl import public

    # Generate a recipient keypair simulating GitHub's public key endpoint
    private_key = public.PrivateKey.generate()
    public_key_b64 = base64.b64encode(bytes(private_key.public_key)).decode("utf-8")

    plaintext = "super-secret-production-password"
    encrypted_b64 = encrypt_github_secret(public_key_b64, plaintext)

    # Decrypt with private key to verify correctness
    sealed_box = public.SealedBox(private_key)
    decrypted = sealed_box.decrypt(base64.b64decode(encrypted_b64.encode("utf-8"))).decode("utf-8")
    assert decrypted == plaintext

