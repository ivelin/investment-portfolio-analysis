"""Schwab API client for account and transaction endpoints.

Clean separation from auth. Uses authenticated requests.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from .auth import SchwabAuth

SCHWAB_API_BASE = "https://api.schwabapi.com"


class SchwabClient:
    """High-level client for Schwab Developer API (v1)."""

    def __init__(self, auth: Optional[SchwabAuth] = None):
        self.auth = auth or SchwabAuth()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _auth_header(self) -> Dict[str, str]:
        token = self.auth.get_valid_access_token()
        return {"Authorization": f"Bearer {token}"}

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Internal request helper with error handling."""
        url = urljoin(SCHWAB_API_BASE, endpoint)
        headers = {**self._auth_header(), **kwargs.pop("headers", {})}
        resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
        if resp.status_code == 401:
            # Force refresh on auth error
            self.auth.refresh_tokens()
            headers = self._auth_header()
            resp = self.session.request(
                method, url, headers=headers, timeout=30, **kwargs
            )
        resp.raise_for_status()
        return resp.json()

    # Account endpoints
    def get_account_numbers(self) -> List[Dict[str, Any]]:
        """Return list of account numbers and hashes."""
        return self._request("GET", "/trader/v1/accounts/accountNumbers")

    def get_accounts(self, include_positions: bool = True) -> List[Dict[str, Any]]:
        """Get all accounts with optional positions."""
        params = {"fields": "positions"} if include_positions else {}
        return self._request("GET", "/trader/v1/accounts", params=params)

    def get_account(
        self, account_hash: str, include_positions: bool = True
    ) -> Dict[str, Any]:
        """Get single account details."""
        params = {"fields": "positions"} if include_positions else {}
        return self._request(
            "GET", f"/trader/v1/accounts/{account_hash}", params=params
        )

    # Transaction endpoints
    def get_transactions(
        self,
        account_hash: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        types: Optional[str] = "TRADE",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch transactions for an account."""
        params: Dict[str, Any] = {"types": types, "limit": limit}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        return self._request(
            "GET", f"/trader/v1/accounts/{account_hash}/transactions", params=params
        )

    def get_transaction(self, account_hash: str, transaction_id: str) -> Dict[str, Any]:
        """Get a specific transaction."""
        return self._request(
            "GET", f"/trader/v1/accounts/{account_hash}/transactions/{transaction_id}"
        )

    def get_user_preferences(self) -> Dict[str, Any]:
        """Return user preferences (useful for linked accounts)."""
        return self._request("GET", "/trader/v1/userPreference")
