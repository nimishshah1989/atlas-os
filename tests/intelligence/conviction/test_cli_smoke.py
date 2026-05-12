"""End-to-end smoke for the conviction CLI (dry-run only — no DB writes)."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.integration
def test_cli_dry_run_end_to_end() -> None:
    """The CLI dry-run should run, print a summary, exit 0."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/compute_conviction.py"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"CLI failed:\nSTDERR:\n{result.stderr[-1000:]}"
    # Either the structured log shows conviction_computed or the summary printed.
    combined = result.stdout + result.stderr
    assert "conviction" in combined.lower()
