"""Command line interface for portfolio-analysis."""

import argparse
import sys
from pathlib import Path

from .db import init_db
from .reporting import (
    generate_report,
    print_report_summary,
    get_reports_dir,
    default_report_path,
)
from .charts import generate_position_size_distribution_chart
from .pdf_report import create_portfolio_pdf_report

# NOTE: ingest_daily_positions / classify_transactions_to_cash_flows were moved during
# recent refactor (now primarily in tools/ and daily_positions.py). Lazy placeholders
# so that `portfolio twrr` and `portfolio report` continue to work.
ingest_daily_positions = None
classify_transactions_to_cash_flows = None

from .twrr import InsufficientDailyTwrrData  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Portfolio Analysis - Weed the Garden")
    subparsers = parser.add_subparsers(dest="command")

    # Report command
    report = subparsers.add_parser("report", help="Generate Weed the Garden report")
    report.add_argument(
        "--period",
        default="all-time",
        choices=[
            "ytd",
            "previous-year",
            "last-3-months",
            "last-6-months",
            "last-12-months",
            "all-time",
        ],
        help="Time period to analyze (default: all-time)",
    )
    report.add_argument("--symbol", help="Filter to a specific symbol")
    report.add_argument("--year", type=str, help="Specific year (e.g. 2026)")
    report.add_argument(
        "--format", choices=["text", "pdf"], default="text", help="Output format"
    )

    # Chart command
    chart = subparsers.add_parser("chart", help="Generate portfolio charts")
    chart_sub = chart.add_subparsers(dest="chart_type")

    dist = chart_sub.add_parser("distribution", help="Position size distribution chart")
    dist.add_argument(
        "--positions", type=Path, required=True, help="Path to Schwab Positions CSV"
    )
    dist.add_argument(
        "--output",
        type=Path,
        default=get_reports_dir() / "portfolio_distribution_dual.png",
    )

    # TWRR + OHLC + Position Size (uses anchored daily qty recon for bottom panel)
    ts = chart_sub.add_parser(
        "twrr-ohlc-position",
        help="TWRR / OHLC price / Position size step chart for a symbol (bottom uses clean anchored recon, not daily_position_values)",
    )
    ts.add_argument("--symbol", required=True, help="Symbol e.g. AAPL")
    ts.add_argument("--start-date", help="YYYY-MM-DD")
    ts.add_argument("--end-date", help="YYYY-MM-DD")
    ts.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PNG path (default under reports dir)",
    )

    # PDF Report command
    pdf = subparsers.add_parser(
        "pdf-report", help="Generate professional PDF portfolio report"
    )
    pdf.add_argument(
        "--positions", type=Path, required=True, help="Path to Schwab Positions CSV"
    )
    pdf.add_argument(
        "--output",
        type=Path,
        default=default_report_path(prefix="Portfolio_Analysis_Report", suffix=".pdf"),
    )

    # NEW in PR #1: Capital Efficiency / TWRR daily position ingest
    ip = subparsers.add_parser(
        "ingest-positions",
        help="Ingest daily/periodic Schwab Positions CSV for Daily TWRR Capital Efficiency (additive, does not affect existing reports)",
    )
    ip.add_argument(
        "--positions",
        type=Path,
        required=True,
        help="Path to Schwab Positions CSV export",
    )
    ip.add_argument(
        "--as-of", required=True, help="Valuation date in YYYY-MM-DD format"
    )
    ip.add_argument(
        "--classify-flows",
        action="store_true",
        help="Also run automatic classification of existing transactions into position_cash_flows",
    )

    # Early preview of the new Capital Efficiency TWRR table (PR #2+)
    twrr = subparsers.add_parser(
        "twrr",
        help="Preview Capital Efficiency table with 30d/60d/90d/YTD TWRR (uses current data + backfill)",
    )
    twrr.add_argument(
        "--all", action="store_true", help="Include symbols with no current position"
    )
    twrr.add_argument(
        "--symbols",
        nargs="+",
        help="Limit to specific symbols (e.g. --symbols AAPL NVDA TSLA or --symbols AAPL,NVDA)",
    )
    twrr.add_argument(
        "--detailed",
        "-d",
        action="store_true",
        help="Show full sub-period breakdown (recommended when using --symbols)",
    )
    twrr.add_argument(
        "--separate-options",
        action="store_true",
        help="Show equities and options in separate sections (options treated as independent assets)",
    )

    # Consolidated YTD TWRR + Broker P/L % table (new workflow, top TWRR first)
    ytdpl = subparsers.add_parser(  # noqa: F841 (pre-existing; variable for future extension)
        "ytd-pl",
        help="YTD TWRR + Broker P/L percent table for all current equity positions (sorted by top TWRR performers first)",
    )

    # Daily position quantity reconstruction for charting (anchored, handles journals, full daily series)
    dpos = subparsers.add_parser(
        "daily-positions",
        help="Reconstruct daily position quantities (anchored to gt_daily_positions, skips Journals, full series for charts)",
    )
    dpos.add_argument(
        "--symbol", required=True, help="Symbol to reconstruct (e.g. AAPL)"
    )
    dpos.add_argument("--start-date", help="Start date YYYY-MM-DD (default from data)")
    dpos.add_argument("--end-date", help="End date YYYY-MM-DD (default to latest)")
    dpos.add_argument(
        "--full-daily",
        action="store_true",
        default=True,
        help="Produce row for every calendar day (ffill qty)",
    )

    # Private fund-as-symbol (account-level TWRR index + MA alerts)
    fund = subparsers.add_parser(
        "fund",
        help="Private fund-as-symbol tools (account TWRR index, MAs, alerts)",
    )
    fund_sub = fund.add_subparsers(dest="fund_command")

    fund_rebuild = fund_sub.add_parser(
        "rebuild",
        help="Load synthetic demo data (or use DB) and rebuild fund_daily TWRR index",
    )
    fund_rebuild.add_argument(
        "--demo",
        action="store_true",
        help="Seed synthetic broker data into the DB (safe for CI / dry runs)",
    )
    fund_rebuild.add_argument("--broker", default="synthetic")
    fund_rebuild.add_argument("--account-key", default="demo01")

    fund_import = fund_sub.add_parser(
        "import",
        help="Import accounts/positions/equity from a broker adapter into uniform GT",
    )
    fund_import.add_argument(
        "--broker",
        default="schwab",
        help="Broker id (schwab|synthetic|…). schwab uses connector live source",
    )
    fund_import.add_argument(
        "--account-key",
        default=None,
        help="Optional account_key filter",
    )
    fund_import.add_argument(
        "--demo",
        action="store_true",
        help="Use long synthetic history (safe offline pressure path)",
    )
    fund_import.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Store GT only; skip fund_daily rebuild",
    )

    fund_series = fund_sub.add_parser(
        "series", help="Print fund_daily series (net liq + TWRR index)"
    )
    fund_series.add_argument(
        "--symbol",
        required=True,
        help="Fund symbol e.g. FUND:synthetic:demo01",
    )

    fund_mas = fund_sub.add_parser("mas", help="EMA21 / SMA50 / SMA200 on fund series")
    fund_mas.add_argument("--symbol", required=True)
    fund_mas.add_argument(
        "--price-field",
        default="twrr_index",
        choices=["twrr_index", "liquidation_value"],
        help="Series to average (default cash-flow-neutral TWRR index)",
    )

    fund_alerts = fund_sub.add_parser(
        "alerts", help="Evaluate under-MA and stack alerts for a fund symbol"
    )
    fund_alerts.add_argument("--symbol", required=True)

    fund_chart = fund_sub.add_parser(
        "chart",
        help="TA chart: net liq (or TWRR index) with 21 EMA / 50 DMA / 200 DMA",
    )
    fund_chart.add_argument("--symbol", required=True)
    fund_chart.add_argument(
        "--price-field",
        default="liquidation_value",
        choices=["liquidation_value", "twrr_index"],
        help="Primary series to plot (default net liquidation value)",
    )
    fund_chart.add_argument(
        "--output",
        default=None,
        help="PNG path (default: PORTFOLIO_ANALYSIS_HOME/reports/…)",
    )

    # Multi-broker adapter registry + export paths
    brokers = subparsers.add_parser(
        "brokers",
        help="List registered broker adapters and export paths (multi-broker)",
    )
    brokers_sub = brokers.add_subparsers(dest="brokers_command")
    brokers_sub.add_parser(
        "list",
        help="Show registered brokers, status, and per-broker export directories",
    )

    # Configurable connectors (local secrets + MCP/OAuth)
    conn = subparsers.add_parser(
        "connectors",
        help="Configure broker live sources (MCP URL / direct OAuth); secrets stay local",
    )
    conn_sub = conn.add_subparsers(dest="connectors_command")
    conn_sub.add_parser("list", help="List connectors (redacted)")
    conn_show = conn_sub.add_parser("show", help="Show one connector (redacted)")
    conn_show.add_argument("broker", nargs="?", default="schwab")
    conn_set = conn_sub.add_parser("set", help="Update connector config / secrets")
    conn_set.add_argument("broker", nargs="?", default="schwab")
    conn_set.add_argument(
        "--mode", choices=["auto", "mcp", "direct", "exports_only"], default=None
    )
    conn_set.add_argument("--mcp-url", default=None)
    conn_set.add_argument("--mcp-command", default=None)
    conn_set.add_argument("--mcp-tool-prefix", default=None)
    conn_set.add_argument("--redirect-uri", default=None)
    conn_set.add_argument("--exports-dir", default=None)
    conn_set.add_argument("--client-id", default=None)
    conn_set.add_argument("--client-secret", default=None)
    conn_set.add_argument(
        "--enabled",
        choices=["true", "false"],
        default=None,
        help="Enable or disable connector",
    )
    conn_test = conn_sub.add_parser("test", help="Probe live connector")
    conn_test.add_argument("broker", nargs="?", default="schwab")
    conn_oa = conn_sub.add_parser("oauth-start", help="Start OAuth PKCE (Schwab)")
    conn_oa.add_argument("broker", nargs="?", default="schwab")
    conn_oc = conn_sub.add_parser("oauth-complete", help="Finish OAuth with code")
    conn_oc.add_argument("broker", nargs="?", default="schwab")
    conn_oc.add_argument("--code", required=True)
    conn_oc.add_argument("--verifier", default=None)

    # Continuous connector → local GT sync (one-shot; no scheduler)
    sync_p = subparsers.add_parser(
        "sync",
        help=(
            "One-shot broker connector → local GT sync "
            "(sequential accounts; conflict-free lock)"
        ),
    )
    sync_sub = sync_p.add_subparsers(dest="sync_command")
    sync_run = sync_sub.add_parser(
        "run",
        help="Pull enabled connectors into local GT + rebuild fund series if changed",
    )
    for _sp in (sync_p, sync_run):
        _sp.add_argument(
            "--broker",
            action="append",
            dest="brokers",
            default=None,
            help="Broker id to sync (repeatable). Default: enabled live connectors",
        )
        _sp.add_argument(
            "--demo",
            action="store_true",
            help="Offline synthetic adapter (no credentials / network)",
        )
        _sp.add_argument(
            "--force",
            action="store_true",
            help="Ignore min-interval stale gate",
        )
        _sp.add_argument(
            "--min-interval-seconds",
            type=int,
            default=0,
            help="Skip if last success is newer than this many seconds (0=always try)",
        )
    sync_sub.add_parser(
        "status",
        help="Show last sync status (non-secret; includes lock + staleness)",
    )

    # Unified jobs (list / run / status) — one-shot CLI, no scheduler
    jobs_p = subparsers.add_parser(
        "jobs",
        help="List/run/status registered jobs (connector_sync, daily_net_liq, …)",
    )
    jobs_sub = jobs_p.add_subparsers(dest="jobs_command")
    jobs_sub.add_parser("list", help="List registered jobs and last status")
    jobs_run = jobs_sub.add_parser("run", help="Run a job once (foreground)")
    jobs_run.add_argument(
        "job_id",
        help="Job id: connector_sync | daily_net_liq",
    )
    jobs_run.add_argument("--demo", action="store_true", help="For connector_sync")
    jobs_run.add_argument("--force", action="store_true")
    jobs_run.add_argument("--broker", default=None, help="Limit to one broker")
    jobs_run.add_argument(
        "--background",
        action="store_true",
        help="Return run_id immediately (poll with jobs status --run-id)",
    )
    jobs_run.add_argument(
        "--min-interval-seconds",
        type=int,
        default=0,
        help="connector_sync stale gate",
    )
    jobs_st = jobs_sub.add_parser(
        "status", help="Job or run status (pollable; no secrets)"
    )
    jobs_st.add_argument("job_id", nargs="?", default=None)
    jobs_st.add_argument("--run-id", default=None, help="Specific run id")

    # Continuous service (scheduler + optional MCP)
    serve_p = subparsers.add_parser(
        "serve",
        help=(
            "Run continuous service: built-in scheduler + optional MCP "
            "(survives reboot when installed as a system unit)"
        ),
    )
    serve_p.add_argument("--mcp-http", action="store_true")
    serve_p.add_argument("--mcp-stdio", action="store_true")
    serve_p.add_argument("--host", default=None)
    serve_p.add_argument("--port", type=int, default=None)
    serve_p.add_argument("--timezone", default=None)
    serve_p.add_argument("--no-scheduler", action="store_true")
    serve_p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.command == "report":
        conn = init_db()
        from .db import ensure_real_data

        if not ensure_real_data(conn, require_daily_positions=False):
            print(
                "\n[INSUFFICIENT REAL DATA] Could not find enough verified Schwab data."
            )
            print("The system attempted to auto-discover files in common locations.")
            print(
                "Please ensure your Schwab exports (Positions, Realized Gains, Transactions) are available.\n"
            )
            return

        period = args.year if args.year else args.period
        report_data = generate_report(period=period, symbol=args.symbol, conn=conn)
        print_report_summary(report_data, period=period)

    elif args.command == "chart":
        if args.chart_type == "distribution":
            chart_path = generate_position_size_distribution_chart(
                positions_csv_path=args.positions, output_path=args.output
            )
            print(f"Chart saved to: {chart_path}")
        elif args.chart_type == "twrr-ohlc-position":
            from .charts import generate_twrr_ohlc_position_chart

            out = args.output
            chart_path = generate_twrr_ohlc_position_chart(
                symbol=args.symbol,
                output_path=out,
                start_date=getattr(args, "start_date", None),
                end_date=getattr(args, "end_date", None),
            )
            print(f"Chart saved to: {chart_path}")

    elif args.command == "pdf-report":
        pdf_path = create_portfolio_pdf_report(
            positions_csv_path=args.positions, output_path=args.output
        )
        print(f"PDF Report saved to: {pdf_path}")

    elif args.command == "ingest-positions":
        conn = init_db()
        count = ingest_daily_positions(
            conn=conn,
            csv_path=args.positions,
            as_of_date=args.as_of,
        )
        print(f"Ingested {count} daily position rows for {args.as_of}")

        if args.classify_flows:
            flow_count = classify_transactions_to_cash_flows(conn=conn)
            print(f"Classified {flow_count} transactions into position_cash_flows")

        print(
            "Note: Only real Schwab Positions data is used. No simulated data is created."
        )

    elif args.command == "twrr":
        conn = init_db()

        from .twrr import (
            get_capital_efficiency_twrr_report,
            print_twrr_capital_efficiency_table,
        )

        # Parse --symbols (support both space-separated and comma-separated)
        requested_symbols = None
        if getattr(args, "symbols", None):
            flat = []
            for item in args.symbols:
                flat.extend(item.split(","))
            requested_symbols = [s.strip().upper() for s in flat if s.strip()]

        if args.detailed and requested_symbols:
            # Detailed mode - reuse the exact same detailed breakdown function
            from .twrr import print_detailed_twrr_breakdown

            for sym in requested_symbols:
                print_detailed_twrr_breakdown(sym, conn=conn)
        else:
            try:
                report = get_capital_efficiency_twrr_report(
                    conn=conn,
                    only_active=not args.all,
                    symbols=requested_symbols,
                )
                print_twrr_capital_efficiency_table(
                    report, separate_options=getattr(args, "separate_options", False)
                )
            except InsufficientDailyTwrrData as e:
                print(f"\n[INSUFFICIENT DAILY DATA] {e}\n")
                sys.exit(1)

        # (Optional future: pull fresh real positions via Schwab API if credentials are configured)
        pass

    elif args.command == "ytd-pl":
        conn = init_db()
        from .reporting import get_ytd_twrr_pl_table, print_ytd_twrr_pl_table

        # Auto-ensure some data freshness for TWRR (reuses existing logic)
        try:
            from .db import ensure_real_data

            ensure_real_data(conn, require_daily_positions=True)
        except Exception:
            pass

        try:
            data = get_ytd_twrr_pl_table(conn=conn)
            print_ytd_twrr_pl_table(data)
        except Exception as e:
            print(f"\n[ERROR generating ytd-pl table] {e}\n")
            # Fallback suggestion
            print(
                "If numbers look off, run: python tools/build_reconciled_daily_positions.py --start-date 2026-01-01 --loop --max-iterations 2"
            )

    elif args.command == "daily-positions":
        conn = init_db()
        from .daily_positions import reconstruct_daily_position_quantities

        df = reconstruct_daily_position_quantities(
            conn,
            args.symbol,
            args.start_date,
            args.end_date,
        )
        if df.empty:
            print(f"No data for {args.symbol}")
        else:
            print(df.to_string(index=False))
            print(f"\nFinal qty on last date: {df.iloc[-1]['quantity']}")

    elif args.command == "fund":
        _run_fund_command(args)

    elif args.command == "brokers":
        _run_brokers_command(args)

    elif args.command == "connectors":
        _run_connectors_command(args)

    elif args.command == "sync":
        _run_sync_command(args)

    elif args.command == "jobs":
        _run_jobs_command(args)

    elif args.command == "serve":
        import os

        from .service import run_service

        sys.exit(
            run_service(
                mcp_http=bool(args.mcp_http),
                mcp_stdio=bool(args.mcp_stdio),
                host=args.host or os.environ.get("MCP_HOST", "0.0.0.0"),
                port=int(
                    args.port
                    if args.port is not None
                    else os.environ.get("MCP_PORT", "3460")
                ),
                timezone=args.timezone
                or os.environ.get("PORTFOLIO_ANALYSIS_TZ", "America/Chicago"),
                enable_scheduler=not args.no_scheduler,
            )
        )

    else:
        parser.print_help()


