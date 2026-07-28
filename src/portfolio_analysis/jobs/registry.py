"""Job catalog: ids, schedules, handlers (MECE)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

JOB_CONNECTOR_SYNC = "connector_sync"
JOB_DAILY_NET_LIQ = "daily_net_liq"

# Staggered hourly: sync at minute 5, net-liq at minute 35 (same hour cadence).
CONNECTOR_SYNC_CRON = {"minute": "5"}
DAILY_NET_LIQ_CRON = {"minute": "35"}


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    description: str
    # APScheduler trigger kwargs for CronTrigger (hour='*', minute=…)
    cron: dict[str, str]
    # Handler name for docs / list
    handler: str


def list_jobs() -> list[dict[str, Any]]:
    """Public job catalog (no secrets)."""
    return [
        {
            "job_id": JOB_CONNECTOR_SYNC,
            "description": (
                "Sequential broker/account live sync → local GT "
                "(accounts, positions, equity snapshots)"
            ),
            "schedule": "hourly at :05",
            "cron": dict(CONNECTOR_SYNC_CRON),
            "handler": "run_connector_sync",
        },
        {
            "job_id": JOB_DAILY_NET_LIQ,
            "description": (
                "Gap-fill daily_account_net_liq from local GT "
                "(market days only; live exact match for current snapshot)"
            ),
            "schedule": "hourly at :35 (staggered after connector_sync)",
            "cron": dict(DAILY_NET_LIQ_CRON),
            "handler": "run_daily_net_liq",
        },
    ]


def get_job_runner(job_id: str) -> Callable[..., Any]:
    """Return the shipped runner for ``job_id``."""
    if job_id == JOB_CONNECTOR_SYNC:
        from .connector_sync import run_connector_sync

        return run_connector_sync
    if job_id == JOB_DAILY_NET_LIQ:
        from .daily_net_liq import run_daily_net_liq

        return run_daily_net_liq
    known = ", ".join(j["job_id"] for j in list_jobs())
    raise KeyError(f"unknown job_id {job_id!r}; known: {known}")
