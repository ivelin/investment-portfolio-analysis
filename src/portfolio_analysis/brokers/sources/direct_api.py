"""Direct Schwab Developer API live source (in-process; no MCP)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .base import LiveAccountEquity
from .schwab_mcp import parse_schwab_accounts_payload


class SchwabDirectApiLiveSource:
    """Use portfolio_analysis.schwab.client.SchwabClient against api.schwabapi.com."""

    name = "schwab_direct_api"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        from portfolio_analysis.schwab.auth import SchwabAuth
        from portfolio_analysis.schwab.client import SchwabClient

        return SchwabClient(SchwabAuth())

    def fetch_account_equities(self) -> Sequence[LiveAccountEquity]:
        client = self._client_or_create()
        raw = client.get_accounts(include_positions=False)
        # Enrich with hashes from accountNumbers if missing
        try:
            numbers = client.get_account_numbers()
        except Exception:
            numbers = []
        hash_by_num = {
            e.get("accountNumber"): e.get("hashValue")
            for e in numbers
            if isinstance(e, dict)
        }
        enriched = _inject_hashes(raw, hash_by_num)
        return parse_schwab_accounts_payload(enriched, source_label="direct_api")


def _inject_hashes(payload: Any, hash_by_num: dict[Any, Any]) -> Any:
    if isinstance(payload, list):
        return [_inject_hashes(x, hash_by_num) for x in payload]
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    sec = out.get("securitiesAccount")
    if isinstance(sec, dict):
        sec = dict(sec)
        if not sec.get("accountHash"):
            num = sec.get("accountNumber")
            if num in hash_by_num and hash_by_num[num]:
                sec["accountHash"] = hash_by_num[num]
        out["securitiesAccount"] = sec
    return out
