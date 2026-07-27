"""Weed the Garden report workflow.

Generates clean, actionable output with summary statistics and CANSLIM scoring.
"""

from typing import List, Dict, Any
import sqlite3
from datetime import datetime

from .db import get_connection
from .twrr import calculate_daily_twrr
from .canslim import score_canslim


def generate_weed_the_garden_report(
    conn: sqlite3.Connection = None,
) -> List[Dict[str, Any]]:
    """
    Generate the full Weed the Garden report with efficiency + CANSLIM scoring.
    """
    if conn is None:
        conn = get_connection()

    from .db import ensure_real_data

    if not ensure_real_data(conn, require_daily_positions=False):
        return []  # Caller should show appropriate message

    report = []

    symbols = conn.execute("""
        SELECT DISTINCT symbol FROM (
            SELECT symbol FROM positions
            UNION
            SELECT symbol FROM realized_gains
        )
        ORDER BY symbol
    """).fetchall()

    for row in symbols:
        symbol = row["symbol"]

        pos = conn.execute(
            """
            SELECT symbol, quantity, avg_cost, unrealized_pl, as_of_date
            FROM positions
            WHERE symbol = ?
            ORDER BY as_of_date DESC
            LIMIT 1
        """,
            (symbol,),
        ).fetchone()

        current_position = dict(pos) if pos else None

        realized_rows = conn.execute(
            """
            SELECT 
                opened_date,
                closed_date,
                quantity,
                cost_basis,
                gain_loss
            FROM realized_gains
            WHERE symbol = ?
            ORDER BY closed_date
        """,
            (symbol,),
        ).fetchall()

        realized_gains = [dict(r) for r in realized_rows]

        # Use real Daily TWRR as the source of truth for Capital Efficiency
        twrr = calculate_daily_twrr(symbol, conn=conn) or {}
        canslim = score_canslim(symbol, realized_gains, current_position)

        combined = {
            "symbol": symbol,
            "efficiency_index": twrr.get("twrr_30d", 0),
            "twrr_30d": twrr.get("twrr_30d"),
            "twrr_60d": twrr.get("twrr_60d"),
            "twrr_90d": twrr.get("twrr_90d"),
            "twrr_ytd": twrr.get("twrr_ytd"),
            "recommendation": twrr.get("recommendation_hint", "Monitor"),
            **canslim,
        }
        report.append(combined)

    return report


def print_weed_the_garden_report(report: List[Dict[str, Any]]) -> None:
    """Print a clean, professional report with summary."""
    if not report:
        print("No data found. Please ingest Schwab exports first.")
        return

    # Sort by real 30-day TWRR (event-driven) + CANSLIM
    def sort_key(x):
        twrr30 = x.get("twrr_30d", 0)
        canslim = x.get("canslim_score", 50)
        return (twrr30 * 0.6) + (canslim * 0.4)

    sorted_report = sorted(report, key=sort_key, reverse=True)

    print("\n" + "=" * 100)
    print("                    WEED THE GARDEN REPORT (Event-Driven TWRR + CANSLIM)")
    print(f"                    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100 + "\n")

    # Header (using real TWRR 30d as primary signal)
    print(
        f"{'Symbol':<8} {'TWRR 30d':>9} {'CANSLIM':>8} {'Profit':>12}  Recommendation"
    )
    print("-" * 100)

    keep_count = 0
    weed_count = 0
    monitor_count = 0
    total_profit = 0.0

    for r in sorted_report:
        twrr30 = r.get("twrr_30d", 0)
        canslim = r.get("canslim_score", 50)
        profit = r.get("total_profit", 0)
        rec = r.get("recommendation", "")

        total_profit += profit

        if "Keep" in rec and "Weed" not in rec:
            keep_count += 1
        elif "Weed" in rec:
            weed_count += 1
        else:
            monitor_count += 1

        print(
            f"{r['symbol']:<8} {twrr30:>9.2f} {canslim:>8.0f} {profit:>12,.0f}  {rec}"
        )

    # Summary
    print("\n" + "-" * 100)
    print("SUMMARY")
    print("-" * 100)
    print(f"Total symbols analyzed     : {len(report)}")
    print(f"Strong performers (Keep)   : {keep_count}")
    print(f"Monitor                    : {monitor_count}")
    print(f"Weed candidates            : {weed_count}")
    print(f"Total realized + unrealized profit : ${total_profit:,.0f}")
    print("=" * 100 + "\n")
