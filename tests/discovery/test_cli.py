"""Tests for :mod:`atlas.discovery.cli`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.discovery.cli import _build_parser, run_sweep_cli


def _last_json_block(stdout: str) -> dict:
    """Parse the last JSON block on stdout.

    structlog writes log lines to stdout in addition to the CLI's
    ``print(json.dumps(...))`` summary. The summary is always the last
    well-formed JSON block — we walk backward from EOF until a json.loads
    succeeds.
    """
    # The summary is pretty-printed with indent=2; find the last '{' that
    # starts a balanced block at column 0 (the top-level dict).
    lines = stdout.splitlines()
    # Find the start of the last block beginning at col 0 with '{'.
    start = None
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].startswith("}"):
            # found the end; walk back to find the start.
            for j in range(idx, -1, -1):
                if lines[j].startswith("{"):
                    start = j
                    end = idx
                    break
            break
    if start is None:
        raise AssertionError(f"no JSON block found in stdout: {stdout!r}")
    return json.loads("\n".join(lines[start : end + 1]))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_defaults() -> None:
    p = _build_parser()
    args = p.parse_args([])
    assert args.mode == "synthetic"
    assert args.dry_run is False
    assert args.output_html is None
    assert args.synthetic_seed == 42


def test_parser_dry_run_flag() -> None:
    p = _build_parser()
    args = p.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parser_mode_choices() -> None:
    p = _build_parser()
    for mode in ("synthetic", "cache", "supabase", "ec2"):
        args = p.parse_args(["--mode", mode])
        assert args.mode == mode


def test_parser_rejects_invalid_mode() -> None:
    p = _build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--mode", "bogus"])


def test_parser_output_html_path(tmp_path: Path) -> None:
    out = tmp_path / "foo.html"
    p = _build_parser()
    args = p.parse_args(["--output-html", str(out)])
    assert args.output_html == str(out)


def test_parser_synthetic_seed() -> None:
    p = _build_parser()
    args = p.parse_args(["--synthetic-seed", "1729"])
    assert args.synthetic_seed == 1729


# ---------------------------------------------------------------------------
# run_sweep_cli — smoke tests
# ---------------------------------------------------------------------------


def test_run_sweep_cli_dry_run_synthetic_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run_sweep_cli(["--mode", "synthetic", "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    summary = _last_json_block(captured.out)
    assert summary["mode"] == "synthetic"
    assert summary["total_cells"] == 24
    assert summary["validated"] >= 2


def test_run_sweep_cli_dry_run_does_not_call_engine() -> None:
    """--dry-run must NOT construct the DB engine (no creds needed)."""
    with patch("atlas.discovery.cli._make_engine") as mock_engine:
        rc = run_sweep_cli(["--mode", "synthetic", "--dry-run"])
        assert rc == 0
        mock_engine.assert_not_called()


def test_run_sweep_cli_writes_html(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "matrix.html"
    rc = run_sweep_cli(["--mode", "synthetic", "--dry-run", "--output-html", str(out)])
    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr()
    summary = _last_json_block(captured.out)
    assert summary["output_html"] == str(out)


def test_run_sweep_cli_creates_parent_dirs(tmp_path: Path) -> None:
    """Parent directories of --output-html are auto-created."""
    out = tmp_path / "deeper" / "still_deeper" / "matrix.html"
    rc = run_sweep_cli(["--mode", "synthetic", "--dry-run", "--output-html", str(out)])
    assert rc == 0
    assert out.exists()


def test_run_sweep_cli_cache_mode_returns_2_when_files_missing(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cache mode without cache pickles → FileNotFoundError → CLI exit 2."""
    # Point the cache loader at an empty tmp_path so FileNotFoundError fires
    # regardless of whether /tmp has real cache pickles on this developer
    # laptop.
    import atlas.discovery.engine as engine_mod

    monkeypatch.setattr(engine_mod, "DEFAULT_CACHE_DIR", tmp_path)
    rc = run_sweep_cli(["--mode", "cache", "--dry-run"])
    assert rc == 2
    captured = capsys.readouterr()
    payload = json.loads([ln for ln in captured.out.splitlines() if ln.startswith("{")][-1])
    assert (
        "missing cache files" in payload["error"].lower()
        or "scp from ec2" in payload["error"].lower()
    )


def test_run_sweep_cli_supabase_mode_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run_sweep_cli(["--mode", "supabase", "--dry-run"])
    assert rc == 2
    captured = capsys.readouterr()
    payload = json.loads([ln for ln in captured.out.splitlines() if ln.startswith("{")][-1])
    assert "supabase" in payload["error"].lower() or "not implemented" in payload["error"].lower()


def test_run_sweep_cli_ec2_mode_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run_sweep_cli(["--mode", "ec2", "--dry-run"])
    assert rc == 2


def test_run_sweep_cli_deterministic_seed(capsys: pytest.CaptureFixture[str]) -> None:
    """Same seed → same summary stats across two CLI invocations."""
    run_sweep_cli(["--mode", "synthetic", "--dry-run", "--synthetic-seed", "42"])
    first = _last_json_block(capsys.readouterr().out)
    run_sweep_cli(["--mode", "synthetic", "--dry-run", "--synthetic-seed", "42"])
    second = _last_json_block(capsys.readouterr().out)
    assert first["validated"] == second["validated"]
    assert first["no_conviction"] == second["no_conviction"]
