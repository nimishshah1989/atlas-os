"""Daily inference orchestrator — Phase 4 entrypoint (#46).

Sequences the three v6 daily writers in a single transaction-shaped run:

1. :func:`atlas.features.scorecard_writer.compute_daily_scorecard`
2. :func:`atlas.regime.cron.compute_daily_regime`
3. :func:`atlas.decisions.cron.compute_daily_signal_calls`

and writes ONE row to ``atlas.atlas_provenance_log`` recording the SHA-256
hash of the input dataset (de_equity_ohlcv + de_index_prices at
``target_date``), the universe definition, and the running code commit.

Look-ahead audit (CONTEXT.md §"Look-ahead audit gate")
======================================================
Each phase already structurally clamps its queries to
``date <= target_date``. The orchestrator adds two further guarantees:

* ``target_date <= today`` — refuses to run inference against a future
  ``target_date`` (asserted at entry).
* The provenance row's ``ts`` (NOW()) is logged via structlog with a
  warning when ``ts > target_date + 1 day`` — a late cron run that may
  imply the IST window was missed.

Provenance log write-once
==========================
``atlas.atlas_provenance_log`` is guarded by a plpgsql trigger that
forbids ``UPDATE`` and ``DELETE`` (migration 087). We therefore:

* Compute the input/universe SHAs at run start (snapshot semantics — the
  hashes reflect the input dataset state at that moment).
* Accumulate per-phase row counts in memory across the run.
* INSERT the provenance row ONCE at the end with the complete
  ``output_row_range`` JSONB blob.

If a fatal exception is raised mid-pipeline we still attempt a best-effort
INSERT of a partial provenance row so the audit log records the failed
run. The exception is then re-raised.

Error semantics
===============
* **Non-fatal** errors (e.g. regime row absent for ``target_date``, threshold
  load fail with fallback) collect into ``DailyInferenceResult.errors``
  and the pipeline continues. PagerDuty signal raised via a structlog
  warning (``pagerduty:cron_failure``) — actual PD wiring lives outside
  this module.
* **Fatal** errors (DB connection lost, unrecoverable I/O) re-raised
  after best-effort provenance write.

Partial-run failsafe
====================
If the scorecard succeeds but the regime cron fails (or is skipped), the
downstream decisions cron will short-circuit on ``_load_regime`` returning
``None`` (recorded as an error in its result; no signal_calls written).
Operations should investigate before re-running — there is NO silent
fallback to a synthetic regime.

Performance target
==================
<5 min on EC2 t3.large for 727+ instruments (eng review §4). The
orchestrator itself adds < 5 s overhead (two SHA queries + one INSERT);
the bulk of the runtime is the three vectorised phases.
"""

# allow-large: single cohesive daily-cron orchestration — phase wrappers,
# SHA helpers, provenance row construction, late-run audit, and the
# entrypoint form one indivisible compute unit. Same shape as the per-phase
# crons (atlas/features/scorecard_writer.py, atlas/regime/cron.py): splitting
# would force shared mutable run-state across modules with no clean public
# seam (the helpers all share the same run_id + engine + errors list).

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from psycopg2.extras import Json
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, open_compute_session
from atlas.db import get_engine
from atlas.decisions.cron import SignalCallsWriteResult, compute_daily_signal_calls
from atlas.features.scorecard_writer import ScorecardWriteResult, compute_daily_scorecard
from atlas.regime.cron import RegimeWriteResult, compute_daily_regime

if TYPE_CHECKING:  # pragma: no cover - typing only
    from atlas.regime.classifier import RegimeState

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Schema + table for the provenance log row INSERT. Constants — never user
# input. (See migration 087 for the full DDL.)
_PROVENANCE_TABLE = "atlas.atlas_provenance_log"

# Columns we write. ``run_id`` and ``ts`` use server defaults but we pass
# them explicitly so the in-Python ``run_id`` matches what's persisted.
_PROVENANCE_COLUMNS: tuple[str, ...] = (
    "run_id",
    "ts",
    "input_dataset_sha256",
    "universe_definition_sha256",
    "code_commit_sha",
    "friction_params_row_ids",
    "output_table",
    "output_row_range",
    "run_type",
    "actor",
    "notes",
)

# Code commit SHA fallback when neither git nor env produces a value.
_UNKNOWN_COMMIT_SHA = "unknown"

