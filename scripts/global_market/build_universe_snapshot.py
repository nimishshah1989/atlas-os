#!/usr/bin/env python3
"""Daily universe-membership journal → ``atlas_global.universe_snapshot``, and the ADV$ table
the FM sets the liquidity floor from.

    python scripts/global_market/build_universe_snapshot.py --eod 2026-09-03 --report universe.csv
    python scripts/global_market/build_universe_snapshot.py --eod 2026-09-03 --report-dir /tmp/atlas-logs

One row per ACTIVE instrument (stock or ETF) per session, whether or not it is in the universe,
with the ADV$ that produced the decision — India's ``scripts/foundation/build_universe_snapshot.py``
in USD. The LIQUIDITY rule is ``universe_core.members`` VERBATIM (a Decimal floor is
currency-agnostic); the window is India's ``adv_frame`` logic on ``ohlcv_daily`` — copied, not
imported, because that function is bound to India's ``_db`` and ``ohlcv_stock`` — with ONE
difference: the sessions are SPY's bars (the platform's calendar, membership-by-presence), not
the table's distinct dates. Stooq carries stray bars on exchange holidays (Memorial Day,
Juneteenth and 3 July 2026 in the FM's archive) and a holiday is not a session.

Two FM rules of 2026-09-06 sit AROUND that predicate — never inside it, so India's
``universe_core`` is untouched:

* a STOCK must also be an S&P 500 member on the date (``docs/global/plan.md``: "scored =
  current members"). ``in_sp500`` is computed per date from ``index_membership``, so a trailing
  member is still ``in_universe`` on the dates it was one — history is not special-cased.
* an ETF must also be neither leveraged nor inverse
  (``atlas.global_market.classify.leverage_flags`` over the instrument name — the ONLY L0 fact
  Phase 1 has for all 5,656 of them; Phase 2 supersedes it with holdings and
  ``derivatives_share``). The rules run on ETFs only: a company can be called 10x Genomics.

Every active instrument still gets a ROW either way — survivorship honesty and the journal
contract are unchanged. Only ``in_universe`` narrows, and ``exclusion_reason`` names the reason
— in the TABLE, not only in ``--report``: the board reads Postgres directly, so a reason that
lives in a run's CSV is a reason nobody can see.

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
* ``exclusion_reason`` — NULL when ``in_universe``, else the FIRST reason the row is out:
  ``universe_status``'s answer, or ``below_floor`` when it says ``ok`` (the row cleared every
  structural rule and failed only the liquidity floor). The seven PARTITION the excluded set —
  asserted on the frame before the upsert, and again by the DDL's two CHECKs on every INSERT.

THE FLOOR IS THE FM'S, NOT THE CODE'S. ``liquidity_min_traded_value_usd`` was set to $1,000,000
on 2026-09-06 from the REAL distribution this script printed
(``docs/global/reports/adv_usd_2026-09-03.md``) and is seeded from that decision
(``seed_thresholds.py``). The refusal path is unchanged and is not a placeholder: on any
database where the row is missing or inactive, the run prints and saves the ADV$ percentile
table to ``<report-dir>/adv_usd_<date>.md``, writes nothing and exits 2 — so a half-provisioned
schema fails loudly instead of cutting the universe on an invented floor. With the floor in
force the rows are upserted (idempotent, ``computed_at`` moves) and the counts per exclusion
reason are printed. ``--report`` lists every instrument's outcome — no bars / too few
observations / stale / not_sp500 / leveraged / inverse / ok, plus the leverage rule that
fired — in a CSV.
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
from atlas.global_market.classify import CLEAN, LeverageFlags, leverage_flags

if TYPE_CHECKING:
    from scripts.foundation import universe_core as U
else:
    import universe_core as U

M = _gdb.M
TGT = f"{M}.universe_snapshot"
THRESHOLD_KEY = "liquidity_min_traded_value_usd"  # the FM's floor: a table row, never a literal
REPORTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "global" / "reports"
# The FM's question, not a methodology number: the percentiles reported and the candidate
# floors counted (docs/global/phase1.md P1-E). The floor itself comes from atlas_thresholds.
PERCENTILES = (10, 25, 50, 75, 90, 95, 99)
CANDIDATE_FLOORS_USD = (500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000)
STATUS_OK = "ok"
# The FM's two structural rules (2026-09-06), as report statuses. An instrument out on one of
# these is listed with its reason instead of vanishing into a smaller universe count.
STATUS_NOT_SP500 = "not_sp500"
STATUS_LEVERAGED = "leveraged"
STATUS_INVERSE = "inverse"
STATUS_BELOW_FLOOR = "below_floor"
ADV_REASONS = ("no_bars", "too_few_observations", "stale")  # the ladder, in the order it bites
# Everything ``exclusion_reason`` may hold, and everything ddl/05_scores.sql's CHECK allows.
EXCLUSION_REASONS = (
    *ADV_REASONS,
    STATUS_NOT_SP500,
    STATUS_LEVERAGED,
    STATUS_INVERSE,
    STATUS_BELOW_FLOOR,
)
REPORT_COLUMNS = (
    "asset_class",
    "symbol",
    "instrument_id",
    "status",
    "n_obs",
    "last_date",
    "adv_usd_median_60d",
    "in_sp500",
    "leverage_rule",
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
    SELECT im.instrument_id::text AS instrument_id, im.symbol, im.asset_class, im.name,
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


def universe_status(adv_status: str, asset_class: str, in_sp500: bool, flags: LeverageFlags) -> str:
    """The FIRST reason an instrument is out of the universe, or ``ok``.

    The ADV$ ladder bites first: no signal is no signal, whatever the instrument is. The two
    2026-09-06 rules follow, ETF flags last (an UltraShort ETF is both, and is reported as
    ``leveraged``). Below the floor stays ``ok`` here — that is the ADV$ column's own story,
    and it moves whenever the FM moves the floor; these three do not."""
    if adv_status != STATUS_OK:
        return adv_status
    if asset_class == "stock" and not in_sp500:
        return STATUS_NOT_SP500
    if asset_class == "etf" and flags.leveraged:
        return STATUS_LEVERAGED
    if asset_class == "etf" and flags.inverse:
        return STATUS_INVERSE
    return STATUS_OK


def exclusions(adv: pd.DataFrame) -> dict[str, pd.Series]:
    """The FM's 2026-09-06 rules, one boolean mask per reason. NOT disjoint — an UltraShort ETF
    is leveraged AND inverse — so the counts never sum to the total; their union is what
    ``in_universe`` subtracts from the liquidity predicate."""
    etf, stock = adv["asset_class"] == "etf", adv["asset_class"] == "stock"
    return {
        STATUS_NOT_SP500: stock & ~adv["in_sp500"],
        STATUS_LEVERAGED: etf & adv["leveraged"],
        STATUS_INVERSE: etf & adv["inverse"],
    }


def exclusion_reasons(status: pd.Series, in_universe: pd.Series) -> pd.Series:
    """The ``exclusion_reason`` column: the ONE reason each excluded row is out, NULL for a
    row that is in. ``universe_status`` has already named the first STRUCTURAL reason; a row
    it calls ``ok`` that is still out cleared all three and failed only the liquidity floor —
    which is why ``below_floor`` is derived HERE, at the write site, from the liquidity mask:
    the floor moves whenever the FM moves it and those three rules do not. The result
    PARTITIONS the excluded set, one of :data:`EXCLUSION_REASONS` each (:func:`assert_partition`)."""
    return status.where(status != STATUS_OK, STATUS_BELOW_FLOOR).where(~in_universe, None)


def assert_partition(adv: pd.DataFrame) -> None:
    """Refuse to write a frame whose reasons do not partition the excluded set — checked on
    the frame, before the upsert, so a later change to the ladder stops the run here instead
    of publishing a row the board can only render as a bare "excluded". The DDL's two CHECKs
    say the same to anyone else's INSERT; this says it while the diagnosis is still in hand."""
    reason, inside = adv["exclusion_reason"], adv["in_universe"]
    unexplained = list(adv.loc[~inside & reason.isna(), "symbol"])
    explained = list(adv.loc[inside & reason.notna(), "symbol"])
    unknown = sorted(set(reason.dropna()) - set(EXCLUSION_REASONS))
    if unexplained or explained or unknown:
        raise RuntimeError(
            f"exclusion_reason does not partition the excluded rows — nothing written: "
            f"{len(unexplained)} out with no reason {unexplained[:5]}; {len(explained)} in "
            f"the universe with one {explained[:5]}; outside {EXCLUSION_REASONS}: {unknown}"
        )


