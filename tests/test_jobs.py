"""Gating tests for connector_sync + daily_net_liq jobs (shipped runners)."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from portfolio_analysis.brokers.base import (
    AccountPosition,
    EquitySnapshot,
    FundAccount,
)
from portfolio_analysis.brokers.synthetic import SyntheticBrokerAdapter
from portfolio_analysis.db import init_db
from portfolio_analysis.jobs.connector_sync import (
    run_connector_sync,
    sync_broker_to_gt,
)
from portfolio_analysis.jobs.daily_net_liq import (
    fill_account_net_liq_gap,
    run_daily_net_liq,
    validate_net_liq_value,
)
from portfolio_analysis.jobs.lock import JobLock
from portfolio_analysis.jobs.market_days import is_us_market_day
from portfolio_analysis.jobs.registry import (
    JOB_CONNECTOR_SYNC,
    JOB_DAILY_NET_LIQ,
)
from portfolio_analysis.jobs.runner import start_job, wait_job
from portfolio_analysis.jobs.scheduler import (
    scheduled_job_ids,
    scheduler_started,
    scheduler_status,
    start_scheduler,
    stop_scheduler,
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


def _multi_account_adapter() -> SyntheticBrokerAdapter:
    """Two accounts, multi-day equity — sequential sync target."""
    accounts = []
    snaps = []
    positions = []
    start = date(2026, 1, 5)  # Monday
    for i, key in enumerate(("acct_a", "acct_b")):
        accounts.append(
            FundAccount(
                broker="synthetic",
                account_key=key,
                display_name=f"Acct {key}",
                broker_account_ref=f"REF-{key}",
            )
        )
        base = 100_000.0 + i * 10_000
        for d_off in range(5):
            d = start + timedelta(days=d_off)
            if not is_us_market_day(d):
                continue
            snaps.append(
                EquitySnapshot(
                    account_key=key,
                    broker="synthetic",
                    as_of_date=d.isoformat(),
                    liquidation_value=round(base * (1 + 0.01 * d_off), 2),
                    source="synthetic",
                )
            )
        last = snaps[-1].as_of_date
        positions.append(
            AccountPosition(
                broker="synthetic",
                account_key=key,
                as_of_date=last,
                symbol="AAA" if i == 0 else "BBB",
                quantity=10.0 + i,
                market_value=1000.0,
                price=100.0,
                source="synthetic",
            )
        )
    return SyntheticBrokerAdapter(
        accounts=accounts, snapshots=snaps, cash_flows=[], positions=positions
    )


def test_validate_net_liq_rejects_nonsensical():
    ok, reason, _ = validate_net_liq_value(float("nan"))
    assert not ok and reason == "non_finite"
    ok, reason, _ = validate_net_liq_value(float("inf"))
    assert not ok and reason == "non_finite"
    ok, reason, _ = validate_net_liq_value(-1.0)
    assert not ok and reason == "negative"
    ok, reason, _ = validate_net_liq_value("nope")
    assert not ok and reason == "not_numeric"
    ok, reason, v = validate_net_liq_value(12345.67)
    assert ok and v == 12345.67


def test_connector_sync_sequential_multi_account(isolated_home: Path):
    adapter = _multi_account_adapter()
    result = run_connector_sync(
        brokers=["synthetic"],
        adapters={"synthetic": adapter},
        force=True,
    )
    assert result.ok and not result.skipped
    br = result.brokers[0]
    assert br.accounts == 2
    assert br.snapshots >= 2
    assert set(br.accounts_processed) == {"acct_a", "acct_b"}
    # No invented balances: only adapter values in GT
    conn = init_db()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM gt_fund_equity_snapshots WHERE broker='synthetic'"
        ).fetchone()[0]
        assert n == br.snapshots
        # Values finite and positive
        for row in conn.execute(
            "SELECT liquidation_value FROM gt_fund_equity_snapshots"
        ):
            assert math.isfinite(row[0]) and row[0] > 0
    finally:
        conn.close()


def test_connector_sync_already_running(isolated_home: Path):
    lock = JobLock(JOB_CONNECTOR_SYNC)
    assert lock.try_acquire()
    try:
        result = run_connector_sync(demo=True, force=True)
        assert result.skipped is True
        assert result.reason == "already_running"
        assert result.ok is True
        assert result.lock_held is True
    finally:
        lock.release()


def test_connector_sync_demo_idempotent(isolated_home: Path):
    r1 = run_connector_sync(demo=True, force=True)
    assert r1.ok and r1.brokers[0].gt_changed
    r2 = run_connector_sync(demo=True, force=True)
    assert r2.ok
    assert r2.brokers[0].gt_changed is False
    assert r2.brokers[0].reason == "gt_unchanged_idempotent"


def test_daily_net_liq_gap_market_days_only(isolated_home: Path):
    conn = init_db()
    # Seed GT with Mon–Fri plus a weekend (should ignore weekend for writes
    # even if someone stuffed weekend GT — market day filter still applies)
    mon = date(2026, 1, 5)
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="gap1",
                display_name="Gap",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="gap1",
                broker="synthetic",
                as_of_date=(mon + timedelta(days=i)).isoformat(),
                liquidation_value=50_000.0 + i * 100,
                source="synthetic",
            )
            for i in range(7)  # Mon..Sun
        ],
    )
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)
    # First run: fill all market days with GT through as_of_today=Sunday
    r = run_daily_net_liq(
        broker="synthetic",
        account_key="gap1",
        as_of_today=mon + timedelta(days=6),
        force=True,
        conn=conn,
        skip_lock=True,
    )
    assert r.ok
    rows = conn.execute(
        """
        SELECT as_of_date, net_liquidation_value FROM daily_account_net_liq
        WHERE account_key='gap1' ORDER BY as_of_date
        """
    ).fetchall()
    dates = [r[0] for r in rows]
    # Only market days
    for ds in dates:
        assert is_us_market_day(date.fromisoformat(ds))
    # Weekend not stored
    sat = (mon + timedelta(days=5)).isoformat()
    sun = (mon + timedelta(days=6)).isoformat()
    assert sat not in dates
    assert sun not in dates
    assert len(dates) >= 4  # Mon-Thu or Mon-Fri depending holidays

    # Gap: wipe last two market days and re-run — should refill from last saved
    last_two = dates[-2:]
    for ds in last_two:
        conn.execute(
            "DELETE FROM daily_account_net_liq WHERE account_key='gap1' AND as_of_date=?",
            (ds,),
        )
    conn.commit()
    r2 = fill_account_net_liq_gap(
        conn,
        "synthetic",
        "gap1",
        as_of_today=mon + timedelta(days=6),
    )
    assert r2.rows_written >= 1
    re_dates = [
        x[0]
        for x in conn.execute(
            "SELECT as_of_date FROM daily_account_net_liq WHERE account_key='gap1' ORDER BY 1"
        )
    ]
    for ds in last_two:
        assert ds in re_dates
    conn.close()


def test_daily_net_liq_rejects_bad_and_exact_live_match(isolated_home: Path):
    conn = init_db()
    d0 = date(2026, 1, 5)  # Monday
    live_lv = 77777.77
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="live1",
                display_name="Live",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="live1",
                broker="synthetic",
                as_of_date=d0.isoformat(),
                liquidation_value=77000.0,  # GT differs from live
                source="synthetic",
            ),
            EquitySnapshot(
                account_key="live1",
                broker="synthetic",
                as_of_date=(d0 + timedelta(days=1)).isoformat(),
                liquidation_value=float("nan"),  # invalid — reject
                source="synthetic",
            ),
        ],
    )
    # Manually insert bad GT for Tuesday without going through float nan in EquitySnapshot
    from portfolio_analysis.fund.series import store_adapter_ground_truth

    # Only valid Monday via adapter
    good = SyntheticBrokerAdapter(
        accounts=adapter.list_accounts(),
        snapshots=[adapter.equity_snapshots("live1")[0]],
    )
    store_adapter_ground_truth(conn, good)
    # Inject nonsensical GT row directly
    conn.execute(
        """
        INSERT INTO gt_fund_equity_snapshots
        (broker, account_key, as_of_date, liquidation_value, source, data_quality)
        VALUES ('synthetic', 'live1', ?, -999.0, 'synthetic', 100)
        """,
        ((d0 + timedelta(days=1)).isoformat(),),
    )
    conn.commit()

    r = fill_account_net_liq_gap(
        conn,
        "synthetic",
        "live1",
        as_of_today=d0 + timedelta(days=1),
        live_snapshots={d0.isoformat(): live_lv},
    )
    assert r.rows_rejected >= 1
    row = conn.execute(
        """
        SELECT net_liquidation_value, source FROM daily_account_net_liq
        WHERE account_key='live1' AND as_of_date=?
        """,
        (d0.isoformat(),),
    ).fetchone()
    assert row is not None
    assert row[0] == live_lv  # exact match to live
    assert row[1] == "live_exact"
    # Negative day not written
    bad = conn.execute(
        """
        SELECT COUNT(*) FROM daily_account_net_liq
        WHERE account_key='live1' AND as_of_date=?
        """,
        ((d0 + timedelta(days=1)).isoformat(),),
    ).fetchone()[0]
    assert bad == 0
    conn.close()


def test_daily_net_liq_reprocesses_today_for_live_exact(isolated_home: Path):
    """When last_saved == today, re-run with live must overwrite GT value exactly."""
    conn = init_db()
    today = date(2026, 1, 5)  # Monday market day
    gt_lv = 100.0
    live_lv = 999.99
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="today1",
                display_name="Today",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="today1",
                broker="synthetic",
                as_of_date=today.isoformat(),
                liquidation_value=gt_lv,
                source="synthetic",
            )
        ],
    )
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)

    # First pass: write GT value for today
    r1 = fill_account_net_liq_gap(conn, "synthetic", "today1", as_of_today=today)
    assert r1.rows_written >= 1
    row1 = conn.execute(
        """
        SELECT net_liquidation_value, source FROM daily_account_net_liq
        WHERE account_key='today1' AND as_of_date=?
        """,
        (today.isoformat(),),
    ).fetchone()
    assert row1 is not None
    assert row1[0] == gt_lv

    # Second pass: last_saved == today; live must still win exactly
    r2 = fill_account_net_liq_gap(
        conn,
        "synthetic",
        "today1",
        as_of_today=today,
        live_snapshots={today.isoformat(): live_lv},
    )
    assert r2.live_exact_match is True
    assert r2.rows_written >= 1
    row2 = conn.execute(
        """
        SELECT net_liquidation_value, source FROM daily_account_net_liq
        WHERE account_key='today1' AND as_of_date=?
        """,
        (today.isoformat(),),
    ).fetchone()
    assert row2 is not None
    assert row2[0] == live_lv
    assert row2[1] == "live_exact"
    conn.close()


def test_run_daily_net_liq_adapters_enforce_live_exact(isolated_home: Path):
    """Production-shaped path: adapters provide live LV; stored row matches exactly."""
    today = date(2026, 1, 5)
    gt_lv = 100.0
    live_lv = 88888.88
    # GT first via sync (stale vs live)
    gt_adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="prod1",
                display_name="Prod",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="prod1",
                broker="synthetic",
                as_of_date=today.isoformat(),
                liquidation_value=gt_lv,
                source="synthetic",
            )
        ],
    )
    conn = init_db()
    sync_broker_to_gt(conn, "synthetic", adapter=gt_adapter)
    # Seed daily row from GT only (no live)
    run_daily_net_liq(
        broker="synthetic",
        account_key="prod1",
        as_of_today=today,
        force=True,
        conn=conn,
        adapters={},  # disable auto-load
        skip_lock=True,
    )
    seed = conn.execute(
        "SELECT net_liquidation_value FROM daily_account_net_liq WHERE account_key='prod1'"
    ).fetchone()
    assert seed is not None and seed[0] == gt_lv
    conn.close()

    # Live adapter returns different LV for same as-of (broker snapshot)
    live_adapter = SyntheticBrokerAdapter(
        accounts=list(gt_adapter.list_accounts()),
        snapshots=[
            EquitySnapshot(
                account_key="prod1",
                broker="synthetic",
                as_of_date=today.isoformat(),
                liquidation_value=live_lv,
                source="live_api",
            )
        ],
    )
    # Full shipped runner (new connection via init_db) with adapters inject
    r = run_daily_net_liq(
        broker="synthetic",
        account_key="prod1",
        as_of_today=today,
        force=True,
        adapters={"synthetic": live_adapter},
    )
    assert r.ok and not r.skipped
    assert any(a.live_exact_match for a in r.accounts)

    conn2 = init_db()
    try:
        row = conn2.execute(
            """
            SELECT net_liquidation_value, source FROM daily_account_net_liq
            WHERE broker='synthetic' AND account_key='prod1' AND as_of_date=?
            """,
            (today.isoformat(),),
        ).fetchone()
        assert row is not None
        assert row[0] == live_lv
        assert row[1] == "live_exact"
    finally:
        conn2.close()


def test_daily_net_liq_no_fabricate_without_gt(isolated_home: Path):
    conn = init_db()
    mon = date(2026, 1, 5)
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="sparse",
                display_name="S",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="sparse",
                broker="synthetic",
                as_of_date=mon.isoformat(),
                liquidation_value=10_000.0,
                source="synthetic",
            )
        ],
    )
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)
    # Ask for gap through next Friday with only Monday GT
    fri = mon + timedelta(days=4)
    r = fill_account_net_liq_gap(conn, "synthetic", "sparse", as_of_today=fri)
    rows = conn.execute(
        "SELECT as_of_date FROM daily_account_net_liq WHERE account_key='sparse'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == mon.isoformat()
    # Skipped market days without GT
    assert r.rows_skipped_no_gt >= 1
    conn.close()


def test_jobs_start_background_and_status(isolated_home: Path):
    out = start_job(
        JOB_CONNECTOR_SYNC, background=True, trigger="test", demo=True, force=True
    )
    assert out["run_id"]
    assert out["state"] in ("pending", "running", "ok")
    st = wait_job(out["run_id"], timeout_s=30)
    assert st["state"] in ("ok", "skipped")
    assert st.get("ok") is True
    blob = json.dumps(st)
    assert "client_secret" not in blob
    assert "access_token" not in blob


def test_cli_jobs_and_sync(isolated_home: Path, capsys, monkeypatch):
    import sys

    from portfolio_analysis.cli import main

    monkeypatch.setattr(sys, "argv", ["portfolio", "sync", "--demo", "--force"])
    main()
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["brokers"][0]["broker"] == "synthetic"

    monkeypatch.setattr(sys, "argv", ["portfolio", "jobs", "list"])
    main()
    listing = json.loads(capsys.readouterr().out)
    ids = {j["job_id"] for j in listing["jobs"]}
    from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

    assert JOB_DATA_REFRESH in ids and JOB_DAILY_NET_LIQ in ids

    monkeypatch.setattr(
        sys,
        "argv",
        ["portfolio", "jobs", "run", "daily_net_liq", "--force"],
    )
    main()
    run_out = json.loads(capsys.readouterr().out)
    assert run_out["job_id"] == JOB_DAILY_NET_LIQ
    assert run_out["state"] in ("ok", "skipped")

    monkeypatch.setattr(
        sys,
        "argv",
        ["portfolio", "jobs", "status", "connector_sync"],
    )
    main()
    st = json.loads(capsys.readouterr().out)
    assert st["job_id"] == JOB_CONNECTOR_SYNC
    assert "client_secret" not in st


def test_mcp_jobs_tools(isolated_home: Path):
    from portfolio_analysis import mcp_server

    assert mcp_server.jobs_list_tool is not None
    assert mcp_server.jobs_run_tool is not None
    assert mcp_server.jobs_status_tool is not None

    body = mcp_server.jobs_run_tool(
        job_id="connector_sync", background=False, demo=True, force=True
    )
    data = json.loads(body)
    assert data["job_id"] == "connector_sync"
    assert data.get("ok") is True or data.get("state") == "ok"
    assert "client_secret" not in body

    # Background + poll
    started = json.loads(
        mcp_server.jobs_run_tool(job_id="daily_net_liq", background=True, force=True)
    )
    run_id = started["run_id"]
    wait_job(run_id, timeout_s=30)
    polled = json.loads(mcp_server.jobs_status_tool(run_id=run_id))
    assert polled["run_id"] == run_id
    assert polled["state"] in ("ok", "skipped", "failed", "running")
    assert "access_token" not in mcp_server.jobs_status_tool(run_id=run_id)

    listing = json.loads(mcp_server.jobs_list_tool())
    assert any(j["job_id"] == "daily_net_liq" for j in listing["jobs"])


def test_scheduler_registers_both_jobs(isolated_home: Path):
    assert scheduler_started() is False
    start_scheduler(timezone="UTC")
    try:
        assert scheduler_started() is True
        ids = set(scheduled_job_ids())
        from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

        assert JOB_DATA_REFRESH in ids
        assert JOB_DAILY_NET_LIQ in ids
        st = scheduler_status()
        assert st["started"] is True
        catalog_ids = {j["job_id"] for j in st["catalog"]}
        assert JOB_DATA_REFRESH in catalog_ids
        assert JOB_DAILY_NET_LIQ in catalog_ids
        # One-shot CLI path does not flip scheduler — already started in service only
    finally:
        stop_scheduler()
    assert scheduler_started() is False


def test_service_smoke_env(isolated_home: Path, monkeypatch):
    """Drive service smoke path (scheduler register + clean stop)."""
    import subprocess
    import sys

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PORTFOLIO_ANALYSIS_HOME": str(isolated_home),
        "PORTFOLIO_ANALYSIS_DB_PATH": str(isolated_home / "portfolio.db"),
        "PORTFOLIO_ANALYSIS_SERVICE_SMOKE": "1",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "portfolio_analysis.service"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "connector_sync" in proc.stdout
    assert "daily_net_liq" in proc.stdout
    assert "SMOKE ok" in proc.stdout
