"""Daily per-account net liquidation series from local GT (gap-fill, validated).

Rules (hard):
- Only **US market days** are candidates for rows.
- Never invent intermediate-day net-liq without a real local
  ``gt_fund_equity_snapshots`` row for that day.
- Reject nonsensical values (non-finite, negative).
- When a **live** liquidation value is available for an account's current
  snapshot date, the stored daily row for that date must **exactly equal**
  the live value (and we write the live value).
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
from .market_days import iter_market_days
from .registry import JOB_DAILY_NET_LIQ
from .status import strip_secrets, utc_now_iso, write_job_status


@dataclass
class NetLiqAccountResult:
    broker: str
    account_key: str
    ok: bool
    rows_written: int = 0
    rows_skipped_no_gt: int = 0
    rows_rejected: int = 0
    gap_from: str | None = None
    gap_to: str | None = None
    last_as_of: str | None = None
    live_exact_match: bool | None = None
    rejected: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.accounts and isinstance(self.accounts[0], NetLiqAccountResult):
            d["accounts"] = [a.to_public_dict() for a in self.accounts]
        d["version"] = 1
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


def gt_equity_by_date(
    conn: sqlite3.Connection, broker: str, account_key: str
) -> dict[str, tuple[float, str, int]]:
    """Map as_of_date → (liquidation_value, source, data_quality).

    When multiple sources exist for a day, prefer highest data_quality then
    non-synthetic source labels.
    """
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


def _upsert_daily_net_liq(
    conn: sqlite3.Connection,
    *,
    broker: str,
    account_key: str,
    as_of_date: str,
    net_liquidation_value: float,
    source: str,
    data_quality: int = 100,
) -> None:
    conn.execute(
        """
        INSERT INTO daily_account_net_liq (
            broker, account_key, as_of_date, net_liquidation_value,
            source, data_quality, validated, calc_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(broker, account_key, as_of_date) DO UPDATE SET
            net_liquidation_value = excluded.net_liquidation_value,
            source = excluded.source,
            data_quality = excluded.data_quality,
            validated = 1,
            calc_timestamp = excluded.calc_timestamp
        """,
        (
            broker.lower(),
            account_key.lower(),
            as_of_date,
            net_liquidation_value,
            source,
            data_quality,
            utc_now_iso(),
        ),
    )


def fill_account_net_liq_gap(
    conn: sqlite3.Connection,
    broker: str,
    account_key: str,
    *,
    as_of_today: date | None = None,
    live_snapshots: Mapping[str, float] | None = None,
) -> NetLiqAccountResult:
    """Reconcile daily_account_net_liq from last saved date through today.

    ``live_snapshots`` maps as_of_date → liquidation_value from live broker
    (optional). When present for a day, stored value must equal live exactly.

    **Today is always reprocessed** when it is a US market day (even if a row
    already exists for today), so live exact-match / GT refresh can overwrite
    the current-day value. Historical gap days still start at last_saved+1 and
    are never invented without local GT (or live for that exact date).
    """
    from .market_days import is_us_market_day

    b = normalize_broker_id(broker)
    key = account_key.lower()
    result = NetLiqAccountResult(broker=b, account_key=key, ok=True)
    today = as_of_today or _today()
    live = dict(live_snapshots or {})
    gt_map = gt_equity_by_date(conn, b, key)
    if not gt_map and not live:
        result.ok = True
        result.error = None
        return result

    last = last_saved_net_liq_date(conn, b, key)
    if gt_map:
        min_gt = min(gt_map.keys())
        hist_start = (
            _parse_date(last) + timedelta(days=1) if last else _parse_date(min_gt)
        )
    else:
        # Live-only: still allow exact write for live dates (typically today)
        hist_start = today

    # Always reprocess today when it is a market day (live exact / GT refresh).
    # min(hist_start, today) pulls the window back so last==today is not a no-op.
    start = min(hist_start, today) if is_us_market_day(today) else hist_start
    result.gap_from = start.isoformat()
    result.gap_to = today.isoformat()

    if start > today:
        result.last_as_of = last
        return result

    written = 0
    skipped = 0
    rejected = 0

    for d in iter_market_days(start, today):
        ds = d.isoformat()
        # Only write when local GT exists for this market day (no fabrication),
        # or live provides an exact value for this date.
        if ds not in gt_map and ds not in live:
            skipped += 1
            continue

        if ds in live:
            lv_raw = live[ds]
            source = "live_exact"
            quality = 100
        else:
            lv_raw, source, quality = gt_map[ds]
            source = f"gt:{source}"

        ok, reason, lv = validate_net_liq_value(lv_raw)
        if not ok or lv is None:
            rejected += 1
            result.rejected.append(
                {"as_of_date": ds, "reason": reason, "raw": str(lv_raw)}
            )
            continue

        # Exact match gate when live is available for this day
        if ds in live:
            live_v = float(live[ds])
            ok2, reason2, lv2 = validate_net_liq_value(live_v)
            if not ok2 or lv2 is None:
                rejected += 1
                result.rejected.append(
                    {
                        "as_of_date": ds,
                        "reason": f"live_invalid:{reason2}",
                        "raw": str(live_v),
                    }
                )
                continue
            # Store live value exactly (identity) — never keep a stale GT row
            lv = float(live_v)
            source = "live_exact"
            quality = 100
            result.live_exact_match = True

        _upsert_daily_net_liq(
            conn,
            broker=b,
            account_key=key,
            as_of_date=ds,
            net_liquidation_value=lv,
            source=source,
            data_quality=quality,
        )
        written += 1
        result.last_as_of = ds

    conn.commit()
    result.rows_written = written
    result.rows_skipped_no_gt = skipped
    result.rows_rejected = rejected
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
    """broker,account_key → {as_of_date: lv} from injected adapters."""
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
            # All provided snapshot dates map for exact match (latest wins)
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
    """Resolve adapters used for live exact-match on the production path.

    - If ``adapters`` is provided (including empty ``{}``), use it as-is
      (tests inject fakes; empty means "do not auto-load").
    - If ``adapters is None``, best-effort load enabled live connectors
      (same broker resolution as connector_sync). Soft-fails per broker.
    """
    if adapters is not None:
        return dict(adapters)

    from portfolio_analysis.jobs.connector_sync import (
        _adapter_for_broker,
        _resolve_brokers,
    )

    out: dict[str, Any] = {}
    try:
        brokers = _resolve_brokers(
            [broker] if broker else None,
            demo=False,
        )
    except Exception:
        return out
    for b in brokers:
        try:
            out[b] = _adapter_for_broker(b, demo=False)
        except Exception:
            # Soft-fail: net-liq still runs from local GT only
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
) -> NetLiqRunResult:
    """Build/update daily_account_net_liq for accounts (gap-fill, validated).

    On the real path (``adapters is None``), best-effort loads enabled broker
    adapters so today's row can be enforced to **exactly** match live
    liquidation values. Pass ``adapters={}`` to disable auto-load (tests).
    """
    ensure_instance_home()
    started = utc_now_iso()
    job_id = JOB_DAILY_NET_LIQ

    lock: JobLock | None = None
    if not skip_lock:
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
            )
            path = write_job_status(job_id, result.to_public_dict())
            result.status_path = str(path)
            return result

    own_conn = conn is None
    db = conn if conn is not None else init_db()
    try:
        accounts = _list_accounts(db, broker=broker, account_key=account_key)
        resolved = resolve_live_adapters_for_net_liq(broker=broker, adapters=adapters)
        live_map: dict[tuple[str, str], dict[str, float]] = {}
        if live_by_account:
            for k, v in live_by_account.items():
                live_map[(k[0].lower(), k[1].lower())] = dict(v)
        for k, v in _live_from_adapters(resolved).items():
            live_map[k] = dict(v)

        results: list[NetLiqAccountResult] = []
        for b, ak in accounts:
            live = live_map.get((b.lower(), ak.lower()))
            ar = fill_account_net_liq_gap(
                db,
                b,
                ak,
                as_of_today=as_of_today,
                live_snapshots=live,
            )
            results.append(ar)

        all_ok = all(r.ok for r in results) if results else True
        finished = utc_now_iso()
        result = NetLiqRunResult(
            ok=all_ok,
            skipped=False,
            reason="completed" if results else "no_accounts",
            started_at=started,
            finished_at=finished,
            accounts=results,
            lock_held=False,
            state="ok" if all_ok else "failed",
            force=force,
        )
        # Summary without balances
        summary = {
            "accounts": len(results),
            "rows_written": sum(r.rows_written for r in results),
            "rows_rejected": sum(r.rows_rejected for r in results),
            "rows_skipped_no_gt": sum(r.rows_skipped_no_gt for r in results),
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
