"""OAuth callback principal bind + intended-use flags (pure CI tests)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEC = REPO / "docs" / "MULTI_TENANT_SECURITY.md"


def assert_oauth_callback_principal(
    state_user_id: str | None, session_user_id: str | None
) -> dict:
    if not state_user_id:
        return {"ok": False, "reason": "missing_state_user"}
    if not session_user_id:
        return {"ok": False, "reason": "no_session"}
    if session_user_id != state_user_id:
        return {"ok": False, "reason": "user_mismatch"}
    return {"ok": True}


def test_bind_ok():
    assert assert_oauth_callback_principal("a", "a") == {"ok": True}


def test_bind_no_session():
    assert assert_oauth_callback_principal("a", None)["reason"] == "no_session"


def test_bind_mismatch():
    assert assert_oauth_callback_principal("a", "b")["reason"] == "user_mismatch"


def test_security_doc_covers_session_bind_and_self_management():
    text = SEC.read_text(encoding="utf-8").lower()
    assert "session" in text and "state" in text
    assert "self-management" in text or "their own" in text
    assert "not" in text and "advice" in text
