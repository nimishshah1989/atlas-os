#!/usr/bin/env python3
"""Nightly technicals journal → ``atlas_global.technical_daily``, from ``ohlcv_daily``.

    python scripts/global_market/compute_technicals.py                       # incremental
    python scripts/global_market/compute_technicals.py --eod 2026-09-03 --report tech.csv
    python scripts/global_market/compute_technicals.py --scope all           # every listing
    python scripts/global_market/compute_technicals.py --redo                # rewrite history

India's ``scripts/foundation/compute_all.py`` is the writer pattern, in USD and on the SPY
calendar: an incremental floor per instrument (recompute from the FULL history, write only
the tail beyond what is stored, so a normal night costs about one upsert per instrument),
a cap at the EOD cutoff, an upsert on the primary key, and one ``compute_run_id`` per run.
All the arithmetic is in :mod:`technicals_global`; this file is the I/O around it.

Which instruments
-----------------
``--scope universe`` (the default) is the set that can actually be scored or charted:
``universe_snapshot.in_universe`` on the latest snapshot, PLUS every instrument
``index_membership`` has ever carried (a former S&P 500 member is out of the universe but
its history is what backtests and the IC study read), PLUS the active benchmarks. Computing
all 13k listings is possible — ``--scope all`` — but most of them are never shown, never
scored and never a benchmark, so the default does not spend the night on them.

The price basis
---------------
Each instrument's ``ohlcv_daily.adjustment_source`` label says WHICH adjusted series its rows
carry, and :func:`atlas.global_market.price_basis.plan_for` turns that into the pair this
file computes on: the trend block (EMA / RSI / ATR / Bollinger / IBS) on the SPLIT-ONLY
series, and every return, relative-strength and risk metric on the TOTAL-RETURN one. The
vendor is pulled on three adjustments per window, so an ``alpaca:split+all`` row holds both
and neither family has to settle. ``price_basis`` on the written row records the pair.

Where a feed carries only ONE series both families read it, and the stamp says so rather than
hiding it: the Stooq archive has ``close_tr`` alone, so its EMAs run on a dividend-adjusted
series, which drifts up against a price series and reads slightly bullish. Nothing here
decides what a feed carries: the label is minted by the ingester only after
``validate_global.py --check BASIS`` has MEASURED the basis from real bars, and the
orchestrator re-runs that gate ahead of this step every night, so a feed that changes its
adjustment cannot be scored under its old label.

Three ways an instrument is SKIPPED and listed in the report rather than guessed at: its bars
carry no label this code knows (there is no safe default — a raw close is neither split- nor
dividend-adjusted), they carry two, or its return series differs from SPY's, which would make
every ``rs_*_spy`` a ratio of a total return to a price return.

Sessions are SPY's bars, exactly as ``build_universe_snapshot.py`` defines them: Stooq
carries stray bars on exchange holidays, and a holiday is not a session.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report, technicals_global
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package, run as a file

import _gdb
import numpy as np
import pandas as pd
import technicals_global as G
from _report import Report

from atlas.db import load_thresholds
from atlas.global_market import calendar as gcal
from atlas.global_market import price_basis as PB

M = _gdb.M
BENCHMARK_SYMBOL = "SPY"
KEY_COLUMNS = ["instrument_id", "date"]
IDENTITY_COLUMNS = ["instrument_id", "asset_class", "symbol", "date"]
WRITTEN_COLUMNS = (
    IDENTITY_COLUMNS
    + G.METRIC_COLUMNS
    + G.LIQUIDITY_COLUMNS
    + ["price_basis", "compute_run_id", "computed_at"]
)
BOOLEAN_COLUMNS = [f"above_ema_{p}" for p in G.T.EMA_PERIODS]

ADV_SCALE = Decimal(1).scaleb(-4)  # allow-threshold: technical_daily.adv_usd_* is numeric(20,4)
MIN_OBSERVATIONS_KEY = "liquidity_min_observations_60d"

# The status vocabulary of the per-instrument report.
STATUS_COMPUTED = "computed"
STATUS_UP_TO_DATE = "up_to_date"
STATUS_NO_BARS = "no_bars"
STATUS_TOO_SHORT = "too_short"
STATUS_NO_BASIS = "no_price_basis"
STATUS_MIXED_BASIS = "mixed_price_basis"
STATUS_BENCHMARK_BASIS = "benchmark_basis_mismatch"
STATUS_ERROR = "error"
REPORT_COLUMNS = (
    "instrument_id",
    "symbol",
    "asset_class",
    "status",
    "rows",
    "first_date",
    "last_date",
    "price_basis",
    "detail",
)

SESSIONS_SQL = f"""
SELECT date FROM {M}.ohlcv_daily
WHERE instrument_id = (SELECT instrument_id FROM {M}.instrument_master
                       WHERE symbol = :symbol AND is_active)
  AND date <= :cutoff
