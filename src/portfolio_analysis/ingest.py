import csv
import sqlite3
from pathlib import Path

# ------------------------------------------------------------------
# Compatibility shims (retired paths 2026-05)
# gt_* tables are canonical. Direct structured exports only.
# Old ingest_* shims kept for minimal backward compat in tests/tools.
# ------------------------------------------------------------------


def ingest_brokerage_statement_data(conn: sqlite3.Connection, data: dict) -> int:
    """Deprecated. Returns 0."""
    return 0


def ingest_1099r_distribution(conn: sqlite3.Connection, data: dict) -> int:
    """Stub."""
    print("[shim] ingest_1099r_distribution - not implemented")
    return 0


def ingest_transactions(
    conn: sqlite3.Connection, csv_path: Path, force: bool = False
) -> int:
    """DEPRECATED: use gt_transactions."""
    raise NotImplementedError("Use gt_transactions ingestion instead.")


def ingest_positions(conn: sqlite3.Connection, csv_path: Path, as_of: str) -> int:
    """DEPRECATED: use gt_daily_positions + reconstruction."""
    raise NotImplementedError("Use gt_daily_positions instead.")


def ingest_realized_gains(
    conn: sqlite3.Connection, csv_path: Path, force: bool = False
) -> int:
    """DEPRECATED: use gt_realized_gains."""
    raise NotImplementedError("Use gt_realized_gains instead.")


def ingest_transactions_from_schwab_xml(
    conn: sqlite3.Connection, xml_path: Path, force: bool = False
) -> int:
    """DEPRECATED."""
    raise NotImplementedError("Deprecated.")


def ingest_daily_positions(
    conn: sqlite3.Connection, csv_path: Path, as_of: str, force: bool = False
) -> int:
    """DEPRECATED: use gt_daily_positions."""
    raise NotImplementedError("Use gt_daily_positions instead.")


# ------------------------------------------------------------------
# Real Schwab export ingestors (moved to library for MCP + CLI reuse)
# These populate the gt_* Ground Truth tables from direct user exports.
# Idempotent (INSERT OR IGNORE).
# ------------------------------------------------------------------


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


def ingest_daily_positions_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """Ingest Schwab Positions CSV export into gt_daily_positions."""
    count = 0
    as_of_date = None

    stem = csv_path.stem
    for part in stem.split("_"):
        if len(part) == 10 and part.count("-") == 2:
            as_of_date = part
            break
    if not as_of_date:
        import re

        m = re.search(r"Positions-(\d{4}-\d{2}-\d{2})", stem)
        if m:
            as_of_date = m.group(1)

    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith('"Symbol"'):
            header_idx = i
            break

    if header_idx is None:
        return 0

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
        next(f)  # Skip title row
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


def ingest_schwab_export_file(conn: sqlite3.Connection, file_path: Path) -> int:
    """
    Dispatch ingestion for a single Schwab export file based on its name.
    Supports the primary CSV exports used for GT population.
    """

    name = file_path.name.lower()
    if "positions" in name and name.endswith(".csv"):
        return ingest_daily_positions_csv(conn, file_path)
    elif "gainloss" in name and "realized" in name and name.endswith(".csv"):
        return ingest_realized_gains_csv(conn, file_path)
    elif "transactions" in name and name.endswith(".csv"):
        return ingest_transactions_csv(conn, file_path)
    # XML transactions and brokerage statements are handled by other paths / tools for now.
    # The file will still be saved for manual use or future extension.
    return 0


def ingest_schwab_exports_from_dir(
    export_dir: Path, conn: sqlite3.Connection | None = None
) -> dict[str, int]:
    """
    Ingest all supported Schwab exports found under export_dir (recursive).
    Mirrors the discovery logic of tools/ingest_all_schwab_exports.py .
    Returns counts per category.
    """

    if conn is None:
        from .db import init_db

        conn = init_db()

    positions_files = sorted(export_dir.rglob("*Positions*.csv"))
    gains_files = sorted(export_dir.rglob("*GainLoss*Realized*.csv"))
    tx_csv_files = sorted(export_dir.rglob("*Transactions*.csv"))

    totals = {"positions": 0, "gains": 0, "transactions": 0}

    for f in positions_files:
        totals["positions"] += ingest_daily_positions_csv(conn, f)

    for f in gains_files:
        totals["gains"] += ingest_realized_gains_csv(conn, f)

    for f in tx_csv_files:
        totals["transactions"] += ingest_transactions_csv(conn, f)

    return totals
