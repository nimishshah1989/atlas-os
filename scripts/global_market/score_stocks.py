#!/usr/bin/env python3
"""Score every in-universe S&P 500 member and rank it inside its SPY-weight cohort.

    python scripts/global_market/score_stocks.py                       # latest EOD
    python scripts/global_market/score_stocks.py --eod 2026-09-07 --report s.csv
    python scripts/global_market/score_stocks.py --dry-run             # print, write nothing

WHAT IS SCORED. The stocks the FM's universe cut leaves standing: ``universe_snapshot``'s
latest session with ``in_universe`` true, which for a stock ALREADY means "a current S&P 500
member above the ADV$ floor" (``build_universe_snapshot.py`` applies the membership rule; this
script does not re-apply it and must not, or the two would drift). A member without a
``technical_daily`` row on the anchor session has nothing to be scored on, so it gets no row —
but the run COUNTS AND NAMES those members, because "503 members, 470 scored" is the number
P2-D's done-condition is written against and a silently smaller denominator would hide it.

WHAT IS HONESTLY ABSENT. ``atlas.global_market.scoring.stock_lenses`` says it in full: the
technical lens is complete from ``technical_daily``; the fundamental lens is wired to
``stock_financials_pit`` through ``fundamentals.metrics`` and scores as soon as the FM has
locked the 37 US bands — until then it is NULL and every run prints the live S&P 500
cross-section to set them from; valuation needs the same feed plus its own bands, catalyst and
flow need ``filings_8k`` /
``insider_form4`` (P3-B), and policy is not ported. Those four columns stay NULL — never 0,
which would say a company is weak at something nobody has measured (rule #0). ``blend()``
renormalises over the lenses PRESENT, ``lenses_active`` records how many that was, and
``coverage_factor`` is the share of total lens weight they carry (0.30 of 1.00 tonight), so
the board can print "1 of 4 lenses" beside every score.

WHILE ONE LENS IS ACTIVE THE TIER LADDER CAPS AT MEDIUM. ``lens_conviction_highest_min_layers``
is 3 and ``..._high_min_layers`` is 2: a single-lens score cannot be HIGH however strong the
trend. That is the methodology working as designed — conviction means agreement between
independent reads, and there is only one read today.

COHORT = SPY-WEIGHT TERCILES (``docs/global/plan.md`` §B, phase2.md P2-D). India cuts deciles
within a market-cap cohort (``scripts/foundation/decile_core.py``); the US analogue is the
member's own weight in the index, ``index_membership.weight_frac`` on the anchor date, cut in
three: heaviest third ``mega``, middle ``large``, lightest ``mid`` — the three words
``chk_lens_scores_daily_cap_cohort`` allows. It is the better cohort here because it is the
index's OWN measure of the name's size, ingested weekly from the SSGA holdings file, not a
market cap this repo would have to derive.

A MEMBER WITH NO WEIGHT IS NOT DROPPED. ``weight_frac`` is nullable: an addition between the
issuer's weekly files can carry a membership interval and no weight yet. Such a name goes in
the LOWEST cohort — where a name too new to have a published weight belongs, and where it is
ranked against the smallest members rather than flattering itself against the largest — and
the run counts and lists it. Dropping it would silently shrink the S&P 500.

DECILES ARE NOT STORED. They are cut on read — ``ntile(10) OVER (PARTITION BY date, cap_cohort
ORDER BY composite)`` — exactly as India cuts them (``decile_core.py``: "read-only, nothing
materialised here"), over non-null composites only, and Leader is the top decile within the
cohort. A decile is a statement about a population on a date; materialising it would let a
stock's rank go stale while its score moved.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
from _cross_section import cross_section, print_cross_section
from _financials import GICS_FINANCIALS, financial_metrics
from _lens_inputs import lens_inputs
from _report import Report
from psycopg2.extras import Json

from atlas.db import load_thresholds
from atlas.global_market import calendar as gcal
from atlas.global_market import index_membership as imx
from atlas.global_market.fundamentals import cross_section as xsec
from atlas.global_market.fundamentals.metrics import Metrics
from atlas.global_market.providers.finra import ShortInterest
from atlas.global_market.scoring import blend, tiers_from_thresholds, weights_from_thresholds
from atlas.global_market.scoring.stock_catalyst import Filing, score_catalyst
from atlas.global_market.scoring.stock_catalyst import missing_keys as missing_catalyst_keys
from atlas.global_market.scoring.stock_flow import missing_keys as missing_flow_keys
from atlas.global_market.scoring.stock_flow import score_flow
from atlas.global_market.scoring.stock_lenses import (
    REACHABLE_KEYS,
    score_fundamental,
    score_technical,
)

M = _gdb.M
KEY = ["instrument_id", "date"]
_Q4 = Decimal("0.0001")  # lens_scores_daily.coverage_factor is numeric(6,4)

# The four WEIGHTED stock lenses — the ``lens_weight_*`` keys seed_thresholds.py writes and
# blend() renormalises over. Order is the blend's tie-break order and the board's render
# order. Valuation is deliberately absent: §B makes it an overlay (zone + multiplier), it
# carries no weight key, and blend() would KeyError on it — correctly.
LENSES = ("technical", "fundamental", "catalyst", "flow")

# Terciles of SPY weight, LIGHTEST FIRST so the index of a 0/1/2 tercile label is the cohort.
# The vocabulary is ddl/05_scores.sql's CHECK constraint, not this file's invention.
COHORTS_LIGHTEST_FIRST = ("mid", "large", "mega")
LIGHTEST_COHORT = COHORTS_LIGHTEST_FIRST[0]

COHORT_FROM_WEIGHT = "spy_weight"  # the member's own index weight put it in its cohort
COHORT_NO_WEIGHT = "no_weight_lowest_cohort"  # index_membership carried no weight_frac


# The distribution the FM sets the 37 bands from lives in ``fundamentals.cross_section``: it is
# pure (metric sets in, percentiles out) and the units it reports are the ones the lens adapter
# reads them back on, so the two cannot drift onto different scales.
METRIC_REPORT_COLUMNS = xsec.COLUMNS

STATUS_SCORED = "scored"
STATUS_NO_LENS = "no_lens_had_inputs"

REPORT_COLUMNS = (
    "symbol",
    "name",
    "cap_cohort",
    "weight_frac",
    "cohort_source",
    "technical",
    "tech_trend",
    "tech_rs",
    "composite",
    "conviction_tier",
    "lenses_active",
    "status",
)

ANCHOR_SQL = f"SELECT max(date) AS d FROM {M}.technical_daily WHERE date <= :cutoff"

# The scored set: in-universe stocks (which already means current S&P 500 members above the
# FM's ADV$ floor) with a metric row on the anchor session. The weight is a SCALAR SUBQUERY,
# not a join: a join can multiply a stock's row if its membership spells ever overlap, and a
# duplicated key makes the whole upsert fail ("ON CONFLICT DO UPDATE cannot affect row a
# second time"). A member whose weight has not been published yet still scores — NULL here is
# handled by cap_cohorts, not by dropping the name.
TARGETS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.name,
       t.ema_21, t.ema_50, t.ema_200, t.rsi_14, t.ret_1w,
       t.rs_1m_spy, t.rs_3m_spy, t.rs_6m_spy, t.rs_12m_spy,
       t.rs_1m_peer, t.rs_3m_peer, t.rs_6m_peer, t.rs_12m_peer,
       t.atr_14, t.bb_width, t.vol_ratio_30d, t.vol_ratio_60d, t.pos_52w,
       im.sector_gics,
       o.close_adj AS price,
       (SELECT mem.weight_frac FROM {M}.index_membership mem
         WHERE mem.instrument_id = im.instrument_id AND mem.index_code = :index_code
           AND mem.effective_from <= :anchor
           AND (mem.effective_to IS NULL OR mem.effective_to > :anchor)
         ORDER BY mem.effective_from DESC LIMIT 1) AS weight_frac
FROM {M}.instrument_master im
JOIN {M}.universe_snapshot u
  ON u.instrument_id = im.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
JOIN {M}.technical_daily t
  ON t.instrument_id = im.instrument_id AND t.date = :anchor
LEFT JOIN {M}.ohlcv_daily o
  ON o.instrument_id = im.instrument_id AND o.date = :anchor
WHERE im.asset_class = 'stock' AND im.is_active
"""

