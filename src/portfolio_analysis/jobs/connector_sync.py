"""Sequential broker/account → local GT sync (no fabricated balances)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from portfolio_analysis.db import init_db
from portfolio_analysis.paths import ensure_instance_home, normalize_broker_id

from .lock import JobLock, is_job_lock_held
from .registry import JOB_CONNECTOR_SYNC
from .status import (
    load_job_status,
    strip_secrets,
    utc_now_iso,
    write_job_status,
)

DEFAULT_MIN_INTERVAL_SECONDS = 0


@dataclass
class BrokerSyncResult:
    broker: str
    ok: bool
    skipped: bool = False
    reason: str | None = None
    accounts: int = 0
    snapshots: int = 0
    cash_flows: int = 0
    positions: int = 0
    gt_changed: bool = False
    rebuilt: list[dict[str, Any]] = field(default_factory=list)
    accounts_processed: list[str] = field(default_factory=list)
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncRunResult:
    ok: bool
    skipped: bool
    reason: str | None
    started_at: str
    finished_at: str | None
    brokers: list[BrokerSyncResult] = field(default_factory=list)
    lock_held: bool = False
    status_path: str | None = None
    demo: bool = False
    force: bool = False
    min_interval_seconds: int = 0
    job_id: str = JOB_CONNECTOR_SYNC
    state: str = "ok"

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.brokers and isinstance(self.brokers[0], BrokerSyncResult):
            d["brokers"] = [b.to_public_dict() for b in self.brokers]
        d["version"] = 1
        return strip_secrets(d)


def _gt_fingerprint(conn: sqlite3.Connection, broker: str) -> str:
    b = broker.lower()
    row = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM gt_fund_accounts WHERE broker = ?) AS n_acct,
          (SELECT COUNT(*) FROM gt_fund_equity_snapshots WHERE broker = ?) AS n_snap,
          (SELECT COALESCE(SUM(liquidation_value), 0) FROM gt_fund_equity_snapshots
             WHERE broker = ?) AS sum_lv,
          (SELECT COALESCE(MAX(as_of_date), '') FROM gt_fund_equity_snapshots
             WHERE broker = ?) AS max_d,
          (SELECT COUNT(*) FROM gt_fund_cash_flows WHERE broker = ?) AS n_cf,
          (SELECT COUNT(*) FROM gt_account_positions WHERE broker = ?) AS n_pos,
          (SELECT COALESCE(SUM(quantity), 0) FROM gt_account_positions
             WHERE broker = ?) AS sum_qty
        """,
        (b, b, b, b, b, b, b),
    ).fetchone()
    return "|".join(str(x) for x in row)


def _demo_adapter():
    from datetime import date, timedelta

    from portfolio_analysis.brokers.base import (
        AccountPosition,
        CashFlow,
        EquitySnapshot,
        FundAccount,
    )
    from portfolio_analysis.brokers.synthetic import SyntheticBrokerAdapter

    acct = FundAccount(
        broker="synthetic",
        account_key="demo01",
        display_name="Sync Demo Fund",
        broker_account_ref="REF-SYNC-DEMO01",
    )
    start = date(2025, 1, 2)
    n_days = 40
    snaps: list = []
    flows: list = []
    prev = 100_000.0
    for i in range(n_days):
        d = start + timedelta(days=i)
        cf = 0.0
        if i == 10:
            cf = 2_500.0
            flows.append(
                CashFlow(
                    account_key="demo01",
                    broker="synthetic",
                    flow_date=d.isoformat(),
                    amount=cf,
                    flow_type="deposit",
                    source="synthetic",
                )
            )
        v = (prev + cf) * 1.0005
        snaps.append(
            EquitySnapshot(
                account_key="demo01",
                broker="synthetic",
                as_of_date=d.isoformat(),
                liquidation_value=round(v, 2),
                cash=1_000.0,
                source="synthetic",
            )
        )
        prev = v
    last = snaps[-1].as_of_date
    positions = [
        AccountPosition(
            broker="synthetic",
            account_key="demo01",
            as_of_date=last,
            symbol="DEMO",
            quantity=10.0,
            market_value=1_000.0,
            price=100.0,
            source="synthetic",
        )
    ]
    return SyntheticBrokerAdapter(
        accounts=[acct], snapshots=snaps, cash_flows=flows, positions=positions
    )


