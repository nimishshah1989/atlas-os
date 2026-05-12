"""Persistence helpers for the auto-optimization loop.

Three responsibilities:

1. ``upsert_ic_batch`` — write rolling-IC rows to ``atlas_signal_ic_rolling``.
2. ``insert_proposal`` — write a candidate weight set to
   ``atlas_weight_proposals``. Supersedes any existing pending proposal
   for the same (tier, regime) inside one transaction.
3. ``apply_proposal`` — atomic FM approval: blend the proposed weights
   with the current active set (Bayesian smoothing), bookend the old
   active rows with ``effective_to = CURRENT_DATE``, insert new active
   rows with the blended values, and mark the proposal ``approved``.

``reject_proposal`` and ``snooze_proposal`` are simple status updates.
``snooze_proposal`` records the ``until_date`` in ``review_notes``.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.optimization.ic_monitor import ICMeasurement
from atlas.intelligence.conviction.optimization.smoothing import (
    DEFAULT_LAMBDA,
    blend_weights,
)

log = structlog.get_logger()


_UPSERT_IC_SQL = text("""
    INSERT INTO atlas.atlas_signal_ic_rolling
        (as_of_date, tier, signal_name, lookback_window, forward_horizon,
         n_observations, ic, t_stat)
    VALUES
        (:as_of_date, :tier, :signal_name, :lookback_window, :forward_horizon,
         :n_observations, :ic, :t_stat)
    ON CONFLICT (as_of_date, tier, signal_name, lookback_window, forward_horizon)
    DO UPDATE SET
        n_observations = EXCLUDED.n_observations,
        ic = EXCLUDED.ic,
        t_stat = EXCLUDED.t_stat
""")


def upsert_ic_batch(engine: Engine, measurements: list[ICMeasurement]) -> int:
    """UPSERT a batch of IC measurements. Returns row count written."""
    if not measurements:
        return 0
    records = [
        {
            "as_of_date": m.as_of_date,
            "tier": m.tier,
            "signal_name": m.signal_name,
            "lookback_window": m.lookback_window,
            "forward_horizon": m.forward_horizon,
            "n_observations": m.n_observations,
            "ic": m.ic,
            "t_stat": m.t_stat,
        }
        for m in measurements
    ]
    with engine.begin() as conn:
        conn.execute(_UPSERT_IC_SQL, records)
    log.info("ic_rolling_batch_persisted", n=len(records))
    return len(records)


_SUPERSEDE_PENDING_SQL = text("""
    UPDATE atlas.atlas_weight_proposals
       SET status = 'superseded'
     WHERE tier = :tier AND regime = :regime AND status = 'pending'
""")

_INSERT_PROPOSAL_SQL = text("""
    INSERT INTO atlas.atlas_weight_proposals
        (tier, regime, proposed_weights, current_weights,
         proposed_holdout_ic, current_holdout_ic, ic_delta,
         rationale, generator_version, status)
    VALUES
        (:tier, :regime,
         CAST(:proposed_weights AS jsonb),
         CAST(:current_weights AS jsonb),
         :proposed_holdout_ic, :current_holdout_ic, :ic_delta,
         :rationale, :generator_version, 'pending')
    RETURNING id::text
""")


def insert_proposal(engine: Engine, payload: dict[str, Any]) -> str:
    """Insert one pending proposal; supersede any existing pending row
    for the same (tier, regime). Returns the new proposal id."""
    tier = payload["tier"]
    regime = payload.get("regime", "all")
    with engine.begin() as conn:
        conn.execute(_SUPERSEDE_PENDING_SQL, {"tier": tier, "regime": regime})
        row = conn.execute(
            _INSERT_PROPOSAL_SQL,
            {
                "tier": tier,
                "regime": regime,
                "proposed_weights": json.dumps(
                    {k: str(v) for k, v in payload["proposed_weights"].items()}
                ),
                "current_weights": json.dumps(
                    {k: str(v) for k, v in payload["current_weights"].items()}
                ),
                "proposed_holdout_ic": payload.get("proposed_holdout_ic"),
                "current_holdout_ic": payload.get("current_holdout_ic"),
                "ic_delta": payload.get("ic_delta"),
                "rationale": payload.get("rationale"),
                "generator_version": payload.get("generator_version", "sp04-stage4a-v1"),
            },
        ).fetchone()
    if row is None:
        raise RuntimeError("insert_proposal returned no id")
    return str(row[0])


_LOAD_PROPOSAL_SQL = text("""
    SELECT id::text, tier, regime, proposed_weights, current_weights,
           status, proposed_holdout_ic
    FROM atlas.atlas_weight_proposals
    WHERE id = CAST(:pid AS uuid)
""")

_LOAD_ACTIVE_WEIGHTS_SQL = text("""
    SELECT signal_name, weight, flipped
    FROM atlas.atlas_signal_weights
    WHERE tier = :tier AND regime = :regime AND effective_to IS NULL
""")

_BOOKEND_OLD_WEIGHTS_SQL = text("""
    UPDATE atlas.atlas_signal_weights
       SET effective_to = CURRENT_DATE
     WHERE tier = :tier AND regime = :regime AND effective_to IS NULL
