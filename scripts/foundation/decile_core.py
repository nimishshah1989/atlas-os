#!/usr/bin/env python3
"""Shared decile/leadership computation (D27 methodology) — single source used by the
instrument view and every roll-up. Read-only, on-read (nothing materialised here).

Deciles are cut WITHIN market-cap cohort (large/mid/small/micro); the cohort is the
official Indian cap class via index-ETF free-float-weight rank inside Nifty Total Market
(ETF weight = free-float cap). Decile is computed over NON-NULL values only — null = 'no
signal' (NaN), never fabricated into a rank. Leadership badge counts how many of the 4
conviction lenses (technical/fundamental/catalyst/flow) are top-decile; valuation is its
own decile and never feeds the badge. Strength = mean conviction decile (1-10).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import _db

L = "foundation_staging.atlas_lens_scores_daily"   # canonical journal (D22 consolidated)
CONV = ["technical", "fundamental", "catalyst", "flow"]   # feed leadership badge
LENSES = CONV + ["valuation"]                              # valuation = own decile
BROAD = "F00001PXO0"                                      # Nifty Total Market ETF (750)
BROAD2 = "F00001GZXV"                                     # Nifty 500 fallback
MIN_COHORT = 20                                           # need >=20 non-null to rank


def cap_bucket() -> pd.DataFrame:
    """instrument_id -> cap cohort via free-float-weight rank inside the broad index."""
    w = _db.read_df(
        """WITH r AS (
             SELECT instrument_id, weight,
                    row_number() OVER (PARTITION BY instrument_id ORDER BY
                      CASE ticker WHEN :b1 THEN 1 WHEN :b2 THEN 2 ELSE 3 END, weight DESC) rn
             FROM foundation_staging.de_etf_holdings WHERE ticker IN (:b1, :b2) AND weight > 0)
           SELECT instrument_id, weight FROM r WHERE rn = 1""",
        {"b1": BROAD, "b2": BROAD2})
    w["instrument_id"] = w["instrument_id"].astype(str)
    w = w.sort_values("weight", ascending=False).reset_index(drop=True)
    w["rank"] = np.arange(1, len(w) + 1)
    w["cap"] = np.select(
        [w["rank"] <= 100, w["rank"] <= 250, w["rank"] <= 500],
        ["large", "mid", "small"], default="micro")
    return w[["instrument_id", "cap"]]


def latest_date():
    return _db.scalar(f"SELECT max(date) FROM {L} WHERE asset_class='stock'")


def add_deciles(j: pd.DataFrame, caps: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add per-(cap, lens) deciles + leadership badge/strength to a frame that already
    has instrument_id + the LENSES score columns. Cohort cut WITHIN cap; null = no signal.
    Adds: cap, d_<lens> (1-10, NaN=no signal), lead (top-decile count over CONV), lead_t2
    (top-2-decile count), lead2 (>=2 flag), strength (avg conviction decile)."""
    j = j.copy()
    j["instrument_id"] = j["instrument_id"].astype(str)
    if "cap" not in j.columns:
        caps = cap_bucket() if caps is None else caps
        j = j.merge(caps, on="instrument_id", how="left")
    j["cap"] = j["cap"].fillna("micro")
    for lens in LENSES:
        j[f"d_{lens}"] = np.nan
        for _cap, idx in j.groupby("cap").groups.items():
            s = j.loc[idx, lens]
            ok = s.notna()
            if ok.sum() >= MIN_COHORT:
                dec = pd.qcut(s[ok].rank(method="first"), 10, labels=False) + 1
                j.loc[s[ok].index, f"d_{lens}"] = dec.values
    j["lead"] = sum((j[f"d_{c}"] == 10).astype(int) for c in CONV)
    j["lead_t2"] = sum((j[f"d_{c}"] >= 9).astype(int) for c in CONV)
    j["lead2"] = (j["lead"] >= 2).astype(int)
    j["strength"] = j[[f"d_{c}" for c in CONV]].mean(axis=1)
    return j


def deciles(date, caps: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-(cap, lens) decile + leadership/strength for one journal date (one row/stock,
    incl. symbol/name/sector + raw lens scores)."""
    j = _db.read_df(
        f"SELECT instrument_id, symbol, name, sector, {','.join(LENSES)} "
        f"FROM {L} t JOIN foundation_staging.instrument_master im USING (instrument_id) "
        f"WHERE t.asset_class='stock' AND t.date=:d", {"d": str(date)})
    return add_deciles(j, caps)
