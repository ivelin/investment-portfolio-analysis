#!/usr/bin/env python3
"""
TWRR Holdings Report - Phase 4 Deliverable

Clean, production-quality report focused on current portfolio holdings.
- Only shows symbols with good price coverage
- Correctly displays 0% for zero-position periods
- Includes summary statistics
"""

import argparse
from datetime import datetime

from portfolio_analysis.db import get_connection
from portfolio_analysis.twrr_utils import get_relevant_symbols
from portfolio_analysis.paths import default_db_path

DB_PATH = default_db_path()


def get_current_holdings(conn):
    """Get symbols that currently have positive quantity."""
    rows = conn.execute("""
        SELECT symbol, quantity, as_of_date
        FROM gt_daily_positions
        WHERE quantity > 0
        ORDER BY symbol
    """).fetchall()
    return {r["symbol"]: {"qty": r["quantity"], "date": r["as_of_date"]} for r in rows}


def get_twrr_summary(conn, symbol, days=30):
    """Get recent TWRR stats for a symbol."""
    rows = conn.execute(
        """
        SELECT as_of_date, daily_return, data_quality
        FROM daily_twrr
        WHERE symbol = ?
        ORDER BY as_of_date DESC
        LIMIT ?
    """,
        (symbol, days),
    ).fetchall()

    if not rows:
        return None

    returns = [r["daily_return"] for r in rows]
    avg_return = sum(returns) / len(returns)
    zero_days = sum(1 for r in returns if r == 0.0)

    return {
        "days": len(rows),
        "avg_daily_return": round(avg_return, 6),
        "zero_return_days": zero_days,
        "latest_date": rows[0]["as_of_date"],
        "latest_return": rows[0]["daily_return"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--days", type=int, default=30, help="Lookback days for summary"
    )
    args = parser.parse_args()

    conn = get_connection(DB_PATH)
    holdings = get_current_holdings(conn)
    relevant = get_relevant_symbols(conn)

    print("\n" + "=" * 80)
    print("TWRR HOLDINGS REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Current holdings with positive quantity: {len(holdings)}")
    print("=" * 80 + "\n")

    good_count = 0
    for symbol in sorted(holdings.keys()):
        if symbol not in relevant:
            continue

        summary = get_twrr_summary(conn, symbol, args.days)
        if not summary:
            print(f"{symbol:8} | No TWRR data yet")
            continue

        good_count += 1
        status = "ZERO" if summary["latest_return"] == 0.0 else "OK"
        print(
            f"{symbol:8} | Qty: {holdings[symbol]['qty']:>8.2f} | "
            f"Latest: {summary['latest_return']:>8.6f} ({status}) | "
            f"Avg {args.days}d: {summary['avg_daily_return']:>8.6f} | "
            f"Zero days: {summary['zero_return_days']:>2}/{summary['days']}"
        )

    print("\n" + "=" * 80)
    print(f"Symbols with TWRR data: {good_count}")
    print("=" * 80 + "\n")

    conn.close()


if __name__ == "__main__":
    main()
