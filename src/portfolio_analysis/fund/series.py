"""Account-level TWRR growth index from equity snapshots + external cash flows."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from portfolio_analysis.brokers.base import (
    AccountPosition,
    BrokerAdapter,
    CashFlow,
    EquitySnapshot,
    FundAccount,
)

from .symbols import fund_symbol


class InsufficientFundHistory(Exception):
    """Raised when there is not enough real fund_daily history for a request."""


def store_adapter_ground_truth(
    conn: sqlite3.Connection,
    adapter: BrokerAdapter,
    *,
    account_key: str | None = None,
) -> dict[str, int]:
    """Persist adapter accounts / snapshots / cash flows / positions into GT.

    Idempotent upserts. Does not rebuild the derived TWRR index.
    """
    accounts = list(adapter.list_accounts())
    if account_key:
        accounts = [a for a in accounts if a.account_key == account_key]

    n_accounts = n_snaps = n_flows = n_pos = 0
    for acct in accounts:
        _upsert_account(conn, acct)
        n_accounts += 1
        for snap in adapter.equity_snapshots(acct.account_key):
            _upsert_snapshot(conn, snap)
            n_snaps += 1
        for flow in adapter.external_cash_flows(acct.account_key):
            _upsert_cash_flow(conn, flow)
            n_flows += 1
        # Optional positions (uniform multi-broker table)
        get_pos = getattr(adapter, "account_positions", None)
        if callable(get_pos):
            for pos in get_pos(acct.account_key):
                _upsert_position(conn, pos)
                n_pos += 1
    conn.commit()
    return {
        "accounts": n_accounts,
        "snapshots": n_snaps,
        "cash_flows": n_flows,
        "positions": n_pos,
    }


def import_broker_to_gt(
    conn: sqlite3.Connection,
    adapter: BrokerAdapter,
    *,
    account_key: str | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Import adapter GT then rebuild fund_daily for each imported account.

    Returns counts plus list of fund symbols rebuilt.
    """
    counts = store_adapter_ground_truth(conn, adapter, account_key=account_key)
    rebuilt: list[dict[str, Any]] = []
    if rebuild:
        accounts = list(adapter.list_accounts())
        if account_key:
            accounts = [a for a in accounts if a.account_key == account_key]
        for acct in accounts:
            n = rebuild_fund_daily(
                conn, broker=acct.broker, account_key=acct.account_key
            )
            rebuilt.append(
                {
                    "fund_symbol": fund_symbol(acct.broker, acct.account_key),
                    "broker": acct.broker,
                    "account_key": acct.account_key,
                    "fund_daily_rows": n,
                }
            )
    return {**counts, "rebuilt": rebuilt}


def rebuild_fund_daily(
    conn: sqlite3.Connection,
    *,
    broker: str,
    account_key: str,
    base_index: float = 100.0,
) -> int:
    """Rebuild derived ``fund_daily`` rows for one account from gt_fund_* data.

    Each row includes liquidation_value (net liq "price") and cash-flow-neutral
    twrr_index. Returns number of daily index rows written.
    """
    symbol = fund_symbol(broker, account_key)
    snaps = conn.execute(
        """
        SELECT as_of_date, liquidation_value, data_quality
        FROM gt_fund_equity_snapshots
        WHERE broker = ? AND account_key = ?
        ORDER BY as_of_date ASC
        """,
        (broker.lower(), account_key.lower()),
    ).fetchall()
    if not snaps:
        conn.execute("DELETE FROM fund_daily WHERE fund_symbol = ?", (symbol,))
        conn.commit()
        return 0

    flows = conn.execute(
        """
        SELECT flow_date, amount
        FROM gt_fund_cash_flows
        WHERE broker = ? AND account_key = ?
        ORDER BY flow_date ASC
        """,
        (broker.lower(), account_key.lower()),
    ).fetchall()
    cf_by_date: dict[str, float] = defaultdict(float)
    for row in flows:
        cf_by_date[row["flow_date"]] += float(row["amount"])

    rows = _build_index_rows(snaps, cf_by_date, base_index=base_index)
    conn.execute("DELETE FROM fund_daily WHERE fund_symbol = ?", (symbol,))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for r in rows:
        conn.execute(
            """
            INSERT INTO fund_daily (
                fund_symbol, broker, account_key, as_of_date,
                liquidation_value, external_cf, daily_return, twrr_index,
                data_quality, calc_version, calc_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                broker.lower(),
                account_key.lower(),
                r["as_of_date"],
                r["liquidation_value"],
                r["external_cf"],
                r["daily_return"],
                r["twrr_index"],
                r["data_quality"],
                "fund-twrr-sod-cf-v1",
                now,
            ),
        )
    conn.commit()
    return len(rows)


def load_fund_index_series(
    conn: sqlite3.Connection, fund_sym: str
) -> list[dict[str, Any]]:
    """Return fund_daily rows ordered by date for technicals and charts."""
    symbol = fund_sym.strip()
    if symbol.upper().startswith("FUND:") and symbol.count(":") >= 2:
        parts = symbol.split(":", 2)
        symbol = f"FUND:{parts[1].lower()}:{parts[2].lower()}"

    rows = conn.execute(
        """
        SELECT as_of_date, twrr_index, liquidation_value, daily_return, external_cf
        FROM fund_daily
        WHERE fund_symbol = ?
        ORDER BY as_of_date ASC
        """,
        (symbol,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_account_positions(
    conn: sqlite3.Connection,
    *,
    broker: str,
    account_key: str,
    as_of_date: str | None = None,
) -> list[dict[str, Any]]:
    """Load uniform multi-broker positions for one account."""
    if as_of_date:
        rows = conn.execute(
            """
            SELECT broker, account_key, as_of_date, symbol, quantity,
                   market_value, price, cost_basis, asset_type, currency, source
            FROM gt_account_positions
            WHERE broker = ? AND account_key = ? AND as_of_date = ?
            ORDER BY symbol
            """,
            (broker.lower(), account_key.lower(), as_of_date),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT broker, account_key, as_of_date, symbol, quantity,
                   market_value, price, cost_basis, asset_type, currency, source
            FROM gt_account_positions
            WHERE broker = ? AND account_key = ?
              AND as_of_date = (
                SELECT MAX(as_of_date) FROM gt_account_positions
                WHERE broker = ? AND account_key = ?
              )
            ORDER BY symbol
            """,
            (
                broker.lower(),
                account_key.lower(),
                broker.lower(),
                account_key.lower(),
            ),
        ).fetchall()
    return [dict(r) for r in rows]