def reason_section(adv: pd.DataFrame) -> list[str]:
    """The report's ``exclusion_reason`` table: what the journal now says about every row."""
    counts = {r: int((adv["exclusion_reason"] == r).sum()) for r in EXCLUSION_REASONS}
    return [
        "## Why each excluded instrument is out (`universe_snapshot.exclusion_reason`)",
        "",
        "The STORED reason, one per row: the ADV$ ladder first, then the FM's rules, then the "
        "floor. The table above counts every instrument a rule TOUCHES (overlapping, and "
        "independent of the floor); these count the rows each reason was the FIRST to take "
        "out, so they PARTITION the excluded set and sum to it.",
        "",
        _md(
            ["`exclusion_reason`", "instruments"],
            [
                *([f"`{r}`", f"{n:,d}"] for r, n in counts.items()),
                ["NULL (in the universe)", f"{int(adv['exclusion_reason'].isna().sum()):,d}"],
            ],
        ),
        "",
    ]


def exclusion_line(adv: pd.DataFrame, liquid: pd.Series) -> str:
    """One line per run: what each FM rule took out and what the floor took out on its own, in
    the report's own words — so a universe that shrinks overnight says WHY on the console."""
    m = exclusions(adv)
    both = int((m[STATUS_LEVERAGED] & m[STATUS_INVERSE]).sum())
    counts = ", ".join(f"{int(v.sum()):,d} {k}" for k, v in m.items())
    return (
        f"excluded: {counts} (of which {both:,d} both); "
        f"{int((~liquid).sum()):,d} below the floor or without an ADV$"
    )


