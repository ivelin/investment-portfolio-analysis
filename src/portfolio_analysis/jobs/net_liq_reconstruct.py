"""Reconstruct account net-liq for market days without GT equity snapshots.

Inputs (real local data only — never stamp today's live NAV onto the past):
- ``gt_account_positions`` market values (preferred book for a day)
- ``gt_fund_equity_snapshots`` as anchors (cash + verified liquidations)
- ``gt_fund_cash_flows`` external capital between anchors (order/flow history)

When a reconstructed value and a GT equity snapshot both exist for the same
account+date, ``verify_reconstruct_vs_snapshot`` checks they match within
tolerance so reconstruction logic can be audited.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Any

# Absolute $ tolerance for recon vs GT snapshot (money amounts).
DEFAULT_VERIFY_TOLERANCE = 0.02

PROVENANCE_GROUND_TRUTH = "ground_truth"
PROVENANCE_LIVE = "live_exact"
PROVENANCE_RECONSTRUCTED = "reconstructed"


@dataclass(frozen=True)
class ReconDay:
    """One reconstructed net-liq candidate."""

    as_of_date: str
    net_liquidation_value: float
    source: str
    data_quality: int
    provenance: str = PROVENANCE_RECONSTRUCTED
    components: dict[str, Any] | None = None


def verify_reconstruct_vs_snapshot(
    reconstructed: float,
    snapshot: float,
    *,
    tolerance: float = DEFAULT_VERIFY_TOLERANCE,
) -> tuple[bool, float]:
    """Return (matches, abs_diff). Both must be finite."""
    if not math.isfinite(reconstructed) or not math.isfinite(snapshot):
        return False, float("inf")
    diff = abs(float(reconstructed) - float(snapshot))
    return diff <= float(tolerance), diff


def position_book_value(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    as_of_date: str,
) -> float | None:
    """Sum market_value of holdings for account on as_of_date; None if no rows."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(market_value), 0), COUNT(*)
        FROM gt_account_positions
        WHERE broker = ? AND account_key = ? AND as_of_date = ?
        """,
        (broker.lower(), account_key.lower(), as_of_date),
    ).fetchone()
    if not row or int(row[1] or 0) == 0:
        return None
    return float(row[0])


def cash_from_equity_snapshot(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    as_of_date: str,
) -> float | None:
    row = conn.execute(
        """
        SELECT cash FROM gt_fund_equity_snapshots
        WHERE broker = ? AND account_key = ? AND as_of_date = ?
        ORDER BY data_quality DESC
        LIMIT 1
        """,
        (broker.lower(), account_key.lower(), as_of_date),
    ).fetchone()
    if not row or row[0] is None:
        return None
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return None


def external_cash_flows_between(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    start_exclusive: str,
    end_inclusive: str,
) -> float:
    """Sum external CF with start_exclusive < flow_date <= end_inclusive."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) FROM gt_fund_cash_flows
        WHERE broker = ? AND account_key = ?
          AND flow_date > ? AND flow_date <= ?
        """,
        (
            broker.lower(),
            account_key.lower(),
            start_exclusive,
            end_inclusive,
        ),
    ).fetchone()
    return float(row[0] or 0)


def prior_equity_anchor(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    as_of_date: str,
) -> tuple[str, float] | None:
    """Nearest GT equity snapshot strictly before as_of_date."""
    row = conn.execute(
        """
        SELECT as_of_date, liquidation_value
        FROM gt_fund_equity_snapshots
        WHERE broker = ? AND account_key = ? AND as_of_date < ?
        ORDER BY as_of_date DESC, data_quality DESC
        LIMIT 1
        """,
        (broker.lower(), account_key.lower(), as_of_date),
    ).fetchone()
    if not row:
        return None
    return str(row[0]), float(row[1])


def reconstruct_net_liq_for_day(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    as_of_date: str,
) -> ReconDay | None:
    """Best-effort reconstruct account net liq for one calendar day.

    Priority:
    1. Positions book (sum market_value) + cash from same-day equity snap if any
    2. Prior equity anchor + external cash flows only (no mark-to-market —
       used when positions missing; quality lower)

    Returns None when no real local inputs exist (do not invent).
    """
    b = broker.lower()
    key = account_key.lower()
    book = position_book_value(conn, b, key, as_of_date)
    cash = cash_from_equity_snapshot(conn, b, key, as_of_date)

    if book is not None:
        cash_part = float(cash or 0.0)
        total = book + cash_part
        if not math.isfinite(total) or total < 0:
            return None
        return ReconDay(
            as_of_date=as_of_date,
            net_liquidation_value=round(total, 2),
            source="recon:positions+cash",
            data_quality=80 if cash is not None else 70,
            provenance=PROVENANCE_RECONSTRUCTED,
            components={
                "position_book": book,
                "cash": cash_part,
                "method": "positions_sum",
            },
        )

    # Flow-only bridge from prior GT anchor (no mark-to-market).
    # Require non-zero external CF on the path — pure carry-forward of last
    # statement NLV onto every market day is fabrication (flat false series).
    anchor = prior_equity_anchor(conn, b, key, as_of_date)
    if anchor is None:
        return None
    a_date, a_lv = anchor
    cf = external_cash_flows_between(conn, b, key, a_date, as_of_date)
    if abs(float(cf)) < 1e-9:
        return None
    total = a_lv + cf
    if not math.isfinite(total) or total < 0:
        return None
    return ReconDay(
        as_of_date=as_of_date,
        net_liquidation_value=round(total, 2),
        source="recon:anchor+cash_flows",
        data_quality=50,
        provenance=PROVENANCE_RECONSTRUCTED,
        components={
            "anchor_date": a_date,
            "anchor_lv": a_lv,
            "external_cf": cf,
            "method": "anchor_plus_cf",
        },
    )
