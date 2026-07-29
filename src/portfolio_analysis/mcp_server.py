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
(~/.investment-portfolio-analysis/portfolio.db by default).
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
        "LOCAL-FIRST portfolio platform (not a broker API passthrough). "
        "Remote brokers only feed the local cache; multi-day history is served from local DB.\n\n"
        "## Which tool for which question\n"
        "Rule of thumb: if the identifier is not a public/held security ticker, "
        "treat it as a **user account reference** and use account NLV tools — "
        "never position/TWRR tools (those return useless zeros).\n"
        "1) **Account net liquidation value (NLV) over time / current account value** "
        "→ `get_account_nlv_series_tool`. "
        "Identify the account by display_name (e.g. 'Active Trading IRA'), account_key, "
        "or last-3 digits of the brokerage account number (e.g. '052' when the account "
        "is masked as …052). "
        "Do NOT pass account suffixes or account names to symbol tools.\n"
        "2) **Per-security share quantity series** "
        "→ `get_daily_positions_tool(symbol=TICKER)` where TICKER is a real security "
        "(e.g. TSLA, SGOV, NVDA) — never an account number fragment.\n"
        "3) **Per-security TWRR / capital efficiency / OHLC+position chart** "
        "→ `get_twrr_report_tool` / `generate_twrr_ohlc_position_chart_tool` with a ticker.\n"
        "4) **YTD TWRR + broker P/L table across holdings** → `get_ytd_twrr_pl_table_tool`.\n"
        "5) **Refresh local cache** (sync remote→GT, seed on-disk statement NLV, maximize "
        "local daily NLV) → `refresh_portfolio_data_tool` (same as hourly job). "
        "Sparse multi-day history is normal; serve best-available local series + current "
        "snapshot; do not invent past NLV from today's live NAV.\n"
        "6) **Dense 60-day account NLV is usually NOT available** — live MCP is "
        "point-in-time; Account Statements are monthly anchors already seeded when present. "
        "NEVER tell the user to re-upload Schwab exports just to 'unlock' dense daily NLV. "
        "Use get_account_nlv_series_tool and chart sparse anchors + current NLV.\n"
        "7) **Jobs / connectors** → jobs_* tools, list/configure/test_connector. "
        "upload_and_ingest_schwab_exports_tool is only for NEW files the user just "
        "downloaded — not a workaround for dense NLV.\n\n"
        "Examples:\n"
        "- User: 'NLV history for the account ending in 052' "
        "→ get_account_nlv_series_tool(account='052')\n"
        "- User: 'What is Active Trading IRA worth over 60 days?' "
        "→ get_account_nlv_series_tool(account='Active Trading IRA', min_days=60)\n"
        "- User: 'TSLA position size last 60 days' "
        "→ get_daily_positions_tool(symbol='TSLA', start_date=..., end_date=...)\n"
        "- User: 'Chart TSLA TWRR' "
        "→ generate_twrr_ohlc_position_chart_tool(symbol='TSLA')\n\n"
        "Responses often include message, next_steps, client_guidance "
        "(coverage-first, not false alarms). Instance data under PORTFOLIO_ANALYSIS_HOME only."
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
def get_account_nlv_series_tool(
    account: str,
    broker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_days: int | None = None,
) -> str:
    """Account-level net liquidation value (NLV) time series from **local** DB.

    Use this for whole-account value history / current account NLV — NOT for
    per-stock position quantity or TWRR charts.

    Reads derived table ``daily_account_net_liq`` (local-first). Does not call the
    broker for a multi-day history API. Short series is coverage truth after few
    syncs; hourly ``data_refresh`` maximizes reconstructible days without stamping
    today's live NAV onto past dates.

    **When to use**
    - "What is my Active Trading IRA worth over time?"
    - "NLV for the Schwab account ending in 052"
    - "Current net liq for Roth IRA"

    **When NOT to use**
    - Per-security quantity or TWRR → get_daily_positions_tool /
      generate_twrr_ohlc_position_chart_tool with a **ticker** (TSLA, SGOV, …)

    Args:
        account: account_key (e.g. 47a915ae0e7e), display_name
            (e.g. "Active Trading IRA"), or last-3 digits of the account number
            when known (e.g. "052").
        broker: Optional broker filter (e.g. "schwab").
        start_date, end_date: Optional YYYY-MM-DD window filter on local rows.
        min_days: If set and local series is shorter, reason=partial_coverage
            with best-available series (not a hard tool failure).

    Returns:
        JSON: ok, resolved account, series[{as_of_date, net_liquidation_value,
        provenance, ...}], coverage, message, next_steps, client_guidance.
    """
    import json

    from portfolio_analysis.account_nlv import get_account_nlv_series

    return json.dumps(
        get_account_nlv_series(
            account,
            broker=broker,
            start_date=start_date,
            end_date=end_date,
            min_days=min_days,
        ),
        indent=2,
    )