def _run_sync_command(args) -> None:
    """Handle ``portfolio sync`` / ``portfolio sync run|status``."""
    import json

    from portfolio_analysis.sync import (
        format_sync_result_json,
        load_sync_status,
        run_sync,
    )

    cmd = getattr(args, "sync_command", None)
    if cmd == "status":
        print(json.dumps(load_sync_status(), indent=2))
        return

    result = run_sync(
        brokers=getattr(args, "brokers", None),
        demo=bool(getattr(args, "demo", False)),
        force=bool(getattr(args, "force", False)),
        min_interval_seconds=int(getattr(args, "min_interval_seconds", 0) or 0),
    )
    print(format_sync_result_json(result))
    if not result.ok and not result.skipped:
        sys.exit(1)


def _run_jobs_command(args) -> None:
    """Handle ``portfolio jobs list|run|status``."""
    import json

    from portfolio_analysis.jobs.registry import list_jobs
    from portfolio_analysis.jobs.runner import (
        get_run_status,
        list_job_statuses,
        start_job,
    )

    cmd = getattr(args, "jobs_command", None)
    if cmd is None or cmd == "list":
        print(
            json.dumps(
                {"jobs": list_jobs(), "status": list_job_statuses()},
                indent=2,
            )
        )
        return
    if cmd == "status":
        print(
            json.dumps(
                get_run_status(
                    run_id=getattr(args, "run_id", None),
                    job_id=getattr(args, "job_id", None),
                ),
                indent=2,
            )
        )
        return
    if cmd == "run":
        job_id = args.job_id
        kwargs: dict = {"force": bool(getattr(args, "force", False))}
        if job_id == "connector_sync":
            kwargs["demo"] = bool(getattr(args, "demo", False))
            kwargs["min_interval_seconds"] = int(
                getattr(args, "min_interval_seconds", 0) or 0
            )
            if getattr(args, "broker", None):
                kwargs["brokers"] = [args.broker]
        elif job_id == "daily_net_liq":
            if getattr(args, "broker", None):
                kwargs["broker"] = args.broker
        out = start_job(
            job_id,
            background=bool(getattr(args, "background", False)),
            trigger="cli",
            **kwargs,
        )
        print(json.dumps(out, indent=2))
        if out.get("state") == "failed" or out.get("ok") is False:
            if not out.get("skipped"):
                sys.exit(1)
        return
    print("Usage: portfolio jobs {list|run|status} …")
    sys.exit(2)


