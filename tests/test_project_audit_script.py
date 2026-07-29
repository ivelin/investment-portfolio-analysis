"""Executable project audit is present and passes on a clean tree."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_project_audit_script_exists():
    assert (REPO / "scripts" / "project_audit.py").is_file()
    assert (REPO / ".grok" / "workflows" / "project-audit.rhai").is_file()


def test_project_audit_passes():
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "project_audit.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
