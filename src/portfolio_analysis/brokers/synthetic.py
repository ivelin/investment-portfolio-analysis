"""In-memory synthetic broker for tests and demos (no real balances)."""

from __future__ import annotations

from collections.abc import Sequence

from .base import AccountPosition, CashFlow, EquitySnapshot, FundAccount


class SyntheticBrokerAdapter:
    """Deterministic fake broker used in unit tests / CI."""

    broker = "synthetic"

    def __init__(
        self,
        accounts: Sequence[FundAccount] | None = None,
        snapshots: Sequence[EquitySnapshot] | None = None,
        cash_flows: Sequence[CashFlow] | None = None,
        positions: Sequence[AccountPosition] | None = None,
    ) -> None:
        self._accounts = list(accounts or [])
        self._snapshots = list(snapshots or [])
        self._cash_flows = list(cash_flows or [])
        self._positions = list(positions or [])

    def list_accounts(self) -> Sequence[FundAccount]:
        return list(self._accounts)

    def equity_snapshots(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[EquitySnapshot]:
        rows = [s for s in self._snapshots if s.account_key == account_key]
        if start_date:
            rows = [s for s in rows if s.as_of_date >= start_date]
        if end_date:
            rows = [s for s in rows if s.as_of_date <= end_date]
        return sorted(rows, key=lambda s: s.as_of_date)

    def external_cash_flows(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[CashFlow]:
        rows = [c for c in self._cash_flows if c.account_key == account_key]
        if start_date:
            rows = [c for c in rows if c.flow_date >= start_date]
        if end_date:
            rows = [c for c in rows if c.flow_date <= end_date]
        return sorted(rows, key=lambda c: c.flow_date)

    def account_positions(
        self,
        account_key: str,
        *,
        as_of_date: str | None = None,
    ) -> Sequence[AccountPosition]:
        rows = [p for p in self._positions if p.account_key == account_key]
        if as_of_date:
            rows = [p for p in rows if p.as_of_date == as_of_date]
        return list(rows)
