#!/usr/bin/env python3
"""FUND leaderboard (read-only): evaluate equity funds by LEADERSHIP-BREADTH — the
weighted share of each fund's holdings that are multi-factor leaders (top-decile in >=2
conviction lenses, cut within cap cohort). Look-through via de_mf_holdings.instrument_id
to the atom; deciles from the shared decile_core (single source). Ranks funds and rolls
up by AMFI category. Honest scope note: breadth is a current-snapshot DESCRIPTION (which
funds hold the names our lenses rate highest), not a NAV forecast — fund predictive IC is
weak/uncertain on the available 6 holdings snapshots (D27). No writes.
"""
from __future__ import annotations

import pandas as pd

import _db
import decile_core as dc

MIN_HOLD = 20   # need >=20 mapped holdings for a meaningful breadth


def run() -> None:
    date = dc.latest_date()
    j = dc.deciles(date)
    leadmap = dict(zip(j["instrument_id"], j["lead2"].astype(float)))
    strmap = dict(zip(j["instrument_id"], j["strength"]))
    snap = _db.scalar("SELECT max(as_of_date) FROM foundation_staging.de_mf_holdings")

    h = _db.read_df(
        """SELECT m.fund_name, m.category_name, m.amc_name, h.instrument_id, h.weight_pct
           FROM foundation_staging.de_mf_holdings h JOIN foundation_staging.de_mf_master m USING (mstar_id)
           WHERE h.as_of_date=:d AND h.instrument_id IS NOT NULL AND h.weight_pct>0
             AND m.broad_category='Equity' AND m.is_active AND m.is_etf IS NOT TRUE""",
        {"d": snap})
    h["instrument_id"] = h["instrument_id"].astype(str)
    h["ld"] = h["instrument_id"].map(leadmap).fillna(0.0)
    h["st"] = h["instrument_id"].map(strmap)
    h["_wl"] = h["ld"] * h["weight_pct"]
    h["_ws"] = h["st"].fillna(0) * h["weight_pct"]

    g = h.groupby(["fund_name", "category_name", "amc_name"])
    f = g.agg(n=("instrument_id", "size"), _wl=("_wl", "sum"), _ws=("_ws", "sum"),
              _w=("weight_pct", "sum")).reset_index()
    f = f[f["n"] >= MIN_HOLD].copy()
    f["breadth_%"] = (100 * f["_wl"] / f["_w"]).round(1)
    f["strength"] = (f["_ws"] / f["_w"]).round(2)
    f = f.sort_values("breadth_%", ascending=False)

    print(f"=== FUND leadership-breadth leaderboard — holdings {snap}, deciles {date} ===")
    print(f"equity funds with >={MIN_HOLD} mapped holdings: {len(f)}")
    hdr = f"{'fund':40s} {'category':16s} {'n':>4s} {'brdth%':>6s} {'str':>4s}"
    print("\n-- TOP 20 by leadership-breadth --"); print(hdr); print("-" * len(hdr))
    for _, r in f.head(20).iterrows():
        print(f"{str(r['fund_name'])[:40]:40s} {str(r['category_name'])[:16]:16s} "
              f"{int(r['n']):>4d} {r['breadth_%']:>6.1f} {r['strength']:>4.1f}")
    print("\n-- BOTTOM 8 by leadership-breadth --"); print(hdr); print("-" * len(hdr))
    for _, r in f.tail(8).iterrows():
        print(f"{str(r['fund_name'])[:40]:40s} {str(r['category_name'])[:16]:16s} "
              f"{int(r['n']):>4d} {r['breadth_%']:>6.1f} {r['strength']:>4.1f}")

    cat = f.groupby("category_name").agg(funds=("fund_name", "size"),
                                         breadth=("breadth_%", "mean"),
                                         strength=("strength", "mean")).reset_index()
    cat = cat[cat["funds"] >= 3].sort_values("breadth", ascending=False)
    print("\n=== by AMFI category (avg across funds, >=3 funds) ===")
    print(f"{'category':22s} {'funds':>5s} {'breadth%':>8s} {'str':>4s}")
    for _, r in cat.iterrows():
        print(f"{str(r['category_name'])[:22]:22s} {int(r['funds']):>5d} {r['breadth']:>8.1f} {r['strength']:>4.1f}")


if __name__ == "__main__":
    run()