# The in-universe members the join above drops: no technical_daily row on the anchor session.
# They are not scored — there is nothing to score them on — but they ARE the difference between
# "503 members" and "n scored", so the run names them instead of quietly shrinking its own
# denominator (phase2.md P2-D: "≥95% of members scored").
MISSING_METRICS_SQL = f"""
SELECT im.symbol
FROM {M}.instrument_master im
JOIN {M}.universe_snapshot u
  ON u.instrument_id = im.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
WHERE im.asset_class = 'stock' AND im.is_active
  AND NOT EXISTS (SELECT 1 FROM {M}.technical_daily t
                   WHERE t.instrument_id = im.instrument_id AND t.date = :anchor)
ORDER BY im.symbol
"""


def missing_bands(th: Mapping[str, Decimal]) -> list[str]:
    """The fundamental bands ``atlas_global.atlas_thresholds`` does not carry yet.

    India's scorer falls back to India's own numbers for every one of them, so a partial set
    would score the S&P 500 on a methodology this market never approved — invisibly. The lens
    is therefore all-or-nothing: until the US bands are in the table, ``fundamental`` is NULL
    and the run says so (rule #1, rule #0).

    REACHABLE, not all 37: the three quick-ratio rungs grade an input no US filer supplies here
    (``stock_lenses.QUICK_RATIO_KEYS`` says why), and a band no code path reads cannot fall back
    to India's number. ``seed_thresholds.py --fundamental-bands`` cuts the rest from this run's
    own cross-section.
    """
    return sorted(REACHABLE_KEYS - set(th))


