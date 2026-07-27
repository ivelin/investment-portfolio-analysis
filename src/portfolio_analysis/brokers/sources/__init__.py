"""Live broker data sources (MCP, direct API, etc.).

Transports are pluggable so the same broker adapter can talk to:
- a local MCP/API process (e.g. schwab-mcp on 127.0.0.1)
- a remote MCP gateway URL
- an in-process direct HTTP API client
"""

from .base import BrokerLiveSource, LiveAccountEquity
from .factory import resolve_schwab_live_source
from .mcp_transport import McpTransportConfig, create_mcp_session

__all__ = [
    "BrokerLiveSource",
    "LiveAccountEquity",
    "McpTransportConfig",
    "create_mcp_session",
    "resolve_schwab_live_source",
]