def _run_brokers_command(args) -> None:
    """Handle ``portfolio brokers …`` (multi-broker registry / paths)."""
    from .brokers import (
        ensure_builtin_brokers_registered,
        get_adapter,
        list_registered_brokers,
    )
    from .paths import broker_exports_dir, default_exports_dir, instance_home

    if getattr(args, "brokers_command", None) not in (None, "list"):
        print("Usage: portfolio brokers list")
        sys.exit(2)

    ensure_builtin_brokers_registered()
    print(f"instance_home: {instance_home()}")
    print(f"exports_root:  {default_exports_dir()}")
    print()
    print(f"{'broker':<12} {'status':<12} exports_dir")
    print("-" * 72)
    for reg in list_registered_brokers():
        try:
            adapter = get_adapter(reg.broker)
            export_path = getattr(adapter, "exports_dir", None)
            if export_path is None and reg.broker != "synthetic":
                export_path = broker_exports_dir(reg.broker)
            export_s = str(export_path) if export_path else "(n/a)"
        except Exception as exc:  # noqa: BLE001 — display registry health only
            export_s = f"(adapter error: {exc})"
        print(f"{reg.broker:<12} {reg.status:<12} {export_s}")
        if reg.description:
            print(f"  {reg.description}")


def _run_connectors_command(args) -> None:
    """Handle ``portfolio connectors …``."""
    import json

    from portfolio_analysis.connectors import (
        configure_connector,
        get_connector,
        list_connectors,
        oauth_complete,
        oauth_start,
        probe_connector,
        redact_connector,
    )

    cmd = getattr(args, "connectors_command", None)
    if cmd in (None, "list"):
        for c in list_connectors():
            r = redact_connector(c)
            print(
                f"{r['broker']:<12} mode={r['mode']:<12} "
                f"secrets={r['secrets_present']} tokens={r['tokens_present']} "
                f"mcp={r.get('mcp_url') or '-'}"
            )
        return
    if cmd == "show":
        print(json.dumps(redact_connector(get_connector(args.broker)), indent=2))
        return
    if cmd == "set":
        enabled = None
        if getattr(args, "enabled", None) is not None:
            enabled = args.enabled == "true"
        cfg = configure_connector(
            args.broker,
            mode=args.mode,
            enabled=enabled,
            mcp_url=args.mcp_url,
            mcp_command=args.mcp_command,
            mcp_tool_prefix=args.mcp_tool_prefix,
            redirect_uri=args.redirect_uri,
            exports_dir=args.exports_dir,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )
        print(json.dumps(redact_connector(cfg), indent=2))
        return
    if cmd == "test":
        print(json.dumps(probe_connector(args.broker), indent=2))
        return
    if cmd == "oauth-start":
        print(json.dumps(oauth_start(args.broker), indent=2))
        return
    if cmd == "oauth-complete":
        print(
            json.dumps(
                oauth_complete(
                    args.broker, code=args.code, code_verifier=args.verifier
                ),
                indent=2,
            )
        )
        return
    print("Usage: portfolio connectors {list|show|set|test|oauth-start|oauth-complete}")
    sys.exit(2)


