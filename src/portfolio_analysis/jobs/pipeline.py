"""Local-first data refresh: sync remote→GT, then maximize local derived NLV.

Hourly scheduler and client-forced MCP/CLI all call :func:`run_data_refresh`.
Acquires ``data_refresh`` + ``connector_sync`` + ``daily_net_liq`` flocks so
standalone/hourly top-up jobs cannot double-write during a pipeline run.
"""

from __future__ import annotations

from typing import Any

from portfolio_analysis.jobs.client_messages import enrich_job_payload
from portfolio_analysis.jobs.connector_sync import run_connector_sync
from portfolio_analysis.jobs.daily_net_liq import run_daily_net_liq
from portfolio_analysis.jobs.lock import JobLock, is_job_lock_held
from portfolio_analysis.jobs.registry import JOB_DATA_REFRESH
from portfolio_analysis.jobs.status import (
    strip_secrets,
    utc_now_iso,
    write_job_status,
)
from portfolio_analysis.paths import ensure_instance_home


def run_data_refresh(
    *,
    broker: str | None = None,
    force: bool = True,
    demo: bool = False,
    min_days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    allow_reconstruct: bool = True,
    on_insufficient: str = "partial",
    skip_net_liq: bool = False,
    maximize_history: bool = True,
    skip_lock: bool = False,
) -> dict[str, Any]:
    """Pull broker raw into local GT, then derive daily NLV from local DB.

    This is the product pipeline (not a broker passthrough):
    1. Sync remote → local raw/GT (as much as the API provides *now*)
    2. Derive/extend ``daily_account_net_liq`` from **local** raw (GT snapshots
       + reconstruction of every market day that can be justified)
    3. Return coverage-first guidance for clients

    Concurrent hourly and client-forced runs share flock ``data_refresh``;
    a second trigger returns ``already_running`` without double-writing.
    """
    ensure_instance_home()
    started = utc_now_iso()

    # Acquire data_refresh + family locks in fixed order so standalone
    # connector_sync / daily_net_liq cannot double-write during a pipeline run.
    from portfolio_analysis.jobs.registry import JOB_CONNECTOR_SYNC, JOB_DAILY_NET_LIQ

    held: list[JobLock] = []
    if not skip_lock:
        lock_ids = [JOB_DATA_REFRESH, JOB_CONNECTOR_SYNC]
        if not skip_net_liq:
            lock_ids.append(JOB_DAILY_NET_LIQ)
        for jid in lock_ids:
            lk = JobLock(jid)
            if not lk.try_acquire():
                for h in reversed(held):
                    h.release()
                payload = {
                    "job_id": JOB_DATA_REFRESH,
                    "ok": True,
                    "skipped": True,
                    "reason": "already_running",
                    "state": "skipped",
                    "started_at": started,
                    "finished_at": utc_now_iso(),
                    "lock_held": True,
                    "blocked_on": jid,
                    "pipeline": ["connector_sync", "daily_net_liq"],
                }
                payload = enrich_job_payload(JOB_DATA_REFRESH, payload)
                write_job_status(JOB_DATA_REFRESH, payload)
                return strip_secrets(payload)
            held.append(lk)

    try:
        # Sub-jobs use skip_lock: pipeline already holds family locks
        sync_kw: dict[str, Any] = {
            "force": force,
            "demo": demo,
            "skip_lock": True,
        }
        if broker:
            sync_kw["brokers"] = [broker]
        sync_res = run_connector_sync(**sync_kw)
        sync_pub = enrich_job_payload("connector_sync", sync_res.to_public_dict())

        # Local exports (statements / positions) already on disk often hold multi-month
        # NLV that live MCP never returns — seed GT equity before derive.
        export_seed_pub: dict[str, Any] | None = None
        try:
            from portfolio_analysis.jobs.export_equity_seed import (
                seed_equity_from_local_exports,
            )

            seed_res = seed_equity_from_local_exports()
            export_seed_pub = seed_res.to_public_dict()
        except Exception as exc:  # noqa: BLE001 — never block NLV derive on seed
            export_seed_pub = {"ok": False, "error": str(exc)}

        net_pub: dict[str, Any] | None = None
        if not skip_net_liq:
            net_kw: dict[str, Any] = {
                "force": True,
                "pre_sync": False,
                "allow_reconstruct": allow_reconstruct,
                "on_insufficient": on_insufficient or "partial",
                "demo": demo,
                "skip_lock": True,
                "maximize_history": maximize_history
                and start_date is None
                and min_days is None,
            }
            if broker:
                net_kw["broker"] = broker
            if min_days is not None:
                net_kw["min_days"] = int(min_days)
                net_kw["maximize_history"] = False
            if start_date:
                net_kw["start_date"] = start_date
                net_kw["maximize_history"] = False
            if end_date:
                net_kw["end_date"] = end_date
            net_res = run_daily_net_liq(**net_kw)
            net_pub = enrich_job_payload("daily_net_liq", net_res.to_public_dict())

        sync_ok = bool(sync_res.ok or sync_res.skipped)
        if skip_net_liq:
            overall_ok = sync_ok
            reason = sync_res.reason
            state = "ok" if overall_ok else "failed"
        else:
            net_ok = bool(net_pub and (net_pub.get("ok") or net_pub.get("skipped")))
            net_reason = (net_pub or {}).get("reason")
            overall_ok = sync_ok and net_ok
            if not sync_ok:
                reason = sync_res.reason or "sync_failed"
                state = "failed"
            elif net_reason in ("insufficient_history", "partial_coverage"):
                reason = net_reason
                state = "ok" if net_pub.get("ok") else "failed"
                overall_ok = bool(net_pub.get("ok"))
            elif overall_ok:
                state = "ok"
                reason = "completed"
            else:
                state = "failed"
                reason = net_reason or sync_res.reason or "failed"

        payload: dict[str, Any] = {
            "job_id": JOB_DATA_REFRESH,
            "ok": overall_ok,
            "skipped": False,
            "reason": reason,
            "state": state,
            "started_at": started,
            "finished_at": utc_now_iso(),
            "lock_held": False,
            "connector_sync": sync_pub,
            "export_equity_seed": export_seed_pub,
            "daily_net_liq": net_pub,
            "pipeline": (
                ["connector_sync", "export_equity_seed", "daily_net_liq"]
                if not skip_net_liq
                else ["connector_sync", "export_equity_seed"]
            ),
            "local_first": True,
            "maximize_history": maximize_history
            and start_date is None
            and min_days is None,
        }
        payload = enrich_job_payload(JOB_DATA_REFRESH, payload)
        write_job_status(JOB_DATA_REFRESH, payload)
        return strip_secrets(payload)
    finally:
        for h in reversed(held):
            h.release()


def is_data_refresh_running() -> bool:
    return is_job_lock_held(JOB_DATA_REFRESH)
