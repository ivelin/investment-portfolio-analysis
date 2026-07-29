"""Sufficiency, reconstruction, provenance for daily net-liq (shipped path)."""

from __future__ import annotations

import json
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
from portfolio_analysis.jobs.connector_sync import sync_broker_to_gt
from portfolio_analysis.jobs.daily_net_liq import (
    fill_account_net_liq_gap,
    run_daily_net_liq,
)
from portfolio_analysis.jobs.market_days import is_us_market_day
from portfolio_analysis.jobs.net_liq_reconstruct import (
    PROVENANCE_GROUND_TRUTH,
    PROVENANCE_RECONSTRUCTED,
    reconstruct_net_liq_for_day,
    verify_reconstruct_vs_snapshot,
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


def _next_market_days(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if is_us_market_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def test_sufficiency_insufficient_with_single_gt_day(isolated_home: Path):
    """Only one GT equity day + min_days>1 → insufficient_history (not silent ok)."""
    mon = date(2026, 1, 5)
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="one",
                display_name="One",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="one",
                broker="synthetic",
                as_of_date=mon.isoformat(),
                liquidation_value=50_000.0,
                source="synthetic",
            )
        ],
    )
    conn = init_db()
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)
    conn.close()

    # Window includes mon and later market days with no GT → only mon filled
    end = mon + timedelta(days=14)
    r = run_daily_net_liq(
        broker="synthetic",
        account_key="one",
        min_days=5,
        start_date=mon.isoformat(),
        end_date=end.isoformat(),
        as_of_today=end,
        allow_reconstruct=False,
        adapters={},
        force=True,
    )
    assert r.reason == "insufficient_history"
    assert r.ok is False
    assert r.state == "failed"
    assert r.coverage.get("insufficient") is True
    assert r.coverage.get("min_days_requested") == 5
    assert r.accounts[0].available_market_days < 5
    assert r.accounts[0].series_len_in_window >= 1
    assert r.accounts[0].rows_written >= 1


def test_sufficiency_partial_mode(isolated_home: Path):
    mon = date(2026, 1, 5)
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="p1",
                display_name="P",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="p1",
                broker="synthetic",
                as_of_date=mon.isoformat(),
                liquidation_value=10_000.0,
                source="synthetic",
            )
        ],
    )
    conn = init_db()
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)
    conn.close()
    r = run_daily_net_liq(
        broker="synthetic",
        account_key="p1",
        min_days=10,
        as_of_today=mon + timedelta(days=14),
        allow_reconstruct=False,
        on_insufficient="partial",
        adapters={},
        force=True,
    )
    assert r.ok is True
    assert r.reason == "partial_coverage"
    assert r.coverage["insufficient"] is True


def test_multi_day_gt_meets_min_days(isolated_home: Path):
    days = _next_market_days(date(2026, 1, 5), 5)
    snaps = [
        EquitySnapshot(
            account_key="m5",
            broker="synthetic",
            as_of_date=d.isoformat(),
            liquidation_value=100_000.0 + i * 100,
            cash=1_000.0,
            source="synthetic",
        )
        for i, d in enumerate(days)
    ]
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="m5",
                display_name="M5",
                broker_account_ref="R",
            )
        ],
        snapshots=snaps,
    )
    conn = init_db()
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)
    conn.close()
    r = run_daily_net_liq(
        broker="synthetic",
        account_key="m5",
        min_days=5,
        as_of_today=days[-1],
        allow_reconstruct=False,
        adapters={},
        force=True,
    )
    assert r.ok is True
    assert r.reason == "completed"
    assert r.accounts[0].series_len_in_window >= 5
    assert r.coverage["min_series_len"] >= 5


