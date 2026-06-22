#!/usr/bin/env python3
"""REAL decile/leadership sample (D27 methodology, read-only). Per-lens deciles are cut
WITHIN market-cap cohort (large/mid/small/micro) — the cohort is the official Indian cap
class taken from index-ETF membership (Nifty 100 / Midcap 150 / Smallcap 250), realised
here as the free-float-weight rank inside the broad Nifty Total Market index (ETF weight =
free-float cap). Decile is computed over NON-NULL values only; null = 'no signal' (—),
never fabricated into a rank. Leadership badge = how many of the 4 conviction lenses
(technical/fundamental/catalyst/flow) are top-decile (D10). Valuation is its own decile,
not part of the badge. Prints decile cards for recognisable names across caps + the
leadership-breadth of a few real equity funds. No writes.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import _db

L = "atlas.atlas_lens_scores_daily"
CONV = ["technical", "fundamental", "catalyst", "flow"]          # feed the leadership badge
LENSES = CONV + ["valuation"]                                    # valuation = own decile
BROAD = "F00001PXO0"                                             # Nifty Total Market ETF (750)
BROAD2 = "F00001GZXV"                                            # Nifty 500 fallback


def _cap_bucket() -> pd.DataFrame:
    """instrument_id -> cap cohort via free-float-weight rank inside the broad index."""
    w = _db.read_df(
        """WITH r AS (
             SELECT instrument_id, ticker, weight,
                    row_number() OVER (PARTITION BY instrument_id ORDER BY
                      CASE ticker WHEN :b1 THEN 1 WHEN :b2 THEN 2 ELSE 3 END, weight DESC) rn
             FROM public.de_etf_holdings WHERE ticker IN (:b1, :b2) AND weight > 0)
           SELECT instrument_id, weight FROM r WHERE rn = 1""",
        {"b1": BROAD, "b2": BROAD2})
    w["instrument_id"] = w["instrument_id"].astype(str)
    w = w.sort_values("weight", ascending=False).reset_index(drop=True)
    w["rank"] = np.arange(1, len(w) + 1)
    w["cap"] = np.select(
        [w["rank"] <= 100, w["rank"] <= 250, w["rank"] <= 500],
        ["large", "mid", "small"], default="micro")
    return w[["instrument_id", "cap"]]


def _deciles(date) -> pd.DataFrame:
    """Per-(cap, lens) decile over non-null values; + leadership_count over CONV lenses."""
    j = _db.read_df(
        f"SELECT instrument_id, symbol, name, sector, {','.join(LENSES)} "
        f"FROM {L} t JOIN foundation_staging.instrument_master im USING (instrument_id) "
        f"WHERE t.asset_class='stock' AND t.date=:d", {"d": str(date)})
    j["instrument_id"] = j["instrument_id"].astype(str)
    j = j.merge(_cap_bucket(), on="instrument_id", how="left")
    j["cap"] = j["cap"].fillna("micro")
    for lens in LENSES:
        j[f"d_{lens}"] = np.nan
        for cap, idx in j.groupby("cap").groups.items():
            s = j.loc[idx, lens]
            ok = s.notna()
            if ok.sum() >= 20:                                   # need a cohort to rank
                dec = pd.qcut(s[ok].rank(method="first"), 10, labels=False) + 1
                j.loc[s[ok].index, f"d_{lens}"] = dec.values
    j["lead"] = sum((j[f"d_{c}"] == 10).astype(int) for c in CONV)        # strict: top decile
    j["lead_t2"] = sum((j[f"d_{c}"] >= 9).astype(int) for c in CONV)       # soft: top 2 deciles
    j["strength"] = j[[f"d_{c}" for c in CONV]].mean(axis=1)               # avg conviction decile
    return j


def _fmt(v) -> str:
    return "—" if pd.isna(v) else f"D{int(v)}"


def run() -> None:
    date = _db.scalar(f"SELECT max(date) FROM {L} WHERE asset_class='stock'")
    j = _deciles(date)
    print(f"=== instrument decile/leadership cards — {date} (deciles cut WITHIN cap cohort) ===")
    print(f"cohort sizes: " + ", ".join(f"{c}={int(n)}" for c, n in j["cap"].value_counts().items()))
    show = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL",
            "TATAMOTORS", "TATASTEEL", "DIXON", "PERSISTENT", "KPITTECH", "CDSL", "POLYCAB"]
    hdr = (f"{'symbol':12s} {'cap':6s} {'sector':16s} " + " ".join(f"{c[:4]:>4s}" for c in CONV)
           + f" {'val':>4s} | {'D10':>3s} {'D9+':>3s} {'str':>4s}")
    print(hdr); print("-" * len(hdr))
    sub = j[j["symbol"].isin(show)].set_index("symbol").reindex(show).dropna(how="all")
    sub = sub.sort_values("strength", ascending=False)
    for sym, r in sub.iterrows():
        cells = " ".join(f"{_fmt(r[f'd_{c}']):>4s}" for c in CONV)
        strv = "—" if pd.isna(r["strength"]) else f"{r['strength']:.1f}"
        print(f"{sym:12s} {r['cap']:6s} {str(r['sector'])[:16]:16s} {cells} {_fmt(r['d_valuation']):>4s} | "
              f"{int(r['lead']):>3d} {int(r['lead_t2']):>3d} {strv:>4s}")
    print("  legend: D10 = #conviction lenses in TOP decile (strict badge); D9+ = # in top-2 deciles "
          "(soft badge); str = avg conviction decile (1-10, sort key)")

    # leadership counts by cap (how many genuine multi-factor leaders exist per cohort)
    print(f"\n=== multi-factor leaders by cohort (lead>=2 of 4 conviction lenses) ===")
    lc = j.groupby("cap").agg(n=("instrument_id", "size"),
                              lead2=("lead", lambda s: int((s >= 2).sum())),
                              lead3=("lead", lambda s: int((s >= 3).sum())))
    print(lc.to_string())

    # fund leadership-breadth on the latest holdings snapshot
    snap = _db.scalar("SELECT max(as_of_date) FROM public.de_mf_holdings")
    j["lead2"] = (j["lead"] >= 2).astype(float)
    leadmap = dict(zip(j["instrument_id"], j["lead2"]))
    funds = _db.read_df(
        """SELECT m.fund_name, h.mstar_id, h.instrument_id, h.weight_pct
           FROM public.de_mf_holdings h JOIN public.de_mf_master m USING (mstar_id)
           WHERE h.as_of_date=:d AND h.instrument_id IS NOT NULL AND h.weight_pct>0
             AND m.broad_category='Equity' AND m.is_active
             AND (m.fund_name ILIKE '%%parag parikh flexi%%' OR m.fund_name ILIKE '%%nippon%%large cap%%'
                  OR m.fund_name ILIKE '%%hdfc mid%%' OR m.fund_name ILIKE '%%quant small%%')""",
        {"d": snap})
    if len(funds):
        funds["instrument_id"] = funds["instrument_id"].astype(str)
        funds["ld"] = funds["instrument_id"].map(leadmap)
        funds["_wl"] = funds["ld"].fillna(0) * funds["weight_pct"]
        ag = funds.groupby("fund_name").agg(_wl=("_wl", "sum"), _w=("weight_pct", "sum"),
                                            n=("instrument_id", "size"))
        ag["breadth_%"] = (100 * ag["_wl"] / ag["_w"]).round(1)
        print(f"\n=== fund LEADERSHIP-BREADTH (snapshot {snap}) — wt%% of holdings that are >=2-lens leaders ===")
        print(ag[["n", "breadth_%"]].sort_values("breadth_%", ascending=False).to_string())


if __name__ == "__main__":
    run()
