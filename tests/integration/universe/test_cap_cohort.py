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
from pathlib import Path

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


def _old_vs_new():
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
    assert len(df) > 700, "expected the current active universe"
    return df


def test_disagreements_are_boundary_drift_not_bias() -> None:
    """Equal numbers must cross each boundary in each direction. Systematic one-way
    flow would mean the market-cap basis is wrong, not merely out of phase."""
    df = _old_vs_new()
    d = df[df["old_cap"] != df["new_cap"]]
    for a, b in (("large", "mid"), ("mid", "small"), ("small", "micro")):
        out = len(d[(d["old_cap"] == a) & (d["new_cap"] == b)])
        back = len(d[(d["old_cap"] == b) & (d["new_cap"] == a)])
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
    df = _old_vs_new()
    d = df[df["old_cap"] != df["new_cap"]].copy()
    d["jump"] = (d["new_cap"].map(_TIER_ORDER) - d["old_cap"].map(_TIER_ORDER)).abs()
    skips = d[(d["jump"] > 1) & (~d["symbol"].isin(justified))]
    assert skips.empty, (
        "unexplained tier skips — verify each market cap against an external source "
        f"before accepting:\n{skips.to_string(index=False)}"
    )


def test_no_universe_member_is_missing_a_market_cap() -> None:
    """A NULL cap must never fall through to 'micro' — that would drop a real mid-cap
    into the micro cohort and distort its deciles."""
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