def structure_flags(adv: pd.DataFrame) -> list[LeverageFlags]:
    """``leverage_flags`` per row — ETFs only. A stock's name is a company's name, and one of
    them is 10x Genomics; its universe test is S&P 500 membership, never a word."""
    return [
        leverage_flags(str(name)) if cls == "etf" and name is not None else CLEAN
        for cls, name in zip(adv["asset_class"], adv["name"], strict=True)
    ]


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
    adv: pd.DataFrame,
) -> str:
    """The FM's floor-decision report, in markdown — printed and saved on every run."""
    floor = thr.get(THRESHOLD_KEY)
    first, last, n_sessions = bars.iloc[0][["first_session", "last_session", "n_sessions"]]
    classes = list(table["asset_class"])
    missing = [
        [
            cls,
            *(f"{counts[f'{cls}:{r}']:,d}" for r in ADV_REASONS),
            f"{sum(counts[f'{cls}:{r}'] for r in ADV_REASONS):,d}",
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
        "## Excluded by the FM's universe rules (2026-09-06)",
        "",
        "Independent of the floor, and not disjoint — an UltraShort ETF is both. Every one of "
        "these still has a `universe_snapshot` row; only `in_universe` is false, and "
        "`--report` names the rule.",
        "",
        _md(
            ["`--report` status", "instruments"],
            ([f"`{k}`", f"{int(v.sum()):,d}"] for k, v in exclusions(adv).items()),
        ),
        "",
        *(() if floor is None else reason_section(adv)),
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
    flags = structure_flags(adv)
    adv["leveraged"] = [f.leveraged for f in flags]
    adv["inverse"] = [f.inverse for f in flags]
    adv["leverage_rule"] = [f.rule for f in flags]
    adv["status"] = [
        universe_status(s, c, m, f)
        for s, c, m, f in zip(
            adv["status"], adv["asset_class"], adv["in_sp500"], flags, strict=True
        )
    ]
    # The liquidity predicate is India's, VERBATIM; the FM's two rules are filters around it.
    inside = U.members(adv, floor, frozenset()) if floor is not None else set()
    # pd.Series() wrap for pyright, as in universe_core.members: isin is typed as a broad union.
    liquid = pd.Series(adv["instrument_id"].isin(list(inside)))
    out = exclusions(adv)
    adv["in_universe"] = liquid & ~(
        out[STATUS_NOT_SP500] | out[STATUS_LEVERAGED] | out[STATUS_INVERSE]
    )
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
        # Only with a floor in force: without one nothing is written, and nothing is below it.
        # pd.Series() wraps for pyright, as in universe_core.members: a frame column is typed
        # as a broad union, and the bare values cost ratchet errors.
        adv["exclusion_reason"] = exclusion_reasons(
            pd.Series(adv["status"]), pd.Series(adv["in_universe"])
        )
        assert_partition(adv)
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
            "exclusion_reason",
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
        adv,
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
    n_in = int(adv["in_universe"].sum())
    print(
        f"  universe: {n_in:,d} / {len(adv):,d} active instruments at floor {_usd(floor)} "
        f"({', '.join(f'{c} {n:,d}' for c, n in by_class.items())}); {written:,d} rows upserted "
        f"into {TGT} for {as_of}"
    )
    print(f"  {exclusion_line(adv, liquid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
