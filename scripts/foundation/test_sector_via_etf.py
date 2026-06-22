#!/usr/bin/env python3
"""Test the FM hypothesis: derive each sector from its SECTOR ETF (the index basket —
exact constituents at index weights) instead of bottom-up sector membership. If the
sector composite is built from the SAME basket whose return is the benchmark, the IC
should be tighter. Pooled rank-IC of the ETF-holdings-weighted composite vs the sector
index forward return, over the sectors with a clean (<=80-holding) tracking ETF.
Read-only.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

import _db

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlas.db import load_thresholds  # noqa: E402
from atlas.lenses.compute.composite import compute_composite  # noqa: E402
from atlas.lenses.compute.thresholds_view import nest_thresholds  # noqa: E402

SUBS = ["technical", "fundamental", "valuation", "catalyst", "flow", "policy"]
HORIZONS = [21, 63, 126]
IDX = "foundation_staging.index_prices"


def _th():
    raw = load_thresholds()
    return nest_thresholds({k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()})


def _sector_etfs() -> pd.DataFrame:
    """sector -> primary_nse_index -> a focused (<=80-holding) tracking ETF + its holdings."""
    return _db.read_df("""
      WITH s AS (SELECT DISTINCT sector_name, primary_nse_index FROM atlas.atlas_sector_master WHERE is_active),
      cand AS (
        SELECT s.sector_name, s.primary_nse_index, em.ticker,
               (SELECT count(*) FROM public.de_etf_holdings h WHERE h.ticker=em.ticker AND h.weight IS NOT NULL) nh
        FROM s JOIN public.de_etf_master em
          ON upper(em.name) LIKE '%'||upper(replace(replace(s.primary_nse_index,'NIFTY ',''),'NIFTY',''))||'%')
      SELECT DISTINCT ON (sector_name) sector_name, primary_nse_index, ticker, nh
      FROM cand WHERE nh BETWEEN 8 AND 80 ORDER BY sector_name, nh DESC""")


def run() -> None:
    th = _th()
    etfs = _sector_etfs()
    print(f"sectors with a clean sector ETF: {len(etfs)}")
    print(etfs.to_string(index=False))
    # holdings (instrument_id, weight) per sector ETF
    hold = _db.read_df("""SELECT ticker, instrument_id, weight FROM public.de_etf_holdings
                          WHERE ticker = ANY(:t) AND weight IS NOT NULL AND instrument_id IS NOT NULL""",
                       {"t": etfs["ticker"].tolist()})
    hold["instrument_id"] = hold["instrument_id"].astype(str)
    t2s = dict(zip(etfs["ticker"], etfs["sector_name"]))
    s2idx = dict(zip(etfs["sector_name"], etfs["primary_nse_index"]))
    hold["sector"] = hold["ticker"].map(t2s)

    # atom sub-scores
    j = _db.read_df(f"SELECT instrument_id, date, {','.join(SUBS)} "
                    "FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'")
    j["instrument_id"] = j["instrument_id"].astype(str)
    j["date"] = pd.to_datetime(j["date"])
    df = j.merge(hold[["instrument_id", "sector", "weight"]], on="instrument_id", how="inner")

    # holdings-weighted sub-scores per (sector, date) -> composite on-read
    rows = []
    for (sec, dt), g in df.groupby(["sector", "date"], sort=False):
        w = g["weight"].to_numpy(float)
        sub = {}
        for s in SUBS:
            v = g[s].to_numpy(float); m = ~np.isnan(v); tw = w[m].sum()
            sub[s] = float((v[m] * w[m]).sum() / tw) if tw > 0 else None
        comp = float(compute_composite(
            technical=sub["technical"], fundamental=sub["fundamental"], valuation_score=sub["valuation"],
            catalyst=sub["catalyst"], flow=sub["flow"], policy=sub["policy"],
            valuation_multiplier=1.0, smart_money_score=0.0, degradation_score=0.0, thresholds=th).final_score)
        rows.append({"sector": sec, "date": dt, "composite": comp})
    sld = pd.DataFrame(rows)

    sess = list(pd.to_datetime(_db.read_df(
        f"SELECT DISTINCT date FROM {IDX} WHERE index_code='NIFTY 50' ORDER BY date")["date"]))
    codes = sorted(set(s2idx.values()))
    px = _db.read_df(f"SELECT index_code, date, close FROM {IDX} WHERE index_code = ANY(:c) AND close>0",
                     {"c": codes})
    px["date"] = pd.to_datetime(px["date"])
    panel = px.pivot_table(index="date", columns="index_code", values="close").reindex(sess)
    print(f"\nETF-based sectors={sld['sector'].nunique()} dates={sld['date'].nunique()}")
    for h in HORIZONS:
        fwd = panel.shift(-h) / panel - 1.0
        ics = []
        for dt, grp in sld.groupby("date"):
            pts = [(r["composite"], fwd.at[dt, s2idx[r["sector"]]])
                   for _, r in grp.iterrows()
                   if s2idx.get(r["sector"]) in fwd.columns and dt in fwd.index
                   and pd.notna(fwd.at[dt, s2idx[r["sector"]]])]
            if len(pts) >= 6:
                c = pd.DataFrame(pts, columns=["comp", "fr"])
                ics.append(c["comp"].corr(c["fr"], method="spearman"))
        ics = [x for x in ics if pd.notna(x)]
        print(f"  h={h:>3}: ETF-based sector-rotation IC = {np.mean(ics):+.4f} (over {len(ics)} dates)")


if __name__ == "__main__":
    run()
