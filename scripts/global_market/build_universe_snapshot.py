#!/usr/bin/env python3
"""Daily universe-membership journal → ``atlas_global.universe_snapshot``, and the ADV$ table
the FM sets the liquidity floor from.

    python scripts/global_market/build_universe_snapshot.py --eod 2026-09-03 --report universe.csv
    python scripts/global_market/build_universe_snapshot.py --eod 2026-09-03 --report-dir /tmp/atlas-logs

One row per ACTIVE instrument (stock or ETF) per session, whether or not it is in the universe,
with the ADV$ that produced the decision — India's ``scripts/foundation/build_universe_snapshot.py``
in USD. The membership rule is ``universe_core.members`` VERBATIM (a Decimal floor is
currency-agnostic); the window is India's ``adv_frame`` logic on ``ohlcv_daily`` — copied, not
imported, because that function is bound to India's ``_db`` and ``ohlcv_stock`` — with ONE
difference: the sessions are SPY's bars (the platform's calendar, membership-by-presence), not
the table's distinct dates. Stooq carries stray bars on exchange holidays (Memorial Day,
Juneteenth and 3 July 2026 in the FM's archive) and a holiday is not a session.

* ``adv_usd_median_60d`` — median of RAW ``close × volume`` (volume has no adjusted twin) over
  the most recent 60 DISTINCT sessions within 150 calendar days at or before the anchor, the
  latest SPY session ≤ ``--eod``. NULL below ``liquidity_min_observations_60d`` traded sessions
  (a median of two prints IS the block deal), and NULL when the last bar is not within the
  window's final ``liquidity_recency_trading_days`` sessions (a stale median is not a current
  one). NULL is "no signal", never 0 and never "low": ``members`` never passes it.
* ``in_sp500`` — an ``index_membership`` interval (``index_code`` SP500) containing the date;
  ``effective_to`` is EXCLUSIVE (ddl/00_core.sql).
* ``aum_usd`` NULL until Phase 2; ``basket_eligible`` false until an execution provider supplies
  ``fractionable``; ``floor_usd`` = the threshold in force that day, so a later change never
  rewrites history; ``in_universe`` = ``members(adv, floor, held_ids)`` with ``held_ids`` = ∅
  until M2 (``basket_constituents``).

THE FLOOR IS NEVER SEEDED (``seed_thresholds.py``): the FM sets ``liquidity_min_traded_value_usd``
from the REAL distribution. Every run prints the ADV$ percentile table and saves it to
``<report-dir>/adv_usd_<date>.md``; while the floor is unset the run then exits 2 with nothing
written, so the step fails loudly every night until the floor is set from ``/admin/thresholds``
(or an ``atlas_thresholds`` insert with an ``atlas_thresholds_audit`` row naming who and why).
With it set the rows are upserted — idempotent, ``computed_at`` moves — and the ``in_universe``
count is printed. ``--report`` lists every instrument's outcome (no bars / too few observations /
stale / ok) in a CSV.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
import _gdb  # must precede universe_core: it puts scripts/foundation on sys.path
from _report import Report

from atlas.db import load_thresholds
from atlas.global_market import calendar as gcal
from atlas.global_market import index_membership as imx

if TYPE_CHECKING:
    from scripts.foundation import universe_core as U
else:
    import universe_core as U

M = _gdb.M
TGT = f"{M}.universe_snapshot"
THRESHOLD_KEY = "liquidity_min_traded_value_usd"  # the FM's floor: never seeded, never a literal
REPORTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "global" / "reports"
# The FM's question, not a methodology number: the percentiles reported and the candidate
# floors counted (docs/global/phase1.md P1-E). The floor itself comes from atlas_thresholds.
PERCENTILES = (10, 25, 50, 75, 90, 95, 99)
CANDIDATE_FLOORS_USD = (500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000)
STATUS_OK = "ok"
REPORT_COLUMNS = (
    "asset_class",
    "symbol",
    "instrument_id",
    "status",
    "n_obs",
    "last_date",
    "adv_usd_median_60d",
    "in_sp500",
    "in_universe",
)

# India's adv_frame window on the SPY calendar: the most recent 60 sessions at or before the
# cutoff, so holidays cannot shorten it and today's partial candle can never enter it.
_WINDOW = f"""
    d AS (
        SELECT date FROM {M}.ohlcv_daily
        WHERE instrument_id = (SELECT instrument_id FROM {M}.instrument_master
                               WHERE symbol = 'SPY' AND is_active)
          AND date <= :cutoff
          AND date > (CAST(:cutoff AS date) - INTERVAL '{U.LOOKBACK_CALENDAR_DAYS} days')
        ORDER BY date DESC LIMIT {U.LOOKBACK_TRADING_DAYS}
    )"""

ADV_SQL = f"""
    WITH {_WINDOW},
    recent AS (SELECT date FROM d ORDER BY date DESC LIMIT :recency_days),
    liq AS (
        SELECT instrument_id, count(*) AS n_obs, max(date) AS last_date,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume)::numeric AS traded
        FROM {M}.ohlcv_daily
        WHERE date IN (SELECT date FROM d) AND close IS NOT NULL AND volume IS NOT NULL
        GROUP BY instrument_id
    )
    SELECT im.instrument_id::text AS instrument_id, im.symbol, im.asset_class,
           coalesce(liq.n_obs, 0) AS n_obs, liq.last_date,
           coalesce(liq.last_date IN (SELECT date FROM recent), false) AS is_recent,
           CASE WHEN liq.n_obs >= :min_obs AND liq.last_date IN (SELECT date FROM recent)
                THEN liq.traded END AS adv_median_60d
    FROM {M}.instrument_master im
    LEFT JOIN liq ON liq.instrument_id = im.instrument_id
    WHERE im.is_active
    ORDER BY im.asset_class, im.symbol
