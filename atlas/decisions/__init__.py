"""atlas.decisions — cell rule evaluator + daily inference cron (#45).

The decisions layer is the **Phase 4** v6 module that turns the
``atlas_scorecard_daily`` snapshot + ``atlas_regime_daily`` regime state +
``atlas_cell_definitions`` ruleset into ``atlas_signal_calls`` rows — one
row per *trigger event* (per CONTEXT.md §"signal_call_id" cadence lock).

Three layers, three responsibilities:

* :mod:`atlas.decisions.rule_dsl` — Pydantic v2 ``CellRule`` schema for the
  ``atlas_cell_definitions.rule_dsl`` JSONB column. Includes the
  ``FEATURES`` allowlist check that surfaces a feature-name typo at
  validation time (per /grill-with-docs Q4) instead of at inference time.

* :mod:`atlas.decisions.evaluator` — pure, side-effect-free evaluator.
  Takes a scorecard row + regime + cell definition, returns a hit/miss with
  a structured ``EvaluationResult``. Cross-section ``in_top_quantile``
  predicates pre-compute the per-feature ranks **once per date**, never
  per cell, so the cross-product is vectorised.

* :mod:`atlas.decisions.cron` — daily orchestrator. Reads the three input
  tables, calls the evaluator, and writes ``atlas_signal_calls`` rows
  honouring trigger-only cadence: a fresh ``signal_call_id`` is minted on
  INACTIVE→ACTIVE transitions, day-2-active does NOT re-write, and
  re-entry after exit DOES mint a new id (same domain pair, distinct
  ``signal_call_id`` per CONTEXT.md). The open-positions partial index
  ``ix_atlas_signal_calls_open`` (migration 080) supports the open-check
  query without scanning the full event table.

Action vocabulary is ``POSITIVE`` / ``NEUTRAL`` / ``NEGATIVE`` per the R1
collapse (CONTEXT.md §"Cell state vocabulary"). Display labels
(BUY/ACCUMULATE/HOLD/WATCH/AVOID/SELL) are resolved at the API layer
based on user ownership and are NOT validated as separate cells.

Drift status (CONTEXT.md §"Cell deprecation (REVISED post adversarial
review)") is advisory in v6 — ``drift_warn`` cells continue to fire. Only
``deprecated_at IS NOT NULL`` filters a cell out of the daily inference;
the cron's read query enforces this at the source.
"""

from __future__ import annotations

from atlas.decisions.cron import (
    SignalCallsWriteResult,
    compute_daily_signal_calls,
)
from atlas.decisions.evaluator import (
    EvaluationResult,
    evaluate_all_cells,
    evaluate_cell,
)
from atlas.decisions.rule_dsl import (
    CellRule,
    FeaturePredicate,
    validate_rule_dsl,
)

__all__ = [
    "CellRule",
    "EvaluationResult",
    "FeaturePredicate",
    "SignalCallsWriteResult",
    "compute_daily_signal_calls",
    "evaluate_all_cells",
    "evaluate_cell",
    "validate_rule_dsl",
]
