"""SP04 Stage 4a — auto-optimization loop for the conviction composite.

Public surface:

- ``ic_monitor.measure_all_tiers`` — compute rolling per-tier IC
- ``candidate_generator.generate_candidates`` — propose new weight sets
- ``smoothing.blend_weights`` — Bayesian (1-λ)·current + λ·proposed
- ``persistence`` — upsert_ic_batch / insert_proposal /
  apply_proposal / reject_proposal / snooze_proposal

See ``docs/phase2/plans/2026-05-12-sp04-stage4a-auto-optimization-loop.md``.
"""

from atlas.intelligence.conviction.optimization.candidate_generator import (
    CandidatePayload,
    generate_candidates,
)
from atlas.intelligence.conviction.optimization.ic_monitor import (
    ICMeasurement,
    measure_all_tiers,
    measure_ic_for_signal,
)
from atlas.intelligence.conviction.optimization.persistence import (
    apply_proposal,
    insert_proposal,
    reject_proposal,
    snooze_proposal,
    upsert_ic_batch,
)
from atlas.intelligence.conviction.optimization.smoothing import (
    DEFAULT_LAMBDA,
    blend_weights,
)

__all__ = [
    "ICMeasurement",
    "CandidatePayload",
    "DEFAULT_LAMBDA",
    "measure_all_tiers",
    "measure_ic_for_signal",
    "generate_candidates",
    "blend_weights",
    "upsert_ic_batch",
    "insert_proposal",
    "apply_proposal",
    "reject_proposal",
    "snooze_proposal",
]