"""

BARS_SQL = f"""
    WITH {_WINDOW},
    w AS (SELECT min(date) AS first_session, max(date) AS last_session, count(*) AS n_sessions FROM d)
    SELECT w.first_session, w.last_session, w.n_sessions, o.source, o.adjustment_source,
           count(*) AS bars
    FROM w, {M}.ohlcv_daily o
    WHERE o.date IN (SELECT date FROM d)
    GROUP BY 1, 2, 3, 4, 5
    ORDER BY bars DESC
"""

SP500_SQL = f"""
    SELECT instrument_id::text AS instrument_id FROM {M}.index_membership
    WHERE index_code = :code AND effective_from <= :d
      AND (effective_to IS NULL OR effective_to > :d)
"""


INACTIVE_SQL = f"""
SELECT is_active FROM {M}.atlas_thresholds WHERE threshold_key = :key
"""


def thresholds() -> dict[str, Decimal]:
    return load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())


def anchor(eod: dt.date) -> dt.date | None:
    """The latest SPY session at or before ``eod`` — the date the snapshot describes. The EOD is
    an upper bound (weekends and holidays included); the date IS the record in a journal, so a
    Saturday run is a no-op upsert over Friday's row, never a duplicate under a non-session."""
    return _gdb.scalar(
        f"select max(date) from {M}.ohlcv_daily where instrument_id = (select instrument_id "
        f"from {M}.instrument_master where symbol = 'SPY' and is_active) and date <= :d",
        {"d": eod},
    )


def adv_frame(cutoff: dt.date, min_obs: int, recency_days: int) -> pd.DataFrame:
    """One row per ACTIVE instrument: ``adv_median_60d`` (USD, Decimal; NULL outside the two
    guards) plus the diagnostics behind a NULL — ``n_obs``, ``last_date``, ``is_recent`` — and
    ``status`` (no_bars / too_few_observations / stale / ok)."""
    adv = _gdb.read_df(
        ADV_SQL,
        {"cutoff": cutoff, "min_obs": min_obs, "recency_days": recency_days},
        coerce_float=False,  # numeric stays Decimal: money is never a float
    )
    adv["status"] = [
        status(int(n), bool(r), min_obs)
        for n, r in zip(adv["n_obs"], adv["is_recent"], strict=True)
    ]
    return adv


def status(n_obs: int, is_recent: bool, min_obs: int) -> str:
    """Why an instrument has no ADV$ — in the order the guards bite — or ``ok``."""
    if n_obs == 0:
        return "no_bars"
    if n_obs < min_obs:
        return "too_few_observations"
    return STATUS_OK if is_recent else "stale"


def sp500_members(d: dt.date) -> frozenset[str]:
    df = _gdb.read_df(SP500_SQL, {"code": imx.INDEX_CODE, "d": d})
    return frozenset(df["instrument_id"])


