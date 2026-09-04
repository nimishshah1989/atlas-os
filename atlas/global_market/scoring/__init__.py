"""Scoring for the US platform — pure functions, thresholds passed in, no I/O.

``blend`` is the composite: a weighted mean over the lenses PRESENT + a conviction-tier
cut, parity-tested against India's ``compute_composite`` on real ``atlas_foundation`` rows.
Lens scorers (etf_lenses, stock_catalyst, stock_flow, fundamentals_us) land in Phase 3.
"""

from .blend import BlendResult, blend, tiers_from_thresholds, weights_from_thresholds

__all__ = ["BlendResult", "blend", "tiers_from_thresholds", "weights_from_thresholds"]
