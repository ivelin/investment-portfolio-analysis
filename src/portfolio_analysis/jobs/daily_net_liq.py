"""Daily per-account net liquidation: windowed fill, reconstruction, provenance.

Hard rules:
- Only US market days are candidates.
- Never stamp today's live NAV onto past days.
- Prefer GT/live broker equity snapshots; reconstruct gaps from real local
  positions/cash-flows when enabled.
- Mark every stored day as ground_truth / live_exact / reconstructed.
- Request-aware sufficiency (min_days / window) — insufficient is not silent ok.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping

from portfolio_analysis.db import init_db
from portfolio_analysis.paths import ensure_instance_home, normalize_broker_id

from .lock import JobLock
from .market_days import is_us_market_day, iter_market_days
from .net_liq_reconstruct import (
    PROVENANCE_GROUND_TRUTH,
    PROVENANCE_LIVE,
    PROVENANCE_RECONSTRUCTED,
    reconstruct_net_liq_for_day,
    verify_reconstruct_vs_snapshot,
)
from .registry import JOB_DAILY_NET_LIQ
from .status import strip_secrets, utc_now_iso, write_job_status


@dataclass
class NetLiqAccountResult:
    broker: str
    account_key: str
    ok: bool
    rows_written: int = 0
    rows_skipped_no_source: int = 0
    rows_rejected: int = 0
    rows_ground_truth: int = 0
    rows_reconstructed: int = 0
    series_len_in_window: int = 0
    requested_market_days: int | None = None
    available_market_days: int = 0
    gap_from: str | None = None
    gap_to: str | None = None
    last_as_of: str | None = None
    live_exact_match: bool | None = None
    verify_ok: bool | None = None
    verify_mismatches: list[dict[str, Any]] = field(default_factory=list)
    provenance_days: dict[str, list[str]] = field(default_factory=dict)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    # back-compat alias used by older tests/status
    rows_skipped_no_gt: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rows_skipped_no_gt"] = self.rows_skipped_no_source
        return d


@dataclass
class NetLiqRunResult:
    ok: bool
    skipped: bool
    reason: str | None
    started_at: str
    finished_at: str | None
    accounts: list[NetLiqAccountResult] = field(default_factory=list)
    lock_held: bool = False
    status_path: str | None = None
    job_id: str = JOB_DAILY_NET_LIQ
    state: str = "ok"
    force: bool = False
    min_days: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    pre_sync: bool = False
    allow_reconstruct: bool = False
    on_insufficient: str = "fail"
    coverage: dict[str, Any] = field(default_factory=dict)
    pre_sync_result: dict[str, Any] | None = None

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.accounts and isinstance(self.accounts[0], NetLiqAccountResult):
            d["accounts"] = [a.to_public_dict() for a in self.accounts]
        d["version"] = 2
        return strip_secrets(d)


def validate_net_liq_value(
    value: Any,
    *,
    allow_zero: bool = True,
) -> tuple[bool, str | None, float | None]:
    """Return (ok, reason, coerced_float). Rejects non-finite and negative."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "not_numeric", None
    if not math.isfinite(v):
        return False, "non_finite", None
    if v < 0:
        return False, "negative", None
    if v == 0 and not allow_zero:
        return False, "zero_not_allowed", None
    return True, None, v


def _parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def _today() -> date:
    return date.today()


