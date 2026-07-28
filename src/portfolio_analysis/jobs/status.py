"""Durable job status (no secrets) under PORTFOLIO_ANALYSIS_HOME/jobs/."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from portfolio_analysis.paths import (
    ensure_instance_home,
    job_runs_dir,
    job_status_path,
    jobs_dir,
)

from .lock import is_job_lock_held

_STATUS_VERSION = 1
_SECRET_KEYS = (
    "client_secret",
    "client_id",
    "access_token",
    "refresh_token",
    "token",
    "apikey",
    "api_key",
    "password",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_id() -> str:
    return uuid.uuid4().hex


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique tmp name avoids races when multiple threads write the same path.
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def strip_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for bad in _SECRET_KEYS:
        out.pop(bad, None)
    # Nested scrub (one level)
    for k, v in list(out.items()):
        if isinstance(v, dict):
            for bad in _SECRET_KEYS:
                v.pop(bad, None)
    return out


def seconds_since(iso_ts: str | None) -> int | None:
    if not iso_ts:
        return None
    try:
        ts = str(iso_ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    except ValueError:
        return None


def write_run_status(run_id: str, payload: dict[str, Any]) -> Path:
    """Persist one run's status under jobs/runs/{run_id}.json."""
    ensure_instance_home()
    jobs_dir().mkdir(parents=True, exist_ok=True)
    out = job_runs_dir() / f"{run_id}.json"
    data = strip_secrets(dict(payload))
    data["run_id"] = run_id
    data["version"] = _STATUS_VERSION
    data["status_path"] = str(out)
    _atomic_write_json(out, data)
    return out


def load_run_status(run_id: str) -> dict[str, Any]:
    path = job_runs_dir() / f"{run_id}.json"
    base: dict[str, Any] = {
        "version": _STATUS_VERSION,
        "run_id": run_id,
        "exists": path.is_file(),
        "state": None,
        "ok": None,
        "status_path": str(path),
        "message": "run not found" if not path.is_file() else None,
    }
    if not path.is_file():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base["ok"] = False
        base["error"] = f"status unreadable: {exc}"
        return base
    if not isinstance(raw, dict):
        base["ok"] = False
        base["error"] = "status file is not an object"
        return base
    base.update(strip_secrets(raw))
    base["exists"] = True
    base["run_id"] = run_id
    base["status_path"] = str(path)
    base["message"] = None
    return base


def write_job_status(job_id: str, payload: dict[str, Any]) -> Path:
    """Persist last status for a job id (and preserve last_success)."""
    ensure_instance_home()
    jobs_dir().mkdir(parents=True, exist_ok=True)
    out = job_status_path(job_id)
    data = strip_secrets(dict(payload))
    data["job_id"] = job_id
    data["version"] = _STATUS_VERSION

    prev: dict[str, Any] = {}
    if out.is_file():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            if not isinstance(prev, dict):
                prev = {}
        except (OSError, json.JSONDecodeError):
            prev = {}

    state = data.get("state")
    ok = data.get("ok")
    skipped = data.get("skipped")
    if ok and not skipped and state in ("ok", "completed", None):
        data["last_success"] = {
            "finished_at": data.get("finished_at"),
            "started_at": data.get("started_at"),
            "run_id": data.get("run_id"),
            "reason": data.get("reason"),
            "summary": data.get("summary"),
        }
    elif prev.get("last_success"):
        data["last_success"] = prev["last_success"]

    data["status_path"] = str(out)
    data["lock_held"] = is_job_lock_held(job_id)
    _atomic_write_json(out, data)
    return out


def load_job_status(job_id: str) -> dict[str, Any]:
    """Load last recorded status for ``job_id``."""
    status_file = job_status_path(job_id)
    # Legacy connector_sync root file
    if job_id == "connector_sync":
        legacy = ensure_instance_home() / "sync_status.json"
        if not status_file.is_file() and legacy.is_file():
            status_file = legacy

    base: dict[str, Any] = {
        "version": _STATUS_VERSION,
        "job_id": job_id,
        "ok": None,
        "skipped": None,
        "reason": None,
        "state": None,
        "started_at": None,
        "finished_at": None,
        "lock_held": is_job_lock_held(job_id),
        "status_path": str(status_file),
        "exists": status_file.is_file(),
        "stale_seconds": None,
        "message": "no run recorded yet" if not status_file.is_file() else None,
    }
    if not status_file.is_file():
        return base
    try:
        raw = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base["ok"] = False
        base["error"] = f"status unreadable: {exc}"
        return base
    if not isinstance(raw, dict):
        base["ok"] = False
        base["error"] = "status file is not an object"
        return base
    base.update(strip_secrets(raw))
    base["exists"] = True
    base["job_id"] = job_id
    base["lock_held"] = is_job_lock_held(job_id)
    base["status_path"] = str(status_file)
    base["message"] = None
    success_at = None
    ls = base.get("last_success")
    if isinstance(ls, dict):
        success_at = ls.get("finished_at") or ls.get("started_at")
    finished = success_at or base.get("finished_at") or base.get("started_at")
    base["stale_seconds"] = seconds_since(
        finished if isinstance(finished, str) else None
    )
    for bad in _SECRET_KEYS:
        base.pop(bad, None)
    return base
