"""MCP transport must work from sync code even inside a running event loop."""

from __future__ import annotations

import asyncio

from portfolio_analysis.brokers.sources.mcp_transport import _run_coro_sync


def test_run_coro_sync_without_running_loop():
    async def _mul(a: int, b: int) -> int:
        return a * b

    assert _run_coro_sync(_mul(4, 5)) == 20


def test_run_coro_sync_from_running_loop():
    """Reproduce connector_sync failure: asyncio.run nested in running loop."""

    async def _add(a: int, b: int) -> int:
        await asyncio.sleep(0)
        return a + b

    async def _host() -> int:
        # Nested: already on a loop (same as FastMCP HTTP tool handler)
        return _run_coro_sync(_add(2, 3))

    assert asyncio.run(_host()) == 5


def test_call_mcp_tool_sync_path_does_not_use_bare_asyncio_run():
    """Structural: shipped helper is used by call_mcp_tool_sync."""
    import inspect

    from portfolio_analysis.brokers.sources import mcp_transport as mt

    src = inspect.getsource(mt.call_mcp_tool_sync)
    assert "_run_coro_sync" in src
    assert "asyncio.run(_run())" not in src.replace(" ", "")
