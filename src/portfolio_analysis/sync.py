"""Back-compat facade for continuous connector sync.

Prefer :mod:`portfolio_analysis.jobs.connector_sync` and the unified
``portfolio jobs`` / MCP ``jobs_*`` tools for new code.
"""

from portfolio_analysis.jobs.connector_sync import (
    BrokerSyncResult,
    SyncRunResult,
    format_sync_result_json,
    is_sync_lock_held,
    load_sync_status,
    run_connector_sync,
    run_sync,
    sync_broker_to_gt,
)
from portfolio_analysis.jobs.lock import JobLock as SyncLock

__all__ = [
    "BrokerSyncResult",
    "SyncLock",
    "SyncRunResult",
    "format_sync_result_json",
    "is_sync_lock_held",
    "load_sync_status",
    "run_connector_sync",
    "run_sync",
    "sync_broker_to_gt",
]
