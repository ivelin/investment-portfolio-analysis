"""Broker adapters that normalize accounts, equity snapshots, and cash flows.

Multi-broker rule: core never imports broker SDKs. Register adapters here and
resolve them via :func:`get_adapter`.
"""

from .base import (
    BrokerAdapter,
    CashFlow,
    EquitySnapshot,
    FundAccount,
)
from .fidelity import FidelityBrokerAdapter
from .ibkr import IbkrBrokerAdapter
from .registry import (
    BrokerRegistration,
    ensure_builtin_brokers_registered,
    get_adapter,
    get_broker_registration,
    list_registered_brokers,
    register_broker,
)
from .robinhood import RobinhoodBrokerAdapter
from .schwab import SchwabBrokerAdapter
from .synthetic import SyntheticBrokerAdapter

ensure_builtin_brokers_registered()

__all__ = [
    "BrokerAdapter",
    "BrokerRegistration",
    "CashFlow",
    "EquitySnapshot",
    "FidelityBrokerAdapter",
    "FundAccount",
    "IbkrBrokerAdapter",
    "RobinhoodBrokerAdapter",
    "SchwabBrokerAdapter",
    "SyntheticBrokerAdapter",
    "ensure_builtin_brokers_registered",
    "get_adapter",
    "get_broker_registration",
    "list_registered_brokers",
    "register_broker",
]
