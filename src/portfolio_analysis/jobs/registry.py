"""Job catalog: ids, schedules, handlers (MECE)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

JOB_CONNECTOR_SYNC = "connector_sync"
JOB_DAILY_NET_LIQ = "daily_net_liq"
JOB_DATA_REFRESH = "data_refresh"

# Hourly local-first pipeline (sync remote→GT then maximize local derive).
# Staggered fine-grained jobs remain invokable; scheduler prefers data_refresh.
DATA_REFRESH_CRON = {"minute": "5"}
CONNECTOR_SYNC_CRON = {"minute": "5"}
DAILY_NET_LIQ_CRON = {"minute": "35"}


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    description: str
    cron: dict[str, str]
    handler: str


def list_jobs() -> list[dict[str, Any]]:
    """Public job catalog (no secrets)."""
    return [
        {
            "job_id": JOB_DATA_REFRESH,
            "description": (
                "Local-first pipeline: sync broker→local GT, then maximize "
                "daily_account_net_liq from local raw (GT + reconstruction). "
                "Hourly default; same path for client force."
            ),
            "schedule": "hourly at :05",
            "cron": dict(DATA_REFRESH_CRON),
            "handler": "run_data_refresh",
            "params": [
                "force",
                "min_days",
                "start_date",
                "end_date",
                "allow_reconstruct",
                "on_insufficient",
                "maximize_history",
            ],
        },
        {
            "job_id": JOB_CONNECTOR_SYNC,
            "description": (
                "Sequential broker/account live sync → local GT only "
                "(accounts, positions, equity snapshots)"
            ),
            "schedule": "also via data_refresh :05 (standalone on demand)",
            "cron": dict(CONNECTOR_SYNC_CRON),
            "handler": "run_connector_sync",
        },
        {
            "job_id": JOB_DAILY_NET_LIQ,
            "description": (
                "Derive daily_account_net_liq from local GT + reconstruction; "
                "provenance audit; optional min_days sufficiency"
            ),
            "schedule": "also via data_refresh :05 (standalone on demand / :35 legacy)",
            "cron": dict(DAILY_NET_LIQ_CRON),
            "handler": "run_daily_net_liq",
            "params": [
                "min_days",
                "start_date",
                "end_date",
                "pre_sync",
                "allow_reconstruct",
                "on_insufficient",
                "maximize_history",
            ],
        },
    ]


def get_job_runner(job_id: str) -> Callable[..., Any]:
    """Return the shipped runner for ``job_id``."""
    if job_id == JOB_DATA_REFRESH:
        from .pipeline import run_data_refresh

        return run_data_refresh
    if job_id == JOB_CONNECTOR_SYNC:
        from .connector_sync import run_connector_sync

        return run_connector_sync
    if job_id == JOB_DAILY_NET_LIQ:
        from .daily_net_liq import run_daily_net_liq

        return run_daily_net_liq
    known = ", ".join(j["job_id"] for j in list_jobs())
    raise KeyError(f"unknown job_id {job_id!r}; known: {known}")
