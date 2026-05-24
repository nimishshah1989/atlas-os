"""Per-component IC validator for the Atlas State Engine.

Each (component, badge) pair gets its own IC validation against forward
returns at the badge's implied horizon. Status taxonomy mirrors state_validator:
  - validated:          IR > 0.4 AND sign matches implied_action
  - validated_inverse:  IR > 0.4 AND sign opposite to implied_action
  - weak:               IR in (0.2, 0.4)
  - decorative:         IR <= 0.2

Reuses atlas/intelligence/validation/{ic_engine, forward_returns}.

Public API:
  validate_all_components(engine, start, end) -> list[ComponentValidationResult]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import compute_ic_over_window

log = structlog.get_logger()

ComponentStatus = Literal["validated", "validated_inverse", "weak", "decorative"]


@dataclass(frozen=True)
class ComponentValidationResult:
    component_name: str
    badge: str
    threshold_range: str
    implied_action: str
    horizon_days: int
    as_of: date
    mean_ic: float
    ic_std: float
    ic_t_stat: float
    ic_ir: float
    q5_q1_spread: float
    n_observations: int
    status: ComponentStatus


# Catalog: each entry = a (component, badge) row that gets independently validated.
# implied_action: 'favours_long' = top tier should have POSITIVE IC.
#                 'warns_long'   = top tier should have NEGATIVE IC.
#                 'neutral_informational' = magnitude matters; sign is not prescribed.
_COMPONENT_CATALOG: list[dict] = [
    # RS rank: 5 tiers; implied favours_long
    {
        "name": "rs_rank_12m",
        "badge": "Leader",
        "range": "rs_rank_12m >= 0.90",
        "low": 0.90,
        "high": 1.01,
        "implied": "favours_long",
        "horizon": 63,
    },
    {
        "name": "rs_rank_12m",
        "badge": "Strong",
        "range": "rs_rank_12m in [0.70, 0.90)",
        "low": 0.70,
        "high": 0.90,
        "implied": "favours_long",
        "horizon": 63,
    },
    {
        "name": "rs_rank_12m",
        "badge": "Average",
        "range": "rs_rank_12m in [0.30, 0.70)",
        "low": 0.30,
        "high": 0.70,
        "implied": "neutral_informational",
        "horizon": 63,
    },
    {
        "name": "rs_rank_12m",
        "badge": "Weak",
        "range": "rs_rank_12m in [0.10, 0.30)",
        "low": 0.10,
        "high": 0.30,
        "implied": "warns_long",
        "horizon": 63,
    },
    {
        "name": "rs_rank_12m",
        "badge": "Laggard",
        "range": "rs_rank_12m < 0.10",
        "low": 0.0,
        "high": 0.10,
        "implied": "warns_long",
        "horizon": 63,
    },
    # OBV slope 50d: 2 tiers
    {
        "name": "obv_slope_50d",
        "badge": "Accumulation",
        "range": "obv_slope > 0",
        "low": 0.0,
        "high": float("inf"),
        "implied": "favours_long",
        "horizon": 63,
    },
    {
        "name": "obv_slope_50d",
        "badge": "Distribution",
        "range": "obv_slope < 0",
        "low": float("-inf"),
        "high": 0.0,
        "implied": "warns_long",
        "horizon": 63,
    },
    # Realized vol 63d: 4 tiers by cross-sectional percentile
    {
        "name": "realized_vol_63",
        "badge": "Low",
        "range": "cross-sectional percentile [0, 0.25)",
        "low": 0.0,
        "high": 0.25,
        "implied": "warns_long",
        "horizon": 63,
        "percentile": True,
    },
    {
        "name": "realized_vol_63",
        "badge": "Normal",
        "range": "cross-sectional percentile [0.25, 0.50)",
        "low": 0.25,
        "high": 0.50,
        "implied": "neutral_informational",
        "horizon": 63,
        "percentile": True,
    },
    {
        "name": "realized_vol_63",
        "badge": "Elevated",
        "range": "cross-sectional percentile [0.50, 0.75)",
        "low": 0.50,
        "high": 0.75,
        "implied": "neutral_informational",
        "horizon": 63,
        "percentile": True,
    },
    {
        "name": "realized_vol_63",
        "badge": "High",
        "range": "cross-sectional percentile >= 0.75",
        "low": 0.75,
        "high": 1.01,
        "implied": "favours_long",
        "horizon": 63,
        "percentile": True,
    },
    # ATR contraction ratio (atr_14 / atr_14_252d_avg): 2 tiers
    {
        "name": "atr_contraction_ratio",
        "badge": "Contracting",
        "range": "atr_14/atr_14_252d_avg < 1.0",
        "low": 0.0,
        "high": 1.0,
        "implied": "favours_long",
        "horizon": 63,
    },
    {
        "name": "atr_contraction_ratio",
        "badge": "Expanding",
        "range": "atr_14/atr_14_252d_avg >= 1.0",
        "low": 1.0,
        "high": float("inf"),
        "implied": "warns_long",
        "horizon": 63,
    },
]


def _build_factor_for_component(
    engine: Engine,
    component_name: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Build continuous factor series for a component, indexed by (date, instrument_id).

    Returns DataFrame with MultiIndex (date, instrument_id) and column 'factor'.
    Empty DataFrame if no data is available.
    """
    if component_name == "rs_rank_12m":
        with engine.connect() as c:
            df = pd.read_sql(
                text("""
                    SELECT date, instrument_id::text AS instrument_id,
                           rs_rank_12m AS factor
                    FROM atlas.atlas_stock_state_daily
                    WHERE date BETWEEN :s AND :e
                      AND rs_rank_12m IS NOT NULL
                """),
                c,
                params={"s": start, "e": end},
            )
    elif component_name == "realized_vol_63":
        with engine.connect() as c:
            df = pd.read_sql(
                text("""
                    SELECT date, instrument_id::text AS instrument_id,
                           realized_vol_63::numeric AS factor
                    FROM atlas.atlas_stock_metrics_daily
                    WHERE date BETWEEN :s AND :e
                      AND realized_vol_63 IS NOT NULL
                """),
                c,
                params={"s": start, "e": end},
            )
    elif component_name in ("obv_slope_50d", "atr_contraction_ratio"):
        df = _build_ohlcv_derived_factor(engine, component_name, start, end)
    else:
        raise ValueError(f"unknown component: {component_name}")

    if df.empty:
        empty = pd.DataFrame(columns=["factor"])
        empty.index = pd.MultiIndex.from_tuples([], names=["date", "instrument_id"])
        return empty

    df["date"] = pd.to_datetime(df["date"])
    df["factor"] = df["factor"].astype(float)
    return df.set_index(["date", "instrument_id"])[["factor"]]


