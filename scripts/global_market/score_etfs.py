#!/usr/bin/env python3
"""Score every in-universe ETF and rank it against funds that do the same job.

    python scripts/global_market/score_etfs.py                       # latest EOD
    python scripts/global_market/score_etfs.py --eod 2026-09-07 --report s.csv
    python scripts/global_market/score_etfs.py --dry-run             # print, write nothing

WHAT THIS ANSWERS. Not "is this fund good" — "of the funds that do this job, which ones are
working". A gold-miners fund and a Treasury fund and an S&P tracker have nothing to say to each
other, and a league table containing all three is a league table of nothing. So every fund is
scored on its own merits and then RANKED INSIDE ITS PEER GROUP.

PEER GROUP = asset class × strategy, both from ``etf_classification`` (written by
classify_etfs.py from the fund's own registered name). ``equity:sector``, ``equity:country``,
``fixed_income:fixed_income``, ``alternative:options_income``, and so on. A group with fewer
than ``peer_group_min_members`` funds cannot support a percentile — five funds have no
quintiles — so those funds fall back to their ASSET GROUP (``equity``, ``fixed_income``, …)
and the row records which was used, because a reader comparing two funds needs to know they
were measured against different fields.

WHAT IS SCORED, AND WHAT IS HONESTLY ABSENT. ``atlas.global_market.scoring.etf_lenses`` says
it in full: technical and risk are complete from ``technical_daily``; cost_liquidity has three
of its four sub-scores — ADV$, AUM (``ingest_nport.py`` fills ``etf_meta.aum_usd``, and leaves
it NULL for a multi-class series, where the filed net assets are the whole fund's and not this
share class's) and concentration (``build_exposures.py`` fills ``etf_exposure_daily.top10_w``
from the latest holdings snapshot at or before the anchor). Expense waits on an issuer feed;
flow and quality have no producer at all yet. ``blend()`` renormalises over the lenses PRESENT, ``lenses_active``
records how many there were, and the board prints "n of 5 lenses" beside every score. A lens
with no data is NULL — never zero, which would say the fund is bad at something we did not
measure (rule #0).

WHILE ONE LENS IS ACTIVE THE TIER LADDER CAPS AT MEDIUM. ``lens_conviction_highest_min_layers``
is 3 and ``..._high_min_layers`` is 2: a single-lens score cannot be HIGH however strong it is.
That is the methodology working as designed, not a defect — conviction means agreement between
independent reads, and there is only one read today.

GEARED AND INVERSE FUNDS ARE SCORED, AND MUST NOT BE OFFERED. This paragraph used to say they
were never scored, on the strength of a join to ``universe_snapshot.in_universe`` that the FM
himself asked to be removed ("we should score all the funds, irrespective… from a scoring point
of view, we have coverage that is close to 100%"). Scoring them is right and the docstring simply
went stale: measuring a fund is not the same as putting it forward.

What keeps a 3x fund out of a ranking is therefore NOT this script. It is two separate things:
``peer_group`` below, which ranks geared funds only against each other, and
``universe_snapshot.in_universe``, which every consumer — the board's country, theme and sector
rankings, and every basket — cuts its population over. The same cut removes everything below the
FM's ADV$ floor. A consumer that ranks on ``composite`` alone will offer him a bear fund as a way
to own the thing it bets against, which is exactly what the board did until 2026-09-10.

DECILES ARE NOT STORED. They are cut on read — ``ntile(10) OVER (PARTITION BY date,
peer_group ORDER BY composite)`` — exactly as India cuts them within cap cohort
(``scripts/foundation/decile_core.py``: "read-only, nothing materialised here"). A decile is a
statement about a population on a date; materialising it would let a fund's rank go stale
while its score moved.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
from _report import Report
from psycopg2.extras import Json

from atlas.db import load_thresholds
from atlas.global_market.scoring import blend, tiers_from_thresholds, weights_from_thresholds
from atlas.global_market.scoring.etf_lenses import (
    score_cost_liquidity,
    score_risk,
    score_technical,
)

M = _gdb.M
KEY = ["instrument_id", "date"]

# The five lens names ddl/05_scores.sql and the etf_lens_weight_* keys share. Order is the
# blend's tie-break order and the order the board renders them in.
LENSES = ("technical", "risk", "cost_liquidity", "flow", "quality")

STATUS_SCORED = "scored"
STATUS_NO_CLASS = "no_classification"
STATUS_NO_LENS = "no_lens_had_inputs"

REPORT_COLUMNS = (
    "symbol",
    "name",
    "peer_group",
    "peer_n",
    "grouped_by",
    "technical",
    "risk",
    "cost_liquidity",
    "composite",
    "conviction_tier",
    "lenses_active",
    "status",
)

ANCHOR_SQL = f"SELECT max(date) AS d FROM {M}.technical_daily WHERE date <= :cutoff"

# The scored set: EVERY active classified ETF with a metric row on the anchor session. Liquidity
# is not a gate here — it is a lens input (`cost_liquidity` scores ADV$ and AUM directly) and a
# basket rule, which is where a floor belongs. An INNER join on the classification is deliberate:
# a fund we cannot group cannot be ranked, and giving it a score with no peers to read it against
# would be worse than leaving it out and saying so in the report.
TARGETS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.name,
       c.asset_class, c.strategy, c.leveraged, c.inverse,
       coalesce(u.in_universe, false) AS in_universe,
       t.ema_21, t.ema_50, t.ema_200, t.rsi_14, t.ret_1w, t.ret_6m,
       t.rs_3m_spy, t.rs_6m_spy, t.rs_12m_spy,
       t.vol_63d_ann, t.mdd_12m, t.downside_dev_63d, t.beta_spy_252,
       t.adv_usd_60d_median,
       m.aum_usd,
       e.top10_w,
       o.close_adj AS price
FROM {M}.instrument_master im
-- LEFT, and with no `AND u.in_universe`: the universe is what a fund can be TRADED in, not what
-- it may be measured. The FM, reversing the earlier cut: "we should score all the funds,
-- irrespective… if we have the data for all those funds… that way we have coverage that is close
-- to 100%." So `in_universe` rides along as an attribute — baskets and the board still read it —
-- and the gate below is the only one left.
LEFT JOIN {M}.universe_snapshot u
  ON u.instrument_id = im.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
-- THE REAL GATE, and it always was: an INNER join on the metric row. A fund with no technicals on
-- the anchor session cannot be scored by any lens, which is exactly the FM's own condition.
JOIN {M}.etf_classification c
  ON c.instrument_id = im.instrument_id AND c.version = 1
JOIN {M}.technical_daily t
  ON t.instrument_id = im.instrument_id AND t.date = :anchor
LEFT JOIN {M}.etf_meta m
  ON m.instrument_id = im.instrument_id
-- The LATEST exposure snapshot at or before the anchor, never a join on every one of them:
-- N-PORT is quarterly, so a fund has several, and a plain join would multiply its row and
-- fail the upsert ("ON CONFLICT DO UPDATE cannot affect row a second time").
LEFT JOIN LATERAL (
    SELECT x.top10_w FROM {M}.etf_exposure_daily x
     WHERE x.instrument_id = im.instrument_id AND x.as_of_date <= :anchor
     ORDER BY x.as_of_date DESC LIMIT 1
) e ON true
LEFT JOIN {M}.ohlcv_daily o
  ON o.instrument_id = im.instrument_id AND o.date = :anchor
WHERE im.asset_class = 'etf' AND im.is_active
"""


