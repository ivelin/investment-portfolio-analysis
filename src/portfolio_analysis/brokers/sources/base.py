"""Transport-agnostic live account data for fund-as-symbol adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class LivePosition:
    """One holding from a live source (pre-normalized)."""

    symbol: str
    quantity: float
    market_value: float | None = None
    price: float | None = None
    cost_basis: float | None = None
    asset_type: str | None = None


@dataclass(frozen=True)
class LiveAccountEquity:
    """One account's identity + current equity (from a live source).

    ``broker_account_ref`` is an opaque broker handle (e.g. Schwab account hash).
    ``account_key`` is the stable short id used in FUND:{broker}:{account_key}.
    """

    broker: str
    account_key: str
    display_name: str
    broker_account_ref: str
    as_of_date: str  # YYYY-MM-DD (local calendar date of the snapshot)
    liquidation_value: float
    cash: float | None = None
    currency: str = "USD"
    source: str = "live"
    positions: tuple[LivePosition, ...] = ()


class BrokerLiveSource(Protocol):
    """Minimal live feed used by multi-broker fund adapters.

    Implementations must not invent balances. If the upstream is unreachable
    or unauthenticated, methods should raise (or return empty only when the
    source legitimately has zero accounts).
    """

    name: str

    def fetch_account_equities(self) -> Sequence[LiveAccountEquity]:
        """Return current equity snapshots for linked accounts."""
