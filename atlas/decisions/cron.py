"""Daily decisions cron — Phase 4 entry point (#45).

Orchestrates the daily inference:

1. Read :py:meth:`atlas.atlas_scorecard_daily` rows for ``target_date``.
2. Read :py:meth:`atlas.atlas_regime_daily` (single row) for ``target_date``.
3. Read :py:meth:`atlas.atlas_cell_definitions` rows where
   ``deprecated_at IS NULL`` (drift_warn cells still fire — advisory mode
   per CONTEXT.md §"Cell deprecation (REVISED post adversarial review)").
4. Evaluate every (row × cell) via :func:`atlas.decisions.evaluator.evaluate_all_cells`.
5. For each *hit*, check the open-positions partial index to determine
   whether a fresh ``signal_call_id`` should be minted (trigger-only
   cadence per CONTEXT.md §"signal_call_id").
6. Bulk-INSERT the new ``atlas_signal_calls`` rows.

Trigger-only cadence
--------------------
``atlas_signal_calls`` is a **tall event table**. A row is written ONLY on
INACTIVE → ACTIVE transitions for ``(instrument_id, cell_id, tenure)``.
If a position is already open (``exit_date IS NULL``) on the same domain
tuple, the cron SKIPS writing — the existing ``signal_call_id`` stays
load-bearing for the brief / portfolio / ledger correlation chain.

A re-entry after exit (``exit_date IS NOT NULL`` on the prior row, then
the cell re-fires today) gets a fresh ``signal_call_id`` per
CONTEXT.md — same domain tuple, distinct row. The open-positions index
``ix_atlas_signal_calls_open`` only includes rows with
``exit_date IS NULL``, so the open-check naturally returns no match in
this case.

Idempotency
-----------
Within one cron run, the same (iid, cell, tenure) can hit at most once
(de-duped before writing). Across runs, the same target_date re-run will
not write duplicate rows because the open-check filter is identical.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, open_compute_session
from atlas.db import get_engine
from atlas.decisions.evaluator import EvaluationResult, evaluate_all_cells
from atlas.regime.classifier import RegimeState

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------


@dataclass
class SignalCallsWriteResult:
    """Outcome of one :func:`compute_daily_signal_calls` invocation."""

    target_date: date | None = None
    regime_state: RegimeState | None = None
    universe_size: int = 0
    cells_evaluated: int = 0
    hits_total: int = 0
    new_signals: int = 0
    reactivations: int = 0
    skipped_open: int = 0
    errors: int = 0
    runtime_seconds: float = 0.0
    run_id: str | None = None
    extras: dict = field(default_factory=dict)


# Columns the cron writes into atlas_signal_calls. id is auto-generated
# server-side; computed_at defaults to NOW(); exit_* columns left NULL on
# insert (set by atlas/ledger/ when the exit fires).
SIGNAL_CALL_COLUMNS: tuple[str, ...] = (
    "signal_call_id",
    "instrument_id",
    "scorecard_id",
    "date",
    "cell_id",
    "cap_tier_at_trigger",
    "tenure",
    "action",
    "confidence_unconditional",
    "confidence_regime_conditional",
    "predicted_excess",
    "regime_state_at_call",
    "cell_active_in_regime",
)


# ---------------------------------------------------------------------------
# Loaders — all read-only, all clamped to target_date.
# ---------------------------------------------------------------------------


def _load_scorecard(engine: Engine, target_date: date) -> list[dict[str, Any]]:
    """Load all ``atlas_scorecard_daily`` rows for ``target_date``.

    Returns a list of dicts (one per instrument) carrying the columns
    needed by the evaluator: the 6 locked features, ``cap_tier``, the
    ``id`` (scorecard PK — written to ``signal_call.scorecard_id``), and
    the ``instrument_id``.
    """
    sql = """
        SELECT
            id::text                  AS scorecard_id,
            instrument_id::text       AS instrument_id,
            cap_tier::text            AS cap_tier,
            family_trend::text        AS family_trend,
            family_volatility::text   AS family_volatility,
            family_volume::text       AS family_volume,
            family_path::text         AS family_path,
            family_sector::text       AS family_sector,
            rs_residual_6m,
            log_med_tv_60d,
            realized_vol_60d,
            formation_max_dd,
            listing_age_days,
            log_price,
            features
        FROM atlas.atlas_scorecard_daily
        WHERE date = %(target_date)s
    """
    with open_compute_session(engine) as conn:
        from psycopg2.extras import RealDictCursor  # local — psycopg2 only

        raw = conn.connection.cursor(cursor_factory=RealDictCursor)
        raw.execute(sql, {"target_date": target_date})
        rows = [dict(r) for r in raw.fetchall()]
        raw.close()

    # Flatten the JSONB ``features`` column onto the row dict so the
    # evaluator can pick up extension features (rs_momentum, atr_14, etc.)
    # without a special lookup path.
    for row in rows:
        extras = row.pop("features", None)
        if isinstance(extras, Mapping):
            for k, v in extras.items():
                if k not in row:
                    row[k] = v
    log.info("decisions_scorecard_loaded", target_date=str(target_date), count=len(rows))
    return rows


def _load_regime(engine: Engine, target_date: date) -> RegimeState | None:
    """Load the regime state for ``target_date`` from ``atlas_regime_daily``.

    Returns ``None`` when no row exists for that date — the caller must
    decide whether to halt or fall back. Production cron treats absence
    as an error (regime cron should have run first).
    """
    sql = """
        SELECT state::text AS state
        FROM atlas.atlas_regime_daily
        WHERE date = %(target_date)s
        LIMIT 1
    """
    with open_compute_session(engine) as conn:
        result = conn.exec_driver_sql(sql, {"target_date": target_date}).fetchone()
    if result is None:
        return None
    state_str = result[0] if not hasattr(result, "_mapping") else result._mapping["state"]
    return RegimeState(state_str)


def _load_active_cells(engine: Engine) -> list[dict[str, Any]]:
    """Load every active cell definition.

    Active == ``deprecated_at IS NULL``. ``drift_warn`` cells are included
    (advisory mode per CONTEXT.md §"Cell deprecation (REVISED post
    adversarial review)"); only confirmed-deprecated cells filter out.

    Returns dicts with ``rule_dsl`` already JSON-decoded by psycopg2.
    """
    sql = """
        SELECT
            cell_id,
            cap_tier::text     AS cap_tier,
            action::text       AS action,
            tenure::text       AS tenure,
            rule_dsl,
            confidence_unconditional,
            confidence_by_regime,
            friction_adjusted_excess,
            stable_features,
            methodology_lock_ref,
            rule_version,
            drift_status::text AS drift_status
        FROM atlas.atlas_cell_definitions
        WHERE deprecated_at IS NULL
    """
    with open_compute_session(engine) as conn:
        from psycopg2.extras import RealDictCursor  # local — psycopg2 only

        raw = conn.connection.cursor(cursor_factory=RealDictCursor)
        raw.execute(sql)
        rows = [dict(r) for r in raw.fetchall()]
        raw.close()
    log.info("decisions_cells_loaded", count=len(rows))
    return rows


def _load_open_positions(
    engine: Engine,
    target_date: date,
) -> set[tuple[str, str, str]]:
    """Set of ``(instrument_id, cell_id, tenure)`` triples currently open.

    "Open" == ``exit_date IS NULL`` AND ``date <= target_date`` (i.e. the
    position triggered before today and has not exited). Uses the
    ``ix_atlas_signal_calls_open`` partial index from migration 080.
    """
    sql = """
        SELECT
            instrument_id::text AS instrument_id,
            cell_id::text       AS cell_id,
            tenure::text        AS tenure
        FROM atlas.atlas_signal_calls
        WHERE exit_date IS NULL
          AND date <= %(target_date)s
    """
    with open_compute_session(engine) as conn:
        from psycopg2.extras import RealDictCursor  # local — psycopg2 only

        raw = conn.connection.cursor(cursor_factory=RealDictCursor)
        raw.execute(sql, {"target_date": target_date})
        rows = [
            (str(r["instrument_id"]), str(r["cell_id"]), str(r["tenure"])) for r in raw.fetchall()
        ]
        raw.close()
    return set(rows)


def _load_prior_calls(
    engine: Engine,
    target_date: date,
) -> set[tuple[str, str, str]]:
    """Set of ``(iid, cell_id, tenure)`` that have triggered at least once before.

    Used to distinguish "new signal" from "reactivation" in the result
    counts — has no bearing on the write path itself.
    """
    sql = """
        SELECT DISTINCT
            instrument_id::text AS instrument_id,
            cell_id::text       AS cell_id,
            tenure::text        AS tenure
        FROM atlas.atlas_signal_calls
        WHERE date < %(target_date)s
    """
    with open_compute_session(engine) as conn:
        from psycopg2.extras import RealDictCursor  # local — psycopg2 only

        raw = conn.connection.cursor(cursor_factory=RealDictCursor)
        raw.execute(sql, {"target_date": target_date})
        rows = [
            (str(r["instrument_id"]), str(r["cell_id"]), str(r["tenure"])) for r in raw.fetchall()
        ]
        raw.close()
    return set(rows)


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------


def _to_decimal_or_none(value: object, places: int = 4) -> Decimal | None:
    """Coerce a confidence value to ``Decimal(places)`` or ``None``."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal(10) ** -places)
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return Decimal(str(round(value, places)))
    try:
        return Decimal(str(value)).quantize(Decimal(10) ** -places)
    except (ArithmeticError, ValueError, TypeError):
        return None