def anchor_date(cutoff: dt.date) -> dt.date:
    frame = _gdb.read_df(ANCHOR_SQL, {"cutoff": cutoff})
    day = frame["d"].iloc[0] if not frame.empty else None
    if day is None:
        raise SystemExit(
            f"technical_daily holds nothing at or before {cutoff} — run compute_technicals.py "
            "first; scoring reads its output, it does not recompute metrics"
        )
    return day


def assign_groups(frame: pd.DataFrame, min_members: int) -> pd.DataFrame:
    """Add ``peer_group``, ``asset_group``, ``grouped_by`` and ``peer_n``.

    ``peer_group`` is the group a fund is actually RANKED in: its own asset-class × strategy
    when that group is big enough to cut percentiles, otherwise its asset class. ``grouped_by``
    records which happened, so the board can say "ranked among 34 sector funds" or "ranked
    among 210 equity funds (too few sector-thematic peers)" rather than implying a precision
    the group size does not support.

    THE FALLBACK CHAIN HAS AN END, and the first live run found it. Six in-universe
    multi-asset funds against a floor of eight: the original code fell back to the asset class
    unconditionally and handed gate C a group of six to rank in. There is nowhere further to
    fall that means anything — a multi-asset fund ranked against equity sector funds is a
    league table of nothing, which is the whole reason peer groups exist. So such a fund gets
    NO peer group: ``peer_group`` is None and ``grouped_by`` says ``unranked``.

    THE FALLBACK GROUP IS THE FUNDS THAT FELL BACK, not every fund of that asset class, and
    its OWN size is what decides. This is not obvious and a test caught it: twelve
    equity-sector funds and two equity-thematic ones make an asset class of fourteen, but the
    two thematic funds fall into a group containing only each other, because the twelve are
    ranked in ``equity:sector``. Sizing the fallback by the asset class would have passed them
    straight back into a group of two — the very thing this function exists to prevent.

    The cost is deliberate: a fund can be unranked while its asset class is large. Ranking it
    against all fourteen would be more useful and is the obvious next step, but it needs a
    ranking POPULATION stored apart from the group LABEL, since the gate and the board both
    count rows by label today. That is a schema change, not a line here. Conservative is the
    safe direction: an absent rank is honest, an overclaimed one is not.

    An unranked fund is not a dropped fund. It is scored and shown under its asset group; what
    it does not get is a rank, because a rank is a statement about a population and there is
    no population. It also falls out of the peer percentile for free — pandas drops a NaN
    group key — so that sub-score is absent rather than invented and the composite
    renormalises over the rest, as it does for any missing input. Its RISK percentiles
    survive: those are cut within the asset group by design (``add_percentiles``), and an
    asset group exists even when it is too small to rank in.
    """
    out = frame.copy()
    # GEARED AND INVERSE FUNDS ARE SCORED, AND RANKED ONLY AGAINST EACH OTHER.
    #
    # The FM opened the scoring gate: "we should score all the funds, irrespective… from a
    # scoring point of view, we have coverage that is close to 100%." Scoring them is right.
    # Ranking them TOGETHER is not. A 3x semiconductor fund's returns and relative strength are
    # three times an unlevered one's BY CONSTRUCTION, and a bear fund's are the market's negated,
    # so mixed into equity:thematic they top every column in one direction of market and bottom it
    # in the other while telling nobody anything. The peer of a geared fund is another geared fund.
    #
    # It is the ASSET GROUP that changes, not a flag bolted onto the label — so the risk
    # percentiles (`add_percentiles` cuts those within the asset group) are also cut among geared
    # funds, which is the only population in which a 60 percent annualised volatility is ordinary.
    geared = out["leveraged"].fillna(False).astype(bool) | out["inverse"].fillna(False).astype(bool)
    plain_group = out["asset_class"].fillna("unclassified")
    out["asset_group"] = ("geared:" + plain_group).where(geared, plain_group)
    narrow = out["asset_group"] + ":" + out["strategy"].fillna("unclassified")
    # A list comprehension, not Series.map(dict): pandas accepts a dict there but the type
    # stubs declare a callable, and the ratchet counts that as a new error every run.
    counts: dict[str, int] = narrow.value_counts().to_dict()
    big_enough = pd.Series([counts[n] >= min_members for n in narrow], index=out.index)
    # Counted over the FALLERS only — see the docstring. Sizing this by the whole asset class
    # is the plausible-looking version of this line that puts two funds back in a group of two.
    faller_counts: dict[str, int] = out.loc[~big_enough, "asset_group"].value_counts().to_dict()
    asset_ok = pd.Series(
        [faller_counts.get(a, 0) >= min_members for a in out["asset_group"]], index=out.index
    )

    out["peer_group"] = narrow.where(big_enough, out["asset_group"].where(asset_ok, None))
    out["grouped_by"] = pd.Series("strategy", index=out.index).where(
        big_enough, pd.Series("asset_class", index=out.index).where(asset_ok, "unranked")
    )
    peer_counts: dict[str, int] = out["peer_group"].value_counts().to_dict()
    # peer_n is NaN, not 0, where there is no group: "no peers" and "zero peers" read the same
    # in a count and mean different things on a card.
    out["peer_n"] = [peer_counts.get(g) if g is not None else None for g in out["peer_group"]]
    return out