def _looks_like_public_ticker(symbol: str) -> bool:
    """Heuristic: classic equity/option-ish security symbols (not account ids)."""
    import re

    s = (symbol or "").strip().upper()
    if not s:
        return False
    # Equity tickers: 1–5 letters (AAPL, TSLA, BRK.B → allow one dot)
    if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", s):
        return True
    # OSI-ish / spaced option roots
    if re.fullmatch(r"[A-Z]{1,6}\s+\d{6}[CP]\d+", s):
        return True
    if re.search(r"\d{2}/\d{2}/\d{4}", s) and re.search(r"[A-Z]{1,6}", s):
        return True
    return False


def _looks_like_account_reference(query: str) -> bool:
    """Account keys, last-3 digits, nicknames — not public tickers."""
    import re

    s = (query or "").strip()
    if not s:
        return False
    if _looks_like_public_ticker(s):
        return False
    # last-3 / short digit account masks
    if re.fullmatch(r"\d{2,4}", s):
        return True
    # opaque account_key hex-ish
    if re.fullmatch(r"[0-9a-f]{8,16}", s, re.I):
        return True
    # multi-word nicknames (Active Trading IRA)
    if " " in s or "-" in s:
        return True
    return False


def _wrong_tool_if_account_query(query: str) -> str | None:
    """Redirect ticker tools when the query is an account reference.

    Order:
    1) Unique fund-account match → hard redirect with NLV preview
    2) Account-like query that is not a public ticker shape → soft redirect
    3) Public ticker shape (AAPL, TSLA, …) → proceed even if not yet in local GT
    """
    import json

    from portfolio_analysis.account_nlv import (
        get_account_nlv_series,
        list_fund_accounts,
        resolve_account,
    )

    resolved, cands, err = resolve_account(query)
    if resolved is not None:
        nlv = get_account_nlv_series(
            resolved.account_key,
            broker=resolved.broker,
            min_days=None,
        )
        payload = {
            "ok": False,
            "reason": "wrong_tool_account_not_ticker",
            "message": (
                f"{query!r} resolves to fund account "
                f"{resolved.display_name} ({resolved.broker}/{resolved.account_key}) "
                f"via {resolved.match_via}. "
                "This tool is for security tickers only (TSLA, SGOV, …). "
                "For account NLV history / current account value call "
                "get_account_nlv_series_tool."
            ),
            "resolved_account": {
                "broker": resolved.broker,
                "account_key": resolved.account_key,
                "display_name": resolved.display_name,
                "match_via": resolved.match_via,
            },
            "next_steps": [
                (
                    f"get_account_nlv_series_tool(account={query!r}) "
                    "or account_key / display_name"
                ),
                "For a stock position series use a real ticker, e.g. symbol='TSLA'.",
            ],
            "account_nlv_preview": {
                "ok": nlv.get("ok"),
                "reason": nlv.get("reason"),
                "series_len": len(nlv.get("series") or []),
                "latest": (nlv.get("coverage") or {}).get("latest"),
                "client_guidance": nlv.get("client_guidance"),
            },
            "hint_error": err,
        }
        return json.dumps(payload, indent=2)

    # Soft redirect only for account-shaped queries (not AAPL/TSLA/…)
    if _looks_like_account_reference(query):
        accounts = list_fund_accounts()
        payload = {
            "ok": False,
            "reason": "unknown_symbol_likely_account_reference",
            "message": (
                f"{query!r} looks like a user account reference, not a public "
                "security ticker. Use get_account_nlv_series_tool for account NLV."
            ),
            "candidates": cands or accounts,
            "next_steps": [
                (
                    f"get_account_nlv_series_tool(account={query!r}) "
                    "if this names an account; or pick display_name/account_key "
                    "from candidates"
                ),
                "For per-security quantity/TWRR pass a real ticker (e.g. TSLA, SGOV).",
            ],
            "client_guidance": {
                "local_first": True,
                "not_symbol_tool": True,
                "likely_account_reference": True,
                "outcome": "unknown_symbol_likely_account_reference",
            },
        }
        return json.dumps(payload, indent=2)

    return None


