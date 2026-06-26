#!/usr/bin/env python3
"""REAL decile/leadership sample (D27, read-only) — instrument decile cards + fund
leadership-breadth, using the shared decile_core computation (single source of truth, so
this can never diverge from the roll-up views). Deciles cut WITHIN cap cohort; null = no
signal (—); leadership badge over the 4 conviction lenses; valuation = own decile.
Co-primary headline (FM): strength (avg conviction decile) AND leadership badge, both shown.
No writes.
"""

from __future__ import annotations

import _db
import decile_core as dc
import pandas as pd


def _fmt(v) -> str:
    return "—" if pd.isna(v) else f"D{int(v)}"


def run() -> None:
    date = dc.latest_date()
    j = dc.deciles(date)
    print(f"=== instrument decile/leadership cards — {date} (deciles cut WITHIN cap cohort) ===")
    print("cohort sizes: " + ", ".join(f"{c}={int(n)}" for c, n in j["cap"].value_counts().items()))
    show = [
        "RELIANCE",
        "HDFCBANK",
        "TCS",
        "INFY",
        "ICICIBANK",
        "SBIN",
        "BHARTIARTL",
        "TATASTEEL",
        "DIXON",
        "PERSISTENT",
        "KPITTECH",
        "CDSL",
        "POLYCAB",
    ]
    hdr = (
        f"{'symbol':12s} {'cap':6s} {'sector':16s} "
        + " ".join(f"{c[:4]:>4s}" for c in dc.CONV)
        + f" {'val':>4s} | {'D10':>3s} {'D9+':>3s} {'str':>4s}"
    )
    print(hdr)
    print("-" * len(hdr))
    sub = j[j["symbol"].isin(show)].set_index("symbol").reindex(show).dropna(how="all")
    sub = sub.sort_values("strength", ascending=False)
    for sym, r in sub.iterrows():
        cells = " ".join(f"{_fmt(r[f'd_{c}']):>4s}" for c in dc.CONV)
        strv = "—" if pd.isna(r["strength"]) else f"{r['strength']:.1f}"
        print(
            f"{sym:12s} {r['cap']:6s} {str(r['sector'])[:16]:16s} {cells} {_fmt(r['d_valuation']):>4s} | "
            f"{int(r['lead']):>3d} {int(r['lead_t2']):>3d} {strv:>4s}"
        )
    print(
        "  legend: D10 = #conviction lenses in TOP decile; D9+ = # in top-2 deciles; "
        "str = avg conviction decile (co-primary headline w/ the badge)"
    )

    print("\n=== multi-factor leaders by cohort (lead>=2 of 4 conviction lenses) ===")
    lc = j.groupby("cap").agg(
        n=("instrument_id", "size"),
        lead2=("lead2", "sum"),
        lead3=("lead", lambda s: int((s >= 3).sum())),
    )
    print(lc.to_string())

    # fund leadership-breadth on the latest holdings snapshot (real funds)
    snap = _db.scalar("SELECT max(as_of_date) FROM foundation_staging.de_mf_holdings")
    leadmap = dict(zip(j["instrument_id"], j["lead2"].astype(float), strict=False))
    funds = _db.read_df(
        """SELECT m.fund_name, h.instrument_id, h.weight_pct
           FROM foundation_staging.de_mf_holdings h JOIN foundation_staging.de_mf_master m USING (mstar_id)
           WHERE h.as_of_date=:d AND h.instrument_id IS NOT NULL AND h.weight_pct>0
             AND m.broad_category='Equity' AND m.is_active
             AND (m.fund_name ILIKE '%%parag parikh flexi%%' OR m.fund_name ILIKE '%%nippon%%large cap%%'
                  OR m.fund_name ILIKE '%%hdfc mid%%' OR m.fund_name ILIKE '%%quant small%%')""",
        {"d": snap},
    )
    if len(funds):
        funds["instrument_id"] = funds["instrument_id"].astype(str)
        funds["_wl"] = funds["instrument_id"].map(leadmap).fillna(0) * funds["weight_pct"]
        ag = funds.groupby("fund_name").agg(
            _wl=("_wl", "sum"), _w=("weight_pct", "sum"), n=("instrument_id", "size")
        )
        ag["breadth_%"] = (100 * ag["_wl"] / ag["_w"]).round(1)
        print(
            f"\n=== fund LEADERSHIP-BREADTH (snapshot {snap}) — wt%% of holdings that are >=2-lens leaders ==="
        )
        print(ag[["n", "breadth_%"]].sort_values("breadth_%", ascending=False).to_string())


if __name__ == "__main__":
    run()
