"""Local connector configuration + secrets (outside the git worktree)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from portfolio_analysis.paths import (
    broker_exports_dir,
    connector_config_path,
    connector_secrets_path,
    connectors_dir,
    default_broker_tokens_path,
    default_schwab_tokens_path,
    normalize_broker_id,
    secrets_dir,
)

# Supported modes for live data.
MODES = ("auto", "mcp", "direct", "exports_only")


@dataclass
class ConnectorConfig:
    """Non-secret connector settings for one broker."""

    broker: str
    enabled: bool = True
    mode: str = "auto"  # auto | mcp | direct | exports_only
    mcp_url: str | None = None
    mcp_command: str | None = None
    mcp_tool_prefix: str = ""
    mcp_apikey_env: str | None = None  # name of env var holding gateway apikey
    redirect_uri: str = "https://127.0.0.1:8080/callback"
    exports_dir: str | None = None
    notes: str = ""
    # Extra free-form settings (never secrets)
    options: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["broker"] = normalize_broker_id(self.broker)
        return d


@dataclass
class ConnectorStatus:
    broker: str
    enabled: bool
    mode: str
    config_path: str
    secrets_present: bool
    tokens_present: bool
    exports_dir: str
    live_source: str | None
    message: str = ""


def _atomic_write_json(
    path: Path, data: dict[str, Any], *, secret: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if secret:
        path.parent.chmod(0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600 if secret else 0o644)
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def default_connector(broker: str) -> ConnectorConfig:
    b = normalize_broker_id(broker)
    if b == "schwab":
        return ConnectorConfig(
            broker=b,
            mode="auto",
            mcp_url="http://127.0.0.1:3473/mcp",
            notes="Schwab: MCP (local/remote schwab-mcp) or direct Developer API OAuth",
        )
    return ConnectorConfig(broker=b, mode="exports_only", notes=f"{b} connector (stub)")


def load_connector(broker: str) -> ConnectorConfig:
    b = normalize_broker_id(broker)
    path = connector_config_path(b)
    if not path.exists():
        return default_connector(b)
    raw = _read_json(path)
    base = default_connector(b)
    mode = str(raw.get("mode") or base.mode).strip().lower()
    if mode not in MODES:
        mode = "auto"
    return ConnectorConfig(
        broker=b,
        enabled=bool(raw.get("enabled", True)),
        mode=mode,
        mcp_url=raw.get("mcp_url") or base.mcp_url,
        mcp_command=raw.get("mcp_command"),
        mcp_tool_prefix=str(raw.get("mcp_tool_prefix") or ""),
        mcp_apikey_env=raw.get("mcp_apikey_env"),
        redirect_uri=str(raw.get("redirect_uri") or base.redirect_uri),
        exports_dir=raw.get("exports_dir"),
        notes=str(raw.get("notes") or base.notes),
        options=dict(raw.get("options") or {}),
    )


def save_connector(cfg: ConnectorConfig) -> Path:
    path = connector_config_path(cfg.broker)
    connectors_dir().mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, cfg.to_public_dict(), secret=False)
    return path


def load_oauth_credentials(broker: str) -> dict[str, str]:
    """Return {client_id, client_secret} from secrets file and/or env."""
    b = normalize_broker_id(broker)
    path = connector_secrets_path(b, "oauth")
    data = _read_json(path) if path.exists() else {}
    client_id = str(data.get("client_id") or "")
    client_secret = str(data.get("client_secret") or "")
    if b == "schwab":
        client_id = client_id or os.environ.get("SCHWAB_CLIENT_ID") or ""
        client_secret = client_secret or os.environ.get("SCHWAB_CLIENT_SECRET") or ""
    else:
        prefix = b.upper()
        client_id = client_id or os.environ.get(f"{prefix}_CLIENT_ID") or ""
        client_secret = client_secret or os.environ.get(f"{prefix}_CLIENT_SECRET") or ""
    out: dict[str, str] = {}
    if client_id:
        out["client_id"] = str(client_id)
    if client_secret:
        out["client_secret"] = str(client_secret)
    return out


def save_oauth_credentials(
    broker: str, *, client_id: str | None = None, client_secret: str | None = None
) -> Path:
    b = normalize_broker_id(broker)
    path = connector_secrets_path(b, "oauth")
    existing = _read_json(path) if path.exists() else {}
    if client_id is not None:
        existing["client_id"] = client_id
    if client_secret is not None:
        existing["client_secret"] = client_secret
    secrets_dir().mkdir(parents=True, exist_ok=True)
    secrets_dir().chmod(0o700)
    _atomic_write_json(path, existing, secret=True)
    return path


def tokens_path_for(broker: str) -> Path:
    b = normalize_broker_id(broker)
    if b == "schwab":
        return default_schwab_tokens_path()
    return default_broker_tokens_path(b)


def exports_path_for(cfg: ConnectorConfig) -> Path:
    if cfg.exports_dir:
        return Path(cfg.exports_dir).expanduser().resolve()
    return broker_exports_dir(cfg.broker)


def configure_connector(
    broker: str,
    *,
    mode: str | None = None,
    enabled: bool | None = None,
    mcp_url: str | None = None,
    mcp_command: str | None = None,
    mcp_tool_prefix: str | None = None,
    mcp_apikey_env: str | None = None,
    redirect_uri: str | None = None,
    exports_dir: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    notes: str | None = None,
) -> ConnectorConfig:
    """Update connector config and optional secrets. Never logs secrets."""
    cfg = load_connector(broker)
    if mode is not None:
        m = mode.strip().lower()
        if m not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        cfg.mode = m
    if enabled is not None:
        cfg.enabled = enabled
    if mcp_url is not None:
        cfg.mcp_url = mcp_url or None
    if mcp_command is not None:
        cfg.mcp_command = mcp_command or None
    if mcp_tool_prefix is not None:
        cfg.mcp_tool_prefix = mcp_tool_prefix
    if mcp_apikey_env is not None:
        cfg.mcp_apikey_env = mcp_apikey_env or None
    if redirect_uri is not None:
        cfg.redirect_uri = redirect_uri
    if exports_dir is not None:
        cfg.exports_dir = exports_dir or None
    if notes is not None:
        cfg.notes = notes
    save_connector(cfg)
    if client_id is not None or client_secret is not None:
        save_oauth_credentials(broker, client_id=client_id, client_secret=client_secret)
    return cfg


def get_connector(broker: str) -> ConnectorConfig:
    return load_connector(broker)


def list_connectors() -> list[ConnectorConfig]:
    """Built-in brokers + any extra config files on disk."""
    from portfolio_analysis.brokers import (
        ensure_builtin_brokers_registered,
        list_registered_brokers,
    )

    ensure_builtin_brokers_registered()
    names = {r.broker for r in list_registered_brokers()}
    if connectors_dir().is_dir():
        for p in connectors_dir().glob("*.json"):
            names.add(p.stem)
    return [load_connector(n) for n in sorted(names)]


def redact_connector(cfg: ConnectorConfig) -> dict[str, Any]:
    """Public view: no secrets; indicate secret presence only."""
    b = normalize_broker_id(cfg.broker)
    creds = load_oauth_credentials(b)
    tok = tokens_path_for(b)
    return {
        "broker": b,
        "enabled": cfg.enabled,
        "mode": cfg.mode,
        "mcp_url": cfg.mcp_url,
        "mcp_command": cfg.mcp_command,
        "mcp_tool_prefix": cfg.mcp_tool_prefix,
        "mcp_apikey_env": cfg.mcp_apikey_env,
        "redirect_uri": cfg.redirect_uri,
        "exports_dir": str(exports_path_for(cfg)),
        "notes": cfg.notes,
        "options": cfg.options,
        "config_path": str(connector_config_path(b)),
        "secrets_present": bool(creds.get("client_id") and creds.get("client_secret")),
        "client_id_set": bool(creds.get("client_id")),
        "tokens_path": str(tok),
        "tokens_present": tok.exists(),
    }


def resolve_live_source_for_connector(cfg: ConnectorConfig) -> Any:
    """Build a BrokerLiveSource (or None) from connector config."""
    from portfolio_analysis.brokers.sources.direct_api import SchwabDirectApiLiveSource
    from portfolio_analysis.brokers.sources.mcp_transport import McpTransportConfig
    from portfolio_analysis.brokers.sources.schwab_mcp import SchwabMcpLiveSource

    b = normalize_broker_id(cfg.broker)
    if not cfg.enabled or cfg.mode == "exports_only":
        return None

    if b != "schwab":
        # Other brokers: only MCP generic path when mode is mcp/auto and URL set
        if cfg.mode in ("mcp", "auto") and (cfg.mcp_url or cfg.mcp_command):
            # Generic MCP source only implemented for Schwab account parsing for now
            return None
        return None

    def _mcp() -> SchwabMcpLiveSource:
        headers: dict[str, str] = {}
        url = cfg.mcp_url
        if cfg.mcp_apikey_env and url:
            key = os.environ.get(cfg.mcp_apikey_env)
            if key:
                from portfolio_analysis.brokers.sources.mcp_transport import (
                    _append_query,
                )

                url = _append_query(url, {"apikey": key})
        if cfg.mcp_command:
            parts = cfg.mcp_command.split()
            conf = McpTransportConfig(
                url=None,
                command=parts[0],
                args=tuple(parts[1:]),
                headers=headers,
                tool_prefix=cfg.mcp_tool_prefix or "",
            )
        else:
            conf = McpTransportConfig(
                url=url or "http://127.0.0.1:3473/mcp",
                headers=headers,
                tool_prefix=cfg.mcp_tool_prefix or "",
            )
        return SchwabMcpLiveSource(conf)

    def _direct() -> SchwabDirectApiLiveSource | None:
        creds = load_oauth_credentials("schwab")
        if not creds.get("client_id") or not creds.get("client_secret"):
            return None
        # Inject into env for SchwabAuth defaults without printing
        os.environ.setdefault("SCHWAB_CLIENT_ID", creds["client_id"])
        os.environ.setdefault("SCHWAB_CLIENT_SECRET", creds["client_secret"])
        from portfolio_analysis.schwab.auth import SchwabAuth
        from portfolio_analysis.schwab.client import SchwabClient

        auth = SchwabAuth(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            redirect_uri=cfg.redirect_uri,
            token_file=tokens_path_for("schwab"),
        )
        return SchwabDirectApiLiveSource(client=SchwabClient(auth))

    if cfg.mode == "mcp":
        return _mcp()
    if cfg.mode == "direct":
        return _direct()
    # auto: prefer MCP, then direct
    try:
        return _mcp()
    except Exception:
        pass
    return _direct()


def probe_connector(broker: str) -> dict[str, Any]:
    """Probe connector without fabricating data. Returns structured status."""
    cfg = load_connector(broker)
    b = normalize_broker_id(broker)
    result: dict[str, Any] = {
        "broker": b,
        "mode": cfg.mode,
        "enabled": cfg.enabled,
        "ok": False,
        "live_source": None,
        "accounts": 0,
        "error": None,
        "redacted": redact_connector(cfg),
    }
    if not cfg.enabled:
        result["error"] = "connector disabled"
        return result
    if cfg.mode == "exports_only":
        exp = exports_path_for(cfg)
        result["ok"] = True
        result["live_source"] = None
        result["exports_dir"] = str(exp)
        result["exports_exists"] = exp.is_dir()
        result["message"] = "exports_only mode — no live probe"
        return result
    try:
        source = resolve_live_source_for_connector(cfg)
        if source is None:
            result["error"] = (
                "no live source available (configure MCP URL or OAuth credentials)"
            )
            return result
        result["live_source"] = getattr(source, "name", type(source).__name__)
        rows = list(source.fetch_account_equities())
        result["accounts"] = len(rows)
        result["account_keys"] = [r.account_key for r in rows]
        result["ok"] = True
        result["message"] = f"fetched {len(rows)} account equity snapshot(s)"
    except Exception as exc:  # noqa: BLE001 — surface probe errors to operator
        result["error"] = str(exc)
    return result