def percentile_within(
    frame: pd.DataFrame, group: str, column: str, *, higher_is_better: bool
) -> pd.Series:
    """Each row's position in [0, 1] within its own ``group``: 1 = best, NaN preserved.

    ``groupby(...)[col].rank(pct=True)`` is a TRANSFORM — pandas guarantees the result is
    aligned to the original index, one value per input row. The obvious alternative,
    ``groupby(...).apply(...)``, returns a frame whose index depends on what the callable
    returned, and a misalignment there is invisible: every fund silently gets some OTHER
    fund's percentile, the scores stay in range, and no gate can tell. Not worth the risk for
    a line of code that does the same thing.

    ``na_option="keep"`` ranks over non-null values only: a fund with no volatility figure gets
    no volatility percentile, rather than being placed at the bottom of its group — which would
    be a measurement nobody took.
    """
    ranked = frame.groupby(group)[column].rank(pct=True, na_option="keep").astype(float)
    return ranked if higher_is_better else 1.0 - ranked


def add_percentiles(frame: pd.DataFrame) -> pd.DataFrame:
    """Peer-group percentile for the 6-month return; asset-group percentiles for the three
    risk measures. Risk is ranked in the WIDER group on purpose: a narrow strategy rarely has
    enough funds to describe a distribution of volatility, and volatility compares across a
    whole asset class in a way relative strength does not."""
    out = frame.copy()
    out["peer_pct_6m"] = percentile_within(out, "peer_group", "ret_6m", higher_is_better=True)
    for column, target, higher_is_better in (
        # Low volatility and low downside deviation are the good end, so those two are
        # inverted. mdd_12m is stored as a NEGATIVE fraction, so higher is already better on
        # the raw number: -0.05 is a shallower drawdown than -0.40 and must rank above it.
        ("vol_63d_ann", "vol_pct", False),
        ("mdd_12m", "mdd_pct", True),
        ("downside_dev_63d", "downside_pct", False),
    ):
        out[target] = percentile_within(
            out, "asset_group", column, higher_is_better=higher_is_better
        )
    return out


