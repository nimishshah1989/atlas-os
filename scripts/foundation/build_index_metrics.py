#!/usr/bin/env python3
"""Native index-metrics builder — calendar-anchored returns from staging OHLCV.

Replaces the legacy mirror of ``atlas.atlas_index_metrics_daily`` (which carried
row-count-anchored returns that drift onto the wrong calendar date on a gap-ridden
index series — Nifty 50 3m read 6.9% vs a true 3.2%). This computes every index's
trailing returns DIRECTLY from ``foundation_staging.index_prices`` using the single
canonical definition in ``technicals.windowed_return`` (month+ windows anchored by
calendar duration, cross-validated across two feeds to <0.1pp).

Because it reads ``index_prices`` rather than a sector-index allow-list, it also
covers the indices the old mirror left NULL (Nifty Media, Nifty India Tourism …),
which is why those sectors used to vanish from the heatmap at the 3m+ windows.

Writes the return columns (ret_1d/1w/1m/3m/6m/12m) + RS vs Nifty 500 for the latest
priced date of every index. ``--all-dates`` backfills the full history.

Run:
  python -m scripts.foundation.build_index_metrics              # latest snapshot
  python -m scripts.foundation.build_index_metrics --all-dates  # full history
"""

from __future__ import annotations

import argparse
import datetime as dt
import uuid

import pandas as pd

from scripts.foundation import _db
from scripts.foundation import technicals as T

M = "foundation_staging"
N500 = "NIFTY 500"
RET_COLS = [f"ret_{w}" for w in T.RETURN_WINDOWS]  # ret_1d..ret_12m
RS_COLS = ["rs_1w_nifty500", "rs_1m_nifty500", "rs_3m_nifty500"]


def _series(code: str) -> pd.Series:
    df = _db.read_df(
        f"select date, close from {M}.index_prices "
        "where index_code = :c and close > 0 order by date",
        {"c": code},
    )
    if df.empty:
        return pd.Series(dtype="float64")
    return pd.Series(
        df["close"].astype(float).values,
        index=pd.DatetimeIndex(pd.to_datetime(df["date"])),
    )


def build(all_dates: bool) -> int:
    codes = [
        r
        for r in _db.read_df(f"select distinct index_code from {M}.index_prices")[
            "index_code"
        ].tolist()
    ]
    n500 = _series(N500)
    if n500.empty:
        raise RuntimeError("NIFTY 500 series empty — cannot compute RS")
    # benchmark returns per window, calendar-anchored, on the benchmark's own dates
    n500_ret = {w: T.windowed_return(n500, w) for w in T.RETURN_WINDOWS}

    run_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    frames: list[pd.DataFrame] = []
    for code in codes:
        s = _series(code)
        if len(s) < 2:
            continue
        out = pd.DataFrame(index=s.index)
        out["index_code"] = code
        out["date"] = [d.date() for d in s.index]
        for w in T.RETURN_WINDOWS:
            out[f"ret_{w}"] = T.windowed_return(s, w)
        # RS vs Nifty 500: index return − benchmark return on the same date
        bench = {w: n500_ret[w].reindex(s.index).ffill() for w in T.RETURN_WINDOWS}
        out["rs_1w_nifty500"] = out["ret_1w"] - bench["1w"].to_numpy()
        out["rs_1m_nifty500"] = out["ret_1m"] - bench["1m"].to_numpy()
        out["rs_3m_nifty500"] = out["ret_3m"] - bench["3m"].to_numpy()
        if not all_dates:
            out = out.tail(1)  # latest priced date only
        frames.append(out)

    full = pd.concat(frames, ignore_index=True)
    full["compute_run_id"] = run_id
    full["updated_at"] = now
    cols = ["index_code", "date", *RET_COLS, *RS_COLS, "compute_run_id", "updated_at"]
    full = full[cols].astype(object).where(pd.notna(full), None)
    n = _db.upsert_df(f"{M}.atlas_index_metrics_daily", full, ["index_code", "date"])
    print(f"[index_metrics] indices={len(frames)} rows_written={n} run={run_id}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all-dates",
        action="store_true",
        help="backfill full history (default: latest priced date only)",
    )
    args = ap.parse_args()
    build(args.all_dates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
