"""Robinhood adapter stub (planned)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from portfolio_analysis.paths import broker_exports_dir

from .base import AccountPosition, CashFlow, EquitySnapshot, FundAccount


class RobinhoodBrokerAdapter:
    """Robinhood placeholder — export path reserved; fund feeds not implemented."""

    broker = "robinhood"

    def __init__(self, *, exports_dir: Path | str | None = None) -> None:
        self.exports_dir = (
            Path(exports_dir).expanduser().resolve()
            if exports_dir
            else broker_exports_dir("robinhood")
        )

    def list_accounts(self) -> Sequence[FundAccount]:
        raise NotImplementedError(
            "Robinhood adapter is planned; place exports under "
            f"{self.exports_dir} when implementing (no fabricated data)."
        )

    def equity_snapshots(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[EquitySnapshot]:
        del account_key, start_date, end_date
        raise NotImplementedError("Robinhood equity snapshots not implemented yet.")

    def external_cash_flows(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[CashFlow]:
        del account_key, start_date, end_date
        raise NotImplementedError("Robinhood external cash flows not implemented yet.")

    def account_positions(
        self,
        account_key: str,
        *,
        as_of_date: str | None = None,
    ) -> Sequence[AccountPosition]:
        del account_key, as_of_date
        raise NotImplementedError(
            f"{self.broker} account positions not implemented yet."
        )