def _build_index_rows(
    snaps: list[sqlite3.Row] | list[Any],
    cf_by_date: dict[str, float],
    *,
    base_index: float,
) -> list[dict[str, Any]]:
    """Pure TWRR index construction (start-of-day CF convention)."""
    out: list[dict[str, Any]] = []
    prev_v: float | None = None
    index = base_index

    for snap in snaps:
        d = snap["as_of_date"] if isinstance(snap, sqlite3.Row) else snap["as_of_date"]
        v = float(
            snap["liquidation_value"]
            if isinstance(snap, sqlite3.Row)
            else snap["liquidation_value"]
        )
        q = int(
            snap["data_quality"]
            if isinstance(snap, sqlite3.Row) and "data_quality" in snap.keys()
            else snap.get("data_quality", 100)
        )
        cf = float(cf_by_date.get(d, 0.0))

        if prev_v is None:
            daily_return = 0.0
        else:
            denom = prev_v + cf
            if denom <= 0:
                raise ValueError(
                    f"Non-positive capital base on {d}: V_prev={prev_v}, CF={cf}"
                )
            daily_return = (v / denom) - 1.0
            index = index * (1.0 + daily_return)

        out.append(
            {
                "as_of_date": d,
                "liquidation_value": v,
                "external_cf": cf,
                "daily_return": daily_return,
                "twrr_index": index,
                "data_quality": q,
            }
        )
        prev_v = v

    return out


def _upsert_account(conn: sqlite3.Connection, acct: FundAccount) -> None:
    conn.execute(
        """
        INSERT INTO gt_fund_accounts (
            broker, account_key, display_name, currency, broker_account_ref, fund_symbol
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(broker, account_key) DO UPDATE SET
            display_name = excluded.display_name,
            currency = excluded.currency,
            broker_account_ref = excluded.broker_account_ref,
            fund_symbol = excluded.fund_symbol
        """,
        (
            acct.broker.lower(),
            acct.account_key.lower(),
            acct.display_name,
            acct.currency,
            acct.broker_account_ref,
            fund_symbol(acct.broker, acct.account_key),
        ),
    )


def _upsert_snapshot(conn: sqlite3.Connection, snap: EquitySnapshot) -> None:
    conn.execute(
        """
        INSERT INTO gt_fund_equity_snapshots (
            broker, account_key, as_of_date, liquidation_value, cash, source, data_quality
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(broker, account_key, as_of_date, source) DO UPDATE SET
            liquidation_value = excluded.liquidation_value,
            cash = excluded.cash,
            data_quality = excluded.data_quality
        """,
        (
            snap.broker.lower(),
            snap.account_key.lower(),
            snap.as_of_date,
            snap.liquidation_value,
            snap.cash,
            snap.source,
            snap.data_quality,
        ),
    )


def _upsert_cash_flow(conn: sqlite3.Connection, flow: CashFlow) -> None:
    conn.execute(
        """
        INSERT INTO gt_fund_cash_flows (
            broker, account_key, flow_date, amount, flow_type, source, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(broker, account_key, flow_date, flow_type, amount, source) DO UPDATE SET
            notes = excluded.notes
        """,
        (
            flow.broker.lower(),
            flow.account_key.lower(),
            flow.flow_date,
            flow.amount,
            flow.flow_type,
            flow.source,
            flow.notes,
        ),
    )


def _upsert_position(conn: sqlite3.Connection, pos: AccountPosition) -> None:
    conn.execute(
        """
        INSERT INTO gt_account_positions (
            broker, account_key, as_of_date, symbol, quantity,
            market_value, price, cost_basis, asset_type, currency, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(broker, account_key, as_of_date, symbol, source) DO UPDATE SET
            quantity = excluded.quantity,
            market_value = excluded.market_value,
            price = excluded.price,
            cost_basis = excluded.cost_basis,
            asset_type = excluded.asset_type,
            currency = excluded.currency
        """,
        (
            pos.broker.lower(),
            pos.account_key.lower(),
            pos.as_of_date,
            pos.symbol.upper(),
            pos.quantity,
            pos.market_value,
            pos.price,
            pos.cost_basis,
            pos.asset_type,
            pos.currency,
            pos.source,
        ),
    )
