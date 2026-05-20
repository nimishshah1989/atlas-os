"""Wave 4C — soft-band breakout gate IC tuning (READ + COMPUTE only, no DB writes).

Re-introduces the Stage-2A breakout gate as a SOFT tolerance band and grids
theta_base_breakout in {0.90, 0.92, 0.94, 0.96, 0.98} (plus 1.00 baseline).
For each theta it classifies the 2023-2026 panel in memory and computes the
Stage-2 (a u b u c) membership IC at the 63d and 21d horizons, exactly as
Wave 4C Task 5 did.

Run on EC2:
  cd /home/ubuntu/atlas-os-consolidation
  source /home/ubuntu/atlas-os/.venv/bin/activate
  export PYTHONPATH=/home/ubuntu/atlas-os-consolidation
  set -a && source .env && set +a
  python3 scripts/wave4c_softband_ic_tune.py
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
from sqlalchemy import create_engine

import atlas.intelligence.states.classifier as clf
from atlas.intelligence.states.classifier import classify_state_panel
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import compute_ic_over_window
from atlas.trading.cli import _compute_features_for_stock, _load_data

# Validation window — same as Task 5.
WARMUP_START = dt.date(2021, 11, 1)
VAL_START = dt.date(2023, 1, 1)
VAL_END = dt.date(2026, 5, 19)
THETA_GRID = [0.90, 0.92, 0.94, 0.96, 0.98, 1.00]

# Capture the unmodified (post-Task-3, gate-removed) classifier function.
_BASE_CLASSIFY_2A = clf.classify_stage_2a


def make_softband_2a(theta_base_breakout: float):
    """Return a classify_stage_2a wrapper that ADDS the soft breakout band.

    Conjoins close >= theta_base_breakout * max_close_60d onto the existing
    (post-Task-3) Stage-2A predicate. All other gates unchanged.
    """

    def classify_stage_2a_softband(
        prior_state,
        close,
        sma_50,
        sma_150,
        sma_200,
        sma_200_slope,
        max_close_60d,
        rs_rank_12m,
        days_in_stage_2,
        thresholds,
    ):
        base = _BASE_CLASSIFY_2A(
            prior_state,
            close,
            sma_50,
            sma_150,
            sma_200,
            sma_200_slope,
            max_close_60d,
            rs_rank_12m,
            days_in_stage_2,
            thresholds,
        )
        if not base:
            return False
        # Soft breakout band: close must be within tolerance of the 60d high.
        if clf._is_nan(max_close_60d) or max_close_60d <= 0:
            # No valid 60d high (early history) — admit, consistent with the
            # production feature panel where max_close_60d is NaN < 60 bars.
            return True
        return close >= theta_base_breakout * max_close_60d

    return classify_stage_2a_softband


def build_panel(eng) -> pd.DataFrame:
    """Build the 2023-2026 feature panel (with 400d warm-up). Returns features DF."""
    metrics, _regime = _load_data(WARMUP_START, VAL_END, "stocks_nifty500")
    print(
        f"  loaded metrics: {len(metrics):,} rows, "
        f"{metrics['instrument_id'].nunique()} instruments"
    )
    feature_dfs = [
        _compute_features_for_stock(group) for _iid, group in metrics.groupby("instrument_id")
    ]
    features = pd.concat(feature_dfs, ignore_index=True)
    features["rs_rank_12m"] = features.groupby("date")["ret_12m_raw"].rank(pct=True).fillna(0.5)
    features["date"] = pd.to_datetime(features["date"]).dt.date
    features = features[features["date"].between(VAL_START, VAL_END)].reset_index(drop=True)
    print(f"  feature panel: {len(features):,} (date, instrument) rows")
    return features


def membership_factor(panel: pd.DataFrame) -> pd.DataFrame:
    """Turn 'in Stage 2 (2a u 2b u 2c)' into a 0/1 MultiIndex factor."""
    f = panel[["date", "instrument_id", "state"]].copy()
    f["factor"] = f["state"].isin(["stage_2a", "stage_2b", "stage_2c"]).astype(float)
    f["date"] = pd.to_datetime(f["date"])
    return f.set_index(["date", "instrument_id"])[["factor"]]


def compute_ir(factor: pd.DataFrame, returns_wide: pd.DataFrame) -> tuple[float, float, int]:
    ic = compute_ic_over_window(factor, returns_wide)
    ir = ic.mean_ic / ic.ic_std if ic.ic_std and ic.ic_std > 0 else 0.0
    return float(ir), float(ic.mean_ic), int(ic.n_observations)


def main() -> None:
    db_url = os.environ["ATLAS_DB_URL"]
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    print("[1] Building feature panel ...")
    features = build_panel(eng)

    print("[2] Loading forward returns ...")
    prices = load_price_matrix(eng, start_date=VAL_START, end_date=VAL_END)
    fwd = compute_forward_returns(prices, periods=[21, 63])
    ret_21 = fwd["return_21d"]
    ret_63 = fwd["return_63d"]

    # Pull the live thresholds for the classifier (the soft-band wrapper hard-codes
    # theta itself, so no theta_base_breakout entry is needed here).
    from atlas.intelligence.states.thresholds import load_active_thresholds

    thresholds = load_active_thresholds(eng)
    print(f"  loaded {len(thresholds)} live thresholds")

    latest_date = max(p for p in features["date"])
    print(f"  latest panel date: {latest_date}")

    results = []
    for theta in THETA_GRID:
        print(f"[3] theta_base_breakout = {theta:.2f} ...")
        clf.classify_stage_2a = make_softband_2a(theta)
        try:
            panel = classify_state_panel(features, thresholds, "wave4c-softband")
        finally:
            clf.classify_stage_2a = _BASE_CLASSIFY_2A

        factor = membership_factor(panel)
        ir63, mic63, n63 = compute_ir(factor, ret_63)
        ir21, mic21, n21 = compute_ir(factor, ret_21)

        latest = panel[pd.to_datetime(panel["date"]).dt.date == latest_date]
        n_2a = int((latest["state"] == "stage_2a").sum())
        n_2b = int((latest["state"] == "stage_2b").sum())
        n_2c = int((latest["state"] == "stage_2c").sum())

        results.append(
            {
                "theta": theta,
                "ir_63d": ir63,
                "mic_63d": mic63,
                "n63": n63,
                "ir_21d": ir21,
                "mic_21d": mic21,
                "n21": n21,
                "stage_2a": n_2a,
                "stage_2b": n_2b,
                "stage_2c": n_2c,
            }
        )
        print(
            f"    63d IR={ir63:+.4f} (mic={mic63:+.6f}, n={n63})  "
            f"21d IR={ir21:+.4f}  2A={n_2a} 2B={n_2b} 2C={n_2c}"
        )

    print()
    print("=" * 78)
    print("WAVE 4C SOFT-BAND IC-TUNE GRID")
    print("=" * 78)
    print(
        f"{'theta':>7} | {'Stage-2 63d IR':>15} | {'21d IR':>9} | "
        f"{'2A cnt':>7} | {'2B':>4} | {'2C':>4}"
    )
    print("-" * 78)
    for r in results:
        print(
            f"{r['theta']:>7.2f} | {r['ir_63d']:>+15.4f} | {r['ir_21d']:>+9.4f} | "
            f"{r['stage_2a']:>7} | {r['stage_2b']:>4} | {r['stage_2c']:>4}"
        )
    print("-" * 78)

    bar = 0.243
    passing = [r for r in results if r["theta"] <= 0.98 and r["ir_63d"] >= bar]
    if passing:
        best = max(passing, key=lambda r: r["stage_2a"])
        print(f"BAR: Stage-2 63d IR >= {bar}")
        print(f"CLEARED: theta in {[r['theta'] for r in passing]}")
        print(
            f"CHOSEN : theta={best['theta']:.2f} "
            f"(63d IR={best['ir_63d']:+.4f}, 2A cohort={best['stage_2a']}, "
            f"largest cohort among passers)"
        )
        print("VERDICT: SHIP")
    else:
        print(f"BAR: Stage-2 63d IR >= {bar}")
        print("CLEARED: NONE in 0.90-0.98")
        print("VERDICT: DO-NOT-SHIP — recommend keeping theta_base_breakout=1.000")
    print("=" * 78)


if __name__ == "__main__":
    main()
