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
it in full: technical and risk are complete from ``technical_daily``; cost_liquidity is the
ADV$ sub-score alone until ``etf_meta`` exists; flow and quality have no inputs at all until
the P3-C ingestors land. ``blend()`` renormalises over the lenses PRESENT, ``lenses_active``
records how many there were, and the board prints "n of 5 lenses" beside every score. A lens
with no data is NULL — never zero, which would say the fund is bad at something we did not
measure (rule #0).

WHILE ONE LENS IS ACTIVE THE TIER LADDER CAPS AT MEDIUM. ``lens_conviction_highest_min_layers``
is 3 and ``..._high_min_layers`` is 2: a single-lens score cannot be HIGH however strong it is.
That is the methodology working as designed, not a defect — conviction means agreement between
independent reads, and there is only one read today.

GEARED AND INVERSE FUNDS ARE NEVER SCORED. They are classified and listed, but
``universe_snapshot.in_universe`` excludes them (the FM's rule of 2026-09-07) and this script
scores the in-universe set, so a 3x fund cannot appear in a ranking or be picked up by a
basket. The same cut removes everything below the FM's ADV$ floor.

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

# The scored set: in-universe ETFs (the FM's cut — current members, above the ADV$ floor,
# never geared or inverse) with a metric row on the anchor session and a classification to
# group them by. An INNER join on the classification is deliberate: a fund we cannot group
# cannot be ranked, and giving it a score with no peers to read it against would be worse
# than leaving it out and saying so in the report.
TARGETS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.name,
       c.asset_class, c.strategy,
       t.ema_21, t.ema_50, t.ema_200, t.rsi_14, t.ret_1w, t.ret_6m,
       t.rs_3m_spy, t.rs_6m_spy, t.rs_12m_spy,
       t.vol_63d_ann, t.mdd_12m, t.downside_dev_63d, t.beta_spy_252,
       t.adv_usd_60d_median,
       o.close_adj AS price
FROM {M}.instrument_master im
JOIN {M}.universe_snapshot u
  ON u.instrument_id = im.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
JOIN {M}.etf_classification c
  ON c.instrument_id = im.instrument_id AND c.version = 1
JOIN {M}.technical_daily t
  ON t.instrument_id = im.instrument_id AND t.date = :anchor
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
    """
    out = frame.copy()
    out["asset_group"] = out["asset_class"].fillna("unclassified")
    narrow = out["asset_group"] + ":" + out["strategy"].fillna("unclassified")
    # A list comprehension, not Series.map(dict): pandas accepts a dict there but the type
    # stubs declare a callable, and the ratchet counts that as a new error every run.
    counts: dict[str, int] = narrow.value_counts().to_dict()
    big_enough = pd.Series([counts[n] >= min_members for n in narrow], index=out.index)
    out["peer_group"] = narrow.where(big_enough, out["asset_group"])
    out["grouped_by"] = pd.Series("strategy", index=out.index).where(big_enough, "asset_class")
    peer_counts: dict[str, int] = out["peer_group"].value_counts().to_dict()
    out["peer_n"] = [peer_counts[g] for g in out["peer_group"]]
    return out


def percentile(series: pd.Series, *, higher_is_better: bool) -> pd.Series:
    """Position in [0, 1] within one group, 1 = best, NaN preserved.

    ``rank(pct=True)`` over non-null values only: a fund with no volatility figure gets no
    volatility percentile rather than being placed at the bottom of the group, which would be
    a measurement we never took.
    """
    ranked = series.rank(pct=True, na_option="keep")
    return ranked if higher_is_better else 1.0 - ranked


def add_percentiles(frame: pd.DataFrame) -> pd.DataFrame:
    """Peer-group percentile for the 6-month return; asset-group percentiles for the three
    risk measures. Risk is ranked in the WIDER group on purpose: a narrow strategy rarely has
    enough funds to describe a distribution of volatility, and volatility compares across a
    whole asset class in a way relative strength does not."""
    out = frame.copy()
    out["peer_pct_6m"] = (
        out.groupby("peer_group", group_keys=False)["ret_6m"]
        .apply(lambda s: percentile(s, higher_is_better=True))
        .astype(float)
    )
    for column, target in (
        ("vol_63d_ann", "vol_pct"),
        ("mdd_12m", "mdd_pct"),
        ("downside_dev_63d", "downside_pct"),
    ):
        # Low volatility, shallow drawdown and low downside deviation are the good end, so the
        # percentile is inverted before it reaches the ladder. mdd_12m is stored as a negative
        # fraction (a drawdown), so "higher is better" is already true of the raw number: -0.05
        # ranks above -0.40. Only the two positive-scale measures are flipped.
        flip = column != "mdd_12m"
        out[target] = (
            out.groupby("asset_group", group_keys=False)[column]
            .apply(lambda s, f=flip: percentile(s, higher_is_better=not f))
            .astype(float)
        )
    return out


def _f(value: Any) -> float | None:
    """A database numeric as a float, or None. NaN is missing data, not a number."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    return float(value)


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
        cost = score_cost_liquidity(adv_usd_60d=_f(r["adv_usd_60d_median"]), th=th)

        lenses: dict[str, Decimal | None] = {
            "technical": technical.value,
            "risk": risk.value,
            "cost_liquidity": cost.value,
            "flow": None,  # etf_shares_daily — no producer yet (phase2.md P3-C)
            "quality": None,  # etf_holdings look-through — no producer yet (P3-C)
        }
        result = blend(lenses, weights, tiers, order=LENSES)
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
                        "peer_n": int(r["peer_n"]),
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
                int(r["peer_n"]),
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
    groups = table["peer_group"].nunique()
    fell_back = int((frame["grouped_by"] == "asset_class").sum())
    print(
        f"[score_etfs] anchor={anchor} etfs={len(table):,d} scored={scored:,d} "
        f"peer_groups={groups} fell_back_to_asset_class={fell_back:,d} "
        f"min_members={min_members}"
    )
    if scored:
        top = table.nlargest(min(5, scored), "composite")[["peer_group", "composite"]]
        for group, count in table["peer_group"].value_counts().head(12).items():
            median = table.loc[table["peer_group"] == group, "composite"].median()
            print(f"    {group:<28} n={count:>4,d}  median composite={median}")
        print(f"    highest composite: {list(top.itertuples(index=False, name=None))}")

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