def test_reconstruction_and_verify_against_gt(isolated_home: Path):
    """Positions reconstruct mid-week; GT anchors Mon/Fri match recon within tol."""
    days = _next_market_days(date(2026, 1, 5), 5)
    mon, tue, wed, thu, fri = days
    # GT equity only on Mon and Fri — equal to position book + cash
    cash = 500.0
    book = {d: 10_000.0 + i * 250 for i, d in enumerate(days)}
    acct = FundAccount(
        broker="synthetic",
        account_key="recon1",
        display_name="Recon",
        broker_account_ref="R",
    )
    snaps = [
        EquitySnapshot(
            account_key="recon1",
            broker="synthetic",
            as_of_date=mon.isoformat(),
            liquidation_value=book[mon] + cash,
            cash=cash,
            source="synthetic",
        ),
        EquitySnapshot(
            account_key="recon1",
            broker="synthetic",
            as_of_date=fri.isoformat(),
            liquidation_value=book[fri] + cash,
            cash=cash,
            source="synthetic",
        ),
    ]
    positions = []
    for d in days:
        positions.append(
            AccountPosition(
                broker="synthetic",
                account_key="recon1",
                as_of_date=d.isoformat(),
                symbol="AAA",
                quantity=100.0,
                market_value=book[d],
                price=book[d] / 100.0,
                source="synthetic",
            )
        )
    adapter = SyntheticBrokerAdapter(
        accounts=[acct], snapshots=snaps, positions=positions
    )
    conn = init_db()
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)

    # Unit: recon matches GT on overlap
    for d in (mon, fri):
        recon = reconstruct_net_liq_for_day(conn, "synthetic", "recon1", d.isoformat())
        assert recon is not None
        gt_lv = book[d] + cash
        ok, diff = verify_reconstruct_vs_snapshot(recon.net_liquidation_value, gt_lv)
        assert ok, diff

    r = fill_account_net_liq_gap(
        conn,
        "synthetic",
        "recon1",
        start_date=mon,
        end_date=fri,
        allow_reconstruct=True,
        as_of_today=fri,
    )
    assert r.rows_written >= 5
    assert r.rows_reconstructed >= 3  # tue/wed/thu
    assert r.rows_ground_truth >= 2
    assert r.verify_ok is True
    assert not r.verify_mismatches

    rows = conn.execute(
        """
        SELECT as_of_date, provenance, net_liquidation_value
        FROM daily_account_net_liq
        WHERE account_key='recon1' ORDER BY as_of_date
        """
    ).fetchall()
    by_d = {r[0]: (r[1], r[2]) for r in rows}
    assert by_d[mon.isoformat()][0] == PROVENANCE_GROUND_TRUTH
    assert by_d[fri.isoformat()][0] == PROVENANCE_GROUND_TRUTH
    assert by_d[tue.isoformat()][0] == PROVENANCE_RECONSTRUCTED
    assert by_d[wed.isoformat()][0] == PROVENANCE_RECONSTRUCTED
    # mid-week recon uses position book (+0 cash without same-day snap)
    assert by_d[tue.isoformat()][1] == book[tue]
    conn.close()


def test_never_stamp_live_onto_past(isolated_home: Path):
    mon = date(2026, 1, 5)
    fri = mon + timedelta(days=4)
    while not is_us_market_day(fri):
        fri += timedelta(days=1)
    adapter = SyntheticBrokerAdapter(
        accounts=[
            FundAccount(
                broker="synthetic",
                account_key="stamp",
                display_name="S",
                broker_account_ref="R",
            )
        ],
        snapshots=[
            EquitySnapshot(
                account_key="stamp",
                broker="synthetic",
                as_of_date=mon.isoformat(),
                liquidation_value=1_000.0,
                source="synthetic",
            )
        ],
    )
    conn = init_db()
    sync_broker_to_gt(conn, "synthetic", adapter=adapter)
    live = {fri.isoformat(): 999_999.0}
    fill_account_net_liq_gap(
        conn,
        "synthetic",
        "stamp",
        start_date=mon,
        end_date=fri,
        live_snapshots=live,
        allow_reconstruct=False,
        as_of_today=fri,
    )
    # Past days without GT must not get live stamped
    for d in iter_days(mon, fri):
        if d == fri or d == mon:
            continue
        if not is_us_market_day(d):
            continue
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_account_net_liq WHERE as_of_date=?",
            (d.isoformat(),),
        ).fetchone()[0]
        assert n == 0
    # Friday has live exact
    row = conn.execute(
        "SELECT net_liquidation_value, provenance FROM daily_account_net_liq WHERE as_of_date=?",
        (fri.isoformat(),),
    ).fetchone()
    assert row[0] == 999_999.0
    assert row[1] == "live_exact"
    conn.close()


