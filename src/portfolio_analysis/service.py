"""Continuous portfolio-analysis service: scheduler + optional MCP transports.

This is the boot-surviving process. One-shot CLI commands must not import-start
the scheduler; only this module (and ``portfolio serve``) enables it.

Usage:
    python -m portfolio_analysis.service
    python -m portfolio_analysis.service --mcp-http --port 3460
    portfolio serve --mcp-http
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from typing import Any

log = logging.getLogger("portfolio_analysis.service")


def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run_service(
    *,
    mcp_http: bool = False,
    mcp_stdio: bool = False,
    host: str = "0.0.0.0",
    port: int = 3460,
    timezone: str = "America/Chicago",
    enable_scheduler: bool = True,
) -> int:
    """Start continuous service. Blocks until SIGINT/SIGTERM."""
    from portfolio_analysis.paths import ensure_instance_home

    ensure_instance_home()

    if enable_scheduler:
        from portfolio_analysis.jobs.scheduler import (
            scheduled_job_ids,
            scheduler_status,
            start_scheduler,
        )

        start_scheduler(timezone=timezone)
        st = scheduler_status()
        log.info(
            "continuous service up scheduler_jobs=%s catalog=%s",
            scheduled_job_ids(),
            [(j["job_id"], j["schedule"]) for j in st.get("catalog") or []],
        )
        print(
            f"portfolio-analysis service: scheduler ON; jobs={scheduled_job_ids()}",
            flush=True,
        )
        for j in st.get("catalog") or []:
            print(
                f"  registered job: {j['job_id']} schedule={j['schedule']}",
                flush=True,
            )
    else:
        print("portfolio-analysis service: scheduler OFF", flush=True)

    stop = threading.Event()

    def _shutdown(*_args: Any) -> None:
        log.info("shutdown signal")
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    http_thread: threading.Thread | None = None
    if mcp_http:
        from portfolio_analysis import mcp_server

        def _http() -> None:
            if hasattr(mcp_server.mcp, "settings"):
                mcp_server.mcp.settings.host = host
                mcp_server.mcp.settings.port = port
            log.info("MCP HTTP on %s:%s", host, port)
            print(f"MCP Streamable HTTP on {host}:{port}", flush=True)
            mcp_server.mcp.run(transport="streamable-http")

        http_thread = threading.Thread(target=_http, name="mcp-http", daemon=True)
        http_thread.start()

    if mcp_stdio:
        # stdio MCP in a child thread is awkward (stdin); only valid when this
        # process is dedicated. Prefer HTTP for multi-client. Still allowed.
        from portfolio_analysis import mcp_server

        def _stdio() -> None:
            log.info("MCP stdio transport")
            mcp_server.mcp.run()

        t = threading.Thread(target=_stdio, name="mcp-stdio", daemon=True)
        t.start()

    if not mcp_http and not mcp_stdio:
        print(
            "Service running (scheduler only). "
            "Pass --mcp-http and/or --mcp-stdio to expose MCP tools.",
            flush=True,
        )

    try:
        while not stop.is_set():
            stop.wait(1.0)
    finally:
        if enable_scheduler:
            from portfolio_analysis.jobs.scheduler import stop_scheduler

            stop_scheduler()
            log.info("scheduler stopped")
        print("portfolio-analysis service stopped", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Continuous portfolio-analysis service (scheduler + optional MCP)"
    )
    parser.add_argument(
        "--mcp-http",
        action="store_true",
        help="Expose MCP tools over Streamable HTTP",
    )
    parser.add_argument(
        "--mcp-stdio",
        action="store_true",
        help="Expose MCP tools over stdio (same process)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="HTTP bind host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "3460")),
        help="HTTP bind port",
    )
    parser.add_argument(
        "--timezone",
        default=os.environ.get("PORTFOLIO_ANALYSIS_TZ", "America/Chicago"),
        help="Scheduler timezone",
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Disable built-in scheduler (MCP-only continuous process)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    return run_service(
        mcp_http=args.mcp_http,
        mcp_stdio=args.mcp_stdio,
        host=args.host,
        port=args.port,
        timezone=args.timezone,
        enable_scheduler=not args.no_scheduler,
    )


if __name__ == "__main__":
    # Quick path for tests: PORTFOLIO_ANALYSIS_SERVICE_SMOKE=1 exits after start
    if os.environ.get("PORTFOLIO_ANALYSIS_SERVICE_SMOKE") == "1":
        _configure_logging(True)
        from portfolio_analysis.jobs.scheduler import (
            scheduled_job_ids,
            scheduler_status,
            start_scheduler,
            stop_scheduler,
        )
        from portfolio_analysis.paths import ensure_instance_home

        ensure_instance_home()
        start_scheduler()
        st = scheduler_status()
        print("SMOKE scheduler started", flush=True)
        print(f"SMOKE job_ids={scheduled_job_ids()}", flush=True)
        for j in st.get("catalog") or []:
            print(f"SMOKE catalog {j['job_id']} {j['schedule']}", flush=True)
        stop_scheduler()
        print("SMOKE ok", flush=True)
        sys.exit(0)
    sys.exit(main())
