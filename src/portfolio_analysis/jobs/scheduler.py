"""Built-in APScheduler for continuous service mode only."""

from __future__ import annotations

import logging
from typing import Any

from .registry import (
    DAILY_NET_LIQ_CRON,
    DATA_REFRESH_CRON,
    JOB_DAILY_NET_LIQ,
    JOB_DATA_REFRESH,
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
    """Start BackgroundScheduler with hourly local-first data_refresh.

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

    def _run_refresh() -> None:
        """Hourly: sync remote→GT, then maximize every reconstructible local NLV day.

        Same pipeline as client-forced refresh_portfolio_data_tool. Does not pretend
        the broker returned multi-day history; series lengthens from local raw.
        """
        log.info("scheduled run: %s (sync→maximize local derive)", JOB_DATA_REFRESH)
        start_job(
            JOB_DATA_REFRESH,
            background=True,
            trigger="schedule",
            force=True,  # always attempt remote→GT feed; NLV still maximize_history
            maximize_history=True,
            allow_reconstruct=True,
            on_insufficient="partial",
        )

    def _run_net_liq_topup() -> None:
        """Mid-hour: re-derive only from local raw (no remote if refresh just ran)."""
        log.info("scheduled run: %s (local derive top-up)", JOB_DAILY_NET_LIQ)
        start_job(
            JOB_DAILY_NET_LIQ,
            background=True,
            trigger="schedule",
            force=True,
            pre_sync=False,
            maximize_history=True,
            allow_reconstruct=True,
            on_insufficient="partial",
        )

    sched.add_job(
        _run_refresh,
        CronTrigger(minute=DATA_REFRESH_CRON["minute"], timezone=timezone),
        id=JOB_DATA_REFRESH,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    sched.add_job(
        _run_net_liq_topup,
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