def iter_days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def test_default_path_upgrades_reconstructed_when_gt_arrives(isolated_home: Path):
    """Default job path (no min_days/start_date): recon then later GT upgrades row.

    Skeptic repro: mon GT + tue–fri recon; insert tue GT; run_daily_net_liq
    force=True without window → tue becomes ground_truth with GT value.
    """
    days = _next_market_days(date(2026, 1, 5), 5)
    mon, tue, wed, thu, fri = days
    cash = 0.0
    book = {d: 10_000.0 + i * 100 for i, d in enumerate(days)}
    acct = FundAccount(
        broker="synthetic",
        account_key="upg1",
        display_name="Upgrade",
        broker_account_ref="R",
    )
    # Pass 1: only Mon has GT equity; positions all week for recon
    snaps_p1 = [
        EquitySnapshot(
            account_key="upg1",
            broker="synthetic",
            as_of_date=mon.isoformat(),
            liquidation_value=book[mon] + cash,
            cash=cash,
            source="synthetic",
        )
    ]
    positions = [
        AccountPosition(
            broker="synthetic",
            account_key="upg1",
            as_of_date=d.isoformat(),
            symbol="AAA",
            quantity=100.0,
            market_value=book[d],
            price=book[d] / 100.0,
            source="synthetic",
        )
        for d in days
    ]
    conn = init_db()
    sync_broker_to_gt(
        conn,
        "synthetic",
        adapter=SyntheticBrokerAdapter(
            accounts=[acct], snapshots=snaps_p1, positions=positions
        ),
    )
    # Default-style fill with reconstruct (as job default) through fri
    r1 = run_daily_net_liq(
        broker="synthetic",
        account_key="upg1",
        as_of_today=fri,
        allow_reconstruct=True,
        adapters={},
        force=True,
        # no min_days/start_date → legacy path with force reprocess
    )
    assert r1.ok or r1.reason in (
        "completed",
        "partial_coverage",
        "insufficient_history",
    )
    row_tue = conn.execute(
        """
        SELECT net_liquidation_value, provenance FROM daily_account_net_liq
        WHERE account_key='upg1' AND as_of_date=?
        """,
        (tue.isoformat(),),
    ).fetchone()
    assert row_tue is not None
    assert row_tue[1] == PROVENANCE_RECONSTRUCTED
    assert row_tue[0] == book[tue]

    # Pass 2: broker GT snapshot arrives for Tuesday (different value)
    gt_tue = 99_999.0
    conn.execute(
        """
        INSERT INTO gt_fund_equity_snapshots
        (broker, account_key, as_of_date, liquidation_value, cash, source, data_quality)
        VALUES ('synthetic', 'upg1', ?, ?, 0, 'broker_api', 100)
        ON CONFLICT(broker, account_key, as_of_date, source) DO UPDATE SET
          liquidation_value = excluded.liquidation_value
        """,
        (tue.isoformat(), gt_tue),
    )
    conn.commit()
    conn.close()

    # Default job path again — no window params; must upgrade tue
    r2 = run_daily_net_liq(
        broker="synthetic",
        account_key="upg1",
        as_of_today=fri,
        allow_reconstruct=True,
        adapters={},
        force=True,
    )
    assert r2.accounts[0].rows_written >= 1
    conn2 = init_db()
    try:
        row2 = conn2.execute(
            """
            SELECT net_liquidation_value, provenance, source
            FROM daily_account_net_liq
            WHERE account_key='upg1' AND as_of_date=?
            """,
            (tue.isoformat(),),
        ).fetchone()
        assert row2 is not None
        assert row2[0] == gt_tue
        assert row2[1] == PROVENANCE_GROUND_TRUTH
        # Multi-source verify should have run (recon book vs new GT may mismatch)
        # provenance must still be GT after upgrade
        assert "recon" not in (row2[2] or "")
    finally:
        conn2.close()


def test_pre_sync_demo_pipeline(isolated_home: Path):
    # Demo synthetic history is early 2025 — pin window to that range
    r = run_daily_net_liq(
        pre_sync=True,
        demo=True,
        min_days=5,
        start_date="2025-01-02",
        end_date="2025-02-10",
        as_of_today=date(2025, 2, 10),
        allow_reconstruct=False,
        force=True,
        adapters={},  # no live auto-load; demo seeds GT via pre_sync
    )
    assert r.pre_sync is True
    assert r.pre_sync_result is not None
    assert r.pre_sync_result.get("ok") is True
    assert r.ok is True
    assert r.reason == "completed"
    assert r.coverage.get("min_series_len", 0) >= 5
    assert "coverage" in r.to_public_dict()


def test_cli_and_mcp_window_params(isolated_home: Path, capsys, monkeypatch):
    import sys

    from portfolio_analysis import mcp_server
    from portfolio_analysis.cli import main

    # Seed via demo sync
    monkeypatch.setattr(sys, "argv", ["portfolio", "sync", "--demo", "--force"])
    main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portfolio",
            "jobs",
            "run",
            "daily_net_liq",
            "--min-days",
            "3",
            "--force",
            "--demo",
            "--on-insufficient",
            "partial",
        ],
    )
    try:
        main()
    except SystemExit as exc:
        # partial_coverage may still exit non-zero depending on CLI mapping
        assert exc.code in (0, 1, None)
    out = json.loads(capsys.readouterr().out)
    # result nested when via start_job
    payload = out.get("result") or out
    assert "coverage" in payload or out.get("job_id") == "daily_net_liq"
    # MCP tool with min_days
    body = mcp_server.jobs_run_tool(
        job_id="daily_net_liq",
        background=False,
        force=True,
        demo=True,
        min_days=3,
        allow_reconstruct=True,
    )
    data = json.loads(body)
    res = data.get("result") or data
    assert res.get("coverage") is not None or data.get("ok") is not None
    assert "client_secret" not in body
