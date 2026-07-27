"""Multi-broker adapter registry and export layout."""

from __future__ import annotations


import pytest

from portfolio_analysis.brokers import (
    IbkrBrokerAdapter,
    SchwabBrokerAdapter,
    SyntheticBrokerAdapter,
    ensure_builtin_brokers_registered,
    get_adapter,
    list_registered_brokers,
)
from portfolio_analysis.paths import (
    broker_exports_dir,
    default_exports_dir,
    is_legacy_schwab_exports_layout,
    normalize_broker_id,
)


def test_normalize_broker_aliases():
    assert normalize_broker_id("Schwab") == "schwab"
    assert normalize_broker_id("TDA") == "schwab"
    assert normalize_broker_id("Interactive Brokers") == "ibkr"
    assert normalize_broker_id("RH") == "robinhood"


def test_builtin_registry_contains_expected_brokers():
    ensure_builtin_brokers_registered()
    names = {r.broker for r in list_registered_brokers()}
    assert {"synthetic", "schwab", "ibkr", "robinhood", "fidelity"} <= names


def test_get_adapter_synthetic_and_schwab(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path))
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_EXPORTS_DIR", raising=False)
    # Hermetic: no live MCP/API calls during unit tests
    monkeypatch.setenv("SCHWAB_LIVE_SOURCE", "exports_only")
    from portfolio_analysis.connectors import configure_connector

    configure_connector("schwab", mode="exports_only")
    ensure_builtin_brokers_registered()
    syn = get_adapter("synthetic")
    assert isinstance(syn, SyntheticBrokerAdapter)
    assert syn.list_accounts() == []

    schwab = get_adapter("schwab")
    assert isinstance(schwab, SchwabBrokerAdapter)
    assert schwab.exports_dir == broker_exports_dir("schwab")
    # exports_only: empty live feed, no fabricated accounts/snapshots
    assert list(schwab.list_accounts()) == []
    assert list(schwab.equity_snapshots("any")) == []


def test_planned_brokers_raise_not_implemented(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path))
    ibkr = get_adapter("ibkr")
    assert isinstance(ibkr, IbkrBrokerAdapter)
    assert ibkr.exports_dir == (tmp_path / "exports" / "ibkr").resolve()
    with pytest.raises(NotImplementedError):
        ibkr.list_accounts()


def test_exports_root_prefers_modern_exports(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path))
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_EXPORTS_DIR", raising=False)
    modern = tmp_path / "exports"
    modern.mkdir()
    legacy = tmp_path / "schwab-exports"
    legacy.mkdir()
    assert default_exports_dir() == modern.resolve()
    assert broker_exports_dir("schwab") == (modern / "schwab").resolve()
    assert broker_exports_dir("ibkr") == (modern / "ibkr").resolve()
    assert not is_legacy_schwab_exports_layout()


def test_exports_root_legacy_schwab_flat(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path))
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_EXPORTS_DIR", raising=False)
    legacy = tmp_path / "schwab-exports"
    legacy.mkdir()
    assert default_exports_dir() == legacy.resolve()
    assert is_legacy_schwab_exports_layout()
    # Schwab keeps using the flat legacy tree; other brokers never mix into it
    assert broker_exports_dir("schwab") == legacy.resolve()
    assert (
        broker_exports_dir("robinhood")
        == (tmp_path / "exports" / "robinhood").resolve()
    )


def test_new_install_defaults_to_exports_not_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path))
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_EXPORTS_DIR", raising=False)
    # Neither directory exists yet
    assert default_exports_dir() == (tmp_path / "exports").resolve()
    assert broker_exports_dir("schwab") == (tmp_path / "exports" / "schwab").resolve()
