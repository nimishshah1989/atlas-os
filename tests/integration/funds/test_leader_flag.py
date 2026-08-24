"""Integration tests for atlas_foundation.v_stock_leader — the single LEADER rule.

The leader flag was written five times in SQL and disagreed with itself. The funds
page used lead = (d_composite >= 10) filtered on >= 1; build_fund_rank_history.py and
verify_fund_rank.py used lead = (d_tech >= 9) + (d_flow >= 9) filtered on >= 2. On
2026-08-18 that was 73 leaders vs 25, only 17 in common — so fund_rank_daily.breadth
was a different number from the breadth the fund page displayed, and the DoD gate could
not see it because the verifier copied the builder's rule rather than production's.

These tests assert on REAL rows only (rule #0). They are deliberately tie-safe: SQL
ntile breaks ties at a decile edge in plan-dependent order, so a test that re-derives
bucket numbers would be flaky. What is asserted instead are the properties the rule
actually claims — leaders are the TOP names by composite within their cap cohort, the
flag is 0/1, and breadth distinguishes a real 0% from a genuine unknown.
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


@pytest.fixture(scope="module")
def latest_date() -> str:
    """The latest scored day — the one the funds/ETF pages render."""
    return str(
        _db.scalar(
            """SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock'"""
        )
    )


def test_view_covers_every_scored_stock_on_the_latest_date(latest_date: str) -> None:
    """A stock scored on the latest lens date but absent from the view would be dropped
    by every roll-up's INNER JOIN — silently shrinking the breadth base, not erroring."""
    n_missing = _db.scalar(
        """SELECT count(*)
           FROM atlas_foundation.atlas_lens_scores_daily l
           JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
           LEFT JOIN atlas_foundation.v_stock_leader v
             ON v.instrument_id = l.instrument_id AND v.date = l.date
           WHERE l.asset_class='stock' AND l.date = :d AND v.lead IS NULL""",
        {"d": latest_date},
    )
    assert n_missing == 0, f"{n_missing} scored stocks have no leader flag"


def test_leader_flag_is_zero_or_one(latest_date: str) -> None:
    """The retired 2-lens rule summed two flags and could return 2. A lead of 2 anywhere
    means that rule has leaked back in."""
    bad = _db.scalar(
        """SELECT count(*) FROM atlas_foundation.v_stock_leader
           WHERE date = :d AND lead NOT IN (0,1)""",
        {"d": latest_date},
    )
    assert bad == 0, f"{bad} rows carry a leader flag outside 0/1"


def test_leaders_are_the_top_names_by_composite_within_their_cap_cohort(latest_date: str) -> None:
    """The rule's whole claim: within a cap cohort no non-leader outscores a leader.

    Equality is allowed — two names on the decile edge can share a composite, and which
    one ntile puts in D10 is arbitrary. A genuine break (a leader scored BELOW a
    non-leader) means the flag is not derived from composite at all.
    """
    df = _db.read_df(
        """SELECT COALESCE(c.cap,'micro') AS cap,
                  min(l.composite) FILTER (WHERE v.lead = 1) AS min_leader,
                  max(l.composite) FILTER (WHERE v.lead = 0) AS max_other
           FROM atlas_foundation.v_stock_leader v
           JOIN atlas_foundation.atlas_lens_scores_daily l
             ON l.instrument_id = v.instrument_id AND l.date = v.date AND l.asset_class='stock'
           LEFT JOIN atlas_foundation.v_stock_cap c ON c.instrument_id = v.instrument_id
           WHERE v.date = :d AND l.composite IS NOT NULL
           GROUP BY 1""",
        {"d": latest_date},
    )
    assert not df.empty, "no leader rows on the latest lens date"
    breaks = [
        (cap, float(lo), float(hi))
        for cap, lo, hi in zip(df["cap"], df["min_leader"], df["max_other"], strict=True)
        if lo == lo and hi == hi and lo < hi  # NaN = cohort with no leader / no other
    ]
    assert not breaks, f"leaders scored below non-leaders in the same cohort: {breaks}"


def test_leaders_are_about_a_tenth_of_each_cap_cohort(latest_date: str) -> None:
    """Top DECILE — so ~10% per cohort. Wider than that and the cut is not a decile."""
    df = _db.read_df(
        """SELECT COALESCE(c.cap,'micro') AS cap, count(*) AS n, sum(v.lead) AS n_lead
           FROM atlas_foundation.v_stock_leader v
           LEFT JOIN atlas_foundation.v_stock_cap c ON c.instrument_id = v.instrument_id
           WHERE v.date = :d
           GROUP BY 1""",
        {"d": latest_date},
    )
    off = [
        (cap, int(n_lead), int(n))
        for cap, n_lead, n in zip(df["cap"], df["n_lead"], df["n"], strict=True)
        if not 0.08 <= int(n_lead) / int(n) <= 0.12
    ]
    assert not off, f"leader share is not a decile in {off}"


def test_fund_breadth_is_zero_not_null_when_no_holding_is_a_leader() -> None:
    """A fund holding scored names of which none lead has breadth 0%, not "unknown".

    NULL is reserved for a fund with NO scored holdings — which the roll-up's INNER JOIN
    excludes from the result entirely, so a row that exists must carry a number.
    """
    import verify_fund_rank as v  # pyright: ignore[reportMissingImports]

    df = _db.read_df(v.PROD_QUERY)
    nulls = df["breadth"].isna().sum()
    zeros = (df["breadth"] == 0).sum()
    assert nulls == 0, f"{nulls} funds with scored holdings report NULL breadth"
    assert zeros > 0, "no fund has zero breadth — the zero case is not being exercised"


def test_builder_at_the_latest_date_matches_the_latest_date_path(latest_date: str) -> None:
    """The builder reads the leader flag for an arbitrary day (:d) so it can backfill;
    the page reads it for max(date). Asked for the same day they must return the same
    breadth — otherwise the builder's date wiring, not the rule, is the defect.

    This does NOT prove the builder agrees with the FUNDS PAGE: both queries live in
    Python. That is what test_leader_rule_single_source.py is for — the rule itself is
    the view, and the guard is that no consumer re-derives it.
    """
    import build_fund_rank_history as b  # pyright: ignore[reportMissingImports]
    import verify_fund_rank as v  # pyright: ignore[reportMissingImports]

    built = _db.read_df(b.ROLLUP_SQL, {"d": latest_date}).set_index("mstar_id")["breadth"]
    page = _db.read_df(v.PROD_QUERY).set_index("mstar_id")["breadth"]
    assert set(built.index) == set(page.index), "builder and page rank different fund cohorts"
    diff = (built - page.reindex(built.index)).abs()
    worst = diff.max()
    assert worst < 1e-9, f"breadth differs on {(diff > 1e-9).sum()} funds, worst {worst}"
