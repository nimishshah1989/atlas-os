"""Generate weight-set candidate proposals from rolling IC measurements.

Algorithm (v1, conservative):

1. Load currently-active weights per tier from ``atlas_signal_weights``.
2. Load the last ``N`` rolling-IC measurements per (tier, signal) from
   ``atlas_signal_ic_rolling`` (default last 30 days).
3. For each tier:
   - Average rolling IC per signal across the recent window.
   - Use ``|mean IC|`` as the proposed-weight numerator; renormalize so
     proposed weights sum to 1.0.
   - Anti-predictive signals (negative IC) keep their ``flipped`` bit
     from the active set — the magnitude drives weight, the sign drives
     whether we flip at compose time.
4. If the max element-wise abs(weight delta) is below
   ``MATERIAL_CHANGE_THRESHOLD``, skip the tier (no proposal). This
   keeps the proposal queue free of noise.
5. Otherwise: build a payload and let ``persistence.insert_proposal``
   handle supersede + insert.

The output of this module is a list of ``CandidatePayload`` dicts ready
for ``insert_proposal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

MATERIAL_CHANGE_THRESHOLD: Final[Decimal] = Decimal("0.05")
DEFAULT_IC_WINDOW_DAYS: Final[int] = 30
MIN_IC_OBSERVATIONS_FOR_PROPOSAL: Final[int] = 3


@dataclass(frozen=True)
class CandidatePayload:
    """The payload that ``insert_proposal`` expects, plus diagnostics."""

    tier: str
    regime: str
    proposed_weights: dict[str, Decimal]
    current_weights: dict[str, Decimal]
    proposed_holdout_ic: Decimal | None
    current_holdout_ic: Decimal | None
    ic_delta: Decimal | None
    rationale: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "regime": self.regime,
            "proposed_weights": self.proposed_weights,
            "current_weights": self.current_weights,
            "proposed_holdout_ic": (
                None if self.proposed_holdout_ic is None else float(self.proposed_holdout_ic)
            ),
            "current_holdout_ic": (
                None if self.current_holdout_ic is None else float(self.current_holdout_ic)
            ),
            "ic_delta": (None if self.ic_delta is None else float(self.ic_delta)),
            "rationale": self.rationale,
        }


_LOAD_CURRENT_WEIGHTS_SQL = text("""
    SELECT tier, signal_name, weight, holdout_ic
    FROM atlas.atlas_signal_weights
    WHERE effective_to IS NULL AND regime = :regime
    ORDER BY tier, weight DESC
""")

_LOAD_RECENT_IC_SQL = text("""
    SELECT tier, signal_name, AVG(ic) AS mean_ic, AVG(n_observations) AS mean_n
    FROM atlas.atlas_signal_ic_rolling
    WHERE as_of_date >= :since
    GROUP BY tier, signal_name