def _build_signal_row(
    result: EvaluationResult,
    *,
    scorecard_row: Mapping[str, Any],
    cell: Mapping[str, Any],
    regime: RegimeState,
    target_date: date,
) -> tuple[Any, ...]:
    """Build one row tuple matching :data:`SIGNAL_CALL_COLUMNS`.

    The cap_tier at the moment of trigger is read from the scorecard row
    (NOT from the cell rule) — this is the v6 contract per migration 080
    column ``cap_tier_at_trigger``.
    """
    signal_call_id = uuid.uuid4()
    scorecard_id_raw = scorecard_row.get("scorecard_id") or scorecard_row.get("id")
    scorecard_id = (
        scorecard_id_raw if isinstance(scorecard_id_raw, UUID) else UUID(str(scorecard_id_raw))
    )
    instrument_id_raw = scorecard_row.get("instrument_id")
    instrument_id = (
        instrument_id_raw if isinstance(instrument_id_raw, UUID) else UUID(str(instrument_id_raw))
    )
    cell_id = result.cell_id if isinstance(result.cell_id, UUID) else UUID(str(result.cell_id))
    cap_tier = str(scorecard_row.get("cap_tier") or "Mid")
    tenure = str(cell.get("tenure"))
    action = str(cell.get("action"))

    # Confidence unconditional is required by the schema (NOT NULL) —
    # use Decimal("0") as a defensible default when the cell hasn't been
    # walk-forward-validated yet (placeholder cells from migration 089).
    conf_uncond = result.confidence_unconditional
    if conf_uncond is None:
        conf_uncond = Decimal("0.0000")
    else:
        conf_uncond = _to_decimal_or_none(conf_uncond, 4) or Decimal("0.0000")
    conf_regime = _to_decimal_or_none(result.confidence_regime_conditional, 4)

    # predicted_excess = the cell's friction-adjusted expected excess return
    # (a cell-level prior, same nature as confidence_unconditional). Without
    # this the frontend "Expected" column renders em-dashes for every call.
    pred_excess = _to_decimal_or_none(cell.get("friction_adjusted_excess"), 6)

    return (
        signal_call_id,
        instrument_id,
        scorecard_id,
        target_date,
        cell_id,
        cap_tier,
        tenure,
        action,
        conf_uncond,
        conf_regime,
        pred_excess,
        regime.value,
        bool(result.cell_active_in_regime),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compute_daily_signal_calls(
    target_date: date,
    db_engine: Engine | None = None,
    *,
    write: bool = True,
) -> SignalCallsWriteResult:
    """Daily decisions cron — evaluate cells and write trigger-only signal_calls.

    Args:
        target_date: the audit date. Every read clamps to ``date = target_date``
            (regime, scorecard) or ``date <= target_date`` (open positions).
        db_engine: optional engine override; defaults to the process-wide
            engine via :func:`atlas.db.get_engine`.
        write: when ``False``, evaluate but skip the bulk insert. Useful
            for backfill dry-runs.

    Returns:
        :class:`SignalCallsWriteResult` capturing the run.

    Behaviour:
        - Drops cells whose ``rule_dsl`` fails Pydantic validation — those
          are counted in ``errors`` and skipped (the daily run does NOT
          halt on a single malformed cell, but does log loudly).
        - Hits where the (iid, cell, tenure) triple is already in
          ``ix_atlas_signal_calls_open`` are SKIPPED (no new signal_call_id).
        - Hits that were never seen before (or had an earlier closed call)
          mint a new ``signal_call_id``. ``reactivations`` counts the
          subset that re-fired after a prior exit.
    """
    engine = db_engine or get_engine()
    started = time.time()
    run_id = uuid.uuid4()
    result = SignalCallsWriteResult(target_date=target_date, run_id=str(run_id))

    log.info(
        "decisions_cron_start",
        run_id=str(run_id),
        target_date=str(target_date),
        write=write,
    )

    # ---- Load regime first — it's a single row and required up front -------
    regime = _load_regime(engine, target_date)
    if regime is None:
        result.errors += 1
        result.runtime_seconds = round(time.time() - started, 3)
        log.error(
            "decisions_no_regime_for_date",
            target_date=str(target_date),
            run_id=str(run_id),
        )
        return result
    result.regime_state = regime

    # ---- Load scorecard rows + active cells --------------------------------
    scorecard_rows = _load_scorecard(engine, target_date)
    if not scorecard_rows:
        log.warning("decisions_no_scorecard_rows", target_date=str(target_date))
        result.runtime_seconds = round(time.time() - started, 3)
        return result
    result.universe_size = len(scorecard_rows)

    cells = _load_active_cells(engine)
    if not cells:
        log.warning("decisions_no_active_cells", target_date=str(target_date))
        result.runtime_seconds = round(time.time() - started, 3)
        return result
    result.cells_evaluated = len(cells)

    # ---- Drop cells whose rule_dsl fails to validate -----------------------
    valid_cells: list[dict[str, Any]] = []
    for cell in cells:
        try:
            # Lazy validation — parse to catch shape issues; the evaluator
            # will re-parse but this surface the error here for counting.
            from atlas.decisions.rule_dsl import validate_rule_dsl

            rule_blob = cell.get("rule_dsl")
            if isinstance(rule_blob, Mapping):
                validate_rule_dsl(dict(rule_blob))
            valid_cells.append(cell)
        except (ValueError, TypeError) as exc:
            result.errors += 1
            log.warning(
                "decisions_cell_rule_invalid",
                cell_id=str(cell.get("cell_id")),
                error=str(exc),
            )
    if not valid_cells:
        log.warning("decisions_no_valid_cells", target_date=str(target_date))
        result.runtime_seconds = round(time.time() - started, 3)
        return result

    # ---- Evaluate cross-product -------------------------------------------
    eval_results = evaluate_all_cells(scorecard_rows, valid_cells, regime)
    hits = [r for r in eval_results if r.hit]
    result.hits_total = len(hits)

    if not hits:
        result.runtime_seconds = round(time.time() - started, 3)
        log.info(
            "decisions_cron_complete",
            run_id=str(run_id),
            target_date=str(target_date),
            hits_total=0,
            new_signals=0,
            runtime_seconds=result.runtime_seconds,
        )
        return result

    # ---- Build lookup maps for open-position + prior-call checks ----------
    open_triples = _load_open_positions(engine, target_date)
    prior_triples = _load_prior_calls(engine, target_date)

    # Build maps for row construction
    scorecard_by_iid: dict[str, dict[str, Any]] = {
        str(row["instrument_id"]): row for row in scorecard_rows
    }
    cells_by_id: dict[str, dict[str, Any]] = {str(cell["cell_id"]): cell for cell in valid_cells}

    # ---- Decide which hits to write + idempotent dedup within run --------
    written_triples: set[tuple[str, str, str]] = set()
    rows_to_write: list[tuple[Any, ...]] = []
    for hit in hits:
        iid = str(hit.instrument_id)
        cell_id_str = str(hit.cell_id)
        hit_cell = cells_by_id.get(cell_id_str)
        if hit_cell is None:
            result.errors += 1
            continue
        tenure = str(hit_cell.get("tenure"))
        triple = (iid, cell_id_str, tenure)

        # In-run dedup — same triple cannot fire twice from one cron call.
        if triple in written_triples:
            continue

        # Open-position dedup — existing open call blocks new id.
        if triple in open_triples:
            result.skipped_open += 1
            continue

        scorecard_row = scorecard_by_iid.get(iid)
        if scorecard_row is None:
            result.errors += 1
            continue

        row_tuple = _build_signal_row(
            hit,
            scorecard_row=scorecard_row,
            cell=hit_cell,
            regime=regime,
            target_date=target_date,
        )
        rows_to_write.append(row_tuple)
        written_triples.add(triple)
        if triple in prior_triples:
            result.reactivations += 1

    result.new_signals = len(rows_to_write)

    # ---- Bulk insert ------------------------------------------------------
    if write and rows_to_write:
        try:
            written = bulk_upsert(
                engine,
                table="atlas.atlas_signal_calls",
                columns=list(SIGNAL_CALL_COLUMNS),
                rows=rows_to_write,
                pk_columns=["signal_call_id"],
            )
            log.info("decisions_signal_calls_written", count=written)
        except Exception as exc:
            result.errors += 1
            log.error(
                "decisions_bulk_upsert_failed",
                error=str(exc),
                target_date=str(target_date),
            )
            raise

    result.runtime_seconds = round(time.time() - started, 3)
    log.info(
        "decisions_cron_complete",
        run_id=str(run_id),
        target_date=str(target_date),
        regime_state=regime.value,
        universe_size=result.universe_size,
        cells_evaluated=result.cells_evaluated,
        hits_total=result.hits_total,
        new_signals=result.new_signals,
        reactivations=result.reactivations,
        skipped_open=result.skipped_open,
        errors=result.errors,
        runtime_seconds=result.runtime_seconds,
    )
    return result


__all__ = [
    "SIGNAL_CALL_COLUMNS",
    "SignalCallsWriteResult",
    "compute_daily_signal_calls",
]