ORDER BY date
"""

# in_universe on the latest snapshot, every instrument index_membership has ever carried,
# and the active benchmarks. asset_class comes from instrument_master, which is also what
# restricts the set to the two classes technical_daily's CHECK allows.
TARGETS_SQL = f"""
WITH picked AS (
    SELECT instrument_id FROM {M}.universe_snapshot
    WHERE date = (SELECT max(date) FROM {M}.universe_snapshot) AND in_universe
    UNION SELECT instrument_id FROM {M}.index_membership
    UNION SELECT instrument_id FROM {M}.benchmark_master WHERE is_active
)
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.asset_class
FROM {M}.instrument_master im
WHERE im.is_active AND im.asset_class IN ('stock', 'etf')
  AND (:everything OR im.instrument_id IN (SELECT instrument_id FROM picked))
ORDER BY im.asset_class, im.symbol
"""

# One row per instrument: its adjustment_source labels, and the dates it has bars for.
# Aggregated in two steps on purpose. `array_agg(DISTINCT ...)` over the raw bars cannot be
# hashed, so Postgres SORTS all 8.4M rows for it and spills ~585 MB of temp files to do it;
# grouping by (instrument_id, adjustment_source) FIRST is a hash aggregate down to one row
# per label, and the DISTINCT then runs over ~2.3k rows. Measured on the real archive: 4.17 s
# -> 0.79 s, no spill, and byte-identical output for all 2,346 instruments.
COVERAGE_SQL = f"""
SELECT d.instrument_id::text AS instrument_id,
       sum(d.bars)::bigint AS bars, max(d.last_date) AS last_date,
       array_agg(DISTINCT d.adjustment_source) AS adjustment_sources
FROM (SELECT o.instrument_id, o.adjustment_source, count(*) AS bars, max(o.date) AS last_date
      FROM {M}.ohlcv_daily o
      WHERE o.instrument_id = ANY(CAST(:ids AS uuid[])) AND o.date <= :cutoff
      GROUP BY 1, 2) d
GROUP BY 1
"""

FLOOR_SQL = f"""
SELECT instrument_id::text AS instrument_id, max(date) AS last_date
FROM {M}.technical_daily GROUP BY 1
"""

# The bars the ADV$ block is computed FROM; the window itself is pandas' (liquidity_frame).
# `traded` is the archive's own close x volume — the quantity the FM's ADV$ table and the
# $1,000,000 floor were measured in. Postgres multiplies it in exact numeric and hands over
# one float8, so that conversion is the only rounding between the archive and the window.
TRADED_SQL = f"""
SELECT o.instrument_id::text AS instrument_id, o.date,
       (o.close * o.volume)::float8 AS traded, (o.volume = 0) AS zero_volume
FROM {M}.ohlcv_daily o
WHERE o.instrument_id = ANY(CAST(:ids AS uuid[]))
  AND o.date BETWEEN :since AND :cutoff
  AND o.close IS NOT NULL AND o.volume IS NOT NULL