def _f(value: Any) -> float | None:
    """A database numeric as a float, or None. NaN is missing data, not a number."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    return float(value)


def _i(value: Any) -> int | None:
    """A count as an int, or None where there is no count to give.

    ``peer_n`` is None for an unranked fund (``assign_groups``), and pandas carries that as
    NaN in a numeric column. ``int(NaN)`` raises, which is how this crashed a whole nightly
    step after it had scored every fund correctly."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    return int(value)


def score_rows(
    frame: pd.DataFrame, anchor: dt.date, th: dict[str, Decimal], run_id: str
) -> tuple[pd.DataFrame, list]:
    """One ``etf_scores_daily`` row per fund, plus the per-fund report lines."""
    weights = weights_from_thresholds(th, LENSES, prefix="etf_lens_weight_")
    tiers = tiers_from_thresholds(th)
    total_weight = sum(weights.values())
    rows: list[dict[str, Any]] = []
    lines: list[list[Any]] = []

    # dict records, not itertuples: pandas resolves `.name` to the index name, and pyright
    # cannot see a DataFrame row's columns as attributes at all.
    for r in frame.to_dict("records"):
        technical = score_technical(
            ema_21=_f(r["ema_21"]),
            ema_50=_f(r["ema_50"]),
            ema_200=_f(r["ema_200"]),
            price=_f(r["price"]),
            ret_1w=_f(r["ret_1w"]),
            rsi_14=_f(r["rsi_14"]),
            rs_3m_spy=_f(r["rs_3m_spy"]),
            rs_6m_spy=_f(r["rs_6m_spy"]),
            rs_12m_spy=_f(r["rs_12m_spy"]),
            peer_pct_6m=_f(r["peer_pct_6m"]),
            th=th,
        )
        risk = score_risk(
            vol_pct_rank=_f(r["vol_pct"]),
            mdd_pct_rank=_f(r["mdd_pct"]),
            downside_pct_rank=_f(r["downside_pct"]),
            beta_spy=_f(r["beta_spy_252"]),
            th=th,
        )
        cost = score_cost_liquidity(
            adv_usd_60d=_f(r["adv_usd_60d_median"]),
            aum_usd=_f(r["aum_usd"]),
            top10_weight=_f(r["top10_w"]),
            th=th,
        )

        lenses: dict[str, Decimal | None] = {
            "technical": technical.value,
            "risk": risk.value,
            "cost_liquidity": cost.value,
            "flow": None,  # etf_shares_daily — no producer yet (phase2.md P3-C)
            "quality": None,  # etf_holdings look-through — no producer yet (P3-C)
        }
        # blend()'s `order` is the CONVICTION-TIER order, not the lens order — passing LENSES
        # there raised KeyError on every row (caught by test_score_writes_match_schema before
        # this ever ran on the box). The lens order that matters for India parity is the order
        # `lenses` itself is built in, which is LENSES above.
        result = blend(lenses, weights, tiers)
        present_weight = sum(w for name, w in weights.items() if lenses[name] is not None)
        coverage = (present_weight / total_weight) if total_weight else None
        status = STATUS_SCORED if result.composite is not None else STATUS_NO_LENS

        rows.append(
            {
                "instrument_id": r["instrument_id"],
                "date": anchor,
                "technical": technical.value,
                "risk": risk.value,
                "cost_liquidity": cost.value,
                "flow": None,
                "quality": None,
                **{k: v for k, v in technical.subs.items()},
                **{k: v for k, v in risk.subs.items()},
                **{k: v for k, v in cost.subs.items()},
                "composite": result.composite,
                "conviction_tier": result.conviction_tier,
                "peer_group": r["peer_group"],
                "asset_group": r["asset_group"],
                "lenses_active": result.lenses_active,
                "coverage_factor": coverage,
                "evidence": Json(
                    {
                        "grouped_by": r["grouped_by"],
                        "peer_n": _i(r["peer_n"]),
                        "technical": technical.evidence,
                        "risk": risk.evidence,
                        "cost_liquidity": cost.evidence,
                        "blend": result.evidence,
                    }
                ),
                "compute_run_id": run_id,
            }
        )
        lines.append(
            [
                r["symbol"],
                str(r["name"])[:48],
                r["peer_group"],
                _i(r["peer_n"]),
                r["grouped_by"],
                technical.value,
                risk.value,
                cost.value,
                result.composite,
                result.conviction_tier,
                result.lenses_active,
                status,
            ]
        )
    return pd.DataFrame(rows), lines


