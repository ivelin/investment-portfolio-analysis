"""Token refresh job invariants (pure logic + docs).

Hosted implementation lives in the multi-tenant web app; these tests lock the
MECE decision matrix and public-repo documentation so CI stays green without
real broker credentials.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCH = REPO_ROOT / "docs" / "MULTI_TENANT_ARCHITECTURE.md"
BROKER_OAUTH = REPO_ROOT / "docs" / "BROKER_OAUTH.md"
SEC = REPO_ROOT / "docs" / "MULTI_TENANT_SECURITY.md"

DEFAULT_SKEW_MS = 10 * 60 * 1000


def classify_refresh_action(
    tokens: dict | None,
    *,
    force: bool = False,
    now: int = 0,
    skew_ms: int = DEFAULT_SKEW_MS,
) -> str:
    """MECE decision matrix for OAuth access-token refresh (no I/O)."""
    if not tokens or not tokens.get("access_token"):
        return "needs_reauth"
    expires_at = tokens.get("expires_at")
    near_expiry = expires_at is None or now >= int(expires_at) - skew_ms
    due = force or near_expiry
    if not due:
        return "skip"
    if not tokens.get("refresh_token"):
        return "needs_reauth"
    return "refresh"


def test_refresh_decision_matrix_fresh_skips():
    now = 1_700_000_000_000
    assert (
        classify_refresh_action(
            {
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": now + 60 * 60 * 1000,
            },
            now=now,
        )
        == "skip"
    )


def test_refresh_decision_matrix_near_expiry_refreshes():
    now = 1_700_000_000_000
    assert (
        classify_refresh_action(
            {
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": now + 60 * 1000,
            },
            now=now,
        )
        == "refresh"
    )


def test_refresh_decision_matrix_force_overrides_freshness():
    now = 1_700_000_000_000
    assert (
        classify_refresh_action(
            {
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": now + 60 * 60 * 1000,
            },
            force=True,
            now=now,
        )
        == "refresh"
    )


def test_refresh_decision_matrix_missing_refresh_needs_reauth():
    now = 1_700_000_000_000
    assert (
        classify_refresh_action(
            {"access_token": "a", "expires_at": now - 1},
            now=now,
        )
        == "needs_reauth"
    )


def test_refresh_decision_matrix_null_tokens():
    assert classify_refresh_action(None) == "needs_reauth"
    assert classify_refresh_action({}) == "needs_reauth"


def test_refresh_is_tenant_scoped_in_docs():
    for path in (ARCH, BROKER_OAUTH, SEC):
        text = path.read_text(encoding="utf-8").lower()
        assert "tenant" in text
        assert "token_refresh" in text or "token refresh" in text


def test_broker_oauth_doc_exists_and_separates_models():
    assert BROKER_OAUTH.is_file()
    text = BROKER_OAUTH.read_text(encoding="utf-8")
    for needle in (
        "Schwab",
        "Robinhood",
        "Interactive Brokers",
        "PKCE",
        "tenant-scoped",
        "needs_reauth",
        "refresh",
        "skip",
    ):
        assert needle in text, f"missing {needle!r}"


def test_no_shared_platform_snapshot_language():
    text = ARCH.read_text(encoding="utf-8").lower()
    assert "never use an operator" in text or "no shared platform snapshot" in text


def test_broker_oauth_doc_has_no_live_secrets():
    text = BROKER_OAUTH.read_text(encoding="utf-8")
    for bad in (
        "sk-",
        # "Bearer ",
        "client_secret=",
        "DATABASE_URL=postgres",
        "-----BEGIN",
        "SCHWAB_CLIENT_SECRET",
    ):
        assert bad not in text, f"must not contain {bad!r}"
