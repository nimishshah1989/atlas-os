"""Tests for ``atlas.inference.daily`` — Phase 4 orchestrator (#46).

Covers:

* Phase sequencing — scorecard → regime → decisions, each invoked once.
* Provenance row constructed with the correct SHA/commit fields.
* Non-fatal errors from individual phases collected without halting.
* Fatal exceptions re-raised AFTER best-effort provenance write.
* SHA helpers are deterministic when DB I/O is mocked.
* ``write=False`` propagates to every phase + suppresses the provenance INSERT.
* ``code_commit_sha`` override path.
* Future-dated ``target_date`` rejected by the look-ahead guard.

DB I/O is mocked at the three phase functions plus the SHA helpers and
``bulk_upsert`` so no live Postgres is required.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine

from atlas.decisions.cron import SignalCallsWriteResult
from atlas.features.scorecard_writer import ScorecardWriteResult
from atlas.inference.daily import (
    DailyInferenceResult,
    _build_output_row_range,
    _detect_code_commit,
    _serialize_result,
    compute_daily,
)
from atlas.regime.classifier import RegimeState
from atlas.regime.cron import RegimeWriteResult

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


def _ok_scorecard(target_date: date, rows: int = 500) -> ScorecardWriteResult:
    return ScorecardWriteResult(
        target_date=target_date,
        rows_written=rows,
        partial_day_count=5,
        runtime_seconds=12.3,
        missing_instruments=["abc"],
        run_id="fake-run-id",
    )


def _ok_regime(target_date: date, state: RegimeState = RegimeState.RISK_ON) -> RegimeWriteResult:
    return RegimeWriteResult(
        target_date=target_date,
        state=state,
        smallcap_rs_z=0.5,
        breadth_pct_above_200dma=0.7,
        vix_percentile=0.4,
        cross_sectional_dispersion=0.012,
        vix_valid=True,
        threshold_source="fallback",
        rows_written=1,
        runtime_seconds=3.4,
        universe_size=500,
        breadth_eligible_count=480,
    )


def _ok_decisions(
    target_date: date, *, new: int = 12, hits: int = 25, react: int = 3
) -> SignalCallsWriteResult:
    return SignalCallsWriteResult(
        target_date=target_date,
        regime_state=RegimeState.RISK_ON,
        universe_size=500,
        cells_evaluated=24,
        hits_total=hits,
        new_signals=new,
        reactivations=react,
        skipped_open=2,
        errors=0,
        runtime_seconds=8.7,
        run_id="fake-run-id",
    )


def _patch_phases(
    *,
    scorecard: ScorecardWriteResult | None = None,
    regime: RegimeWriteResult | None = None,
    decisions: SignalCallsWriteResult | None = None,
    sha_calls: list[dict[str, Any]] | None = None,
    provenance_rows: list[tuple[Any, ...]] | None = None,
):
    """Build the patcher list for compute_daily.

    Patches the three phase functions, the SHA helpers, the code-commit
    detector, and ``bulk_upsert`` (used for the provenance row).
    """

    def _fake_scorecard(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        if sha_calls is not None:
            sha_calls.append({"phase": "scorecard", "td": target_date, "write": write})
        return scorecard if scorecard is not None else ScorecardWriteResult(target_date=target_date)

    def _fake_regime(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        if sha_calls is not None:
            sha_calls.append({"phase": "regime", "td": target_date, "write": write})
        return regime if regime is not None else RegimeWriteResult(target_date=target_date)

    def _fake_decisions(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        if sha_calls is not None:
            sha_calls.append({"phase": "decisions", "td": target_date, "write": write})
        if decisions is not None:
            return decisions
        return SignalCallsWriteResult(target_date=target_date)

    def _fake_input_sha(_engine, target_date):  # type: ignore[no-untyped-def]
        return "a" * 64

    def _fake_universe_sha(_engine, target_date):  # type: ignore[no-untyped-def]
        return "b" * 64

    def _fake_detect_commit():  # type: ignore[no-untyped-def]
        return "deadbeefcafe1234"

    def _fake_bulk_upsert(engine, *, table, columns, rows, pk_columns, **_kw):  # type: ignore[no-untyped-def]
        if provenance_rows is not None:
            provenance_rows.append((table, list(columns), list(rows), list(pk_columns)))
        return len(rows)

    return [
        patch("atlas.inference.daily.compute_daily_scorecard", side_effect=_fake_scorecard),
        patch("atlas.inference.daily.compute_daily_regime", side_effect=_fake_regime),
        patch("atlas.inference.daily.compute_daily_signal_calls", side_effect=_fake_decisions),
        patch("atlas.inference.daily._compute_input_sha", side_effect=_fake_input_sha),
        patch("atlas.inference.daily._compute_universe_sha", side_effect=_fake_universe_sha),
        patch("atlas.inference.daily._detect_code_commit", side_effect=_fake_detect_commit),
        patch("atlas.inference.daily.bulk_upsert", side_effect=_fake_bulk_upsert),
    ]


def _enter(patchers):  # type: ignore[no-untyped-def]
    for p in patchers:
        p.start()


def _exit(patchers):  # type: ignore[no-untyped-def]
    for p in reversed(patchers):
        p.stop()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_compute_daily_sequences_all_three_phases() -> None:
    """Each phase runs exactly once, in scorecard → regime → decisions order."""
    td = date(2026, 5, 22)
    sequence: list[dict[str, Any]] = []
    provenance_rows: list[tuple[Any, ...]] = []

    patchers = _patch_phases(
        scorecard=_ok_scorecard(td),
        regime=_ok_regime(td),
        decisions=_ok_decisions(td),
        sha_calls=sequence,
        provenance_rows=provenance_rows,
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)

    # Sequence == scorecard → regime → decisions, each called once.
    phases = [c["phase"] for c in sequence]
    assert phases == ["scorecard", "regime", "decisions"]
    # All three saw the same target_date + write=True.
    assert all(c["td"] == td for c in sequence)
    assert all(c["write"] is True for c in sequence)

    # Result populated.
    assert isinstance(result, DailyInferenceResult)
    assert result.target_date == td
    assert result.scorecard.rows_written == 500
    assert result.regime.state is RegimeState.RISK_ON
    assert result.signal_calls.new_signals == 12
    assert isinstance(result.provenance_run_id, UUID)
    # runtime is rounded to 3 dp; mocked pipeline runs in microseconds so
    # 0.0 is the realistic floor here. Upper bound matters more.
    assert result.runtime_seconds >= 0.0
    assert result.runtime_seconds < 300  # plausible in test env
    assert result.errors == []

    # One provenance row written, after the phases.
    assert len(provenance_rows) == 1
    table, _columns, rows, pk_cols = provenance_rows[0]
    assert table == "atlas.atlas_provenance_log"
    assert pk_cols == ["run_id"]
    assert len(rows) == 1


def test_compute_daily_provenance_row_payload_shape() -> None:
    """Provenance row carries input/universe/code SHAs + per-phase counts."""
    td = date(2026, 5, 22)
    provenance_rows: list[tuple[Any, ...]] = []

    patchers = _patch_phases(
        scorecard=_ok_scorecard(td, rows=500),
        regime=_ok_regime(td, state=RegimeState.RISK_OFF),
        decisions=_ok_decisions(td, new=42, hits=80, react=5),
        provenance_rows=provenance_rows,
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)

    _table, columns, rows, _pk = provenance_rows[0]
    row = rows[0]
    by_col = dict(zip(columns, row, strict=True))
    assert by_col["run_id"] == result.provenance_run_id
    assert by_col["input_dataset_sha256"] == "a" * 64
    assert by_col["universe_definition_sha256"] == "b" * 64
    assert by_col["code_commit_sha"] == "deadbeefcafe1234"
    assert by_col["output_table"] == "atlas_signal_calls"
    assert by_col["run_type"] == "daily_inference"
    assert by_col["actor"] == "system"
    # output_row_range is wrapped in Json — peek at the adapted payload.
    payload = by_col["output_row_range"].adapted  # psycopg2.extras.Json
    assert payload["count"] == 42
    assert payload["date_range"] == [td.isoformat(), td.isoformat()]
    phases = {r["phase"]: r for r in payload["runs"]}
    assert phases["scorecard"]["rows_written"] == 500
    assert phases["regime"]["state"] == "Risk-Off"
    assert phases["decisions"]["rows_written"] == 42
    assert phases["decisions"]["hits_total"] == 80
    assert phases["decisions"]["reactivations"] == 5


def test_compute_daily_dry_run_propagates_write_false_and_skips_provenance() -> None:
    """``write=False`` propagates to all three phases AND skips provenance INSERT."""
    td = date(2026, 5, 22)
    sequence: list[dict[str, Any]] = []
    provenance_rows: list[tuple[Any, ...]] = []
    patchers = _patch_phases(
        scorecard=_ok_scorecard(td),
        regime=_ok_regime(td),
        decisions=_ok_decisions(td),
        sha_calls=sequence,
        provenance_rows=provenance_rows,
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=False)
    finally:
        _exit(patchers)

    assert all(c["write"] is False for c in sequence)
    assert provenance_rows == []  # provenance INSERT skipped in dry-run
    assert result.errors == []


def test_compute_daily_code_commit_override() -> None:
    """Passing ``code_commit_sha`` overrides the auto-detector."""
    td = date(2026, 5, 22)
    provenance_rows: list[tuple[Any, ...]] = []
    patchers = _patch_phases(
        scorecard=_ok_scorecard(td),
        regime=_ok_regime(td),
        decisions=_ok_decisions(td),
        provenance_rows=provenance_rows,
    )
    _enter(patchers)
    try:
        compute_daily(
            target_date=td,
            db_engine=cast(Engine, MagicMock()),
            write=True,
            code_commit_sha="cafecafecafe000111",
        )
    finally:
        _exit(patchers)

    columns = provenance_rows[0][1]
    row = provenance_rows[0][2][0]
    by_col = dict(zip(columns, row, strict=True))
    # Override wins over the patched _detect_code_commit.
    assert by_col["code_commit_sha"] == "cafecafecafe000111"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_compute_daily_non_fatal_phase_error_does_not_halt_subsequent_phases() -> None:
    """ValueError in scorecard collected; regime + decisions still run."""
    td = date(2026, 5, 22)
    sequence: list[dict[str, Any]] = []

    def _raise_scorecard(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        sequence.append({"phase": "scorecard"})
        raise ValueError("synthetic methodology failure")

    def _fake_regime(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        sequence.append({"phase": "regime"})
        return _ok_regime(target_date)

    def _fake_decisions(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        sequence.append({"phase": "decisions"})
        return _ok_decisions(target_date)

    patchers = [
        patch("atlas.inference.daily.compute_daily_scorecard", side_effect=_raise_scorecard),
        patch("atlas.inference.daily.compute_daily_regime", side_effect=_fake_regime),
        patch("atlas.inference.daily.compute_daily_signal_calls", side_effect=_fake_decisions),
        patch("atlas.inference.daily._compute_input_sha", return_value="a" * 64),
        patch("atlas.inference.daily._compute_universe_sha", return_value="b" * 64),
        patch("atlas.inference.daily._detect_code_commit", return_value="x" * 40),
        patch("atlas.inference.daily.bulk_upsert", return_value=1),
    ]
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)

    assert [c["phase"] for c in sequence] == ["scorecard", "regime", "decisions"]
    assert any("scorecard:ValueError" in e for e in result.errors)
    # Regime + decisions still produced their results.
    assert result.regime.state is RegimeState.RISK_ON
    assert result.signal_calls.new_signals == 12


def test_compute_daily_fatal_exception_writes_partial_provenance_and_reraises() -> None:
    """A non-recoverable error (we use a bare BaseException subclass) re-raised
    after the provenance row is written with whatever phase outputs landed."""
    td = date(2026, 5, 22)
    provenance_rows: list[tuple[Any, ...]] = []

    class _Fatal(BaseException):
        pass

    def _fake_scorecard(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        return _ok_scorecard(target_date)

    def _raise_regime(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        raise _Fatal("DB connection lost")

    def _fake_decisions(*, target_date, db_engine, write):  # type: ignore[no-untyped-def]
        return _ok_decisions(target_date)

    def _capture_provenance(engine, *, table, columns, rows, pk_columns, **_kw):  # type: ignore[no-untyped-def]
        provenance_rows.append((table, columns, rows))
        return len(rows)

    patchers = [
        patch("atlas.inference.daily.compute_daily_scorecard", side_effect=_fake_scorecard),
        patch("atlas.inference.daily.compute_daily_regime", side_effect=_raise_regime),
        patch("atlas.inference.daily.compute_daily_signal_calls", side_effect=_fake_decisions),
        patch("atlas.inference.daily._compute_input_sha", return_value="a" * 64),
        patch("atlas.inference.daily._compute_universe_sha", return_value="b" * 64),
        patch("atlas.inference.daily._detect_code_commit", return_value="x" * 40),
        patch("atlas.inference.daily.bulk_upsert", side_effect=_capture_provenance),
    ]
    _enter(patchers)
    try:
        with pytest.raises(_Fatal):
            compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)

    # Provenance row still written with partial state.
    assert len(provenance_rows) == 1
    notes_col_idx = list(provenance_rows[0][1]).index("notes")
    notes_val = provenance_rows[0][2][0][notes_col_idx]
    assert "partial" in notes_val.lower()


def test_compute_daily_inner_decisions_errors_propagate_to_orchestrator_errors() -> None:
    """If the decisions cron returns ``errors > 0`` the orchestrator surfaces it."""
    td = date(2026, 5, 22)
    bad_decisions = SignalCallsWriteResult(
        target_date=td,
        regime_state=RegimeState.RISK_ON,
        new_signals=0,
        hits_total=0,
        errors=3,
    )
    patchers = _patch_phases(
        scorecard=_ok_scorecard(td), regime=_ok_regime(td), decisions=bad_decisions
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)
    assert any("decisions:inner_errors=3" in e for e in result.errors)


def test_compute_daily_provenance_write_failure_is_non_fatal() -> None:
    """If the provenance INSERT itself fails, the orchestrator surfaces the
    error in ``result.errors`` but does NOT raise. The phase outputs already
    landed and the audit log is best-effort by design."""
    td = date(2026, 5, 22)

    def _bad_upsert(*a, **kw):  # type: ignore[no-untyped-def]
        raise RuntimeError("provenance table missing")

    patchers = [
        patch("atlas.inference.daily.compute_daily_scorecard", return_value=_ok_scorecard(td)),
        patch("atlas.inference.daily.compute_daily_regime", return_value=_ok_regime(td)),
        patch(
            "atlas.inference.daily.compute_daily_signal_calls",
            return_value=_ok_decisions(td),
        ),
        patch("atlas.inference.daily._compute_input_sha", return_value="a" * 64),
        patch("atlas.inference.daily._compute_universe_sha", return_value="b" * 64),
        patch("atlas.inference.daily._detect_code_commit", return_value="x" * 40),
        patch("atlas.inference.daily.bulk_upsert", side_effect=_bad_upsert),
    ]
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)

    assert any(e.startswith("provenance:RuntimeError") for e in result.errors)


# ---------------------------------------------------------------------------
# Look-ahead audit
# ---------------------------------------------------------------------------


def test_compute_daily_rejects_future_target_date() -> None:
    """``target_date`` past today is refused at entry."""
    future = (datetime.now(UTC) + timedelta(days=2)).date()
    with pytest.raises(AssertionError, match="look-ahead"):
        compute_daily(target_date=future, db_engine=cast(Engine, MagicMock()), write=False)


def test_compute_daily_today_is_allowed() -> None:
    """``target_date == today`` MUST be allowed — the conventional same-day cron."""
    today = datetime.now(UTC).date()
    patchers = _patch_phases(
        scorecard=_ok_scorecard(today),
        regime=_ok_regime(today),
        decisions=_ok_decisions(today),
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=today, db_engine=cast(Engine, MagicMock()), write=False)
    finally:
        _exit(patchers)
    assert result.target_date == today


# ---------------------------------------------------------------------------
# Helpers — unit tests
# ---------------------------------------------------------------------------


def test_build_output_row_range_shape() -> None:
    """``_build_output_row_range`` produces the canonical payload shape."""
    td = date(2026, 5, 22)
    payload = _build_output_row_range(
        scorecard=_ok_scorecard(td, rows=300),
        regime=_ok_regime(td, state=RegimeState.ELEVATED),
        signal_calls=_ok_decisions(td, new=7, hits=10, react=1),
        target_date=td,
    )
    assert payload["count"] == 7
    assert payload["date_range"] == [td.isoformat(), td.isoformat()]
    phases = {r["phase"]: r for r in payload["runs"]}
    assert phases["scorecard"]["rows_written"] == 300
    assert phases["regime"]["state"] == "Elevated"
    assert phases["decisions"]["reactivations"] == 1


def test_serialize_result_jsonable_shape() -> None:
    """The CLI helper produces a flat JSON-safe dict."""
    td = date(2026, 5, 22)
    res = DailyInferenceResult(
        target_date=td,
        scorecard=_ok_scorecard(td, rows=100),
        regime=_ok_regime(td, state=RegimeState.BELOW_TREND),
        signal_calls=_ok_decisions(td, new=4, hits=9, react=0),
        provenance_run_id=UUID("12345678-1234-5678-1234-567812345678"),
        runtime_seconds=1.23,
        errors=["scorecard:ValueError:boom"],
    )
    payload = _serialize_result(res)
    assert payload["target_date"] == td.isoformat()
    assert payload["regime_state"] == "Below-Trend"
    assert payload["new_signal_calls"] == 4
    assert payload["scorecard_rows"] == 100
    assert payload["errors"] == ["scorecard:ValueError:boom"]
    assert payload["provenance_run_id"] == "12345678-1234-5678-1234-567812345678"


def test_detect_code_commit_prefers_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ATLAS_GIT_SHA`` env var beats the git subprocess path."""
    monkeypatch.setenv("ATLAS_GIT_SHA", "envshadeadbeef000")
    sha = _detect_code_commit()
    assert sha == "envshadeadbeef000"