""")

_INSERT_NEW_WEIGHT_SQL = text("""
    INSERT INTO atlas.atlas_signal_weights
        (tier, regime, signal_name, weight, flipped,
         effective_from, effective_to, holdout_ic,
         approved_by, notes)
    VALUES
        (:tier, :regime, :signal_name, :weight, :flipped,
         CURRENT_DATE + INTERVAL '1 day', NULL, :holdout_ic,
         :approved_by, :notes)
""")

_FINALIZE_PROPOSAL_SQL = text("""
    UPDATE atlas.atlas_weight_proposals
       SET status = 'approved',
           applied_weights = CAST(:applied AS jsonb),
           applied_at = NOW(),
           reviewed_by = :reviewer,
           reviewed_at = NOW(),
           review_notes = :notes
     WHERE id = CAST(:pid AS uuid)
""")


def apply_proposal(
    engine: Engine,
    *,
    proposal_id: str,
    reviewer: str,
    notes: str | None = None,
    lambda_: Decimal = DEFAULT_LAMBDA,
) -> dict[str, Decimal]:
    """Apply an approved proposal: blend with current weights, bookend
    old weights, insert new active weights, mark proposal approved.

    Returns the applied (blended) weights so the caller can echo them.
    Raises RuntimeError if the proposal is not pending.
    """
    with engine.begin() as conn:
        prop = conn.execute(_LOAD_PROPOSAL_SQL, {"pid": proposal_id}).fetchone()
        if prop is None:
            raise RuntimeError(f"proposal {proposal_id} not found")
        if prop[5] != "pending":
            raise RuntimeError(f"proposal {proposal_id} status is {prop[5]!r}, expected pending")

        tier = prop[1]
        regime = prop[2]
        proposed_weights_json = prop[3]
        if isinstance(proposed_weights_json, str):
            proposed_dict = json.loads(proposed_weights_json)
        else:
            proposed_dict = proposed_weights_json
        proposed: dict[str, Decimal] = {k: Decimal(str(v)) for k, v in proposed_dict.items()}
        holdout_ic = prop[6]

        current_rows = conn.execute(
            _LOAD_ACTIVE_WEIGHTS_SQL, {"tier": tier, "regime": regime}
        ).fetchall()
        current: dict[str, Decimal] = {r[0]: Decimal(str(r[1])) for r in current_rows}
        # flipped flag carries over by signal name; default False for
        # newly introduced signals
        current_flipped: dict[str, bool] = {r[0]: bool(r[2]) for r in current_rows}

        blended = blend_weights(current, proposed, lambda_=lambda_)

        conn.execute(_BOOKEND_OLD_WEIGHTS_SQL, {"tier": tier, "regime": regime})

        new_rows = [
            {
                "tier": tier,
                "regime": regime,
                "signal_name": sig,
                "weight": w,
                "flipped": current_flipped.get(sig, False),
                "holdout_ic": holdout_ic,
                "approved_by": reviewer,
                "notes": notes or f"Stage 4a auto-optimization blend (λ={lambda_})",
            }
            for sig, w in blended.items()
        ]
        if new_rows:
            conn.execute(_INSERT_NEW_WEIGHT_SQL, new_rows)

        conn.execute(
            _FINALIZE_PROPOSAL_SQL,
            {
                "pid": proposal_id,
                "applied": json.dumps({k: str(v) for k, v in blended.items()}),
                "reviewer": reviewer,
                "notes": notes,
            },
        )

    log.info(
        "proposal_applied",
        proposal_id=proposal_id,
        tier=tier,
        n_signals=len(blended),
    )
    return blended


_REJECT_SQL = text("""
    UPDATE atlas.atlas_weight_proposals
       SET status = 'rejected',
           reviewed_by = :reviewer,
           reviewed_at = NOW(),
           review_notes = :notes
     WHERE id = CAST(:pid AS uuid) AND status = 'pending'
""")

_SNOOZE_SQL = text("""
    UPDATE atlas.atlas_weight_proposals
       SET status = 'snoozed',
           reviewed_by = :reviewer,
           reviewed_at = NOW(),
           review_notes = :notes
     WHERE id = CAST(:pid AS uuid) AND status = 'pending'
""")


def reject_proposal(
    engine: Engine, *, proposal_id: str, reviewer: str, notes: str | None = None
) -> None:
    with engine.begin() as conn:
        result = conn.execute(
            _REJECT_SQL,
            {"pid": proposal_id, "reviewer": reviewer, "notes": notes},
        )
    if result.rowcount == 0:
        raise RuntimeError(f"proposal {proposal_id} not found or not pending — cannot reject")
    log.info("proposal_rejected", proposal_id=proposal_id)


def snooze_proposal(
    engine: Engine,
    *,
    proposal_id: str,
    reviewer: str,
    until_date: date,
    notes: str | None = None,
) -> None:
    combined = (notes or "").strip()
    snooze_note = f"snoozed until {until_date.isoformat()}"
    full_notes = f"{snooze_note}. {combined}" if combined else snooze_note
    with engine.begin() as conn:
        result = conn.execute(
            _SNOOZE_SQL,
            {"pid": proposal_id, "reviewer": reviewer, "notes": full_notes},
        )
    if result.rowcount == 0:
        raise RuntimeError(f"proposal {proposal_id} not found or not pending — cannot snooze")
    log.info("proposal_snoozed", proposal_id=proposal_id, until=str(until_date))
