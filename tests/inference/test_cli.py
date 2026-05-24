"""Tests for ``atlas.inference.cli`` — daily cron CLI wrapper (#46)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from atlas.decisions.cron import SignalCallsWriteResult
from atlas.features.scorecard_writer import ScorecardWriteResult
from atlas.inference.cli import _build_parser, _yesterday_ist, main
from atlas.inference.daily import DailyInferenceResult
from atlas.regime.classifier import RegimeState
from atlas.regime.cron import RegimeWriteResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_result(
    td: date,
    *,
    errors: list[str] | None = None,
    provenance_uuid: UUID | None = None,
) -> DailyInferenceResult:
    return DailyInferenceResult(
        target_date=td,
        scorecard=ScorecardWriteResult(target_date=td, rows_written=500),
        regime=RegimeWriteResult(target_date=td, state=RegimeState.RISK_ON, rows_written=1),
        signal_calls=SignalCallsWriteResult(
            target_date=td, regime_state=RegimeState.RISK_ON, new_signals=7
        ),
        provenance_run_id=provenance_uuid or UUID("12345678-1234-5678-1234-567812345678"),
        runtime_seconds=1.23,
        errors=errors or [],
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_target_date_iso() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--target-date", "2026-05-22"])
    assert args.target_date == date(2026, 5, 22)


def test_parser_default_target_date_is_none() -> None:
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.target_date is None
    assert args.dry_run is False
    assert args.code_commit_sha is None


def test_parser_dry_run_and_commit_sha() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--dry-run", "--code-commit-sha", "abc123"])
    assert args.dry_run is True
    assert args.code_commit_sha == "abc123"


def test_parser_rejects_invalid_date() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--target-date", "not-a-date"])


# ---------------------------------------------------------------------------
# _yesterday_ist
# ---------------------------------------------------------------------------


def test_yesterday_ist_is_one_calendar_day_before_now_ist() -> None:
    """The default target_date is yesterday in IST (UTC+5:30)."""
    yest = _yesterday_ist()
    now_ist = (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()
    # Allow a 1-day tolerance around midnight UTC transitions.
    delta = (now_ist - yest).days
    assert delta in (1, 2), f"expected 1-2 days before now_ist, got {delta}"


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------


def _patch_main_io(
    *,
    result: DailyInferenceResult | None = None,
    fatal: BaseException | None = None,
    captured_kwargs: dict[str, Any] | None = None,
):
    def _fake_compute(
        *,
        target_date,  # type: ignore[no-untyped-def]
        db_engine,
        write,
        code_commit_sha,
    ):
        if captured_kwargs is not None:
            captured_kwargs.update(
                {
                    "target_date": target_date,
                    "write": write,
                    "code_commit_sha": code_commit_sha,
                }
            )
        if fatal is not None:
            raise fatal
        assert result is not None
        return result

    return [
        patch("atlas.inference.cli._make_engine", return_value=MagicMock()),
        patch("atlas.inference.cli.compute_daily", side_effect=_fake_compute),
    ]


def _enter(patchers):  # type: ignore[no-untyped-def]
    for p in patchers:
        p.start()


def _exit(patchers):  # type: ignore[no-untyped-def]
    for p in reversed(patchers):
        p.stop()


def test_main_exit_code_0_on_clean_run(capsys: pytest.CaptureFixture[str]) -> None:
    td = date(2026, 5, 22)
    patchers = _patch_main_io(result=_ok_result(td, errors=[]))
    _enter(patchers)
    try:
        code = main(["--target-date", "2026-05-22"])
    finally:
        _exit(patchers)
    assert code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["target_date"] == "2026-05-22"
    assert parsed["errors"] == []
    assert parsed["new_signal_calls"] == 7


def test_main_exit_code_1_on_non_fatal_errors(capsys: pytest.CaptureFixture[str]) -> None:
    td = date(2026, 5, 22)
    patchers = _patch_main_io(result=_ok_result(td, errors=["regime:ValueError:boom"]))
    _enter(patchers)
    try:
        code = main(["--target-date", "2026-05-22"])
    finally:
        _exit(patchers)
    assert code == 1
    parsed = json.loads(capsys.readouterr().out)
    assert "regime:ValueError:boom" in parsed["errors"]


def test_main_exit_code_2_on_fatal_exception(capsys: pytest.CaptureFixture[str]) -> None:
    patchers = _patch_main_io(fatal=RuntimeError("DB lost"))
    _enter(patchers)
    try:
        code = main(["--target-date", "2026-05-22"])
    finally:
        _exit(patchers)
    assert code == 2
    out = capsys.readouterr().out
    assert "RuntimeError" in out


def test_main_dry_run_propagates_write_false() -> None:
    td = date(2026, 5, 22)
    captured: dict[str, Any] = {}
    patchers = _patch_main_io(result=_ok_result(td), captured_kwargs=captured)
    _enter(patchers)
    try:
        code = main(["--target-date", "2026-05-22", "--dry-run"])
    finally:
        _exit(patchers)
    assert code == 0
    assert captured["write"] is False


def test_main_passes_code_commit_sha_override() -> None:
    td = date(2026, 5, 22)
    captured: dict[str, Any] = {}
    patchers = _patch_main_io(result=_ok_result(td), captured_kwargs=captured)
    _enter(patchers)
    try:
        main(["--target-date", "2026-05-22", "--code-commit-sha", "feedface"])
    finally:
        _exit(patchers)
    assert captured["code_commit_sha"] == "feedface"


def test_main_default_target_date_is_yesterday_ist() -> None:
    """When --target-date is omitted, main uses _yesterday_ist()."""
    td = _yesterday_ist()
    captured: dict[str, Any] = {}
    patchers = _patch_main_io(result=_ok_result(td), captured_kwargs=captured)
    _enter(patchers)
    try:
        code = main([])
    finally:
        _exit(patchers)
    assert code == 0
    assert captured["target_date"] == td
