#!/usr/bin/env python3
"""
Portfolio Analysis MCP Server

Exposes tools that mirror the `portfolio` CLI and core analysis modules
(TWRR reports, YTD P/L table, daily position reconstruction, chart generation).

Designed for Streamable HTTP (via the mcp-gateway + Tailscale Funnel) and stdio.

Usage (local dev):
    uv run --with mcp python -m portfolio_analysis.mcp_server

Usage (HTTP, as used by the deployment wrapper):
    uv run --with mcp python -m portfolio_analysis.mcp_server --http --port 3460 --host 0.0.0.0

Tools are thin, well-documented wrappers around the canonical functions in
reporting.py, daily_positions.py, charts.py, and twrr.py so that behavior
stays in sync with the CLI.

The server uses the instance DB under PORTFOLIO_ANALYSIS_HOME
(~/.portfolio-analysis/portfolio.db by default).
(the same one used by the CLI after reconciliation).
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .charts import generate_twrr_ohlc_position_chart
from .daily_positions import reconstruct_daily_position_quantities
from .ingest import ingest_schwab_export_file

# Import the project's canonical implementations (keep parity with CLI)
# print_ytd_twrr_pl_table is used only inside one tool via stdout capture
from .reporting import (
    get_ytd_twrr_pl_table,
    print_ytd_twrr_pl_table,  # noqa: F401 (used inside tool via redirect_stdout)
)
from .twrr import (
    InsufficientDailyTwrrData,
    get_capital_efficiency_twrr_report,
    print_twrr_capital_efficiency_table,
)

# Optional integration with the enhanced chart generator (staged on current branch)
try:
    # The enhanced version lives in tools/ during development
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
    from generate_symbol_twrr_chart import (
        generate_symbol_chart as _enhanced_generate_symbol_chart,
    )
except Exception:
    _enhanced_generate_symbol_chart = None  # Fall back to the one in charts.py

mcp = FastMCP(
    "portfolio-analysis",
    instructions=(
        "Tools for personal portfolio TWRR / Capital Efficiency, YTD P/L vs broker, "
        "daily position reconstruction (anchored + Journal-safe), and TWRR/OHLC/position "
        "size chart generation (with optional trade annotations). "
        "You can also upload fresh Schwab export files (Positions CSVs, Transactions CSVs, "
        "Realized Gain/Loss CSVs) using upload_and_ingest_schwab_exports_tool. The server "
        "will persist the raw files and ingest them into the immutable gt_* ground truth tables. "
        "After upload+ingest, call the report tools for fresh numbers. "
        "Configure multi-broker live connectors with list/configure/test_connector tools "
        "(credentials + OAuth tokens stored only under PORTFOLIO_ANALYSIS_HOME/secrets and tokens). "
        "All private data lives under PORTFOLIO_ANALYSIS_HOME (never the git repo). "
        "Behavior matches the `portfolio` CLI. Use after reconciliation for best TWRR results."
    ),
)


@mcp.tool()
def get_ytd_twrr_pl_table_tool(
    sacred_dir: str | None = None,
) -> str:
    """
    Return the YTD TWRR + Broker P/L % table for all current equity positions,
    sorted by top TWRR performers first (exactly like `portfolio ytd-pl`).

    Columns: Symbol, Qty, Mkt Val, YTD TWRR%, P/L %, P/L YTD $, Mark Val

    Args:
        sacred_dir: Optional path to Schwab exports (for latest AccountStatement P/L %).
                    Defaults to the normal discovery locations.

    Returns:
        Formatted markdown table (or a clear message if no sufficient data).
    """
    data = get_ytd_twrr_pl_table(sacred_dir=Path(sacred_dir) if sacred_dir else None)
    if not data:
        return "No positions with sufficient data for YTD TWRR + P/L table."

    # Reuse the existing pretty printer but capture output
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        print_ytd_twrr_pl_table(data)
    return buf.getvalue().strip()


@mcp.tool()
def get_twrr_report_tool(
    symbols: list[str] | None = None,
    period: str = "all-time",
    detailed: bool = False,
) -> str:
    """
    Capital Efficiency / Daily TWRR report (mirrors `portfolio twrr`).

    Returns a formatted table (or detailed sub-period breakdown when detailed=True).

    Args:
        symbols: Limit to specific symbols (e.g. ["AAPL", "AAPL"]). None = all active.
        period: Not directly used by the canonical fast path (kept for CLI parity).
        detailed: If True, return full sub-period breakdown instead of the summary table.

    Returns:
        Text report (table or detailed breakdown).
    """

    if detailed and symbols:
        from .twrr import print_detailed_twrr_breakdown

        out = []
        for sym in symbols:
            # Capture the detailed print
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    print_detailed_twrr_breakdown(sym)
                except Exception as e:
                    buf.write(f"Error for {sym}: {e}\n")
            out.append(buf.getvalue().strip())
        return "\n\n".join(out)

    try:
        report = get_capital_efficiency_twrr_report(
            only_active=(symbols is None),
            symbols=symbols,
        )
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_twrr_capital_efficiency_table(report, separate_options=False)
        return buf.getvalue().strip()
    except InsufficientDailyTwrrData as e:
        return f"[INSUFFICIENT DAILY DATA] {e}\n\nRun reconciliation first."


@mcp.tool()
def get_daily_positions_tool(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """
    Clean daily position quantity series for a symbol (anchored reconstruction).

    Uses the canonical `reconstruct_daily_position_quantities`:
    - Anchors to latest good gt_daily_positions snapshot
    - Only applies Buy/Sell after the anchor
    - Ignores Journal entries (internal adjustments)
    - Returns a dense daily step series (no gaps)

    This is the data source used by the TWRR/OHLC/position chart bottom panel.

    Args:
        symbol: Ticker (e.g. "AAPL", "AAPL").
        start_date, end_date: YYYY-MM-DD (defaults chosen from available data).

    Returns:
        Markdown table of date,quantity (or a short message if no data).
    """
    df = reconstruct_daily_position_quantities(
        None,  # will open the default DB
        symbol.upper(),
        start_date,
        end_date,
    )
    if df is None or df.empty:
        return f"No position data for {symbol}."

    # Nice small table
    lines = ["date | quantity", "---|---"]
    for _, row in df.iterrows():
        lines.append(f"{row['as_of_date']} | {row['quantity']}")
    return "\n".join(lines)


@mcp.tool()
def generate_twrr_ohlc_position_chart_tool(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    annotate_trades: bool = False,
    output: str | None = None,
) -> str:
    """
    Generate the TWRR + OHLC + Position Size chart for a symbol (3-panel PNG).

    Bottom panel uses the clean anchored reconstruction (Journals ignored).
    When annotate_trades=True, Buy/Sell markers are overlaid (uses the enhanced
    generator from tools/generate_symbol_twrr_chart.py when available).

    Args:
        symbol: Ticker.
        start_date, end_date: YYYY-MM-DD range.
        annotate_trades: Overlay trade markers on the TWRR line.
        output: Explicit output PNG path (otherwise a timestamped file under
                the standard reports directory is used).

    Returns:
        Path to the generated PNG + a one-line status.
    """
    out_path = Path(output) if output else None

    if annotate_trades and _enhanced_generate_symbol_chart is not None:
        # Use the enhanced version that supports trade annotation
        p = _enhanced_generate_symbol_chart(
            symbol.upper(),
            start_date,
            end_date,
            out_path,
            annotate_trades=True,
        )
        return f"Chart (with trade annotations) saved to: {p}"

    # Fall back to / use the canonical one in the package
    p = generate_twrr_ohlc_position_chart(
        symbol.upper(),
        output_path=out_path,
        start_date=start_date,
        end_date=end_date,
    )
    note = (
        " (annotate_trades requested but enhanced generator not available; used base version)"
        if annotate_trades
        else ""
    )
    return f"Chart saved to: {p}{note}"


@mcp.tool()
def upload_and_ingest_schwab_exports_tool(
    files: list[dict[str, str]],
    exports_dir: str | None = None,
    db_path: str | None = None,
) -> str:
    """
    Upload one or more fresh Schwab export files (CSV content + original filename)
    and ingest them into the Ground Truth (gt_*) tables.

    This is the primary way for MCP clients (such as the Grok app) to bring new
    user-downloaded Schwab data (Positions, Transactions, Realized Gains, etc.)
    into the system so that subsequent reports and charts reflect the latest exports.

    Files are persisted under the standard schwab-exports directory (in a
    timestamped mcp-uploads/ subdir) so they remain available for manual
    re-ingestion, sacred_dir use, and audit.

    Supported: *Positions*.csv, *GainLoss*Realized*.csv, *Transactions*.csv
    (XML transactions can be uploaded for storage but full parsing may require
    additional tooling).

    After successful ingestion you should call get_ytd_twrr_pl_table_tool or
    get_twrr_report_tool (or get_daily_positions_tool for a symbol) to see
    updated results. Full daily TWRR may require running reconciliation
    (build_reconciled_daily_positions) if the new data introduces new trade dates.

    Args:
        files: List of dicts, each with:
               - "filename": original name, e.g. "Account_Positions_2026-06-12.csv"
               - "content": the complete text content of the file
        exports_dir: Optional override for the base exports directory
                     (primarily for testing / advanced use). Defaults to
                     PORTFOLIO_ANALYSIS_HOME/schwab-exports .
        db_path: Optional path to the portfolio DB to ingest into. Defaults
                 to PORTFOLIO_ANALYSIS_HOME/portfolio.db . Useful
                 for hermetic tests or targeting a specific DB.

    Returns:
        Markdown report of files written + per-file ingest counts + totals +
        next-step guidance.
    """
    if not files:
        return "No files provided. Please supply at least one Schwab export file."

    from .db import init_db
    from .paths import broker_exports_dir

    # Schwab MCP upload path (other brokers will get their own tools/dirs).
    base = Path(exports_dir) if exports_dir else broker_exports_dir("schwab")
    uploads_dir = base / "mcp-uploads" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    per_file_counts: list[tuple[str, int]] = []

    # Resolve DB once (supports hermetic tests via db_path)
    resolved_db = Path(db_path) if db_path else None

    for item in files:
        raw_name = item.get("filename") or "unknown_export.csv"
        content = item.get("content") or ""
        # Sanitize: only the basename, no path traversal
        safe_name = Path(raw_name).name
        if not safe_name or "/" in safe_name or "\\" in safe_name:
            safe_name = "upload_" + datetime.now().strftime("%H%M%S") + ".csv"

        target = uploads_dir / safe_name
        target.write_text(content, encoding="utf-8")
        written.append(str(target))

        # Ingest this specific file
        conn = init_db(resolved_db)  # ensures schema on the chosen DB
        try:
            n = ingest_schwab_export_file(conn, target)
            per_file_counts.append((safe_name, n))
        finally:
            conn.close()

    # Build nice summary
    lines = ["## Schwab Export Upload + Ingestion Summary", ""]
    lines.append(f"Saved {len(written)} file(s) under: `{uploads_dir}`")
    lines.append("")
    lines.append("Ingestion results:")
    total_ingested = 0
    for name, cnt in per_file_counts:
        lines.append(f"- `{name}`: {cnt} rows ingested into GT tables")
        total_ingested += cnt
    lines.append("")
    lines.append(f"**Total rows ingested this upload: {total_ingested}**")
    lines.append("")
    lines.append("Next steps (call these tools):")
    lines.append(
        "- `get_ytd_twrr_pl_table_tool` for updated YTD TWRR + broker P/L table"
    )
    lines.append(
        "- `get_twrr_report_tool` (or with specific symbols) for Capital Efficiency / TWRR"
    )
    lines.append(
        "- `get_daily_positions_tool(symbol=...)` to inspect reconstructed quantities"
    )
    lines.append("")
    lines.append(
        "Note: If the new data includes trades on previously unseen dates, "
        "you may want to run full reconciliation (`build_reconciled_daily_positions.py --loop`) "
        "for complete daily_twrr coverage before detailed reports."
    )
    lines.append("")
    lines.append(
        "Raw files are persisted and will be picked up by future manual or scripted ingestion runs."
    )

    return "\n".join(lines)


# ------------------------------------------------------------------
# Configurable broker connectors (local secrets + OAuth / MCP)
# ------------------------------------------------------------------


@mcp.tool()
def list_connectors_tool() -> str:
    """List configured broker connectors (redacted — never returns secrets).

    Shows mode (mcp|direct|exports_only|auto), MCP URL if set, whether OAuth
    client credentials and tokens exist under PORTFOLIO_ANALYSIS_HOME.
    """
    import json

    from portfolio_analysis.connectors import list_connectors, redact_connector

    rows = [redact_connector(c) for c in list_connectors()]
    return json.dumps(rows, indent=2)


@mcp.tool()
def get_connector_tool(broker: str = "schwab") -> str:
    """Get one connector's redacted status/config (no secrets)."""
    import json

    from portfolio_analysis.connectors import get_connector, redact_connector

    return json.dumps(redact_connector(get_connector(broker)), indent=2)


