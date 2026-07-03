#!/usr/bin/env python3
"""EMA ladder (10/21/50/200) over NAV for every Atlas-universe fund
→ atlas_foundation.technical_fund_daily (resumable, incremental by date).

Funds are keyed by mstar_id (no instrument_id), so they get their own slim
technicals table; the EMA math is the same canonical technicals module used
for stocks/ETFs.

    python compute_fund_technicals.py            # incremental: only funds with new NAV dates
    python compute_fund_technicals.py --limit 5  # smoke test
    python compute_fund_technicals.py --redo     # full recompute + rewrite of ALL history
"""

from __future__ import annotations

import argparse
import uuid

import _db
import pandas as pd
import technicals as T

M = "atlas_foundation"
_EMA_COLS = [f"ema_{p}" for p in T.EMA_PERIODS]


def targets(incremental: bool, limit: int | None, cutoff) -> list[str]:
    """Universe funds to (re)compute; incremental keeps only those with NAV dates
    beyond what technical_fund_daily already holds."""
    df = _db.read_df(f"select mstar_id from {M}.atlas_universe_funds order by mstar_id")
    ids = df["mstar_id"].tolist()
    if incremental:
        floor = _db.read_df(
            f"select mstar_id, max(date) d from {M}.technical_fund_daily group by 1"
        )
        fl = dict(zip(floor["mstar_id"], floor["d"], strict=False))
        src = _db.read_df(
            f"select mstar_id, max(nav_date) d from {M}.de_mf_nav_daily "
            f"where nav_date <= :c group by 1",
            {"c": cutoff},
        )
        sr = dict(zip(src["mstar_id"], src["d"], strict=False))
        ids = [i for i in ids if sr.get(i) and (fl.get(i) is None or sr[i] > fl[i])]
    return ids[:limit] if limit else ids


def compute_one(mstar_id: str, run_id: str, floor, cutoff) -> int:
    px = _db.read_df(
        f"select nav_date, nav from {M}.de_mf_nav_daily "
        "where mstar_id = :k and nav > 0 and nav_date <= :c order by nav_date",
        {"k": mstar_id, "c": cutoff},
    )
    if len(px) < 2:
        return 0
    nav = pd.Series(
        px["nav"].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(px["nav_date"]))
    )
    out = pd.DataFrame(index=nav.index)
    out["mstar_id"] = mstar_id
    out["date"] = [d.date() for d in nav.index]
    out["nav"] = nav.values
    for p in T.EMA_PERIODS:
        out[f"ema_{p}"] = T.ema(nav, p).values
    out["compute_run_id"] = run_id
    if floor is not None:  # incremental: EMAs from full history, write only the new tail
        out = out[[d > floor for d in out["date"]]]
        if out.empty:
            return 0
    out = out.astype(object).where(pd.notna(out), None)
    return _db.upsert_df(f"{M}.technical_fund_daily", out, ["mstar_id", "date"])


def run(incremental: bool = True, limit: int | None = None) -> dict:
    run_id = str(uuid.uuid4())
    cutoff = _db.eod_cutoff()
    floor = {}
    if incremental:
        df = _db.read_df(f"select mstar_id, max(date) d from {M}.technical_fund_daily group by 1")
        floor = dict(zip(df["mstar_id"], df["d"], strict=False))
    ids = targets(incremental, limit, cutoff)
    done = err = rows_tot = 0
    print(
        f"[fund-tech] targets={len(ids)} mode={'incr' if incremental else 'full'} eod={cutoff}",
        flush=True,
    )
    for n, mid in enumerate(ids, 1):
        try:
            rows_tot += compute_one(mid, run_id, floor.get(mid) if incremental else None, cutoff)
            done += 1
        except Exception as e:
            print(f"[fund-tech] ERROR {mid}: {e!r}", flush=True)
            err += 1
        if n % 100 == 0 or n == len(ids):
            print(f"[fund-tech] {n}/{len(ids)} done={done} err={err} rows={rows_tot:,}", flush=True)
    res = {"targets": len(ids), "done": done, "errors": err, "rows_written": rows_tot}
    print(f"[fund-tech] COMPLETE {res}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description="EMA ladder over NAV for all universe funds")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", "--full", dest="redo", action="store_true")
    args = ap.parse_args()
    run(incremental=not args.redo, limit=args.limit)


if __name__ == "__main__":
    main()
