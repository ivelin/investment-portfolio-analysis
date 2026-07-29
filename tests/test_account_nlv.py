"""Local account NLV series tool — resolve + serve from daily_account_net_liq."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio_analysis.account_nlv import get_account_nlv_series, resolve_account
from portfolio_analysis.db import init_db


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


def _seed_accounts(conn) -> None:
    conn.execute(
        """
        INSERT INTO gt_fund_accounts (
            broker, account_key, display_name, currency, broker_account_ref, fund_symbol
        ) VALUES
        ('schwab', '47a915ae0e7e', 'Active Trading IRA', 'USD', 'REF1',
         'FUND:schwab:47a915ae0e7e'),
        ('schwab', '8e7febd2cf60', 'Roth IRA', 'USD', 'REF2',
         'FUND:schwab:8e7febd2cf60')
        """
    )
    # last3 column may need ensure
    from portfolio_analysis.account_nlv import set_account_number_last3

    set_account_number_last3(conn, "schwab", "47a915ae0e7e", "052")
    conn.execute(
        """
        INSERT INTO daily_account_net_liq (
            broker, account_key, as_of_date, net_liquidation_value,
            source, provenance
        ) VALUES
        ('schwab', '47a915ae0e7e', '2026-07-27', 1107841.28, 'gt', 'ground_truth'),
        ('schwab', '47a915ae0e7e', '2026-07-28', 1104580.17, 'live', 'live_exact')
        """
    )
    conn.commit()


def test_resolve_by_display_name_and_last3(isolated_home: Path):
    conn = init_db()
    try:
        _seed_accounts(conn)
        r, _, err = resolve_account("Active Trading IRA", conn=conn)
        assert err is None
        assert r is not None
        assert r.account_key == "47a915ae0e7e"
        assert r.match_via == "display_name"

        r2, _, err2 = resolve_account("052", conn=conn)
        assert err2 is None
        assert r2 is not None
        assert r2.account_key == "47a915ae0e7e"
        assert "last3" in r2.match_via or r2.match_via == "account_number_last3"
    finally:
        conn.close()


def test_get_account_nlv_series_local(isolated_home: Path):
    conn = init_db()
    try:
        _seed_accounts(conn)
        out = get_account_nlv_series(
            "052",
            min_days=60,
            conn=conn,
        )
        assert out["ok"] is True
        assert out["reason"] == "partial_coverage"
        assert out["resolved"]["display_name"] == "Active Trading IRA"
        assert len(out["series"]) == 2
        assert out["series"][-1]["net_liquidation_value"] == pytest.approx(1104580.17)
        assert out["client_guidance"]["local_first"] is True
        assert out["client_guidance"]["latest_nlv"] == pytest.approx(1104580.17)
        assert out["client_guidance"]["not_symbol_tool"] is True
    finally:
        conn.close()


def test_mcp_get_account_nlv_series_tool(isolated_home: Path):
    conn = init_db()
    try:
        _seed_accounts(conn)
    finally:
        conn.close()

    from portfolio_analysis import mcp_server

    body = mcp_server.get_account_nlv_series_tool(
        account="Active Trading IRA",
        min_days=60,
    )
    data = json.loads(body)
    assert data["ok"] is True
    assert data["coverage"]["series_len"] == 2
    assert "next_steps" in data
    assert "client_secret" not in body


def test_symbol_tools_redirect_when_query_is_account(isolated_home: Path):
    """Clients must not get a flat-zero position series for account suffix 052."""
    conn = init_db()
    try:
        _seed_accounts(conn)
    finally:
        conn.close()

    from portfolio_analysis import mcp_server

    body = mcp_server.get_daily_positions_tool(
        symbol="052",
        start_date="2026-05-29",
        end_date="2026-07-28",
    )
    data = json.loads(body)
    assert data["ok"] is False
    assert data["reason"] == "wrong_tool_account_not_ticker"
    assert data["resolved_account"]["display_name"] == "Active Trading IRA"
    assert "get_account_nlv_series_tool" in data["message"]
    preview = data["account_nlv_preview"]
    assert preview["series_len"] == 2
    assert preview["latest"]["net_liquidation_value"] == pytest.approx(1104580.17)

    chart = mcp_server.generate_twrr_ohlc_position_chart_tool(symbol="052")
    chart_data = json.loads(chart)
    assert chart_data["reason"] == "wrong_tool_account_not_ticker"


def test_unknown_non_ticker_soft_redirect_to_account_tools(isolated_home: Path):
    """Account-shaped queries soft-redirect; public tickers still proceed."""
    conn = init_db()
    try:
        _seed_accounts(conn)
    finally:
        conn.close()

    from portfolio_analysis import mcp_server

    # Account-shaped, not unique resolve → soft redirect
    body = mcp_server.get_daily_positions_tool(symbol="Mystery Account Nickname")
    data = json.loads(body)
    assert data["ok"] is False
    assert data["reason"] == "unknown_symbol_likely_account_reference"
    assert data["client_guidance"]["likely_account_reference"] is True
    assert "get_account_nlv_series_tool" in data["message"]

    # Public ticker shape must NOT soft-redirect even if absent from empty GT
    body2 = mcp_server.get_daily_positions_tool(
        symbol="AAPL",
        start_date="2026-07-01",
        end_date="2026-07-28",
    )
    if body2.strip().startswith("{"):
        d2 = json.loads(body2)
        assert d2.get("reason") not in (
            "wrong_tool_account_not_ticker",
            "unknown_symbol_likely_account_reference",
        )
    else:
        assert "date | quantity" in body2 or "No " in body2 or "AAPL" in body2


def test_scheduler_data_refresh_maximizes_history():
    """Hourly job must request maximize_history (step 3)."""
    import inspect

    from portfolio_analysis.jobs import scheduler as sched_mod

    src = inspect.getsource(sched_mod.start_scheduler)
    assert "maximize_history=True" in src
    assert "JOB_DATA_REFRESH" in src


def test_pipeline_maximize_after_demo_sync(isolated_home: Path):
    """data_refresh demo path maximizes local NLV (multi-day when raw allows)."""
    from portfolio_analysis.jobs.pipeline import run_data_refresh

    out = run_data_refresh(
        demo=True,
        force=True,
        maximize_history=True,
        allow_reconstruct=True,
        on_insufficient="partial",
    )
    assert out.get("local_first") is True
    assert out.get("maximize_history") is True
    nl = out.get("daily_net_liq") or {}
    # demo seeds multi-day equity → non-empty series
    assert nl.get("ok") is True or nl.get("reason") in (
        "partial_coverage",
        "completed",
        "insufficient_history",
    )
