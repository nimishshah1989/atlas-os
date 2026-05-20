"""Wave 4C — soft-band IC tune in the OLD (pre-Task-4) classifier topology.

The first grid run used the CURRENT classifier (Task 4 cold-start path active),
which routes structurally-mature names to 2C bypassing the Stage-2A gate
entirely — so the soft band never filters them. To get a clean apples-to-apples
vs Task 5's +0.243 OLD baseline, this run drops in the OLD classify_state_panel
from commit 749282e (hard gate, NO cold-start) and sweeps theta_base_breakout
through the threshold dict.

This isolates: does the soft band, applied in the SAME topology Task 5's +0.243
was measured in, restore the 63d IR?

Run on EC2 (see wave4c_softband_ic_tune.py header for env setup).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os

import pandas as pd
from sqlalchemy import create_engine

from atlas.intelligence.states.thresholds import ThresholdValue, load_active_thresholds
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import compute_ic_over_window
from atlas.trading.cli import _compute_features_for_stock, _load_data

WARMUP_START = dt.date(2021, 11, 1)
VAL_START = dt.date(2023, 1, 1)
VAL_END = dt.date(2026, 5, 19)
THETA_GRID = [0.90, 0.92, 0.94, 0.96, 0.98, 1.00]
# Path to the OLD (commit 749282e) classifier dropped in for the apples-to-apples
# run. Override with WAVE4C_OLD_CLASSIFIER if running outside the default EC2 path.
_DEFAULT_OLD_CLASSIFIER = "/tmp/classifier_old_749282e.py"  # noqa: S108 -- developer-supplied analysis artifact path, not untrusted input
OLD_CLASSIFIER_PATH = os.environ.get("WAVE4C_OLD_CLASSIFIER", _DEFAULT_OLD_CLASSIFIER)


def load_old_classifier():
    spec = importlib.util.spec_from_file_location("classifier_old", OLD_CLASSIFIER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_panel(eng) -> pd.DataFrame:
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

    old = load_old_classifier()
    print("[0] OLD classifier (749282e) loaded — hard gate, NO cold-start path")

    print("[1] Building feature panel ...")
    features = build_panel(eng)

    print("[2] Loading forward returns ...")
    prices = load_price_matrix(eng, start_date=VAL_START, end_date=VAL_END)
    fwd = compute_forward_returns(prices, periods=[21, 63])
    ret_21 = fwd["return_21d"]
    ret_63 = fwd["return_63d"]

    thresholds = load_active_thresholds(eng)
    print(f"  loaded {len(thresholds)} live thresholds")
    latest_date = max(features["date"])

    results = []
    for theta in THETA_GRID:
        print(f"[3] OLD-topology, theta_base_breakout = {theta:.2f} ...")
        th = dict(thresholds)
        th[("theta_base_breakout", "stage_2a")] = ThresholdValue(theta, None, None)
        panel = old.classify_state_panel(features, th, "wave4c-softband-oldtopo")

        factor = membership_factor(panel)
        ir63, mic63, n63 = compute_ir(factor, ret_63)
        ir21, _mic21, _n21 = compute_ir(factor, ret_21)
        latest = panel[pd.to_datetime(panel["date"]).dt.date == latest_date]
        n_2a = int((latest["state"] == "stage_2a").sum())
        n_2b = int((latest["state"] == "stage_2b").sum())
        n_2c = int((latest["state"] == "stage_2c").sum())
        results.append(
            {
                "theta": theta,
                "ir_63d": ir63,
                "ir_21d": ir21,
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
    print("WAVE 4C SOFT-BAND IC-TUNE GRID — OLD TOPOLOGY (no cold-start)")
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
        print(
            f"CLEARED 0.243 in 0.90-0.98: theta={[r['theta'] for r in passing]} "
            f"-> chosen {best['theta']:.2f} (cohort {best['stage_2a']})"
        )
    else:
        print("NO soft-band value in 0.90-0.98 clears 0.243 in OLD topology either.")
    print("=" * 78)


if __name__ == "__main__":
    main()
