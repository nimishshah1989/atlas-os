"""Signal validation — Information Coefficient measurement and reporting.

Per Phase 2 sub-project SP01. Public surface:

- encoding: pure state→numeric encoder
- factor_loader: SQL → composite factor DataFrame
- forward_returns: SQL → forward return matrix
- ic_engine: alphalens-driven IC computation
- persistence: writes results to atlas_signal_ic
- report: markdown tearsheet generator
"""

from atlas.intelligence.validation.encoding import (
    DIMENSION_WEIGHTS,
    SENTINEL_STATES,
    STATE_ENCODINGS,
    compute_decision_state_score,
    encode_state,
)

__all__ = [
    "DIMENSION_WEIGHTS",
    "SENTINEL_STATES",
    "STATE_ENCODINGS",
    "compute_decision_state_score",
    "encode_state",
]
