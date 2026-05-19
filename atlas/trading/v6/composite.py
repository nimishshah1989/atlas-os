"""atlas.trading.v6.composite — z-score blend + sector neutralization + selection.

Two public responsibilities:

1. compute_composite — for each signal column in signals_panel:
   a. Compute sector-demeaned z-score (per spec §6.1).
   b. Winsorize at ±winsorize_z (default 3.0).
   c. Multiply by signal weight.
   Sum to produce a composite score per instrument.

2. select — apply buffer zones per spec §6.4:
   - Governance-excluded → composite = -inf → forced exit if held.
   - Entries restricted to trend_gate_pass.
   - rank ≤ 30  → enter if not held yesterday
   - rank ≤ 50 AND held yesterday → stay (held)
   - rank > 50 AND held yesterday → exit
   - rank ≤ 50 AND NOT held AND NOT in trend_gate_pass → bench_hold (blocked entry)

No DB writes. All logic is pure-pandas in-memory.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Signal weights (§6.2 priors)
# ---------------------------------------------------------------------------

_SIGNAL_COLUMNS = [
    "natr_14",
    "beta_alpha_63d",
    "mom_low_vol",
    "residual_momentum",
    "proximity_52wh",
    "industry_rs",
    "fip_smoothness",
    "bab",
    "quality_proxy",
]


@dataclass
class SignalWeights:
    """Per-signal blend weights — §6.2 priors.

    Sum = 0.99 ≈ 1.0. Normalized internally before use so drift to 0.99
    does not bias the composite.

    Stage 4a Bayesian shrinkage will tune these weights annually once
    rolling OOS-IC data accumulates. For now these are informative priors.
    """

    natr_14: float = 0.15
    beta_alpha_63d: float = 0.15
    mom_low_vol: float = 0.15
    residual_momentum: float = 0.13
    proximity_52wh: float = 0.13
    industry_rs: float = 0.13
    fip_smoothness: float = 0.05
    bab: float = 0.05
    quality_proxy: float = 0.05
    # Sum = 0.99 ≈ 1.0 — normalized before use

    def as_dict(self) -> dict[str, float]:
        """Return weight dictionary keyed by signal name."""
        return {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]

    def normalized(self) -> dict[str, float]:
        """Return weights normalized to sum exactly to 1.0."""
        raw = self.as_dict()
        total = sum(raw.values())
        if total == 0:
            raise ValueError("SignalWeights: all weights are zero — cannot normalize")
        return {k: v / total for k, v in raw.items()}


# ---------------------------------------------------------------------------
# SelectionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionResult:
    """Output of select() per spec §6.4.

    entered   — new entries this rebalance
    held      — names held from yesterday (still in portfolio)
    exited    — forced exits (rank > stay_cutoff, governance hit, trend break)
    bench_hold — in top quintile by rank but blocked from entry (trend gate or
                 rank > enter_cutoff but ≤ stay_cutoff and not held yesterday)
    """

    entered: list[uuid.UUID]
    held: list[uuid.UUID]
    exited: list[uuid.UUID]
    bench_hold: list[uuid.UUID]


# ---------------------------------------------------------------------------
# compute_composite
# ---------------------------------------------------------------------------


def compute_composite(
    signals_panel: pd.DataFrame,
    weights: SignalWeights | dict[str, float] | None = None,
    winsorize_z: float = 3.0,
) -> pd.Series:
    """Blend sector-neutralized z-scores into a composite score per instrument.

    Parameters
    ----------
    signals_panel : pd.DataFrame
        Rows indexed by instrument_id (uuid.UUID).
        Columns: signal names (see _SIGNAL_COLUMNS) plus 'sector' (str).
        Missing signals are silently skipped (weight applied only to present columns).
    weights : SignalWeights | dict[str, float] | None
        Signal weights. None → default SignalWeights() priors, normalized.
    winsorize_z : float
        Z-score clip threshold. Default 3.0 (per spec §6.1).

    Returns
    -------
    pd.Series
        Composite score per instrument, same index as signals_panel.
        Range approximately [-3.5, +3.5] but unbounded by design.
    """
    if weights is None:
        weight_dict = SignalWeights().normalized()
    elif isinstance(weights, SignalWeights):
        weight_dict = weights.normalized()
    else:
        total = sum(weights.values())
        if total == 0:
            raise ValueError("weights sum to zero — cannot normalize")
        weight_dict = {k: v / total for k, v in weights.items()}

    if "sector" not in signals_panel.columns:
        raise ValueError("signals_panel must contain a 'sector' column")

    sectors: pd.Series = signals_panel["sector"]

    # Identify signal columns that exist in the panel
    present_signals = [col for col in weight_dict if col in signals_panel.columns]
    missing_signals = [col for col in weight_dict if col not in signals_panel.columns]
    if missing_signals:
        log.warning(
            "composite.missing_signals",
            missing=missing_signals,
            present=present_signals,
        )

    row_count_before = len(signals_panel)
    composite = pd.Series(0.0, index=signals_panel.index, dtype=float)

    for signal_col in present_signals:
        raw: pd.Series = signals_panel[signal_col].astype(float)

        # Sector-demeaned mean and std
        sector_mean: pd.Series = raw.groupby(sectors).transform("mean")
        sector_std: pd.Series = raw.groupby(sectors).transform("std", ddof=1)

        # Sectors with a single member → std = NaN → z = 0 (neutral, not excluded)
        sector_std = sector_std.replace(0.0, np.nan)

        z = (raw - sector_mean) / sector_std
        # Single-member sectors produce NaN z → set to 0
        z = z.fillna(0.0)

        # Winsorize
        z = z.clip(lower=-winsorize_z, upper=winsorize_z)

        composite = composite + weight_dict[signal_col] * z

    row_count_after = len(composite)
    if row_count_before != row_count_after:
        log.error(
            "composite.row_count_mismatch",
            before=row_count_before,
            after=row_count_after,
        )
        raise RuntimeError(
            f"Row count changed during compute_composite: {row_count_before} → {row_count_after}"
        )

    log.debug(
        "composite.computed",
        n_instruments=row_count_after,
        n_signals=len(present_signals),
    )
    return composite


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------


def select(
    composite: pd.Series,
    governance_excluded: set[uuid.UUID],
    trend_gate_pass: set[uuid.UUID],
    held_yesterday: set[uuid.UUID],
    enter_rank_cutoff: int = 30,
    stay_rank_cutoff: int = 50,
) -> SelectionResult:
    """Apply buffer zones and return SelectionResult per spec §6.4.

    Parameters
    ----------
    composite : pd.Series
        Composite scores indexed by instrument_id (uuid.UUID).
    governance_excluded : set[uuid.UUID]
        Instruments that fail governance checks. These receive composite = -inf
        and are forced-exited from held_yesterday.
    trend_gate_pass : set[uuid.UUID]
        Instruments where close >= 200dMA. Required for NEW entries.
        Held names are not re-gated.
    held_yesterday : set[uuid.UUID]
        Portfolio holdings from the previous rebalance.
    enter_rank_cutoff : int
        Names ranked ≤ this value can be newly entered. Default 30.
    stay_rank_cutoff : int
        Names ranked ≤ this value AND held yesterday stay in. Default 50.

    Returns
    -------
    SelectionResult
        entered   — newly entering this rebalance
        held      — continuing from yesterday
        exited    — removed this rebalance
        bench_hold — top quintile but blocked from entry
    """
    if enter_rank_cutoff > stay_rank_cutoff:
        raise ValueError(
            f"enter_rank_cutoff ({enter_rank_cutoff}) must be"
            f" ≤ stay_rank_cutoff ({stay_rank_cutoff})"
        )

    # Step 1: Apply governance exclusions → set composite to -inf
    scores = composite.copy().astype(float)
    gov_hits = set(scores.index) & governance_excluded
    if gov_hits:
        scores[list(gov_hits)] = float("-inf")
        log.info("composite.governance_excluded", count=len(gov_hits))

    # Step 2: Rank descending (rank 1 = highest composite)
    # method='first' ensures stable ordering with ties
    ranks: pd.Series = scores.rank(ascending=False, method="first")

    # Step 3: Classify each instrument
    entered: list[uuid.UUID] = []
    held_out: list[uuid.UUID] = []
    exited: list[uuid.UUID] = []
    bench_hold: list[uuid.UUID] = []

    all_ids = set(scores.index)
    held_yesterday_present = held_yesterday & all_ids

    for iid in scores.index:
        r = int(ranks[iid])
        is_held = iid in held_yesterday_present
        is_gov_excluded = iid in governance_excluded
        passes_trend = iid in trend_gate_pass

        # Governance-excluded: force exit if held, skip entirely if not held
        if is_gov_excluded:
            if is_held:
                exited.append(iid)
            # Not held + governance excluded → silently dropped (not entered, not bench_hold)
            continue

        # Held yesterday
        if is_held:
            if r <= stay_rank_cutoff:
                # Within stay buffer → keep
                held_out.append(iid)
            else:
                # Beyond stay cutoff → exit
                exited.append(iid)
            continue

        # Not held yesterday: can only enter if rank ≤ enter_rank_cutoff AND trend gate passes
        if r <= enter_rank_cutoff:
            if passes_trend:
                entered.append(iid)
            else:
                # Rank ≤ enter cutoff but trend gate blocked — bench_hold
                bench_hold.append(iid)
        elif r <= stay_rank_cutoff:
            # Between enter and stay cutoff, not held → bench_hold
            # (would stay if held, but can't newly enter at this rank)
            bench_hold.append(iid)
        # rank > stay_cutoff, not held → silently dropped (not entered, not bench_hold)

    log.info(
        "composite.selection",
        entered=len(entered),
        held=len(held_out),
        exited=len(exited),
        bench_hold=len(bench_hold),
        enter_cutoff=enter_rank_cutoff,
        stay_cutoff=stay_rank_cutoff,
    )

    return SelectionResult(
        entered=entered,
        held=held_out,
        exited=exited,
        bench_hold=bench_hold,
    )
