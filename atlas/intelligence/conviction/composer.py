"""Compute conviction scores per (instrument, date) using tier-active weights.

Per stock:

1. Identify the stock's liquidity tier (from ``tier_assignment``).
2. Load the active weight set for that tier.
3. Cross-sectionally percentile-rank each signal within the tier.
4. Apply weights: ``score = sum(w_i × (rank_i if not flipped else 1 - rank_i))``.
5. Renormalize by the sum of weights actually applied (handles missing signals).
6. Build a ``contributing_signals`` JSONB blob for the UI breakdown panel.
7. Assign a tier-conditional ``confidence_label`` from the measured holdout IC.

The breakdown records ``was_neutral_fill`` so the UI can flag stocks where
a NaN signal value was neutral-filled to 0.5 rather than measured.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.tier_assignment import compute_tier_membership
from atlas.intelligence.conviction.weight_loader import (
    TierWeightSet,
    load_active_weights,
)

log = structlog.get_logger()

CONFIDENCE_LABEL_THRESHOLD: Final[Decimal] = Decimal("0.05")

SIGNAL_COLUMNS: Final[tuple[str, ...]] = (
    "rs_pctile_3m",
    "ret_6m",
    "ret_12m_1m",
    "ema_10_ratio",
    "extension_pct",
    "vol_ratio_63",
    "max_drawdown_252",
    "realized_vol_63",
    "atr_21",
    "ma_30w_slope_4w",
    "effort_ratio_63",
)


def assign_confidence_label(holdout_ic: Decimal | None) -> str:
    """Map measured holdout IC magnitude to a frontend confidence badge.

    ``industry_grade`` when ``|holdout_ic| >= 0.05``; ``baseline`` for
    smaller magnitudes; ``descriptive_only`` when no IC has been measured.
    """
    if holdout_ic is None:
        return "descriptive_only"
    if abs(holdout_ic) >= CONFIDENCE_LABEL_THRESHOLD:
        return "industry_grade"
    return "baseline"


def apply_weights_to_percentile_ranks(df: pd.DataFrame, weights: TierWeightSet) -> pd.DataFrame:
    """Apply ``weights`` to pre-ranked signal columns and return scored df.

    ``df`` must have ``instrument_id`` plus ``<signal>_pct`` columns for
    each signal in ``weights.signals`` that's available. Missing signals
    are skipped; the remaining weights are renormalized so the score stays
    in ``[0, 1]``.
    """
    out: pd.DataFrame = df.loc[:, ["instrument_id"]].copy()
    n = len(df)
    weighted_sum = pd.Series(0.0, index=df.index)
    weight_applied_total = 0.0
    breakdown_per_row: list[dict[str, dict[str, float | bool]]] = [{} for _ in range(n)]

    for signal_name, weight, flipped in weights.signals:
        col = f"{signal_name}_pct"
        if col not in df.columns:
            continue

        raw_pct = pd.Series(pd.to_numeric(df[col], errors="coerce"))
        was_nan = raw_pct.isna()
        applied: pd.Series = raw_pct.where(~was_nan, 0.5)
        if flipped:
            applied = 1.0 - applied

        w = float(weight)
        weighted_sum = weighted_sum + (w * applied)
        weight_applied_total += w

        applied_list = applied.tolist()
        nan_flags = was_nan.tolist()
        for i in range(n):
            breakdown_per_row[i][signal_name] = {
                "weight": w,
                "flipped": flipped,
                "percentile_rank": float(applied_list[i]),
                "contribution": w * float(applied_list[i]),
                "was_neutral_fill": bool(nan_flags[i]),
            }

    if weight_applied_total == 0:
        out["conviction_score"] = 0.5
    else:
        out["conviction_score"] = weighted_sum / weight_applied_total
    out["contributing_signals"] = [json.dumps(b) for b in breakdown_per_row]
    return out


def _load_raw_signals(engine: Engine, *, as_of: date, instrument_ids: list[str]) -> pd.DataFrame:
    """Load all signal columns for the given instruments on ``as_of``."""
    cols = ", ".join(SIGNAL_COLUMNS)
    sql = text(
        f"""
        SELECT instrument_id::text AS instrument_id,
               {cols}
        FROM atlas.atlas_stock_metrics_daily
        WHERE date = :as_of
          AND instrument_id = ANY(CAST(:uni AS uuid[]))
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(
            sql,
            conn,
            params={"as_of": as_of, "uni": instrument_ids},
        )


def compute_conviction_scores(engine: Engine, *, as_of: date) -> pd.DataFrame:
    """Compute conviction scores for every tiered instrument on ``as_of``.

    Output columns: ``instrument_id, date, tier, conviction_score,
    confidence_label, backing_ic, contributing_signals,
    weight_set_version``. Empty DataFrame if there's no tier data or no
    metrics data for the date.
    """
    out_cols = [
        "instrument_id",
        "date",
        "tier",
        "conviction_score",
        "confidence_label",
        "backing_ic",
        "contributing_signals",
        "weight_set_version",
    ]

    tier_df = compute_tier_membership(engine, as_of=as_of)
    if tier_df.empty:
        return pd.DataFrame({c: pd.Series(dtype=object) for c in out_cols})

    weights_by_tier = load_active_weights(engine, regime="all")
    if not weights_by_tier:
        log.error("no_active_weights_seeded")
        raise RuntimeError(
            "No active weight sets in atlas_signal_weights. "
            "Run scripts/seed_signal_weights.py first."
        )

    instruments = tier_df["instrument_id"].tolist()
    raw_signals = _load_raw_signals(engine, as_of=as_of, instrument_ids=instruments)

    out_rows: list[pd.DataFrame] = []
    for tier_name, weight_set in weights_by_tier.items():
        tier_instruments = tier_df.loc[tier_df["tier"] == tier_name, "instrument_id"].tolist()
        if not tier_instruments:
            continue

        mask = raw_signals["instrument_id"].isin(tier_instruments)
        tier_raw: pd.DataFrame = raw_signals.loc[mask].copy()
        if tier_raw.empty:
            continue

        for sig in SIGNAL_COLUMNS:
            sig_series = pd.Series(pd.to_numeric(tier_raw[sig], errors="coerce"))
            tier_raw[f"{sig}_pct"] = sig_series.rank(pct=True)

        scored = apply_weights_to_percentile_ranks(tier_raw, weight_set)
        scored["tier"] = tier_name
        scored["date"] = as_of
        scored["confidence_label"] = assign_confidence_label(weight_set.holdout_ic)
        scored["backing_ic"] = (
            float(weight_set.holdout_ic) if weight_set.holdout_ic is not None else None
        )
        scored["weight_set_version"] = weight_set.weight_set_version
        out_rows.append(scored)

    if not out_rows:
        return pd.DataFrame({c: pd.Series(dtype=object) for c in out_cols})

    final = pd.concat(out_rows, ignore_index=True)
    log.info("conviction_computed", as_of=str(as_of), n_rows=len(final))

    result: pd.DataFrame = final.loc[:, out_cols]
    return result
