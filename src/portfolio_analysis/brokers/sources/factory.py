"""Resolve which live Schwab source to use (MCP vs direct API vs none)."""

from __future__ import annotations

import os
from typing import Any

from .base import BrokerLiveSource
from .direct_api import SchwabDirectApiLiveSource
from .mcp_transport import McpTransportConfig
from .schwab_mcp import SchwabMcpLiveSource


def resolve_schwab_live_source(
    *,
    mode: str | None = None,
    mcp_config: McpTransportConfig | None = None,
    direct_client: Any | None = None,
    use_connector_store: bool = True,
) -> BrokerLiveSource | None:
    """Choose a live source for the Schwab adapter.

    Preference order:
    1. Explicit ``mode`` argument
    2. Local connector config (``PORTFOLIO_ANALYSIS_HOME/connectors/schwab.json``)
    3. Environment (``SCHWAB_LIVE_SOURCE``, ``SCHWAB_MCP_URL``, client id/secret)

    Modes: ``mcp`` | ``direct`` | ``exports_only``/``none`` | ``auto``
    """
    # Connector store is the primary operator configuration surface.
    if (
        use_connector_store
        and mode is None
        and not os.environ.get("SCHWAB_LIVE_SOURCE")
    ):
        try:
            from portfolio_analysis.connectors.store import (
                load_connector,
                resolve_live_source_for_connector,
            )

            return resolve_live_source_for_connector(load_connector("schwab"))
        except Exception:
            pass

    chosen = (mode or os.environ.get("SCHWAB_LIVE_SOURCE") or "auto").strip().lower()
    if chosen in ("none", "off", "export", "exports", "exports_only"):
        return None
    if chosen == "mcp":
        return SchwabMcpLiveSource(mcp_config or McpTransportConfig.from_env())
    if chosen in ("direct", "api"):
        return SchwabDirectApiLiveSource(client=direct_client)
    if chosen != "auto":
        raise ValueError(
            f"Unknown SCHWAB_LIVE_SOURCE={chosen!r}; use mcp|direct|none|auto"
        )

    if os.environ.get("SCHWAB_MCP_URL") or os.environ.get("SCHWAB_MCP_COMMAND"):
        return SchwabMcpLiveSource(mcp_config or McpTransportConfig.from_env())
    if os.environ.get("SCHWAB_PREFER_MCP", "1").lower() not in ("0", "false", "no"):
        try:
            return SchwabMcpLiveSource(mcp_config or McpTransportConfig.from_env())
        except Exception:
            pass
    if os.environ.get("SCHWAB_CLIENT_ID") and os.environ.get("SCHWAB_CLIENT_SECRET"):
        return SchwabDirectApiLiveSource(client=direct_client)
    return None
