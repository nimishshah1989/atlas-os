"""Integration tests for the signal-evaluation loaders.

Read-only against the live DB. Forward returns come from ohlcv_stock.close_adj,
which is corporate-action adjusted and has zero NULLs across 1,976 trading dates.

Every expected value here is read back out of the live DB in the test itself
(rule #0 — no synthetic fixtures). Where a criterion is asserted, the test states
it independently in SQL rather than re-using the loader's own WHERE clause, so a
loader that drops the filter fails instead of agreeing with itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _db  # noqa: E402  # pyright: ignore[reportMissingImports]
import eval_signal as E  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.integration

# Each query below spells the "row carries signal" clause out literally rather than
# importing it from the loader — a test that borrowed the loader's own clause would agree
# with itself no matter what it said. The clause names the five per-instrument lenses;
# policy and composite are absent on purpose, being non-NULL even on placeholder rows.


def test_forward_returns_are_computed_in_sql_not_pandas() -> None:
    """The frame must arrive already reduced. ohlcv_stock is 6.1M rows and the box has
    2 vCPUs — pulling raw prices into pandas to shift them is the thing the
    data-engineering rule forbids."""
    df = E.forward_returns(start="2024-01-01", end="2024-03-31", horizons=(21,))
    assert not df.empty
    assert set(df.columns) >= {"instrument_id", "date", "fwd_21"}
    total = _db.scalar("SELECT count(*) FROM atlas_foundation.ohlcv_stock")
    assert len(df) < total / 10, (
        f"loader returned {len(df):,} of {total:,} rows — the date bounds are not in SQL"
    )
    # The window is ~60 sessions; anything near a full year means the bounds slipped.
    assert df["date"].nunique() < 120, f"{df['date'].nunique()} distinct dates for a Q1 window"


def test_forward_returns_stop_at_the_requested_end_date() -> None:
    """The upper bound is widened in SQL so lead() has rows to look forward into.
    That widening must be trimmed off again, or the caller silently gets extra dates."""
    df = E.forward_returns(start="2024-01-01", end="2024-03-31", horizons=(21,))
    assert str(df["date"].max()) <= "2024-03-31"
    assert str(df["date"].min()) >= "2024-01-01"


def test_last_sessions_of_window_still_carry_a_forward_return() -> None:
    """Without the widened upper bound the final max(horizons) sessions come back all
    NULL — a silent hole at the recent end of every study window."""
    df = E.forward_returns(start="2024-01-01", end="2024-03-31", horizons=(21,))
    last_date = df["date"].max()
    tail = df[df["date"] == last_date]
    assert tail["fwd_21"].notna().sum() > 100, (
        f"only {tail['fwd_21'].notna().sum()} non-NULL fwd_21 on {last_date} — "
        "the lookahead window is not being widened in SQL"
    )


def test_fwd_21_does_not_depend_on_which_other_horizons_were_requested() -> None:
    """A horizon's value is a property of the instrument's price history, not of the
    caller's argument list. A calendar-day cap on the lookahead breaks that: asking for
    21 alone looked ahead 63 days and returned NULL for thinly-traded names, while asking
    for 21 alongside 126 looked ahead 231 days and returned a real number for the same
    rows. The NULLs were an artifact of the cap, and they fell on the illiquid tail."""
    alone = E.forward_returns(start="2024-01-01", end="2024-03-31", horizons=(21,))
    together = E.forward_returns(start="2024-01-01", end="2024-03-31", horizons=(21, 126))
    merged = alone.merge(
        together[["instrument_id", "date", "fwd_21"]],
        on=["instrument_id", "date"],
        suffixes=("_alone", "_together"),
    )
    assert len(merged) == len(alone)
    assert merged["fwd_21_alone"].isna().sum() == merged["fwd_21_together"].isna().sum(), (
        "fwd_21 nullity changed with the requested horizon set — the lookahead is capped "
        "by calendar days and is inventing NULLs for thinly-traded names"
    )
    both = merged.dropna(subset=["fwd_21_alone", "fwd_21_together"])
    assert (both["fwd_21_alone"] - both["fwd_21_together"]).abs().max() < 1e-12


def test_forward_return_matches_a_hand_computed_value() -> None:
    """Reproduce one instrument's 21-session forward return from raw closes."""
    df = E.forward_returns(start="2024-06-03", end="2024-06-05", horizons=(21,))
    assert not df.empty
    row = df.dropna(subset=["fwd_21"]).iloc[0]

    closes = _db.read_df(
        """SELECT close_adj FROM atlas_foundation.ohlcv_stock
           WHERE instrument_id = :i AND date >= :d
           ORDER BY date LIMIT 22""",
        {"i": str(row["instrument_id"]), "d": str(row["date"])},
    )
    assert len(closes) == 22, "need 22 sessions to span a 21-session forward return"
    expected = float(closes["close_adj"].iloc[21]) / float(closes["close_adj"].iloc[0]) - 1
    assert abs(float(row["fwd_21"]) - expected) < 1e-6


