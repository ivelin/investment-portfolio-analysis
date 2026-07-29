"""Schwab live source backed by an MCP server (local or remote).

Default local endpoint matches the operator's schwab-mcp service
(``http://127.0.0.1:3473/mcp``). Set ``SCHWAB_MCP_URL`` for remote gateways.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import date
from typing import Any

from .base import LiveAccountEquity, LivePosition
from .mcp_transport import McpTransportConfig, call_mcp_tool_sync


def _account_number_last3(sec: dict[str, Any]) -> str | None:
    """Extract last-3 digits only from broker account number fields (never store full)."""
    raw = sec.get("accountNumber") or sec.get("account_number")
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) < 3:
        return None
    return digits[-3:]


def stable_account_key(broker_account_ref: str, *, length: int = 12) -> str:
    """Opaque short key from a broker-native id (never log full account numbers)."""
    digest = hashlib.sha256(broker_account_ref.encode("utf-8")).hexdigest()
    return digest[:length]


def _as_of_today() -> str:
    return date.today().isoformat()


def _parse_positions(sec: dict[str, Any]) -> tuple[LivePosition, ...]:
    raw = sec.get("positions")
    if not isinstance(raw, list):
        return ()
    out: list[LivePosition] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        # Compact MCP shape: symbol at top level; verbose: instrument.symbol
        symbol = p.get("symbol")
        if not symbol and isinstance(p.get("instrument"), dict):
            symbol = p["instrument"].get("symbol")
        if not symbol:
            continue
        try:
            qty = float(p.get("quantity", p.get("longQuantity", 0)) or 0)
            short_q = float(p.get("shortQuantity", 0) or 0)
            if "quantity" not in p and short_q:
                qty = qty - short_q
        except (TypeError, ValueError):
            continue
        if qty == 0:
            continue
        mv = p.get("marketValue")
        px = p.get("averagePrice") or p.get("price")
        try:
            mv_f = float(mv) if mv is not None else None
        except (TypeError, ValueError):
            mv_f = None
        try:
            px_f = float(px) if px is not None else None
        except (TypeError, ValueError):
            px_f = None
        cost = None
        if px_f is not None and qty:
            cost = abs(qty) * px_f
        asset = None
        if isinstance(p.get("instrument"), dict):
            asset = p["instrument"].get("assetType") or p["instrument"].get("type")
        out.append(
            LivePosition(
                symbol=str(symbol).upper(),
                quantity=qty,
                market_value=mv_f,
                price=px_f,
                cost_basis=cost,
                asset_type=str(asset) if asset else None,
            )
        )
    return tuple(out)


def parse_schwab_accounts_payload(
    payload: Any,
    *,
    broker: str = "schwab",
    source_label: str = "mcp",
    as_of_date: str | None = None,
) -> list[LiveAccountEquity]:
    """Parse get_accounts JSON (compact or verbose Schwab shapes) into live rows."""
    as_of = as_of_date or _as_of_today()
    rows: list[LiveAccountEquity] = []
    items: list[Any]
    if payload is None:
        return []
    if isinstance(payload, dict) and "securitiesAccount" in payload:
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        return []

    for item in items:
        if not isinstance(item, dict):
            continue
        sec = item.get("securitiesAccount", item)
        if not isinstance(sec, dict):
            continue
        account_hash = sec.get("accountHash") or sec.get("hashValue")
        if not account_hash:
            account_hash = sec.get("accountNumber")
        if not account_hash or not isinstance(account_hash, str):
            continue
        balances = sec.get("currentBalances") or {}
        if not isinstance(balances, dict):
            balances = {}
        liq = balances.get("liquidationValue")
        if liq is None:
            liq = balances.get("equity")
        if liq is None:
            continue
        try:
            liq_f = float(liq)
        except (TypeError, ValueError):
            continue
        cash_raw = balances.get("cashBalance")
        cash: float | None
        try:
            cash = float(cash_raw) if cash_raw is not None else None
        except (TypeError, ValueError):
            cash = None
        nick = sec.get("nickname") or sec.get("nickName")
        acct_type = sec.get("type") or "account"
        display = str(nick) if nick else f"Schwab {acct_type}"
        positions = _parse_positions(sec)
        rows.append(
            LiveAccountEquity(
                broker=broker,
                account_key=stable_account_key(account_hash),
                display_name=display,
                broker_account_ref=account_hash,
                as_of_date=as_of,
                liquidation_value=liq_f,
                cash=cash,
                source=source_label,
                positions=positions,
                account_number_last3=_account_number_last3(sec),
            )
        )
    return rows


class SchwabMcpLiveSource:
    """Fetch Schwab account equities (+ optional positions) via MCP tools."""

    name = "schwab_mcp"

    def __init__(
        self,
        config: McpTransportConfig | None = None,
        *,
        include_positions: bool = True,
    ) -> None:
        self.config = config or McpTransportConfig.from_env()
        self.include_positions = include_positions

    def fetch_account_equities(self) -> Sequence[LiveAccountEquity]:
        payload = call_mcp_tool_sync(
            self.config,
            "get_accounts",
            {
                "include_positions": self.include_positions,
                "verbose": False,
            },
        )
        if isinstance(payload, str) and payload.lower().startswith("error"):
            raise RuntimeError(payload)
        return parse_schwab_accounts_payload(
            payload, source_label=f"mcp:{self.config.url or 'stdio'}"
        )
