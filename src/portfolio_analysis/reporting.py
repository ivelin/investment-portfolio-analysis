"""Reusable reporting logic with period filtering."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import sqlite3
from pathlib import Path

from .db import get_connection
from .paths import default_exports_dir, get_reports_dir
from .twrr import (
    calculate_daily_twrr,
    get_capital_efficiency_twrr_report,
    InsufficientDailyTwrrData,
    build_trade_driven_subperiods,
    compute_linked_twrr,
)
from .canslim import score_canslim


def _parse_schwab_date(date_str: str) -> Optional[datetime]:
    """Parse Schwab date formats (MM/DD/YYYY or MM/DD/YY)."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def get_date_range_for_period(
    period: str,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Return start and end datetime objects for the given period."""
    today = datetime.now()
    period = period.lower().strip()

    if period in ("all-time", "all"):
        return None, None

    if period == "ytd":
        return datetime(today.year, 1, 1), today

    if period in ("previous-year", "last-year"):
        year = today.year - 1
        return datetime(year, 1, 1), datetime(year, 12, 31)

    if period.startswith("last-") and "month" in period:
        try:
            months = int(period.split("-")[1])
        except (IndexError, ValueError):
            months = 12
        start = today - timedelta(days=months * 30)
        return start, today

    # Specific year (e.g. "2026")
    if period.isdigit() and len(period) == 4:
        year = int(period)
        return datetime(year, 1, 1), datetime(year, 12, 31)

    return None, None


def generate_report(
    period: str = "all-time",
    symbol: Optional[str] = None,
    conn: sqlite3.Connection = None,
) -> List[Dict[str, Any]]:
    """Generate report filtered by period. Now uses the event-driven TWRR model with aggressive on-demand price population on trade dates."""
    if conn is None:
        conn = get_connection()

    # Aggressive on-demand price population on the actual recent trade dates of active symbols
    # (Massive first via Massive_Key + full local caching). This makes the main report able
    # to show real TWRR numbers without requiring dozens of manual Positions snapshots.
    try:
        from .market_data import ensure_prices_for_recent_trades_of_active_symbols

        ensure_prices_for_recent_trades_of_active_symbols(
            conn, lookback_days=180, price_provider="auto", verbose=False
        )
    except Exception as e:
        print(f"[Auto] Price population warning in report: {e}")

    start_dt, end_dt = get_date_range_for_period(period)

    # Get distinct symbols from ground truth realized gains (or current holdings)
    query = """
        SELECT DISTINCT symbol FROM gt_realized_gains WHERE 1=1
        UNION
        SELECT DISTINCT symbol FROM gt_daily_positions WHERE quantity > 0
    """
    params: list = []

    if symbol:
        # For single symbol filter we still support it via gt tables
        query = """
            SELECT ? as symbol WHERE EXISTS (
                SELECT 1 FROM gt_realized_gains WHERE symbol = ?
                UNION
                SELECT 1 FROM gt_daily_positions WHERE symbol = ? AND quantity > 0
            )
        """
        params = [symbol, symbol, symbol]

    symbols = conn.execute(query, params).fetchall()

    report = []
    for row in symbols:
        sym = row["symbol"]

        rg_query = """
            SELECT opened_date, closed_date, quantity, cost_basis, gain_loss
            FROM gt_realized_gains
            WHERE symbol = ?
        """
        rg_params: list = [sym]

        realized_rows = conn.execute(rg_query, rg_params).fetchall()
        realized_gains = []

        for r in realized_rows:
            rec = dict(r)
            opened = _parse_schwab_date(rec.get("opened_date", ""))
            closed = _parse_schwab_date(rec.get("closed_date", ""))

            # Apply period filter
            if start_dt and end_dt:
                if not (opened and opened >= start_dt) and not (
                    closed and closed >= start_dt
                ):
                    continue

            realized_gains.append(rec)

        if not realized_gains:
            continue

        # Use the real Daily TWRR system when possible.
        # Falls back to basic CANSLIM + realized data if insufficient daily snapshots.
        twrr_metrics = calculate_daily_twrr(sym, conn=conn) or {}
        if hasattr(twrr_metrics, "twrr_30d"):  # TwrrResult dataclass
            twrr_metrics = {
                "twrr_30d": twrr_metrics.twrr_30d,
                "twrr_60d": twrr_metrics.twrr_60d,
                "twrr_90d": twrr_metrics.twrr_90d,
                "twrr_ytd": twrr_metrics.twrr_ytd,
                "recommendation_hint": twrr_metrics.recommendation_hint,
            }
        canslim = score_canslim(sym, realized_gains, {})
        combined = {
            "symbol": sym,
            "twrr_30d": twrr_metrics.get("twrr_30d", 0),
            "twrr_60d": twrr_metrics.get("twrr_60d", 0),
            "twrr_90d": twrr_metrics.get("twrr_90d", 0),
            "twrr_ytd": twrr_metrics.get("twrr_ytd", 0),
            "total_profit": sum(g.get("gain_loss", 0) or 0 for g in realized_gains),
            "recommendation": twrr_metrics.get("recommendation_hint", "Monitor"),
            **canslim,
        }
        report.append(combined)

    # Primary sort: 30-day TWRR (real event-driven), falling back to CANSLIM
    report.sort(
        key=lambda x: (x.get("twrr_30d", 0), x.get("canslim_score", 0)), reverse=True
    )
    return report


def print_report_summary(
    report: List[Dict[str, Any]], period: str = "all-time"
) -> None:
    """Print clean report summary."""
    if not report:
        print(f"No data found for period: {period}")
        return

    print("\n" + "=" * 100)
    print(
        f"  WEED THE GARDEN REPORT — Period: {period.upper()} (Event-Driven TWRR + CANSLIM)"
    )
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100 + "\n")

    print(
        f"{'Symbol':<10} {'TWRR 30d':>9} {'YTD':>8} {'CANSLIM':>8} {'Profit':>12}  Recommendation"
    )
    print("-" * 100)

    for r in report[:40]:
        twrr30 = r.get("twrr_30d", 0)
        twrrytd = r.get("twrr_ytd", 0)
        canslim = r.get("canslim_score", 0)
        profit = r.get("total_profit", 0)
        rec = r.get("recommendation", "")[:42]
        print(
            f"{r['symbol']:<10} {twrr30:>9.2f} {twrrytd:>8.2f} {canslim:>8.0f} {profit:>12,.0f}  {rec}"
        )

    print(f"\nShowing top 40 of {len(report)} symbols for period: {period}")
    print("=" * 100 + "\n")


# -----------------------------------------------------------------------------
# Report artifact location helpers (keeps git trees clean)
# -----------------------------------------------------------------------------


# get_reports_dir imported from .paths (canonical instance home).


def default_report_path(prefix: str = "Report", suffix: str = ".pdf") -> Path:
    """Generate a timestamped default path inside the reports directory."""
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_prefix = (
        "".join(c for c in prefix if c.isalnum() or c in ("-", "_")) or "Report"
    )
    return get_reports_dir() / f"{safe_prefix}_{ts}{suffix}"


# ------------------------------------------------------------------
# YTD TWRR + Broker P/L % Table (consolidated from ad-hoc workflow)
# ------------------------------------------------------------------


import csv  # noqa: E402 (placed after ytd-pl helper functions for organization; pre-existing)


def _find_latest_account_statement(
    sacred_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Find the most recent AccountStatement CSV in the sacred exports dir (by mtime)."""
    if sacred_dir is None:
        sacred_dir = default_exports_dir()
    if not sacred_dir.exists():
        return None
    candidates = list(sacred_dir.rglob("*AccountStatement*.csv"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def parse_pl_from_account_statement(csv_path: Path) -> dict[str, dict]:
    """
    Parse the 'Profits and Losses' section of an AccountStatement CSV.
    Returns {SYMBOL: {'pl_pct': str, 'pl_ytd': str, 'mark': str}} for equity symbols only.
    Robust to header variations (Mark Value / Close Value) and some layout shifts.
    """
    if not csv_path or not csv_path.exists():
        return {}
    pl: dict[str, dict] = {}
    try:
        with open(csv_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return {}
    in_pl = False
    header = None
    for line in lines:
        low = line.lower().strip()
        if "profits and losses" in low:
            in_pl = True
            continue
        if in_pl:
            if low.startswith("symbol,"):
                try:
                    header = [h.strip() for h in next(csv.reader([line]))]
                except Exception:
                    header = None
                continue
            if any(x in low for x in ["account summary", "cash balance", "equities"]):
                break
            if header:
                try:
                    row = next(csv.reader([line]))
                except Exception:
                    continue
                if len(row) < len(header):
                    continue
                rec = dict(zip(header, row))
                sym = rec.get("Symbol", "").strip().upper()
                if not sym or " " in sym:
                    continue  # skip options / derivatives
                pl_pct = rec.get("P/L %", rec.get("P/L%", "N/A")).strip()
                pl_ytd = rec.get("P/L YTD", "N/A").strip()
                mark = rec.get(
                    "Mark Value", rec.get("Close Value", rec.get("mark", "N/A"))
                ).strip()
                pl[sym] = {"pl_pct": pl_pct, "pl_ytd": pl_ytd, "mark": mark}
    return pl


def get_ytd_twrr_pl_table(
    conn: Optional[sqlite3.Connection] = None,
    sacred_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Return merged data for YTD TWRR + broker P/L % table for current equity positions.
    Sorted descending by YTD TWRR (top performers first).
    Each entry: symbol, qty, mv, ytd_twrr, pl_pct, pl_ytd, mark
    """
    if conn is None:
        conn = get_connection()

    # Get current equity holdings (latest snapshot)
    latest = conn.execute("SELECT MAX(as_of_date) FROM gt_daily_positions").fetchone()[
        0
    ]
    if not latest:
        return []

    holdings_rows = conn.execute(
        """
        SELECT symbol, quantity, market_value
        FROM gt_daily_positions
        WHERE as_of_date = ? AND quantity > 0
        ORDER BY market_value DESC
        """,
        (latest,),
    ).fetchall()

    equity_holdings = [
        {"symbol": r["symbol"], "qty": r["quantity"], "mv": r["market_value"]}
        for r in holdings_rows
        if " " not in r["symbol"]
    ]
    if not equity_holdings:
        return []

    symbols = [h["symbol"] for h in equity_holdings]

    # TWRR YTD via the canonical report (uses daily_twrr after recon)
    try:
        twrr_rows = get_capital_efficiency_twrr_report(
            conn=conn, only_active=True, symbols=symbols
        )
    except InsufficientDailyTwrrData:
        # Fallback per-workflow: use event-driven for missing
        twrr_rows = []
        for sym in symbols:
            try:
                subs = build_trade_driven_subperiods(sym, conn)
                ytd = compute_linked_twrr(subs, f"{datetime.now().year}-01-01", latest)
                if ytd is not None:
                    twrr_rows.append(
                        {
                            "symbol": sym,
                            "twrr_ytd": round(ytd * 100, 2),
                            "days_of_data": len(
                                [s for s in subs if s.start_date != "inception"]
                            ),
                            "last_as_of": latest,
                        }
                    )
            except Exception:
                continue

    twrr_map = {r["symbol"]: r for r in twrr_rows}

    # Broker P/L from latest statement
    stmt_path = _find_latest_account_statement(sacred_dir)
    pl_map = parse_pl_from_account_statement(stmt_path) if stmt_path else {}

    # Merge + filter to those with TWRR data (prefer data quality)
    merged = []
    for h in equity_holdings:
        sym = h["symbol"]
        t = twrr_map.get(sym)
        p = pl_map.get(sym, {})
        if not t:
            continue
        ytd = t.get("twrr_ytd")
        if ytd is None:
            continue
        # filter garbage as in workflow
        if abs(ytd) > 10000:
            continue
        merged.append(
            {
                "symbol": sym,
                "qty": h["qty"],
                "mv": h["mv"],
                "ytd_twrr": ytd,
                "pl_pct": p.get("pl_pct", "N/A"),
                "pl_ytd": p.get("pl_ytd", "N/A"),
                "mark": p.get("mark", "N/A"),
            }
        )

    # Sort by YTD TWRR desc (top performers first)
    merged.sort(key=lambda x: x["ytd_twrr"], reverse=True)
    return merged


def print_ytd_twrr_pl_table(data: list[dict]) -> None:
    """Print the sorted table (matches the workflow output format)."""
    if not data:
        print("No positions with sufficient data for YTD TWRR + P/L table.")
        return

    print("YTD TWRR + Broker P/L % for all positions (top TWRR first)")
    header = "%-8s %8s %12s %12s %12s %15s %15s" % (
        "Symbol",
        "Qty",
        "Mkt Val",
        "YTD TWRR%",
        "P/L %",
        "P/L YTD $",
        "Mark Val",
    )
    print(header)
    print("-" * 100)
    for d in data:
        ytd_str = "%.2f" % d["ytd_twrr"]
        print(
            "%-8s %8.0f %12.2f %12s %12s %15s %15s"
            % (
                d["symbol"],
                d["qty"],
                d["mv"],
                ytd_str,
                d["pl_pct"],
                d["pl_ytd"],
                d["mark"],
            )
        )
    print("\nTotal positions shown: %d" % len(data))


# ------------------------------------------------------------------
# Position series for charts (uses anchored reconstruction, not raw tables)
# ------------------------------------------------------------------


def get_daily_position_series_for_symbol(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Any:
    """
    Return clean daily (date, quantity) series for charting the position size panel.
    # (pandas.DataFrame at runtime)

    Delegates to the reliable anchored reconstruction so that:
    - We start from latest gt_daily_positions <= window (respects pre-period holdings)
    - Journal tx are ignored (prevents artificial quantity spikes)
    - Always returns dense daily rows (ffill step) with no gaps.

    Never queries daily_position_values or gt_daily_positions directly for the series.
    """
    if conn is None:
        from .db import get_connection

        conn = get_connection()
    from .daily_positions import reconstruct_daily_position_quantities

    df = reconstruct_daily_position_quantities(conn, symbol, start_date, end_date)
    return df
