#!/usr/bin/env python3
"""One ETF per country → ``atlas_global.country`` + ``atlas_global.country_daily``.

    python scripts/global_market/build_country_views.py                 # latest EOD
    python scripts/global_market/build_country_views.py --eod 2026-09-07 --report c.csv
    python scripts/global_market/build_country_views.py --dry-run       # print, write nothing

WHAT THE PAGE ASKS AND THIS ANSWERS. "If I want exposure to Japan, which one fund do I buy?"
Not "what is Japan's factor loading" — one tradeable instrument per country, and the evidence
to judge it: how it has done against the S&P over six windows, and how many other funds cover
the same market.

MEMBERSHIP IS THE FUND'S NAME (``atlas.global_market.classify.countries``), which reverses the
2026-09-04 plan's holdings look-through on the FM's instruction of 2026-09-08. The reasoning,
and what it gives up, is in that module's docstring; the short version is that a holdings
pipeline is enormous machinery to establish something the issuer states in the title, and the
whole answer here is fifty rows a human reads once.

THE REPRESENTATIVE IS THE MOST-TRADED FUND, not the largest. Three reasons, in order:

* It is the one you can actually transact in. This is a product for taking a position, and a
  fund with ten times the AUM and a tenth of the daily volume is the worse instrument to buy
  and a far worse one to leave.
* ADV$ is a MEASUREMENT we already hold, computed nightly over a 60-session median from real
  volume. AUM is a vendor-reported figure that would need a whole new feed (``etf_meta``) —
  new machinery for a worse answer.
* It moves with the market. A fund losing its liquidity stops being the representative on its
  own, without anyone maintaining a list.

Three kinds of fund are excluded from BEING the representative, though they still count toward
``n_etfs``: geared and inverse funds (``classify.rules.leverage_flags``), which answer a
different question with the same country in the title, and currency-hedged share classes,
which are a bet on the currency as much as the market. A reader who wants "the Japan ETF" does
not mean "2x Japan daily" — and putting one there is the kind of wrong that is only noticed
after somebody buys it.

RANK, NOT JUST RELATIVE STRENGTH (P2-E, the FM's decision D2 of 2026-09-09). ``composite`` is
the representative fund's own composite from ``etf_scores_daily`` — the same number the ETF
board shows for that fund, read here rather than recomputed, so a country and its fund can
never disagree. ``breadth_pct`` is the share of that market's SCORED funds at or above
``rollup_breadth_min``: it separates "one strong fund" from "the whole market is working",
which is the difference between a trade and a theme. Its denominator is the scored members,
not all members, and the report carries both counts so the page can say which.

Countries are then RANKED ACROSS MARKETS on read — deciles and quartiles cut over the
composite, the same way every other Atlas ranking is cut. Nothing is materialised here: a
rank is a statement about a population on a date.

WHAT IS STILL DELIBERATELY NULL. ``aum_usd_total`` needs ``etf_meta``, which has no producer
until phase2.md P3-C. A column with no honest source stays empty rather than carrying a number
nobody can trace (rule #0). The page renders what is present and says what is not.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
from _report import Report

from atlas.db import load_thresholds
from atlas.global_market.classify.countries import COUNTRIES, country_of, is_currency_hedged
from atlas.global_market.classify.rules import leverage_flags

M = _gdb.M
RS_WINDOWS = ("1w", "1m", "3m", "6m", "12m", "24m")
RS_COLUMNS = [f"rs_{w}_spy" for w in RS_WINDOWS]
COUNTRY_KEY = ["iso2"]
DAILY_KEY = ["iso2", "date"]
# ``status`` is the outcome word every global report carries, and it is not decoration: it is
# what ``_report.Report`` counts by default, so the run prints "picked=44 no_eligible_fund=6"
# without anyone reading the CSV. Its absence here is what made the first run of this script
# die inside the Report constructor.
PICKED = "picked"
NO_ELIGIBLE = "no_eligible_fund"
REPORT_COLUMNS = (
    "iso2",
    "country",
    "region",
    "representative",
    "representative_name",
    "adv_usd_60d_median",
    "n_etfs",
    "n_eligible",
    "n_scored",
    "composite",
    "breadth_pct",
    "rs_3m_spy",
    "rs_12m_spy",
    "status",
)

# The anchor: the newest session technical_daily holds at or before the cutoff. One date for
# every country, so the grid compares like with like — a row carried forward from an older
# session would sit beside today's and read as today's.
ANCHOR_SQL = f"SELECT max(date) AS d FROM {M}.technical_daily WHERE date <= :cutoff"

# Every active ETF that has a metric row on the anchor session, with the two things the
# representative rule needs (liquidity) and the six the page shows (relative strength).
# An ETF with no row on the anchor has not traded into it and cannot represent anything.
MEMBERS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.name,
       t.adv_usd_60d_median, {", ".join(f"t.{c}" for c in RS_COLUMNS)},
       s.composite
FROM {M}.instrument_master im
JOIN {M}.technical_daily t USING (instrument_id)
LEFT JOIN {M}.etf_scores_daily s
       ON s.instrument_id = im.instrument_id AND s.date = :anchor
WHERE im.asset_class = 'etf' AND im.is_active AND t.date = :anchor
"""


