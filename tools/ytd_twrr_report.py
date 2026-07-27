#!/usr/bin/env python3
"""
YTD TWRR Report for current holdings > $10k

Compounds daily returns from the start of the current year.
"""

from datetime import datetime

from portfolio_analysis.db import get_connection
from portfolio_analysis.paths import default_db_path

DB_PATH = default_db_path()


def get_ytd_twrr(conn, symbol, year_start):
    """Compound daily returns from year_start to latest available."""
    rows = conn.execute(
        """
        SELECT as_of_date, daily_return
        FROM daily_twrr
        WHERE symbol = ? AND as_of_date >= ?
        ORDER BY as_of_date
    """,
        (symbol, year_start),
    ).fetchall()

    if not rows:
        return None

    twrr = 1.0
    for r in rows:
        twrr *= 1 + r["daily_return"]

    return {
        "twrr": twrr - 1.0,
        "days": len(rows),
        "start_date": rows[0]["as_of_date"],
        "end_date": rows[-1]["as_of_date"],
    }


def main():
    conn = get_connection(DB_PATH)

    # Get current holdings with market_value > 10000
    holdings = conn.execute("""
        SELECT symbol, quantity, market_value, as_of_date
        FROM gt_daily_positions
        WHERE quantity > 0 AND market_value > 10000
        ORDER BY market_value DESC
    """).fetchall()

    # Filter out options (symbols with spaces or long option-like names)
    holdings = [h for h in holdings if " " not in h["symbol"] and len(h["symbol"]) <= 5]

    year = datetime.now().year
    year_start = f"{year}-01-01"

    print(
        f"\nYTD TWRR Report — Current Positions > $10k (as of {holdings[0]['as_of_date'] if holdings else 'N/A'})"
    )
    print(f"Period: {year_start} → latest\n")
    print(f"{'Symbol':<8} {'Value':>12} {'YTD TWRR':>12} {'Days':>6} {'Period':<20}")
    print("-" * 65)

    total_value = 0
    for h in holdings:
        symbol = h["symbol"]
        value = h["market_value"]
        total_value += value

        ytd = get_ytd_twrr(conn, symbol, year_start)

        if ytd:
            twrr_str = f"{ytd['twrr'] * 100:>8.2f}%"
            period = f"{ytd['start_date']} → {ytd['end_date']}"
            print(
                f"{symbol:<8} ${value:>10,.0f} {twrr_str:>12} {ytd['days']:>6} {period}"
            )
        else:
            print(
                f"{symbol:<8} ${value:>10,.0f} {'— no data —':>12} {'—':>6} {'—':<20}"
            )

    print("-" * 65)
    print(f"{'TOTAL':<8} ${total_value:>10,.0f}")
    print()

    conn.close()


if __name__ == "__main__":
    main()
