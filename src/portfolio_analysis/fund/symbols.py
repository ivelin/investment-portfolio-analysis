"""Private fund symbol naming (local only — not exchange tickers)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedFundSymbol:
    broker: str
    account_key: str
    is_combined: bool = False


def fund_symbol(broker: str, account_key: str) -> str:
    """Build per-account fund id: FUND:{broker}:{account_key}."""
    b = broker.strip().lower()
    k = account_key.strip().lower()
    if not b or not k:
        raise ValueError("broker and account_key are required")
    if ":" in b or ":" in k:
        raise ValueError("broker and account_key must not contain ':'")
    return f"FUND:{b}:{k}"


def combined_fund_symbol() -> str:
    """Book-level fund id (Phase 5)."""
    return "FUND:ALL"


def parse_fund_symbol(symbol: str) -> ParsedFundSymbol:
    """Parse FUND:broker:key or FUND:ALL."""
    raw = symbol.strip().upper()
    if not raw.startswith("FUND:"):
        raise ValueError(f"Not a fund symbol: {symbol!r}")
    rest = raw[5:]
    if rest == "ALL":
        return ParsedFundSymbol(broker="all", account_key="all", is_combined=True)
    parts = rest.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Expected FUND:broker:account_key, got {symbol!r}")
    return ParsedFundSymbol(broker=parts[0].lower(), account_key=parts[1].lower())