def percentile_table(adv: pd.DataFrame) -> pd.DataFrame:
    """One row per asset class: P10…P99 of ADV$ and the count at each candidate floor.

    pandas ``quantile`` (linear interpolation) on float64 — a statistic for the floor
    decision, printed to whole dollars; the stored ADV$ stays Decimal."""
    rows = []
    for cls, grp in adv.groupby("asset_class", sort=True):
        v = pd.Series(pd.to_numeric(grp["adv_median_60d"], errors="coerce")).dropna()
        q = v.quantile([p / 100 for p in PERCENTILES])
        row: dict[str, object] = {"asset_class": cls, "n_active": len(grp), "n_with_adv": len(v)}
        row |= {f"p{p}": float(q.iloc[i]) for i, p in enumerate(PERCENTILES)}
        row |= {f"ge_{f}": int((v >= f).sum()) for f in CANDIDATE_FLOORS_USD}
        rows.append(row)
    return pd.DataFrame(rows)


def _md(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def _usd(x: object) -> str:
    return f"${float(str(x)):,.0f}"


def render_report(
    as_of: dt.date,
    thr: dict[str, Decimal],
    bars: pd.DataFrame,
    table: pd.DataFrame,
    counts: Counter[str],
    written: int,
) -> str:
    """The FM's floor-decision report, in markdown — printed and saved on every run."""
    floor = thr.get(THRESHOLD_KEY)
    first, last, n_sessions = bars.iloc[0][["first_session", "last_session", "n_sessions"]]
    classes = list(table["asset_class"])
    reasons = ("no_bars", "too_few_observations", "stale")
    missing = [
        [
            cls,
            *(f"{counts[f'{cls}:{r}']:,d}" for r in reasons),
            f"{sum(counts[f'{cls}:{r}'] for r in reasons):,d}",
        ]
        for cls in classes
    ]
    parts = [
        f"# ADV$ distribution — EOD {as_of}",
        "",
        f"Produced by `scripts/global_market/build_universe_snapshot.py` at "
        f"{dt.datetime.now(ZoneInfo(gcal.NEW_YORK)).isoformat(timespec='seconds')} for the FM to "
        f"set `atlas_global.atlas_thresholds.liquidity_min_traded_value_usd` — the universe floor "
        f"(`universe_core.members`: ADV$ ≥ floor, NULL never passes). "
        + (
            "**The floor is unset**: this run wrote nothing and exited 2; set it from this table "
            "via `/admin/thresholds` or an `atlas_thresholds` insert with an `atlas_thresholds_audit` "
            "row (`changed_by`, `change_reason`) — never in code or a seed."
            if floor is None
            else f"Floor in force: **{_usd(floor)}**."
        ),
        "",
        f"**Definition.** ADV$ = median of raw `close × volume` over the last {n_sessions} distinct "
        f"sessions ({first} → {last}, within {U.LOOKBACK_CALENDAR_DAYS} calendar days of the EOD); "
        f"NULL below {int(thr[U.THRESHOLD_KEY_MIN_OBS])} observations "
        f"(`liquidity_min_observations_60d`) or when the last bar is outside the window's final "
        f"{int(thr[U.THRESHOLD_KEY_RECENCY])} sessions (`liquidity_recency_trading_days`).",
        "",
        "**Bars.** "
        + "; ".join(
            f"`source={s}`, `adjustment_source={a}` ({int(n):,d} bars in the window)"
            for s, a, n in bars[["source", "adjustment_source", "bars"]].itertuples(index=False)
        )
        + ". Stooq closes (`stooq:unknown`) are dividend-adjusted on an undocumented, moving basis "
        "(docs/global/phase1.md §1), so a trailing-60-session ADV$ on them sits within about 1 % of "
        "the raw-close figure: good enough for the floor decision, **not for display**.",
        "",
        "## Percentiles of ADV$ (USD)",
        "",
        _md(
            ["asset_class", "active", "with ADV$", *(f"P{p}" for p in PERCENTILES)],
            (
                [
                    r["asset_class"],
                    f"{r['n_active']:,d}",
                    f"{r['n_with_adv']:,d}",
                    *(_usd(r[f"p{p}"]) for p in PERCENTILES),
                ]
                for r in table.to_dict("records")
            ),
        ),
        "",
        "## Instruments at candidate floors (ADV$ ≥ floor)",
        "",
        _md(
            ["asset_class", *(_usd(f) for f in CANDIDATE_FLOORS_USD)],
            (
                [r["asset_class"], *(f"{r[f'ge_{f}']:,d}" for f in CANDIDATE_FLOORS_USD)]
                for r in table.to_dict("records")
            ),
        ),
        "",
        "## Instruments without ADV$ (why)",
        "",
        _md(
            [
                "asset_class",
                "no bars in window",
                f"< {int(thr[U.THRESHOLD_KEY_MIN_OBS])} observations",
                f"stale (last bar before the final {int(thr[U.THRESHOLD_KEY_RECENCY])} sessions)",
                "total",
            ],
            missing,
        ),
        "",
        "## Rows",
        "",
        f"- active `instrument_master` rows: {int(table['n_active'].sum()):,d} "
        + "("
        + ", ".join(f"{r['asset_class']} {r['n_active']:,d}" for r in table.to_dict("records"))
        + ")",
        f"- `universe_snapshot` rows written for {as_of}: {written:,d}"
        + (" (floor unset — exit 2)" if floor is None else ""),
        "",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None, help="default: eod_cutoff()")
    ap.add_argument("--report", type=Path, default=None, help="CSV of per-instrument outcomes")
    ap.add_argument(
        "--report-dir",
        type=Path,
        default=REPORTS_DIR,
        help=f"where adv_usd_<date>.md is saved (default: {REPORTS_DIR})",
    )
    args = ap.parse_args(argv)
    eod = args.eod or _gdb.eod_cutoff()

    as_of = anchor(eod)
    if as_of is None:
        print(f"  REFUSED: no SPY bar in {M}.ohlcv_daily at or before EOD {eod}; nothing written")
        return 2
    thr = thresholds()  # the two seeded keys raise KeyError by name if seed_thresholds.py never ran
    min_obs, recency = int(thr[U.THRESHOLD_KEY_MIN_OBS]), int(thr[U.THRESHOLD_KEY_RECENCY])
    floor = thr.get(THRESHOLD_KEY)

    adv = adv_frame(as_of, min_obs, recency)
    members = sp500_members(as_of)
    adv["in_sp500"] = adv["instrument_id"].isin(list(members))
    inside = U.members(adv, floor, frozenset()) if floor is not None else set()
    adv["in_universe"] = adv["instrument_id"].isin(list(inside))
    print(
        f"== {len(adv):,d} active instruments as of {as_of} (EOD {eod}): "
        f"{int(adv['adv_median_60d'].notna().sum()):,d} with ADV$ over {min_obs}+ of the last "
        f"{U.LOOKBACK_TRADING_DAYS} sessions, traded within {recency}; {len(members)} in the S&P 500 =="
    )

    report = Report(args.report, REPORT_COLUMNS, count_by=("asset_class", "status"))
    frame_cols = [c if c != "adv_usd_median_60d" else "adv_median_60d" for c in REPORT_COLUMNS]
    for row in adv[frame_cols].itertuples(index=False, name=None):
        report.add(*row)
    report.close()

    written = 0
    if floor is not None:
        out = adv.rename(columns={"adv_median_60d": "adv_usd_median_60d"}).assign(
            date=as_of,
            floor_usd=floor,
            aum_usd=None,
            basket_eligible=False,
            computed_at=dt.datetime.now(ZoneInfo(gcal.NEW_YORK)),
        )
        cols = [
            "date",
            "instrument_id",
            "in_universe",
            "in_sp500",
            "adv_usd_median_60d",
            "floor_usd",
            "aum_usd",
            "basket_eligible",
            "computed_at",
        ]
        written = _gdb.upsert_df(TGT, out.loc[:, cols], ["date", "instrument_id"])

    text = render_report(
        as_of,
        thr,
        _gdb.read_df(BARS_SQL, {"cutoff": as_of}),
        percentile_table(adv),
        report.counts,
        written,
    )
    print(text)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    path = args.report_dir / f"adv_usd_{as_of}.md"
    path.write_text(text)
    print(f"  saved {path} {report.where()}")
    if floor is None:
        # load_thresholds() reads only `is_active = TRUE`, so an inactive row and a missing row
        # look identical to it — and "is not in atlas_thresholds" would be a false trail when the
        # row is sitting right there. One extra query, only on this path, tells them apart.
        inactive = _gdb.scalar(INACTIVE_SQL, {"key": THRESHOLD_KEY})
        why = (
            f"{THRESHOLD_KEY} IS in {M}.atlas_thresholds but is_active is "
            f"{inactive!r}, and load_thresholds() reads only is_active = TRUE — activate it"
            if inactive is not None
            else f"{THRESHOLD_KEY} is not in {M}.atlas_thresholds — set the floor"
        )
        print(
            f"  REFUSED: {why} from the table above (/admin/thresholds, or an insert naming "
            "is_active plus an audit row); nothing written"
        )
        return 2
    by_class = adv.loc[adv["in_universe"]].groupby("asset_class").size()
    print(
        f"  universe: {len(inside):,d} / {len(adv):,d} active instruments at floor {_usd(floor)} "
        f"({', '.join(f'{c} {n:,d}' for c, n in by_class.items())}); {written:,d} rows upserted "
        f"into {TGT} for {as_of}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
