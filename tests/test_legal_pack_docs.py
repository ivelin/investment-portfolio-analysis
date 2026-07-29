"""Legal pack presence for multi-tenant retail product."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEC = REPO / "docs" / "MULTI_TENANT_SECURITY.md"


def test_legal_acceptance_documented():
    text = SEC.read_text(encoding="utf-8").lower()
    assert "legal acceptance" in text
    assert "terms" in text and "privacy" in text
    assert "version" in text