"""

RISK_FREE_SQL = f"SELECT date, dtb3 FROM {M}.macro_daily WHERE dtb3 IS NOT NULL ORDER BY date"

# Both series in one read. `close` is the TREND series (split-only where the feed has it),
# `close_ret` the RETURN series (total return where it has it); where a feed carries only one
# the two names resolve to the same column and the duplicated predicate is a no-op. A session
# missing EITHER close is dropped, so the two series always span the same index — a trend
# metric and a return metric on a row are then statements about the same set of sessions.
BARS_SQL_TEMPLATE = f"""
SELECT o.date, o.{{open}} AS open, o.{{high}} AS high, o.{{low}} AS low,
       o.{{close}} AS close, o.{{close_ret}} AS close_ret, o.volume
FROM {M}.ohlcv_daily o
WHERE o.instrument_id = CAST(:iid AS uuid) AND o.date <= :cutoff
  AND o.{{close}} IS NOT NULL AND o.{{close}} > 0
  AND o.{{close_ret}} IS NOT NULL AND o.{{close_ret}} > 0
ORDER BY o.date
"""


def sessions(cutoff: dt.date) -> pd.DatetimeIndex:
    """The platform calendar: every date SPY has a bar at or before the cutoff."""
    frame = _gdb.read_df(SESSIONS_SQL, {"symbol": BENCHMARK_SYMBOL, "cutoff": cutoff})
    if frame.empty:
        raise SystemExit(f"no {BENCHMARK_SYMBOL} bars at or before {cutoff}: there is no calendar")
    return pd.DatetimeIndex(pd.to_datetime(gcal.sessions(frame["date"])))


def bar_frame(
    instrument_id: str, plan: PB.BasisPlan, cutoff: dt.date, cal: pd.DatetimeIndex
) -> pd.DataFrame:
    """One instrument's OHLCV on ``plan``, restricted to SPY sessions, ascending by date.

    ``open/high/low/close/volume`` are the trend series; ``close_ret`` is the return series.
    """
    trend = PB.price_columns(plan.trend)
    sql = BARS_SQL_TEMPLATE.format(
        open=trend[0],
        high=trend[1],
        low=trend[2],
        close=trend[3],
        close_ret=PB.price_columns(plan.returns)[3],
    )
    frame = _gdb.read_df(sql, {"iid": instrument_id, "cutoff": cutoff})
    if frame.empty:
        return frame
    frame.index = pd.DatetimeIndex(pd.to_datetime(G.series(frame, "date")))
    for column in ("open", "high", "low", "close", "close_ret", "volume"):
        frame[column] = G.as_series(pd.to_numeric(frame[column], errors="coerce")).astype("float64")
    return frame.loc[frame.index.isin(cal)]


def risk_free_daily(cal: pd.DatetimeIndex) -> pd.Series:
    """FRED DTB3 as a DAILY rate on the session calendar, or all-NaN when macro is empty.

    DTB3 is quoted as a PERCENT PER ANNUM (5.25 means 5.25 percent a year), so the daily
    equivalent is the geometric one, ``(1 + dtb3/100) ** (1/252) - 1`` — not a division by
    252, which would understate a compounding rate. It is carried forward across sessions
    FRED does not post (a market holiday, a delayed release): the bill rate on a day without
    a print is the last printed rate, not zero. Where nothing has printed yet the value stays
    NaN, and every Sharpe / Sortino window touching it is NULL rather than risk-free-free.
    """
    frame = _gdb.read_df(RISK_FREE_SQL)
    if frame.empty:
        return pd.Series(np.nan, index=cal, dtype="float64")
    annual = pd.Series(
        G.as_series(pd.to_numeric(frame["dtb3"], errors="coerce")).to_numpy(dtype="float64"),
        index=pd.DatetimeIndex(pd.to_datetime(G.series(frame, "date"))),
    )
    daily = G.as_series((1.0 + annual / 100.0) ** (1.0 / G.ANNUALISATION) - 1.0)
    return G.as_series(daily.reindex(cal)).ffill()


def benchmark_close(cutoff: dt.date, cal: pd.DatetimeIndex) -> tuple[pd.Series, PB.BasisPlan]:
    """SPY's RETURN-series close — the RS denominator and the beta / correlation factor.

    Only the return series is needed: nothing in the trend block reads the benchmark. Every
    instrument's own return series must match this one, or its relative strength would divide
    a total return by a price return; :func:`run` refuses the mismatch rather than store it.
    """
    row = _gdb.read_df(
        f"SELECT instrument_id::text AS instrument_id FROM {M}.instrument_master "
        "WHERE symbol = :symbol AND is_active",
        {"symbol": BENCHMARK_SYMBOL},
    )
    if row.empty:
        raise SystemExit(f"{BENCHMARK_SYMBOL} is not an active instrument")
    instrument_id = str(row["instrument_id"].iloc[0])
    sources = _gdb.read_df(COVERAGE_SQL, {"ids": [instrument_id], "cutoff": cutoff})
    plan = uniform_plan(list(sources["adjustment_sources"].iloc[0])) if not sources.empty else None
    if plan is None:
        raise SystemExit(
            f"{BENCHMARK_SYMBOL} bars carry no price basis this build knows "
            f"({list(sources['adjustment_sources'].iloc[0]) if not sources.empty else 'no bars'}); "
            "re-run import_stooq.py --relabel, or ingest SPY from a labelled source"
        )
    return G.series(bar_frame(instrument_id, plan, cutoff, cal), "close_ret"), plan


def uniform_plan(adjustment_sources: list[str | None]) -> PB.BasisPlan | None:
    """The ONE basis plan an instrument's bars carry, or ``None`` if none or more than one.

    Mixing bases inside one series would put a dividend-adjusted close next to a split-only
    one and call the step between them a return, so a mixed instrument is refused outright.
    """
    plans = {PB.plan_for(source) for source in adjustment_sources}
    if len(plans) != 1:
        return None
    return plans.pop()


def liquidity_window(
    cal: pd.DatetimeIndex, ids: list[str], floor: dict[str, dt.date], incremental: bool
) -> pd.DatetimeIndex:
    """The slice of the session calendar the ADV$ block has to be computed over.

    A 60-session window needs 59 sessions of run-up before the first row that will be WRITTEN
    and nothing before that, so a normal night reads sixty sessions and not sixty years. A
    target never computed has no floor and needs its whole history — as does ``--redo``.
    """
    if not incremental or not ids or any(instrument_id not in floor for instrument_id in ids):
        return cal
    first_written = min(floor[instrument_id] for instrument_id in ids)
    start = int(np.searchsorted(cal.to_numpy(), np.datetime64(first_written)))
    start -= G.ADV_MEDIAN_SESSIONS - 1
    return cal[max(start, 0) :]


def liquidity_frame(
    ids: list[str], cutoff: dt.date, window: pd.DatetimeIndex, min_observations: int
) -> pd.DataFrame:
    """ADV$ (20-session mean, 60-session median) and zero-volume days, keyed by (id, date).

    The window is ``build_universe_snapshot.ADV_SQL``'s — the last 60 SPY SESSIONS, the same
    ``>= min_obs`` guard — so the median is the SAME number the universe gate set the
    liquidity floor from, and ``test_adv_matches_build_universe_snapshot`` asserts it. It is
    rolled the way India rolls a window (``scripts/foundation/technicals.py``): pandas, in
    :func:`technicals_global.rolling_liquidity`, over the whole universe in one pass.

    Measured at 2026-09-03 over all 2,345 instruments against the sibling's exact ``::numeric``
    percentile_cont: worst disagreement 3.0e-06 USD on an ADV\\$ of 2.2e+10 (2.4e-16 relative),
    1,827 bit-identical, and no NULL landing anywhere different.
    """
    if not ids or window.empty:
        return G.rolling_liquidity(pd.DataFrame(), window, min_observations)
    since = G.as_dates(window)[0]
    raw = _gdb.read_df(TRADED_SQL, {"ids": ids, "since": since, "cutoff": cutoff})
    return G.rolling_liquidity(raw, window, min_observations)


def targets(scope: str, limit: int | None) -> pd.DataFrame:
    frame = _gdb.read_df(TARGETS_SQL, {"everything": scope == "all"})
    return frame.head(limit) if limit else frame


def floors() -> dict[str, dt.date]:
    """Per-instrument latest date already in technical_daily — the incremental floor."""
    frame = _gdb.read_df(FLOOR_SQL)
    return dict(zip(frame["instrument_id"], frame["last_date"], strict=True))


def extends_beyond(coverage: pd.DataFrame, instrument_id: str, floor: dict[str, dt.date]) -> bool:
    """Do this instrument's bars reach past the last date technical_daily holds for it?

    ``coverage`` carries each instrument's newest bar at or before the EOD cutoff, so an
    instrument that has not traded since its last computed row needs no work at all. Never
    computed yet (no floor) always counts as extending.
    """
    stored = floor.get(instrument_id)
    if stored is None:
        return True
    return bool(coverage.loc[instrument_id, "last_date"] > stored)


def rows_for(
    instrument: tuple[str, str, str],
    bars: pd.DataFrame,
    plan: PB.BasisPlan,
    benchmark: pd.Series,
    risk_free: pd.Series,
    liquidity: pd.DataFrame,
    run_id: str,
    floor: dt.date | None,
) -> pd.DataFrame:
    """The technical_daily rows for one instrument, tail-filtered to the incremental floor.

    Every metric is derived from the instrument's FULL history — an EMA or a 252-session beta
    on a truncated series is a different number — and only the rows after ``floor`` are
    returned, so a normal night writes one row per instrument and not the whole journal.
    """
    instrument_id, asset_class, symbol = instrument
    metrics = G.metric_frame(bars, G.series(bars, "close_ret"), benchmark, risk_free)
    out = pd.DataFrame(index=bars.index)
    out["instrument_id"] = instrument_id
    out["asset_class"] = asset_class
    out["symbol"] = symbol
    out["date"] = G.as_dates(bars.index)
    for column in G.METRIC_COLUMNS:
        out[column] = metrics[column]
    out["price_basis"] = plan.stamp
    out["compute_run_id"] = run_id
    out["computed_at"] = dt.datetime.now(ZoneInfo(gcal.NEW_YORK))
    if floor is not None:
        out = out.loc[out.index > pd.Timestamp(floor)]
    attach_liquidity(out, instrument_id, liquidity)
    return out


def attach_liquidity(out: pd.DataFrame, instrument_id: str, liquidity: pd.DataFrame) -> None:
    """Join the per-session ADV$ block onto this instrument's rows, back in Decimal.

    A reindex IS the left join: an instrument the block has no rows for — or a session it has
    none for — falls out as NaN, the all-NULL column the hand-written branches built by hand.
    Money is never a float in storage, so the dollar columns go back to exact Decimals at the
    column's own scale on the way to the upsert.
    """
    mine = liquidity.reindex(pd.MultiIndex.from_product([[instrument_id], out["date"]]))
    for column in G.LIQUIDITY_COLUMNS:
        values = mine[column].to_numpy(dtype="float64")
        if column == "zero_volume_days_60d":
            out[column] = pd.array(values, dtype="Int64")  # a count, not an amount
        else:  # .tolist() for PYTHON floats: repr(numpy.float64) is "np.float64(...)"
            out[column] = [
                None if v != v else Decimal(repr(v)).quantize(ADV_SCALE) for v in values.tolist()
            ]


def clean(out: pd.DataFrame) -> pd.DataFrame:
    """+-inf to NaN, and the boolean columns onto a dtype psycopg2 can adapt.

    An infinity is an undefined metric (a ratio over a zero denominator), not a large one, so
    it is stored as NULL. NaN-to-NULL itself is NOT done here: ``_db.upsert_df`` does that
    object cast for every producer in both markets, and doing it twice built a second object
    copy of the whole frame. What is left is this table's own — the infinity mask, and
    pandas' nullable ``boolean``, whose object form is a Python ``bool`` (psycopg2 has no
    adapter for the ``numpy.bool_`` a plain bool column casts to).
    """
    floats = list(out.select_dtypes(include=["floating"]).columns)
    if floats:
        out[floats] = out[floats].mask(~np.isfinite(out[floats]))
    for column in BOOLEAN_COLUMNS:
        out[column] = out[column].astype("boolean")
    return out


def compute_one(
    instrument: tuple[str, str, str],
    plan: PB.BasisPlan,
    cutoff: dt.date,
    cal: pd.DatetimeIndex,
    benchmark: pd.Series,
    risk_free: pd.Series,
    liquidity: pd.DataFrame,
    run_id: str,
    floor: dt.date | None,
) -> tuple[str, int, pd.DataFrame]:
    """(status, rows written, the rows) for one instrument."""
    instrument_id = instrument[0]
    bars = bar_frame(instrument_id, plan, cutoff, cal)
    if bars.empty:
        return STATUS_NO_BARS, 0, bars
    if len(bars) < 2:
        return STATUS_TOO_SHORT, 0, bars  # a return needs two closes
    out = rows_for(instrument, bars, plan, benchmark, risk_free, liquidity, run_id, floor)
    if out.empty:
        return STATUS_UP_TO_DATE, 0, out
    out = clean(out.reindex(columns=WRITTEN_COLUMNS))
    written = _gdb.upsert_df(f"{M}.technical_daily", out, KEY_COLUMNS)
    return STATUS_COMPUTED, written, out


def run(
    *,
    eod: dt.date | None,
    scope: str,
    limit: int | None,
    incremental: bool,
    report: Report,
) -> dict[str, object]:
    started = time.monotonic()
    run_id = str(uuid.uuid4())
    cutoff = eod or _gdb.eod_cutoff()
    cal = sessions(cutoff)
    benchmark, benchmark_plan = benchmark_close(cutoff, cal)
    risk_free = risk_free_daily(cal)
    thresholds = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())
    min_observations = int(thresholds[MIN_OBSERVATIONS_KEY])
    picked = targets(scope, limit)
    ids = [str(i) for i in picked["instrument_id"]]
    coverage = _gdb.read_df(COVERAGE_SQL, {"ids": ids, "cutoff": cutoff}).set_index("instrument_id")
    floor = floors() if incremental else {}
    # The ADV$ block only has to cover what will actually be WRITTEN: an instrument with no
    # bars, or none past what technical_daily holds, is skipped below before a metric is run.
    known = coverage.index
    todo = [
        i for i in ids if i in known and (not incremental or extends_beyond(coverage, i, floor))
    ]
    liquidity = liquidity_frame(
        todo, cutoff, liquidity_window(cal, todo, floor, incremental), min_observations
    )
    print(
        f"[technicals] targets={len(picked):,d} scope={scope} eod={cutoff} "
        f"sessions={len(cal):,d} benchmark={BENCHMARK_SYMBOL}({benchmark_plan.returns}) "
        f"mode={'incremental' if incremental else 'full'} "
        f"risk_free={'macro_daily.dtb3' if risk_free.notna().any() else 'ABSENT (Sharpe/Sortino NULL)'}",
        flush=True,
    )

    counts: dict[str, int] = {}
    rows_total = 0
    rows = zip(picked["instrument_id"], picked["asset_class"], picked["symbol"], strict=True)
    for n, (raw_id, raw_class, raw_symbol) in enumerate(rows, 1):
        instrument = (str(raw_id), str(raw_class), str(raw_symbol))
        instrument_id = instrument[0]
        plan = None
        if instrument_id in coverage.index:
            plan = uniform_plan(list(coverage.loc[instrument_id, "adjustment_sources"]))
        try:
            if instrument_id not in coverage.index:
                status, written, out = STATUS_NO_BARS, 0, pd.DataFrame()
            elif incremental and not extends_beyond(coverage, instrument_id, floor):
                # India's compute_all rule: an instrument whose bars do not reach past what
                # technical_daily already holds is SKIPPED here, before its history is read
                # or a metric computed. Filtering the rows afterwards would still pay for the
                # whole recompute, which is the cost a nightly incremental exists to avoid.
                status, written, out = STATUS_UP_TO_DATE, 0, pd.DataFrame()
            elif plan is None or plan.returns != benchmark_plan.returns:
                labels = sorted(str(s) for s in coverage.loc[instrument_id, "adjustment_sources"])
                if plan is None:
                    status = STATUS_MIXED_BASIS if len(labels) > 1 else STATUS_NO_BASIS
                    note = ",".join(labels)
                else:
                    # RS divides this instrument's return by SPY's. One of them being a price
                    # return and the other a total return makes that ratio a number about the
                    # dividend yield, not about relative strength — so it is not computed.
                    status = STATUS_BENCHMARK_BASIS
                    note = (
                        f"{','.join(labels)} → {plan.returns}, but "
                        f"{BENCHMARK_SYMBOL} is {benchmark_plan.returns}"
                    )
                written, out = 0, pd.DataFrame()
                report.add(
                    *instrument[:1],
                    instrument[2],
                    instrument[1],
                    status,
                    0,
                    None,
                    None,
                    None,
                    note,
                )
                counts[status] = counts.get(status, 0) + 1
                continue
            else:
                status, written, out = compute_one(
                    instrument,
                    plan,
                    cutoff,
                    cal,
                    benchmark,
                    risk_free,
                    liquidity,
                    run_id,
                    floor.get(instrument_id) if incremental else None,
                )
        except Exception as error:  # one bad instrument never stops the journal
            status, written, out = STATUS_ERROR, 0, pd.DataFrame()
            report.add(
                instrument_id,
                instrument[2],
                instrument[1],
                status,
                0,
                None,
                None,
                plan.stamp if plan else None,
                repr(error)[:300],
            )
            counts[status] = counts.get(status, 0) + 1
            continue
        first = out["date"].iloc[0] if written else None
        last = out["date"].iloc[-1] if written else None
        report.add(
            instrument_id,
            instrument[2],
            instrument[1],
            status,
            written,
            first,
            last,
            plan.stamp if plan else None,
            "",
        )
        counts[status] = counts.get(status, 0) + 1
        rows_total += written
        if n % 250 == 0 or n == len(picked):
            print(
                f"[technicals] {n}/{len(picked)} rows={rows_total:,d} "
                f"{' '.join(f'{k}={v}' for k, v in sorted(counts.items()))}",
                flush=True,
            )
    result = {
        "targets": len(picked),
        "rows_written": rows_total,
        "seconds": round(time.monotonic() - started, 1),
        **counts,
    }
    print(f"[technicals] COMPLETE {result} {report.where()}", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--eod",
        type=dt.date.fromisoformat,
        default=None,
        help="anchor date (default: _gdb.eod_cutoff())",
    )
    parser.add_argument(
        "--scope",
        choices=("universe", "all"),
        default="universe",
        help="universe (default): scored names + former index members + "
        "benchmarks; all: every active stock and ETF",
    )
    parser.add_argument("--limit", type=int, default=None, help="first N targets (smoke test)")
    parser.add_argument(
        "--redo",
        "--full",
        dest="redo",
        action="store_true",
        help="recompute and rewrite ALL history (default is incremental)",
    )
    parser.add_argument("--report", type=Path, default=None, help="CSV of per-instrument outcomes")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="write compute_technicals_<eod>.csv into this directory",
    )
    args = parser.parse_args()

    path = args.report
    if path is None and args.report_dir is not None:
        stamp = args.eod or _gdb.eod_cutoff()
        path = args.report_dir / f"compute_technicals_{stamp}.csv"
    report = Report(path, REPORT_COLUMNS)
    try:
        run(
            eod=args.eod,
            scope=args.scope,
            limit=args.limit,
            incremental=not args.redo,
            report=report,
        )
    finally:
        report.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
