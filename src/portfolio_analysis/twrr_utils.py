"""
Reusable TWRR Utilities and Guards

This module contains permanent, reusable functions used by
(replaced by subperiod-based daily_twrr population + gapfill).
"""

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Set


def get_relevant_symbols(conn: sqlite3.Connection, recent_days: int = 90) -> Set[str]:
    """
    Return symbols that are currently relevant for TWRR calculation.

    A symbol is considered relevant if it is either:
    - Present in gt_daily_positions (current holdings), or
    - Has at least one anchor in gt_brokerage_statement_positions, or
    - Has transaction activity in gt_transactions (this includes options treated as independent assets).
    """
    # Current holdings
    holdings = set(
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT symbol FROM gt_daily_positions"
        ).fetchall()
    )

    # Recent anchors from statements
    cutoff = (datetime.now() - timedelta(days=recent_days)).strftime("%Y-%m-%d")
    recent = set(
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT symbol FROM gt_brokerage_statement_positions "
            f"WHERE as_of_date >= '{cutoff}'"
        ).fetchall()
    )

    # Also include symbols with transaction activity (important for options)
    tx_symbols = set(
        r[0]
        for r in conn.execute("SELECT DISTINCT symbol FROM gt_transactions").fetchall()
    )

    return holdings | recent | tx_symbols


def get_symbols_with_price_data(conn: sqlite3.Connection) -> Set[str]:
    """Return all symbols that have at least one price record."""
    return set(
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT symbol FROM market_price_bars"
        ).fetchall()
    )


def has_price_coverage(
    conn: sqlite3.Connection, symbol: str, first_anchor: str
) -> bool:
    """Check if a symbol has price data after its first anchor."""
    count = conn.execute(
        """
        SELECT COUNT(*) FROM market_price_bars
        WHERE symbol = ? AND date >= ?
    """,
        (symbol, first_anchor),
    ).fetchone()[0]
    return count > 0


def should_compute_twrr(conn, symbol, recent_days=90):
    """
    Decide whether we should compute new TWRR rows for this symbol.

    Returns True if the symbol is currently relevant (held or recent anchor).
    This controls *new calculations*, not historical data.
    """
    relevant = get_relevant_symbols(conn, recent_days)
    return symbol in relevant


def classify_symbol(symbol: str) -> str:
    """
    Classify a symbol as 'stock', 'option', or 'other'.
    Options typically contain a space and a strike price pattern (e.g. "TSLA 12/15/2028 400.00 C").
    """
    if not symbol:
        return "other"

    # Options usually have a space and a date/strike pattern
    if " " in symbol and re.search(r"\d{1,2}/\d{1,2}/\d{4}", symbol):
        return "option"

    # Common stock / ETF / etc.
    return "stock"
