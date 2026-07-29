"""Seed equity snapshots from local statement/positions exports → NLV series."""

from __future__ import annotations

from pathlib import Path

import pytest

from portfolio_analysis.account_nlv import get_account_nlv_series
from portfolio_analysis.db import init_db
from portfolio_analysis.jobs.daily_net_liq import run_daily_net_liq
from portfolio_analysis.jobs.export_equity_seed import (
    seed_from_account_statement,
    seed_equity_from_local_exports,
)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "pa-home"
    home.mkdir()
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(home))
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_DB_PATH", str(home / "portfolio.db"))
    for key in (
        "PORTFOLIO_ANALYSIS_EXPORTS_DIR",
        "PORTFOLIO_ANALYSIS_REPORTS_DIR",
        "SCHWAB_TOKENS_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    return home


def _seed_account(conn) -> None:
    conn.execute(
        """
        INSERT INTO gt_fund_accounts (
            broker, account_key, display_name, currency, broker_account_ref, fund_symbol
        ) VALUES (
            'schwab', '47a915ae0e7e', 'Active Trading IRA', 'USD', 'REF',
            'FUND:schwab:47a915ae0e7e'
        )
        """
    )
    conn.commit()


def test_parse_statement_nlv_and_derive_series(isolated_home: Path):
    conn = init_db()
    try:
        _seed_account(conn)
        stmt_dir = (
            isolated_home
            / "schwab-exports"
            / "Active-Trading-IRA"
            / "AccountStatements"
        )
        stmt_dir.mkdir(parents=True)
        # Minimal statement with header + NLV (filename date is as_of)
        body = (
            "Account Statement for 46017052SCHW (Active Trading IRA) "
            "since 3/31/26 through 4/29/26\n\n"
            'Net Liquidating Value,"$1,146,571.14"\n'
        )
        path = stmt_dir / "2026-04-29-AccountStatement.csv"
        path.write_text(body, encoding="utf-8")
        # second month
        path2 = stmt_dir / "2026-05-27-AccountStatement.csv"
        path2.write_text(
            "Account Statement for 46017052SCHW (Active Trading IRA)\n"
            'Net Liquidating Value,"$1,311,378.20"\n',
            encoding="utf-8",
        )

        n, err = seed_from_account_statement(conn, path)
        assert err is None
        assert n == 1
        n2, err2 = seed_from_account_statement(conn, path2)
        assert err2 is None and n2 == 1
        conn.commit()

        r = run_daily_net_liq(
            force=True,
            maximize_history=True,
            allow_reconstruct=True,
            on_insufficient="partial",
            skip_lock=True,
            conn=conn,
            adapters={},  # hermetic: no live Schwab bleed-in
            live_by_account={},
        )
        assert r.ok
        # Only statement days (no flat carry-forward for every market day)
        rows = conn.execute(
            """
            SELECT as_of_date, net_liquidation_value, provenance
            FROM daily_account_net_liq
            WHERE account_key='47a915ae0e7e'
            ORDER BY 1
            """
        ).fetchall()
        assert [(r[0], r[2]) for r in rows] == [
            ("2026-04-29", "ground_truth"),
            ("2026-05-27", "ground_truth"),
        ]
        assert rows[0][1] == pytest.approx(1146571.14)
        assert rows[1][1] == pytest.approx(1311378.20)

        out = get_account_nlv_series(
            "052",
            min_days=60,
            start_date="2026-05-29",
            end_date="2026-07-28",
            conn=conn,
        )
        assert out["ok"] is True
        assert out["reason"] == "partial_coverage"
        # May–Jul window only has May 27 among our two anchors? May 27 is before
        # 2026-05-29 → 0 or 1 in window; full local has both.
        assert out["coverage"]["series_len_all_local"] == 2
        assert "series_all_local" in out
        assert len(out["series_all_local"]) == 2
        assert out["client_guidance"]["chart_sparse_ok"] is True
        assert out["client_guidance"]["do_not_invent_missing_days"] is True
        assert (
            out["client_guidance"]["do_not_recommend_export_upload_for_dense_nlv"]
            is True
        )
        assert any(
            "do not ask" in s.lower() and "upload" in s.lower()
            for s in out["next_steps"]
        )
    finally:
        conn.close()


def test_no_flat_forward_fill_without_cash_flows(isolated_home: Path):
    """anchor+cf recon must not invent daily NLV when CF=0."""
    from portfolio_analysis.jobs.net_liq_reconstruct import reconstruct_net_liq_for_day

    conn = init_db()
    try:
        _seed_account(conn)
        conn.execute(
            """
            INSERT INTO gt_fund_equity_snapshots (
                broker, account_key, as_of_date, liquidation_value, source, data_quality
            ) VALUES ('schwab', '47a915ae0e7e', '2026-04-29', 1000000.0, 'export:test', 95)
            """
        )
        conn.commit()
        # Day with no positions and no CF → None (not flat 1e6)
        recon = reconstruct_net_liq_for_day(
            conn, "schwab", "47a915ae0e7e", "2026-05-01"
        )
        assert recon is None
    finally:
        conn.close()
