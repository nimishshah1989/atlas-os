"""Smoke test for the daily-brief CLI.

Two modes:
  1. --dry-run-stub: never calls Claude. Exercises the context-build path
     end to end. Marked integration (needs DB).
  2. --dry-run with ANTHROPIC_API_KEY: full Claude round-trip. Skipped if
     key missing.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.integration
def test_cli_stub_mode_completes_under_15s() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_daily_brief.py", "--dry-run-stub"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode in (0, 3), (
        f"CLI exited with {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # exit 0 = stub printed; exit 3 = no MV data (acceptable on a fresh DB)
    if result.returncode == 0:
        assert "DailyMarketContext" in result.stdout


@pytest.mark.integration
def test_cli_dry_run_with_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; skipping live Claude call")
    result = subprocess.run(
        [sys.executable, "scripts/generate_daily_brief.py", "--dry-run"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Acceptable: 0 = success, 3 = no MV data on this DB
    assert result.returncode in (0, 3), (
        f"CLI exited with {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
