"""Atlas-M2 compute layer.

Per ``docs/01_BACKEND_ARCHITECTURE.md`` §5 and ``docs/milestones/ATLAS_M2_*.md``.

Public surface:

- ``primitives`` — the four primitive math functions (RS, Momentum, Risk, Volume)
  plus EMAs and ATR. All vectorised across the universe via pandas groupby +
  pandas-ta. No Python row loops.
- ``gates`` — pre-classification gates (history, liquidity) and the Weinstein
  absolute-trend gate.
- ``states`` — ``np.select``-based classifiers driven by ``atlas_thresholds``
  per architecture 5.6. No hardcoded threshold literals.
- ``benchmarks`` — benchmark cache materialisation; runs once per pipeline.
- ``stocks`` / ``etfs`` — orchestrators that wire primitives → states → DB writes.

The flow: ``benchmarks → primitives → gates → states → write``. Each step is
vectorised across the entire universe in a single C-level call (no Python loops).

See ``prds/M2_BUILD_PLAN.md`` for the full vectorisation strategy and time budget.
"""

from atlas.compute._session import (
    bulk_upsert,
    open_compute_session,
)

__all__ = ["bulk_upsert", "open_compute_session"]