@mcp.tool()
def configure_connector_tool(
    broker: str = "schwab",
    mode: str | None = None,
    enabled: bool | None = None,
    mcp_url: str | None = None,
    mcp_command: str | None = None,
    mcp_tool_prefix: str | None = None,
    mcp_apikey_env: str | None = None,
    redirect_uri: str | None = None,
    exports_dir: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    notes: str | None = None,
) -> str:
    """Configure a broker connector. Secrets are stored locally only.

    Modes:
      - mcp: call local/remote MCP (e.g. http://127.0.0.1:3473/mcp or gateway URL)
      - direct: Schwab Developer API with OAuth tokens in PORTFOLIO_ANALYSIS_HOME
      - exports_only: file exports only (no live calls)
      - auto: try MCP then direct

    client_id/client_secret are written to
    ``$PORTFOLIO_ANALYSIS_HOME/secrets/{broker}_oauth.json`` (mode 0600), never to git.
    Non-secret settings go to ``connectors/{broker}.json``.

    Returns redacted connector status JSON.
    """
    import json

    from portfolio_analysis.connectors import configure_connector, redact_connector

    cfg = configure_connector(
        broker,
        mode=mode,
        enabled=enabled,
        mcp_url=mcp_url,
        mcp_command=mcp_command,
        mcp_tool_prefix=mcp_tool_prefix,
        mcp_apikey_env=mcp_apikey_env,
        redirect_uri=redirect_uri,
        exports_dir=exports_dir,
        client_id=client_id,
        client_secret=client_secret,
        notes=notes,
    )
    return json.dumps(redact_connector(cfg), indent=2)