def anchor_date(cutoff: dt.date) -> dt.date:
    frame = _gdb.read_df(ANCHOR_SQL, {"cutoff": cutoff})
    day = frame["d"].iloc[0] if not frame.empty else None
    if day is None:
        raise SystemExit(
            f"technical_daily holds nothing at or before {cutoff} — run compute_technicals.py "
            "first; the country view is a read over its output, not a second computation"
        )
    return day


def members(anchor: dt.date) -> pd.DataFrame:
    """Every active ETF on the anchor session, tagged with the country its name names.

    Adds four columns and drops nothing, so the report can show what was excluded and why
    rather than leaving a fund unexplained.
    """
    frame = _gdb.read_df(MEMBERS_SQL, {"anchor": anchor})
    if frame.empty:
        return frame
    countries = [country_of(str(n)) for n in frame["name"]]
    frame["iso2"] = [c.iso2 if c else None for c in countries]
    frame["country_name"] = [c.name if c else None for c in countries]
    frame["region"] = [c.region if c else None for c in countries]
    flags = [leverage_flags(str(n)) for n in frame["name"]]
    frame["eligible"] = [
        not f.leveraged and not f.inverse and not is_currency_hedged(str(n))
        for f, n in zip(flags, frame["name"], strict=True)
    ]
    return frame.loc[frame["iso2"].notna()]


def representative(group: pd.DataFrame) -> pd.Series | None:
    """The most-traded eligible fund for one country, or ``None`` when none qualifies.

    ``None`` is a real outcome, not a failure: a country covered only by a 3x fund has no
    instrument that answers "buy this for exposure to it". The row is still written — the
    country IS covered, and saying so with an empty representative is more useful than
    omitting it — and the report names the reason.
    """
    eligible = group.loc[group["eligible"] & group["adv_usd_60d_median"].notna()]
    if eligible.empty:
        return None
    return eligible.loc[eligible["adv_usd_60d_median"].idxmax()]


def country_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """The ``atlas_global.country`` reference rows the FK needs, for countries with members.

    Only countries that actually have a fund are written. Seeding all fifty would put rows on
    the page for markets no US-listed instrument covers, which is a grid of empty promises.
    ``msci_class`` stays NULL: developed / emerging / frontier is MSCI's proprietary
    determination and we hold no licence to restate it.
    """
    # Deduping on all three columns is the same as deduping on iso2: `country_of` reads them
    # off one frozen record per code, so a code cannot arrive with two names or two regions.
    seen = frame[["iso2", "country_name", "region"]].drop_duplicates()
    return pd.DataFrame(
        {"iso2": seen["iso2"], "name": seen["country_name"], "region": seen["region"]}
    )


def breadth(group: pd.DataFrame, minimum: Decimal) -> tuple[int, float | None]:
    """``(n_scored, percent of them at or above the cut)`` for one country.

    The denominator is the SCORED members, not every member: geared, inverse and
    below-floor funds carry no composite by design (they are excluded from ``in_universe``),
    and counting them as failures would make every market look weak in proportion to how many
    leveraged products someone launched on it. A market with nothing scored gets ``None`` —
    not 0, which reads as "measured, and bad".
    """
    scored = group["composite"].dropna()
    if scored.empty:
        return 0, None
    above = int((scored >= float(minimum)).sum())
    return len(scored), round(100.0 * above / len(scored), 2)


