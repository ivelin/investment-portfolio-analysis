"""On-demand data refresh pipeline + client-facing messages (shipped path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio_analysis.jobs.client_messages import enrich_job_payload
from portfolio_analysis.jobs.pipeline import run_data_refresh


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


def test_run_data_refresh_demo_has_guidance(isolated_home: Path):
    out = run_data_refresh(
        demo=True,
        force=True,
        min_days=5,
        start_date="2025-01-02",
        end_date="2025-02-10",
        on_insufficient="partial",
    )
    assert out["job_id"] == "data_refresh"
    assert "connector_sync" in out
    assert "daily_net_liq" in out
    assert out.get("message")
    assert out.get("next_steps")
    assert out.get("client_guidance")
    assert out["connector_sync"].get("ok") is True
    # pipeline should not hide short-history semantics
    assert (
        "message" in out["daily_net_liq"] or out["daily_net_liq"].get("ok") is not None
    )


def test_enrich_insufficient_history_guides_current_snapshot(isolated_home: Path):
    payload = {
        "ok": False,
        "reason": "insufficient_history",
        "state": "failed",
        "coverage": {
            "min_days_requested": 60,
            "min_series_len": 2,
            "max_series_len": 2,
            "window_start": "2026-01-01",
            "window_end": "2026-07-28",
            "rows_ground_truth": 2,
            "rows_reconstructed": 0,
            "rows_skipped_no_source": 40,
        },
    }
    enriched = enrich_job_payload("daily_net_liq", payload)
    assert enriched["client_guidance"]["can_answer_current_snapshot"] is True
    assert enriched["client_guidance"]["serve_best_available_series"] is True
    assert enriched["client_guidance"]["local_first"] is True
    assert (
        enriched["client_guidance"]["do_not_recommend_export_upload_for_dense_nlv"]
        is True
    )
    assert (
        "local" in enriched["message"].lower() or "nlv" in enriched["message"].lower()
    )
    assert any(
        "current" in s.lower() or "nlv" in s.lower() for s in enriched["next_steps"]
    )
    joined = " ".join(enriched["next_steps"]).lower()
    assert "upload" in joined and ("do not" in joined or "don't" in joined)


def test_mcp_refresh_and_jobs_run_tools(isolated_home: Path):
    from portfolio_analysis import mcp_server

    assert hasattr(mcp_server, "refresh_portfolio_data_tool")
    body = mcp_server.refresh_portfolio_data_tool(
        demo=True,
        force=True,
        min_days=5,
        start_date="2025-01-02",
        end_date="2025-02-10",
        on_insufficient="partial",
        background=False,
    )
    data = json.loads(body)
    assert data["job_id"] == "data_refresh"
    assert data.get("next_steps")
    assert data.get("client_guidance", {}).get("local_first") is True
    assert "client_secret" not in body

    # jobs_run still works and carries guidance after finish
    run_body = mcp_server.jobs_run_tool(
        job_id="connector_sync",
        background=False,
        demo=True,
        force=True,
    )
    run = json.loads(run_body)
    assert run.get("ok") is True
    assert run.get("message") or (run.get("result") or {}).get("message")


def test_data_refresh_lock_prevents_duplicate(isolated_home: Path):
    from portfolio_analysis.jobs.lock import JobLock
    from portfolio_analysis.jobs.pipeline import run_data_refresh
    from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

    lock = JobLock(JOB_DATA_REFRESH)
    assert lock.try_acquire()
    try:
        out = run_data_refresh(demo=True, force=True)
        assert out.get("skipped") is True
        assert out.get("reason") == "already_running"
        assert out.get("next_steps")
        assert out.get("client_guidance", {}).get("outcome") == "already_running"
    finally:
        lock.release()


def test_pipeline_respects_standalone_connector_lock(isolated_home: Path):
    """Skeptic: holding connector_sync must block data_refresh from syncing."""
    from portfolio_analysis.jobs.lock import JobLock
    from portfolio_analysis.jobs.pipeline import run_data_refresh
    from portfolio_analysis.jobs.registry import JOB_CONNECTOR_SYNC

    lock = JobLock(JOB_CONNECTOR_SYNC)
    assert lock.try_acquire()
    try:
        out = run_data_refresh(demo=True, force=True)
        assert out.get("skipped") is True
        assert out.get("reason") == "already_running"
        assert out.get("blocked_on") == JOB_CONNECTOR_SYNC
        # Must not have run a successful sync while lock held
        assert out.get("connector_sync") is None or out.get("skipped")
    finally:
        lock.release()


def test_standalone_connector_skips_when_pipeline_lock_held(isolated_home: Path):
    from portfolio_analysis.jobs.connector_sync import run_connector_sync
    from portfolio_analysis.jobs.lock import JobLock
    from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

    lock = JobLock(JOB_DATA_REFRESH)
    assert lock.try_acquire()
    try:
        r = run_connector_sync(demo=True, force=True)
        assert r.skipped is True
        assert r.reason == "already_running"
    finally:
        lock.release()


def test_standalone_daily_net_liq_skips_when_pipeline_lock_held(isolated_home: Path):
    """Skeptic: :35 top-up / standalone NLV must not race data_refresh."""
    from portfolio_analysis.jobs.daily_net_liq import run_daily_net_liq
    from portfolio_analysis.jobs.lock import JobLock
    from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

    lock = JobLock(JOB_DATA_REFRESH)
    assert lock.try_acquire()
    try:
        r = run_daily_net_liq(force=True, allow_reconstruct=True)
        assert r.skipped is True
        assert r.reason == "already_running"
    finally:
        lock.release()


def test_pipeline_respects_standalone_daily_net_liq_lock(isolated_home: Path):
    """Holding daily_net_liq must block data_refresh (family lock order)."""
    from portfolio_analysis.jobs.lock import JobLock
    from portfolio_analysis.jobs.pipeline import run_data_refresh
    from portfolio_analysis.jobs.registry import JOB_DAILY_NET_LIQ

    lock = JobLock(JOB_DAILY_NET_LIQ)
    assert lock.try_acquire()
    try:
        out = run_data_refresh(demo=True, force=True)
        assert out.get("skipped") is True
        assert out.get("reason") == "already_running"
        assert out.get("blocked_on") == JOB_DAILY_NET_LIQ
        assert out.get("connector_sync") is None
    finally:
        lock.release()


def test_mcp_jobs_run_data_refresh_passes_demo_and_window(isolated_home: Path):
    """jobs_run_tool(job_id=data_refresh) must forward demo/window kwargs."""
    import json

    from portfolio_analysis import mcp_server

    body = mcp_server.jobs_run_tool(
        job_id="data_refresh",
        background=False,
        demo=True,
        force=True,
        min_days=5,
        start_date="2025-01-02",
        end_date="2025-02-10",
        allow_reconstruct=True,
        on_insufficient="partial",
    )
    data = json.loads(body)
    # start_job wraps result
    res = data.get("result") or data
    assert data.get("job_id") == "data_refresh" or res.get("job_id") == "data_refresh"
    assert data.get("ok") is True or res.get("ok") is True
    # demo path must have completed sync section when not skipped
    if not data.get("skipped") and not res.get("skipped"):
        sync = res.get("connector_sync") or data.get("connector_sync")
        assert sync is not None
        assert (
            sync.get("demo") is True
            or (sync.get("brokers") or [{}])[0].get("broker") == "synthetic"
        )


def test_maximize_history_fills_from_earliest_raw(isolated_home: Path):
    """After demo sync, maximize_history derives multi-day NLV from local raw."""
    from portfolio_analysis.db import init_db
    from portfolio_analysis.jobs.pipeline import run_data_refresh

    out = run_data_refresh(
        demo=True,
        force=True,
        maximize_history=True,
        allow_reconstruct=True,
        on_insufficient="partial",
    )
    assert out.get("ok") is True or out.get("reason") in (
        "partial_coverage",
        "completed",
        "insufficient_history",
    )
    assert out.get("local_first") is True
    nl = out.get("daily_net_liq") or {}
    cov = nl.get("coverage") or {}
    # demo seeds ~40 calendar days of equity → multi market-day series
    assert (cov.get("min_series_len") or 0) >= 5 or (
        nl.get("accounts") and nl["accounts"][0].get("series_len_in_window", 0) >= 5
    )
    conn = init_db()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_account_net_liq WHERE broker='synthetic'"
        ).fetchone()[0]
        assert n >= 5
        prov = {
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT provenance FROM daily_account_net_liq WHERE broker='synthetic'"
            )
        }
        assert "ground_truth" in prov or "live_exact" in prov or "reconstructed" in prov
    finally:
        conn.close()
