#!/usr/bin/env python3
"""
Full Schwab Export Ingestion Script
====================================
Ingests all Schwab export files into the immutable ground-truth tables.

Supported file types:
- Brokerage Statement PDFs          → gt_brokerage_statement_positions
- Positions CSV exports             → gt_daily_positions
- Realized Gain/Loss CSV exports    → gt_realized_gains
- Transactions CSV/XML exports      → gt_transactions

This script is idempotent and safe to re-run when new exports appear.

Usage:
    python ingest_all_schwab_exports.py

Location:
    ~/.portfolio-analysis/ingest_all_schwab_exports.py
"""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

# Ensure we can import the skill

from portfolio_analysis.db import init_db
from portfolio_analysis.paths import broker_exports_dir, default_db_path

# Local copies of the ingest_* functions are defined below for this standalone script
# (used when the script is copied to ~/.portfolio-analysis/). The package versions
# (in src/portfolio_analysis/ingest.py) power the MCP upload tool.

DB_PATH = default_db_path()
EXPORT_DIR = broker_exports_dir("schwab")


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def ingest_daily_positions_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """Ingest Schwab Positions CSV export into gt_daily_positions."""
    count = 0
    as_of_date = None

    # Extract date from filename (supports multiple Schwab naming patterns)
    stem = csv_path.stem
    # Try underscore split first (older patterns)
    for part in stem.split("_"):
        if len(part) == 10 and part.count("-") == 2:
            as_of_date = part
            break
    # Fallback for "…-Positions-YYYY-MM-DD-HHMMSS" style filenames
    if not as_of_date:
        import re

        m = re.search(r"Positions-(\d{4}-\d{2}-\d{2})", stem)
        if m:
            as_of_date = m.group(1)

    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    # Find the header line (starts with "Symbol")
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith('"Symbol"'):
            header_idx = i
            break

    if header_idx is None:
        log(f"  WARNING: No header found in {csv_path.name}")
        return 0

    # Use csv module on the remaining lines
    import io

    data = "".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(data))

    for row in reader:
        symbol = (row.get("Symbol") or "").strip().strip('"')
        if not symbol:
            continue

        qty = _safe_float(row.get("Qty (Quantity)") or row.get("Quantity"))
        if qty is None or qty == 0:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO gt_daily_positions
            (symbol, as_of_date, quantity, avg_cost, market_value,
             unrealized_pl, source_file, data_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, 100)
        """,
            (
                symbol,
                as_of_date,
                qty,
                _safe_float(row.get("Cost/Share")),
                _safe_float(
                    row.get("Mkt Val (Market Value)") or row.get("Market Value")
                ),
                _safe_float(row.get("Gain $ (Gain/Loss $)")),
                csv_path.name,
            ),
        )
        count += 1

    conn.commit()
    return count


def ingest_realized_gains_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """Ingest Schwab Realized Gain/Loss CSV into gt_realized_gains."""
    count = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        # Skip title row
        next(f)
        reader = csv.DictReader(f)

        for row in reader:
            symbol = row.get("Symbol", "").strip().strip('"')
            if not symbol:
                continue

            conn.execute(
                """
                INSERT OR IGNORE INTO gt_realized_gains
                (symbol, opened_date, closed_date, quantity,
                 cost_basis, proceeds, gain_loss, term, wash_sale, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    symbol,
                    _normalize_date(row.get("Opened Date")),
                    _normalize_date(row.get("Closed Date")),
                    _safe_float(row.get("Quantity")),
                    _safe_float(row.get("Cost Per Share")),
                    _safe_float(row.get("Proceeds Per Share")),
                    _safe_float(row.get("Gain/Loss ($)")),
                    row.get("Term", "").strip(),
                    row.get("Wash Sale?", "").strip(),
                    csv_path.name,
                ),
            )
            count += 1

    conn.commit()
    return count


def ingest_transactions_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """Ingest Schwab Transactions CSV into gt_transactions."""
    count = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            symbol = row.get("Symbol", "").strip().strip('"')
            if not symbol:
                continue

            conn.execute(
                """
                INSERT OR IGNORE INTO gt_transactions
                (symbol, transaction_date, transaction_type, quantity,
                 price, amount, fees, description, source_file, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'schwab_export')
            """,
                (
                    symbol,
                    _normalize_date(row.get("Date")),
                    row.get("Action", "").strip(),
                    _safe_float(row.get("Quantity")),
                    _safe_float(row.get("Price")),
                    _safe_float(row.get("Amount")),
                    _safe_float(row.get("Fees & Comm")),
                    row.get("Description", "").strip(),
                    csv_path.name,
                ),
            )
            count += 1

    conn.commit()
    return count


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(
            str(val).replace("$", "").replace(",", "").replace("%", "").strip()
        )
    except (ValueError, TypeError):
        return None


def _normalize_date(d):
    if not d:
        return None
    try:
        from datetime import datetime as dt

        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                return dt.strptime(d.strip().strip('"'), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
    except Exception:
        return None


def main():
    print("=" * 60)
    print("SCHWAB FULL EXPORT INGESTION")
    print("=" * 60)

    # Ensure schema exists
    log("Initializing database schema...")
    conn = init_db(DB_PATH)

    # Discover files — support both flat and nested layout
    # (e.g. <account-folder>/Positions/, <account-folder>/Realized-Gains/, etc.)
    positions_files = sorted(EXPORT_DIR.rglob("*Positions*.csv"))
    gains_files = sorted(EXPORT_DIR.rglob("*GainLoss*Realized*.csv"))
    tx_csv_files = sorted(EXPORT_DIR.rglob("*Transactions*.csv"))

    log(f"Found {len(positions_files)} Positions files")
    log(f"Found {len(gains_files)} Realized Gains files")
    log(f"Found {len(tx_csv_files)} Transactions CSV files")

    total = {"positions": 0, "gains": 0, "transactions": 0}

    # 1. Ingest Daily Positions
    for f in positions_files:
        n = ingest_daily_positions_csv(conn, f)
        log(f"  {f.name}: {n} positions")
        total["positions"] += n

    # 2. Ingest Realized Gains
    for f in gains_files:
        n = ingest_realized_gains_csv(conn, f)
        log(f"  {f.name}: {n} lots")
        total["gains"] += n

    # 3. Ingest Transactions
    for f in tx_csv_files:
        n = ingest_transactions_csv(conn, f)
        log(f"  {f.name}: {n} transactions")
        total["transactions"] += n

    # Final verification
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    for table, cnt in [
        ("gt_daily_positions", "SELECT COUNT(*) FROM gt_daily_positions"),
        ("gt_realized_gains", "SELECT COUNT(*) FROM gt_realized_gains"),
        ("gt_transactions", "SELECT COUNT(*) FROM gt_transactions"),
        (
            "gt_brokerage_statement_positions",
            "SELECT COUNT(*) FROM gt_brokerage_statement_positions",
        ),
    ]:
        row = conn.execute(cnt).fetchone()
        print(f"{table:35} : {row[0]:>6} rows")

    conn.close()
    print("\nFull Schwab export ingestion complete.")


if __name__ == "__main__":
    main()