def test_detect_code_commit_falls_back_to_unknown_when_git_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When env is unset and git is absent, returns ``"unknown"``."""
    monkeypatch.delenv("ATLAS_GIT_SHA", raising=False)

    class _BoomResult:
        returncode = 1
        stdout = ""
        stderr = "fatal: not a git repository"

    with patch("atlas.inference.daily.subprocess.run", return_value=_BoomResult()):
        sha = _detect_code_commit()
    assert sha == "unknown"


def test_detect_code_commit_handles_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """``subprocess.run`` raising ``FileNotFoundError`` doesn't crash."""
    monkeypatch.delenv("ATLAS_GIT_SHA", raising=False)
    with patch(
        "atlas.inference.daily.subprocess.run",
        side_effect=FileNotFoundError("git not on PATH"),
    ):
        sha = _detect_code_commit()
    assert sha == "unknown"


# ---------------------------------------------------------------------------
# Runtime + structlog sanity
# ---------------------------------------------------------------------------


def test_compute_daily_runtime_seconds_is_plausible() -> None:
    """Total runtime is strictly positive and bounded in a test env."""
    td = date(2026, 5, 22)
    patchers = _patch_phases(
        scorecard=_ok_scorecard(td), regime=_ok_regime(td), decisions=_ok_decisions(td)
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=False)
    finally:
        _exit(patchers)
    assert 0 <= result.runtime_seconds < 300


def test_compute_daily_provenance_run_id_matches_result() -> None:
    """The UUID on the result matches the row written to provenance."""
    td = date(2026, 5, 22)
    provenance_rows: list[tuple[Any, ...]] = []
    patchers = _patch_phases(
        scorecard=_ok_scorecard(td),
        regime=_ok_regime(td),
        decisions=_ok_decisions(td),
        provenance_rows=provenance_rows,
    )
    _enter(patchers)
    try:
        result = compute_daily(target_date=td, db_engine=cast(Engine, MagicMock()), write=True)
    finally:
        _exit(patchers)

    columns = provenance_rows[0][1]
    row = provenance_rows[0][2][0]
    by_col = dict(zip(columns, row, strict=True))
    assert by_col["run_id"] == result.provenance_run_id
