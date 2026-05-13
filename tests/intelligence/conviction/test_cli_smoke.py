"""End-to-end smoke for the conviction CLI (dry-run only — no DB writes)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ATLAS_DB_URL"), reason="needs ATLAS_DB_URL")
def test_cli_dry_run_end_to_end() -> None:
    """The CLI dry-run should run, print a summary, exit 0."""
    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT)}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/compute_conviction.py"],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert result.returncode == 0, f"CLI failed:\nSTDERR:\n{result.stderr[-1000:]}"
    combined = result.stdout + result.stderr
    assert "conviction" in combined.lower()