def anchor_date(cutoff: dt.date) -> dt.date:
    frame = _gdb.read_df(ANCHOR_SQL, {"cutoff": cutoff})
    day = frame["d"].iloc[0] if not frame.empty else None
    if day is None:
        raise SystemExit(
            f"technical_daily holds nothing at or before {cutoff} — run compute_technicals.py "
            "first; scoring reads its output, it does not recompute metrics"
        )
    return day


def cap_cohorts(weight_frac: pd.Series) -> pd.Series:
    """SPY-weight terciles as ``mega`` / ``large`` / ``mid``, one label per row.

    ``ntile(3)`` over the members that HAVE a weight — ranked first so ties cannot put the
    same weight on both sides of a cut, which is India's ``decile_core`` rule (``pd.qcut``
    over ``rank(method="first")``) at three buckets instead of ten. A member with no
    ``weight_frac`` lands in the lightest cohort; :func:`cohort_sources` reports it.

    Fewer than three weighted members cannot make three terciles — a database mid-backfill,
    never a real S&P 500 — so every row falls to the lightest cohort rather than the run
    inventing a cut. The caller prints the cohort sizes, so that state is visible.
    """
    ranked = weight_frac.rank(method="first", na_option="keep")
    present = ranked.notna()
    out = pd.Series(LIGHTEST_COHORT, index=weight_frac.index, dtype=object)
    if int(present.sum()) >= len(COHORTS_LIGHTEST_FIRST):
        # pd.Series() wrap for pyright, as in universe_core.members: qcut is typed as a broad
        # union and iterating the bare result costs ratchet errors.
        terciles = pd.Series(pd.qcut(ranked[present], len(COHORTS_LIGHTEST_FIRST), labels=False))
        out.loc[present] = [COHORTS_LIGHTEST_FIRST[int(t)] for t in terciles]
    return out


def cohort_sources(weight_frac: pd.Series) -> pd.Series:
    """Which rule put each row in its cohort — its own index weight, or the absence of one."""
    return pd.Series(
        [COHORT_NO_WEIGHT if _missing(w) else COHORT_FROM_WEIGHT for w in weight_frac],
        index=weight_frac.index,
        dtype=object,
    )


def _f(value: Any) -> float | None:
    """A database numeric as a float, or None. NaN is missing data, not a number."""
    if _missing(value):
        return None
    return float(value)


def _weight(value: Any) -> Decimal | None:
    """``weight_frac`` as the exact Decimal the database holds, or None.

    Never a float: the index weight is read back into the evidence trail and the report, and
    restating an exact numeric as an approximation of itself is how a number stops matching
    the row it came from. An all-NULL column comes back as float64 NaN, which is the same
    absence as None and must be written as an empty cell, not the word "nan".
    """
    return None if _missing(value) else Decimal(str(value))


def _missing(value: Any) -> bool:
    """None, or the NaN pandas puts where a database NULL was."""
    return value is None or (isinstance(value, float) and value != value)


