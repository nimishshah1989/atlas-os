#!/usr/bin/env python3
"""Sector IC (per-altitude, D15): does the ON-READ sector composite predict its
NSE-sector-index forward returns? Pooled Spearman rank-IC across (sector, date) at
1m/3m/6m horizons, sector composite computed from sector_lens_daily sub-scores × the
live atlas_thresholds lens weights (same on-read function as the atom). Read-only.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import _db
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlas.db import load_thresholds
from atlas.lenses.compute.composite import compute_composite
from atlas.lenses.compute.thresholds_view import nest_thresholds

SUBS = ["technical", "fundamental", "valuation", "catalyst", "flow", "policy"]
HORIZONS = [21, 63, 126]
SLD = "atlas_foundation.sector_lens_daily"
IDX = "atlas_foundation.index_prices"
SM = "atlas.atlas_sector_master"


def _th():
    raw = load_thresholds()
    flat = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}
    return nest_thresholds(flat)


def _composite(row, th) -> float:
    def f(v):
        return float(v) if v is not None and pd.notna(v) else None

    return float(
        compute_composite(
            technical=f(row["technical"]),
            fundamental=f(row["fundamental"]),
            valuation_score=f(row["valuation"]),
            catalyst=f(row["catalyst"]),
            flow=f(row["flow"]),
            policy=f(row["policy"]),
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=th,
        ).final_score
    )


def _nifty_sessions() -> list:
    d = _db.read_df(f"SELECT DISTINCT date FROM {IDX} WHERE index_code='NIFTY 50' ORDER BY date")
    return list(pd.to_datetime(d["date"]))


def _sector_index_map() -> dict:
    m = _db.read_df(f"SELECT sector_name, primary_nse_index FROM {SM} WHERE is_active")
    return dict(zip(m["sector_name"], m["primary_nse_index"], strict=False))


def run() -> None:
    th = _th()
    sld = _db.read_df(f"SELECT sector, date, {','.join(SUBS)} FROM {SLD}")
    sld["date"] = pd.to_datetime(sld["date"])
    sld["composite"] = [_composite(r, th) for _, r in sld.iterrows()]

    sessions = _nifty_sessions()
    smap = _sector_index_map()
    # forward returns of each sector index on the NIFTY-50 grid
    idx_codes = sorted(set(smap.values()))
    px = _db.read_df(
        f"SELECT index_code, date, close FROM {IDX} WHERE index_code = ANY(:c) AND close>0",
        {"c": idx_codes},
    )
    px["date"] = pd.to_datetime(px["date"])
    panel = px.pivot_table(index="date", columns="index_code", values="close").reindex(sessions)

    print(
        f"sectors={sld['sector'].nunique()} dates={sld['date'].nunique()} "
        f"sector-indices priced={panel.shape[1]}/{len(idx_codes)}"
    )
    sess_pos = {d: i for i, d in enumerate(sessions)}
    for h in HORIZONS:
        fwd = panel.shift(-h) / panel - 1.0  # index forward return over h NSE sessions
        ics = []
        for dt, grp in sld.groupby("date"):
            if dt not in sess_pos:
                continue
            rows = []
            for _, r in grp.iterrows():
                ic_code = smap.get(r["sector"])
                if ic_code in fwd.columns and dt in fwd.index:
                    fr = fwd.at[dt, ic_code]
                    if pd.notna(fr):
                        rows.append((r["composite"], fr))
            if len(rows) >= 8:  # cross-section of >=8 sectors that day
                c = pd.DataFrame(rows, columns=["comp", "fr"])
                ics.append(c["comp"].corr(c["fr"], method="spearman"))
        ics = [x for x in ics if pd.notna(x)]
        mean_ic = float(np.mean(ics)) if ics else float("nan")
        print(
            f"  h={h:>3} sessions: cross-sectional sector-rotation IC = {mean_ic:+.4f} "
            f"(over {len(ics)} dates)"
        )


if __name__ == "__main__":
    run()
