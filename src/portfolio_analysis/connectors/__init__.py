"""Configurable broker connectors with local secrets + OAuth.

Configs and credentials live under PORTFOLIO_ANALYSIS_HOME (never the git repo).
"""

from .oauth import oauth_complete, oauth_start, oauth_status
from .store import (
    ConnectorConfig,
    ConnectorStatus,
    configure_connector,
    get_connector,
    list_connectors,
    load_oauth_credentials,
    probe_connector,
    redact_connector,
)

# CLI/MCP-friendly alias (not collected as a pytest test)
test_connector = probe_connector

__all__ = [
    "ConnectorConfig",
    "ConnectorStatus",
    "configure_connector",
    "get_connector",
    "list_connectors",
    "load_oauth_credentials",
    "oauth_complete",
    "oauth_start",
    "oauth_status",
    "probe_connector",
    "redact_connector",
    "test_connector",
]
