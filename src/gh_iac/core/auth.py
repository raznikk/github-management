"""GitHub App Authentication and Token Rotation."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt


class GitHubAppAuthenticator:
    """
    Handles GitHub App authentication using RSA private key JWT generation
    and automatic installation token generation and rotation.
    """

    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: int,
        base_url: str = "https://api.github.com",
    ):
        self.app_id = str(app_id)
        self.private_key = private_key
        self.installation_id = int(installation_id)
        self.base_url = base_url.rstrip("/")
        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def generate_jwt(self, expiration_minutes: int = 10) -> str:
        """Generate RS256 signed JWT for the GitHub App."""
        now = datetime.now(timezone.utc)
        payload = {
            "iat": int(now.timestamp()) - 60,  # 60s in the past for clock drift
            "exp": int((now + timedelta(minutes=expiration_minutes)).timestamp()),
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_token(self) -> str:
        """
        Return a valid installation access token, rotating if expired or near expiration.
        """
        now = datetime.now(timezone.utc)
        # Check cache (refresh if within 2 minutes of expiration)
        if self._cached_token and self._token_expires_at:
            if self._token_expires_at - now > timedelta(minutes=2):
                return self._cached_token

        jwt_token = self.generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"{self.base_url}/app/installations/{self.installation_id}/access_tokens"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers)
            if resp.status_code != 201:
                raise RuntimeError(
                    f"Failed to obtain installation token for app {self.app_id}: {resp.status_code} {resp.text}"
                )
            data = resp.json()
            self._cached_token = data["token"]
            expires_at_str = data.get("expires_at")
            if expires_at_str:
                self._token_expires_at = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )
            else:
                self._token_expires_at = now + timedelta(hours=1)

            return self._cached_token
