"""OAuth user flows for connectors that need developer API tokens (e.g. Schwab)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from portfolio_analysis.paths import (
    connector_secrets_path,
    normalize_broker_id,
    secrets_dir,
)

from .store import load_connector, load_oauth_credentials, tokens_path_for


def _pending_path(broker: str) -> Path:
    return connector_secrets_path(broker, "oauth_pending")


def _write_secret_json(path: Path, data: dict[str, Any]) -> None:
    secrets_dir().mkdir(parents=True, exist_ok=True)
    secrets_dir().chmod(0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def oauth_status(broker: str) -> dict[str, Any]:
    b = normalize_broker_id(broker)
    cfg = load_connector(b)
    creds = load_oauth_credentials(b)
    tok = tokens_path_for(b)
    pending = _pending_path(b)
    return {
        "broker": b,
        "client_id_set": bool(creds.get("client_id")),
        "client_secret_set": bool(creds.get("client_secret")),
        "redirect_uri": cfg.redirect_uri,
        "tokens_path": str(tok),
        "tokens_present": tok.exists(),
        "oauth_pending": pending.exists(),
        "supports_oauth": b == "schwab",
    }


def oauth_start(broker: str) -> dict[str, Any]:
    """Begin OAuth (PKCE). Returns authorization_url; stores verifier locally."""
    b = normalize_broker_id(broker)
    if b != "schwab":
        raise NotImplementedError(
            f"OAuth user flow not implemented for broker {b!r} yet (Schwab only)"
        )
    cfg = load_connector(b)
    creds = load_oauth_credentials(b)
    if not creds.get("client_id") or not creds.get("client_secret"):
        raise ValueError(
            "Missing OAuth client_id/client_secret. Call configure_connector with "
            "client_id and client_secret first (stored under PORTFOLIO_ANALYSIS_HOME/secrets/)."
        )
    from portfolio_analysis.schwab.auth import SchwabAuth

    auth = SchwabAuth(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        redirect_uri=cfg.redirect_uri,
        token_file=tokens_path_for(b),
    )
    url, verifier = auth.get_authorization_url()
    _write_secret_json(
        _pending_path(b),
        {
            "code_verifier": verifier,
            "redirect_uri": cfg.redirect_uri,
            "created_at": time.time(),
        },
    )
    return {
        "broker": b,
        "authorization_url": url,
        "redirect_uri": cfg.redirect_uri,
        "instructions": (
            "Open authorization_url in a browser, approve access, then call "
            "oauth_complete with the ?code= query parameter from the redirect URL. "
            "code_verifier is stored locally and used automatically if omitted."
        ),
        # Return verifier for headless agents that cannot rely on local pending file
        "code_verifier": verifier,
    }


def oauth_complete(
    broker: str,
    *,
    code: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    """Exchange authorization code for tokens; persist under instance tokens/."""
    b = normalize_broker_id(broker)
    if b != "schwab":
        raise NotImplementedError(
            f"OAuth user flow not implemented for broker {b!r} yet (Schwab only)"
        )
    cfg = load_connector(b)
    creds = load_oauth_credentials(b)
    if not creds.get("client_id") or not creds.get("client_secret"):
        raise ValueError("Missing OAuth client credentials in secrets store")

    verifier = code_verifier
    pending_path = _pending_path(b)
    if not verifier and pending_path.exists():
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        verifier = pending.get("code_verifier")
    if not verifier:
        raise ValueError("code_verifier required (or run oauth_start first)")

    from portfolio_analysis.schwab.auth import SchwabAuth

    auth = SchwabAuth(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        redirect_uri=cfg.redirect_uri,
        token_file=tokens_path_for(b),
    )
    tokens = auth.exchange_code_for_tokens(code, verifier)
    if pending_path.exists():
        pending_path.unlink()
    return {
        "broker": b,
        "status": "authenticated",
        "tokens_path": str(tokens_path_for(b)),
        "expires_in": tokens.get("expires_in"),
        "has_refresh_token": bool(tokens.get("refresh_token")),
    }
