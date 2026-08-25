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
from collections.abc import Iterator
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


# --- Task 3: journal table + backfill driver ---------------------------------------
#
# The plan's era boundary (2024-04-01) is not where the break is. Measured here, in the
# test, rather than trusted: 2024-05-31 carries 1,936 scored names and 2024-06-03 carries
# 473. test_era_boundaries_land_on_the_real_universe_breaks holds that to the live DB.


@pytest.fixture(scope="module")
def journal() -> Iterator[str]:
    """A scratch journal for the tests that WRITE, so they never touch the live one.

    atlas_signal_ic is keyed by (lens, horizon_d, cohort, era) with no window in the key,
    so `backfill(2023-01-01 .. 2023-06-30)` replaces the full 2019-2024 'wide' row for that
    key with a six-month recompute. Nothing heals it: the nightly step spans the trailing
    two years and so never recomputes the wide era at all. Pointing the tests at a window
    that cannot collide is not available — every window inside an era maps to the same key.
    """
    table = f"{E.M}.atlas_signal_ic_pytest"
    E.ensure_table(table)
    yield table
    _db.exec_sql(f"DROP TABLE IF EXISTS {table}")


def _scored_on(day: str) -> int:
    return int(
        _db.scalar(
            """SELECT count(*) FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date = :d
                 AND (technical IS NOT NULL OR fundamental IS NOT NULL
                      OR valuation IS NOT NULL OR catalyst IS NOT NULL OR flow IS NOT NULL)""",
            {"d": day},
        )
    )


def test_era_boundaries_land_on_the_real_universe_breaks() -> None:
    """An era exists to stop an IC being averaged across a change in the universe, so
    each boundary must sit ON the change. The last session of an era and the first
    session of the next one must differ sharply in cross-section size; two sessions
    inside one era must not."""
    for _, lo, hi in E.ERAS:
        if hi > "2026-08-24":  # open-ended final era: nothing after it to compare
            continue
        last = _db.scalar(
            """SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date <= :d
                 AND (technical IS NOT NULL OR fundamental IS NOT NULL
                      OR valuation IS NOT NULL OR catalyst IS NOT NULL OR flow IS NOT NULL)""",
            {"d": hi},
        )
        nxt = _db.scalar(
            """SELECT min(date) FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date > :d
                 AND (technical IS NOT NULL OR fundamental IS NOT NULL
                      OR valuation IS NOT NULL OR catalyst IS NOT NULL OR flow IS NOT NULL)""",
            {"d": hi},
        )
        a, b = _scored_on(str(last)), _scored_on(str(nxt))
        assert abs(b - a) / max(a, b) > 0.25, (
            f"era ending {hi}: {last} has {a} scored names, {nxt} has {b} — "
            "that is not a structural break, the boundary is in the wrong place"
        )
        # ...and the era is internally stable across the session before its own end.
        prev = _db.scalar(
            """SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date < :d
                 AND (technical IS NOT NULL OR fundamental IS NOT NULL
                      OR valuation IS NOT NULL OR catalyst IS NOT NULL OR flow IS NOT NULL)""",
            {"d": str(last)},
        )
        if prev is not None and str(prev) >= lo:
            p = _scored_on(str(prev))
            assert abs(a - p) / max(a, p) < 0.25, (
                f"{prev} -> {last} jumps {p} -> {a} inside era ending {hi}"
            )


def test_backfill_writes_one_row_per_lens_horizon_cohort_era(journal: str) -> None:
    E.backfill(
        start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,), table=journal
    )

    df = _db.read_df(
        f"""SELECT lens, horizon_d, cohort, era, n_dates, mean_n, mean_ic, hit_rate,
                   mean_spread, cap_coverage
            FROM {journal}
            WHERE lens = 'technical' AND horizon_d = 21 AND era = 'wide'"""
    )
    assert not df.empty
    assert set(df["cohort"]) <= {"all", "large", "mid", "small", "micro"}
    assert "all" in set(df["cohort"]), "the pooled cross-section is the headline number"
    assert (df["n_dates"] > 0).all()
    assert df.set_index("cohort").loc["all", "cap_coverage"] == 1


def test_cap_less_rows_are_dropped_from_the_bands_never_defaulted_to_micro(journal: str) -> None:
    """v_stock_cap has no date dimension, so 43% of the wide era's scored rows carry no
    cap band. Defaulting them to 'micro' would invent a cohort label for exactly the
    names that later left the universe. They belong in 'all' and nowhere else."""
    E.backfill(
        start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,), table=journal
    )
    df = _db.read_df(
        f"""SELECT cohort, mean_n, cap_coverage FROM {journal}
            WHERE lens='technical' AND horizon_d=21 AND era='wide'"""
    ).set_index("cohort")

    pooled = float(df.loc["all", "mean_n"])
    banded = float(df.drop(index="all")["mean_n"].sum())
    covered = _db.scalar(
        """SELECT avg((c.instrument_id IS NOT NULL)::int)
           FROM atlas_foundation.atlas_lens_scores_daily s
           LEFT JOIN atlas_foundation.v_stock_cap c USING (instrument_id)
           WHERE s.asset_class='stock' AND s.date BETWEEN '2023-01-01' AND '2023-06-30'
             AND (s.technical IS NOT NULL OR s.fundamental IS NOT NULL
                  OR s.valuation IS NOT NULL OR s.catalyst IS NOT NULL OR s.flow IS NOT NULL)"""
    )
    assert float(covered) < 0.95, "fixture window must actually contain cap-less rows"
    assert banded < pooled * 0.95, (
        f"bands sum to {banded:.0f} of a {pooled:.0f}-name cross-section — cap-less rows "
        "are being defaulted into a band instead of dropped"
    )
    assert float(df.loc["micro", "cap_coverage"]) == pytest.approx(float(covered), abs=0.02)


