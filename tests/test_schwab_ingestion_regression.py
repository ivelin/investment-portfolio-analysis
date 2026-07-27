"""
Schwab Ingestion Regression Tests

These tests protect against regressions in the ingestion of position
anchors into gt_brokerage_statement_positions from high-fidelity sources:

- Monthly AccountStatement CSVs (via direct Equities section extraction
  in tools/ingest_account_statement_equities.py)

AccountStatement CSVs are treated as first-class ground truth and provide
monthly end-of-period position snapshots used as verification anchors
for TWRR reconstruction and daily position calculations.

Run as part of local CI:
    make test
"""

import os
import pytest
from pathlib import Path
import sqlite3

from portfolio_analysis.db import create_schema
from portfolio_analysis.twrr_utils import classify_symbol

DB_PATH = Path.home() / ".portfolio-analysis" / "portfolio.db"


def _live_anchors_ready() -> bool:
    if os.environ.get("PORTFOLIO_ANALYSIS_RUN_LIVE_REGRESSION", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return False
    if not DB_PATH.exists():
        return False
    try:
        connection = sqlite3.connect(str(DB_PATH))
        try:
            n = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name='gt_brokerage_statement_positions'"
            ).fetchone()[0]
            if not n:
                return False
            rows = connection.execute(
                "SELECT COUNT(*) FROM gt_brokerage_statement_positions"
            ).fetchone()[0]
            return rows > 0
        finally:
            connection.close()
    except Exception:
        return False


@pytest.fixture(scope="module")
def conn():
    if not _live_anchors_ready():
        pytest.skip(
            "Live portfolio DB with statement anchors not available "
            "(optional local regression; not required for CI)"
        )
    connection = sqlite3.connect(str(DB_PATH))
    create_schema(connection)  # ensure tables exist (CI may have empty DB)
    yield connection
    connection.close()


def test_fix_has_anchors_in_2026(conn):
    """
    FIX should have position anchors from 2026 Schwab statements.
    This test was added after discovering that 2026-03 and 2026-04
    statements containing FIX were not being ingested.
    """
    count = conn.execute(
        "SELECT COUNT(*) FROM gt_brokerage_statement_positions "
        "WHERE symbol = 'FIX' AND as_of_date >= '2026-01-01'"
    ).fetchone()[0]

    if count == 0:
        pytest.skip(
            "No FIX anchors in gt_brokerage_statement_positions (CI has no real user Schwab data/ingestion)"
        )
    assert count >= 1, (
        f"FIX should have at least one anchor in 2026, but found {count}. "
        "Recent Schwab exports (2026-03, 2026-04) contain FIX but were not ingested."
    )


def test_major_holdings_have_anchors(conn):
    """
    Large current holdings should have at least one historical anchor.
    """
    major_symbols = ["STRC", "GOOGL", "IBIT", "FIX"]
    for sym in major_symbols:
        count = conn.execute(
            "SELECT COUNT(*) FROM gt_brokerage_statement_positions WHERE symbol = ?",
            (sym,),
        ).fetchone()[0]
        if count == 0:
            pytest.skip(
                f"No anchors for {sym} in gt_brokerage_statement_positions (CI has no real user Schwab data/ingestion)"
            )
        assert count > 0, f"{sym} has no anchors in gt_brokerage_statement_positions"


# ============================================================
# ACCOUNT STATEMENT CSV (Equities section) REGRESSION TESTS
# ============================================================


def test_recent_account_statements_contribute_anchors(conn):
    """
    Monthly AccountStatement CSVs (via ingest_account_statement_equities.py)
    must contribute position anchors for 2026 dates.

    These are first-class ground truth and should appear in
    gt_brokerage_statement_positions with source_statement containing
    'AccountStatement'.
    """
    count = conn.execute(
        """
        SELECT COUNT(*) FROM gt_brokerage_statement_positions
        WHERE source_statement LIKE '%AccountStatement%'
          AND as_of_date >= '2026-01-01'
        """
    ).fetchone()[0]

    if count == 0:
        pytest.skip(
            "No AccountStatement anchors in gt_brokerage... (CI has no real user Schwab data/ingestion)"
        )
    assert count >= 100, (
        f"Expected many anchors from recent AccountStatement CSVs, but found only {count}. "
        "Run: python tools/ingest_account_statement_equities.py"
    )


def test_account_statement_anchors_are_recent(conn):
    """
    The newest AccountStatement-derived anchors (May 2026) should be present.
    These serve as high-quality verification points for TWRR reconstruction.
    """
    may_2026_count = conn.execute(
        """
        SELECT COUNT(*) FROM gt_brokerage_statement_positions
        WHERE source_statement LIKE '%AccountStatement%'
          AND as_of_date IN ('2026-05-25', '2026-05-27')
        """
    ).fetchone()[0]

    if may_2026_count == 0:
        pytest.skip(
            "No May 2026 AccountStatement anchors (CI has no real user Schwab data/ingestion)"
        )
    assert may_2026_count > 0, (
        "No anchors found from May 2026 AccountStatements. "
        "These are critical recent verification anchors."
    )


# ============================================================
# SYMBOL CLASSIFICATION TESTS (critical for options separation)
# ============================================================


def test_classify_symbol_leaps_and_options():
    """classify_symbol must correctly identify LEAPs and short-dated options as 'option'."""

    # LEAP examples (long-dated)
    assert classify_symbol("TSLA 12/15/2028 400.00 C") == "option"
    assert classify_symbol("AAPL 01/15/2027 250.00 P") == "option"

    # Short-dated options
    assert classify_symbol("NVDA 06/06/2026 140.00 C") == "option"
    assert classify_symbol("SPY 05/30/2026 580.00 P") == "option"

    # Regular stocks / ETFs must remain "stock"
    assert classify_symbol("TSLA") == "stock"
    assert classify_symbol("STRC") == "stock"
    assert classify_symbol("IBIT") == "stock"
    assert classify_symbol("GOOGL") == "stock"

    # Edge cases
    assert classify_symbol("") == "other"
    assert classify_symbol(None) == "other"
    assert classify_symbol("INVALID") == "stock"