@mcp.tool()
def test_connector_tool(broker: str = "schwab") -> str:
    """Probe a connector (MCP or direct API). Does not invent balances.

    Returns JSON: ok, live_source name, account count, errors if any.
    """
    import json

    from portfolio_analysis.connectors import probe_connector

    return json.dumps(probe_connector(broker), indent=2)


@mcp.tool()
def connector_oauth_start_tool(broker: str = "schwab") -> str:
    """Start OAuth (PKCE) for a connector that supports developer-API auth (Schwab).

    Prerequisites: configure_connector_tool with client_id + client_secret.
    Open the returned authorization_url in a browser, then call
    connector_oauth_complete_tool with the redirect ``code``.
    """
    import json

    from portfolio_analysis.connectors import oauth_start

    try:
        return json.dumps(oauth_start(broker), indent=2)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def connector_oauth_complete_tool(
    broker: str = "schwab",
    code: str = "",
    code_verifier: str | None = None,
) -> str:
    """Complete OAuth: exchange authorization code for tokens (local storage only).

    Tokens are saved under PORTFOLIO_ANALYSIS_HOME/tokens/ (mode 0600).
    If code_verifier is omitted, the value from connector_oauth_start_tool is used.
    """
    import json

    from portfolio_analysis.connectors import oauth_complete

    if not code:
        return json.dumps(
            {"ok": False, "error": "code is required (from OAuth redirect URL)"},
            indent=2,
        )
    try:
        return json.dumps(
            oauth_complete(broker, code=code, code_verifier=code_verifier),
            indent=2,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def connector_oauth_status_tool(broker: str = "schwab") -> str:
    """OAuth credential/token presence for a connector (never returns secret values)."""
    import json

    from portfolio_analysis.connectors import oauth_status

    return json.dumps(oauth_status(broker), indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Analysis MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run with Streamable HTTP transport (for gateway / remote use).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", 3460)),
        help="Port for HTTP transport (default 3460 or MCP_PORT env).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host to bind (default 0.0.0.0).",
    )
    args = parser.parse_args()

    if args.http:
        print(
            f"Starting portfolio-analysis MCP (Streamable HTTP) on {args.host}:{args.port}"
        )
        print(
            f"Starting portfolio-analysis MCP (Streamable HTTP) on {args.host}:{args.port}"
        )
        # Some versions of FastMCP.run() don't accept host/port as kwargs.
        # Configure via .settings if available, then call with just transport.
        if hasattr(mcp, "settings"):
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        print("Starting portfolio-analysis MCP (stdio)")
        mcp.run()


if __name__ == "__main__":
    main()