def test_forward_return_is_null_not_zero_at_the_data_edge() -> None:
    """At the newest session there is nothing to look forward into, so the forward
    return does not exist and must arrive as NULL. A zero would read as 'flat over the
    next month' and drag the decile spread toward nothing.

    (No instrument in ohlcv_stock ever stops trading — all 2,611 run to the data edge —
    so the edge is where the absent-return case actually lives.)"""
    edge = str(_db.scalar("SELECT max(date) FROM atlas_foundation.ohlcv_stock"))
    df = E.forward_returns(start=edge, end=edge, horizons=(21,))
    assert not df.empty, f"expected price rows on the data edge {edge}"
    assert df["fwd_21"].isna().all(), (
        f"{df['fwd_21'].notna().sum()} rows carry a forward return on {edge}, "
        "which has no future — an absent return must be NULL, never 0"
    )


def test_scores_loader_excludes_null_lens_rows() -> None:
    """composite = 0.00 with all-NULL lenses is a NO-SIGNAL sentinel (839 instruments
    carry such rows predating their listing). Including them would rank ~750 zeros at
    the bottom of every date and manufacture a fake IC."""
    df = E.lens_scores(lens="technical", start="2019-01-01", end="2019-12-31")
    assert not df.empty
    assert df["score"].notna().all(), "loader must not return NULL scores"
    per_date = df.groupby("date").size()
    assert per_date.max() < 2000, (
        f"max {per_date.max()} rows on a date — the 2,093 placeholder rows are leaking in"
    )
    assert per_date.median() > 800, "2019 should have ~1,343 genuinely scored names"


def test_composite_loader_excludes_no_signal_sentinel_rows() -> None:
    """The one that matters. `composite` and `policy` are non-NULL on EVERY row,
    including the pre-listing placeholders — so filtering `<lens> IS NOT NULL` is a
    no-op for them and lets the 0.00 sentinels through. A row is a no-signal
    placeholder iff all five real lenses are NULL; that, not the lens's own
    nullability, is the criterion."""
    day = "2019-06-28"
    scored = _db.scalar(
        """SELECT count(*) FROM atlas_foundation.atlas_lens_scores_daily
           WHERE asset_class='stock' AND date=:d AND composite IS NOT NULL
             AND (technical IS NOT NULL OR fundamental IS NOT NULL OR valuation IS NOT NULL
                  OR catalyst IS NOT NULL OR flow IS NOT NULL)""",
        {"d": day},
    )
    everything = _db.scalar(
        """SELECT count(*) FROM atlas_foundation.atlas_lens_scores_daily
           WHERE asset_class='stock' AND date=:d""",
        {"d": day},
    )
    assert everything > scored, "fixture date must actually contain placeholder rows"

    df = E.lens_scores(lens="composite", start=day, end=day)
    assert len(df) == scored, (
        f"composite loader returned {len(df)} rows on {day}; "
        f"{scored} are genuinely scored and {everything} exist in total"
    )


def test_policy_loader_excludes_no_signal_sentinel_rows() -> None:
    """policy is a sector-level tailwind, so it is populated even for an instrument
    that had not listed yet. Same no-op-filter trap as composite."""
    day = "2019-06-28"
    scored = _db.scalar(
        """SELECT count(*) FROM atlas_foundation.atlas_lens_scores_daily
           WHERE asset_class='stock' AND date=:d AND policy IS NOT NULL
             AND (technical IS NOT NULL OR fundamental IS NOT NULL OR valuation IS NOT NULL
                  OR catalyst IS NOT NULL OR flow IS NOT NULL)""",
        {"d": day},
    )
    df = E.lens_scores(lens="policy", start=day, end=day)
    assert len(df) == scored


def test_genuine_zero_scores_are_kept() -> None:
    """The mirror of the sentinel rule: a lens that genuinely scored 0.00 is a real
    observation and must survive. Dropping it would be filtering on `> 0`, which is
    what the study must never do."""
    zero_day = _db.read_df(
        """SELECT date, count(*) AS n
           FROM atlas_foundation.atlas_lens_scores_daily
           WHERE asset_class='stock' AND catalyst = 0
             AND (technical IS NOT NULL OR fundamental IS NOT NULL OR valuation IS NOT NULL
                  OR catalyst IS NOT NULL OR flow IS NOT NULL)
           GROUP BY date ORDER BY date LIMIT 1"""
    )
    assert not zero_day.empty, "expected genuinely-zero catalyst scores to exist"
    day = str(zero_day["date"].iloc[0])
    df = E.lens_scores(lens="catalyst", start=day, end=day)
    assert (df["score"] == 0).sum() == int(zero_day["n"].iloc[0])


def test_unknown_lens_is_rejected() -> None:
    """The lens name is interpolated into SQL, so it must be validated, not trusted."""
    with pytest.raises(ValueError):
        E.lens_scores(lens="composite; DROP TABLE x", start="2024-01-01", end="2024-01-02")


def test_cap_cohorts_cover_the_scored_universe() -> None:
    """Cohort splits are only meaningful if most scored names carry a cap."""
    caps = E.cap_cohorts()
    assert set(caps.columns) == {"instrument_id", "cap"}
    assert caps["cap"].notna().all()
    assert caps["instrument_id"].is_unique
    scored = E.lens_scores(lens="technical", start="2026-08-21", end="2026-08-21")
    covered = scored["instrument_id"].isin(caps["instrument_id"]).mean()
    assert covered > 0.9, f"only {covered:.1%} of scored names have a cap cohort"
