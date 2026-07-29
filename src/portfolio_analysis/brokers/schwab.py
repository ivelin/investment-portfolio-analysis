"""Schwab / TDA broker adapter.

Live account equities come from a pluggable source (MCP local/remote or direct
OAuth API). File exports remain under :func:`broker_exports_dir` / connector
``exports_dir``. No fabricated balances.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from portfolio_analysis.paths import broker_exports_dir, default_schwab_tokens_path

from .base import AccountPosition, CashFlow, EquitySnapshot, FundAccount
from .sources.base import BrokerLiveSource, LiveAccountEquity


class SchwabBrokerAdapter:
    """Charles Schwab (and legacy TDA) adapter."""

    broker = "schwab"

    def __init__(
        self,
        *,
        exports_dir: Path | str | None = None,
        tokens_path: Path | str | None = None,
        live_source: BrokerLiveSource | None = None,
        use_connector: bool = True,
    ) -> None:
        self.exports_dir = (
            Path(exports_dir).expanduser().resolve()
            if exports_dir
            else broker_exports_dir("schwab")
        )
        self.tokens_path = (
            Path(tokens_path).expanduser().resolve()
            if tokens_path
            else default_schwab_tokens_path()
        )
        self._live = live_source
        self._use_connector = use_connector
        self._equity_cache: list[LiveAccountEquity] | None = None

    @classmethod
    def from_connector(cls) -> SchwabBrokerAdapter:
        """Build adapter from local connector config (MCP / direct / exports)."""
        from portfolio_analysis.connectors.store import (
            exports_path_for,
            load_connector,
            resolve_live_source_for_connector,
            tokens_path_for,
        )

        cfg = load_connector("schwab")
        live = resolve_live_source_for_connector(cfg)
        return cls(
            exports_dir=exports_path_for(cfg),
            tokens_path=tokens_path_for("schwab"),
            live_source=live,
            use_connector=False,  # live_source already resolved
        )

    def _ensure_live(self) -> BrokerLiveSource | None:
        if self._live is not None:
            return self._live
        if not self._use_connector:
            return None
        from portfolio_analysis.connectors.store import (
            load_connector,
            resolve_live_source_for_connector,
        )

        self._live = resolve_live_source_for_connector(load_connector("schwab"))
        return self._live

    def _live_rows(self) -> list[LiveAccountEquity]:
        if self._equity_cache is not None:
            return self._equity_cache
        src = self._ensure_live()
        if src is None:
            self._equity_cache = []
            return self._equity_cache
        self._equity_cache = list(src.fetch_account_equities())
        return self._equity_cache

    def list_accounts(self) -> Sequence[FundAccount]:
        return [
            FundAccount(
                broker=self.broker,
                account_key=row.account_key,
                display_name=row.display_name,
                currency=row.currency,
                broker_account_ref=row.broker_account_ref,
                account_number_last3=getattr(row, "account_number_last3", None),
            )
            for row in self._live_rows()
        ]

    def equity_snapshots(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[EquitySnapshot]:
        rows = [
            EquitySnapshot(
                account_key=row.account_key,
                broker=self.broker,
                as_of_date=row.as_of_date,
                liquidation_value=row.liquidation_value,
                cash=row.cash,
                source=row.source,
            )
            for row in self._live_rows()
            if row.account_key == account_key
        ]
        if start_date:
            rows = [r for r in rows if r.as_of_date >= start_date]
        if end_date:
            rows = [r for r in rows if r.as_of_date <= end_date]
        return rows

    def external_cash_flows(
        self,
        account_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[CashFlow]:
        # Cash-flow history via MCP/API is a later phase; do not invent.
        del account_key, start_date, end_date
        return []

    def account_positions(
        self,
        account_key: str,
        *,
        as_of_date: str | None = None,
    ) -> Sequence[AccountPosition]:
        rows: list[AccountPosition] = []
        for row in self._live_rows():
            if row.account_key != account_key:
                continue
            if as_of_date and row.as_of_date != as_of_date:
                continue
            for pos in row.positions:
                rows.append(
                    AccountPosition(
                        broker=self.broker,
                        account_key=row.account_key,
                        as_of_date=row.as_of_date,
                        symbol=pos.symbol,
                        quantity=pos.quantity,
                        market_value=pos.market_value,
                        price=pos.price,
                        cost_basis=pos.cost_basis,
                        asset_type=pos.asset_type,
                        source=row.source,
                    )
                )
        return rows