def _run_fund_command(args) -> None:
    """Handle ``portfolio fund …`` subcommands."""
    from .fund.alerts import evaluate_fund_alerts
    from .fund.charts import generate_fund_ta_chart_from_db
    from .fund.series import (
        InsufficientFundHistory,
        import_broker_to_gt,
        load_fund_index_series,
        rebuild_fund_daily,
        store_adapter_ground_truth,
    )
    from .fund.symbols import fund_symbol, parse_fund_symbol
    from .fund.technicals import compute_fund_moving_averages

    if not getattr(args, "fund_command", None):
        print("Usage: portfolio fund {import|rebuild|series|mas|alerts|chart} …")
        sys.exit(2)

    conn = init_db()

    if args.fund_command == "import":
        from .brokers import get_adapter
        from .brokers.base import AccountPosition, CashFlow, EquitySnapshot, FundAccount
        from .brokers.synthetic import SyntheticBrokerAdapter

        if args.demo or args.broker == "synthetic":
            adapter = _demo_synthetic_adapter(
                FundAccount,
                EquitySnapshot,
                CashFlow,
                AccountPosition,
                SyntheticBrokerAdapter,
                long_history=True,
            )
        else:
            adapter = get_adapter(args.broker)
        result = import_broker_to_gt(
            conn,
            adapter,
            account_key=args.account_key,
            rebuild=not args.no_rebuild,
        )
        print(result)
        return

    if args.fund_command == "rebuild":
        if args.demo:
            from .brokers.base import (
                AccountPosition,
                CashFlow,
                EquitySnapshot,
                FundAccount,
            )
            from .brokers.synthetic import SyntheticBrokerAdapter

            adapter = _demo_synthetic_adapter(
                FundAccount,
                EquitySnapshot,
                CashFlow,
                AccountPosition,
                SyntheticBrokerAdapter,
                long_history=False,
            )
            counts = store_adapter_ground_truth(
                conn, adapter, account_key=args.account_key
            )
            print(f"Stored GT: {counts}")
        n = rebuild_fund_daily(conn, broker=args.broker, account_key=args.account_key)
        print(
            f"Rebuilt {n} fund_daily rows for "
            f"{fund_symbol(args.broker, args.account_key)}"
        )
        return

    if args.fund_command == "chart":
        try:
            path = generate_fund_ta_chart_from_db(
                conn,
                args.symbol,
                price_field=args.price_field,
                output_path=args.output,
            )
        except InsufficientFundHistory as exc:
            print(f"[INSUFFICIENT HISTORY] {exc}")
            sys.exit(1)
        print(f"Chart saved to: {path}")
        return

    parsed = parse_fund_symbol(args.symbol)
    if parsed.is_combined:
        print("FUND:ALL is not implemented yet (per-account only in v1).")
        sys.exit(1)

    series = load_fund_index_series(conn, args.symbol)
    if args.fund_command == "series":
        if not series:
            print(f"No fund_daily rows for {args.symbol}")
            sys.exit(1)
        print("as_of_date  twrr_index  daily_return  external_cf  liquidation_value")
        for row in series:
            print(
                f"{row['as_of_date']}  {row['twrr_index']:.6f}  "
                f"{float(row['daily_return'] or 0):+.6f}  "
                f"{float(row['external_cf'] or 0):+.2f}  "
                f"{float(row['liquidation_value']):.2f}"
            )
        return

    if args.fund_command == "mas":
        try:
            mas = compute_fund_moving_averages(
                series,
                fund_symbol=args.symbol,
                price_field=getattr(args, "price_field", "twrr_index"),
            )
        except InsufficientFundHistory as exc:
            print(f"[INSUFFICIENT HISTORY] {exc}")
            sys.exit(1)
        for k, v in mas.as_dict().items():
            print(f"{k}: {v}")
        return

    if args.fund_command == "alerts":
        alerts = evaluate_fund_alerts(series, fund_symbol=args.symbol)
        fired = [a for a in alerts if a.fired]
        print(f"Evaluated {len(alerts)} rules; {len(fired)} fired")
        for a in alerts:
            flag = "FIRE" if a.fired else "ok"
            print(f"[{flag}] {a.rule}: {a.message}")
        return

    print(f"Unknown fund subcommand: {args.fund_command}")
    sys.exit(2)


