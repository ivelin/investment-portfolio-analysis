"""Instance data must live under PORTFOLIO_ANALYSIS_HOME, never the git worktree."""

from __future__ import annotations

from pathlib import Path

from portfolio_analysis.paths import (
    default_db_path,
    default_env_file,
    default_exports_dir,
    default_reports_dir,
    default_schwab_tokens_path,
    env_file_candidates,
    get_reports_dir,
    instance_home,
)


def test_instance_home_default_is_dot_dir_under_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # Re-import not needed: instance_home calls Path.home() each time
    root = instance_home()
    # Canonical: dot + repo/dir name (investment-portfolio-analysis)
    assert root == (tmp_path / ".investment-portfolio-analysis").resolve()
    assert root.is_absolute()
    # Never resolve into a path that looks like a source checkout of this project
    assert "src/portfolio_analysis" not in str(root)


def test_instance_home_legacy_dot_dir_if_preferred_missing(monkeypatch, tmp_path):
    """Pre-rename ~/.portfolio-analysis is still resolved when preferred is absent."""
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    legacy = tmp_path / ".portfolio-analysis"
    legacy.mkdir()
    assert instance_home() == legacy.resolve()


def test_instance_home_env_override(monkeypatch, tmp_path):
    home = tmp_path / "my-instance"
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(home))
    # GHA sets PORTFOLIO_ANALYSIS_DB_PATH to an empty CI DB; clear path-level
    # overrides so this test asserts HOME-derived defaults only.
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_DB_PATH", raising=False)
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_EXPORTS_DIR", raising=False)
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_REPORTS_DIR", raising=False)
    assert instance_home() == home.resolve()
    assert default_db_path() == (home / "portfolio.db").resolve()
    # Preferred multi-broker root when nothing exists yet
    assert default_exports_dir() == (home / "exports").resolve()
    assert default_reports_dir() == (home / "reports").resolve()
    assert default_env_file() == (home / ".env").resolve()


def test_specific_path_env_overrides_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path / "home"))
    db = tmp_path / "elsewhere" / "custom.db"
    exports = tmp_path / "exports-root"
    reports = tmp_path / "reports-root"
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_DB_PATH", str(db))
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_EXPORTS_DIR", str(exports))
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_REPORTS_DIR", str(reports))
    assert default_db_path() == db.resolve()
    assert default_exports_dir() == exports.resolve()
    assert default_reports_dir() == reports.resolve()


def test_get_reports_dir_creates_under_instance_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path / "inst"))
    monkeypatch.delenv("PORTFOLIO_ANALYSIS_REPORTS_DIR", raising=False)
    reports = get_reports_dir()
    assert reports.is_dir()
    assert reports == (tmp_path / "inst" / "reports").resolve()


def test_schwab_tokens_prefer_instance_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path / "inst"))
    monkeypatch.delenv("SCHWAB_TOKENS_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # No legacy file → preferred multi-broker tokens path
    assert (
        default_schwab_tokens_path()
        == (tmp_path / "inst" / "tokens" / "schwab.json").resolve()
    )


def test_schwab_tokens_legacy_fallback_when_only_legacy_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path / "inst"))
    monkeypatch.delenv("SCHWAB_TOKENS_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    legacy = tmp_path / ".schwab" / "tokens.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}")
    assert default_schwab_tokens_path() == legacy.resolve()


def test_env_file_candidates_prefer_instance_local(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_HOME", str(tmp_path / "inst"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cands = env_file_candidates()
    assert cands[0] == (tmp_path / "inst" / ".env").resolve()


def test_db_module_delegates_to_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_ANALYSIS_DB_PATH", str(tmp_path / "t.db"))
    from portfolio_analysis.db import default_db_path as db_default

    assert db_default() == (tmp_path / "t.db").resolve()