def summary_lines(
    table: pd.DataFrame, anchor: dt.date, min_members: int, fell_back: int
) -> list[str]:
    """What the step prints about what it just scored. Pure, so it can be TESTED.

    It lives out here because it was inside ``run`` and crashed the whole step on its first
    live execution: ``composite`` is a column of ``Decimal | None`` — object dtype, which is
    what the upsert needs — and ``nlargest`` refuses an object column outright. Nothing had
    exercised it, because the only caller was the one function that needs a database.

    So the ORDERING reads a float view and the WRITTEN column keeps its Decimals. Note that
    ``median()`` happens to work on the object column via a Python fallback; it is computed
    from the same float view anyway, because "works today by accident" is not a property to
    build a nightly on.
    """
    # Wrapped in a Series with an explicit dtype: to_numeric's return type is a union that
    # pyright will not let anything be called on, and coerce (rather than a bare astype) keeps
    # a value that is somehow neither Decimal nor None out of the summary instead of raising.
    as_float = pd.Series(pd.to_numeric(table["composite"], errors="coerce"), dtype=float)
    scored = int(as_float.notna().sum())
    out = [
        f"[score_etfs] anchor={anchor} etfs={len(table):,d} scored={scored:,d} "
        f"peer_groups={table['peer_group'].nunique()} fell_back_to_asset_class={fell_back:,d} "
        f"min_members={min_members}"
    ]
    if not scored:
        return out
    for group, count in table["peer_group"].value_counts().head(12).items():
        # An explicit boolean Series and an emptiness test, rather than a mask expression and
        # a NaN check: both of those are unions in the pandas stubs, and "is this group empty"
        # is the question being asked anyway.
        member = pd.Series(table["peer_group"] == group, dtype=bool)
        values = as_float.loc[member].dropna()
        shown = "—" if values.empty else f"{float(values.median()):.2f}"
        out.append(f"    {group:<28} n={count:>4,d}  median composite={shown}")
    top = table.loc[as_float.nlargest(min(5, scored)).index, ["peer_group", "composite"]]
    out.append(f"    highest composite: {list(top.itertuples(index=False, name=None))}")
    return out


