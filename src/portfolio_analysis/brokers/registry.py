"""Broker adapter registry (multi-broker entry point).

Core fund/TWRR code should depend on :class:`BrokerAdapter` + this registry,
never on broker SDKs or export formats directly.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from portfolio_analysis.paths import normalize_broker_id

from .base import BrokerAdapter

AdapterFactory = Callable[..., BrokerAdapter]


@dataclass(frozen=True)
class BrokerRegistration:
    """Metadata for a registered broker adapter."""

    broker: str
    factory: AdapterFactory
    status: str  # "ready" | "export_path" | "planned"
    description: str = ""


_REGISTRY: dict[str, BrokerRegistration] = {}


def register_broker(
    broker: str,
    factory: AdapterFactory,
    *,
    status: str = "planned",
    description: str = "",
    replace: bool = False,
) -> None:
    """Register (or replace) an adapter factory for ``broker``."""
    bid = normalize_broker_id(broker)
    if bid in _REGISTRY and not replace:
        raise ValueError(f"broker already registered: {bid}")
    _REGISTRY[bid] = BrokerRegistration(
        broker=bid,
        factory=factory,
        status=status,
        description=description,
    )


def unregister_broker(broker: str) -> None:
    """Remove a registration (tests)."""
    _REGISTRY.pop(normalize_broker_id(broker), None)


def clear_registry() -> None:
    """Drop all registrations (tests)."""
    _REGISTRY.clear()


def list_registered_brokers() -> Sequence[BrokerRegistration]:
    """Return registrations sorted by broker id."""
    return tuple(sorted(_REGISTRY.values(), key=lambda r: r.broker))


def get_broker_registration(broker: str) -> BrokerRegistration:
    bid = normalize_broker_id(broker)
    if bid not in _REGISTRY:
        known = ", ".join(r.broker for r in list_registered_brokers()) or "(none)"
        raise KeyError(f"unknown broker {bid!r}; registered: {known}")
    return _REGISTRY[bid]


def get_adapter(broker: str, **kwargs: Any) -> BrokerAdapter:
    """Construct an adapter for ``broker`` (may be planned / incomplete)."""
    reg = get_broker_registration(broker)
    return reg.factory(**kwargs)


def ensure_builtin_brokers_registered() -> None:
    """Idempotently register built-in adapters (safe to call many times)."""
    from .fidelity import FidelityBrokerAdapter
    from .ibkr import IbkrBrokerAdapter
    from .robinhood import RobinhoodBrokerAdapter
    from .schwab import SchwabBrokerAdapter
    from .synthetic import SyntheticBrokerAdapter

    builtins: list[tuple[str, AdapterFactory, str, str]] = [
        (
            "synthetic",
            SyntheticBrokerAdapter,
            "ready",
            "In-memory demo/test broker (no real balances)",
        ),
        (
            "schwab",
            lambda **kw: (
                SchwabBrokerAdapter(**kw)
                if kw
                else SchwabBrokerAdapter.from_connector()
            ),
            "live_capable",
            "Schwab: local/remote MCP or direct OAuth API via connectors config",
        ),
        (
            "ibkr",
            IbkrBrokerAdapter,
            "planned",
            "Interactive Brokers (adapter stub)",
        ),
        (
            "robinhood",
            RobinhoodBrokerAdapter,
            "planned",
            "Robinhood (adapter stub)",
        ),
        (
            "fidelity",
            FidelityBrokerAdapter,
            "planned",
            "Fidelity (adapter stub)",
        ),
    ]
    for broker, factory, status, desc in builtins:
        if broker not in _REGISTRY:
            register_broker(broker, factory, status=status, description=desc)