@mcp.tool()
def get_daily_positions_tool(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """
    Clean daily **share quantity** series for one **security ticker** (not an account).

    Use for: "How many shares of TSLA did I hold each day?"
    Do **not** use for account NLV / "account ending in 052" / IRA total value —
    use ``get_account_nlv_series_tool`` instead.

    If ``symbol`` uniquely matches a fund account (display_name, account_key, or
    last-3 account digits), this tool refuses and returns JSON pointing at
    ``get_account_nlv_series_tool`` instead of a fake all-zero quantity series.

    Uses the canonical `reconstruct_daily_position_quantities`:
    - Anchors to latest good gt_daily_positions snapshot
    - Only applies Buy/Sell after the anchor
    - Ignores Journal entries (internal adjustments)
    - Returns a dense daily step series (no gaps)

    This is the data source used by the TWRR/OHLC/position chart bottom panel.

    Args:
        symbol: Security ticker only (e.g. "TSLA", "SGOV", "NVDA").
                Not an account number, account suffix, or account nickname.
        start_date, end_date: YYYY-MM-DD (defaults chosen from available data).

    Returns:
        Markdown table of date,quantity — or JSON redirect if symbol is an account,
        or a short message if no position data for a real ticker.

    Example: get_daily_positions_tool(symbol="TSLA", start_date="2026-05-29",
             end_date="2026-07-28")
    """
    redirect = _wrong_tool_if_account_query(symbol)
    if redirect is not None:
        return redirect

    df = reconstruct_daily_position_quantities(
        None,  # will open the default DB
        symbol.upper(),
        start_date,
        end_date,
    )
    if df is None or df.empty:
        return (
            f"No position data for ticker {symbol!r}. "
            "If you wanted account net liquidation value (IRA / account ending in "
            "digits), call get_account_nlv_series_tool(account=...) instead."
        )

    # All-zero dense calendar is not a useful "held nothing" claim for unknown tickers
    if "quantity" in df.columns and float(df["quantity"].abs().sum()) == 0.0:
        return (
            f"No non-zero holdings for ticker {symbol!r} in the requested window "
            f"({len(df)} calendar rows all quantity=0). "
            "This is not account NLV. For account value over time use "
            f"get_account_nlv_series_tool. For a real security pass its ticker "
            f"(e.g. TSLA)."
        )

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
    Generate the TWRR + OHLC + Position Size chart for one **security ticker**.

    Not for account-level NLV. For IRA / account total value over time use
    ``get_account_nlv_series_tool(account=...)``.

    Bottom panel uses the clean anchored reconstruction (Journals ignored).
    When annotate_trades=True, Buy/Sell markers are overlaid (uses the enhanced
    generator from tools/generate_symbol_twrr_chart.py when available).

    Args:
        symbol: Security ticker only (e.g. "TSLA"). Not an account id/suffix.
        start_date, end_date: YYYY-MM-DD range.
        annotate_trades: Overlay trade markers on the TWRR line.
        output: Explicit output PNG path (otherwise a timestamped file under
                the standard reports directory is used).

    Returns:
        Path to the generated PNG + a one-line status.

    Example: generate_twrr_ohlc_position_chart_tool(symbol="TSLA",
             start_date="2026-05-29", end_date="2026-07-28")
    """
    redirect = _wrong_tool_if_account_query(symbol)
    if redirect is not None:
        return redirect

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
    Upload one or more **new** Schwab export files (CSV content + original filename)
    and ingest them into the Ground Truth (gt_*) tables.

    Use only when the user has just downloaded files that are not already under
    PORTFOLIO_ANALYSIS_HOME exports. This is NOT the path to a dense 60-day account
    NLV series — for account value use get_account_nlv_series_tool (sparse anchors +
    current NLV). Existing Account Statements on disk are seeded by data_refresh.

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


@mcp.tool()
def refresh_portfolio_data_tool(
    broker: str | None = None,
    force: bool = True,
    demo: bool = False,
    min_days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    allow_reconstruct: bool = True,
    on_insufficient: str = "partial",
    background: bool = False,
) -> str:
    """Force the local-first hourly pipeline (same as scheduled data_refresh).

    1) Sync remote broker → local GT cache (accounts, positions, equity as available)
    2) Maximize local daily NLV from raw (every reconstructible market day from
       earliest local raw through today; GT + reconstruction; provenance labeled)

    After refresh, read account history with ``get_account_nlv_series_tool`` —
    do not expect the broker to return a multi-day NLV API response here.

    Concurrent with hourly job: second call returns already_running (no duplicate work).
    Returns message, next_steps, client_guidance — serve current NLV and best-available
    series from local DB; short history is coverage, not a hard service failure.
    Never stamps today's live NAV onto past days.
    background=true → run_id; poll jobs_status_tool(run_id=...).
    """
    import json

    if background:
        from portfolio_analysis.jobs.runner import start_job

        out = start_job(
            "data_refresh",
            background=True,
            trigger="mcp",
            force=bool(force),
            demo=bool(demo),
            broker=broker,
            min_days=min_days,
            start_date=start_date,
            end_date=end_date,
            allow_reconstruct=bool(allow_reconstruct),
            on_insufficient=on_insufficient or "partial",
            maximize_history=min_days is None and start_date is None,
        )
        return json.dumps(out, indent=2)

    from portfolio_analysis.jobs.pipeline import run_data_refresh

    result = run_data_refresh(
        broker=broker,
        force=bool(force),
        demo=bool(demo),
        min_days=min_days,
        start_date=start_date,
        end_date=end_date,
        allow_reconstruct=bool(allow_reconstruct),
        on_insufficient=on_insufficient or "partial",
        maximize_history=min_days is None and start_date is None,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def sync_connectors_tool(
    brokers: list[str] | None = None,
    demo: bool = False,
    force: bool = False,
    min_interval_seconds: int = 0,
) -> str:
    """One-shot broker connector → local GT only (same as hourly connector_sync / CLI portfolio sync).

    Prefer refresh_portfolio_data_tool when you also need daily net-liq derivatives.
    Sequential per broker/account. Conflict-free lock. Never fabricates balances.
    Response includes message + next_steps for the client.
    """
    import json

    from portfolio_analysis.jobs.client_messages import enrich_job_payload
    from portfolio_analysis.sync import run_sync

    result = run_sync(
        brokers=brokers,
        demo=demo,
        force=force,
        min_interval_seconds=int(min_interval_seconds or 0),
    )
    payload = enrich_job_payload("connector_sync", result.to_public_dict())
    return json.dumps(payload, indent=2)


@mcp.tool()
def sync_status_tool() -> str:
    """Last connector_sync status (non-secret). Safe for any MCP client."""
    import json

    from portfolio_analysis.sync import load_sync_status

    return json.dumps(load_sync_status(), indent=2)


@mcp.tool()
def jobs_list_tool() -> str:
    """List registered jobs and last status (catalog + status; no secrets)."""
    import json

    from portfolio_analysis.jobs.registry import list_jobs
    from portfolio_analysis.jobs.runner import list_job_statuses

    return json.dumps(
        {"jobs": list_jobs(), "status": list_job_statuses()},
        indent=2,
    )


@mcp.tool()
def jobs_run_tool(
    job_id: str,
    background: bool = True,
    demo: bool = False,
    force: bool = False,
    broker: str | None = None,
    min_interval_seconds: int = 0,
    min_days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    pre_sync: bool = False,
    allow_reconstruct: bool = True,
    on_insufficient: str = "fail",
) -> str:
    """Start a registered job. Default background=True returns run_id immediately.

    Poll with jobs_status_tool(run_id=...). Does not require a streaming MCP session.
    job_id: data_refresh | connector_sync | daily_net_liq

    data_refresh / daily_net_liq extras:
      min_days / start_date / end_date — request-aware history window
      pre_sync — daily_net_liq only: run connector_sync first
      allow_reconstruct — fill gaps from positions/cash-flows (not live stamp)
      on_insufficient — fail|partial when under min_days
    """
    import json

    from portfolio_analysis.jobs.runner import start_job

    kwargs: dict = {"force": bool(force)}
    if job_id == "connector_sync":
        kwargs["demo"] = bool(demo)
        kwargs["min_interval_seconds"] = int(min_interval_seconds or 0)
        if broker:
            kwargs["brokers"] = [broker]
    elif job_id == "data_refresh":
        kwargs["demo"] = bool(demo)
        if broker:
            kwargs["broker"] = broker
        if min_days is not None:
            kwargs["min_days"] = int(min_days)
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        kwargs["allow_reconstruct"] = bool(allow_reconstruct)
        kwargs["on_insufficient"] = on_insufficient or "partial"
        kwargs["maximize_history"] = min_days is None and not start_date
    elif job_id == "daily_net_liq":
        if broker:
            kwargs["broker"] = broker
        if min_days is not None:
            kwargs["min_days"] = int(min_days)
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        kwargs["pre_sync"] = bool(pre_sync)
        kwargs["allow_reconstruct"] = bool(allow_reconstruct)
        kwargs["on_insufficient"] = on_insufficient or "fail"
        kwargs["maximize_history"] = min_days is None and not start_date
        if demo:
            kwargs["demo"] = True
    out = start_job(
        job_id,
        background=bool(background),
        trigger="mcp",
        **kwargs,
    )
    return json.dumps(out, indent=2)


@mcp.tool()
def jobs_status_tool(
    run_id: str | None = None,
    job_id: str | None = None,
) -> str:
    """Poll job/run status (pending/running/ok/failed/skipped). No secrets.

    Pass run_id from jobs_run_tool, or job_id for last status, or neither for all.
    """
    import json

    from portfolio_analysis.jobs.runner import get_run_status

    return json.dumps(get_run_status(run_id=run_id, job_id=job_id), indent=2)


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
