"""Broker-agnostic adapter contracts for fund-as-symbol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class FundAccount:
    """One brokerage account normalized for the fund core."""

    broker: str
    account_key: str
    display_name: str
    currency: str = "USD"
    broker_account_ref: str | None = (
        None  # optional opaque ref; avoid logging raw numbers
    )
    account_number_last3: str | None = None  # last 3 digits only when known


@dataclass(frozen=True)
class EquitySnapshot:
    """Point-in-time account equity / liquidation value."""

    account_key: str
    broker: str
    as_of_date: str  # YYYY-MM-DD
    liquidation_value: float
    cash: float | None = None
    source: str = "api"
    data_quality: int = 100


@dataclass(frozen=True)
class CashFlow:
    """External cash flow (deposit/withdrawal/ACATS/wire)."""

    account_key: str
    broker: str
    flow_date: str  # YYYY-MM-DD
    amount: float  # positive = capital into the account
    flow_type: str  # deposit, withdrawal, acats_in, acats_out, wire, other
    source: str = "api"
    notes: str | None = None


@dataclass(frozen=True)
class AccountPosition:
    """Uniform multi-broker holding row (broker-agnostic ground truth)."""

    broker: str
    account_key: str
    as_of_date: str  # YYYY-MM-DD
    symbol: str
    quantity: float
    market_value: float | None = None
    price: float | None = None
    cost_basis: float | None = None
    asset_type: str | None = None
    currency: str = "USD"
    source: str = "api"


class BrokerAdapter(Protocol):
    """Minimal adapter surface for fund-as-symbol ingestion."""

    broker: str

    def list_accounts(self) -> Sequence[FundAccount]:
        """Return linked accounts for this broker."""

    def equity_snapshots(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[EquitySnapshot]:
        """Return equity snapshots for one account (date range optional)."""

    def external_cash_flows(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[CashFlow]:
        """Return external cash flows (not internal journal transfers)."""

    def account_positions(
        self,
        account_key: str,
        *,
        as_of_date: str | None = None,
    ) -> Sequence[AccountPosition]:
        """Return current (or as-of) holdings in uniform multi-broker shape."""
