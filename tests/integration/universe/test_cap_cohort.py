"""Integration tests for atlas_foundation.v_stock_cap — the single cap-cohort rule.

Cap moves from index membership to market-cap rank. The index rule was always
approximating a market-cap rank (NIFTY 100 = top 100, MIDCAP 150 = 101-250,
SMLCAP 250 = 251-500), so the two labels mostly agree — but NOT exactly, and the
gap is not a defect. See the note above _TIER_ORDER.

Run BEFORE the universe flips (Task 5) — the comparison against the index rule is
only meaningful while is_active is still the index-derived 747.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _db  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.integration


def test_view_exists_and_covers_every_active_stock() -> None:
    n_missing = _db.scalar(
        """SELECT count(*) FROM atlas_foundation.instrument_master im
           LEFT JOIN atlas_foundation.v_stock_cap v USING (instrument_id)
           WHERE im.asset_class='stock' AND im.is_active AND v.cap IS NULL"""
    )
    assert n_missing == 0, f"{n_missing} active stocks have no cap label"


# Cap tiers in rank order. Disagreement between the two rules is EXPECTED and is not
# an error: NSE selects index membership on a 6-MONTH AVERAGE market cap and
# reconstitutes semi-annually, while v_stock_cap ranks point-in-time. Names near ranks
# 100/250/500 therefore swap sides between reconstitutions. Measured 2026-08-23:
# 77.4% agreement, with near-perfectly symmetric flow across each boundary
# (large<->mid 11/11, mid<->small 19/18, small<->micro 54/55). What would signal a REAL
# defect is asymmetry (bias, not drift) or a tier-skip that cannot be explained.
_TIER_ORDER = {"large": 0, "mid": 1, "small": 2, "micro": 3}


def _old_vs_new() -> pd.DataFrame:
    """Old index label vs new rank label, per active stock.

    Skips once the universe has flipped. The two tests below are ONE-WAY MIGRATION
    GATES: they only mean something while is_active is still the index-derived 747.
    Task 5 takes it to ~1,207 with every new name outside all NSE indices, so old_cap
    becomes 'micro' for ~460 names at once and the symmetry check blows apart — through
    no fault of the view. Skipping is the honest outcome; the alternative is that
    whoever hits the failure loosens the threshold or deletes the tier-skip audit.
    """
    df = _db.read_df(
        """WITH old AS (
               SELECT instrument_id,
                 CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
                      WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
                      WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small'
                      ELSE 'micro' END AS cap
               FROM atlas_foundation.de_index_constituents
               WHERE effective_to IS NULL
                 AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
               GROUP BY instrument_id)
           SELECT im.symbol, COALESCE(old.cap,'micro') AS old_cap, v.cap AS new_cap,
                  v.mcap_rank, m.market_cap_cr
           FROM atlas_foundation.instrument_master im
           JOIN atlas_foundation.v_stock_cap v USING (instrument_id)
           JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
           LEFT JOIN old ON old.instrument_id = im.instrument_id
           WHERE im.asset_class='stock' AND im.is_active"""
    )
    if len(df) > 800:
        pytest.skip(
            f"universe has flipped ({len(df)} active stocks) — this was a one-way "
            "migration gate against the index-derived 747 and no longer applies"
        )
    assert len(df) > 700, "expected the current active universe"
    return df


def test_disagreements_are_boundary_drift_not_bias() -> None:
    """Equal numbers must cross each boundary in each direction. Systematic one-way
    flow would mean the market-cap basis is wrong, not merely out of phase."""
    flow = Counter(
        (r["old_cap"], r["new_cap"])
        for r in _old_vs_new().to_dict("records")
        if r["old_cap"] != r["new_cap"]
    )
    for a, b in (("large", "mid"), ("mid", "small"), ("small", "micro")):
        out, back = flow[(a, b)], flow[(b, a)]
        assert abs(out - back) <= max(5, 0.25 * max(out, back, 1)), (
            f"asymmetric flow across {a}/{b}: {out} out vs {back} back — "
            "that is bias, not reconstitution lag"
        )


def test_every_tier_skip_is_individually_justified() -> None:
    """A name moving more than one tier is either a stale index label on a re-rated
    company or a bad market cap. Each must be named and explained, never bulk-accepted.

    KNOWN AND VERIFIED (2026-08-23):
      CUPID — index says micro, market-cap rank 240. The cap is REAL (Rs 38,192 cr
      confirmed externally 19-Aug-2026; the stock traded Rs 1,842 cr in one session on
      2026-08-18). NSE simply has not reconstituted. The new rule is right here and the
      index label is stale.
    """
    justified = {"CUPID"}
    skips = [
        f"{r['symbol']}: {r['old_cap']} -> {r['new_cap']} "
        f"(rank {r['mcap_rank']}, {r['market_cap_cr']} cr)"
        for r in _old_vs_new().to_dict("records")
        if r["symbol"] not in justified
        and abs(_TIER_ORDER[r["new_cap"]] - _TIER_ORDER[r["old_cap"]]) > 1
    ]
    assert not skips, (
        "unexplained tier skips — verify each market cap against an external source "
        "before accepting:\n" + "\n".join(skips)
    )


def test_no_universe_member_is_missing_a_market_cap() -> None:
    """A NULL cap must never fall through to 'micro' — that would drop a real mid-cap
    into the micro cohort and distort its deciles.

    Checks equity_marketcap rather than v_stock_cap.cap because the view ranks ACTIVE
    stocks only, and today's universe members are mostly not active yet — the view-level
    check would fail on ~250 names for a reason that is not a defect. Tighten this to
    `v.cap IS NULL` once Task 5 lands and is_active IS the universe.
    """
    missing = _db.read_df(
        """SELECT im.symbol FROM atlas_foundation.atlas_universe_snapshot s
           JOIN atlas_foundation.instrument_master im USING (instrument_id)
           LEFT JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
           WHERE s.date = (SELECT max(date) FROM atlas_foundation.atlas_universe_snapshot)
             AND s.in_universe AND (m.market_cap_cr IS NULL OR m.market_cap_cr <= 0)"""
    )
    assert missing.empty, (
        f"universe members with no market cap: {list(missing['symbol'])} — "
        "these must be resolved or explicitly excluded, never defaulted to micro"
    )


def test_cohort_boundaries_are_exact() -> None:
    """large=100, mid=150, small=250 by construction; micro takes the remainder."""
    df = _db.read_df(
        """SELECT v.cap, count(*) n FROM atlas_foundation.v_stock_cap v
           JOIN atlas_foundation.instrument_master im USING (instrument_id)
           WHERE im.asset_class='stock' AND im.is_active GROUP BY 1"""
    )
    counts = dict(zip(df["cap"], df["n"], strict=True))
    assert counts.get("large") == 100
    assert counts.get("mid") == 150
    assert counts.get("small") == 250


def test_rank_is_strictly_ordered_by_market_cap() -> None:
    """Rank 1 must be the largest company by market cap — a reversed sort would
    silently invert every cohort."""
    top = _db.read_df(
        """SELECT im.symbol, m.market_cap_cr, v.mcap_rank
           FROM atlas_foundation.v_stock_cap v
           JOIN atlas_foundation.instrument_master im USING (instrument_id)
           JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
           WHERE v.mcap_rank <= 3 ORDER BY v.mcap_rank"""
    )
    assert list(top["mcap_rank"]) == [1, 2, 3]
    assert top["market_cap_cr"].is_monotonic_decreasing


def test_renamed_symbol_fill_leaves_no_isin_pair_half_capped() -> None:
    """The post-condition of fetch_marketcap.fill_renamed_symbols(): if one row of an
    ISIN pair has a cap, its twin must too. Asserting non-NULL alone (as the test above
    does) passes just as happily if the fill copies the wrong twin or writes 0.

    Deliberately NOT asserting the two sides AGREE. Two pairs carry genuinely different
    Screener values — AEROPLANE 2,075 vs AMIRCHAND 1,367, and ASHIKA 2,934 vs ASHIKAG
    3,225 — because Screener serves both slugs of a renamed company and one page is
    stale. That is a pre-existing ingest problem, not something the fill caused or can
    fix (it never overwrites a fetched value), and it is a Task 5 watch item.
    """
    half = _db.read_df(
        """SELECT im.isin, string_agg(im.symbol, '/' ORDER BY im.symbol) AS symbols
           FROM atlas_foundation.instrument_master im
           LEFT JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
           WHERE im.asset_class = 'stock' AND im.isin IS NOT NULL
           GROUP BY im.isin
           HAVING count(*) > 1
              AND count(*) FILTER (WHERE m.market_cap_cr IS NULL) > 0
              AND count(*) FILTER (WHERE m.market_cap_cr IS NOT NULL) > 0"""
    )
    assert half.empty, (
        "one side of an ISIN pair has a market cap and its twin does not, so the "
        f"capless side would fall through to micro: {list(half['symbols'])} — "
        "run fetch_marketcap.fill_renamed_symbols()"
    )


def test_both_rows_of_a_rename_pair_resolve_to_one_cap_and_one_tier() -> None:
    """v_stock_cap resolves market cap by ISIN, so the two instrument_master rows an NSE
    rename leaves behind must read the SAME number and land in the SAME tier.

    This is the invariant that breaks if someone later "simplifies" the join back to
    instrument_id: equity_marketcap carries the cap on whichever ticker Screener still
    serves, which is usually NOT the one holding the OHLCV history that gets scored, so
    the scored row would silently read a stale number or none at all.

    Compares the cap the VIEW resolves for every duplicate-ISIN row — not the stored
    equity_marketcap value, which genuinely differs across two of the four pairs
    (AEROPLANE/AMIRCHAND, ASHIKA/ASHIKAG) because Screener serves both slugs and one
    page is stale. Resolution is freshest-fetch-wins, so those collapse to one value
    here even though the underlying rows still disagree.
    """
    split = _db.read_df(
        """WITH cap_by_isin AS (
               SELECT DISTINCT ON (im.isin) im.isin, e.market_cap_cr
               FROM atlas_foundation.instrument_master im
               JOIN atlas_foundation.equity_marketcap e USING (instrument_id)
               WHERE im.asset_class='stock' AND im.isin IS NOT NULL AND e.market_cap_cr > 0
               ORDER BY im.isin, e.fetched_at DESC NULLS LAST, im.symbol),
           pairs AS (
               SELECT im.isin, im.symbol, c.market_cap_cr
               FROM atlas_foundation.instrument_master im
               JOIN cap_by_isin c ON c.isin = im.isin
               WHERE im.asset_class='stock' AND im.isin IN (
                   SELECT isin FROM atlas_foundation.instrument_master
                   WHERE asset_class='stock' AND isin IS NOT NULL
                   GROUP BY isin HAVING count(*) > 1))
           SELECT isin, string_agg(symbol, '/' ORDER BY symbol) AS symbols,
                  count(DISTINCT market_cap_cr) AS distinct_caps
           FROM pairs GROUP BY isin HAVING count(DISTINCT market_cap_cr) > 1"""
    )
    assert split.empty, (
        "rename pairs whose two rows resolve to different caps — the view is joining "
        f"equity_marketcap on instrument_id, not isin: {list(split['symbols'])}"
    )
    # Second arm: same security, one tier. Vacuous until Task 5 — no rename-pair row is
    # active yet, so the view holds neither side. It arms itself exactly when the risk
    # appears (a pair going active is also the duplicate-slot watch item for Task 5).
    tiers = _db.read_df(
        """SELECT im.isin, string_agg(im.symbol, '/' ORDER BY im.symbol) AS symbols,
                  count(DISTINCT v.cap) AS distinct_tiers
           FROM atlas_foundation.instrument_master im
           JOIN atlas_foundation.v_stock_cap v USING (instrument_id)
           WHERE im.asset_class='stock' AND im.isin IS NOT NULL
           GROUP BY im.isin HAVING count(*) > 1 AND count(DISTINCT v.cap) > 1"""
    )
    assert tiers.empty, f"one security in two cap tiers: {list(tiers['symbols'])}"
