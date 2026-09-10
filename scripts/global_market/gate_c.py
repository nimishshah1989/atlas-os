#!/usr/bin/env python3
"""Gate C — the scores are usable, asserted on PRODUCED rows.

Run through the one gate entry point: ``validate_global.py --check C``. Its own module for
the same reason ``gate_a.py`` is: ``validate_global.py`` is near its size tier. Same ``Gate``.

WHAT THIS IS FOR. India's ``validate_lenses.py`` carries one assertion per past incident —
each check exists because a specific wrong number once reached the board. Global has no such
history yet, so this gate asserts the properties whose ABSENCE would make a score meaningless,
before anyone can act on one:

* **A score that does not discriminate is not a score.** If every fund scores 61, the ranking
  is noise with a decoration. ``stddev(composite) >= 10`` and each lens ``stddev >= 2`` are
  India's own floors, and they are the difference between a scorer that ran and a scorer that
  worked. This is the check that catches a threshold table seeded with zeros, a lens whose
  inputs are all NULL, or a ladder collapsed onto one rung.
* **A decile is a lie in a group that cannot support one.** ``ntile(10)`` over five funds
  produces deciles 1–5 and calls the median fund top-decile. The peer-group fallback exists to
  prevent that; this asserts it actually happened.
* **A geared fund is ranked only among geared funds.** They ARE scored — the FM opened that
  gate ("we should score all the funds, irrespective") — but a 3x fund's returns and relative
  strength are three times an unlevered one's by construction, and a bear fund's are the
  market's negated, so in a shared population they top every column while informing nobody.
  ``score_etfs.assign_groups`` puts them in ``geared:<class>``; this asserts both directions of
  that, because either leak corrupts the same rankings. Basket eligibility is a separate rule
  and still excludes them outright.
* **A composite must be traceable.** Every scored row needs a peer group, an asset group and
  at least one active lens; a composite with ``lenses_active = 0`` is a number from nowhere.

WHAT IT DELIBERATELY DOES NOT CHECK. Whether the scores are any GOOD — whether a high
composite predicts anything — is not a nightly gate, it is the signal-validation work
(``eval_signal`` → ``atlas_signal_ic``, phase2.md P3-D), and until that exists the weights are
seeds and the board says so. A gate that claimed to measure quality would be the worst kind of
wrong: reassuring and empty.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb (sibling)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb

from atlas.db import load_thresholds

if TYPE_CHECKING:  # pragma: no cover - typing only
    from validate_global import Gate

M = _gdb.M

# India's floors (validate_lenses.py), which are about the SHAPE of a score distribution and
# carry no market assumption: a composite that varies by less than 10 points across a whole
# universe, or a lens by less than 2, has stopped discriminating.
MIN_COMPOSITE_STDDEV = 10.0  # allow-threshold: a distribution-shape floor, not a methodology cut
MIN_LENS_STDDEV = 2.0  # allow-threshold: as above — India's own, unchanged for the US
LENSES = ("technical", "risk", "cost_liquidity")  # the ones with producers today

ANCHOR_SQL = f"SELECT max(date) AS d FROM {M}.etf_scores_daily"

SUMMARY_SQL = f"""
SELECT count(*)                                            AS rows,
       count(composite)                                    AS scored,
       min(composite)                                      AS lo,
       max(composite)                                      AS hi,
       stddev_pop(composite)                               AS sd,
       count(*) FILTER (WHERE peer_group IS NULL)          AS no_peer_group,
       count(*) FILTER (WHERE asset_group IS NULL)         AS no_asset_group,
       count(*) FILTER (WHERE composite IS NOT NULL
                          AND coalesce(lenses_active, 0) = 0) AS untraceable
FROM {M}.etf_scores_daily WHERE date = :anchor
"""

# peer_group IS NULL is the deliberate "no peer set large enough to rank in" case that
# score_etfs.assign_groups writes (its docstring says why there is nowhere further to fall).
# Those rows are not a group and must not be counted as an undersized one — a NULL group would
# otherwise be the ONLY group that could ever fail the size check, by construction.
GROUPS_SQL = f"""
SELECT peer_group, count(*) AS n, count(composite) AS scored,
       stddev_pop(composite) AS sd
