#!/usr/bin/env python3
"""
Coverage Report - Phase 1 Deliverable

Generates a data coverage report for all relevant symbols (current holdings + recent anchors).
Reports price coverage gaps from first anchor date to latest available price.

This is the foundation for trustworthy TWRR reporting.
"""

import argparse
from datetime import datetime
import csv

from portfolio_analysis.db import get_connection
from portfolio_analysis.twrr_utils import get_relevant_symbols
from portfolio_analysis.paths import default_db_path, get_reports_dir

DB_PATH = default_db_path()
REPORTS_DIR = get_reports_dir()


def get_first_anchor(conn, symbol):
    row = conn.execute(
        """
        SELECT MIN(as_of_date) FROM gt_brokerage_statement_positions
        WHERE symbol = ?
    """,
        (symbol,),
    ).fetchone()
    return row[0] if row and row[0] else None


def get_last_price_date(conn, symbol):
    row = conn.execute(
        """
        SELECT MAX(date) FROM market_price_bars WHERE symbol = ?
    """,
        (symbol,),
    ).fetchone()
    return row[0] if row and row[0] else None


def count_price_days(conn, symbol, start_date, end_date):
    if not start_date or not end_date:
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) FROM market_price_bars
        WHERE symbol = ? AND date BETWEEN ? AND ?
    """,
        (symbol, start_date, end_date),
    ).fetchone()
    return row[0] if row else 0


def generate_coverage_report(conn, symbols):
    report = []
    datetime.now().strftime("%Y-%m-%d")

    for symbol in sorted(symbols):
        first_anchor = get_first_anchor(conn, symbol)
        last_price = get_last_price_date(conn, symbol)

        if not first_anchor:
            report.append(
                {
                    "symbol": symbol,
                    "first_anchor": None,
                    "last_price": last_price,
                    "price_days": 0,
                    "expected_days": 0,
                    "coverage_pct": 0.0,
                    "status": "NO_ANCHOR",
                }
            )
            continue

        if not last_price:
            report.append(
                {
                    "symbol": symbol,
                    "first_anchor": first_anchor,
                    "last_price": None,
                    "price_days": 0,
                    "expected_days": 0,
                    "coverage_pct": 0.0,
                    "status": "NO_PRICE_DATA",
                }
            )
            continue

        # Calculate expected trading days (rough approximation)
        start = datetime.strptime(first_anchor, "%Y-%m-%d")
        end = datetime.strptime(last_price, "%Y-%m-%d")
        expected_days = (end - start).days * 5 / 7  # rough trading day estimate

        actual_days = count_price_days(conn, symbol, first_anchor, last_price)
        coverage = (
            min(100.0, (actual_days / max(expected_days, 1)) * 100)
            if expected_days > 0
            else 100.0
        )

        status = "GOOD"
        if coverage < 70:
            status = "POOR"
        elif coverage < 90:
            status = "FAIR"

        report.append(
            {
                "symbol": symbol,
                "first_anchor": first_anchor,
                "last_price": last_price,
                "price_days": actual_days,
                "expected_days": int(expected_days),
                "coverage_pct": round(coverage, 1),
                "status": status,
            }
        )

    return report


def print_report(report):
    print("\n=== TWRR Data Coverage Report ===\n")
    print(
        f"{'Symbol':<8} {'First Anchor':<12} {'Last Price':<12} {'Days':>6} {'Exp':>6} {'Cov%':>7} {'Status':<10}"
    )
    print("-" * 70)
    for r in report:
        print(
            f"{r['symbol']:<8} {str(r['first_anchor'] or '-'):12} {str(r['last_price'] or '-'):12} "
            f"{r['price_days']:>6} {r['expected_days']:>6} {r['coverage_pct']:>6.1f}% {r['status']:<10}"
        )
    print()


def save_csv(report, filename):
    path = REPORTS_DIR / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)
    print(f"Report saved to: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", action="store_true", help="Also save as CSV")
    args = parser.parse_args()

    conn = get_connection(DB_PATH)
    relevant = get_relevant_symbols(conn)

    print(f"Analyzing coverage for {len(relevant)} relevant symbols...")
    report = generate_coverage_report(conn, relevant)

    print_report(report)

    if args.csv:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_csv(report, f"coverage_report_{timestamp}.csv")

    # Summary stats
    good = sum(1 for r in report if r["status"] == "GOOD")
    fair = sum(1 for r in report if r["status"] == "FAIR")
    poor = sum(1 for r in report if r["status"] == "POOR")
    no_data = sum(1 for r in report if r["status"] in ("NO_ANCHOR", "NO_PRICE_DATA"))

    print(f"\nSummary: {good} GOOD | {fair} FAIR | {poor} POOR | {no_data} NO_DATA")

    conn.close()


if __name__ == "__main__":
    main()
