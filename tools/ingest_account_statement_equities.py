#!/usr/bin/env python3
"""
Ingest Equities positions from Schwab AccountStatement CSVs into
gt_brokerage_statement_positions as first-class ground truth anchors.

See the canonical reference for the full ingestion strategy:
docs/Ingestion-Workflow.md

This script implements the "Monthly AccountStatement CSVs" path.
It derives as_of_date primarily from the filename and records any
mismatch with the header "through" date as a red flag.

Usage:
    uv run python tools/ingest_account_statement_equities.py
"""

import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from portfolio_analysis.paths import broker_exports_dir, default_db_path

DB_PATH = default_db_path()
# Scan all account subfolders under the Schwab exports tree (no personal folder names).
EXPORT_ROOT = broker_exports_dir("schwab")


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def parse_date_from_filename(filename: str) -> Optional[str]:
    """Extract YYYY-MM-DD from filenames like 2026-05-25-AccountStatement.csv"""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return match.group(1)
    return None


def parse_through_date_from_header(header_line: str) -> Optional[str]:
    """
    Parse the 'through' date from header lines like:
    'Account Statement for ... since 4/30/26 through 5/25/26'
    Returns YYYY-MM-DD or None.
    """
    match = re.search(
        r"through\s+(\d{1,2}/\d{1,2}/\d{2,4})", header_line, re.IGNORECASE
    )
    if not match:
        return None
    raw = match.group(1)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_equities_section(csv_path: Path) -> list[dict]:
    """
    Parse the Equities section from an AccountStatement CSV.
    Returns list of dicts with symbol, quantity, etc.
    """
    positions = []
    in_equities = False
    header_found = False

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue

            line = ",".join(row).strip()

            if "Equities" in line and not header_found:
                in_equities = True
                continue

            if in_equities:
                if line.startswith("Symbol,Description,Qty"):
                    header_found = True
                    continue

                # Stop at next major section
                if any(
                    x in line
                    for x in [
                        "Options",
                        "Profits and Losses",
                        "Account Summary",
                        "Cash Balance",
                    ]
                ):
                    break

                if header_found and len(row) >= 3:
                    symbol = row[0].strip().upper()
                    if not symbol or symbol.startswith(","):
                        continue

                    qty_str = (
                        row[2]
                        .strip()
                        .replace("+", "")
                        .replace(",", "")
                        .replace('"', "")
                    )
                    try:
                        quantity = float(qty_str)
                    except ValueError:
                        continue

                    if quantity == 0:
                        continue

                    # Optional fields
                    market_price = None
                    market_value = None
                    if len(row) > 4:
                        try:
                            market_price = float(
                                row[3].replace(",", "").replace('"', "").strip()
                            )
                        except Exception:
                            pass
                    if len(row) > 5:
                        try:
                            market_value = float(
                                row[4]
                                .replace("$", "")
                                .replace(",", "")
                                .replace('"', "")
                                .strip()
                            )
                        except Exception:
                            pass

                    positions.append(
                        {
                            "symbol": symbol,
                            "quantity": quantity,
                            "market_price": market_price,
                            "market_value": market_value,
                        }
                    )

    return positions


def ingest_account_statement_equities(conn: sqlite3.Connection, csv_path: Path) -> int:
    filename = csv_path.name
    as_of_date = parse_date_from_filename(filename)
    if not as_of_date:
        log(f"  WARNING: Could not parse date from filename: {filename}")
        return 0

    # Read header for cross-check
    header_line = ""
    with open(csv_path, encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i > 5:
                break
            if "Account Statement" in line or "since" in line.lower():
                header_line = line.strip()
                break

    header_through_date = parse_through_date_from_header(header_line)

    notes = f"Extracted from Equities section of Account Statement CSV. Filename-derived as_of_date={as_of_date}."
    if header_through_date and header_through_date != as_of_date:
        red_flag = f" RED FLAG: Header 'through' date ({header_through_date}) differs from filename date ({as_of_date})."
        notes += red_flag
        log(f"  {red_flag}")

    positions = parse_equities_section(csv_path)
    if not positions:
        log(f"  No equities positions found in {filename}")
        return 0

    count = 0
    for pos in positions:
        conn.execute(
            """
            INSERT OR IGNORE INTO gt_brokerage_statement_positions
            (symbol, as_of_date, quantity, market_price, market_value,
             source_statement, statement_period_end, data_quality, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pos["symbol"],
                as_of_date,
                pos["quantity"],
                pos.get("market_price"),
                pos.get("market_value"),
                filename,
                header_through_date or as_of_date,
                95,  # Slightly lower than pure Positions CSVs but still very high
                notes,
            ),
        )
        count += 1

    conn.commit()
    return count


def main():
    print("=" * 70)
    print("ACCOUNT STATEMENT EQUITIES → gt_brokerage_statement_positions INGESTION")
    print("=" * 70)

    if not EXPORT_ROOT.exists():
        print(f"ERROR: Directory not found: {EXPORT_ROOT}")
        return

    # Nested layout: exports/{broker}/<account-folder>/AccountStatements/*.csv
    # Flat layout: exports/{broker}/**/*AccountStatement*.csv
    files = sorted(EXPORT_ROOT.rglob("*AccountStatement*.csv"))
    if not files:
        print("No AccountStatement CSV files found under broker exports root.")
        return

    log(f"Found {len(files)} AccountStatement CSV files under {EXPORT_ROOT}")

    conn = sqlite3.connect(DB_PATH)

    total = 0
    for f in files:
        log(f"Processing {f.name} ...")
        n = ingest_account_statement_equities(conn, f)
        log(f"  Ingested {n} equity positions from {f.name}")
        total += n

    print("\n" + "=" * 70)
    print(
        f"INGESTION COMPLETE — {total} total positions ingested across all statements"
    )
    print("=" * 70)

    # Quick verification
    row = conn.execute("""
        SELECT COUNT(*) as total,
               MIN(as_of_date) as oldest,
               MAX(as_of_date) as newest
        FROM gt_brokerage_statement_positions
    """).fetchone()
    print(f"\nCurrent gt_brokerage_statement_positions: {row[0]} rows")
    print(f"Date range: {row[1]} → {row[2]}")

    conn.close()


if __name__ == "__main__":
    main()