def _resolve_brokers(
    brokers: Sequence[str] | None,
    *,
    demo: bool,
) -> list[str]:
    if demo:
        return ["synthetic"]
    if brokers:
        return [normalize_broker_id(b) for b in brokers]
    try:
        from portfolio_analysis.connectors.store import list_connectors

        names: list[str] = []
        for cfg in list_connectors():
            broker = normalize_broker_id(cfg.broker)
            if not cfg.enabled:
                continue
            if broker == "synthetic":
                continue
            if cfg.mode == "exports_only":
                continue
            names.append(broker)
        if not names:
            names = ["schwab"]
        return names
    except Exception:
        return ["schwab"]


def _adapter_for_broker(broker: str, *, demo: bool):
    if demo or broker == "synthetic":
        return _demo_adapter()
    from portfolio_analysis.brokers import (
        ensure_builtin_brokers_registered,
        get_adapter,
    )
    from portfolio_analysis.connectors.store import load_connector

    ensure_builtin_brokers_registered()
    cfg = load_connector(broker)
    if not cfg.enabled:
        raise RuntimeError(f"connector disabled: {broker}")
    if cfg.mode == "exports_only":
        raise RuntimeError(
            f"connector {broker} is exports_only — live snapshot sync skipped"
        )
    return get_adapter(broker)


def sync_broker_to_gt(
    conn: sqlite3.Connection,
    broker: str,
    *,
    adapter: Any | None = None,
    demo: bool = False,
    rebuild: bool = True,
) -> BrokerSyncResult:
    """Import one broker's accounts **sequentially** into GT; rebuild if changed."""
    from portfolio_analysis.fund.series import (
        rebuild_fund_daily,
        store_adapter_ground_truth,
    )
    from portfolio_analysis.fund.symbols import fund_symbol
    from portfolio_analysis.brokers.synthetic import SyntheticBrokerAdapter

    b = normalize_broker_id(broker)
    result = BrokerSyncResult(broker=b, ok=False)
    try:
        ad = adapter if adapter is not None else _adapter_for_broker(b, demo=demo)
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
        result.reason = "adapter_unavailable"
        return result

    try:
        fp_before = _gt_fingerprint(conn, b)
        accounts = list(ad.list_accounts())
        # Sequential per-account GT upsert (MECE: one account at a time)
        n_acct = n_snap = n_cf = n_pos = 0
        processed: list[str] = []
        for acct in accounts:
            # Slice adapter view to one account when possible
            if isinstance(ad, SyntheticBrokerAdapter) or hasattr(ad, "list_accounts"):
                partial_counts = store_adapter_ground_truth(
                    conn, ad, account_key=acct.account_key
                )
            else:
                partial_counts = store_adapter_ground_truth(
                    conn, ad, account_key=acct.account_key
                )
            n_acct += int(partial_counts.get("accounts", 0))
            n_snap += int(partial_counts.get("snapshots", 0))
            n_cf += int(partial_counts.get("cash_flows", 0))
            n_pos += int(partial_counts.get("positions", 0))
            processed.append(acct.account_key)

        result.accounts = n_acct
        result.snapshots = n_snap
        result.cash_flows = n_cf
        result.positions = n_pos
        result.accounts_processed = processed
        fp_after = _gt_fingerprint(conn, b)
        result.gt_changed = fp_before != fp_after
        rebuilt: list[dict[str, Any]] = []
        if rebuild and result.accounts > 0:
            if result.gt_changed:
                for acct in accounts:
                    n = rebuild_fund_daily(
                        conn, broker=acct.broker, account_key=acct.account_key
                    )
                    rebuilt.append(
                        {
                            "fund_symbol": fund_symbol(acct.broker, acct.account_key),
                            "broker": acct.broker,
                            "account_key": acct.account_key,
                            "fund_daily_rows": n,
                        }
                    )
            else:
                for acct in accounts:
                    sym = fund_symbol(acct.broker, acct.account_key)
                    n_existing = conn.execute(
                        "SELECT COUNT(*) FROM fund_daily WHERE fund_symbol = ?",
                        (sym,),
                    ).fetchone()[0]
                    if n_existing == 0:
                        n = rebuild_fund_daily(
                            conn, broker=acct.broker, account_key=acct.account_key
                        )
                        rebuilt.append(
                            {
                                "fund_symbol": sym,
                                "broker": acct.broker,
                                "account_key": acct.account_key,
                                "fund_daily_rows": n,
                            }
                        )
        result.rebuilt = rebuilt
        result.ok = True
        result.reason = "gt_updated" if result.gt_changed else "gt_unchanged_idempotent"
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
        result.reason = "sync_failed"
        result.ok = False
    return result