def last_saved_net_liq_date(
    conn: sqlite3.Connection, broker: str, account_key: str
) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(as_of_date) FROM daily_account_net_liq
        WHERE broker = ? AND account_key = ?
        """,
        (broker.lower(), account_key.lower()),
    ).fetchone()
    return row[0] if row and row[0] else None


def earliest_local_raw_date(
    conn: sqlite3.Connection, broker: str, account_key: str
) -> date | None:
    """Earliest local raw date usable for NLV derive (equity, positions, cash flows)."""
    b, key = broker.lower(), account_key.lower()
    dates: list[str] = []
    for sql in (
        "SELECT MIN(as_of_date) FROM gt_fund_equity_snapshots WHERE broker=? AND account_key=?",
        "SELECT MIN(as_of_date) FROM gt_account_positions WHERE broker=? AND account_key=?",
        "SELECT MIN(flow_date) FROM gt_fund_cash_flows WHERE broker=? AND account_key=?",
    ):
        row = conn.execute(sql, (b, key)).fetchone()
        if row and row[0]:
            dates.append(str(row[0]))
    if not dates:
        return None
    return _parse_date(min(dates))


def gt_equity_by_date(
    conn: sqlite3.Connection, broker: str, account_key: str
) -> dict[str, tuple[float, str, int]]:
    """Map as_of_date → (liquidation_value, source, data_quality)."""
    rows = conn.execute(
        """
        SELECT as_of_date, liquidation_value, source, data_quality
        FROM gt_fund_equity_snapshots
        WHERE broker = ? AND account_key = ?
        ORDER BY as_of_date ASC, data_quality DESC
        """,
        (broker.lower(), account_key.lower()),
    ).fetchall()
    out: dict[str, tuple[float, str, int]] = {}
    for r in rows:
        d, lv, src, q = r[0], float(r[1]), str(r[2] or "gt"), int(r[3] or 100)
        if d not in out:
            out[d] = (lv, src, q)
        else:
            prev_lv, prev_src, prev_q = out[d]
            if q > prev_q:
                out[d] = (lv, src, q)
            elif q == prev_q and "synthetic" in prev_src and "synthetic" not in src:
                out[d] = (lv, src, q)
    return out


def count_market_days_in_series(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    start: date,
    end: date,
) -> int:
    rows = conn.execute(
        """
        SELECT as_of_date FROM daily_account_net_liq
        WHERE broker = ? AND account_key = ?
          AND as_of_date >= ? AND as_of_date <= ?
        """,
        (broker.lower(), account_key.lower(), start.isoformat(), end.isoformat()),
    ).fetchall()
    n = 0
    for (ds,) in rows:
        if is_us_market_day(_parse_date(ds)):
            n += 1
    return n


def resolve_fill_window(
    *,
    start_date: str | date | None,
    end_date: str | date | None,
    min_days: int | None,
    as_of_today: date | None = None,
) -> tuple[date | None, date]:
    """Return (start_or_None_for_legacy, end).

    When min_days is set without start_date, walk back enough market days.
    """
    end = (
        _parse_date(end_date)
        if isinstance(end_date, str)
        else (end_date or as_of_today or _today())
    )
    if start_date is not None:
        start = _parse_date(start_date) if isinstance(start_date, str) else start_date
        return start, end
    if min_days and min_days > 0:
        found = 0
        d = end
        start = end
        guard = 0
        while found < min_days and guard < min_days * 5 + 60:
            if is_us_market_day(d):
                found += 1
                start = d
            d -= timedelta(days=1)
            guard += 1
        return start, end
    return None, end


def _upsert_daily_net_liq(
    conn: sqlite3.Connection,
    *,
    broker: str,
    account_key: str,
    as_of_date: str,
    net_liquidation_value: float,
    source: str,
    data_quality: int = 100,
    provenance: str = PROVENANCE_GROUND_TRUTH,
) -> None:
    conn.execute(
        """
        INSERT INTO daily_account_net_liq (
            broker, account_key, as_of_date, net_liquidation_value,
            source, data_quality, validated, calc_timestamp, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(broker, account_key, as_of_date) DO UPDATE SET
            net_liquidation_value = excluded.net_liquidation_value,
            source = excluded.source,
            data_quality = excluded.data_quality,
            validated = 1,
            calc_timestamp = excluded.calc_timestamp,
            provenance = excluded.provenance
        """,
        (
            broker.lower(),
            account_key.lower(),
            as_of_date,
            net_liquidation_value,
            source,
            data_quality,
            utc_now_iso(),
            provenance,
        ),
    )


def fill_account_net_liq_gap(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    *,
    as_of_today: date | None = None,
    live_snapshots: Mapping[str, float] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    min_days: int | None = None,
    allow_reconstruct: bool = False,
    force_window: bool = False,
    maximize_history: bool = False,
) -> NetLiqAccountResult:
    """Fill daily_account_net_liq for one account over a window.

    When ``maximize_history`` is True (default for data_refresh pipeline), fill
    from the earliest local raw date through end so every reconstructible market
    day is considered—not only last_saved→today.
    """
    b = normalize_broker_id(broker)
    key = account_key.lower()
    result = NetLiqAccountResult(broker=b, account_key=key, ok=True)
    today = as_of_today or _today()
    live = dict(live_snapshots or {})
    gt_map = gt_equity_by_date(conn, b, key)

    win_start, win_end = resolve_fill_window(
        start_date=start_date,
        end_date=end_date or today,
        min_days=min_days,
        as_of_today=today,
    )
    end = win_end
    last = last_saved_net_liq_date(conn, b, key)

    # Explicit request window (min_days / start_date)
    if win_start is not None:
        start = win_start
    elif maximize_history:
        # Local-first: derive from earliest raw through today (full reconstructible span)
        earliest = earliest_local_raw_date(conn, b, key)
        if earliest is None and not live and not gt_map:
            result.ok = True
            return result
        start = earliest or today
        for ds in gt_map:
            start = min(start, _parse_date(ds))
        for ds in live:
            start = min(start, _parse_date(ds))
        if start > end:
            start = end
    else:
        # Legacy incremental path: advance after last_saved for *new* recon gaps,
        # but ALWAYS reprocess any day that has GT equity or live (source priority
        # upgrade: ground_truth/live_exact over reconstructed).
        if not gt_map and not live and not allow_reconstruct:
            result.ok = True
            return result
        if gt_map:
            min_gt = _parse_date(min(gt_map.keys()))
            hist_start = _parse_date(last) + timedelta(days=1) if last else min_gt
        else:
            hist_start = today
            min_gt = today
        start = min(hist_start, end) if is_us_market_day(end) else hist_start
        # Pull window back to cover every GT / live date (upgrade path)
        for ds in gt_map:
            start = min(start, _parse_date(ds))
        for ds in live:
            start = min(start, _parse_date(ds))
        # force=True: reprocess full known history span (GT + existing series)
        if force_window:
            candidates = [start, end]
            if gt_map:
                candidates.append(_parse_date(min(gt_map.keys())))
            if last:
                # include earliest stored row so recon→GT upgrades apply
                earliest = conn.execute(
                    """
                    SELECT MIN(as_of_date) FROM daily_account_net_liq
                    WHERE broker = ? AND account_key = ?
                    """,
                    (b, key),
                ).fetchone()
                if earliest and earliest[0]:
                    candidates.append(_parse_date(earliest[0]))
            start = min(candidates)

    if start > end:
        result.last_as_of = last
        return result

    # Drop prior pure-recon rows in window so maximize re-derives honestly
    # (removes obsolete flat carry-forward after reconstruction rules tighten).
    if maximize_history or force_window or allow_reconstruct:
        conn.execute(
            """
            DELETE FROM daily_account_net_liq
            WHERE broker = ? AND account_key = ?
              AND as_of_date >= ? AND as_of_date <= ?
              AND provenance = ?
            """,
            (b, key, start.isoformat(), end.isoformat(), PROVENANCE_RECONSTRUCTED),
        )

    market_days = list(iter_market_days(start, end))
    result.gap_from = start.isoformat()
    result.gap_to = end.isoformat()
    result.requested_market_days = (
        min_days if min_days else (len(market_days) if win_start is not None else None)
    )

    written = 0
    skipped = 0
    rejected = 0
    n_gt = 0
    n_recon = 0
    prov_gt: list[str] = []
    prov_live: list[str] = []
    prov_recon: list[str] = []
    verify_ok: bool | None = None

    for d in market_days:
        ds = d.isoformat()
        lv: float | None = None
        source = ""
        quality = 100
        provenance = PROVENANCE_GROUND_TRUTH
        # Existing row provenance (for upgrade decisions)
        existing = conn.execute(
            """
            SELECT provenance, net_liquidation_value FROM daily_account_net_liq
            WHERE broker = ? AND account_key = ? AND as_of_date = ?
            """,
            (b, key, ds),
        ).fetchone()

        if ds in live:
            ok, reason, coerced = validate_net_liq_value(live[ds])
            if not ok or coerced is None:
                rejected += 1
                result.rejected.append(
                    {"as_of_date": ds, "reason": f"live_invalid:{reason}"}
                )
                continue
            lv = float(coerced)
            source = "live_exact"
            provenance = PROVENANCE_LIVE
            quality = 100
            result.live_exact_match = True
        elif ds in gt_map:
            raw, src, quality = gt_map[ds]
            ok, reason, coerced = validate_net_liq_value(raw)
            if not ok or coerced is None:
                rejected += 1
                result.rejected.append({"as_of_date": ds, "reason": reason})
                continue
            lv = float(coerced)
            source = f"gt:{src}"
            provenance = PROVENANCE_GROUND_TRUTH
        elif allow_reconstruct:
            # Do not overwrite a higher-priority GT/live row with recon
            if existing and existing[0] in (
                PROVENANCE_GROUND_TRUTH,
                PROVENANCE_LIVE,
            ):
                continue
            recon = reconstruct_net_liq_for_day(conn, b, key, ds)
            if recon is None:
                skipped += 1
                continue
            ok, reason, coerced = validate_net_liq_value(recon.net_liquidation_value)
            if not ok or coerced is None:
                rejected += 1
                result.rejected.append(
                    {"as_of_date": ds, "reason": f"recon_invalid:{reason}"}
                )
                continue
            lv = float(coerced)
            source = recon.source
            quality = recon.data_quality
            provenance = PROVENANCE_RECONSTRUCTED
        else:
            skipped += 1
            continue

        # Multi-source verification: recon vs GT when both exist (audit)
        if allow_reconstruct and ds in gt_map:
            recon = reconstruct_net_liq_for_day(conn, b, key, ds)
            if recon is not None:
                gt_lv = float(gt_map[ds][0])
                match, diff = verify_reconstruct_vs_snapshot(
                    recon.net_liquidation_value, gt_lv
                )
                if verify_ok is None:
                    verify_ok = match
                else:
                    verify_ok = verify_ok and match
                if not match:
                    result.verify_mismatches.append(
                        {
                            "as_of_date": ds,
                            "abs_diff": diff,
                            "recon_source": recon.source,
                        }
                    )

        assert lv is not None
        _upsert_daily_net_liq(
            conn,
            broker=b,
            account_key=key,
            as_of_date=ds,
            net_liquidation_value=lv,
            source=source,
            data_quality=quality,
            provenance=provenance,
        )
        written += 1
        result.last_as_of = ds
        if provenance == PROVENANCE_LIVE:
            n_gt += 1
            prov_live.append(ds)
        elif provenance == PROVENANCE_RECONSTRUCTED:
            n_recon += 1
            prov_recon.append(ds)
        else:
            n_gt += 1
            prov_gt.append(ds)

    conn.commit()
    result.rows_written = written
    result.rows_skipped_no_source = skipped
    result.rows_skipped_no_gt = skipped
    result.rows_rejected = rejected
    result.rows_ground_truth = n_gt
    result.rows_reconstructed = n_recon
    result.verify_ok = verify_ok
    result.provenance_days = {
        "ground_truth": prov_gt,
        "live_exact": prov_live,
        "reconstructed": prov_recon,
    }
    series_len = count_market_days_in_series(conn, b, key, start, end)
    result.series_len_in_window = series_len
    result.available_market_days = series_len
    if rejected and written == 0 and skipped == 0:
        result.ok = False
        result.error = "all_candidates_rejected"
    return result


def _list_accounts(
    conn: sqlite3.Connection,
    *,
    broker: str | None = None,
    account_key: str | None = None,
) -> list[tuple[str, str]]:
    q = "SELECT broker, account_key FROM gt_fund_accounts"
    params: list[Any] = []
    clauses: list[str] = []
    if broker:
        clauses.append("broker = ?")
        params.append(normalize_broker_id(broker))
    if account_key:
        clauses.append("account_key = ?")
        params.append(account_key.lower())
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY broker, account_key"
    return [(r[0], r[1]) for r in conn.execute(q, params).fetchall()]


def _live_from_adapters(
    adapters: Mapping[str, Any] | None,
) -> dict[tuple[str, str], dict[str, float]]:
    out: dict[tuple[str, str], dict[str, float]] = {}
    if not adapters:
        return out
    for broker, ad in adapters.items():
        b = normalize_broker_id(broker)
        try:
            accounts = list(ad.list_accounts())
        except Exception:
            continue
        for acct in accounts:
            try:
                snaps = list(ad.equity_snapshots(acct.account_key))
            except Exception:
                continue
            if not snaps:
                continue
            m: dict[str, float] = {}
            for s in snaps:
                try:
                    m[s.as_of_date] = float(s.liquidation_value)
                except (TypeError, ValueError):
                    continue
            if m:
                out[(b, acct.account_key.lower())] = m
    return out


def resolve_live_adapters_for_net_liq(
    *,
    broker: str | None = None,
    adapters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if adapters is not None:
        return dict(adapters)

    from portfolio_analysis.jobs.connector_sync import (
        _adapter_for_broker,
        _resolve_brokers,
    )

    out: dict[str, Any] = {}
    try:
        brokers = _resolve_brokers([broker] if broker else None, demo=False)
    except Exception:
        return out
    for b in brokers:
        try:
            out[b] = _adapter_for_broker(b, demo=False)
        except Exception:
            continue
    return out


def run_daily_net_liq(
    *,
    broker: str | None = None,
    account_key: str | None = None,
    force: bool = False,
    conn: sqlite3.Connection | None = None,
    adapters: Mapping[str, Any] | None = None,
    live_by_account: Mapping[tuple[str, str], Mapping[str, float]] | None = None,
    as_of_today: date | None = None,
    skip_lock: bool = False,
    min_days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    pre_sync: bool = False,
    allow_reconstruct: bool = True,
    on_insufficient: str = "fail",
    demo: bool = False,
    maximize_history: bool = False,
) -> NetLiqRunResult:
    """Build/update daily_account_net_liq from **local** raw/GT (not broker passthrough).

    Parameters
    ----------
    min_days:
        Requested minimum market-day series length in the fill window.
    start_date / end_date:
        Explicit window (YYYY-MM-DD). end defaults to today.
    pre_sync:
        Run connector_sync first so live today is available in local GT.
    allow_reconstruct:
        Fill gaps from local positions/cash-flows (never stamp live onto past).
    maximize_history:
        When no explicit window, fill from earliest local raw through end.
    on_insufficient:
        ``fail`` → ok=False / reason=insufficient_history when under min_days;
        ``partial`` → ok=True with reason=partial_coverage.
    """
    ensure_instance_home()
    started = utc_now_iso()
    job_id = JOB_DAILY_NET_LIQ
    on_ins = (on_insufficient or "fail").strip().lower()
    if on_ins not in ("fail", "partial"):
        on_ins = "fail"

    lock: JobLock | None = None
    if not skip_lock:
        # Pipeline holds data_refresh + daily_net_liq; do not race it
        from portfolio_analysis.jobs.lock import is_job_lock_held
        from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

        if is_job_lock_held(JOB_DATA_REFRESH):
            result = NetLiqRunResult(
                ok=True,
                skipped=True,
                reason="already_running",
                started_at=started,
                finished_at=utc_now_iso(),
                accounts=[],
                lock_held=True,
                state="skipped",
                force=force,
                min_days=min_days,
                start_date=start_date,
                end_date=end_date,
                pre_sync=pre_sync,
                allow_reconstruct=allow_reconstruct,
                on_insufficient=on_ins,
            )
            path = write_job_status(job_id, result.to_public_dict())
            result.status_path = str(path)
            return result
        lock = JobLock(job_id)
        if not lock.try_acquire():
            result = NetLiqRunResult(
                ok=True,
                skipped=True,
                reason="already_running",
                started_at=started,
                finished_at=utc_now_iso(),
                accounts=[],
                lock_held=True,
                state="skipped",
                force=force,
                min_days=min_days,
                start_date=start_date,
                end_date=end_date,
                pre_sync=pre_sync,
                allow_reconstruct=allow_reconstruct,
                on_insufficient=on_ins,
            )
            path = write_job_status(job_id, result.to_public_dict())
            result.status_path = str(path)
            return result

    own_conn = conn is None
    db = conn if conn is not None else init_db()
    pre_sync_payload: dict[str, Any] | None = None
    try:
        if pre_sync:
            from portfolio_analysis.jobs.connector_sync import run_connector_sync

            sync_kw: dict[str, Any] = {
                "force": True,
                "skip_lock": True,
                "conn": db,
            }
            if demo:
                sync_kw["demo"] = True
            elif broker:
                sync_kw["brokers"] = [broker]
            if adapters is not None:
                sync_kw["adapters"] = adapters
            sync_res = run_connector_sync(**sync_kw)
            pre_sync_payload = sync_res.to_public_dict()

        accounts = _list_accounts(db, broker=broker, account_key=account_key)
        resolved = resolve_live_adapters_for_net_liq(broker=broker, adapters=adapters)
        live_map: dict[tuple[str, str], dict[str, float]] = {}
        if live_by_account:
            for k, v in live_by_account.items():
                live_map[(k[0].lower(), k[1].lower())] = dict(v)
        for k, v in _live_from_adapters(resolved).items():
            live_map[k] = dict(v)

        win_start, win_end = resolve_fill_window(
            start_date=start_date,
            end_date=end_date,
            min_days=min_days,
            as_of_today=as_of_today,
        )
        results: list[NetLiqAccountResult] = []
        for b, ak in accounts:
            live = live_map.get((b.lower(), ak.lower()))
            ar = fill_account_net_liq_gap(
                db,
                b,
                ak,
                as_of_today=as_of_today or win_end,
                live_snapshots=live,
                start_date=win_start,
                end_date=win_end,
                min_days=min_days,
                allow_reconstruct=allow_reconstruct,
                # force=True or explicit window: reprocess history for GT upgrades
                force_window=bool(force or start_date or min_days or maximize_history),
                maximize_history=bool(
                    maximize_history and win_start is None and not min_days
                ),
            )
            results.append(ar)

        # Sufficiency across accounts (min series length)
        min_series = (
            min((r.series_len_in_window for r in results), default=0) if results else 0
        )
        max_series = (
            max((r.series_len_in_window for r in results), default=0) if results else 0
        )
        req = int(min_days) if min_days else None
        insufficient = bool(req and results and min_series < req)

        if not results:
            reason = "no_accounts"
            all_ok = True
            state = "ok"
        elif any(not r.ok for r in results):
            all_ok = False
            reason = "failed"
            state = "failed"
        elif insufficient:
            if on_ins == "partial":
                all_ok = True
                reason = "partial_coverage"
                state = "ok"
            else:
                all_ok = False
                reason = "insufficient_history"
                state = "failed"
        else:
            all_ok = True
            reason = "completed"
            state = "ok"

        coverage = {
            "min_days_requested": req,
            "window_start": win_start.isoformat() if win_start else None,
            "window_end": win_end.isoformat(),
            "min_series_len": min_series,
            "max_series_len": max_series,
            "insufficient": insufficient,
            "rows_ground_truth": sum(r.rows_ground_truth for r in results),
            "rows_reconstructed": sum(r.rows_reconstructed for r in results),
            "rows_skipped_no_source": sum(r.rows_skipped_no_source for r in results),
            "verify_mismatches": sum(len(r.verify_mismatches) for r in results),
            "allow_reconstruct": allow_reconstruct,
            "pre_sync": pre_sync,
            "maximize_history": maximize_history,
        }

        finished = utc_now_iso()
        result = NetLiqRunResult(
            ok=all_ok,
            skipped=False,
            reason=reason,
            started_at=started,
            finished_at=finished,
            accounts=results,
            lock_held=False,
            state=state,
            force=force,
            min_days=min_days,
            start_date=start_date or (win_start.isoformat() if win_start else None),
            end_date=end_date or win_end.isoformat(),
            pre_sync=pre_sync,
            allow_reconstruct=allow_reconstruct,
            on_insufficient=on_ins,
            coverage=coverage,
            pre_sync_result=pre_sync_payload,
        )
        summary = {
            "accounts": len(results),
            "rows_written": sum(r.rows_written for r in results),
            "rows_rejected": sum(r.rows_rejected for r in results),
            "rows_skipped_no_source": sum(r.rows_skipped_no_source for r in results),
            "rows_ground_truth": coverage["rows_ground_truth"],
            "rows_reconstructed": coverage["rows_reconstructed"],
            "min_series_len": min_series,
            "insufficient": insufficient,
            "reason": reason,
        }
        payload = result.to_public_dict()
        payload["summary"] = summary
        path = write_job_status(job_id, payload)
        result.status_path = str(path)
        return result
    finally:
        if lock is not None:
            lock.release()
        if own_conn and db is not None:
            try:
                db.close()
            except Exception:
                pass


def format_net_liq_result_json(result: NetLiqRunResult | dict[str, Any]) -> str:
    import json

    if isinstance(result, NetLiqRunResult):
        return json.dumps(result.to_public_dict(), indent=2)
    return json.dumps(strip_secrets(dict(result)), indent=2)