""")


def _load_current(
    engine: Engine, regime: str
) -> tuple[dict[str, dict[str, Decimal]], dict[str, Decimal]]:
    """Return ({tier: {signal: weight}}, {tier: holdout_ic})."""
    with engine.connect() as conn:
        rows = conn.execute(_LOAD_CURRENT_WEIGHTS_SQL, {"regime": regime}).fetchall()
    by_tier: dict[str, dict[str, Decimal]] = {}
    ic_by_tier: dict[str, Decimal] = {}
    for r in rows:
        by_tier.setdefault(r[0], {})[r[1]] = Decimal(str(r[2]))
        if r[3] is not None and r[0] not in ic_by_tier:
            ic_by_tier[r[0]] = Decimal(str(r[3]))
    return by_tier, ic_by_tier


def _load_recent_ic(
    engine: Engine, *, window_days: int, as_of: date
) -> dict[str, dict[str, Decimal]]:
    """Return {tier: {signal: mean_recent_ic}}."""
    since = as_of - timedelta(days=window_days)
    with engine.connect() as conn:
        rows = conn.execute(_LOAD_RECENT_IC_SQL, {"since": since}).fetchall()
    by_tier: dict[str, dict[str, Decimal]] = {}
    for r in rows:
        by_tier.setdefault(r[0], {})[r[1]] = Decimal(str(r[2]))
    return by_tier


def _renormalize(weights: dict[str, Decimal]) -> dict[str, Decimal]:
    total = sum(weights.values(), Decimal("0"))
    if total == Decimal("0"):
        return weights
    return {k: v / total for k, v in weights.items()}


def _max_abs_delta(a: dict[str, Decimal], b: dict[str, Decimal]) -> Decimal:
    """Max element-wise |a[k] - b[k]| across the union of keys."""
    keys = set(a) | set(b)
    if not keys:
        return Decimal("0")
    return max(abs(a.get(k, Decimal("0")) - b.get(k, Decimal("0"))) for k in keys)


def _build_rationale(
    tier: str, *, current: dict[str, Decimal], proposed: dict[str, Decimal]
) -> str:
    """Top-3 movers as a one-line rationale string."""
    deltas: list[tuple[str, Decimal]] = []
    keys = set(current) | set(proposed)
    for k in keys:
        deltas.append((k, proposed.get(k, Decimal("0")) - current.get(k, Decimal("0"))))
    deltas.sort(key=lambda x: abs(x[1]), reverse=True)
    top = deltas[:3]
    parts = [f"{sig} {'+' if d >= 0 else ''}{float(d):.3f}" for sig, d in top]
    return f"Stage 4a re-weight from rolling IC. Top movers: {', '.join(parts)}."


def generate_candidates(
    engine: Engine,
    *,
    as_of: date,
    regime: str = "all",
    window_days: int = DEFAULT_IC_WINDOW_DAYS,
) -> list[CandidatePayload]:
    """Return one candidate per tier whose rolling-IC re-weight differs
    materially from the active weights.

    Tiers with no IC measurements in the window are silently skipped.
    """
    current_by_tier, current_holdout_by_tier = _load_current(engine, regime)
    recent_ic_by_tier = _load_recent_ic(engine, window_days=window_days, as_of=as_of)

    candidates: list[CandidatePayload] = []
    for tier, current_weights in current_by_tier.items():
        if tier not in recent_ic_by_tier:
            continue
        ic_map = recent_ic_by_tier[tier]
        if len(ic_map) < MIN_IC_OBSERVATIONS_FOR_PROPOSAL:
            continue

        # Build proposed weights from |IC|, restricted to signals
        # currently in the active set (don't introduce new ones via
        # auto-optimization).
        raw_proposed: dict[str, Decimal] = {}
        for sig in current_weights.keys():
            mean_ic = ic_map.get(sig)
            if mean_ic is None:
                raw_proposed[sig] = Decimal("0")
            else:
                raw_proposed[sig] = abs(mean_ic)
        if sum(raw_proposed.values()) == Decimal("0"):
            continue

        proposed = _renormalize(raw_proposed)
        delta = _max_abs_delta(current_weights, proposed)
        if delta < MATERIAL_CHANGE_THRESHOLD:
            log.info(
                "candidate_skipped_immaterial",
                tier=tier,
                max_delta=float(delta),
                threshold=float(MATERIAL_CHANGE_THRESHOLD),
            )
            continue

        # Predicted IC = sum(weight × |IC|) — a rough proxy.
        proposed_predicted_ic = sum(
            (proposed[sig] * abs(ic_map.get(sig, Decimal("0")))) for sig in proposed
        )
        current_holdout = current_holdout_by_tier.get(tier)
        ic_delta = None
        if current_holdout is not None:
            ic_delta = proposed_predicted_ic - current_holdout

        candidates.append(
            CandidatePayload(
                tier=tier,
                regime=regime,
                proposed_weights=proposed,
                current_weights=current_weights,
                proposed_holdout_ic=Decimal(proposed_predicted_ic),
                current_holdout_ic=current_holdout,
                ic_delta=Decimal(ic_delta) if ic_delta is not None else None,
                rationale=_build_rationale(tier, current=current_weights, proposed=proposed),
            )
        )

    log.info(
        "candidates_generated",
        as_of=str(as_of),
        n_candidates=len(candidates),
        n_tiers_evaluated=len(current_by_tier),
    )
    return candidates
