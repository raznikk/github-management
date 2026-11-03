"""Credential and secret resolution and masking."""

import os
import re


class SecretString:
    """Wrapper around sensitive strings to prevent accidental leakage in logs/diffs."""

    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value

    def __str__(self) -> str:
        return "******"

    def __repr__(self) -> str:
        return "SecretString('******')"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretString):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return False


def mask_secret(value: str) -> str:
    """Mask a secret string for safe display, retaining prefix/suffix if long enough."""
    if len(value) <= 8:
        return "******"
    prefix = value[:4]
    suffix = value[-4:]
    masked_middle = "*" * (min(len(value) - 8, 8))
    return f"{prefix}{masked_middle}{suffix}"


class CredentialResolver:
    """
    Resolves credential references from environment variables, CLI tools,
    or external secret stores.
    """

    ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

    def resolve(self, reference: str) -> str:
        """Resolve a reference string to the actual secret."""
        if not reference:
            return ""

        # Check env:VARIABLE syntax
        if reference.startswith("env:"):
            var_name = reference[4:].strip()
            val = os.environ.get(var_name)
            if val is None:
                raise ValueError(
                    f"Environment variable '{var_name}' referenced in credential was not found."
                )
            return val

        # Check ${VARIABLE} syntax
        match = self.ENV_PATTERN.match(reference.strip())
        if match:
            var_name = match.group(1)
            val = os.environ.get(var_name)
            if val is None:
                raise ValueError(
                    f"Environment variable '{var_name}' referenced in credential was not found."
                )
            return val

        # Literal value
        return reference


def encrypt_github_secret(public_key_b64: str, secret_value: str) -> str:
    """
    Encrypts a plaintext secret using Libsodium sealed box (crypto_box_seal)
    and a base64-encoded recipient public key.
    Returns the base64-encoded encrypted ciphertext suitable for GitHub Secrets REST API.
    """
    import base64

    from nacl import encoding, public

    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder)
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")
