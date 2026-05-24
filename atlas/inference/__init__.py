"""atlas.inference — Phase 4 daily inference orchestrator (#46).

The inference layer wires the three v6 daily writers into a single
entrypoint::

    scorecard_writer  →  regime cron  →  decisions cron

per CONTEXT.md §"Look-ahead audit gate". Each phase computes only from
data ``<= target_date`` and writes its output table; the orchestrator
captures one ``atlas_provenance_log`` row recording the input/universe/code
SHAs and the per-step output row counts (R9 data lineage).

The orchestrator is intentionally NOT in
``atlas/{features,decisions,regime,...}/`` — those are methodology bounded
contexts. ``atlas.inference`` is **plumbing** — it sequences existing
modules and writes one provenance row. No methodology decisions live here.

Public surface:

* :func:`compute_daily` — the single daily entrypoint.
* :class:`DailyInferenceResult` — the dataclass returned by ``compute_daily``,
  carrying the three phase results plus runtime + provenance_run_id.

CLI:

.. code-block:: bash

    python -m atlas.inference.cli --target-date 2026-05-23

Exit codes:

* 0 — clean run (no errors collected)
* 1 — non-fatal errors collected (e.g. regime missing, fallback applied)
* 2 — fatal error raised mid-pipeline (provenance row records partial state)
"""

from __future__ import annotations

from atlas.inference.daily import DailyInferenceResult, compute_daily

__all__ = [
    "DailyInferenceResult",
    "compute_daily",
]
