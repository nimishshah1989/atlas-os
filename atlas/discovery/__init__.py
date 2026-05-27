"""atlas.discovery — v6 24-cell walk-forward matrix sweep engine (Phase 0.5g, #25).

The matrix generator. Runs **24 independent feature-discovery exercises** —
one per ``(cap_tier × tenure × actionable_state)`` per CONTEXT.md §"24-framework
discovery model". Each cell is either VALIDATED (clears the per-tenure IC
floor AND has the right-signed friction-adjusted excess) or marked
``no_conviction`` (renders as "insufficient validation" in the UI).

Three layers, three responsibilities:

* :mod:`atlas.discovery.engine` — :class:`WalkForwardSweep`, the sweep engine.
  Discovers (or re-validates) one cell at a time via :meth:`discover_cell`
  and the full 24-cell matrix via :meth:`run_full_matrix`. Synthetic data
  generator (`mode="synthetic"`) is fully implemented for end-to-end
  pipeline validation; cache/supabase/ec2 modes raise NotImplementedError
  with explicit next-step guidance.

* :mod:`atlas.discovery.cli` — ``python -m atlas.discovery.cli`` entry point
  with ``--mode``, ``--dry-run``, ``--output-html`` flags.

* :mod:`atlas.discovery.matrix_status` — Atlas-visual-language HTML
  rendering of the 24-cell matrix with status indicators + per-cell drill.

Methodology references:

* CONTEXT.md §"Cell rule" — flat-AND ``rule_dsl`` shape.
* CONTEXT.md §"24-framework discovery model" — the 3 × 4 × 2 matrix.
* CONTEXT.md §"Per-tenure IC floors" — literature-backed defaults (revised
  by Phase 0.5g-pre null-distribution sweep, finding 3).
* CONTEXT.md §"Methodology freeze rule" — once cell-validation 2021+
  window opens, no new features added.

Persistence contract:

* Every walk-forward attempt INSERTs into ``atlas_cell_walkforward_runs``
  (audit row; status starts as ``running`` and is UPDATEd to ``completed``
  or ``failed`` on finish).
* Only VALIDATED cells INSERT into ``atlas_cell_definitions``.
  ``no_conviction`` cells are NOT persisted into the cell definitions
  table — they are visible only in the walk-forward audit log.
"""

from __future__ import annotations

from atlas.discovery.engine import (
    DEFAULT_WINDOWS,
    PER_TENURE_IC_FLOOR,
    CellDiscoveryResult,
    CellSpec,
    SweepResult,
    WalkForwardSweep,
    WalkForwardWindow,
)
from atlas.discovery.matrix_status import generate_matrix_status_html

__all__ = [
    "DEFAULT_WINDOWS",
    "PER_TENURE_IC_FLOOR",
    "CellDiscoveryResult",
    "CellSpec",
    "SweepResult",
    "WalkForwardSweep",
    "WalkForwardWindow",
    "generate_matrix_status_html",
]
