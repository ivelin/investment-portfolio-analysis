#!/usr/bin/env python3
"""
Ingest a Positions CSV (extracted from Schwab PDF) into gt_brokerage_statement_positions.

Usage:
    python tools/ingest_positions_csv.py 2026-04-30_positions.csv --as-of 2026-04-30
"""

import argparse
import csv
import sqlite3
from pathlib import Path
from portfolio_analysis.paths import default_db_path

DB_PATH = default_db_path()


def ingest_positions_csv(csv_path: Path, as_of_date: str = None):
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return 0

    conn = sqlite3.connect(DB_PATH)
    count = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row.get("symbol", "").strip().upper()
            if not symbol or " " in symbol:
                continue

            try:
                qty = float(row.get("quantity", 0))
            except Exception:
                qty = 0

            if qty == 0:
                continue

            price = _safe_float(row.get("market_price"))
            value = _safe_float(row.get("market_value"))
            cost = _safe_float(row.get("cost_basis"))

            conn.execute(
                """
                INSERT OR IGNORE INTO gt_brokerage_statement_positions
                (symbol, as_of_date, quantity, market_price, market_value, cost_basis,
                 source_statement, page_number, data_quality, extraction_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 85, 'csv_import')
            """,
                (
                    symbol,
                    as_of_date or "2026-04-30",
                    qty,
                    price,
                    value,
                    cost,
                    csv_path.name,
                    row.get("page"),
                ),
            )
            count += 1

    conn.commit()
    conn.close()
    print(f"Ingested {count} positions from {csv_path.name}")
    return count


def _safe_float(val):
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", help="CSV file from extract_positions_to_csv.py")
    parser.add_argument("--as-of", help="Statement date (YYYY-MM-DD)")
    args = parser.parse_args()

    ingest_positions_csv(Path(args.csv), args.as_of)
