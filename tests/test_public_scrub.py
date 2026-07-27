"""Public-release hygiene: Apache-2.0 packaging + no personal financial fingerprints.

These checks assert the *shipped* tree state used for open distribution.
Forbidden strings are built at runtime so this file itself does not embed
contiguous operator fingerprints for history greps.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _j(*parts: str) -> str:
    """Join fragments into a fingerprint string only at runtime."""
    return "".join(parts)


def test_apache_license_and_notice_present():
    license_path = REPO_ROOT / "LICENSE"
    notice_path = REPO_ROOT / "NOTICE"
    assert license_path.is_file(), "LICENSE must exist at repo root"
    assert notice_path.is_file(), "NOTICE must exist at repo root"
    text = license_path.read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0" in text
    notice = notice_path.read_text(encoding="utf-8")
    assert "portfolio-analysis" in notice.lower() or "Copyright" in notice


def test_package_metadata_declares_apache_not_mit():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = {text = "Apache-2.0"}' in pyproject
    assert 'license = {text = "MIT"}' not in pyproject
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "license: Apache-2.0" in skill
    assert "license: MIT" not in skill
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Apache License" in readme


def test_pdf_report_examples_are_synthetic_not_live_sizes():
    """Drive the real shipped module source for PDF legend examples."""
    from portfolio_analysis import pdf_report

    src = Path(pdf_report.__file__).read_text(encoding="utf-8")
    # Forbidden personal-fingerprint strings (fragmented so the test file is clean)
    forbidden = [
        _j("TSLA (", "512", " shares)"),
        _j("~$", "187", "k"),
        _j("AXTI (", "476"),
        _j("STRC (", "2327"),
        _j("19", "463"),
        _j("real positions from your ", "portfolio"),
        _j("+", "711", "% YTD"),
        _j("+", "214", "% YTD"),
    ]
    for bad in forbidden:
        assert bad not in src, f"pdf_report must not embed live fingerprint: {bad!r}"
    # Expected synthetic markers
    assert "synthetic illustrations" in src
    assert "AAA (" in src and "shares)" in src


def test_no_personal_account_nickname_or_live_size_anchors_in_docs_tools():
    paths = [
        REPO_ROOT / "tools" / "ingest_account_statement_equities.py",
        REPO_ROOT / "tools" / "ingest_all_schwab_exports.py",
        REPO_ROOT / "src" / "portfolio_analysis" / "mcp_server.py",
        REPO_ROOT / "src" / "portfolio_analysis" / "twrr.py",
        REPO_ROOT / "SKILL.md",
        REPO_ROOT
        / "docs"
        / "archive"
        / "extraction_prompts_sota_vqa"
        / "grok_schwab_statement_prompt.md",
    ]
    nick = _j("Active", "-Trading-", "IRA")
    nick_u = _j("Active", "_Trading_", "IRA")
    live_25 = _j("exactly ", "25", " shares")
    live_27 = _j("carries ", "27")
    live_81_mv = _j("24200", ".71")
    live_81_cb = _j("21058", ".24")
    live_81_comment = _j("25k for ", "81", " shares")
    bare_81_spike = _j("e.g. ", "81")
    spikes_to_81 = _j("spikes to ", "81")
    must_25 = _j("exactly ", "25")
    pre_27 = _j("pre value (", "27", ")")
    for_sndk = _j("_for_", "sndk")
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert nick not in text, f"{p} still names personal account folder"
        assert nick_u not in text, f"{p} still names personal account folder"
        assert live_25 not in text, f"{p} still has live size anchor"
        assert live_27 not in text, f"{p} still has live size anchor"
        assert live_81_mv not in text, f"{p} still has live statement example MV"
        assert live_81_cb not in text, f"{p} still has live statement example CB"
        assert live_81_comment not in text, f"{p} still has operator MV comment"
        assert bare_81_spike not in text, f"{p} still has bare Journal size 81"
        assert spikes_to_81 not in text, f"{p} still mentions artificial Journal spikes"
        assert must_25 not in text, f"{p} still hard-codes size 25"
        assert pre_27 not in text, f"{p} still hard-codes pre value 27"
        assert for_sndk not in text.lower(), f"{p} still has operator-symbol test name"

    # charts.py is the chart SSOT docstring source
    charts = (REPO_ROOT / "src" / "portfolio_analysis" / "charts.py").read_text(
        encoding="utf-8"
    )
    assert bare_81_spike not in charts
    assert spikes_to_81 not in charts

    # Regression tests must not publish operator Journal size anchors
    twrr_t = (REPO_ROOT / "tests" / "test_twrr_regression.py").read_text(
        encoding="utf-8"
    )
    assert for_sndk not in twrr_t.lower()
    assert _j("81 on ", "2026") not in twrr_t
    assert _j("exactly ", "25") not in twrr_t
    assert _j("pre value (", "27") not in twrr_t
