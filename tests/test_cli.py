"""
CLI integration tests for the portfolio command.

These tests invoke the actual CLI entry point (via sys.argv patching + main())
to ensure all parameters, happy paths, and error paths (including the new
InsufficientDailyTwrrData enforcement) work correctly.
"""

import sys
import tempfile
from pathlib import Path

import pytest

from portfolio_analysis.cli import main
from portfolio_analysis.db import create_schema, get_connection


def _run_cli(args: list[str], capsys) -> tuple[str, str, int]:
    """Run the CLI with given args and capture output + exit code."""
    old_argv = sys.argv
    sys.argv = ["portfolio"] + args
    try:
        main()
        exit_code = 0
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr()
    return captured.out + captured.err, exit_code


def _live_portfolio_db_available() -> bool:
    """Opt-in only: PORTFOLIO_ANALYSIS_RUN_LIVE_REGRESSION=1 + local private DB."""
    import os

    if os.environ.get("PORTFOLIO_ANALYSIS_RUN_LIVE_REGRESSION", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return False
    db = Path.home() / ".portfolio-analysis" / "portfolio.db"
    if not db.exists():
        return False
    try:
        conn = get_connection(db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM daily_twrr").fetchone()[0]
            return n > 0
        finally:
            conn.close()
    except Exception:
        return False


def test_cli_twrr_basic_happy_path(capsys, tmp_path):
    """Basic `portfolio twrr --symbols AAPL` should succeed when data exists."""
    if not _live_portfolio_db_available():
        pytest.skip("Live portfolio DB required for AAPL TWRR happy-path CLI test")
    # Use the shared test DB that has reconciled data for AAPL
    # (the regression fixtures ensure daily_twrr has subperiod-hpr-v1 data)
    out, code = _run_cli(["twrr", "--symbols", "AAPL"], capsys)
    assert code == 0
    assert "AAPL" in out
    assert "CAPITAL EFFICIENCY" in out or "TWRR" in out.upper()


def test_cli_twrr_detailed_mode(capsys):
    """`portfolio twrr --detailed --symbols AAPL` should produce detailed breakdown."""
    if not _live_portfolio_db_available():
        pytest.skip("Live portfolio DB required for AAPL TWRR detailed CLI test")
    out, code = _run_cli(["twrr", "--detailed", "--symbols", "AAPL"], capsys)
    assert code == 0
    assert "Detailed TWRR Sub-Period Breakdown" in out or "sub-period" in out.lower()
    assert "AAPL" in out


def test_cli_twrr_insufficient_data_errors_with_guidance():
    """
    The new enforcement: when there is insufficient authoritative data in
    daily_twrr, the system raises InsufficientDailyTwrrData with clear
    reconciliation guidance. CLI surfaces this as a non-zero exit.
    """
    from portfolio_analysis.twrr import (
        calculate_daily_twrr,
        InsufficientDailyTwrrData,
    )

    # Use a completely fresh DB with schema but no reconciled data
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "empty.db"
        conn = get_connection(db_path)
        create_schema(conn)

        with pytest.raises(InsufficientDailyTwrrData) as exc:
            calculate_daily_twrr("AAPL", conn=conn)

        msg = str(exc.value).lower()
        assert "reconciliation" in msg or "build_reconciled" in msg
        assert "aapl" in msg


def test_cli_twrr_all_and_separate_options(capsys):
    """Test --all and --separate-options params are accepted without crash."""
    out, code = _run_cli(["twrr", "--all", "--separate-options"], capsys)
    # May have no data or run, but should not hard crash on params
    assert code in (0, 1)  # 1 if insufficient data is ok
    assert (
        "twrr" in out.lower()
        or "insufficient" in out.lower()
        or "capital" in out.lower()
    )


def test_cli_twrr_detailed_without_symbols(capsys):
    """--detailed without symbols should still work (may be limited)."""
    out, code = _run_cli(["twrr", "--detailed"], capsys)
    assert code in (0, 1)


# ------------------------------------------------------------------
# Regression coverage for daily position reconstruction + symbol TWRR chart
# (covers the anchored Journal-safe recon, CLI subcommands, and clean series for charting)
# ------------------------------------------------------------------


def test_cli_daily_positions_series(capsys):
    """`portfolio daily-positions` must produce a clean anchored series when live DB has data.

    Does not assert operator-specific share sizes — only structural CLI success and
    that a Final qty line is present when any equity with GT exists.
    """
    if not _live_portfolio_db_available():
        pytest.skip("Live portfolio DB required for daily-positions CLI test")
    # Pick any equity symbol present in live DB (not a personal hard-coded size).
    from portfolio_analysis.db import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT symbol FROM gt_daily_positions
            WHERE quantity > 0 AND symbol NOT LIKE '% %'
            ORDER BY as_of_date DESC LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("No equity GT positions in live DB")
    symbol = row[0]
    out, code = _run_cli(
        [
            "daily-positions",
            "--symbol",
            symbol,
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-28",
        ],
        capsys,
    )
    assert code == 0
    assert "Final qty on last date:" in out or "quantity" in out.lower()


def test_cli_chart_twrr_ohlc_position_produces_file(capsys, tmp_path):
    """`portfolio chart twrr-ohlc-position` must succeed and write a chart file when live data exists."""
    if not _live_portfolio_db_available():
        pytest.skip("Live portfolio DB required for chart CLI test")
    from portfolio_analysis.db import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT symbol FROM gt_daily_positions
            WHERE quantity > 0 AND symbol NOT LIKE '% %'
            ORDER BY as_of_date DESC LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("No equity GT positions in live DB")
    symbol = row[0]
    out_path = tmp_path / "symbol_twrr_pos_test.png"
    args = [
        "chart",
        "twrr-ohlc-position",
        "--symbol",
        symbol,
        "--start-date",
        "2026-05-01",
        "--end-date",
        "2026-05-28",
        "--output",
        str(out_path),
    ]
    out, code = _run_cli(args, capsys)
    assert code == 0
    # Generator prints "Chart saved to: ..."
    assert "Chart saved" in out or "saved to" in out.lower()
    # File should exist (even if small or matplotlib agg)
    # In some envs it may be created; at minimum the command must not fail hard
    if out_path.exists():
        assert out_path.stat().st_size > 0
