"""Uniform account import + fund TA charts (hermetic)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


from portfolio_analysis.brokers.base import (
    AccountPosition,
    CashFlow,
    EquitySnapshot,
    FundAccount,
)
from portfolio_analysis.brokers.sources.schwab_mcp import parse_schwab_accounts_payload
from portfolio_analysis.brokers.synthetic import SyntheticBrokerAdapter
from portfolio_analysis.db import init_db
from portfolio_analysis.fund.charts import generate_fund_ta_chart
from portfolio_analysis.fund.series import (
    import_broker_to_gt,
    load_account_positions,
    load_fund_index_series,
)
from portfolio_analysis.fund.symbols import fund_symbol
from portfolio_analysis.fund.technicals import (
    compute_fund_moving_averages,
    compute_ma_series,
)


def _long_adapter(n_days: int = 220) -> SyntheticBrokerAdapter:
    acct = FundAccount(
        broker="synthetic",
        account_key="chart01",
        display_name="Chart Demo",
        broker_account_ref="REF-CHART01",
    )
    start = date(2025, 1, 2)
    snaps = []
    flows = []
    prev = 100_000.0
    deposit_i = 50
    for i in range(n_days):
        d = start + timedelta(days=i)
        cf = 5_000.0 if i == deposit_i else 0.0
        if i == deposit_i:
            flows.append(
                CashFlow(
                    account_key="chart01",
                    broker="synthetic",
                    flow_date=d.isoformat(),
                    amount=cf,
                    flow_type="deposit",
                    source="synthetic",
                )
            )
        v = (prev + cf) * 1.001
        snaps.append(
            EquitySnapshot(
                account_key="chart01",
                broker="synthetic",
                as_of_date=d.isoformat(),
                liquidation_value=round(v, 2),
                source="synthetic",
            )
        )
        prev = v
    last = snaps[-1].as_of_date
    positions = [
        AccountPosition(
            broker="synthetic",
            account_key="chart01",
            as_of_date=last,
            symbol="AAA",
            quantity=10,
            market_value=1000.0,
            price=100.0,
            source="synthetic",
        )
    ]
    return SyntheticBrokerAdapter(
        accounts=[acct], snapshots=snaps, cash_flows=flows, positions=positions
    )


def test_import_uniform_positions_and_fund_daily(tmp_path: Path):
    conn = init_db(tmp_path / "t.db")
    adapter = _long_adapter(60)
    result = import_broker_to_gt(conn, adapter)
    assert result["accounts"] == 1
    assert result["snapshots"] == 60
    assert result["positions"] == 1
    assert result["rebuilt"][0]["fund_daily_rows"] == 60
    sym = fund_symbol("synthetic", "chart01")
    series = load_fund_index_series(conn, sym)
    assert len(series) == 60
    assert "liquidation_value" in series[0] and "twrr_index" in series[0]
    # Deposit day must not create a wild return
    deposit_row = next(r for r in series if float(r["external_cf"] or 0) != 0)
    assert abs(float(deposit_row["daily_return"])) < 0.05
    pos = load_account_positions(conn, broker="synthetic", account_key="chart01")
    assert len(pos) == 1
    assert pos[0]["symbol"] == "AAA"


def test_parse_schwab_payload_with_positions():
    payload = [
        {
            "securitiesAccount": {
                "type": "MARGIN",
                "accountHash": "ABC123HASH",
                "nickname": "IRA",
                "currentBalances": {
                    "liquidationValue": 250000.0,
                    "cashBalance": 1000.0,
                },
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": 10,
                        "marketValue": 2000.0,
                        "averagePrice": 200.0,
                    },
                    {
                        "symbol": "MSFT",
                        "quantity": 5,
                        "marketValue": 1500.0,
                        "averagePrice": 300.0,
                    },
                ],
            }
        }
    ]
    rows = parse_schwab_accounts_payload(payload, source_label="fixture")
    assert len(rows) == 1
    assert rows[0].liquidation_value == 250000.0
    assert len(rows[0].positions) == 2
    assert {p.symbol for p in rows[0].positions} == {"AAPL", "MSFT"}


def test_ma_on_net_liq_and_insufficient_history(tmp_path: Path):
    conn = init_db(tmp_path / "t.db")
    import_broker_to_gt(conn, _long_adapter(30))
    series = load_fund_index_series(conn, fund_symbol("synthetic", "chart01"))
    mas = compute_fund_moving_averages(
        series, fund_symbol="FUND:synthetic:chart01", price_field="liquidation_value"
    )
    assert mas.price_field == "liquidation_value"
    assert mas.ema_21 is not None  # 30 > 21
    assert mas.sma_50 is None  # 30 < 50
    assert mas.sma_200 is None


def test_generate_fund_ta_charts_nonempty(tmp_path: Path):
    adapter = _long_adapter(220)
    conn = init_db(tmp_path / "t.db")
    import_broker_to_gt(conn, adapter)
    series = load_fund_index_series(conn, fund_symbol("synthetic", "chart01"))
    assert len(series) >= 200
    out1 = tmp_path / "netliq.png"
    out2 = tmp_path / "twrr.png"
    p1 = generate_fund_ta_chart(
        series,
        fund_symbol="FUND:synthetic:chart01",
        price_field="liquidation_value",
        output_path=out1,
    )
    p2 = generate_fund_ta_chart(
        series,
        fund_symbol="FUND:synthetic:chart01",
        price_field="twrr_index",
        output_path=out2,
    )
    assert p1.is_file() and p1.stat().st_size > 1000
    assert p2.is_file() and p2.stat().st_size > 1000
    ma = compute_ma_series(
        series, fund_symbol="FUND:synthetic:chart01", price_field="liquidation_value"
    )
    assert ma.sma_200[-1] is not None
    assert ma.ema_21[-1] is not None


def test_cli_fund_import_demo_and_chart(tmp_path: Path, monkeypatch):
    import sys
    from portfolio_analysis.cli import main

    monkeypatch.setenv("PORTFOLIO_ANALYSIS_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["portfolio", "fund", "import", "--demo"],
    )
    main()
    chart_path = tmp_path / "reports" / "out.png"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portfolio",
            "fund",
            "chart",
            "--symbol",
            "FUND:synthetic:demo01",
            "--price-field",
            "liquidation_value",
            "--output",
            str(chart_path),
        ],
    )
    main()
    assert chart_path.is_file() and chart_path.stat().st_size > 1000


def test_parse_concatenated_json_accounts():
    """schwab-mcp may return multiple account objects as concatenated JSON text."""
    from portfolio_analysis.brokers.sources.mcp_transport import _parse_jsonish
    from portfolio_analysis.brokers.sources.schwab_mcp import (
        parse_schwab_accounts_payload,
    )

    blob = (
        '{"securitiesAccount":{"accountHash":"H1","nickname":"A",'
        '"currentBalances":{"liquidationValue":100.0},"positions":[]}}\n'
        '{"securitiesAccount":{"accountHash":"H2","nickname":"B",'
        '"currentBalances":{"liquidationValue":200.0},"positions":'
        '[{"symbol":"AAA","quantity":1,"marketValue":10.0}]}}'
    )
    parsed = _parse_jsonish(blob)
    assert isinstance(parsed, list) and len(parsed) == 2
    rows = parse_schwab_accounts_payload(parsed)
    assert len(rows) == 2
    assert rows[0].liquidation_value == 100.0
    assert rows[1].positions[0].symbol == "AAA"
