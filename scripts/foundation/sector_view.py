#!/usr/bin/env python3
"""SECTOR leaderboard (read-only): the roll-up the FM described — evaluate each sector by
its LEADERSHIP (how many constituents are doing amazingly), shown ALONGSIDE observed
RELATIVE STRENGTH vs the Nifty 50 over multiple windows. Two clearly-separated columns so
we never dress observed RS up as a prediction:

  - leadership-breadth %  = our view: share of the sector's constituents that are
    multi-factor leaders (top-decile in >=2 conviction lenses, cut within cap cohort).
  - RS 1m/3m/6m/1y        = observed: sector index trailing return minus Nifty 50's, from
    real index_prices. Factual context, no forecast claim.
No writes.
"""

from __future__ import annotations

import _db
import decile_core as dc
import pandas as pd

IDX = "foundation_staging.index_prices"
SM = "foundation_staging.atlas_sector_master"
BENCH = "NIFTY 50"
WINDOWS = [("1m", 21), ("3m", 63), ("6m", 126), ("1y", 252)]


def _trailing(series: pd.Series, w: int):
    """Trailing return over w trading sessions from the latest close, or None."""
    s = series.dropna()
    if len(s) <= w or s.iloc[-1 - w] <= 0:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - w] - 1)


def _rs_table() -> dict:
    """sector_name -> {window: RS vs benchmark} from real index_prices."""
    idxmap = dict(
        _db.read_df(
            f"SELECT sector_name, primary_nse_index FROM {SM} "
            f"WHERE is_active AND primary_nse_index IS NOT NULL"
        ).values
    )
    codes = tuple(sorted(set([*list(idxmap.values()), BENCH])))
    px = _db.read_df(
        f"SELECT index_code, date, close FROM {IDX} "
        f"WHERE index_code IN :c AND close>0 ORDER BY date",
        {"c": codes},
    )
    px["date"] = pd.to_datetime(px["date"])
    ser = {code: g.set_index("date")["close"] for code, g in px.groupby("index_code")}
    bench = ser.get(BENCH)
    bret = {lbl: _trailing(bench, w) for lbl, w in WINDOWS} if bench is not None else {}
    out = {}
    for sec, code in idxmap.items():
        if code not in ser:
            continue
        out[sec] = {
            lbl: (
                None
                if (_trailing(ser[code], w) is None or bret.get(lbl) is None)
                else _trailing(ser[code], w) - bret[lbl]
            )
            for lbl, w in WINDOWS
        }
    return out


def run() -> None:
    date = dc.latest_date()
    j = dc.deciles(date)
    g = j.dropna(subset=["sector"]).groupby("sector")
    sec = g.agg(
        n=("instrument_id", "size"), leaders=("lead2", "sum"), strength=("strength", "mean")
    ).reset_index()
    sec["breadth_%"] = (100 * sec["leaders"] / sec["n"]).round(1)
    sec["strength"] = sec["strength"].round(2)
    rs = _rs_table()

    def rcell(s, lbl):
        v = rs.get(s, {}).get(lbl)
        return "  —  " if v is None else f"{100 * v:+5.1f}"

    sec = sec[sec["n"] >= 5].sort_values("breadth_%", ascending=False)
    print(f"=== SECTOR leaderboard — {date} (our leadership-breadth | observed RS vs {BENCH}) ===")
    hdr = f"{'sector':18s} {'n':>4s} {'lead':>4s} {'brdth%':>6s} {'str':>4s} | " + " ".join(
        f"{lbl:>6s}" for lbl, _ in WINDOWS
    )
    print(hdr)
    print("-" * len(hdr))
    for _, r in sec.iterrows():
        rscells = " ".join(f"{rcell(r['sector'], lbl):>6s}" for lbl, _ in WINDOWS)
        print(
            f"{str(r['sector'])[:18]:18s} {int(r['n']):>4d} {int(r['leaders']):>4d} "
            f"{r['breadth_%']:>6.1f} {r['strength']:>4.1f} | {rscells}"
        )
    print(
        "  breadth% = share of constituents top-decile in >=2 conviction lenses (within cap cohort, OUR view)"
    )
    print(
        f"  1m/3m/6m/1y = sector index trailing return minus {BENCH}'s, in % (OBSERVED, not a forecast)"
    )


if __name__ == "__main__":
    run()
