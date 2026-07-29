"""Generic MCP client transport: local HTTP, remote HTTP, or stdio.

Used by broker live sources so portfolio-analysis never hard-codes a single
deployment shape for schwab-mcp / future broker MCPs.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


@dataclass(frozen=True)
class McpTransportConfig:
    """How to reach an MCP server.

    Exactly one of ``url`` (streamable HTTP) or ``command`` (stdio) should be set.
    """

    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    tool_prefix: str = ""  # e.g. "" or "schwab_mcp_unified__"
    timeout_s: float = 60.0

    @classmethod
    def from_env(
        cls,
        *,
        url_var: str = "SCHWAB_MCP_URL",
        command_var: str = "SCHWAB_MCP_COMMAND",
        prefix_var: str = "SCHWAB_MCP_TOOL_PREFIX",
        default_url: str | None = "http://127.0.0.1:3473/mcp",
        auth_header_var: str = "SCHWAB_MCP_AUTH_HEADER",
        apikey_var: str = "SCHWAB_MCP_KEY",
    ) -> McpTransportConfig:
        """Build config from environment (local default URL if unset)."""
        url = os.environ.get(url_var) or default_url
        command = os.environ.get(command_var) or None
        prefix = os.environ.get(prefix_var, "")
        headers: dict[str, str] = {}
        auth = os.environ.get(auth_header_var)
        if auth:
            headers["Authorization"] = auth
        apikey = os.environ.get(apikey_var)
        if apikey and url:
            # Gateway style: ?apikey=… (also works for local if ignored)
            url = _append_query(url, {"apikey": apikey})
        if command:
            parts = command.split()
            return cls(
                url=None,
                command=parts[0],
                args=tuple(parts[1:]),
                headers=headers,
                tool_prefix=prefix,
            )
        if not url:
            raise ValueError(
                f"Set {url_var} (HTTP MCP) or {command_var} (stdio MCP command)"
            )
        return cls(url=url, headers=headers, tool_prefix=prefix)


def _append_query(url: str, extra: Mapping[str, str]) -> str:
    parts = urlparse(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update(extra)
    return urlunparse(parts._replace(query=urlencode(q)))


@asynccontextmanager
async def create_mcp_session(
    config: McpTransportConfig,
) -> AsyncIterator[Any]:
    """Yield an initialized MCP ClientSession for HTTP or stdio transport."""
    try:
        from mcp import ClientSession
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "mcp package required for MCP live sources; install with: "
            'uv pip install -e ".[mcp]"'
        ) from exc

    if config.url:
        try:
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "mcp client streamable_http transport unavailable"
            ) from exc

        # httpx headers via optional kwargs depending on mcp version
        async with streamable_http_client(config.url) as streams:
            # streams may be (read, write) or (read, write, _)
            if len(streams) == 2:
                read, write = streams
            else:
                read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    if config.command:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=config.command,
            args=list(config.args),
            env=dict(config.env) if config.env else None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    raise ValueError("McpTransportConfig requires url or command")


def _run_coro_sync(coro: Any) -> Any:
    """Run an async coroutine from sync code, even inside a running event loop.

    ``asyncio.run()`` raises if the portfolio-analysis MCP HTTP server (or any
    async host) already has a loop. In that case run the coroutine on a fresh
    loop in a worker thread so connector_sync / jobs_run still work.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    def _in_thread() -> Any:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_in_thread).result()


def call_mcp_tool_sync(
    config: McpTransportConfig,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
) -> Any:
    """Synchronously call one MCP tool and return parsed content."""

    async def _run() -> Any:
        async with create_mcp_session(config) as session:
            full_name = f"{config.tool_prefix}{tool_name}"
            result = await session.call_tool(full_name, dict(arguments or {}))
            return _extract_tool_payload(result)

    return _run_coro_sync(_run())


def list_mcp_tools_sync(config: McpTransportConfig) -> Sequence[str]:
    """Return tool names exposed by the MCP server."""

    async def _run() -> list[str]:
        async with create_mcp_session(config) as session:
            tools = await session.list_tools()
            return [t.name for t in tools.tools]

    return _run_coro_sync(_run())


def _extract_tool_payload(result: Any) -> Any:
    """Normalize MCP CallToolResult into JSON-ish Python objects."""
    content = getattr(result, "content", None) or []
    texts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            texts.append(text)
        elif isinstance(block, dict) and "text" in block:
            texts.append(str(block["text"]))
    if not texts:
        # Some servers put structured content on result.structuredContent
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured
        return None
    blob = "\n".join(texts).strip()
    if not blob:
        return None
    return _parse_jsonish(blob)


def _parse_jsonish(blob: str) -> Any:
    """Parse a single JSON value, NDJSON, or concatenated JSON values."""
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx = 0
    items: list[Any] = []
    n = len(blob)
    while idx < n:
        while idx < n and blob[idx].isspace():
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(blob, idx)
        except json.JSONDecodeError:
            return blob
        items.append(obj)
        idx = end
    if not items:
        return blob
    if len(items) == 1:
        return items[0]
    return items