FROM {M}.etf_scores_daily WHERE date = :anchor AND peer_group IS NOT NULL
GROUP BY peer_group ORDER BY n DESC
"""

# The funds that got no peer group, and how big their asset class actually is. A fund may be
# unranked ONLY because its own asset class is under the floor; one that landed here with a
# large asset class means the fallback dropped it, which is a bug that would silently remove
# real funds from every ranking on the board.
UNRANKED_SQL = f"""
SELECT asset_group, count(*) AS n
FROM {M}.etf_scores_daily WHERE date = :anchor AND peer_group IS NULL
GROUP BY asset_group ORDER BY n DESC
"""

# A geared or inverse fund must have no score row at all. The join proves it from the
# classification the same nightly wrote, not from a re-reading of the fund's name here.
# GEARED FUNDS ARE SCORED NOW, AND THE INVARIANT MOVED WITH THEM.
#
# This gate used to assert that no geared or inverse fund carried a score at all — the universe
# cut kept them out. The FM opened that gate ("we should score all the funds, irrespective"), so
# the thing worth protecting is no longer their absence but their SEPARATION: a 3x fund's returns
# are three times an unlevered one's by construction, so ranked in the same population it tops
# every column without informing anyone. score_etfs.assign_groups puts them in `geared:<class>`.
#
# Both directions are checked, because either leak corrupts the same rankings.
GEARED_MIXED_SQL = f"""
SELECT im.symbol, s.asset_group
FROM {M}.etf_scores_daily s
JOIN {M}.etf_classification c ON c.instrument_id = s.instrument_id AND c.version = 1
JOIN {M}.instrument_master im ON im.instrument_id = s.instrument_id
WHERE s.date = :anchor AND (c.leveraged OR c.inverse)
  AND (s.asset_group IS NULL OR s.asset_group NOT LIKE 'geared:%')
LIMIT 20
"""

PLAIN_IN_GEARED_SQL = f"""
SELECT im.symbol, s.asset_group
FROM {M}.etf_scores_daily s
JOIN {M}.etf_classification c ON c.instrument_id = s.instrument_id AND c.version = 1
JOIN {M}.instrument_master im ON im.instrument_id = s.instrument_id
WHERE s.date = :anchor AND NOT (coalesce(c.leveraged, false) OR coalesce(c.inverse, false))
  AND s.asset_group LIKE 'geared:%'
LIMIT 20
"""

UNCLASSIFIED_SCORED_SQL = f"""
SELECT count(*) AS n
FROM {M}.etf_scores_daily s
LEFT JOIN {M}.etf_classification c ON c.instrument_id = s.instrument_id AND c.version = 1
WHERE s.date = :anchor AND c.instrument_id IS NULL
"""

CLASSIFICATION_SQL = f"""
SELECT count(*) AS total,
       count(*) FILTER (WHERE status = 'review')  AS in_review,
       count(*) FILTER (WHERE strategy IS NULL)   AS no_strategy,
       count(*) FILTER (WHERE asset_class IS NULL AND strategy IS NOT NULL) AS strategy_no_class
