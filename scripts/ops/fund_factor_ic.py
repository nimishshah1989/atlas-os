#!/usr/bin/env python3
"""Empirical fund-factor IC backtest — derive ranking weights from data, not gut.

For each month-end t over the available history, for every equity fund with >=3y
of trailing NAV, compute a set of candidate factors (trailing 36m) and the
forward 12-month return. Then measure each factor's INFORMATION COEFFICIENT:
the within-category Spearman rank correlation between the factor and the forward
return, averaged across all (date, category) cells. Higher IC = the factor more
reliably picked the funds that went on to outperform their peers.

Weights are then proposed proportional to each factor's positive IC, grouped
into the methodology's layers.

Factors with no history (holdings-conviction, style — data starts 2026) are NOT
in this analysis: they cannot be measured and stay as declared priors.

Monthly frequency throughout (fund factor signals are slow; this keeps the
backtest fast and robust). Run on EC2 (NAV in public.de_mf_nav_daily).

    python scripts/ops/fund_factor_ic.py
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text

load_dotenv(".env")
eng = create_engine(os.environ["ATLAS_DB_URL"])

TRAIL_M = 36  # trailing window for risk metrics (months)
FWD_M = 12  # forward horizon (months)
MIN_TRAIL = 30  # require >=30 of 36 trailing months
RF_M = 0.06 / 12.0  # monthly risk-free (~6% annual)
MIN_COHORT = 8  # min funds in a category-date cell to compute IC

FACTORS = [
    "sharpe",
    "sortino",
    "maxdd_inv",
    "calmar",
    "vol_inv",
    "mom_12m",
    "mom_6m",
    "consistency",
    "ann_ret",
]


def load_monthly_returns() -> tuple[pd.DataFrame, pd.Series]:
    """Return (monthly_returns wide [month x fund], fund->category Series)."""
    funds = pd.read_sql(
        text("""
        SELECT mstar_id, category_name FROM atlas.atlas_universe_funds
        WHERE category_name ILIKE '%Fund%' AND mstar_id IS NOT NULL
    """),
        eng.connect(),
    )
    ids = tuple(funds["mstar_id"].tolist())
    nav = pd.read_sql(
        text(
            "SELECT mstar_id, nav_date, nav FROM public.de_mf_nav_daily "
            "WHERE mstar_id IN :ids AND nav > 0"
        ).bindparams(bindparam("ids", expanding=True)),
        eng.connect(),
        params={"ids": ids},
        parse_dates=["nav_date"],
    )
    nav["m"] = nav["nav_date"].dt.to_period("M")
    me = nav.sort_values(["mstar_id", "nav_date"]).groupby(["mstar_id", "m"])["nav"].last()
    wide = me.reset_index().pivot(index="m", columns="mstar_id", values="nav").sort_index()
    rets = wide.pct_change()
    cat = funds.set_index("mstar_id")["category_name"]
    return rets, cat


def main() -> int:
    rets, cat = load_monthly_returns()
    months = list(rets.index)
    print(f"Loaded {rets.shape[1]} funds x {rets.shape[0]} months " f"({months[0]}..{months[-1]})")

    records: list[pd.DataFrame] = []
    last_m = months[-1]
    for tpos, t in enumerate(months):
        if tpos < MIN_TRAIL or (t + FWD_M) > last_m:
            continue
        win = rets.iloc[tpos - TRAIL_M + 1 : tpos + 1]  # trailing 36m
        fwd = rets.iloc[tpos + 1 : tpos + 1 + FWD_M]  # forward 12m
        valid = (win.notna().sum() >= MIN_TRAIL) & (fwd.notna().sum() >= FWD_M - 1)
        funds = list(win.columns[valid])
        if len(funds) < MIN_COHORT:
            continue
        w = win[funds]
        f = fwd[funds]
        n = w.notna().sum()

        mean = w.mean()
        std = w.std()
        downside = w.where(w < RF_M, 0.0)
        dd_std = np.sqrt((downside**2).sum() / n)
        cum = (1 + w.fillna(0)).cumprod()
        maxdd = ((cum.cummax() - cum) / cum.cummax()).max()
        ann_ret = (1 + w.fillna(0)).prod() ** (12.0 / n) - 1
        # peer-relative consistency: fraction of trailing months above category median
        joined = w.T.join(cat.to_frame("cat"))
        cmed = joined.groupby("cat")[list(w.index)].transform("median").T
        beat = (w > cmed).sum() / n
        fwd_ret = (1 + f.fillna(0)).prod() - 1

        records.append(
            pd.DataFrame(
                {
                    "sharpe": (mean - RF_M) / std * np.sqrt(12),
                    "sortino": (mean - RF_M) / dd_std.replace(0, np.nan) * np.sqrt(12),
                    "maxdd_inv": -maxdd,
                    "calmar": ann_ret / maxdd.replace(0, np.nan),
                    "vol_inv": -std,
                    "mom_12m": (1 + w.tail(12).fillna(0)).prod() - 1,
                    "mom_6m": (1 + w.tail(6).fillna(0)).prod() - 1,
                    "consistency": beat,
                    "ann_ret": ann_ret,
                    "fwd": fwd_ret,
                    "cat": cat.reindex(funds).to_numpy(),
                    "t": str(t),
                }
            )
        )

    allf = pd.concat(records, ignore_index=True)
    print(
        f"\n{len(allf)} fund-month obs across {allf['t'].nunique()} months, "
        f"{allf['cat'].nunique()} categories"
    )

    print("\n=== Information Coefficient (within-category, forward 12m) ===")
    print(f"{'factor':14}{'mean_IC':>9}{'IC_IR':>8}{'hit%>0':>9}{'cells':>7}")
    ic_summary: dict[str, float] = {}
    for fac in FACTORS:
        ics: list[float] = []
        for (_c, _t), g in allf.groupby(["cat", "t"]):
            gg = g[[fac, "fwd"]].dropna()
            if len(gg) < MIN_COHORT or gg[fac].nunique() < 3:
                continue
            ic = gg[fac].corr(gg["fwd"], method="spearman")
            if not np.isnan(ic):
                ics.append(float(ic))
        if not ics:
            continue
        arr = np.array(ics)
        ic_summary[fac] = float(arr.mean())
        ir = arr.mean() / arr.std() if arr.std() > 0 else 0.0
        print(f"{fac:14}{arr.mean():>9.4f}{ir:>8.2f}{(arr > 0).mean() * 100:>8.1f}%{len(arr):>7}")

    print("\n=== Proposed data-driven layer split (positive-IC proportional) ===")
    layers = {
        "risk_adjusted (sharpe,sortino,maxdd,calmar,vol)": [
            "sharpe",
            "sortino",
            "maxdd_inv",
            "calmar",
            "vol_inv",
        ],
        "consistency": ["consistency"],
        "momentum (12m,6m)": ["mom_12m", "mom_6m"],
    }
    layer_ic = {
        name: float(np.mean([max(0.0, ic_summary.get(fa, 0.0)) for fa in fs]))
        for name, fs in layers.items()
    }
    tot = sum(layer_ic.values()) or 1.0
    for name, v in layer_ic.items():
        print(f"  {name:48} avgIC={v:+.4f}  -> {v / tot * 100:5.1f}% of empiricizable budget")
    print("\nDownside check: compare sortino/maxdd_inv IC vs sharpe IC above —")
    print("if downside metrics rank higher, the 1.5x downside tilt is justified.")
    print("holdings-conviction + style + cost: no usable history pre-2026 -> small priors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
