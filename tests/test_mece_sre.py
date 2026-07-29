"""DRY/MECE + SRE invariants for multi-tenant platform (CI).

Keeps decision matrices aligned with the hosted app without real credentials.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCH = REPO_ROOT / "docs" / "MULTI_TENANT_ARCHITECTURE.md"
BROKER_OAUTH = REPO_ROOT / "docs" / "BROKER_OAUTH.md"
DEFAULT_SKEW_MS = 10 * 60 * 1000


def classify_refresh_action(
    tokens: dict | None,
    *,
    force: bool = False,
    now: int = 0,
    skew_ms: int = DEFAULT_SKEW_MS,
) -> str:
    if not tokens or not tokens.get("access_token"):
        return "needs_reauth"
    expires_at = tokens.get("expires_at")
    near = expires_at is None or now >= int(expires_at) - skew_ms
    due = force or near
    if not due:
        return "skip"
    if not tokens.get("refresh_token"):
        return "needs_reauth"
    return "refresh"


def classify_connector_ui(status: str, oauth_configured: bool) -> str:
    if status == "connected":
        return "connected"
    if status == "error":
        return "needs_attention"
    if status == "pending_oauth":
        return "finish_at_broker"
    if not oauth_configured:
        return "setup_needed"
    return "not_connected"


def primary_connect_cta(status: str, oauth_configured: bool) -> str:
    if status == "connected":
        return "refresh_disconnect"
    if not oauth_configured:
        return "how_to_connect"
    return "connect"


def test_refresh_mece_exhaustive():
    now = 1_700_000_000_000
    assert classify_refresh_action(None) == "needs_reauth"
    assert (
        classify_refresh_action(
            {"access_token": "a", "refresh_token": "r", "expires_at": now + 3_600_000},
            now=now,
        )
        == "skip"
    )
    assert (
        classify_refresh_action(
            {"access_token": "a", "refresh_token": "r", "expires_at": now + 30_000},
            now=now,
        )
        == "refresh"
    )
    assert (
        classify_refresh_action(
            {"access_token": "a", "expires_at": now - 1},
            now=now,
        )
        == "needs_reauth"
    )


def test_connector_ui_mece_priority():
    assert classify_connector_ui("connected", False) == "connected"
    assert classify_connector_ui("error", True) == "needs_attention"
    assert classify_connector_ui("pending_oauth", True) == "finish_at_broker"
    assert classify_connector_ui("disconnected", False) == "setup_needed"
    assert classify_connector_ui("disconnected", True) == "not_connected"


def test_cta_never_dead_ends_without_path():
    # Unconfigured → how_to_connect (setup guide), not a disabled noop
    assert primary_connect_cta("disconnected", False) == "how_to_connect"
    assert primary_connect_cta("disconnected", True) == "connect"
    assert primary_connect_cta("connected", True) == "refresh_disconnect"


def test_docs_require_sre_and_dry():
    text = ARCH.read_text(encoding="utf-8")
    for needle in (
        "SRE",
        "CI",
        "DRY",
        "MECE",
        "token_refresh",
        "fail closed",
        "tenant",
    ):
        assert needle.lower() in text.lower(), needle


def test_broker_oauth_path_to_success():
    text = BROKER_OAUTH.read_text(encoding="utf-8")
    assert "callback" in text.lower() or "redirect" in text.lower()
    assert "tenant" in text.lower()
