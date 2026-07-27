"""Connector store, OAuth helpers, and Schwab adapter wiring (hermetic)."""

from __future__ import annotations

import json

import pytest

from portfolio_analysis.brokers.schwab import SchwabBrokerAdapter
from portfolio_analysis.brokers.sources.base import LiveAccountEquity
from portfolio_analysis.brokers.sources.schwab_mcp import (
    parse_schwab_accounts_payload,
    stable_account_key,
)
from portfolio_analysis.connectors import (
    configure_connector,
    get_connector,
    oauth_start,
    redact_connector,
    probe_connector,
)
from portfolio_analysis.connectors.store import (
    load_oauth_credentials,
    resolve_live_source_for_connector,
)


@pytest.fixture()
def instance_home(tmp_path, monkeypatch):
    home = tmp_path / "inst"
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(home))
    monkeypatch.delenv("SCHWAB_CLIENT_ID", raising=False)
    monkeypatch.delenv("SCHWAB_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SCHWAB_LIVE_SOURCE", raising=False)
    monkeypatch.delenv("SCHWAB_MCP_URL", raising=False)
    return home


def test_configure_stores_config_and_secrets_outside_repo(instance_home):
    cfg = configure_connector(
        "schwab",
        mode="mcp",
        mcp_url="http://127.0.0.1:3473/mcp",
        client_id="app-key",
        client_secret="app-secret",
    )
    assert cfg.mode == "mcp"
    conf_path = instance_home / "connectors" / "schwab.json"
    sec_path = instance_home / "secrets" / "schwab_oauth.json"
    assert conf_path.is_file()
    assert sec_path.is_file()
    # secrets not world-readable
    assert (sec_path.stat().st_mode & 0o077) == 0
    raw_conf = json.loads(conf_path.read_text())
    assert "client_secret" not in raw_conf
    assert raw_conf["mcp_url"] == "http://127.0.0.1:3473/mcp"
    creds = load_oauth_credentials("schwab")
    assert creds["client_id"] == "app-key"
    assert creds["client_secret"] == "app-secret"
    red = redact_connector(cfg)
    assert red["secrets_present"] is True
    assert "app-secret" not in json.dumps(red)


def test_exports_only_probe_connector(instance_home):
    configure_connector("schwab", mode="exports_only")
    result = probe_connector("schwab")
    assert result["ok"] is True
    assert result["live_source"] is None


def test_parse_schwab_accounts_payload():
    payload = [
        {
            "securitiesAccount": {
                "type": "MARGIN",
                "accountNumber": "123",
                "accountHash": "HASHVALUE123",
                "nickname": "IRA",
                "currentBalances": {
                    "liquidationValue": 1000.5,
                    "cashBalance": 50.0,
                },
            }
        }
    ]
    rows = parse_schwab_accounts_payload(payload)
    assert len(rows) == 1
    assert rows[0].display_name == "IRA"
    assert rows[0].liquidation_value == 1000.5
    assert rows[0].account_key == stable_account_key("HASHVALUE123")


class _FakeLive:
    name = "fake"

    def fetch_account_equities(self):
        return [
            LiveAccountEquity(
                broker="schwab",
                account_key="abc",
                display_name="Demo",
                broker_account_ref="HASH",
                as_of_date="2026-07-27",
                liquidation_value=42.0,
                cash=1.0,
                source="fake",
            )
        ]


def test_schwab_adapter_uses_live_source(instance_home):
    adapter = SchwabBrokerAdapter(live_source=_FakeLive(), use_connector=False)
    accts = adapter.list_accounts()
    assert len(accts) == 1
    assert accts[0].account_key == "abc"
    snaps = adapter.equity_snapshots("abc")
    assert len(snaps) == 1
    assert snaps[0].liquidation_value == 42.0


def test_resolve_live_source_mcp_from_connector(instance_home, monkeypatch):
    configure_connector("schwab", mode="mcp", mcp_url="http://127.0.0.1:9/mcp")
    cfg = get_connector("schwab")
    src = resolve_live_source_for_connector(cfg)
    assert src is not None
    assert src.name == "schwab_mcp"


def test_oauth_start_requires_credentials(instance_home):
    configure_connector("schwab", mode="direct")
    with pytest.raises(ValueError, match="client_id"):
        oauth_start("schwab")


def test_oauth_start_with_credentials(instance_home, monkeypatch):
    configure_connector(
        "schwab",
        mode="direct",
        client_id="id",
        client_secret="secret",
        redirect_uri="https://127.0.0.1:8080/callback",
    )
    # Do not hit network — mock auth URL generation
    from portfolio_analysis.schwab import auth as schwab_auth

    def fake_url(self):
        return "https://example.com/auth", "verifier-xyz"

    monkeypatch.setattr(schwab_auth.SchwabAuth, "get_authorization_url", fake_url)
    out = oauth_start("schwab")
    assert out["authorization_url"].startswith("https://")
    assert out["code_verifier"] == "verifier-xyz"
    pending = instance_home / "secrets" / "schwab_oauth_pending.json"
    assert pending.is_file()
