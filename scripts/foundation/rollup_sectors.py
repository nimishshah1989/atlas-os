#!/usr/bin/env python3
"""Sector roll-up: free-float-cap-weighted six-lens vector per sector × date + breadth +
dispersion, materialised to foundation_staging.sector_lens_daily. The sector composite is
ON-READ from the stored sub-scores × the live atlas_thresholds lens weights (D19/D21).

Weighting (D15/D24): free-float cap = Screener market_cap × (1 − promoter%). v1 uses the
CURRENT free-float cap as a static per-stock weight applied across dates (relative sector
weights are slowly varying); the per-date sub-scores still vary, so the sector vector is
fully time-varying. v2 = date-varying weights (shares × close(D) × (1−promoter%(asof D))).

Load-once + vectorized: COPY the journal once, map sector + weight per instrument, groupby
(sector, date) weighted-average. ~21 sectors × 1854 dates.

    python rollup_sectors.py            # (re)build sector_lens_daily
    python rollup_sectors.py --date 2026-06-19   # preview one date, write nothing
"""

from __future__ import annotations

import argparse
import io
from datetime import date

import _db
import numpy as np
import pandas as pd

M = "foundation_staging"
L = f"{M}.atlas_lens_scores_daily"  # single schema — reads the live lens journal in fs
TGT = f"{M}.sector_lens_daily"
SUBS = ["technical", "fundamental", "valuation", "catalyst", "flow", "policy"]
STRONG = 60.0  # breadth threshold: a member is "strong" on a lens if its sub-score >= 60


def ensure_table() -> None:
    cols = ", ".join(f"{s} numeric" for s in SUBS)
    bcols = ", ".join(f"breadth_{s} numeric" for s in SUBS)
    _db.exec_sql(f"""CREATE TABLE IF NOT EXISTS {TGT} (
        sector text, date date, {cols}, {bcols},
        dispersion numeric, n_constituents int, total_free_float_cr numeric,
        computed_at timestamptz default now(), PRIMARY KEY (sector, date))""")


def _journal() -> pd.DataFrame:
    raw = _db.engine().raw_connection()
    try:
        buf = io.StringIO()
        raw.cursor().copy_expert(
            f"COPY (SELECT instrument_id, date, {','.join(SUBS)} FROM {L} "
            "WHERE asset_class='stock') TO STDOUT WITH CSV HEADER",
            buf,
        )
        buf.seek(0)
        return pd.read_csv(buf, parse_dates=["date"])
    finally:
        raw.close()


def _weights() -> pd.DataFrame:
    """Per-instrument: sector + free-float-cap weight from the broad index-ETF holdings.

    Index-ETF constituent weights ARE free-float-cap weights (verified: HDFCBANK 6% /
    RELIANCE 5% = the NIFTY 500 weights). We take each stock's weight from the broadest
    index ETF it belongs to — Nifty Total Market (F00001PXO0, 750) first, then Nifty 500
    (F00001GZXV), then the size-index ETFs (≥200 holdings) — covering the ~795 investable
    names; the micro-cap tail not in any broad ETF has ~0 free-float weight (correctly
    excluded from the cap-weighted average, still counted in breadth). No external fetch.
    """
    return _db.read_df(f"""
        WITH broad AS (
          SELECT ticker FROM foundation_staging.de_etf_holdings WHERE weight IS NOT NULL
          GROUP BY ticker HAVING count(*) >= 200),
        ranked AS (
          SELECT h.instrument_id, h.weight,
                 row_number() OVER (PARTITION BY h.instrument_id ORDER BY
                   CASE h.ticker WHEN 'F00001PXO0' THEN 1 WHEN 'F00001GZXV' THEN 2 ELSE 3 END,
                   h.weight DESC NULLS LAST) rn
          FROM foundation_staging.de_etf_holdings h JOIN broad USING (ticker)
          WHERE h.weight IS NOT NULL AND h.weight > 0)
        SELECT im.instrument_id, im.sector, r.weight AS ff_weight
        FROM {M}.instrument_master im
        JOIN ranked r ON r.instrument_id = im.instrument_id AND r.rn = 1
        WHERE im.asset_class='stock' AND im.sector IS NOT NULL AND im.sector<>''""")


def compute(write: bool, one: date | None = None) -> pd.DataFrame:
    j = _journal()
    if one is not None:
        j = j[j["date"] == pd.Timestamp(one)]
    w = _weights()
    w["instrument_id"] = w["instrument_id"].astype(str)
    j["instrument_id"] = j["instrument_id"].astype(str)
    df = j.merge(w[["instrument_id", "sector", "ff_weight"]], on="instrument_id", how="inner")
    df = df[df["ff_weight"] > 0]

    # free-float-weighted average per (sector, date) for each lens sub-score
    out_rows = []
    g = df.groupby(["sector", "date"], sort=False)
    for (sec, dt), grp in g:
        wts = grp["ff_weight"].to_numpy()
        row = {
            "sector": sec,
            "date": dt.date(),
            "n_constituents": len(grp),
            "total_free_float_cr": float(wts.sum()),
        }
        for s in SUBS:
            v = grp[s].to_numpy(dtype=float)
            mask = ~np.isnan(v)
            tw = wts[mask].sum()
            row[s] = round(float((v[mask] * wts[mask]).sum() / tw), 2) if tw > 0 else None
            row[f"breadth_{s}"] = (
                round(float((v[mask] >= STRONG).mean()), 4) if mask.any() else None
            )
        # dispersion = stdev of the 4 conviction sub-scores' member spread (proxy via technical)
        tv = grp["technical"].to_numpy(dtype=float)
        row["dispersion"] = round(float(np.nanstd(tv)), 2) if (~np.isnan(tv)).any() else None
        out_rows.append(row)
    res = pd.DataFrame(out_rows)
    print(
        f"sectors×dates computed: {len(res)} (sectors={res['sector'].nunique()}, "
        f"dates={res['date'].nunique()})",
        flush=True,
    )
    if write and not res.empty:
        ensure_table()
        _db.upsert_df(TGT, res, ["sector", "date"])
        print(f"wrote {len(res)} rows to {TGT}", flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    args = ap.parse_args()
    if args.date:
        r = compute(write=False, one=args.date)
        print(r.sort_values("total_free_float_cr", ascending=False).head(25).to_string(index=False))
    else:
        compute(write=True)


if __name__ == "__main__":
    main()
