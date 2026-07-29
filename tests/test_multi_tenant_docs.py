"""Multi-tenant platform docs: security and architecture invariants.

These tests lock the Phase 1 hosted-platform contract without requiring
Neon, auth, or any real portfolio data. Safe for a public repository.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCH = REPO_ROOT / "docs" / "MULTI_TENANT_ARCHITECTURE.md"
SEC = REPO_ROOT / "docs" / "MULTI_TENANT_SECURITY.md"
SECURITY_MD = REPO_ROOT / "SECURITY.md"
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
ADR = REPO_ROOT / "references" / "architecture-decisions.md"


def test_multi_tenant_docs_exist():
    assert ARCH.is_file(), "MULTI_TENANT_ARCHITECTURE.md required"
    assert SEC.is_file(), "MULTI_TENANT_SECURITY.md required"


def test_architecture_defines_modes_and_tenant_model():
    text = ARCH.read_text(encoding="utf-8")
    for needle in (
        "Local skill",
        "Hosted platform",
        "tenant_id",
        "requireTenantAccess",
        "Neon Postgres",
        "Better Auth",
        "is_demo",
        "connector_secrets",
        "list_tools",
        "workspace_summary",
        "positions",
        "fund_series",
        "Phase 1",
    ):
        assert needle in text, f"architecture doc missing required concept: {needle!r}"


def test_security_doc_hard_rules():
    text = SEC.read_text(encoding="utf-8")
    for needle in (
        "Never commit",
        "tenant isolation",
        "Opaque account keys",
        "encrypted",
        "Redaction",
        "fail closed",
        "Synthetic demo",
        "Do **not** paste secrets",
        "PORTFOLIO_ANALYSIS_HOME",
    ):
        assert needle.lower() in text.lower(), f"security doc missing rule: {needle!r}"


def test_root_security_links_multi_tenant_docs():
    text = SECURITY_MD.read_text(encoding="utf-8")
    assert "MULTI_TENANT_SECURITY.md" in text
    assert "MULTI_TENANT_ARCHITECTURE.md" in text
    assert "Hosted Neon dumps" in text or "multi-tenant portfolio rows" in text


def test_docs_index_and_adr_point_to_multi_tenant():
    index = DOCS_INDEX.read_text(encoding="utf-8")
    assert "MULTI_TENANT_ARCHITECTURE.md" in index
    assert "MULTI_TENANT_SECURITY.md" in index
    adr = ADR.read_text(encoding="utf-8")
    assert "Multi-tenant hosted platform" in adr
    assert "feature/multi-tenant-platform" in adr
    assert "tenant_id" in adr


def test_multi_tenant_docs_have_no_secret_or_live_balance_patterns():
    """Docs must not look like they embed live credentials or balances."""
    forbidden_substrings = [
        "sk-",
        "Bearer ",
        "client_secret=",
        "DATABASE_URL=postgres",
        "BEGIN RSA PRIVATE KEY",
        "-----BEGIN",
        "SCHWAB_CLIENT_SECRET",
        "POLYGON_API_KEY=",
    ]
    for path in (ARCH, SEC):
        text = path.read_text(encoding="utf-8")
        for bad in forbidden_substrings:
            assert bad not in text, f"{path.name} must not contain {bad!r}"


def test_demo_policy_explicit_in_both_docs():
    for path in (ARCH, SEC):
        text = path.read_text(encoding="utf-8").lower()
        assert "demo" in text
        assert "synthetic" in text
