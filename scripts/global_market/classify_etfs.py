#!/usr/bin/env python3
"""Persist what the fund's own name already tells us → ``atlas_global.etf_classification``.

    python scripts/global_market/classify_etfs.py                      # every active ETF
    python scripts/global_market/classify_etfs.py --report c.csv       # per-fund outcomes
    python scripts/global_market/classify_etfs.py --dry-run            # print, write nothing

WHY THIS EXISTS. The four rule modules under ``atlas.global_market.classify`` have run every
night since Phase 1 and their verdicts were thrown away: ``build_universe_snapshot`` kept one
boolean (geared or inverse), ``build_country_views`` kept one country, and the strategy — the
answer to "what job does this fund do" — was computed and discarded on every run. Nothing was
stored, so nothing could be grouped, and with no grouping there is no honest ranking: a
sector fund ranked against a Treasury fund and a gold fund is a league table of nothing.

This writes the verdict down. It is the input to ``score_etfs.py``'s peer group, which is what
makes a decile mean something (docs/global/phase2.md, chunks P2-B and P2-C).

WHAT IS DECIDED HERE, AND FROM WHAT. Every field below is a deterministic function of the
fund's registered name, plus — for the single-stock rule alone — the set of real listed equity
symbols, because "MSCI Brazil" states a ticker and tracks no company:

    strategy        classify_strategy  17 buckets, ordered first-match
    asset_class     derived from the strategy (STRATEGY_ASSET_CLASS below)
    leveraged       leverage_flags     name-anchored: 2X, -3x, Ultra, UltraShort, Bear …
    inverse         leverage_flags
    hedged          is_currency_hedged
    country_codes   country_of         ISO-3166-1 alpha-2, from the country the name names;
                                       EMPTY (not NULL) when the name names none — see
                                       NO_COUNTRIES below for why the distinction matters
    geo_focus_type  single_country when a country is named, region for the region bucket

NO NUMBER IS INVENTED (rule #0). ``confidence`` stays NULL: a regex either matched or it did
not, and a deterministic match has no probability to report — the rule that fired and the text
it matched are in ``evidence`` instead, which is the auditable version of the same thing.
``sector_id``, ``sub_sector_id``, ``theme_ids`` and ``role_id`` need the taxonomy tables and
the LLM pass (plan.md §Classification L3), which is gated on the FM's 150-name eval set and is
NOT in this chunk. ``basket_eligible`` stays NULL because ``universe_snapshot`` already answers
it with the liquidity floor included; two columns of the same name with different answers is
how a board starts contradicting itself.

THE 22% THAT MATCH NOTHING ARE NOT HIDDEN. A name no rule reads gets ``status='review'`` with
a NULL strategy, and the board shows them as their own "Unclassified" group with their names
listed. That is a work queue, not a silent default bucket — a fund quietly filed under
``broad_market`` because nothing else matched would corrupt the peer group it landed in.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
from _report import Report
from psycopg2.extras import Json

from atlas.global_market.classify.countries import country_of, is_currency_hedged
from atlas.global_market.classify.rules import leverage_flags
from atlas.global_market.classify.strategy import classify_strategy

M = _gdb.M

# One row per instrument. Re-running replaces version 1 in place, so a rule change reclassifies
# without leaving a stale row behind. Versioning a CHANGE (keeping the old row and closing its
# valid_to) waits for the LLM/human layer, where an override has to survive a re-run — with
# rules only, the code IS the record and a second version would say nothing the diff does not.
VERSION = 1
TAXONOMY_VERSION = 1
CLASSIFIED_BY = "rules"
STATUS_AUTO = "auto"
STATUS_REVIEW = "review"

# The DDL's asset_class vocabulary is six words (chk_etf_classification_asset_class); the
# strategy vocabulary is seventeen. This is the map between them, and three entries are
# judgement calls stated out loud rather than buried:
#
#   crypto            → alternative. A spot-bitcoin trust is not a commodity in the sense the
#                       commodity bucket means (no futures curve, no storage), and it is
#                       certainly not equity. `alternative` is the honest six-word answer.
#   options_income    → alternative. A covered-call fund holds equity, but its return profile
#                       is the option premium, not the equity's. Filing it under `equity` would
#                       rank it beside plain index funds it cannot behave like.
#   defined_outcome   → alternative, for the same reason: a buffered fund's payoff is the
#                       structure, not the underlying.
#
# The peer group (score_etfs.py) is asset_class × strategy, so these three keep their own
# groups regardless — the asset class only decides the fallback when a group is too small.
STRATEGY_ASSET_CLASS: dict[str, str] = {
    "broad_market": "equity",
    "size_style": "equity",
    "factor": "equity",
    "dividend_income": "equity",
    "sector": "equity",
    "thematic": "equity",
    "country": "equity",
    "region": "equity",
    "single_stock": "equity",
    "fixed_income": "fixed_income",
    "commodity": "commodity",
    "currency": "currency",
    "multi_asset": "multi_asset",
    "crypto": "alternative",
    "defined_outcome": "alternative",
    "options_income": "alternative",
    "alternative": "alternative",
}

GEO_SINGLE = "single_country"
GEO_REGION = "region"

# "This name names no country" is an EMPTY LIST, not NULL. ``etf_classification.country_codes``
# is ``text[] NOT NULL DEFAULT '{}'`` (03_classification.sql), so writing None fails the whole
# upsert — which is exactly what it did on the first live run: every one of the ~4,000 funds
# whose name states no country took the NULL branch, classify_etfs died on the first of them,
# and score_etfs, freshness_guard and gate C all failed behind it with nothing to score.
#
# The empty list is also the right answer, not just the writable one. A set-valued column has
# no use for three states: "no countries" IS the empty set. What the emptiness does NOT tell
# you is WHY it is empty, and that is ``geo_focus_type``'s job —
#
#     single_country + ['JP']  a country the name states
#     region         + []      a region whose members this layer has not enumerated
#     NULL           + []      a name that states no geography at all
#
# — so no reader may infer geography from the array alone. Both readers today are already
# written that way (ClassificationCard checks length; scores.ts joins on country_codes[1],
# which is NULL for an empty array in Postgres and simply does not match).
NO_COUNTRIES: list[str] = []

KEY = ["instrument_id", "version"]
REPORT_COLUMNS = (
    "symbol",
    "name",
    "strategy",
    "asset_class",
    "country",
    "leveraged",
    "inverse",
    "hedged",
    "rule",
    "evidence",
    "status",
)

# Every active ETF, and separately every active stock symbol — the single-stock rule needs the
# real listed-equity set to tell "a fund named after a company" from "a fund whose index name
# happens to contain three capital letters".
ETFS_SQL = f"""
SELECT instrument_id::text AS instrument_id, symbol, name
FROM {M}.instrument_master
WHERE asset_class = 'etf' AND is_active
ORDER BY symbol
"""
STOCK_SYMBOLS_SQL = f"""
SELECT symbol FROM {M}.instrument_master WHERE asset_class = 'stock' AND is_active
"""


def classify_one(name: str, active_symbols: set[str]) -> dict[str, Any]:
    """Every classification field for one fund name. Pure: no I/O, no clock, no database.

    Returns the column values ``etf_classification`` takes, plus ``rule``/``evidence_text``
    for the report. A field the name does not determine is ``None`` — never a default — with
    one deliberate exception: ``country_codes`` is the empty list, because a set-valued column
    has no "unknown" state to express and its NOT NULL constraint would reject one anyway
    (NO_COUNTRIES above).
    """
    match = classify_strategy(name, active_symbols)
    flags = leverage_flags(name)
    country = country_of(name)
    hedged = is_currency_hedged(name)

    if country is not None:
        geo_focus, country_codes = GEO_SINGLE, [country.iso2]
    elif match.strategy == "region":
        geo_focus, country_codes = GEO_REGION, NO_COUNTRIES
    else:
        # Not "global" — a fund whose name names no place has an unstated geography, and
        # asserting `global` would put US-only broad funds on a world map.
        geo_focus, country_codes = None, NO_COUNTRIES

    return {
        "strategy": match.strategy,
        "asset_class": STRATEGY_ASSET_CLASS.get(match.strategy) if match.strategy else None,
        "geo_focus_type": geo_focus,
        "country_codes": country_codes,
        "country_pure": None if country is None else True,
        "leveraged": flags.leveraged,
        "inverse": flags.inverse,
        "hedged": hedged,
        "active": None,  # active vs index management is a prospectus fact, not a name fact
        "status": STATUS_AUTO if match.strategy is not None else STATUS_REVIEW,
        "rule": match.rule,
        "evidence_text": match.evidence,
        "leverage_rule": flags.rule,
        "country_name": None if country is None else country.name,
    }


def rows(
    frame: pd.DataFrame, active_symbols: set[str], now: dt.datetime
) -> tuple[pd.DataFrame, list]:
    """One ``etf_classification`` row per fund, plus the per-fund report lines."""
    out: list[dict[str, Any]] = []
    lines: list[list[Any]] = []
    # dict records, not itertuples: a pandas named tuple resolves `.name` to the INDEX name,
    # so `record.name` would silently read the wrong thing on the one column that matters here.
    for record in frame.to_dict("records"):
        verdict = classify_one(str(record["name"]), active_symbols)
        out.append(
            {
                "instrument_id": record["instrument_id"],
                "version": VERSION,
                "asset_class": verdict["asset_class"],
                "strategy": verdict["strategy"],
                "geo_focus_type": verdict["geo_focus_type"],
                "country_codes": verdict["country_codes"],
                "country_pure": verdict["country_pure"],
                "leveraged": verdict["leveraged"],
                "inverse": verdict["inverse"],
                "hedged": verdict["hedged"],
                "active": verdict["active"],
                # confidence and basket_eligible stay NULL — see the module docstring.
                "rationale": None,
                "evidence": Json(
                    {
                        "strategy_rule": verdict["rule"],
                        "matched_text": verdict["evidence_text"],
                        "leverage_rule": verdict["leverage_rule"],
                        "name": str(record["name"]),
                    }
                ),
                "classified_by": CLASSIFIED_BY,
                "status": verdict["status"],
                "taxonomy_version": TAXONOMY_VERSION,
                "valid_from": now,
            }
        )
        lines.append(
            [
                record["symbol"],
                str(record["name"])[:60],
                verdict["strategy"],
                verdict["asset_class"],
                verdict["country_name"],
                verdict["leveraged"],
                verdict["inverse"],
                verdict["hedged"],
                verdict["rule"],
                verdict["evidence_text"],
                verdict["status"],
            ]
        )
    return pd.DataFrame(out), lines


def run(*, dry_run: bool, report: Report | None) -> dict[str, object]:
    run_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    frame = _gdb.read_df(ETFS_SQL)
    if frame.empty:
        raise SystemExit(
            "instrument_master holds no active ETF — run build_identity.py first; this script "
            "reads identity, it does not create it"
        )
    active_symbols = set(_gdb.read_df(STOCK_SYMBOLS_SQL)["symbol"].astype(str))
    table, lines = rows(frame, active_symbols, now)

    by_strategy = table["strategy"].value_counts(dropna=False)
    unmatched = int(table["strategy"].isna().sum())
    geared = int((table["leveraged"] | table["inverse"]).sum())
    print(
        f"[classify] run={run_id[:8]} etfs={len(table):,d} strategies={by_strategy.count()} "
        f"unclassified={unmatched:,d} ({unmatched / len(table):.1%}) geared_or_inverse={geared:,d}"
    )
    for strategy, count in by_strategy.items():
        label = strategy if isinstance(strategy, str) else "(unclassified)"
        print(f"    {label:<18} {count:>6,d}")

    if report is not None:
        for line in lines:
            report.add(*line)
        print(
            f"[classify] {' '.join(f'{k}={v:,d}' for k, v in sorted(report.counts.items()))} "
            f"{report.where()}"
        )

    if dry_run:
        print("[classify] --dry-run: nothing written")
        return {"etfs": len(table), "unclassified": unmatched, "written": 0}

    written = _gdb.upsert_df(f"{M}.etf_classification", table, KEY)
    print(f"[classify] wrote {written:,d} etf_classification row(s)")
    return {"etfs": len(table), "unclassified": unmatched, "written": written}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--dry-run", action="store_true", help="print the distribution, write nothing")
    ap.add_argument(
        "--report", type=Path, default=None, help="per-fund CSV: the verdict and the rule behind it"
    )
    return ap


def main() -> None:
    args = parser().parse_args()
    report = Report(args.report, REPORT_COLUMNS) if args.report else None
    try:
        run(dry_run=args.dry_run, report=report)
    finally:
        if report is not None:
            report.close()


if __name__ == "__main__":
    main()