def daily_rows(
    frame: pd.DataFrame, anchor: dt.date, run_id: str, breadth_min: Decimal
) -> tuple[pd.DataFrame, list]:
    """One ``country_daily`` row per country, plus the per-country report lines."""
    rows: list[dict[str, Any]] = []
    report: list[list[Any]] = []
    for iso2, group in frame.groupby("iso2", sort=True):
        pick = representative(group)
        n_eligible = int(group["eligible"].sum())
        n_scored, breadth_pct = breadth(group, breadth_min)
        # The country's composite IS its representative's, read from the scorer's own row.
        # Averaging the market's funds would blend a strong tracker with the thin products
        # nobody would buy, and the number would then describe no instrument at all.
        composite = None if pick is None else pick["composite"]
        row: dict[str, Any] = {
            "iso2": iso2,
            "date": anchor,
            "representative_id": None if pick is None else pick["instrument_id"],
            "n_etfs": len(group),
            "composite": composite,
            "breadth_pct": breadth_pct,
            "compute_run_id": run_id,
        }
        for column in RS_COLUMNS:
            row[column] = None if pick is None else pick[column]
        rows.append(row)
        report.append(
            [
                iso2,
                group["country_name"].iloc[0],
                group["region"].iloc[0],
                None if pick is None else pick["symbol"],
                None if pick is None else pick["name"],
                None if pick is None else pick["adv_usd_60d_median"],
                len(group),
                n_eligible,
                n_scored,
                composite,
                breadth_pct,
                None if pick is None else pick["rs_3m_spy"],
                None if pick is None else pick["rs_12m_spy"],
                PICKED if pick is not None else NO_ELIGIBLE,
            ]
        )
    return pd.DataFrame(rows), report


def run(*, eod: dt.date | None, dry_run: bool, report: Report | None) -> dict[str, object]:
    run_id = str(uuid.uuid4())
    cutoff = eod or _gdb.eod_cutoff()
    anchor = anchor_date(cutoff)
    frame = members(anchor)
    if frame.empty:
        raise SystemExit(
            f"no active ETF has a technical_daily row on {anchor} — nothing to build a country "
            "view from"
        )
    countries = country_rows(frame)
    breadth_min = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())["rollup_breadth_min"]
    daily, lines = daily_rows(frame, anchor, run_id, breadth_min)
    with_rep = int(daily["representative_id"].notna().sum())
    print(
        f"[countries] anchor={anchor} etfs_scanned={len(frame):,d} "
        f"countries={len(countries)} of {len(set(c.iso2 for c in COUNTRIES.values()))} known "
        f"with_representative={with_rep} "
        f"with_composite={int(daily['composite'].notna().sum())}"
    )
    if report is not None:
        for line in lines:
            report.add(*line)
        outcomes = " ".join(f"{k}={v:,d}" for k, v in sorted(report.counts.items()))
        print(f"[countries] {outcomes} {report.where()}")
    if dry_run:
        print("[countries] --dry-run: nothing written")
        return {"countries": len(countries), "with_representative": with_rep, "written": 0}
    # Reference rows first: country_daily.iso2 carries a foreign key to them.
    _gdb.upsert_df(f"{M}.country", countries, COUNTRY_KEY)
    written = _gdb.upsert_df(f"{M}.country_daily", daily, DAILY_KEY)
    print(f"[countries] wrote {written:,d} country_daily row(s) for {anchor}")
    return {"countries": len(countries), "with_representative": with_rep, "written": written}


def parser() -> argparse.ArgumentParser:
    """The CLI, reachable from a test — the two defects it carried were both invisible here.

    ``--report`` is a ``Path`` and not a string: ``Report`` opens what it is handed, and a
    ``str`` fails on ``.open`` only once the script has already connected and queried.
    """
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the grid, write nothing")
    ap.add_argument(
        "--report", type=Path, default=None, help="per-country CSV: what was picked and why"
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