def run_connector_sync(
    *,
    brokers: Sequence[str] | None = None,
    demo: bool = False,
    force: bool = False,
    min_interval_seconds: int = DEFAULT_MIN_INTERVAL_SECONDS,
    adapters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
    skip_lock: bool = False,
) -> SyncRunResult:
    """Sequential multi-broker sync into local GT (conflict-free flock)."""
    ensure_instance_home()
    started = utc_now_iso()
    broker_list = _resolve_brokers(brokers, demo=demo)
    job_id = JOB_CONNECTOR_SYNC

    if not force and min_interval_seconds > 0:
        prev = load_job_status(job_id)
        stale = prev.get("stale_seconds")
        had_success = bool(prev.get("last_success")) or (
            prev.get("ok") is True and not prev.get("skipped")
        )
        if had_success and isinstance(stale, int) and stale < min_interval_seconds:
            result = SyncRunResult(
                ok=True,
                skipped=True,
                reason="not_stale",
                started_at=started,
                finished_at=utc_now_iso(),
                brokers=[],
                lock_held=is_job_lock_held(job_id),
                demo=demo,
                force=force,
                min_interval_seconds=min_interval_seconds,
                state="skipped",
            )
            path = write_job_status(job_id, result.to_public_dict())
            result.status_path = str(path)
            return result

    lock: JobLock | None = None
    if not skip_lock:
        # Pipeline holds data_refresh + connector_sync; do not race it
        from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH

        if is_job_lock_held(JOB_DATA_REFRESH):
            result = SyncRunResult(
                ok=True,
                skipped=True,
                reason="already_running",
                started_at=started,
                finished_at=utc_now_iso(),
                brokers=[],
                lock_held=True,
                demo=demo,
                force=force,
                min_interval_seconds=min_interval_seconds,
                state="skipped",
            )
            path = write_job_status(job_id, result.to_public_dict())
            result.status_path = str(path)
            return result
        lock = JobLock(job_id)
        if not lock.try_acquire():
            result = SyncRunResult(
                ok=True,
                skipped=True,
                reason="already_running",
                started_at=started,
                finished_at=utc_now_iso(),
                brokers=[],
                lock_held=True,
                demo=demo,
                force=force,
                min_interval_seconds=min_interval_seconds,
                state="skipped",
            )
            path = write_job_status(job_id, result.to_public_dict())
            result.status_path = str(path)
            return result

    own_conn = conn is None
    db = conn if conn is not None else init_db()
    broker_results: list[BrokerSyncResult] = []
    try:
        # Sequential brokers
        for b in broker_list:
            ad = None
            if adapters:
                ad = adapters.get(b) or adapters.get(normalize_broker_id(b))
            br = sync_broker_to_gt(db, b, adapter=ad, demo=demo or b == "synthetic")
            broker_results.append(br)
        if not broker_results:
            reason = "no_brokers"
            all_ok = True
        elif any(not r.ok and not r.skipped for r in broker_results):
            all_ok = all(r.ok for r in broker_results)
            reason = (
                "partial_failure" if any(r.ok for r in broker_results) else "failed"
            )
        else:
            all_ok = True
            reason = "completed"

        finished = utc_now_iso()
        result = SyncRunResult(
            ok=all_ok,
            skipped=False,
            reason=reason,
            started_at=started,
            finished_at=finished,
            brokers=broker_results,
            lock_held=False,
            demo=demo,
            force=force,
            min_interval_seconds=min_interval_seconds,
            state="ok" if all_ok else "failed",
        )
        path = write_job_status(job_id, result.to_public_dict())
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


def format_sync_result_json(result: SyncRunResult | dict[str, Any]) -> str:
    if isinstance(result, SyncRunResult):
        return json.dumps(result.to_public_dict(), indent=2)
    return json.dumps(strip_secrets(dict(result)), indent=2)


# Back-compat aliases used by older call sites / tests
run_sync = run_connector_sync
load_sync_status = lambda **kw: load_job_status(JOB_CONNECTOR_SYNC)  # noqa: E731
SyncLock = JobLock
is_sync_lock_held = lambda path=None: is_job_lock_held(JOB_CONNECTOR_SYNC, path)  # noqa: E731
