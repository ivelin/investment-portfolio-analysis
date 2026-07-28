"""Canonical locations for operator-private *instance* data.

All concrete brokerage exports, SQLite state, generated reports that may
contain balances, OAuth tokens, and local secret files live under a single
directory **outside the source repository**. Convention: **dot + repo/dir
name** (same pattern as ``~/schwab-mcp`` → ``~/.schwab-mcp``):

    ~/.investment-portfolio-analysis/   # default PORTFOLIO_ANALYSIS_HOME
      portfolio.db
      exports/                      # multi-broker raw exports (preferred)
        schwab/
        ibkr/
        robinhood/
        fidelity/
      schwab-exports/               # legacy flat Schwab tree (still supported)
      reports/                      # PDFs, charts, text reports
      tokens/                       # optional per-broker OAuth JSON
        schwab.json
      connectors/                   # non-secret connector config (mode, MCP URL)
        schwab.json
      secrets/                      # credentials + oauth pending (mode 0600)
        schwab_oauth.json
      schwab/tokens.json            # legacy Schwab token path (still supported)
      .env                          # optional API keys for this skill only
      cache/                        # optional local caches

Never write personal instance data into the git worktree. Synthetic test
fixtures under tests/fixtures/ are the only in-repo data, and they are
placeholders only.

Environment overrides (highest priority first where noted):

- PORTFOLIO_ANALYSIS_HOME         root for all defaults below
- PORTFOLIO_ANALYSIS_DB_PATH      SQLite file
- PORTFOLIO_ANALYSIS_EXPORTS_DIR  raw multi-broker exports root
- PORTFOLIO_ANALYSIS_REPORTS_DIR  generated report artifacts
- SCHWAB_TOKENS_PATH              OAuth token JSON for Schwab (optional)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Directory name under $HOME when PORTFOLIO_ANALYSIS_HOME is unset.
# Canonical: dot-prefixed clone/repo directory name.
_DEFAULT_HOME_NAME = ".investment-portfolio-analysis"
# Pre-rename default (private-repo era); still resolved if present and preferred missing.
_LEGACY_HOME_NAME = ".portfolio-analysis"
_LEGACY_SCHWAB_EXPORTS = "schwab-exports"
_EXPORTS_ROOT_NAME = "exports"

# Known broker ids used for on-disk layout (adapters may add more via registry).
KNOWN_BROKER_IDS = (
    "schwab",
    "ibkr",
    "robinhood",
    "fidelity",
    "synthetic",
)


def instance_home() -> Path:
    """Root directory for all operator-private instance data (never the git repo).

    Resolution order:
    1. ``PORTFOLIO_ANALYSIS_HOME``
    2. ``~/.investment-portfolio-analysis`` if it exists
    3. legacy ``~/.portfolio-analysis`` if it exists (pre-public-rename)
    4. otherwise the preferred path ``~/.investment-portfolio-analysis``
    """
    raw = os.environ.get("PORTFOLIO_ANALYSIS_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    preferred = Path.home() / _DEFAULT_HOME_NAME
    legacy = Path.home() / _LEGACY_HOME_NAME
    if preferred.exists():
        return preferred.resolve()
    if legacy.exists():
        return legacy.resolve()
    return preferred.resolve()


def ensure_instance_home() -> Path:
    """Return instance_home(), creating it if missing."""
    root = instance_home()
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_db_path() -> Path:
    """SQLite database path (env override wins every call)."""
    env = os.environ.get("PORTFOLIO_ANALYSIS_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return instance_home() / "portfolio.db"


def normalize_broker_id(broker: str) -> str:
    """Normalize a broker label to a stable filesystem / registry id."""
    b = (broker or "").strip().lower()
    b = re.sub(r"[^a-z0-9]+", "_", b).strip("_")
    aliases = {
        "td": "schwab",
        "tda": "schwab",
        "tdameritrade": "schwab",
        "charles_schwab": "schwab",
        "interactive_brokers": "ibkr",
        "interactive_broker": "ibkr",
        "rh": "robinhood",
        "fidelity_investments": "fidelity",
    }
    b = aliases.get(b, b)
    if not b:
        raise ValueError("broker id must be non-empty")
    return b


def default_exports_dir() -> Path:
    """Root directory for *all* broker export trees.

    Resolution order:
    1. PORTFOLIO_ANALYSIS_EXPORTS_DIR
    2. ``$PORTFOLIO_ANALYSIS_HOME/exports`` if it exists
    3. legacy ``$PORTFOLIO_ANALYSIS_HOME/schwab-exports`` if it exists
       (treated as a Schwab-only flat tree for backward compatibility)
    4. otherwise the preferred modern path ``…/exports`` (may not exist yet)
    """
    env = os.environ.get("PORTFOLIO_ANALYSIS_EXPORTS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    modern = instance_home() / _EXPORTS_ROOT_NAME
    legacy = instance_home() / _LEGACY_SCHWAB_EXPORTS
    if modern.is_dir():
        return modern.resolve()
    if legacy.is_dir():
        return legacy.resolve()
    return modern.resolve()


def is_legacy_schwab_exports_layout(exports_root: Path | None = None) -> bool:
    """True when the exports root is the pre-multi-broker flat Schwab directory."""
    root = exports_root or default_exports_dir()
    return root.name == _LEGACY_SCHWAB_EXPORTS


def broker_exports_dir(broker: str = "schwab") -> Path:
    """Per-broker immutable export directory under the exports root.

    - Modern layout: ``exports/{broker}/``
    - Legacy layout (root named ``schwab-exports``): that root *is* the Schwab
      tree; other brokers resolve under ``exports/{broker}/`` so they never
      mix into the legacy Schwab folder.
    """
    b = normalize_broker_id(broker)
    root = default_exports_dir()
    if is_legacy_schwab_exports_layout(root):
        if b == "schwab":
            return root.resolve()
        return (instance_home() / _EXPORTS_ROOT_NAME / b).resolve()
    return (root / b).resolve()


def default_reports_dir() -> Path:
    """Generated reports/charts (may contain balances — keep out of the repo)."""
    env = os.environ.get("PORTFOLIO_ANALYSIS_REPORTS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return instance_home() / "reports"


def get_reports_dir() -> Path:
    """Return reports dir, creating it on first use."""
    p = default_reports_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_env_file() -> Path:
    """Optional skill-local .env for market-data / broker keys."""
    return instance_home() / ".env"


def default_broker_tokens_path(broker: str = "schwab") -> Path:
    """Preferred OAuth token path for a broker under the instance home."""
    b = normalize_broker_id(broker)
    return instance_home() / "tokens" / f"{b}.json"


def default_schwab_tokens_path() -> Path:
    """Schwab OAuth token store under the instance home.

    Resolution order:
    1. SCHWAB_TOKENS_PATH
    2. instance tokens/schwab.json if present
    3. instance schwab/tokens.json if present
    4. legacy ~/.schwab/tokens.json if present
    5. preferred new path tokens/schwab.json (for first write)
    """
    env = os.environ.get("SCHWAB_TOKENS_PATH")
    if env:
        return Path(env).expanduser().resolve()
    preferred = default_broker_tokens_path("schwab")
    nested = instance_home() / "schwab" / "tokens.json"
    legacy = Path.home() / ".schwab" / "tokens.json"
    for candidate in (preferred, nested, legacy):
        if candidate.exists():
            return candidate.resolve()
    return preferred.resolve()


def default_cache_dir() -> Path:
    """Optional local cache directory under the instance home."""
    return instance_home() / "cache"


def connectors_dir() -> Path:
    """Non-secret per-broker connector configs (JSON)."""
    return instance_home() / "connectors"


def secrets_dir() -> Path:
    """Sensitive credentials / oauth pending state (mode 0700)."""
    return instance_home() / "secrets"


def connector_config_path(broker: str) -> Path:
    return connectors_dir() / f"{normalize_broker_id(broker)}.json"


def connector_secrets_path(broker: str, kind: str = "oauth") -> Path:
    b = normalize_broker_id(broker)
    return secrets_dir() / f"{b}_{kind}.json"


def locks_dir() -> Path:
    """Advisory lock files for single-writer instance operations."""
    return instance_home() / "locks"


def job_lock_path(job_id: str) -> Path:
    """Exclusive flock path for one registered job id."""
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (job_id or "job").strip()) or "job"
    return locks_dir() / f"{safe}.lock"


def sync_lock_path() -> Path:
    """Exclusive lock for connector → local-DB sync (alias of job lock)."""
    return job_lock_path("connector_sync")


def jobs_dir() -> Path:
    """Durable job run status (non-secret JSON under instance home)."""
    return instance_home() / "jobs"


def job_runs_dir() -> Path:
    """Per-run status files (run_id.json)."""
    return jobs_dir() / "runs"


def job_status_path(job_id: str) -> Path:
    """Last status for a job id (non-secret)."""
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (job_id or "job").strip()) or "job"
    return jobs_dir() / f"{safe}_status.json"


def sync_status_path() -> Path:
    """Last connector_sync status (legacy path + jobs alias)."""
    # Prefer new jobs path; fall back to legacy root-level file if present.
    modern = job_status_path("connector_sync")
    legacy = instance_home() / "sync_status.json"
    if modern.is_file() or not legacy.is_file():
        return modern
    return legacy


def env_file_candidates() -> list[Path]:
    """Ordered list of .env files that may hold market-data API keys.

    Instance-local file is preferred; legacy home/hermes paths remain as
    fallbacks so existing operator setups keep working.
    """
    return [
        default_env_file(),
        Path.home() / ".env",
        Path.home() / ".hermes" / ".env",
    ]
