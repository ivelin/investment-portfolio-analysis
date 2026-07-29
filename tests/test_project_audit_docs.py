"""Ensure project audit expectations stay documented."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "docs" / "PROJECT_AUDIT.md"


def test_audit_doc_mece():
    text = AUDIT.read_text(encoding="utf-8").lower()
    for needle in (
        "dry",
        "mece",
        "tenant",
        "oauth",
        "not advice",
        "self-management",
        "terms",
        "privacy",
    ):
        assert needle in text, needle