def _demo_synthetic_adapter(
    FundAccount,
    EquitySnapshot,
    CashFlow,
    AccountPosition,
    SyntheticBrokerAdapter,
    *,
    long_history: bool = False,
):
    """Synthetic account path with deposit + holdings (for --demo / offline pressure)."""
    from datetime import date, timedelta

    acct = FundAccount(
        broker="synthetic",
        account_key="demo01",
        display_name="Demo Managed Account",
        broker_account_ref="SYNTH-DEMO01",
    )
    if long_history:
        n_days = 220
        start = date(2025, 1, 2)
        deposit_day = 40
        daily_growth = 1.0015
    else:
        # Short path kept for legacy CLI tests (Jan 2026 calendar)
        n_days = 10
        start = date(2026, 1, 1)
        deposit_day = 4
        daily_growth = 1.005
    snaps = []
    base = 100_000.0
    prev = base
    for i in range(n_days):
        d = start + timedelta(days=i)
        cf = 10_000.0 if i == deposit_day else 0.0
        v = (prev + cf) * daily_growth
        snaps.append(
            EquitySnapshot(
                account_key="demo01",
                broker="synthetic",
                as_of_date=d.isoformat(),
                liquidation_value=round(v, 2),
                cash=round(v * 0.05, 2),
                source="synthetic",
            )
        )
        prev = v
    flows = [
        CashFlow(
            account_key="demo01",
            broker="synthetic",
            flow_date=(start + timedelta(days=deposit_day)).isoformat(),
            amount=10_000.0,
            flow_type="deposit",
            source="synthetic",
            notes="demo deposit",
        )
    ]
    last_day = snaps[-1].as_of_date
    positions = [
        AccountPosition(
            broker="synthetic",
            account_key="demo01",
            as_of_date=last_day,
            symbol="AAA",
            quantity=100.0,
            market_value=50_000.0,
            price=500.0,
            cost_basis=45_000.0,
            asset_type="EQUITY",
            source="synthetic",
        ),
        AccountPosition(
            broker="synthetic",
            account_key="demo01",
            as_of_date=last_day,
            symbol="BBB",
            quantity=200.0,
            market_value=round(prev * 0.4, 2),
            price=100.0,
            asset_type="EQUITY",
            source="synthetic",
        ),
    ]
    return SyntheticBrokerAdapter(
        accounts=[acct],
        snapshots=snaps,
        cash_flows=flows,
        positions=positions,
    )


if __name__ == "__main__":
    main()