def _build_ohlcv_derived_factor(
    engine: Engine,
    component_name: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Compute OBV slope or ATR contraction ratio from raw OHLCV data."""
    with engine.connect() as c:
        ohlcv = pd.read_sql(
            text("""
                SELECT p.instrument_id::text AS instrument_id, p.date,
                       COALESCE(p.close_adj, p.close) AS close,
                       p.high, p.low, p.volume
                FROM public.de_equity_ohlcv p
                WHERE p.date BETWEEN :s AND :e
                  AND COALESCE(p.close_adj, p.close) IS NOT NULL
            """),
            c,
            params={"s": start, "e": end},
        )

    if ohlcv.empty:
        return pd.DataFrame(columns=["date", "instrument_id", "factor"])

    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv = ohlcv.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    before_count = len(ohlcv)
    log.info("ohlcv_loaded_for_factor", component=component_name, rows=before_count)

    rows: list[dict] = []
    for iid, g in ohlcv.groupby("instrument_id"):
        g = g.sort_values("date").reset_index(drop=True)
        if component_name == "obv_slope_50d":
            daily_ret = g["close"].pct_change()
            obv = (g["volume"] * np.sign(daily_ret).fillna(0)).cumsum()
            val = obv.rolling(50, min_periods=50).apply(
                lambda a: np.polyfit(np.arange(len(a)), a, 1)[0] / max(abs(float(a.mean())), 1e-9),
                raw=True,
            )
        else:  # atr_contraction_ratio
            prev_close = g["close"].shift(1)
            tr = pd.concat(
                [
                    g["high"] - g["low"],
                    (g["high"] - prev_close).abs(),
                    (g["low"] - prev_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr14 = tr.rolling(14, min_periods=14).mean()
            atr252 = atr14.rolling(252, min_periods=252).mean()
            val = atr14 / atr252.replace(0, pd.NA)

        for i, dt in enumerate(g["date"]):
            if i >= len(val):
                continue
            v = val.iloc[i]
            if pd.notna(v) and np.isfinite(float(v)):
                rows.append({"date": dt, "instrument_id": iid, "factor": float(v)})

    after_count = len(rows)
    log.info(
        "ohlcv_factor_computed",
        component=component_name,
        before=before_count,
        after=after_count,
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "instrument_id", "factor"])


def _tier_membership(
    factor: pd.DataFrame,
    low: float,
    high: float,
    percentile: bool = False,
) -> pd.DataFrame:
    """Build boolean tier membership: 1.0 where factor is in [low, high), else 0.0.

    If percentile=True, ranks factor cross-sectionally per-date before comparing.
    """
    out = factor.copy()
    if percentile:
        out["factor"] = factor.groupby(level="date")["factor"].rank(pct=True)
    out["factor"] = ((out["factor"] >= low) & (out["factor"] < high)).astype(float)
    return out


def _classify_status(ir: float, implied: str) -> ComponentStatus:
    """Map (IR, implied_action) to ComponentStatus."""
    abs_ir = abs(ir)
    if abs_ir <= 0.2:
        return "decorative"
    if abs_ir <= 0.4:
        return "weak"
    # |IR| > 0.4 — check sign alignment
    if implied == "favours_long":
        return "validated" if ir > 0 else "validated_inverse"
    if implied == "warns_long":
        return "validated" if ir < 0 else "validated_inverse"
    # neutral_informational: magnitude IS the signal; any |IR|>0.4 = validated
    return "validated"


def _compute_q5_q1_spread(
    tier: pd.DataFrame,
    returns_wide: pd.DataFrame,
) -> float:
    """Mean forward return of tier=1 minus tier=0 across dates."""
    long_returns = returns_wide.stack()
    long_returns.name = "fwd_return"
    long_returns.index = long_returns.index.set_names(["date", "instrument_id"])
    joined = tier.join(long_returns, how="inner").dropna()

    if joined.empty or joined["factor"].nunique() < 2:
        return 0.0

    diffs: list[float] = []
    for _, g in joined.groupby(level="date"):
        if g["factor"].nunique() < 2:
            continue
        top_ret = g.loc[g["factor"] == 1.0, "fwd_return"].mean()
        bot_ret = g.loc[g["factor"] == 0.0, "fwd_return"].mean()
        if pd.notna(top_ret) and pd.notna(bot_ret):
            diffs.append(float(top_ret - bot_ret))

    return float(np.mean(diffs)) if diffs else 0.0


def _persist(engine: Engine, result: ComponentValidationResult) -> None:
    """UPSERT one component-validation row into atlas_component_validation."""
    sql = """
    INSERT INTO atlas.atlas_component_validation
        (component_name, badge, threshold_range, implied_action, horizon_days,
         as_of_date, mean_ic, ic_std, ic_t_stat, ic_ir, q5_q1_spread,
         n_observations, status)
    VALUES
        (:component_name, :badge, :threshold_range, :implied_action, :horizon_days,
         :as_of, :mean_ic, :ic_std, :ic_t_stat, :ic_ir, :q5_q1_spread, :n_obs, :status)
    ON CONFLICT (component_name, badge, horizon_days, as_of_date) DO UPDATE SET
        threshold_range = EXCLUDED.threshold_range,
        implied_action = EXCLUDED.implied_action,
        mean_ic = EXCLUDED.mean_ic,
        ic_std = EXCLUDED.ic_std,
        ic_t_stat = EXCLUDED.ic_t_stat,
        ic_ir = EXCLUDED.ic_ir,
        q5_q1_spread = EXCLUDED.q5_q1_spread,
        n_observations = EXCLUDED.n_observations,
        status = EXCLUDED.status,
        validated_at = NOW()
    """
    with engine.begin() as c:
        c.execute(
            text(sql),
            {
                "component_name": result.component_name,
                "badge": result.badge,
                "threshold_range": result.threshold_range,
                "implied_action": result.implied_action,
                "horizon_days": result.horizon_days,
                "as_of": result.as_of,
                "mean_ic": float(result.mean_ic),
                "ic_std": float(result.ic_std),
                "ic_t_stat": float(result.ic_t_stat),
                "ic_ir": float(result.ic_ir),
                "q5_q1_spread": float(result.q5_q1_spread),
                "n_obs": int(result.n_observations),
                "status": result.status,
            },
        )


def validate_all_components(
    engine: Engine,
    start: date,
    end: date,
) -> list[ComponentValidationResult]:
    """Run IC validation for every (component, badge) in the catalog.

    Persists each result to atlas.atlas_component_validation via UPSERT.
    Returns all results including those from failed/empty factor panels
    (empty factor → skipped, not returned).
    """
    prices = load_price_matrix(engine, start_date=start, end_date=end)
    if prices.empty:
        log.error("no_price_data", start=str(start), end=str(end))
        return []

    horizons = sorted({entry["horizon"] for entry in _COMPONENT_CATALOG})
    fwd = compute_forward_returns(prices, periods=horizons)

    # Cache factor panels per component_name to avoid redundant DB/compute calls.
    factor_cache: dict[str, pd.DataFrame] = {}
    results: list[ComponentValidationResult] = []
    as_of = end

    for entry in _COMPONENT_CATALOG:
        cname = entry["name"]
        if cname not in factor_cache:
            factor_cache[cname] = _build_factor_for_component(engine, cname, start, end)
        factor = factor_cache[cname]
        if factor.empty:
            log.warning("empty_factor_panel", component=cname)
            continue

        tier = _tier_membership(
            factor,
            entry["low"],
            entry["high"],
            percentile=entry.get("percentile", False),
        )

        returns_wide = fwd[f"return_{entry['horizon']}d"]
        ic = compute_ic_over_window(tier, returns_wide)
        ir = (ic.mean_ic / ic.ic_std) if ic.ic_std and ic.ic_std > 0 else 0.0
        q5_q1 = _compute_q5_q1_spread(tier, returns_wide)
        status = _classify_status(ir, entry["implied"])

        result = ComponentValidationResult(
            component_name=cname,
            badge=entry["badge"],
            threshold_range=entry["range"],
            implied_action=entry["implied"],
            horizon_days=entry["horizon"],
            as_of=as_of,
            mean_ic=float(ic.mean_ic)
            if not (isinstance(ic.mean_ic, float) and np.isnan(ic.mean_ic))
            else 0.0,
            ic_std=float(ic.ic_std)
            if not (isinstance(ic.ic_std, float) and np.isnan(ic.ic_std))
            else 0.0,
            ic_t_stat=float(ic.ic_t_stat)
            if not (isinstance(ic.ic_t_stat, float) and np.isnan(ic.ic_t_stat))
            else 0.0,
            ic_ir=float(ir),
            q5_q1_spread=q5_q1,
            n_observations=int(ic.n_observations),
            status=status,
        )
        _persist(engine, result)
        log.info(
            "component_validated",
            component=cname,
            badge=entry["badge"],
            status=status,
            ic_ir=round(ir, 4),
            q5_q1=round(q5_q1, 4),
        )
        results.append(result)

    return results
