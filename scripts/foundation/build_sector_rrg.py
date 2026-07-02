#!/usr/bin/env python3
"""Native sector RRG (Relative Rotation Graph) builder — JdK-style from staging prices.

Replaces the legacy mirror of ``atlas.mv_sector_rrg`` (which carried a stale,
broken snapshot — 21 of 30 sectors stuck on "Leading" with rs-ratios inflated
far above 100, and inconsistencies like Energy "Weakening" sitting at +15pp
momentum). This computes every canonical sector's rotation DIRECTLY from
``atlas_foundation.index_prices`` against the Nifty 500 benchmark.

RRG math (JdK Relative Rotation Graph, centered to reproduce the standard frame):
  1. RS(t) = sector_close(t) / nifty500_close(t) on common trading dates.
  2. Resample weekly — last RS of each ISO week (week_end_date = that week's last
     trading date).
  3. rs_ratio   = 100 * RS / SMA(RS, 10 weeks)        (100 = in line with Nifty 500)
  4. rs_momentum = 100 * (rs_ratio / rs_ratio.shift(4 weeks) - 1)   (0 = no accel)
  5. quadrant: Leading (ratio>=100, mom>=0), Weakening (>=100, <0),
     Lagging (<100, <0), Improving (<100, >=0).
  6. ``*_current`` = latest week; ``trail_6w`` = last 6 weekly points, oldest-first.

Writes one row per canonical sector into ``atlas_foundation.mv_sector_rrg``,
keyed on (as_of_date, sector_name). ``as_of_date`` = latest priced date.

Run:
  python -m scripts.foundation.build_sector_rrg
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from scripts.foundation import _db

M = "atlas_foundation"
N500 = "NIFTY 500"
TABLE = f"{M}.mv_sector_rrg"

SMA_WEEKS = 10  # RS-ratio trend window
MOM_SHIFT = 4  # RS-momentum look-back (weeks); lands magnitudes in ~-25..+25
TRAIL_LEN = 6  # weekly points kept in trail_6w


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


def _quadrant(ratio: float, mom: float) -> str:
    if ratio >= 100 and mom >= 0:
        return "Leading"
    if ratio >= 100:
        return "Weakening"
    if mom < 0:
        return "Lagging"
    return "Improving"


def _sectors() -> pd.DataFrame:
    """Canonical sectors (mv_sector_cards) joined to their primary NSE index."""
    return _db.read_df(
        f"""
        select m.sector_name, m.primary_nse_index
        from {M}.atlas_sector_master m
        where m.is_active = true
          and lower(m.sector_name) not like '%conglomerate%'
          and m.sector_name in (
            select distinct sector_name from {M}.mv_sector_cards
            where as_of_date = (select max(as_of_date) from {M}.mv_sector_cards)
          )
        order by m.sector_name
        """
    )


def _rrg_frame(sector_close: pd.Series, bench: pd.Series) -> pd.DataFrame:
    """Weekly RS-ratio / RS-momentum / quadrant frame for one sector.

    Returns a frame indexed by week_end_date (the last trading date in each ISO
    week), columns rs_ratio / rs_momentum / quadrant, NaN rows dropped.
    """
    common = sector_close.index.intersection(bench.index)
    rs = sector_close.reindex(common) / bench.reindex(common)
    # week_end_date = last trading date in each ISO week (not the calendar Sunday).
    grp = rs.groupby(pd.Grouper(freq="W"))
    weekly_rs = grp.last().dropna()
    weekly_end = grp.apply(lambda s: s.dropna().index.max())
    week_end = weekly_end.reindex(weekly_rs.index)

    sma = weekly_rs.rolling(SMA_WEEKS).mean()
    ratio = 100.0 * weekly_rs / sma
    mom = 100.0 * (ratio / ratio.shift(MOM_SHIFT) - 1.0)

    out = pd.DataFrame({"rs_ratio": ratio, "rs_momentum": mom})
    out["week_end_date"] = [d.date() for d in week_end]
    out = out.dropna(subset=["rs_ratio", "rs_momentum"])
    out["quadrant"] = [
        _quadrant(r, m) for r, m in zip(out["rs_ratio"], out["rs_momentum"], strict=True)
    ]
    return out


def _ensure_unique_index() -> None:
    """Unique index on (as_of_date, sector_name) so the upsert has a conflict target.

    The legacy mirror left only a non-unique sector_name index; without a unique
    key ON CONFLICT cannot fire. Dedup any pre-existing rows first, then add it.
    """
    if _db.scalar(
        "select 1 from pg_indexes where schemaname=:s and tablename='mv_sector_rrg' "
        "and indexname='ux_sector_rrg_date_sector'",
        {"s": M},
    ):
        return
    _db.exec_sql(
        f"""
        delete from {TABLE} a using {TABLE} b
        where a.ctid < b.ctid
          and a.as_of_date = b.as_of_date and a.sector_name = b.sector_name
        """
    )
    _db.exec_sql(
        f"create unique index ux_sector_rrg_date_sector on {TABLE} (as_of_date, sector_name)"
    )


def build() -> int:
    bench = _series(N500)
    if bench.empty:
        raise RuntimeError("NIFTY 500 series empty — cannot compute RS")
    as_of = max(d.date() for d in bench.index)
    now = dt.datetime.now(dt.UTC)

    _ensure_unique_index()

    rows: list[dict] = []
    skipped: list[str] = []
    for _, r in _sectors().iterrows():
        sector, code = r["sector_name"], r["primary_nse_index"]
        s = _series(code)
        if s.empty:
            skipped.append(f"{sector} (no prices for {code})")
            continue
        frame = _rrg_frame(s, bench)
        if len(frame) < TRAIL_LEN:
            skipped.append(f"{sector} ({len(frame)} weekly points < {TRAIL_LEN})")
            continue
        tail = frame.tail(TRAIL_LEN)
        wk = [str(x) for x in tail["week_end_date"].tolist()]
        rr = [round(float(x), 2) for x in tail["rs_ratio"].tolist()]
        mm = [round(float(x), 2) for x in tail["rs_momentum"].tolist()]
        qq = [str(x) for x in tail["quadrant"].tolist()]
        trail_json = [
            {"week_end_date": wk[i], "rs_ratio": rr[i], "rs_momentum": mm[i], "quadrant": qq[i]}
            for i in range(len(wk))
        ]
        rows.append(
            {
                "as_of_date": as_of,
                "sector_name": sector,
                "rs_ratio_current": rr[-1],
                "rs_momentum_current": mm[-1],
                "quadrant_current": qq[-1],
                "trail_6w": json.dumps(trail_json),
                "refreshed_at": now,
            }
        )

    df = pd.DataFrame(rows)
    n = _db.upsert_df(TABLE, df, ["as_of_date", "sector_name"])

    dist = df["quadrant_current"].value_counts().to_dict()
    print(f"[sector_rrg] as_of={as_of} sectors={n} rows_written={n}")
    print(f"[sector_rrg] quadrants={dist}")
    if skipped:
        print(f"[sector_rrg] skipped: {'; '.join(skipped)}")
    print(
        df[
            ["sector_name", "rs_ratio_current", "rs_momentum_current", "quadrant_current"]
        ].to_string(index=False)
    )
    return n


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
