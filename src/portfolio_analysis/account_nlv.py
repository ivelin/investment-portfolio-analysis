"""Local-first account NLV series (derived ``daily_account_net_liq``).

Serve account-level net liquidation history from the instance DB — not broker
passthrough and not per-symbol position tools.

Account resolution accepts:
- ``account_key`` (stable short id, e.g. ``47a915ae0e7e``)
- ``display_name`` (case-insensitive exact or unique substring)
- last-3 digits of the broker account number when known (export ``XXX###``
  hints and optional ``account_number_last3`` column)
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portfolio_analysis.db import init_db
from portfolio_analysis.paths import broker_exports_dir, instance_home


@dataclass(frozen=True)
class ResolvedAccount:
    broker: str
    account_key: str
    display_name: str
    account_number_last3: str | None = None
    match_via: str = "account_key"


def _ensure_last3_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(gt_fund_accounts)")}
    if "account_number_last3" not in cols:
        conn.execute(
            "ALTER TABLE gt_fund_accounts ADD COLUMN account_number_last3 TEXT"
        )


def list_fund_accounts(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """List local fund accounts (identity only; no secrets)."""
    own = conn is None
    db = conn if conn is not None else init_db()
    try:
        _ensure_last3_column(db)
        rows = db.execute(
            """
            SELECT broker, account_key, display_name, account_number_last3, fund_symbol
            FROM gt_fund_accounts
            ORDER BY broker, display_name
            """
        ).fetchall()
        return [
            {
                "broker": r[0],
                "account_key": r[1],
                "display_name": r[2],
                "account_number_last3": r[3],
                "fund_symbol": r[4],
            }
            for r in rows
        ]
    finally:
        if own:
            db.close()


def _normalize_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _last3_from_exports() -> dict[str, list[str]]:
    """Map last-3 account digits → display-name hints from export filenames.

    Schwab export trees often include ``XXX052`` in filenames under a folder
    like ``Active-Trading-IRA/``. This is local-only discovery — never a live API.
    """
    out: dict[str, list[str]] = {}
    roots: list[Path] = [
        broker_exports_dir("schwab"),
        instance_home() / "schwab-exports",
        instance_home() / "exports" / "schwab",
    ]
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            m = re.search(r"XXX(\d{3})", path.name, re.IGNORECASE)
            if not m:
                m = re.search(
                    r"_(\d{3})_(?:Transactions|Positions|GainLoss)", path.name
                )
            if not m:
                continue
            last3 = m.group(1)
            # Prefer parent folder names as display hints
            hints: list[str] = []
            for part in path.parts:
                if part in ("schwab-exports", "exports", "schwab", "mcp-uploads"):
                    continue
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", part):
                    continue
                if part.endswith((".csv", ".xml", ".pdf", ".json")):
                    continue
                # Active-Trading-IRA → Active Trading IRA
                hints.append(part.replace("-", " ").replace("_", " "))
            bucket = out.setdefault(last3, [])
            for h in hints:
                if h and h not in bucket:
                    bucket.append(h)
    return out


def set_account_number_last3(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    last3: str,
) -> None:
    """Persist last-3 digits only (never full account number)."""
    digits = re.sub(r"\D", "", last3 or "")
    if len(digits) < 3:
        return
    last3 = digits[-3:]
    _ensure_last3_column(conn)
    conn.execute(
        """
        UPDATE gt_fund_accounts
        SET account_number_last3 = ?
        WHERE broker = ? AND account_key = ?
        """,
        (last3, broker.lower(), account_key.lower()),
    )


def resolve_account(
    query: str,
    *,
    broker: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[ResolvedAccount | None, list[dict[str, Any]], str | None]:
    """Resolve one account from a client query.

    Returns (resolved, candidates, error_message).
    """
    q = (query or "").strip()
    if not q:
        return None, list_fund_accounts(conn), "account query is required"

    own = conn is None
    db = conn if conn is not None else init_db()
    try:
        _ensure_last3_column(db)
        accounts = list_fund_accounts(db)
        if broker:
            b = broker.lower()
            accounts = [a for a in accounts if a["broker"] == b]
        if not accounts:
            return (
                None,
                [],
                "no fund accounts in local DB — run refresh_portfolio_data_tool",
            )

        q_low = q.lower()
        q_norm = _normalize_name(q)
        q_digits = re.sub(r"\D", "", q)

        # 1) Exact account_key
        for a in accounts:
            if a["account_key"].lower() == q_low:
                return (
                    ResolvedAccount(
                        broker=a["broker"],
                        account_key=a["account_key"],
                        display_name=a["display_name"],
                        account_number_last3=a.get("account_number_last3"),
                        match_via="account_key",
                    ),
                    [a],
                    None,
                )

        # 2) Exact display_name (case-insensitive)
        exact_name = [a for a in accounts if (a["display_name"] or "").lower() == q_low]
        if len(exact_name) == 1:
            a = exact_name[0]
            return (
                ResolvedAccount(
                    broker=a["broker"],
                    account_key=a["account_key"],
                    display_name=a["display_name"],
                    account_number_last3=a.get("account_number_last3"),
                    match_via="display_name",
                ),
                exact_name,
                None,
            )
        if len(exact_name) > 1:
            return None, exact_name, "ambiguous display_name; pass account_key"

        # 3) Unique display_name substring
        subs = [
            a
            for a in accounts
            if q_norm and q_norm in _normalize_name(a["display_name"] or "")
        ]
        if len(subs) == 1:
            a = subs[0]
            return (
                ResolvedAccount(
                    broker=a["broker"],
                    account_key=a["account_key"],
                    display_name=a["display_name"],
                    account_number_last3=a.get("account_number_last3"),
                    match_via="display_name_substring",
                ),
                subs,
                None,
            )
        if len(subs) > 1:
            return (
                None,
                subs,
                "ambiguous display_name match; pass account_key or full name",
            )

        # 4) Last-3 digits of account number
        last3 = (
            q_digits[-3:]
            if len(q_digits) >= 3
            else (q if re.fullmatch(r"\d{3}", q) else "")
        )
        if last3 and len(last3) == 3:
            by_col = [
                a for a in accounts if (a.get("account_number_last3") or "") == last3
            ]
            if len(by_col) == 1:
                a = by_col[0]
                return (
                    ResolvedAccount(
                        broker=a["broker"],
                        account_key=a["account_key"],
                        display_name=a["display_name"],
                        account_number_last3=a.get("account_number_last3"),
                        match_via="account_number_last3",
                    ),
                    by_col,
                    None,
                )
            if len(by_col) > 1:
                return None, by_col, "ambiguous account_number_last3; pass account_key"

            # Export filename hints (XXX052 under Active-Trading-IRA/, etc.)
            hints = _last3_from_exports().get(last3, [])
            matched: list[dict[str, Any]] = []
            for a in accounts:
                an = _normalize_name(a["display_name"] or "")
                for h in hints:
                    hn = _normalize_name(h)
                    if not hn:
                        continue
                    if (hn == an or hn in an or an in hn) and a not in matched:
                        matched.append(a)
            if len(matched) == 1:
                a = matched[0]
                # Cache last3 for next time
                set_account_number_last3(db, a["broker"], a["account_key"], last3)
                db.commit()
                return (
                    ResolvedAccount(
                        broker=a["broker"],
                        account_key=a["account_key"],
                        display_name=a["display_name"],
                        account_number_last3=last3,
                        match_via="account_number_last3_export_hint",
                    ),
                    matched,
                    None,
                )
            if len(matched) > 1:
                return (
                    None,
                    matched,
                    "ambiguous last-3 account match; pass display_name or account_key",
                )

        return (
            None,
            accounts,
            (
                f"no account matched query={query!r}. "
                "Use account_key, display_name (e.g. 'Active Trading IRA'), "
                "or last-3 digits of the account number when known."
            ),
        )
    finally:
        if own:
            db.close()


def get_account_nlv_series(
    account: str,
    *,
    broker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_days: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Read local ``daily_account_net_liq`` for a resolved account.

    Coverage-first: short series is reported honestly; never fabricates past
    days from today's live NAV.
    """
    own = conn is None
    db = conn if conn is not None else init_db()
    try:
        resolved, candidates, err = resolve_account(account, broker=broker, conn=db)
        base_guidance = {
            "local_first": True,
            "layer": "derived_daily_account_net_liq",
            "not_symbol_tool": True,
            "can_answer_current_snapshot": True,
            "serve_best_available_series": True,
        }
        if resolved is None:
            return {
                "ok": False,
                "reason": "account_not_resolved",
                "message": err or "account not resolved",
                "query": account,
                "candidates": candidates,
                "series": [],
                "coverage": {},
                "next_steps": [
                    (
                        "Call get_account_nlv_series_tool without guessing tickers: "
                        "use display_name (e.g. 'Active Trading IRA'), account_key from "
                        "candidates, or last-3 digits of the Schwab account number."
                    ),
                    (
                        "Do NOT use get_daily_positions_tool / TWRR chart tools for "
                        "account-level NLV — those take security tickers (TSLA, SGOV), "
                        "not account number suffixes."
                    ),
                    (
                        "If candidates is empty, run refresh_portfolio_data_tool to sync "
                        "accounts into local GT, then re-query."
                    ),
                ],
                "client_guidance": {
                    **base_guidance,
                    "outcome": "account_not_resolved",
                    "candidates": len(candidates),
                },
            }

        def _rows_to_series(rows: list[Any]) -> list[dict[str, Any]]:
            return [
                {
                    "as_of_date": r[0],
                    "net_liquidation_value": r[1],
                    "provenance": r[2],
                    "source": r[3],
                    "data_quality": r[4],
                }
                for r in rows
            ]

        base_sql = """
            SELECT as_of_date, net_liquidation_value, provenance, source, data_quality
            FROM daily_account_net_liq
            WHERE broker = ? AND account_key = ?
            ORDER BY as_of_date
        """
        all_rows = db.execute(
            base_sql, (resolved.broker, resolved.account_key)
        ).fetchall()
        series_all = _rows_to_series(all_rows)

        # Window filter for series_in_window; full local history always available
        series = list(series_all)
        if start_date:
            series = [s for s in series if s["as_of_date"] >= start_date]
        if end_date:
            series = [s for s in series if s["as_of_date"] <= end_date]

        def _prov_counts(pts: list[dict[str, Any]]) -> dict[str, int]:
            out: dict[str, int] = {}
            for s in pts:
                p = s.get("provenance") or "unknown"
                out[p] = out.get(p, 0) + 1
            return out

        # Prefer latest overall (may be outside a historical-only window)
        latest = series_all[-1] if series_all else None
        if series and (
            latest is None or series[-1]["as_of_date"] >= latest["as_of_date"]
        ):
            latest = series[-1]

        # sources look like gt:export:statement:... or export:positions_sum:...
        n_export = sum(
            1 for s in series_all if "export" in str(s.get("source") or "").lower()
        )

        coverage = {
            "series_len": len(series),
            "series_len_all_local": len(series_all),
            "min_days_requested": min_days,
            "requested_window_start": start_date,
            "requested_window_end": end_date,
            "window_start": series[0]["as_of_date"] if series else start_date,
            "window_end": series[-1]["as_of_date"] if series else end_date,
            "all_local_start": series_all[0]["as_of_date"] if series_all else None,
            "all_local_end": series_all[-1]["as_of_date"] if series_all else None,
            "provenance_counts": _prov_counts(series),
            "provenance_counts_all_local": _prov_counts(series_all),
            "export_sourced_points": n_export,
            "dense_daily": bool(min_days is not None and len(series) >= int(min_days)),
            "latest": latest,
        }

        insufficient = bool(min_days is not None and len(series) < int(min_days))
        if not series_all:
            reason = "no_local_nlv_rows"
            ok = False
            msg = (
                f"No local daily NLV rows yet for {resolved.display_name} "
                f"({resolved.broker}/{resolved.account_key}). "
                "Run refresh_portfolio_data_tool to sync→seed exports→derive."
            )
            next_steps = [
                "refresh_portfolio_data_tool(force=true) then re-call this tool.",
                "Current live NLV may still be available after connector sync.",
            ]
        elif insufficient:
            reason = "partial_coverage"
            ok = True
            msg = (
                f"Local NLV for {resolved.display_name}: {len(series)} point(s) in the "
                f"requested window"
                f"{f' ({start_date}→{end_date})' if start_date or end_date else ''}"
                f" (min_days={min_days}). "
                f"Full local history has {len(series_all)} real anchor(s) "
                f"{coverage['all_local_start']}→{coverage['all_local_end']}. "
                "This is sparse statement/live GT, not a fabricated dense daily series. "
                "Serve series + series_all_local for charts; use latest for current NLV."
            )
            next_steps = [
                "Answer CURRENT NLV from coverage.latest / client_guidance.latest_nlv.",
                (
                    "Chart series (window) and series_all_local (all real anchors). "
                    "Sparse multi-month statement+live points are the history product."
                ),
                (
                    "STOP: do not ask the user to upload/re-upload Schwab exports to "
                    "produce a dense 60-day daily NLV series. That is not how this "
                    "cache works (live MCP = point-in-time; statements = sparse anchors)."
                ),
                (
                    "If the user still wants denser history later, that is a future "
                    "daily mark-to-market feature — not a missing upload."
                ),
            ]
        else:
            reason = "ok"
            ok = True
            msg = (
                f"Local NLV series for {resolved.display_name}: {len(series)} point(s) "
                f"from daily_account_net_liq (match via {resolved.match_via})."
            )
            next_steps = [
                "Use series for account-level NLV charts; provenance labels audit quality.",
                (
                    "For per-security quantity/TWRR use get_daily_positions_tool / chart tools "
                    "with a ticker (not this tool)."
                ),
            ]

        return {
            "ok": ok,
            "reason": reason,
            "message": msg,
            "query": account,
            "resolved": {
                "broker": resolved.broker,
                "account_key": resolved.account_key,
                "display_name": resolved.display_name,
                "account_number_last3": resolved.account_number_last3,
                "match_via": resolved.match_via,
            },
            "series": series,
            "series_all_local": series_all,
            "coverage": coverage,
            "next_steps": next_steps,
            "client_guidance": {
                **base_guidance,
                "outcome": reason,
                "series_len": len(series),
                "series_len_all_local": len(series_all),
                "min_days_requested": min_days,
                "dense_daily": coverage["dense_daily"],
                "can_answer_current_snapshot": latest is not None,
                "latest_nlv": (latest or {}).get("net_liquidation_value"),
                "latest_as_of": (latest or {}).get("as_of_date"),
                "chart_sparse_ok": True,
                "do_not_invent_missing_days": True,
                "do_not_recommend_export_upload_for_dense_nlv": True,
            },
        }
    finally:
        if own:
            db.close()
