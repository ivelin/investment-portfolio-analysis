#!/usr/bin/env python3
"""Project audit (rhai checklist) for investment-portfolio-analysis.

DRY / MECE / security / compliance scan for the public multi-tenant branch.
Exit 0 = pass, 1 = blocking findings.

  python scripts/project_audit.py
  python scripts/project_audit.py --json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_OUT = "--json" in sys.argv

Finding = dict  # id, severity, area, message, file?


def main() -> int:
    findings: list[Finding] = []

    def add(
        *,
        id: str,
        severity: str,
        area: str,
        message: str,
        file: str | None = None,
    ) -> None:
        findings.append(
            {
                "id": id,
                "severity": severity,
                "area": area,
                "message": message,
                "file": file,
            }
        )

    required = [
        ("docs/MULTI_TENANT_ARCHITECTURE.md", "architecture"),
        ("docs/MULTI_TENANT_SECURITY.md", "security"),
        ("docs/BROKER_OAUTH.md", "oauth"),
        ("docs/PROJECT_AUDIT.md", "audit"),
        ("tests/test_multi_tenant_docs.py", "tests"),
        ("tests/test_token_refresh_job.py", "tests"),
        ("tests/test_mece_sre.py", "tests"),
        ("tests/test_oauth_session_bind.py", "tests"),
        ("tests/test_legal_pack_docs.py", "tests"),
    ]
    for rel, area in required:
        p = ROOT / rel
        if p.is_file():
            add(
                id=f"present:{rel}",
                severity="info",
                area=area,
                message=f"OK — {rel}",
                file=rel,
            )
        else:
            add(
                id=f"missing:{rel}",
                severity="block",
                area=area,
                message=f"Missing required file: {rel}",
                file=rel,
            )

    # Content scans
    secret_res = [
        (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "pem"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "aws"),
        (re.compile(r"sk_live_[a-zA-Z0-9]{20,}"), "stripe"),
        (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "ghpat"),
    ]
    pii_res = [
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "ssn-like"),
    ]
    advice_re = re.compile(
        r"\b(buy now|sell now|guaranteed returns?|you should buy|you should sell|"
        r"personalized investment advice|fiduciary advice)\b",
        re.I,
    )

    skip_dirs = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
    }
    text_ext = {".md", ".py", ".yml", ".yaml", ".toml", ".json", ".txt", ".sql"}

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in text_ext:
            continue
        if path.stat().st_size > 1_500_000:
            continue
        rel = str(path.relative_to(ROOT))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for cre, name in secret_res:
            if cre.search(text):
                add(
                    id=f"secret:{name}:{rel}",
                    severity="block",
                    area="security",
                    message=f"Possible secret material ({name})",
                    file=rel,
                )
        for cre, name in pii_res:
            if cre.search(text) and "test" not in rel.lower():
                add(
                    id=f"pii:{name}:{rel}",
                    severity="block",
                    area="security",
                    message=f"Possible PII pattern ({name})",
                    file=rel,
                )

        # Advice language in user-facing README only (docs can discuss advice risk)
        if rel in {"README.md"} and advice_re.search(text):
            add(
                id=f"advice:{rel}",
                severity="block",
                area="compliance",
                message="Investment-advice-like language in README",
                file=rel,
            )

    # MECE / isolation doc contracts
    sec = ROOT / "docs" / "MULTI_TENANT_SECURITY.md"
    if sec.is_file():
        t = sec.read_text(encoding="utf-8").lower()
        for needle in ("tenant", "oauth", "session", "self-management", "advice"):
            if needle not in t:
                add(
                    id=f"sec-missing:{needle}",
                    severity="block",
                    area="compliance",
                    message=f"MULTI_TENANT_SECURITY.md missing concept: {needle}",
                    file=str(sec.relative_to(ROOT)),
                )

    arch = ROOT / "docs" / "MULTI_TENANT_ARCHITECTURE.md"
    if arch.is_file():
        t = arch.read_text(encoding="utf-8").lower()
        for needle in ("dry", "mece", "token_refresh", "tenant"):
            if needle not in t:
                add(
                    id=f"arch-missing:{needle}",
                    severity="warn",
                    area="dry",
                    message=f"Architecture doc weak on: {needle}",
                    file=str(arch.relative_to(ROOT)),
                )

    blocks = [f for f in findings if f["severity"] == "block"]
    warns = [f for f in findings if f["severity"] == "warn"]
    infos = [f for f in findings if f["severity"] == "info"]
    report = {
        "name": "project-audit",
        "alias": "rhai-audit",
        "root": str(ROOT),
        "summary": {
            "block": len(blocks),
            "warn": len(warns),
            "info": len(infos),
            "pass": len(blocks) == 0,
        },
        "findings": findings,
    }

    if JSON_OUT:
        print(json.dumps(report, indent=2))
    else:
        print("══ Project audit (rhai) — public repo ══")
        print(f"block={len(blocks)}  warn={len(warns)}  info={len(infos)}")
        print()
        for f in blocks + warns:
            loc = f" ({f['file']})" if f.get("file") else ""
            print(f"[{f['severity'].upper()}] [{f['area']}] {f['message']}{loc}")
        print()
        print(
            "OK — no blocking findings"
            if not blocks
            else "FAIL — fix blocking findings"
        )

    out = ROOT / "docs" / "AUDIT_LAST_RUN.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if blocks else 0


if __name__ == "__main__":
    raise SystemExit(main())