# Run type value for this orchestrator. Free-form string per migration 087.
_RUN_TYPE = "daily_inference"

# Canonical output_table value for the provenance row. The orchestrator
# writes to multiple tables across phases (atlas_scorecard_daily,
# atlas_regime_daily, atlas_signal_calls); we record the *terminal* output
# table here because the daily run is fundamentally a signal-call producer
# and the JSONB output_row_range carries the per-phase counts.
_TERMINAL_OUTPUT_TABLE = "atlas_signal_calls"

# Late-run threshold — how many days past target_date is "late". One
# day is the contractual window (cron should fire within T+1 IST).
_LATE_RUN_WINDOW_DAYS = 1


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyInferenceResult:
    """Outcome of one :func:`compute_daily` invocation.

    Carries the three phase results plus the orchestrator-level metadata:
    provenance run UUID (matches the row in ``atlas_provenance_log``),
    total wall-clock runtime, and any non-fatal errors collected from the
    individual phases.
    """

    target_date: date
    scorecard: ScorecardWriteResult
    regime: RegimeWriteResult
    signal_calls: SignalCallsWriteResult
    provenance_run_id: UUID
    runtime_seconds: float
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SHA + commit helpers
# ---------------------------------------------------------------------------


def _compute_input_sha(engine: Engine, target_date: date) -> str:
    """SHA-256 of the OHLCV + index price snapshot at ``target_date``.

    Builds a deterministic fingerprint of the input dataset by hashing the
    sorted list of ``(instrument_id, date)`` tuples in
    ``de_equity_ohlcv`` plus the sorted ``(index_code, date)`` tuples in
    ``de_index_prices``, both clamped to ``date <= target_date``.

    Pure scalar SHA — never loaded into pandas. SQL ``string_agg`` builds
    the deterministic concatenated payload server-side; we hash the result
    once locally. Bounded by ~1M rows * ~40 bytes/row = ~40MB payload at
    the wire layer — well under our query budget.

    Returns a 64-char lowercase hex string (matches the CHECK constraint
    ``ck_atlas_provenance_log_input_dataset_sha256_hex``).
    """
    sql_ohlcv = """
        SELECT COALESCE(
          encode(
            digest(
              string_agg(payload, '|' ORDER BY payload),
              'sha256'
            ),
            'hex'
          ),
          repeat('0', 64)
        ) AS sha
        FROM (
          SELECT instrument_id::text || ':' || date::text AS payload
          FROM public.de_equity_ohlcv
          WHERE date <= %(target_date)s
        ) sub
    """
    sql_indices = """
        SELECT COALESCE(
          encode(
            digest(
              string_agg(payload, '|' ORDER BY payload),
              'sha256'
            ),
            'hex'
          ),
          repeat('0', 64)
        ) AS sha
        FROM (
          SELECT index_code || ':' || date::text AS payload
          FROM public.de_index_prices
          WHERE date <= %(target_date)s
        ) sub
    """
    try:
        with open_compute_session(engine) as conn:
            raw = conn.connection.cursor()
            try:
                raw.execute(sql_ohlcv, {"target_date": target_date})
                row = raw.fetchone()
                ohlcv_sha = (row[0] if row else None) or ("0" * 64)
                raw.execute(sql_indices, {"target_date": target_date})
                row = raw.fetchone()
                indices_sha = (row[0] if row else None) or ("0" * 64)
            finally:
                raw.close()
    except Exception as exc:
        # If the DB lacks the pgcrypto ``digest`` function (older test fixtures
        # or partial schemas), fall back to a local hash of an empty marker.
        # Production EC2 has pgcrypto enabled; this branch fires only in
        # unit tests, which patch the SHA helper anyway.
        log.warning("inference_input_sha_db_path_failed", error=str(exc))
        ohlcv_sha = hashlib.sha256(b"ohlcv:empty").hexdigest()
        indices_sha = hashlib.sha256(b"indices:empty").hexdigest()

    # Combine the two server-side digests into one deterministic SHA so the
    # provenance row stores a single fingerprint per the schema contract.
    combined = f"ohlcv={ohlcv_sha}|indices={indices_sha}|target_date={target_date.isoformat()}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _compute_universe_sha(engine: Engine, target_date: date) -> str:
    """SHA-256 of the active M1 universe at ``target_date``.

    The universe is read from ``atlas_universe_stocks`` where
    ``effective_to IS NULL`` (matches the scorecard writer's loader). We
    fingerprint the sorted instrument_ids — when ``atlas_universe_snapshot``
    ships in Phase 0.5a the loader will become point-in-time and this
    helper will switch to it.
    """
    sql = """
        SELECT COALESCE(
          encode(
            digest(
              string_agg(instrument_id::text, '|' ORDER BY instrument_id::text),
              'sha256'
            ),
            'hex'
          ),
          repeat('0', 64)
        ) AS sha
        FROM atlas.atlas_universe_stocks
        WHERE effective_to IS NULL
    """
    try:
        with open_compute_session(engine) as conn:
            raw = conn.connection.cursor()
            try:
                raw.execute(sql)
                row = raw.fetchone()
                sha = (row[0] if row else None) or ("0" * 64)
            finally:
                raw.close()
    except Exception as exc:
        log.warning("inference_universe_sha_db_path_failed", error=str(exc))
        sha = hashlib.sha256(b"universe:empty").hexdigest()

    # Hash again with the target_date so the same universe state at two
    # different audit dates produces distinct fingerprints (point-in-time
    # semantics, even though the loader is currently snapshot-as-of-now).
    combined = f"universe={sha}|target_date={target_date.isoformat()}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _detect_code_commit() -> str:
    """Best-effort detection of the current code commit SHA.

    Resolution order:

    1. ``ATLAS_GIT_SHA`` environment variable (set by deploy pipeline).
    2. ``git rev-parse HEAD`` from the package's repo root.
    3. ``_UNKNOWN_COMMIT_SHA`` (= ``"unknown"``) fallback.

    Always returns a non-empty string so the CHECK constraint
    ``ck_atlas_provenance_log_code_commit_sha_non_empty`` is satisfied.
    """
    env_sha = os.environ.get("ATLAS_GIT_SHA")
    if env_sha:
        return env_sha.strip()[:40]

    try:
        # Resolve repo root from this module's location (atlas/inference/daily.py
        # → repo root is two parents up).
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(  # noqa: S603 -- fixed argv list; no shell, no untrusted input
            ["git", "rev-parse", "HEAD"],  # noqa: S607 -- git on PATH is conventional
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("inference_git_detect_failed", error=str(exc))
        return _UNKNOWN_COMMIT_SHA

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()[:40]
    return _UNKNOWN_COMMIT_SHA


# ---------------------------------------------------------------------------
# Phase wrappers — each isolates a phase exception so the orchestrator
# can continue. Fatal exceptions are re-raised by the caller.
# ---------------------------------------------------------------------------


def _run_phase_scorecard(
    target_date: date,
    engine: Engine,
    *,
    write: bool,
    errors: list[str],
) -> ScorecardWriteResult:
    """Invoke the scorecard writer; capture non-fatal errors."""
    log.info("inference_phase_scorecard_start", target_date=str(target_date), write=write)
    try:
        return compute_daily_scorecard(target_date=target_date, db_engine=engine, write=write)
    except (ValueError, RuntimeError, KeyError, AssertionError) as exc:
        # Methodology / data-shape failures are non-fatal — log + return a
        # zeroed result so the next phase can proceed (or short-circuit on
        # its own preconditions).
        errors.append(f"scorecard:{type(exc).__name__}:{exc}")
        log.error(
            "pagerduty:cron_failure",
            phase="scorecard",
            target_date=str(target_date),
            error=str(exc),
        )
        return ScorecardWriteResult(target_date=target_date)


def _run_phase_regime(
    target_date: date,
    engine: Engine,
    *,
    write: bool,
    errors: list[str],
) -> RegimeWriteResult:
    """Invoke the regime cron; capture non-fatal errors."""
    log.info("inference_phase_regime_start", target_date=str(target_date), write=write)
    try:
        return compute_daily_regime(target_date=target_date, db_engine=engine, write=write)
    except (ValueError, RuntimeError, KeyError, AssertionError) as exc:
        errors.append(f"regime:{type(exc).__name__}:{exc}")
        log.error(
            "pagerduty:cron_failure",
            phase="regime",
            target_date=str(target_date),
            error=str(exc),
        )
        return RegimeWriteResult(target_date=target_date)


def _run_phase_signal_calls(
    target_date: date,
    engine: Engine,
    *,
    write: bool,
    errors: list[str],
) -> SignalCallsWriteResult:
    """Invoke the decisions cron; capture non-fatal errors.

    If the regime row is absent for ``target_date`` the inner cron records
    ``errors=1`` and returns; we propagate that into the orchestrator's
    error list as well so the failure is visible at the top level.
    """
    log.info("inference_phase_decisions_start", target_date=str(target_date), write=write)
    try:
        result = compute_daily_signal_calls(target_date=target_date, db_engine=engine, write=write)
    except (ValueError, RuntimeError, KeyError, AssertionError) as exc:
        errors.append(f"decisions:{type(exc).__name__}:{exc}")
        log.error(
            "pagerduty:cron_failure",
            phase="decisions",
            target_date=str(target_date),
            error=str(exc),
        )
        return SignalCallsWriteResult(target_date=target_date)

    if result.errors:
        errors.append(f"decisions:inner_errors={result.errors}")
    return result


# ---------------------------------------------------------------------------
# Provenance write
# ---------------------------------------------------------------------------


def _build_output_row_range(
    *,
    scorecard: ScorecardWriteResult,
    regime: RegimeWriteResult,
    signal_calls: SignalCallsWriteResult,
    target_date: date,
) -> dict[str, Any]:
    """Construct the ``output_row_range`` JSONB payload.

    Schema documented in migration 087:
        ``{"min_id": "<uuid>", "max_id": "<uuid>", "count": N,
           "date_range": [...]}``

    For the daily orchestrator we extend that contract with a ``runs``
    array carrying per-phase row counts so the row records the full
    pipeline outcome from one provenance row (avoids 3 separate rows for
    a single conceptual run).
    """
    return {
        "count": int(signal_calls.new_signals or 0),
        "date_range": [target_date.isoformat(), target_date.isoformat()],
        "runs": [
            {
                "phase": "scorecard",
                "table": "atlas_scorecard_daily",
                "rows_written": int(scorecard.rows_written or 0),
                "partial_day_count": int(scorecard.partial_day_count or 0),
                "missing_instruments": len(scorecard.missing_instruments or []),
                "runtime_seconds": float(scorecard.runtime_seconds or 0.0),
            },
            {
                "phase": "regime",
                "table": "atlas_regime_daily",
                "rows_written": int(regime.rows_written or 0),
                "state": regime.state.value if regime.state is not None else None,
                "threshold_source": regime.threshold_source,
                "runtime_seconds": float(regime.runtime_seconds or 0.0),
            },
            {
                "phase": "decisions",
                "table": "atlas_signal_calls",
                "rows_written": int(signal_calls.new_signals or 0),
                "hits_total": int(signal_calls.hits_total or 0),
                "reactivations": int(signal_calls.reactivations or 0),
                "skipped_open": int(signal_calls.skipped_open or 0),
                "errors": int(signal_calls.errors or 0),
                "runtime_seconds": float(signal_calls.runtime_seconds or 0.0),
            },
        ],
    }


def _write_provenance_row(
    engine: Engine,
    *,
    run_id: UUID,
    ts: datetime,
    input_sha: str,
    universe_sha: str,
    code_commit_sha: str,
    target_date: date,
    output_row_range: dict[str, Any],
    notes: str,
) -> int:
    """INSERT one row into ``atlas.atlas_provenance_log``.

    Write-once — see migration 087's trigger
    ``deny_update_delete_atlas_provenance_log``. Returns the
    ``bulk_upsert`` rowcount (always 1 on success).
    """
    row = (
        run_id,
        ts,
        input_sha,
        universe_sha,
        code_commit_sha,
        Json([]),  # friction_params_row_ids — populated when 081 lands
        _TERMINAL_OUTPUT_TABLE,
        Json(output_row_range),
        _RUN_TYPE,
        "system",
        notes,
    )
    return bulk_upsert(
        engine,
        table=_PROVENANCE_TABLE,
        columns=list(_PROVENANCE_COLUMNS),
        rows=[row],
        # ON CONFLICT (run_id) DO UPDATE — would never fire (UUIDs unique),
        # but the trigger denies UPDATE anyway. Using run_id as the
        # conflict target keeps bulk_upsert from rewriting any column on
        # the (impossible) collision path.
        pk_columns=["run_id"],
    )


def _maybe_warn_late_run(target_date: date, ts: datetime) -> None:
    """Emit a structlog warning if the run lands more than 1 day after target_date.

    Look-ahead audit gate cares about *forward* leak (the structural
    ``date <= target_date`` clamp handles that). The companion concern is
    *backward leak*: if the daily cron only fires several days after
    ``target_date`` the brief / portfolio downstream sees stale data.
    """
    cutoff = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC) + timedelta(
        days=_LATE_RUN_WINDOW_DAYS + 1
    )
    if ts > cutoff:
        log.warning(
            "inference_late_run",
            target_date=str(target_date),
            ts=ts.isoformat(),
            window_days=_LATE_RUN_WINDOW_DAYS,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compute_daily(
    target_date: date,
    db_engine: Engine | None = None,
    *,
    write: bool = True,
    code_commit_sha: str | None = None,
) -> DailyInferenceResult:
    """Run the full v6 daily inference pipeline at ``target_date``.

    Sequenced phases:

    1. Snapshot SHAs (input dataset, universe definition, code commit).
    2. :func:`compute_daily_scorecard` — writes ``atlas_scorecard_daily``.
    3. :func:`compute_daily_regime` — writes ``atlas_regime_daily``.
    4. :func:`compute_daily_signal_calls` — writes ``atlas_signal_calls``.
    5. INSERT one ``atlas_provenance_log`` row with per-phase counts.

    Args:
        target_date: the audit date. All phases use only data
            ``<= target_date``. Must not be in the future (asserted).
        db_engine: optional SQLAlchemy engine; defaults to the process-wide
            engine via :func:`atlas.db.get_engine`.
        write: when ``False``, every phase runs in dry-run mode (no DB
            writes) AND the provenance row is NOT inserted. Useful for
            backfill smoke tests.
        code_commit_sha: explicit override. When ``None`` we detect via
            ``ATLAS_GIT_SHA`` env var → ``git rev-parse HEAD`` → fallback.

    Returns:
        :class:`DailyInferenceResult` carrying all three phase results
        plus the provenance ``run_id``, total wall-clock seconds, and any
        non-fatal errors collected.

    Raises:
        AssertionError: if ``target_date`` is in the future (look-ahead
            guard).
        Any unhandled DB-level exception (e.g. ``psycopg2.OperationalError``
            on lost connection) — re-raised after a best-effort partial
            provenance write so the audit log records the failure.

    Performance:
        <5 min on EC2 t3.large for 727+ instruments (eng review §4). The
        orchestrator overhead is bounded by the two SHA queries + one
        INSERT (~5 s aggregate); the rest is the three vectorised phases.
    """
    today = datetime.now(UTC).date()
    assert (
        target_date <= today
    ), f"daily inference look-ahead violation: target_date={target_date} > today={today}"

    engine = db_engine or get_engine()
    started = time.time()
    run_id = uuid.uuid4()
    errors: list[str] = []

    log.info(
        "inference_daily_start",
        run_id=str(run_id),
        target_date=str(target_date),
        write=write,
    )

    # ---- Snapshot SHAs at run start ---------------------------------------
    # We compute these BEFORE running the phases so the SHAs reflect the
    # input state used by the phases. If a SHA computation fails (e.g.
    # pgcrypto missing in a test schema), the helper falls back to a
    # deterministic local hash — we never block the run on SHA I/O.
    input_sha = _compute_input_sha(engine, target_date)
    universe_sha = _compute_universe_sha(engine, target_date)
    resolved_code_sha = (code_commit_sha or _detect_code_commit() or _UNKNOWN_COMMIT_SHA).strip()
    if not resolved_code_sha:
        resolved_code_sha = _UNKNOWN_COMMIT_SHA

    log.info(
        "inference_provenance_snapshot",
        run_id=str(run_id),
        input_sha=input_sha[:12],
        universe_sha=universe_sha[:12],
        code_commit_sha=resolved_code_sha[:12],
    )

    # ---- Execute the three phases -----------------------------------------
    # Each wrapper isolates non-fatal failures (data-shape, methodology) so
    # the next phase still runs. Fatal infra failures (e.g. DB connection
    # lost) propagate up — we'll catch in the outer try/finally below to
    # still record the partial provenance row.
    scorecard_result: ScorecardWriteResult = ScorecardWriteResult(target_date=target_date)
    regime_result: RegimeWriteResult = RegimeWriteResult(target_date=target_date)
    signal_calls_result: SignalCallsWriteResult = SignalCallsWriteResult(target_date=target_date)
    fatal_exc: BaseException | None = None

    try:
        scorecard_result = _run_phase_scorecard(target_date, engine, write=write, errors=errors)
        regime_result = _run_phase_regime(target_date, engine, write=write, errors=errors)
        signal_calls_result = _run_phase_signal_calls(
            target_date, engine, write=write, errors=errors
        )
    except BaseException as exc:
        fatal_exc = exc
        errors.append(f"fatal:{type(exc).__name__}:{exc}")
        log.error(
            "pagerduty:cron_failure",
            phase="fatal",
            target_date=str(target_date),
            error=str(exc),
        )

    # ---- Build + write the provenance row ---------------------------------
    ts = datetime.now(UTC)
    output_row_range = _build_output_row_range(
        scorecard=scorecard_result,
        regime=regime_result,
        signal_calls=signal_calls_result,
        target_date=target_date,
    )
    notes = f"daily inference for {target_date.isoformat()}" + (
        f" (partial — fatal: {type(fatal_exc).__name__})" if fatal_exc is not None else ""
    )
    if write:
        try:
            _write_provenance_row(
                engine,
                run_id=run_id,
                ts=ts,
                input_sha=input_sha,
                universe_sha=universe_sha,
                code_commit_sha=resolved_code_sha,
                target_date=target_date,
                output_row_range=output_row_range,
                notes=notes,
            )
        except Exception as exc:
            # Provenance write failure is non-fatal at the orchestrator
            # level — the phase outputs already landed. Surface but don't
            # raise.
            errors.append(f"provenance:{type(exc).__name__}:{exc}")
            log.error(
                "pagerduty:cron_failure",
                phase="provenance",
                target_date=str(target_date),
                error=str(exc),
            )

    _maybe_warn_late_run(target_date, ts)

    runtime_seconds = round(time.time() - started, 3)
    result = DailyInferenceResult(
        target_date=target_date,
        scorecard=scorecard_result,
        regime=regime_result,
        signal_calls=signal_calls_result,
        provenance_run_id=run_id,
        runtime_seconds=runtime_seconds,
        errors=list(errors),
    )

    log.info(
        "inference_daily_complete",
        run_id=str(run_id),
        target_date=str(target_date),
        runtime_seconds=runtime_seconds,
        scorecard_rows=scorecard_result.rows_written,
        regime_state=regime_result.state.value if regime_result.state is not None else None,
        new_signals=signal_calls_result.new_signals,
        errors=len(errors),
    )

    if fatal_exc is not None:
        # Re-raise the original fatal exception now that provenance is
        # recorded.
        raise fatal_exc

    return result


# ---------------------------------------------------------------------------
# Public helpers — exported for the CLI + tests.
# ---------------------------------------------------------------------------


def _serialize_result(result: DailyInferenceResult) -> dict[str, Any]:
    """Render a :class:`DailyInferenceResult` as a JSON-safe dict.

    Used by :mod:`atlas.inference.cli` to print the run summary.
    """
    state: RegimeState | None = result.regime.state
    return {
        "target_date": str(result.target_date),
        "runtime_s": result.runtime_seconds,
        "scorecard_rows": int(result.scorecard.rows_written or 0),
        "scorecard_partial_day_count": int(result.scorecard.partial_day_count or 0),
        "regime_state": state.value if state is not None else None,
        "regime_threshold_source": result.regime.threshold_source,
        "new_signal_calls": int(result.signal_calls.new_signals or 0),
        "hits_total": int(result.signal_calls.hits_total or 0),
        "reactivations": int(result.signal_calls.reactivations or 0),
        "skipped_open": int(result.signal_calls.skipped_open or 0),
        "errors": list(result.errors),
        "provenance_run_id": str(result.provenance_run_id),
    }


def _result_to_json(result: DailyInferenceResult) -> str:
    """Convenience: :func:`_serialize_result` + ``json.dumps`` indent=2."""
    return json.dumps(_serialize_result(result), indent=2, sort_keys=True)


__all__ = [
    "DailyInferenceResult",
    "compute_daily",
]