FROM {M}.etf_classification WHERE version = 1
"""


def check_C(g: Gate, eod: date | None) -> None:
    """Every assertion below reads produced rows; nothing is recomputed here (rule #0)."""
    anchor = _gdb.read_df(ANCHOR_SQL)["d"].iloc[0]
    if anchor is None:
        g.check("etf_scores_daily has rows", False, "empty — run score_etfs.py")
        return
    if eod is not None and anchor > eod:
        anchor = eod
    print(f"  anchor {anchor}")

    s = _gdb.read_df(SUMMARY_SQL, {"anchor": anchor}).iloc[0]
    rows, scored = int(s["rows"]), int(s["scored"] or 0)
    g.check("scored rows exist", scored > 0, f"{scored:,d} of {rows:,d} rows carry a composite")
    if scored == 0:
        return

    lo, hi = float(s["lo"]), float(s["hi"])
    g.check(
        "every composite is within 0-100",
        0.0 <= lo and hi <= 100.0,
        f"range {lo:.2f}-{hi:.2f}",
    )
    sd = float(s["sd"] or 0.0)
    g.check(
        "the composite discriminates",
        sd >= MIN_COMPOSITE_STDDEV,
        f"stddev {sd:.2f} (floor {MIN_COMPOSITE_STDDEV}) — below it the ranking is noise",
    )
    g.check("every scored row has an asset group", int(s["no_asset_group"]) == 0)
    g.check(
        "no composite without an active lens",
        int(s["untraceable"]) == 0,
        f"{int(s['untraceable']):,d} row(s) carry a score from nowhere",
    )

    for lens in LENSES:
        frame = _gdb.read_df(
            f"SELECT stddev_pop({lens}) AS sd, count({lens}) AS n "
            f"FROM {M}.etf_scores_daily WHERE date = :anchor",
            {"anchor": anchor},
        ).iloc[0]
        n = int(frame["n"] or 0)
        if n == 0:
            # Not a failure: cost_liquidity has one sub-score today and flow/quality have no
            # producer at all. An absent lens is disclosed, never silently passed as good.
            print(f"  [\033[33mSKIP\033[0m] lens {lens} has no rows yet (no producer)")
            continue
        lens_sd = float(frame["sd"] or 0.0)
        g.check(
            f"lens {lens} discriminates",
            lens_sd >= MIN_LENS_STDDEV,
            f"stddev {lens_sd:.2f} over {n:,d} rows (floor {MIN_LENS_STDDEV})",
        )

    th = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())
    minimum = int(th["peer_group_min_members"])
    groups = _gdb.read_df(GROUPS_SQL, {"anchor": anchor})
    too_small = groups.loc[groups["n"] < minimum]
    g.check(
        "no fund is ranked in a group too small to rank in",
        too_small.empty,
        f"{len(too_small)} group(s) under {minimum} members: "
        f"{', '.join(f'{r.peer_group}={r.n}' for r in too_small.head(5).itertuples())}"
        if not too_small.empty
        else f"{len(groups)} groups, smallest {int(groups['n'].min())}, cut at {minimum}",
    )

    # The other half of the same rule. Above: nothing is ranked in a group too small. Here:
    # nothing was left UNRANKED that had a group big enough to rank in — which is what a
    # broken fallback would look like, and it would quietly delete real funds from the board's
    # every ranking while every other check in this gate stayed green.
    unranked = [
        (str(r["asset_group"]), int(r["n"]))
        for r in _gdb.read_df(UNRANKED_SQL, {"anchor": anchor}).to_dict("records")
    ]
    total_unranked = sum(n for _, n in unranked)
    wrongly = [(a, n) for a, n in unranked if n >= minimum]
    g.check(
        "no fund was left unranked that had peers enough to rank",
        not wrongly,
        f"{len(wrongly)} asset class(es) with ≥ {minimum} members got no peer group: "
        + ", ".join(f"{a}={n}" for a, n in wrongly[:5])
        if wrongly
        else f"{total_unranked:,d} fund(s) unranked, all in asset classes under {minimum}",
    )
    if total_unranked:
        print(
            f"  [\033[33mNOTE\033[0m] {total_unranked:,d} fund(s) are scored but NOT ranked — "
            f"their whole asset class has fewer than {minimum} in-universe members "
            f"({', '.join(f'{a}={n}' for a, n in unranked)}). They carry a composite from "
            "their absolute sub-scores and no decile, because a rank is a statement about a "
            "population and there is no population."
        )

    mixed = _gdb.read_df(GEARED_MIXED_SQL, {"anchor": anchor})
    g.check(
        "every geared or inverse fund is ranked only among geared funds",
        mixed.empty,
        "all in a geared asset group"
        if mixed.empty
        else f"ranked among unlevered peers: {', '.join(mixed['symbol'].head(10))}",
    )

    leaked = _gdb.read_df(PLAIN_IN_GEARED_SQL, {"anchor": anchor})
    g.check(
        "no unlevered fund is ranked among geared ones",
        leaked.empty,
        "the geared groups hold only geared funds"
        if leaked.empty
        else f"unlevered in a geared group: {', '.join(leaked['symbol'].head(10))}",
    )

    orphans = int(_gdb.read_df(UNCLASSIFIED_SCORED_SQL, {"anchor": anchor})["n"].iloc[0])
    g.check(
        "every scored fund has a classification",
        orphans == 0,
        f"{orphans:,d} scored fund(s) have no classification row — they cannot be grouped",
    )

    c = _gdb.read_df(CLASSIFICATION_SQL).iloc[0]
    total, review = int(c["total"]), int(c["in_review"])
    g.check("classification rows exist", total > 0, f"{total:,d} funds classified")
    if total:
        # Not a pass/fail: the unread share is a real property of a rule-based classifier and
        # the FM decides when it is small enough. It is REPORTED so it cannot drift unnoticed.
        print(
            f"  [\033[33mNOTE\033[0m] {review:,d} of {total:,d} funds ({review / total:.1%}) "
            f"await review — no rule reads their name; they show as Unclassified"
        )
    g.check(
        "a classified fund always has an asset class",
        int(c["strategy_no_class"]) == 0,
        f"{int(c['strategy_no_class']):,d} fund(s) have a strategy the asset-class map misses",
    )
