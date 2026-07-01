#!/usr/bin/env python3
"""Native index-metrics builder — calendar-anchored returns from staging OHLCV.

Replaces the legacy mirror of ``atlas.atlas_index_metrics_daily`` (which carried
row-count-anchored returns that drift onto the wrong calendar date on a gap-ridden
index series — Nifty 50 3m read 6.9% vs a true 3.2%). This computes every index's
trailing returns DIRECTLY from ``foundation_staging.index_prices`` using the single
canonical definition in ``technicals.windowed_return`` (month+ windows anchored by
calendar duration, cross-validated across two feeds to <0.1pp).

Universe is curated DATA-DRIVEN (not a brittle hardcoded list): the sector→index
map ``atlas_sector_master.primary_nse_index`` (covers every sector incl. Nifty
Media / India Tourism, which the old mirror left NULL) plus a broad/cap-tier
allow-list. NSE publishes ~250 indices in the close file; only these ~40 are read
by the product (sector RS + benchmarks), so the ~210 thematic/strategy/debt indices
are intentionally skipped.

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
# Broad / cap-tier benchmarks the product uses on top of the sector→index map.
BROAD_INDICES = (
    "NIFTY 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250",
    "NIFTY MICROCAP 250",
    "NIFTY TOTAL MARKET",
    "NIFTY BANK",
)


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
    # Curated universe: authoritative sector→index map ∪ broad/cap-tier allow-list.
    # BROAD_INDICES are fixed literals (no injection surface).
    broad_lit = ", ".join(f"'{b}'" for b in BROAD_INDICES)
    codes = _db.read_df(
        f"""select distinct index_code from {M}.index_prices
            where index_code in (
                select primary_nse_index from {M}.atlas_sector_master
                where primary_nse_index is not null
            ) or index_code in ({broad_lit})"""
    )["index_code"].tolist()
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
    # Native builder owns its schema: NSE index codes run to ~54 chars (e.g. "NIFTY
    # INDIA CORPORATE GROUP INDEX - ADITYA BIRLA GROUP"), so a varchar(32) column
    # raised StringDataRightTruncation and silently dropped index-RS. Idempotent —
    # only widens when the column is still narrow.
    curlen = _db.scalar(
        "select character_maximum_length from information_schema.columns "
        "where table_schema = :s and table_name = 'atlas_index_metrics_daily' "
        "and column_name = 'index_code'",
        {"s": M},
    )
    if (curlen or 0) < 64:
        _db.exec_sql(
            f"alter table {M}.atlas_index_metrics_daily alter column index_code type varchar(64)"
        )
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
