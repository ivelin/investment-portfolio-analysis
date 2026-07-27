"""Schwab OAuth2 authentication module.

Handles authorization code flow with PKCE, token storage, and refresh.
Prioritizes security: no hardcoded secrets, uses env vars + secure token storage.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

from portfolio_analysis.paths import default_schwab_tokens_path

SCHWAB_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_API_BASE = "https://api.schwabapi.com"


class SchwabAuthError(Exception):
    """Custom exception for auth failures."""


class SchwabAuth:
    """Manages Schwab OAuth2 lifecycle with secure token handling."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: str = "https://127.0.0.1:8080/callback",
        token_file: Optional[Path] = None,
    ):
        self.client_id = client_id or os.getenv("SCHWAB_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SCHWAB_CLIENT_SECRET")
        self.redirect_uri = redirect_uri
        # Tokens live under PORTFOLIO_ANALYSIS_HOME (not the git repo).
        self.token_file = (
            Path(token_file) if token_file else default_schwab_tokens_path()
        )

        if not self.client_id or not self.client_secret:
            raise SchwabAuthError(
                "Missing SCHWAB_CLIENT_ID or SCHWAB_CLIENT_SECRET. "
                "Set via environment variables or constructor."
            )

        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self._tokens: Dict[str, Any] = {}

    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge."""
        verifier = (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return verifier, challenge

    def get_authorization_url(self) -> tuple[str, str]:
        """Return (auth_url, code_verifier) for user to visit."""
        verifier, challenge = self._generate_pkce_pair()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "readonly",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"{SCHWAB_AUTH_URL}?{urlencode(params)}"
        return auth_url, verifier

    def exchange_code_for_tokens(self, code: str, code_verifier: str) -> Dict[str, Any]:
        """Exchange authorization code for access/refresh tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": code_verifier,
        }
        resp = requests.post(SCHWAB_TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise SchwabAuthError(f"Token exchange failed: {resp.text}")
        tokens = resp.json()
        self._save_tokens(tokens)
        return tokens

    def refresh_tokens(self, refresh_token: Optional[str] = None) -> Dict[str, Any]:
        """Refresh access token using refresh_token."""
        if refresh_token is None:
            tokens = self._load_tokens()
            refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise SchwabAuthError("No refresh token available. Re-authenticate.")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        resp = requests.post(SCHWAB_TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise SchwabAuthError(f"Token refresh failed: {resp.text}")
        tokens = resp.json()
        # Preserve refresh_token if not rotated
        if "refresh_token" not in tokens:
            tokens["refresh_token"] = refresh_token
        self._save_tokens(tokens)
        return tokens

    def _save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Persist tokens securely (basic file storage; consider encryption in prod)."""
        tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800) - 60
        self._tokens = tokens
        with open(self.token_file, "w") as f:
            json.dump(tokens, f, indent=2)
        os.chmod(self.token_file, 0o600)  # Restrict permissions

    def _load_tokens(self) -> Dict[str, Any]:
        """Load tokens from disk."""
        if self._tokens:
            return self._tokens
        if not self.token_file.exists():
            return {}
        with open(self.token_file) as f:
            self._tokens = json.load(f)
        return self._tokens

    def get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        tokens = self._load_tokens()
        if not tokens:
            raise SchwabAuthError("No tokens found. Run authorization flow first.")

        if time.time() >= tokens.get("expires_at", 0):
            tokens = self.refresh_tokens(tokens.get("refresh_token"))

        return tokens["access_token"]

    def is_authenticated(self) -> bool:
        """Quick check if we have usable tokens."""
        try:
            self.get_valid_access_token()
            return True
        except SchwabAuthError:
            return False
