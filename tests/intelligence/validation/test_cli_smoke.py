"""Smoke test for run_signal_validation.py CLI — SP01 Task 8.

Integration test: hits the real DB over a short date range.
Marked with @pytest.mark.integration — excluded from fast unit runs.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.integration
def test_cli_smoke_exit_0_and_tearsheet_content(tmp_path: pytest.TempPathFactory) -> None:
    """Run CLI over a short date window; assert exit 0 and markdown content."""
    output_file = tmp_path / "smoke_tearsheet.md"  # type: ignore[operator]

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/run_signal_validation.py",
            "--signal",
            "decision_state",
            "--periods",
            "5,21",
            "--rolling-window",
            "3M",
            "--start",
            "2024-10-01",
            "--end",
            "2025-01-31",
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"CLI exited with code {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert output_file.exists(), "Output markdown file was not created"

    content = output_file.read_text(encoding="utf-8")
    assert "decision_state" in content, "Tearsheet missing signal name"
    assert "Mean IC" in content, "Tearsheet missing 'Mean IC' column header"


@pytest.mark.integration
def test_cli_unsupported_signal_exits_2(tmp_path: pytest.TempPathFactory) -> None:
    """Unknown signal name must return exit code 2."""
    output_file = tmp_path / "bad_signal.md"  # type: ignore[operator]

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/run_signal_validation.py",
            "--signal",
            "nonexistent_signal",
            "--periods",
            "5",
            "--start",
            "2024-10-01",
            "--end",
            "2024-12-31",
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
