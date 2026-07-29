"""Unified job start + durable run status (CLI / MCP / scheduler).

Long-running work returns quickly with a ``run_id`` when ``background=True``
so MCP clients that cannot stream can poll ``get_run_status``.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Any

from portfolio_analysis.paths import ensure_instance_home

from .client_messages import enrich_job_payload
from .registry import get_job_runner, list_jobs
from .status import (
    load_job_status,
    load_run_status,
    new_run_id,
    strip_secrets,
    utc_now_iso,
    write_job_status,
    write_run_status,
)

# In-process run tracking (continuous service)
_RUNS: dict[str, dict[str, Any]] = {}
_RUNS_LOCK = threading.Lock()


@dataclass
class StartResult:
    run_id: str
    job_id: str
    state: str  # pending | running | ok | failed | skipped
    ok: bool | None = None
    skipped: bool | None = None
    reason: str | None = None
    background: bool = False
    result: dict[str, Any] | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return strip_secrets(asdict(self))


def _normalize_result(job_id: str, raw: Any) -> dict[str, Any]:
    if hasattr(raw, "to_public_dict"):
        d = raw.to_public_dict()
    elif isinstance(raw, dict):
        d = strip_secrets(raw)
    else:
        d = {"raw": str(raw)}
    d.setdefault("job_id", job_id)
    return d


def _execute_job(job_id: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    runner = get_job_runner(job_id)
    raw = runner(**kwargs)
    return _normalize_result(job_id, raw)


def start_job(
    job_id: str,
    *,
    background: bool = False,
    trigger: str = "cli",
    **kwargs: Any,
) -> dict[str, Any]:
    """Start a registered job. If background, return immediately with run_id."""
    ensure_instance_home()
    # Validate job exists
    get_job_runner(job_id)
    run_id = new_run_id()
    started = utc_now_iso()
    base = {
        "run_id": run_id,
        "job_id": job_id,
        "state": "pending",
        "ok": None,
        "skipped": None,
        "reason": None,
        "started_at": started,
        "finished_at": None,
        "trigger": trigger,
        "background": background,
    }
    write_run_status(run_id, base)
    with _RUNS_LOCK:
        _RUNS[run_id] = dict(base)

    def _finish(payload: dict[str, Any]) -> None:
        write_run_status(run_id, payload)
        # Mirror latest onto job status when terminal
        if payload.get("state") in ("ok", "failed", "skipped"):
            write_job_status(job_id, {**payload, "run_id": run_id})
        with _RUNS_LOCK:
            _RUNS[run_id] = dict(payload)

    if not background:
        running = {**base, "state": "running"}
        write_run_status(run_id, running)
        try:
            result = _execute_job(job_id, kwargs)
            state = (
                "skipped"
                if result.get("skipped")
                else ("ok" if result.get("ok", True) else "failed")
            )
            finished = {
                **base,
                "state": state,
                "ok": result.get("ok"),
                "skipped": result.get("skipped"),
                "reason": result.get("reason"),
                "finished_at": utc_now_iso(),
                "result": result,
                "summary": result.get("summary"),
            }
            finished = enrich_job_payload(job_id, finished)
            _finish(finished)
            return strip_secrets(finished)
        except Exception as exc:  # noqa: BLE001
            finished = {
                **base,
                "state": "failed",
                "ok": False,
                "reason": "exception",
                "error": str(exc),
                "finished_at": utc_now_iso(),
                "message": f"Job {job_id} raised: {exc}",
                "next_steps": [
                    "Read the error string (no secrets should appear).",
                    "Retry jobs_run_tool with force=true, or refresh_portfolio_data_tool.",
                    "Check journalctl --user -u portfolio-analysis for stack traces.",
                ],
            }
            _finish(finished)
            return strip_secrets(finished)

    # Background thread for MCP / service async
    def _worker() -> None:
        running = {**base, "state": "running"}
        write_run_status(run_id, running)
        with _RUNS_LOCK:
            _RUNS[run_id] = dict(running)
        try:
            result = _execute_job(job_id, kwargs)
            state = (
                "skipped"
                if result.get("skipped")
                else ("ok" if result.get("ok", True) else "failed")
            )
            finished = {
                **base,
                "state": state,
                "ok": result.get("ok"),
                "skipped": result.get("skipped"),
                "reason": result.get("reason"),
                "finished_at": utc_now_iso(),
                "result": result,
                "summary": result.get("summary"),
            }
            finished = enrich_job_payload(job_id, finished)
            _finish(finished)
        except Exception as exc:  # noqa: BLE001
            finished = {
                **base,
                "state": "failed",
                "ok": False,
                "reason": "exception",
                "error": str(exc),
                "finished_at": utc_now_iso(),
                "message": f"Job {job_id} raised: {exc}",
                "next_steps": [
                    "Read the error string.",
                    "Retry with force=true or refresh_portfolio_data_tool.",
                ],
            }
            _finish(finished)

    t = threading.Thread(target=_worker, name=f"job-{job_id}-{run_id[:8]}", daemon=True)
    t.start()
    pending = {
        **base,
        "state": "running",
        "message": (
            f"Job {job_id} started (run_id={run_id}). "
            "Poll jobs_status_tool(run_id=...) until state is ok|failed|skipped. "
            "Do not assume long history exists until daily_net_liq coverage says so."
        ),
        "next_steps": [
            f"Call jobs_status_tool(run_id='{run_id}') until finished_at is set.",
            "If this was connector_sync, next run daily_net_liq or use refresh_portfolio_data_tool.",
        ],
    }
    write_run_status(run_id, pending)
    return strip_secrets(pending)


def get_run_status(
    run_id: str | None = None, job_id: str | None = None
) -> dict[str, Any]:
    """Status by run_id and/or last status for job_id."""
    if run_id:
        return load_run_status(run_id)
    if job_id:
        return load_job_status(job_id)
    # Both none → list all known jobs' last status
    return {"jobs": list_job_statuses()}


def list_job_statuses() -> list[dict[str, Any]]:
    out = []
    for j in list_jobs():
        st = load_job_status(j["job_id"])
        out.append(
            {
                "job_id": j["job_id"],
                "schedule": j.get("schedule"),
                "description": j.get("description"),
                "last_state": st.get("state"),
                "ok": st.get("ok"),
                "skipped": st.get("skipped"),
                "reason": st.get("reason"),
                "finished_at": st.get("finished_at"),
                "stale_seconds": st.get("stale_seconds"),
                "lock_held": st.get("lock_held"),
                "exists": st.get("exists"),
            }
        )
    return out


def wait_job(
    run_id: str, *, timeout_s: float = 120.0, poll_s: float = 0.05
) -> dict[str, Any]:
    """Poll until terminal state or timeout (tests)."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = load_run_status(run_id)
        if st.get("state") in ("ok", "failed", "skipped") and st.get("finished_at"):
            return st
        time.sleep(poll_s)
    st = load_run_status(run_id)
    st["message"] = "timeout waiting for job"
    return st


def run_job_sync(job_id: str, **kwargs: Any) -> dict[str, Any]:
    """Foreground run (CLI default)."""
    return start_job(job_id, background=False, **kwargs)
