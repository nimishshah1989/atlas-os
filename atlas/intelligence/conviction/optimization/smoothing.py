"""Bayesian smoothing: blend an approved candidate weight set with the
current active weights.

Pure function — no I/O, no logging. ``blend_weights`` produces a new dict
that is ``(1 - lambda_) * current + lambda_ * proposed`` per signal and is
renormalized to sum to 1.0 so rounding errors do not drift the total.

Rationale for default ``lambda_ = 0.15``: empirically, in IC-weighted
composites, a 15% blend toward the new candidate captures most of the
predicted lift while keeping the live composite stable enough that FMs
do not lose intuition about it. The choice is conservative; Stage 4b
can raise lambda once we have a feedback record.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

DEFAULT_LAMBDA: Decimal = Decimal("0.15")


def blend_weights(
    current: Mapping[str, Decimal],
    proposed: Mapping[str, Decimal],
    *,
    lambda_: Decimal = DEFAULT_LAMBDA,
) -> dict[str, Decimal]:
    """Return ``(1 - lambda_)·current + lambda_·proposed``, renormalized.

    Signals present in only one input are treated as 0 in the other before
    blending. The result is renormalized so its sum is exactly 1.0 (within
    Decimal precision) — this is important because downstream consumers
    assume weights sum to 1.0 (see ``apply_weights_to_percentile_ranks``).
    """
    if lambda_ < Decimal("0") or lambda_ > Decimal("1"):
        raise ValueError(f"lambda_ must be in [0, 1], got {lambda_}")

    all_signals = set(current) | set(proposed)
    blended_raw: dict[str, Decimal] = {}
    one_minus_lambda = Decimal("1") - lambda_
    for sig in all_signals:
        c = Decimal(current.get(sig, Decimal("0")))
        p = Decimal(proposed.get(sig, Decimal("0")))
        blended_raw[sig] = one_minus_lambda * c + lambda_ * p

    total = sum(blended_raw.values(), Decimal("0"))
    if total == Decimal("0"):
        return blended_raw

    return {sig: w / total for sig, w in blended_raw.items()}