def score_rows(
    frame: pd.DataFrame,
    anchor: dt.date,
    th: dict[str, Decimal],
    run_id: str,
    by_id: Mapping[str, Metrics] | None = None,
    bands_locked: bool = False,
    filings: Mapping[str, Sequence[Filing]] | None = None,
    short: Mapping[str, Sequence[ShortInterest]] | None = None,
) -> tuple[pd.DataFrame, list[list[Any]]]:
    """One ``lens_scores_daily`` row per stock, plus the per-stock report lines.

    ``by_id`` carries the point-in-time metric set per instrument and ``bands_locked`` says the
    US bands exist. Both are needed for a fundamental score: metrics without bands would be
    scored on India's cross-section, and bands without metrics have nothing to score.

    ``filings`` carries each stock's 8-K history for the catalyst lens. A stock absent from it
    has filed nothing in the window, which the scorer answers with ``None`` — no news is not bad
    news — rather than with a 50 that would claim the news netted out.
    """
    weights = weights_from_thresholds(th, LENSES, prefix="lens_weight_")
    tiers = tiers_from_thresholds(th)
    # Same all-or-nothing rule as the fundamental bands, for the same reason: a partial set
    # would weight the buckets by whatever happened to be seeded, invisibly.
    catalyst_ready = not missing_catalyst_keys(th)
    flow_ready = not missing_flow_keys(th)
    total_weight = sum(weights.values())
    now = dt.datetime.now(ZoneInfo(gcal.NEW_YORK))
    rows: list[dict[str, Any]] = []
    lines: list[list[Any]] = []

    # dict records, not itertuples: pandas resolves `.name` to the index name, and pyright
    # cannot see a DataFrame row's columns as attributes at all.
    for r in frame.to_dict("records"):
        weight = _weight(r["weight_frac"])
        technical = score_technical(
            ema_21=_f(r["ema_21"]),
            ema_50=_f(r["ema_50"]),
            ema_200=_f(r["ema_200"]),
            price=_f(r["price"]),
            ret_1w=_f(r["ret_1w"]),
            rsi_14=_f(r["rsi_14"]),
            rs_1m_spy=_f(r["rs_1m_spy"]),
            rs_3m_spy=_f(r["rs_3m_spy"]),
            rs_6m_spy=_f(r["rs_6m_spy"]),
            rs_12m_spy=_f(r["rs_12m_spy"]),
            rs_1m_peer=_f(r["rs_1m_peer"]),
            rs_3m_peer=_f(r["rs_3m_peer"]),
            rs_6m_peer=_f(r["rs_6m_peer"]),
            rs_12m_peer=_f(r["rs_12m_peer"]),
            atr_14=_f(r["atr_14"]),
            bb_width=_f(r["bb_width"]),
            vol_ratio_30d=_f(r["vol_ratio_30d"]),
            vol_ratio_60d=_f(r["vol_ratio_60d"]),
            pos_52w=_f(r["pos_52w"]),
            th=th,
        )
        found = (by_id or {}).get(str(r["instrument_id"]))
        fundamental = (
            score_fundamental(
                roe=found.roe,
                roce=found.roce,
                operating_margin=found.operating_margin,
                net_margin=found.net_margin,
                revenue_growth=found.revenue_growth,
                eps_growth=found.eps_growth,
                debt_to_equity=found.debt_to_equity,
                current_ratio=found.current_ratio,
                th=th,
            )
            if found is not None and bands_locked
            else None
        )
        # An absent lens is None, not 0 — a company is not weak on something we did not
        # measure. catalyst and flow have no producer at all (P3-B); fundamental has its feed
        # and waits only on the FM's bands.
        catalyst = (
            score_catalyst(filings.get(str(r["instrument_id"]), ()), anchor, th)
            if filings is not None and catalyst_ready
            else None
        )
        flow = (
            score_flow(short.get(str(r["instrument_id"]), ()), anchor, th)
            if short is not None and flow_ready
            else None
        )
        lenses: dict[str, Decimal | None] = {
            "technical": technical.value,
            "fundamental": None if fundamental is None else fundamental.value,
            "catalyst": None if catalyst is None else catalyst.value,
            "flow": None if flow is None else flow.value,
        }
        # NO ``order=`` HERE. blend()'s fourth argument is the CONVICTION-TIER ladder
        # (HIGHEST → HIGH → MEDIUM → WATCH → BELOW_THRESHOLD) and its default is the right
        # one; a lens tuple passed there raises `KeyError: blend: tiers has no entry for
        # ['technical', ...]` on the first scored row. The float-summation order India parity
        # depends on comes from ``lenses``' OWN iteration order, which is LENSES above — the
        # docstring's "pass the canonical lens order" means the dict, not this argument.
        result = blend(lenses, weights, tiers)
        present_weight = sum(
            (w for name, w in weights.items() if lenses[name] is not None), Decimal(0)
        )
        # Quantised to the column's own scale (numeric(6,4)). Decimal division carries an
        # exponent from its operands — `Decimal(0) / Decimal("1.00")` is `Decimal("0E+2")`,
        # which stores correctly and reads like a mistake in every log and CSV that shows it.
        coverage = (present_weight / total_weight).quantize(_Q4) if total_weight else None
        status = STATUS_SCORED if result.composite is not None else STATUS_NO_LENS

        rows.append(
            {
                "instrument_id": r["instrument_id"],
                "date": anchor,
                "asset_class": "stock",
                "technical": technical.value,
                **dict(technical.subs),
                "fundamental": None if fundamental is None else fundamental.value,
                **({} if fundamental is None else dict(fundamental.subs)),
                "catalyst": None if catalyst is None else catalyst.value,
                **({} if catalyst is None else dict(catalyst.subs)),
                "flow": None if flow is None else flow.value,
                **({} if flow is None else dict(flow.subs)),
                "composite": result.composite,
                "conviction_tier": result.conviction_tier,
                "cap_cohort": r["cap_cohort"],
                "lenses_active": result.lenses_active,
                "coverage_factor": coverage,
                "evidence": Json(
                    {
                        "cap_cohort": r["cap_cohort"],
                        "cohort_source": r["cohort_source"],
                        # str(): a Decimal weight is not JSON, and a float would restate an
                        # exact database numeric as an approximation of itself.
                        "weight_frac": None if weight is None else str(weight),
                        "technical": technical.evidence,
                        **({} if catalyst is None else {"catalyst": catalyst.evidence}),
                        **({} if flow is None else {"flow": flow.evidence}),
                        "blend": result.evidence,
                    }
                ),
                "compute_run_id": run_id,
                # lens_scores_daily.computed_at has no DDL default (unlike etf_scores_daily):
                # unwritten it lands NULL, and a score row that cannot say when it was
                # computed is not a journal entry.
                "computed_at": now,
            }
        )
        lines.append(
            [
                r["symbol"],
                str(r["name"])[:48],
                r["cap_cohort"],
                weight,
                r["cohort_source"],
                technical.value,
                technical.subs["tech_trend"],
                technical.subs["tech_rs"],
                result.composite,
                result.conviction_tier,
                result.lenses_active,
                status,
            ]
        )
    return pd.DataFrame(rows), lines