def test_backfill_is_idempotent(journal: str) -> None:
    E.backfill(
        start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,), table=journal
    )
    n1 = _db.scalar(f"SELECT count(*) FROM {journal}")
    E.backfill(
        start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,), table=journal
    )
    n2 = _db.scalar(f"SELECT count(*) FROM {journal}")
    assert n1 == n2, f"re-running duplicated rows: {n1} -> {n2}"


def test_eras_are_reported_separately_never_blended(journal: str) -> None:
    """The scored cross-section goes 1,936 names/date (to 2024-05-31) -> 473 the next
    session -> 1,198 from 2026-08-21. A single blended IC across those breaks is
    uninterpretable, so era is part of the key."""
    E.backfill(
        start="2023-01-01", end="2023-03-31", lenses=("technical",), horizons=(21,), table=journal
    )
    E.backfill(
        start="2025-01-01", end="2025-03-31", lenses=("technical",), horizons=(21,), table=journal
    )
    eras = _db.read_df(f"SELECT DISTINCT era FROM {journal} WHERE lens='technical'")
    assert {"wide", "narrow"} <= set(eras["era"]), "2023 and 2025 collapsed into one era"


# --- Task 4: sanity gates on the LIVE journal -----------------------------------------
#
# These read atlas_signal_ic itself — the production result, not a scratch table. That is
# the point: they are gates on what the board will publish, so they must see what it sees.


def test_no_lens_reports_an_implausibly_high_ic() -> None:
    """|IC| > 0.15 sustained does not happen in equities. If it appears, the most likely
    causes are NULL placeholder rows leaking in (composite = 0.00 for 839 instruments)
    or a forward return overlapping the scoring date. Fail loudly rather than celebrate.

    The ceiling is 0.15 and stays there. The largest |mean_ic| in the journal today is
    0.125 (technical/63/narrow/micro, 61 names), so this has real headroom — tightening it
    to hug that number would make it fire on ordinary drift instead of on a bug.
    """
    df = _db.read_df(
        "SELECT lens, era, cohort, horizon_d, mean_ic, n_dates "
        "FROM atlas_foundation.atlas_signal_ic WHERE abs(mean_ic) > 0.15 AND n_dates > 60"
    )
    assert df.empty, f"implausible IC — investigate before trusting:\n{df.to_string()}"


def test_the_cross_section_matches_the_known_era_shape() -> None:
    """Guards the NULL-exclusion. 2,093 of 2,093 rows on a 2019 date are non-NULL for
    composite and policy, of which 755 predate their instrument's listing. If those
    placeholders leak in, the pooled wide-era cross-section jumps toward 2,093 instead of
    the measured 1,343-1,769 — so the bound is on mean_n, the cross-section itself, not
    only on how many dates were covered."""
    n = _db.scalar("SELECT max(n_dates) FROM atlas_foundation.atlas_signal_ic WHERE era = 'wide'")
    assert n and n > 100, "wide era should span hundreds of dates"

    widest = _db.read_df(
        """SELECT lens, horizon_d, mean_n FROM atlas_foundation.atlas_signal_ic
           WHERE era = 'wide' AND cohort = 'all' ORDER BY mean_n DESC LIMIT 1"""
    )
    assert not widest.empty, "wide era should carry a pooled cohort"
    assert float(widest["mean_n"].iloc[0]) < 2000, (
        f"pooled wide-era cross-section is {widest['mean_n'].iloc[0]:.0f} names/date — "
        f"the 2,093 placeholder rows are leaking in:\n{widest.to_string()}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN UNFIXED DEFECT in atlas_foundation.ohlcv_stock, not in this study. 28,507 "
        "rows across 86 instruments carry close_adj < 1 before 2024-06 — PRIVISCL closes at "
        "0.05 on 2020-03-23 with adj_factor = 1.0, so the RAW close is wrong and no "
        "adjustment can be blamed. A 0.05 -> 539 recovery is a 10,777x return. Rank-IC "
        "shrugs (it ranks first either way), the arithmetic decile spread does not: "
        "composite/126/wide/small reads +2811%. Fix the prices in ohlcv_stock, then remove "
        "this xfail — strict=True makes it fail the moment the fix lands."
    ),
)
def test_no_decile_spread_is_large_enough_to_be_a_price_defect() -> None:
    """A top-minus-bottom decile spread past +/-100% over 126 sessions is not a market
    move, it is a broken price. mean_spread is an arithmetic mean of per-date decile
    spreads, so one 10,777x forward return drags the whole era's number with it."""
    df = _db.read_df(
        """SELECT lens, horizon_d, cohort, era, n_dates, mean_n, mean_ic, mean_spread
           FROM atlas_foundation.atlas_signal_ic
           WHERE abs(mean_spread) > 1.0 ORDER BY abs(mean_spread) DESC"""
    )
    assert df.empty, (
        f"{len(df)} decile spreads exceed +/-100% — a price defect, not a return:\n{df.to_string()}"
    )
