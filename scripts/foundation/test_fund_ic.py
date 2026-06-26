#!/usr/bin/env python3
"""Fund IC test (the roll-up thesis): does a fund's holdings-weighted ATOM composite
predict its forward NAV return? Cross-sectional rank-IC across equity funds at each
monthly holdings snapshot, composite computed on-read from the atom (look-through via
de_mf_holdings.instrument_id). If positive, the atom's stock-selection edge rolls up to
funds (unlike sector rotation). Read-only.
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
L = "atlas.atlas_lens_scores_daily"
NAV = "public.de_mf_nav_daily"


def _th():
    raw = load_thresholds()
    return nest_thresholds({k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()})


def _stock_composite(dt) -> dict:
    """{instrument_id(str): on-read composite} for the journal session on/before dt."""
    th = _th()
    sess = _db.scalar(
        f"SELECT max(date) FROM {L} WHERE asset_class='stock' AND date<=:d", {"d": dt}
    )
    df = _db.read_df(
        f"SELECT instrument_id, {','.join(SUBS)} FROM {L} WHERE asset_class='stock' AND date=:d",
        {"d": sess},
    )

    def f(v):
        return float(v) if v is not None and pd.notna(v) else None

    out = {}
    for _, r in df.iterrows():
        out[str(r["instrument_id"])] = float(
            compute_composite(
                technical=f(r["technical"]),
                fundamental=f(r["fundamental"]),
                valuation_score=f(r["valuation"]),
                catalyst=f(r["catalyst"]),
                flow=f(r["flow"]),
                policy=f(r["policy"]),
                valuation_multiplier=1.0,
                smart_money_score=0.0,
                degradation_score=0.0,
                thresholds=th,
            ).final_score
        )
    return sess, out


def _fwd_nav(mids, d0, h_days) -> dict:
    """Forward NAV return per fund from d0 over ~h_days calendar days."""
    d1 = pd.Timestamp(d0) + pd.Timedelta(days=h_days)
    nav = _db.read_df(
        f"""
      WITH a AS (SELECT DISTINCT ON (mstar_id) mstar_id, nav FROM {NAV}
                 WHERE nav_date<=:d0 AND nav>0 AND mstar_id=ANY(:m) ORDER BY mstar_id, nav_date DESC),
           b AS (SELECT DISTINCT ON (mstar_id) mstar_id, nav FROM {NAV}
                 WHERE nav_date<=:d1 AND nav>0 AND mstar_id=ANY(:m) ORDER BY mstar_id, nav_date DESC)
      SELECT a.mstar_id, b.nav/a.nav - 1 AS ret FROM a JOIN b USING (mstar_id)""",
        {"d0": str(d0), "d1": str(d1.date()), "m": list(mids)},
    )
    return dict(zip(nav["mstar_id"], nav["ret"], strict=False))


def run() -> None:
    snaps = [
        d.date() if hasattr(d, "date") else d
        for d in _db.read_df(
            "SELECT DISTINCT as_of_date FROM public.de_mf_holdings ORDER BY as_of_date"
        )["as_of_date"]
    ]
    eq = set(
        _db.read_df(
            "SELECT mstar_id FROM public.de_mf_master WHERE broad_category='Equity' AND is_active"
        )["mstar_id"]
    )
    print(f"snapshots={snaps}; equity funds={len(eq)}")
    for hd in (30, 60, 90):
        ics = []
        for snap in snaps:
            _sess, scomp = _stock_composite(snap)
            h = _db.read_df(
                """SELECT mstar_id, instrument_id, weight_pct FROM public.de_mf_holdings
                               WHERE as_of_date=:d AND instrument_id IS NOT NULL AND weight_pct>0""",
                {"d": snap},
            )
            h = h[h["mstar_id"].isin(eq)].copy()
            h["comp"] = h["instrument_id"].astype(str).map(scomp)
            h = h.dropna(subset=["comp"])
            h["_wc"] = h["comp"] * h["weight_pct"]
            agg = h.groupby("mstar_id").agg(_wc=("_wc", "sum"), _w=("weight_pct", "sum"))
            fc = (agg["_wc"] / agg["_w"]).rename("fund_comp")
            fwd = _fwd_nav(fc.index.tolist(), snap, hd)
            m = pd.DataFrame({"fund_comp": fc}).join(pd.Series(fwd, name="ret")).dropna()
            if len(m) >= 50:
                ics.append(m["fund_comp"].corr(m["ret"], method="spearman"))
        ics = [x for x in ics if pd.notna(x)]
        mean = float(np.mean(ics)) if ics else float("nan")
        print(
            f"  ~{hd}d fwd NAV: fund IC = {mean:+.4f} (over {len(ics)} snapshots, "
            f"per-snap n>=50 funds)"
        )


if __name__ == "__main__":
    run()