def print_summary(table: pd.DataFrame, frame: pd.DataFrame, anchor: dt.date, report: Report) -> int:
    """The run's own account of itself: how many scored, the cohorts, what each cohort is
    worth, and the count per outcome — printed whether or not ``--report`` asked for a CSV,
    because a run that cannot say how many names it failed on is not a glass box."""
    scored = int(table["composite"].notna().sum())
    no_weight = int((frame["cohort_source"] == COHORT_NO_WEIGHT).sum())
    print(
        f"[score_stocks] anchor={anchor} stocks={len(table):,d} scored={scored:,d} "
        f"cohorts={table['cap_cohort'].nunique()} without_index_weight={no_weight:,d}"
    )
    # Heaviest cohort first, the way a reader reads the index.
    for cohort in reversed(COHORTS_LIGHTEST_FIRST):
        rows = table.loc[table["cap_cohort"] == cohort]
        if rows.empty:
            continue
        # "n/a" where no member of the cohort scored: 0.00 there would read as a score, and
        # taking a median of nothing is a numpy warning on the nightly's console.
        in_cohort = int(rows["composite"].notna().sum())
        shown = f"{float(rows['composite'].median()):.2f}" if in_cohort else "n/a"
        print(
            f"    {cohort:<6} n={len(rows):>4,d}  scored={in_cohort:>4,d}  median composite={shown}"
        )
    outcomes = " ".join(f"{k}={v:,d}" for k, v in sorted(report.counts.items()))
    print(f"    outcomes: {outcomes} {report.where()}")
    if no_weight:
        symbols = list(frame.loc[frame["cohort_source"] == COHORT_NO_WEIGHT, "symbol"])
        print(
            f"    {no_weight:,d} member(s) with no index_membership.weight_frac on {anchor} "
            f"placed in '{LIGHTEST_COHORT}': {', '.join(map(str, symbols[:10]))}"
            + (" …" if no_weight > 10 else "")
        )
    return scored


