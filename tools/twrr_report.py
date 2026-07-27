#!/usr/bin/env python3
"""
Generic TWRR Report - Repeatable Skill Workflow

Uses reusable guards from twrr_utils.py.
"""

import argparse
from datetime import datetime, timedelta

from portfolio_analysis.db import get_connection
from portfolio_analysis.twrr_utils import get_relevant_symbols
from portfolio_analysis.paths import default_db_path

DB_PATH = default_db_path()


def calculate_linked_twrr(returns):
    if not returns:
        return None
    total = 1.0
    for r in returns:
        total *= 1 + r
    return total - 1


def generate_report(conn, symbol):
    rows = conn.execute(
        """
        SELECT as_of_date, daily_return
        FROM daily_twrr
        WHERE symbol = ?
        ORDER BY as_of_date
    """,
        (symbol,),
    ).fetchall()

    if not rows:
        return

    returns_by_date = {r["as_of_date"]: r["daily_return"] for r in rows}
    dates = sorted(returns_by_date.keys())
    today = dates[-1]

    start_30 = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=30)).strftime(
        "%Y-%m-%d"
    )
    start_90 = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=90)).strftime(
        "%Y-%m-%d"
    )
    start_ytd = f"{today[:4]}-01-01"

    r30 = [returns_by_date[d] for d in dates if d >= start_30]
    r90 = [returns_by_date[d] for d in dates if d >= start_90]
    rytd = [returns_by_date[d] for d in dates if d >= start_ytd]

    twrr_30 = calculate_linked_twrr(r30)
    twrr_90 = calculate_linked_twrr(r90)
    twrr_ytd = calculate_linked_twrr(rytd)

    print(f"\n{symbol} TWRR Report (as of {today})")
    print("-" * 45)
    print(
        f"30-Day TWRR : {twrr_30 * 100:7.2f}%"
        if twrr_30 is not None
        else "30-Day TWRR : N/A"
    )
    print(
        f"90-Day TWRR : {twrr_90 * 100:7.2f}%"
        if twrr_90 is not None
        else "90-Day TWRR : N/A"
    )
    print(
        f"YTD TWRR    : {twrr_ytd * 100:7.2f}%"
        if twrr_ytd is not None
        else "YTD TWRR    : N/A"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol")
    parser.add_argument("--symbols")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    conn = get_connection(DB_PATH)
    relevant = get_relevant_symbols(conn)

    if args.symbol:
        symbols = [args.symbol.upper()]
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif args.all:
        symbols = sorted(relevant)
    else:
        print("Use --symbol, --symbols, or --all")
        return

    # Only report on relevant symbols
    symbols = [s for s in symbols if s in relevant]

    for sym in symbols:
        generate_report(conn, sym)

    conn.close()


if __name__ == "__main__":
    main()
