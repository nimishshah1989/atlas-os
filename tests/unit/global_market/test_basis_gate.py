"""``validate_global --check BASIS`` — its statistics and its verdict, on real measurements.

Rule #0 leaves no room for a hand-made price series here, so nothing below invents one. Every
number is either

* a REAL measurement — the gate's own run on 2026-09-07 against the Stooq archive in
  ``atlas_p1e_fix`` (2,513 sessions, 2016-09-06 → 2026-09-03) versus FRED's ``SP500``, the
  same figures the module's constant block records and ``tests/integration/global_market/
  test_basis_gate_db.py`` re-measures against the database; or
* a real FRED series read from the committed export ``tests/fixtures/global/macro/DTB3.csv``; or
* the module's OWN constant, where the point of the test IS the boundary that constant draws.

What is NOT proven here: no split-only equity archive exists to measure, so the
``split_only`` branch is pinned at the constants that define it rather than demonstrated on a
second real feed. The gate's job is to notice if one ever appears.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.global_market.providers.fred import parse_fred_csv
from tests.unit.global_market.live_files import FIXTURES
from tests.unit.global_market.script_loader import load_global_script

vg = load_global_script("validate_global")

DTB3_CSV = FIXTURES / "macro" / "DTB3.csv"

# The gate's printed run, 2026-09-07 (recorded in the BASIS constant block of the gate).
MEASURED_SESSIONS = 2513
MEASURED_CORR = 0.998352
MEASURED_TREND = 0.99712
MEASURED_EXCESS = 0.016339
MEASURED_RATIO_FIRST, MEASURED_RATIO_LAST = 0.086514, 0.099793
# The endpoints of that window: SPY's Stooq close and FRED SP500 on 2016-09-06 / 2026-09-03.
SPY_FIRST, SPY_LAST = 189.162, 773.17
IDX_FIRST, IDX_LAST = 2186.48, 7747.71
SPAN_YEARS = 9.9904

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def dtb3() -> pd.DataFrame:
    return parse_fred_csv(DTB3_CSV.read_text(), "DTB3")


# ── the statistics, on the real window's real endpoints ──


def test_cagr_reproduces_the_measured_ten_year_growth_of_both_series() -> None:
    spy = vg._cagr(SPY_FIRST, SPY_LAST, SPAN_YEARS)
    idx = vg._cagr(IDX_FIRST, IDX_LAST, SPAN_YEARS)
    print(f"SPY {spy:.6%}/yr vs SP500 {idx:.6%}/yr → excess {spy - idx:+.6%}/yr")
    assert spy == pytest.approx(0.15134, abs=1e-5)
    assert idx == pytest.approx(0.13500, abs=1e-5)
    assert spy - idx == pytest.approx(MEASURED_EXCESS, abs=1e-5)


def test_the_ratio_walk_and_the_cagr_excess_agree_the_way_compounding_says_they_must() -> None:
    """Check (2a)'s level drift and check (3)'s annual excess measure ONE fact, but not with
    one number: the ratio walk annualises to the GEOMETRIC excess (1.4396%/yr), while the
    gate reports the ARITHMETIC difference of the two CAGRs (1.6339%/yr). The two differ by
    exactly the factor (1 + index CAGR) — which pins which definition the band is drawn
    around, and would catch either statistic silently changing to the other."""
    geometric = (MEASURED_RATIO_LAST / MEASURED_RATIO_FIRST) ** (1 / SPAN_YEARS) - 1
    index_cagr = vg._cagr(IDX_FIRST, IDX_LAST, SPAN_YEARS)
    print(f"geometric {geometric:.6%}/yr × (1 + {index_cagr:.4%}) = {MEASURED_EXCESS:.6%}/yr")
    assert geometric == pytest.approx(0.014396, abs=2e-5)
    assert geometric * (1 + index_cagr) == pytest.approx(MEASURED_EXCESS, abs=2e-5)


def test_rank_trend_is_one_for_a_real_series_that_only_rises(dtb3: pd.DataFrame) -> None:
    """The committed export's observation dates ascend — a real, ordered record."""
    ordinals = pd.Series([d.toordinal() for d in dtb3["date"]], dtype=float)
    assert vg._rank_trend(ordinals) == pytest.approx(1.0)


def test_rank_trend_rejects_a_real_series_that_does_not_walk_one_way(dtb3: pd.DataFrame) -> None:
    """The same export's VALUES: a real T-bill rate that rose to 2019, collapsed to zero
    through 2020–21 and rose again. It reads 0.616 — below the floor, as a series with a real
    reversal in it must. Check (2a) therefore rejects drift that is not one-way."""
    trend = vg._rank_trend(dtb3["value"].astype(float))
    print(f"real DTB3 rate rank-trend {trend:.6f} vs floor {vg.BASIS_MIN_RATIO_TREND}")
    assert trend == pytest.approx(0.615826, abs=1e-5)
    assert trend < vg.BASIS_MIN_RATIO_TREND


