"""SP04 Stage 4c — live monitoring + hit-rate + auto-revert.

Public surface:

- ``live_ic_tracker.measure_all_active_versions`` — realized IC per active
  weight set, one row per tier per night.
- ``hit_rate_engine.compute_hit_rates_batch`` — per-stock hit-rate
  primitive over a rolling lookback window.
- ``drift_detector.detect_drift`` — surface weight sets whose realized
  IC has been below threshold for too long; optional auto-revert.

See ``docs/phase2/plans/2026-05-12-sp04-stage4c-live-monitoring.md``.
"""

from atlas.intelligence.conviction.monitoring.drift_detector import (
    DriftFinding,
    detect_drift,
    execute_revert,
)
from atlas.intelligence.conviction.monitoring.hit_rate_engine import (
    HitRateRow,
    compute_hit_rate_for_stock,
    compute_hit_rates_batch,
)
from atlas.intelligence.conviction.monitoring.live_ic_tracker import (
    LiveICMeasurement,
    measure_all_active_versions,
    measure_live_composite_ic,
)
from atlas.intelligence.conviction.monitoring.persistence import (
    upsert_hit_rates_batch,
    upsert_live_perf_batch,
    write_revert_log,
)

__all__ = [
    "DriftFinding",
    "HitRateRow",
    "LiveICMeasurement",
    "compute_hit_rate_for_stock",
    "compute_hit_rates_batch",
    "detect_drift",
    "execute_revert",
    "measure_all_active_versions",
    "measure_live_composite_ic",
    "upsert_hit_rates_batch",
    "upsert_live_perf_batch",
    "write_revert_log",
]
