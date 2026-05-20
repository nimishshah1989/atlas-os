"""Wave 4C — FINAL validation gate for the soft-band breakout rework.

Classifies the 2023-2026 panel with the SHIPPING classifier (current
classify_state_panel — Task 4 cold-start path + the re-introduced breakout gate)
and reports the Stage-2 (a u b u c) membership 63d/21d IR. The breakout gate
threshold is read live from atlas_state_thresholds (expected: 1.000).

Reference baselines (from wave4c_softband_ic_tune_old_topology.py):
  OLD topology, hard gate 1.000 = +0.2431 (matches Task 5's +0.243 exactly)
  Task 3 gate-removed (Task 5)   = +0.179

SHIP bar: Stage-2 state 63d IR >= 0.243.

Run on EC2 (see wave4c_softband_ic_tune.py header for env setup).
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
from sqlalchemy import create_engine

from atlas.intelligence.states.classifier import classify_state_panel
from atlas.intelligence.states.thresholds import get as get_threshold
from atlas.intelligence.states.thresholds import load_active_thresholds
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import compute_ic_over_window
from atlas.trading.cli import _compute_features_for_stock, _load_data

WARMUP_START = dt.date(2021, 11, 1)
VAL_START = dt.date(2023, 1, 1)
VAL_END = dt.date(2026, 5, 19)


def main() -> None:
    db_url = os.environ["ATLAS_DB_URL"]
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    thresholds = load_active_thresholds(eng)
    theta = get_threshold(thresholds, "theta_base_breakout", "stage_2a", default=1.000)
    print(f"[0] theta_base_breakout (live) = {theta}")

    print("[1] Building feature panel ...")
    metrics, _regime = _load_data(WARMUP_START, VAL_END, "stocks_nifty500")
    feature_dfs = [
        _compute_features_for_stock(group) for _iid, group in metrics.groupby("instrument_id")
    ]
    features = pd.concat(feature_dfs, ignore_index=True)
    features["rs_rank_12m"] = features.groupby("date")["ret_12m_raw"].rank(pct=True).fillna(0.5)
    features["date"] = pd.to_datetime(features["date"]).dt.date
    features = features[features["date"].between(VAL_START, VAL_END)].reset_index(drop=True)
    print(f"  feature panel: {len(features):,} (date, instrument) rows")

    print("[2] Loading forward returns ...")
    prices = load_price_matrix(eng, start_date=VAL_START, end_date=VAL_END)
    fwd = compute_forward_returns(prices, periods=[21, 63])

    print("[3] Classifying with the SHIPPING classifier ...")
    panel = classify_state_panel(features, thresholds, "wave4c-softband-final")

    f = panel[["date", "instrument_id", "state"]].copy()
    f["factor"] = f["state"].isin(["stage_2a", "stage_2b", "stage_2c"]).astype(float)
    f["date"] = pd.to_datetime(f["date"])
    factor = f.set_index(["date", "instrument_id"])[["factor"]]

    def ir(ret):
        ic = compute_ic_over_window(factor, ret)
        return (
            (ic.mean_ic / ic.ic_std if ic.ic_std and ic.ic_std > 0 else 0.0),
            float(ic.mean_ic),
            int(ic.n_observations),
        )

    ir63, mic63, n63 = ir(fwd["return_63d"])
    ir21, mic21, n21 = ir(fwd["return_21d"])

    latest_date = max(features["date"])
    latest = panel[pd.to_datetime(panel["date"]).dt.date == latest_date]
    n_2a = int((latest["state"] == "stage_2a").sum())
    n_2b = int((latest["state"] == "stage_2b").sum())
    n_2c = int((latest["state"] == "stage_2c").sum())

    print()
    print("=" * 70)
    print("WAVE 4C — FINAL SOFT-BAND VALIDATION GATE")
    print("=" * 70)
    print(f"  theta_base_breakout         : {theta}")
    print(f"  Stage-2 (aubuc) 63d IR      : {ir63:+.4f}  (mic={mic63:+.6f}, n={n63})")
    print(f"  Stage-2 (aubuc) 21d IR      : {ir21:+.4f}  (mic={mic21:+.6f}, n={n21})")
    print(f"  Latest-date ({latest_date}) cohort : 2A={n_2a}  2B={n_2b}  2C={n_2c}")
    print("-" * 70)
    print("  SHIP bar                    : Stage-2 63d IR >= 0.243")
    print(f"  RESULT                      : {ir63:+.4f}")
    print(f"  VERDICT                     : {'SHIP' if ir63 >= 0.243 else 'DO-NOT-SHIP'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