def print_unmeasured(anchor: dt.date) -> int:
    """The in-universe members with no metric row on ``anchor``, counted and named.

    They cannot be scored, and they are also not a failure of this script — they are a gap in
    ``compute_technicals``' output on this session, and saying which names they are is what
    turns "why is it 470 and not 503" into a one-line answer.
    """
    missing = list(_gdb.read_df(MISSING_METRICS_SQL, {"anchor": anchor})["symbol"])
    if missing:
        print(
            f"    {len(missing):,d} in-universe member(s) have no technical_daily row on "
            f"{anchor} and are not scored: {', '.join(map(str, missing[:10]))}"
            + (" …" if len(missing) > 10 else "")
        )
    return len(missing)


def run(
    *,
    eod: dt.date | None,
    dry_run: bool,
    report: Report,
    metric_report: Report | None = None,
) -> dict[str, object]:
    run_id = str(uuid.uuid4())
    cutoff = eod or _gdb.eod_cutoff()
    anchor = anchor_date(cutoff)
    th = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())

    frame = _gdb.read_df(
        TARGETS_SQL,
        {"anchor": anchor, "index_code": imx.INDEX_CODE},
        coerce_float=False,  # weight_frac stays Decimal: an exact index weight, not a float
    )
    if frame.empty:
        raise SystemExit(
            f"no in-universe stock has a technical_daily row on {anchor}. Run "
            "build_universe_snapshot.py (writes in_universe, and for a stock that already "
            "means current S&P 500 membership) and compute_technicals.py first — this script "
            "scores what those two produced."
        )
    frame["cap_cohort"] = cap_cohorts(pd.Series(frame["weight_frac"]))
    frame["cohort_source"] = cohort_sources(pd.Series(frame["weight_frac"]))

    financial_ids = {
        str(r["instrument_id"])
        for r in frame.to_dict("records")
        if r.get("sector_gics") == GICS_FINANCIALS
    }
    by_id = financial_metrics(anchor, financial_ids)
    missing = missing_bands(th)
    events = lens_inputs(anchor, th)
    print(
        f"[score_stocks] fundamentals: {len(by_id):,d} of {len(frame):,d} name(s) have a full "
        f"trailing-twelve-month window as of {anchor}; {len(financial_ids)} financial(s)"
    )
    print_cross_section(cross_section(by_id, metric_report), missing)

    for line in events.lines(M, len(frame)):
        print(f"[score_stocks] {line}")
    table, lines = score_rows(
        frame, anchor, th, run_id, by_id, not missing, events.filings, events.short
    )
    for line in lines:
        report.add(*line)
    scored = print_summary(table, frame, anchor, report)
    print_unmeasured(anchor)

    if dry_run:
        print("[score_stocks] --dry-run: nothing written")
        return {"stocks": len(table), "scored": scored, "written": 0}

    written = _gdb.upsert_df(f"{M}.lens_scores_daily", table, KEY)
    print(f"[score_stocks] wrote {written:,d} lens_scores_daily row(s) for {anchor}")
    return {"stocks": len(table), "scored": scored, "written": written}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the cohorts, write nothing")
    ap.add_argument(
        "--report", type=Path, default=None, help="per-stock CSV: lenses, cohort and composite"
    )
    ap.add_argument(
        "--report-metrics",
        type=Path,
        default=None,
        help="CSV of the S&P 500 fundamental cross-section — the distribution the FM sets bands on",
    )
    return ap


def main() -> None:
    args = parser().parse_args()
    # Always a Report, with or without a path: without one it writes nothing and still counts,
    # so every run can print how many names ended in each outcome (`_report.Report`).
    report = Report(args.report, REPORT_COLUMNS)
    metric_report = Report(args.report_metrics, METRIC_REPORT_COLUMNS, count_by=("metric",))
    try:
        run(eod=args.eod, dry_run=args.dry_run, report=report, metric_report=metric_report)
    finally:
        metric_report.close()
        report.close()


if __name__ == "__main__":
    main()