def run(*, eod: dt.date | None, dry_run: bool, report: Report | None) -> dict[str, object]:
    run_id = str(uuid.uuid4())
    cutoff = eod or _gdb.eod_cutoff()
    anchor = anchor_date(cutoff)
    th = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())

    frame = _gdb.read_df(TARGETS_SQL, {"anchor": anchor})
    if frame.empty:
        raise SystemExit(
            f"no in-universe ETF has both a classification and a technical_daily row on {anchor}. "
            "Run classify_etfs.py (writes etf_classification) and build_universe_snapshot.py "
            "(writes in_universe) first — this script ranks what those two produced."
        )

    min_members = int(th["peer_group_min_members"])
    frame = add_percentiles(assign_groups(frame, min_members))
    table, lines = score_rows(frame, anchor, th, run_id)

    scored = int(table["composite"].notna().sum())
    fell_back = int((frame["grouped_by"] == "asset_class").sum())
    for line in summary_lines(table, anchor, min_members, fell_back):
        print(line)

    if report is not None:
        for line in lines:
            report.add(*line)
        outcomes = " ".join(f"{k}={v:,d}" for k, v in sorted(report.counts.items()))
        print(f"[score_etfs] {outcomes} {report.where()}")

    if dry_run:
        print("[score_etfs] --dry-run: nothing written")
        return {"etfs": len(table), "scored": scored, "written": 0}

    written = _gdb.upsert_df(f"{M}.etf_scores_daily", table, KEY)
    print(f"[score_etfs] wrote {written:,d} etf_scores_daily row(s) for {anchor}")
    return {"etfs": len(table), "scored": scored, "written": written}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the groups, write nothing")
    ap.add_argument(
        "--report", type=Path, default=None, help="per-fund CSV: lenses, group and composite"
    )
    return ap


def main() -> None:
    args = parser().parse_args()
    report = Report(args.report, REPORT_COLUMNS) if args.report else None
    try:
        run(eod=args.eod, dry_run=args.dry_run, report=report)
    finally:
        if report is not None:
            report.close()


if __name__ == "__main__":
    main()
