"""Unit tests for private fund-as-symbol (TWRR index + MAs + alerts)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from portfolio_analysis.brokers.base import EquitySnapshot, FundAccount
from portfolio_analysis.brokers.synthetic import SyntheticBrokerAdapter
from portfolio_analysis.cli import main
from portfolio_analysis.db import init_db
from portfolio_analysis.fund.alerts import evaluate_fund_alerts
from portfolio_analysis.fund.series import (
    InsufficientFundHistory,
    load_fund_index_series,
    rebuild_fund_daily,
    store_adapter_ground_truth,
    _build_index_rows,
)
from portfolio_analysis.fund.symbols import fund_symbol, parse_fund_symbol
from portfolio_analysis.fund.technicals import compute_fund_moving_averages


def test_fund_symbol_roundtrip():
    s = fund_symbol("Schwab", "AbC123")
    assert s == "FUND:schwab:abc123"
    p = parse_fund_symbol(s)
    assert p.broker == "schwab"
    assert p.account_key == "abc123"
    assert not p.is_combined


def test_parse_fund_all():
    p = parse_fund_symbol("FUND:ALL")
    assert p.is_combined


def test_build_index_deposit_does_not_look_like_rally():
    """+10k deposit with flat underlying value must not produce a huge positive return."""
    snaps = [
        {
            "as_of_date": "2026-01-01",
            "liquidation_value": 100_000.0,
            "data_quality": 100,
        },
        {
            "as_of_date": "2026-01-02",
            "liquidation_value": 110_000.0,
            "data_quality": 100,
        },
    ]
    # Deposit 10k on day 2; end value only up by the deposit → r ≈ 0
    cf = {"2026-01-02": 10_000.0}
    rows = _build_index_rows(snaps, cf, base_index=100.0)
    assert rows[0]["twrr_index"] == pytest.approx(100.0)
    assert rows[1]["daily_return"] == pytest.approx(0.0, abs=1e-12)
    assert rows[1]["twrr_index"] == pytest.approx(100.0)


def test_build_index_withdrawal_does_not_look_like_crash():
    """Withdrawal that fully explains a drop must not produce a large negative return."""
    snaps = [
        {
            "as_of_date": "2026-01-01",
            "liquidation_value": 100_000.0,
            "data_quality": 100,
        },
        {
            "as_of_date": "2026-01-02",
            "liquidation_value": 90_000.0,
            "data_quality": 100,
        },
    ]
    cf = {"2026-01-02": -10_000.0}
    rows = _build_index_rows(snaps, cf, base_index=100.0)
    assert rows[1]["daily_return"] == pytest.approx(0.0, abs=1e-12)
    assert rows[1]["twrr_index"] == pytest.approx(100.0)


def test_build_index_manager_skill_positive():
    snaps = [
        {"as_of_date": "2026-01-01", "liquidation_value": 100.0, "data_quality": 100},
        {"as_of_date": "2026-01-02", "liquidation_value": 110.0, "data_quality": 100},
    ]
    rows = _build_index_rows(snaps, {}, base_index=100.0)
    assert rows[1]["daily_return"] == pytest.approx(0.1)
    assert rows[1]["twrr_index"] == pytest.approx(110.0)


def test_build_index_skill_after_deposit():
    """Skill after an external deposit compounds only on post-flow capital."""
    snaps = [
        {
            "as_of_date": "2026-01-01",
            "liquidation_value": 100_000.0,
            "data_quality": 100,
        },
        # deposit 10k SOD; +1% skill on 110k → end 111_100
        {
            "as_of_date": "2026-01-02",
            "liquidation_value": 111_100.0,
            "data_quality": 100,
        },
    ]
    rows = _build_index_rows(snaps, {"2026-01-02": 10_000.0}, base_index=100.0)
    assert rows[1]["daily_return"] == pytest.approx(0.01)
    assert rows[1]["twrr_index"] == pytest.approx(101.0)


def test_synthetic_adapter_to_db_rebuild_and_alerts(tmp_path: Path):
    db_path = tmp_path / "fund.db"
    conn = init_db(db_path)

    acct = FundAccount(broker="synthetic", account_key="t1", display_name="Test")
    # 60 days of gentle uptrend so SMA50 exists; SMA200 still unavailable
    snaps = []
    v = 100_000.0
    for i in range(60):
        d = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        v *= 1.002  # +0.2%/day skill
        snaps.append(
            EquitySnapshot(
                account_key="t1",
                broker="synthetic",
                as_of_date=d,
                liquidation_value=v,
                source="synthetic",
            )
        )
    adapter = SyntheticBrokerAdapter(accounts=[acct], snapshots=snaps, cash_flows=[])
    store_adapter_ground_truth(conn, adapter)
    n = rebuild_fund_daily(conn, broker="synthetic", account_key="t1")
    assert n == 60

    sym = fund_symbol("synthetic", "t1")
    series = load_fund_index_series(conn, sym)
    assert len(series) == 60

    mas = compute_fund_moving_averages(series, fund_symbol=sym)
    assert mas.ema_21 is not None
    assert mas.sma_50 is not None
    assert mas.sma_200 is None  # only 60 points
    assert mas.bullish_stack is None

    alerts = evaluate_fund_alerts(series, fund_symbol=sym)
    rules = {a.rule for a in alerts}
    assert "below_ema_21" in rules
    assert "below_sma_200_unavailable" in rules or "below_sma_200" in rules
    # uptrend → typically not below EMA
    below_21 = next(a for a in alerts if a.rule == "below_ema_21")
    assert below_21.fired is False


def test_downtrend_fires_below_ema21():
    """Downtrend series must fire below_ema_21 via the shipped alert evaluator."""
    series = []
    px = 100.0
    for i in range(40):
        # Steady decline so last price sits under EMA21
        px *= 0.99
        series.append(
            {
                "as_of_date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                "twrr_index": px,
            }
        )
    alerts = evaluate_fund_alerts(series, fund_symbol="FUND:synthetic:down")
    below_21 = next(a for a in alerts if a.rule == "below_ema_21")
    assert below_21.fired is True
    assert below_21.as_of_date == series[-1]["as_of_date"]


def test_insufficient_history_for_mas():
    series = [
        {"as_of_date": "2026-01-01", "twrr_index": 100.0},
    ]
    with pytest.raises(InsufficientFundHistory):
        compute_fund_moving_averages(series, fund_symbol="FUND:x:y", min_points=2)


def test_insufficient_history_alert_path():
    alerts = evaluate_fund_alerts([], fund_symbol="FUND:x:empty")
    assert len(alerts) == 1
    assert alerts[0].rule == "insufficient_history"
    assert alerts[0].fired is True


def _run_cli(args: list[str], capsys) -> tuple[str, int]:
    old_argv = sys.argv
    sys.argv = ["portfolio"] + args
    try:
        main()
        code = 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = old_argv
    captured = capsys.readouterr()
    return captured.out + captured.err, code


def test_cli_fund_rebuild_series_mas_alerts(tmp_path: Path, capsys, monkeypatch):
    """Real CLI entry: fund rebuild --demo, then series / mas / alerts on temp DB."""
    db_path = tmp_path / "fund_cli.db"
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_DB_PATH", str(db_path))

    out1, code1 = _run_cli(
        [
            "fund",
            "rebuild",
            "--demo",
            "--broker",
            "synthetic",
            "--account-key",
            "demo01",
        ],
        capsys,
    )
    assert code1 == 0, out1
    assert "Rebuilt" in out1
    assert "fund_daily rows" in out1
    # demo adapter builds 10 days
    assert "10" in out1

    sym = "FUND:synthetic:demo01"
    out2, code2 = _run_cli(["fund", "series", "--symbol", sym], capsys)
    assert code2 == 0, out2
    assert "twrr_index" in out2
    assert "2026-01-01" in out2
    assert "2026-01-10" in out2

    out3, code3 = _run_cli(["fund", "mas", "--symbol", sym], capsys)
    assert code3 == 0, out3
    assert "ema_21" in out3
    assert "sma_50" in out3
    assert "fund_symbol" in out3

    out4, code4 = _run_cli(["fund", "alerts", "--symbol", sym], capsys)
    assert code4 == 0, out4
    assert "Evaluated" in out4
    assert "below_ema_21" in out4 or "insufficient_history" in out4

    # Second rebuild is deterministic (idempotent)
    out5, code5 = _run_cli(
        [
            "fund",
            "rebuild",
            "--demo",
            "--broker",
            "synthetic",
            "--account-key",
            "demo01",
        ],
        capsys,
    )
    assert code5 == 0, out5
    assert "Rebuilt 10" in out5


def test_cli_fund_series_missing_symbol(tmp_path: Path, capsys, monkeypatch):
    db_path = tmp_path / "empty_fund.db"
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_DB_PATH", str(db_path))
    # ensure schema exists
    init_db(db_path)
    out, code = _run_cli(
        ["fund", "series", "--symbol", "FUND:synthetic:missing"], capsys
    )
    assert code == 1
    assert "No fund_daily rows" in out