def test_a_flat_ratio_scores_zero_and_a_constant_one_is_not_a_number(dtb3: pd.DataFrame) -> None:
    """A ratio that never moves — the shape a split-only archive would produce against a
    price index — has no variance, so the rank correlation is NaN. It must not crash, and
    NaN must fail the floor rather than sneak past it."""
    flat = dtb3["value"].astype(float) / dtb3["value"].astype(float)
    trend = vg._rank_trend(flat)
    assert pd.isna(trend)
    assert not trend >= vg.BASIS_MIN_RATIO_TREND  # NaN comparisons are False either way
    assert vg.basis_verdict(0.0, trend) == "split_only"


# ── the verdict, at its own boundaries ──


def test_the_measured_archive_is_named_total_return() -> None:
    assert vg.basis_verdict(MEASURED_EXCESS, MEASURED_TREND) == "total_return"


def test_the_dividend_band_edges_are_inclusive() -> None:
    lo, hi = vg.BASIS_CAGR_EXCESS_BAND
    assert vg.basis_verdict(lo, MEASURED_TREND) == "total_return"
    assert vg.basis_verdict(hi, MEASURED_TREND) == "total_return"


def test_a_doubled_adjustment_is_above_the_band_and_names_nothing() -> None:
    """Twice the measured excess (3.27%/yr) is what a double-counted dividend adjustment
    would read. It is outside the band by construction, so it must not pass as total_return."""
    _, hi = vg.BASIS_CAGR_EXCESS_BAND
    assert MEASURED_EXCESS * 2 > hi
    assert vg.basis_verdict(MEASURED_EXCESS * 2, MEASURED_TREND) == "indeterminate"


def test_a_flat_ratio_is_never_total_return_however_big_the_excess() -> None:
    """Check (2a) is necessary, not decorative: back-adjustment is monotone by construction,
    so an excess without a one-way walk is some other effect and must not be labelled."""
    lo, hi = vg.BASIS_CAGR_EXCESS_BAND
    assert vg.basis_verdict(lo, 0.0) == "indeterminate"
    assert vg.basis_verdict(hi, 0.0) == "indeterminate"


def test_no_dividend_drift_is_named_split_only() -> None:
    zero = vg.basis_verdict(0.0, MEASURED_TREND)
    ceiling = vg.basis_verdict(vg.BASIS_SPLIT_ONLY_MAX_CAGR_EXCESS, MEASURED_TREND)
    assert zero == ceiling == "split_only"


def test_the_gap_between_the_bands_names_neither_basis() -> None:
    """Between the split-only ceiling and the dividend floor the evidence supports neither
    reading, and an inconclusive gate must not answer as though it did."""
    lo, _ = vg.BASIS_CAGR_EXCESS_BAND
    ceiling = vg.BASIS_SPLIT_ONLY_MAX_CAGR_EXCESS
    assert ceiling < lo, "the gap must exist, or 'indeterminate' has nowhere to live"
    assert vg.basis_verdict((ceiling + lo) / 2, MEASURED_TREND) == "indeterminate"


def test_only_total_return_lets_the_gate_pass() -> None:
    """The exit status keys off check (4): both other labels must register a failure."""
    for excess in (0.0, (vg.BASIS_SPLIT_ONLY_MAX_CAGR_EXCESS + vg.BASIS_CAGR_EXCESS_BAND[0]) / 2):
        g = vg.Gate()
        basis = vg.basis_verdict(excess, MEASURED_TREND)
        g.check("(4) the measured basis is total_return", basis == "total_return", basis)
        assert g.fails == 1, basis


# ── the constants themselves ──


def test_every_threshold_sits_on_the_safe_side_of_the_measurement() -> None:
    """Each constant must leave the measured value room to move without a false alarm, and
    still exclude the reading it is there to exclude."""
    lo, hi = vg.BASIS_CAGR_EXCESS_BAND
    assert 0 < vg.BASIS_SPLIT_ONLY_MAX_CAGR_EXCESS < lo < MEASURED_EXCESS < hi
    assert 0 < vg.BASIS_MIN_RETURN_CORR < MEASURED_CORR < 1
    assert 0 < vg.BASIS_MIN_RATIO_TREND < MEASURED_TREND <= 1
    assert vg.BASIS_MIN_SESSIONS < MEASURED_SESSIONS
    # The measured spot deviation (0.207%) must sit well inside the tolerance.
    assert abs(MEASURED_RATIO_LAST / vg.BASIS_SPOT_RATIO - 1) < vg.BASIS_SPOT_RATIO_TOL / 5


def test_the_check_choices_offer_both_gates() -> None:
    assert vg.BASIS_SYMBOL == "SPY" and vg.BASIS_INDEX_SERIES == "SP500"
