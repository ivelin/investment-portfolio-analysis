"""Built-in APScheduler for continuous service mode only."""

from __future__ import annotations

import logging
from typing import Any

from .registry import (
    CONNECTOR_SYNC_CRON,
    DAILY_NET_LIQ_CRON,
    JOB_CONNECTOR_SYNC,
    JOB_DAILY_NET_LIQ,
    list_jobs,
)
from .runner import start_job

log = logging.getLogger("portfolio_analysis.jobs.scheduler")

_scheduler: Any | None = None
_started = False


def scheduler_started() -> bool:
    return _started


def get_scheduler() -> Any | None:
    return _scheduler


def scheduled_job_ids() -> list[str]:
    if _scheduler is None:
        return []
    try:
        return [j.id for j in _scheduler.get_jobs()]
    except Exception:
        return []


def start_scheduler(*, timezone: str = "America/Chicago") -> Any:
    """Start BackgroundScheduler with both staggered hourly jobs.

    Safe to call once per process. Raises if APScheduler is not installed.
    """
    global _scheduler, _started
    if _started and _scheduler is not None:
        return _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError(
            "APScheduler required for continuous service: "
            "uv pip install 'portfolio-analysis[service]' or apscheduler"
        ) from exc

    sched = BackgroundScheduler(timezone=timezone)

    def _run_connector() -> None:
        log.info("scheduled run: %s", JOB_CONNECTOR_SYNC)
        start_job(
            JOB_CONNECTOR_SYNC,
            background=True,
            trigger="schedule",
            force=False,
        )

    def _run_net_liq() -> None:
        log.info("scheduled run: %s", JOB_DAILY_NET_LIQ)
        start_job(
            JOB_DAILY_NET_LIQ,
            background=True,
            trigger="schedule",
            force=False,
        )

    sched.add_job(
        _run_connector,
        CronTrigger(minute=CONNECTOR_SYNC_CRON["minute"], timezone=timezone),
        id=JOB_CONNECTOR_SYNC,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    sched.add_job(
        _run_net_liq,
        CronTrigger(minute=DAILY_NET_LIQ_CRON["minute"], timezone=timezone),
        id=JOB_DAILY_NET_LIQ,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    sched.start()
    _scheduler = sched
    _started = True
    jobs = list_jobs()
    log.info(
        "scheduler started tz=%s jobs=%s",
        timezone,
        [(j["job_id"], j["schedule"]) for j in jobs],
    )
    return sched


def stop_scheduler() -> None:
    global _scheduler, _started
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    _scheduler = None
    _started = False


def scheduler_status() -> dict[str, Any]:
    jobs_info = []
    if _scheduler is not None:
        for j in _scheduler.get_jobs():
            jobs_info.append(
                {
                    "id": j.id,
                    "next_run_time": str(j.next_run_time) if j.next_run_time else None,
                    "trigger": str(j.trigger),
                }
            )
    return {
        "started": _started,
        "jobs": jobs_info,
        "catalog": list_jobs(),
    }
