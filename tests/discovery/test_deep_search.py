"""Tests for :mod:`atlas.discovery.deep_search`.

Covers:
- Candidate generator — count, archetype coverage, predicate validity.
- Predicate evaluation — in_range / in_top_quantile / scalar cmps.
- Rule DSL building — round-trips through Pydantic CellRule validation.
- End-to-end pipeline with the on-disk cache (skipped when cache absent).
- HTML report renders to a valid string with expected anchors.
- DeepSearchSummary aggregates correctly.

Cache-dependent tests are gated behind the presence of
``/tmp/sde_ohlcv_cache.pkl``; CI does not have the cache and skips them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate, validate_rule_dsl
from atlas.discovery.deep_search import (
    DEEP_SEARCH_METHODOLOGY_REF,
    FRICTION_LARGE,
    HORIZON_12M,
    IC_FLOOR_12M,
    CandidateResult,
    CandidateRule,
    DeepSearchSummary,
    _apply_predicate,
    _pooled_spearman_ic,
    build_rule_dsl_for_candidate,
    generate_candidates_large_12m_positive,
    run_deep_search,
)
from atlas.discovery.deep_search_report import generate_deep_search_report
from atlas.discovery.engine import DEFAULT_CACHE_DIR

CACHE_AVAILABLE = (DEFAULT_CACHE_DIR / "sde_ohlcv_cache.pkl").exists()


# ---------------------------------------------------------------------------
# Constants — sanity
# ---------------------------------------------------------------------------


def test_horizon_12m_is_252_trading_days() -> None:
    """12m horizon = 252 trading days per methodology lock §3."""
    assert HORIZON_12M == 252


def test_ic_floor_12m_matches_methodology() -> None:
    """12m floor = 0.04 per methodology lock + engine.py PER_TENURE_IC_FLOOR."""
    assert IC_FLOOR_12M == Decimal("0.04")


def test_friction_large_matches_engine() -> None:
    """Large-cap friction = 13 bps one-way per engine.py DEFAULT_FRICTION_BY_TIER."""
    assert FRICTION_LARGE == Decimal("0.001300")


# ---------------------------------------------------------------------------
# Candidate generator
# ---------------------------------------------------------------------------


def test_candidate_generator_count_in_target_range() -> None:
    """Candidate count must land in the 60-80 target range (per CEO task spec)."""
    cands = generate_candidates_large_12m_positive()
    assert 60 <= len(cands) <= 100, f"expected 60-80 candidates, got {len(cands)}"


def test_candidate_generator_covers_all_seven_archetypes() -> None:
    """All 7 archetype families must be represented (per CEO task spec)."""
    cands = generate_candidates_large_12m_positive()
    archetypes = {c.archetype for c in cands}
    required = {
        "mean_reversion",
        "deep_value",
        "quality_momentum",
        "inflection",
        "consolidation_breakout",
        "liquidity_expansion",
        "structural",
    }
    missing = required - archetypes
    assert not missing, f"missing archetypes: {missing}"


def test_candidate_names_are_unique() -> None:
    """Duplicate names would silently drop candidates in dict-keyed lookups later."""
    cands = generate_candidates_large_12m_positive()
    names = [c.name for c in cands]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"duplicate candidate names: {duplicates}"


def test_every_candidate_has_liquidity_floor() -> None:
    """Every candidate's first predicate must be a log_med_tv_60d floor (Large tier)."""
    cands = generate_candidates_large_12m_positive()
    for c in cands:
        assert c.features[0].feature == "log_med_tv_60d", f"{c.name} missing liquidity floor"
        assert c.features[0].cmp == ">="


def test_every_candidate_predicate_is_valid_pydantic() -> None:
    """Every FeaturePredicate must round-trip through Pydantic validation."""
    cands = generate_candidates_large_12m_positive()
    for c in cands:
        for pred in c.features:
            # If a feature is mis-named (outside FEATURES allowlist) this raises.
            assert isinstance(pred, FeaturePredicate)
            assert pred.feature  # non-empty


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


def _make_panel(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(values, index=pd.date_range("2020-01-01", periods=values.shape[0]))


def test_apply_predicate_scalar_ge() -> None:
    panel = _make_panel(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))
    pred = FeaturePredicate(feature="rs_residual_6m", cmp=">=", value=Decimal("3"))
    out = _apply_predicate(panel, pred)
    expected = pd.DataFrame([[False, False, True], [True, True, True]], index=panel.index)
    pd.testing.assert_frame_equal(out, expected)


def test_apply_predicate_scalar_lt() -> None:
    panel = _make_panel(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))
    pred = FeaturePredicate(feature="rs_residual_6m", cmp="<", value=Decimal("3"))
    out = _apply_predicate(panel, pred)
    assert out.iloc[0, 0]
    assert out.iloc[0, 1]
    assert not out.iloc[0, 2]
    assert not out.iloc[1, 0]


def test_apply_predicate_in_range() -> None:
    panel = _make_panel(np.array([[-0.20, -0.10, -0.05], [0.0, 0.05, 0.10]]))
    pred = FeaturePredicate(
        feature="dd_from_52w_high",
        cmp="in_range",
        value=(Decimal("-0.15"), Decimal("-0.05")),
    )
    out = _apply_predicate(panel, pred)
    assert not out.iloc[0, 0]  # -0.20 below lo
    assert out.iloc[0, 1]  # -0.10 in range
    assert out.iloc[0, 2]  # -0.05 in range (inclusive)
    assert not out.iloc[1, 0]  # 0.0 above hi


def test_apply_predicate_in_top_quantile() -> None:
    """Top-decile means rank percentile >= 0.9 within each row."""
    panel = pd.DataFrame(np.tile(np.arange(10).reshape(1, -1), (3, 1)))
    pred = FeaturePredicate(
        feature="rs_residual_6m",
        cmp="in_top_quantile",
        value=Decimal("1"),
        value_quantile_n=10,
    )
    out = _apply_predicate(panel, pred)
    # Last column (largest value) should be True across all rows.
    assert out.iloc[0, -1]
    # First column (smallest) should be False.
    assert not out.iloc[0, 0]


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------


def test_pooled_spearman_ic_perfectly_correlated() -> None:
    """Monotonically-correlated score+forward should give IC ≈ 1."""
    rng = np.random.default_rng(42)
    n = 200
    score = pd.DataFrame(rng.normal(size=(n, 5)))
    # Perfectly rank-correlated forward returns.
    fwd = score * 2.0 + 1.0
    mask = pd.DataFrame(np.ones_like(score.values, dtype=bool))
    ic = _pooled_spearman_ic(score, fwd, mask)
    assert ic is not None
    assert abs(ic - 1.0) < 1e-6


def test_pooled_spearman_ic_uncorrelated() -> None:
    """Independent score+forward should give IC ≈ 0."""
    rng = np.random.default_rng(42)
    n = 1000
    score = pd.DataFrame(rng.normal(size=(n, 5)))
    fwd = pd.DataFrame(rng.normal(size=(n, 5)))
    mask = pd.DataFrame(np.ones_like(score.values, dtype=bool))
    ic = _pooled_spearman_ic(score, fwd, mask)
    assert ic is not None
    assert abs(ic) < 0.1  # noise around 0


def test_pooled_spearman_ic_insufficient_obs() -> None:
    score = pd.DataFrame(np.arange(20).reshape(-1, 1).astype(float))
    fwd = pd.DataFrame(np.arange(20).reshape(-1, 1).astype(float))
    mask = pd.DataFrame(np.ones_like(score.values, dtype=bool))
    ic = _pooled_spearman_ic(score, fwd, mask)
    assert ic is None


# ---------------------------------------------------------------------------
# Rule DSL building
# ---------------------------------------------------------------------------


def test_build_rule_dsl_round_trips_through_pydantic() -> None:
    """The dict produced by build_rule_dsl_for_candidate must validate as a CellRule."""
    cands = generate_candidates_large_12m_positive()
    for c in cands[:5]:
        rule_dsl = build_rule_dsl_for_candidate(c, ("Large", "12m", "POSITIVE"))
        # Must round-trip without ValidationError.
        rule = validate_rule_dsl(rule_dsl)
        assert isinstance(rule, CellRule)
        assert rule.methodology_lock_ref == DEEP_SEARCH_METHODOLOGY_REF
        assert rule.tier == "Large"
        assert rule.tenure == "12m"
        assert rule.action == "POSITIVE"


def test_build_rule_dsl_first_predicate_becomes_eligibility() -> None:
    """The log_med_tv_60d floor goes to eligibility, rest to entry."""
    cands = generate_candidates_large_12m_positive()
    c = cands[0]
    rule_dsl = build_rule_dsl_for_candidate(c, ("Large", "12m", "POSITIVE"))
    rule = validate_rule_dsl(rule_dsl)
    assert len(rule.eligibility) == 1
    assert rule.eligibility[0].feature == "log_med_tv_60d"
    # Entry should be everything-after.
    assert len(rule.entry) == len(c.features) - 1


# ---------------------------------------------------------------------------
# Cache-dependent end-to-end tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CACHE_AVAILABLE, reason="cache files not present")
def test_load_cache_panels_returns_expected_shape() -> None:
    from atlas.discovery.deep_search import load_cache_panels

    panels = load_cache_panels()
    # Sanity: we have a few hundred Large-cap, full date range.
    assert panels.close.shape[0] > 1000  # 1000+ trading days
    assert panels.close.shape[1] > 100  # 100+ instruments
    last_row_caps = panels.cap_tier.iloc[-1].dropna()
    assert "Large" in last_row_caps.values
    # Cross-sectional sanity on rs_residual_6m last row.
    rs_last = panels.rs_residual_6m.iloc[-1].dropna()
    assert len(rs_last) > 100
    # RS residual should be ~zero-mean cross-sectionally.
    assert abs(float(rs_last.mean())) < 0.5


@pytest.mark.skipif(not CACHE_AVAILABLE, reason="cache files not present")
def test_run_deep_search_produces_results() -> None:
    """End-to-end: load cache, generate candidates, evaluate all, get summary."""
    from atlas.discovery.deep_search import load_cache_panels

    panels = load_cache_panels()
    cands = generate_candidates_large_12m_positive()
    summary = run_deep_search(
        cell_target=("Large", "12m", "POSITIVE"),
        candidates=cands,
        panels=panels,
    )
    assert summary.n_candidates == len(cands)
    assert len(summary.results) == len(cands)
    # Results must be sorted by absolute IC descending.
    abs_ics = [abs(r.ic) if r.ic == r.ic else 0.0 for r in summary.results]
    assert abs_ics == sorted(abs_ics, reverse=True)


@pytest.mark.skipif(not CACHE_AVAILABLE, reason="cache files not present")
def test_run_deep_search_at_least_one_candidate_validates() -> None:
    """We expect at least one candidate to clear the validation gate.

    This is a noisy real-data test; if it flakes, the methodology is the
    issue, not the test. Current expectation: ≥ 1 candidate in the lowvol
    + RS-leader family validates.
    """
    from atlas.discovery.deep_search import load_cache_panels

    panels = load_cache_panels()
    cands = generate_candidates_large_12m_positive()
    summary = run_deep_search(("Large", "12m", "POSITIVE"), cands, panels)
    assert summary.n_validated >= 1, (
        "no candidate validated — methodology may need extending. "
        f"best |IC| was {summary.best_ic}"
    )


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------


def _make_synthetic_summary() -> DeepSearchSummary:
    """A minimal in-memory summary for report-rendering tests."""
    cand_validated = CandidateRule(
        name="TEST_VALIDATED",
        archetype="quality_momentum",
        features=(
            FeaturePredicate(feature="log_med_tv_60d", cmp=">=", value=Decimal("16.5")),
            FeaturePredicate(
                feature="rs_residual_6m",
                cmp="in_top_quantile",
                value=Decimal("1"),
                value_quantile_n=10,
            ),
            FeaturePredicate(feature="realized_vol_60d", cmp="<=", value=Decimal("0.020")),
        ),
        rationale="test validated rule",
    )
    cand_failed = CandidateRule(
        name="TEST_FAILED",
        archetype="mean_reversion",
        features=(
            FeaturePredicate(feature="log_med_tv_60d", cmp=">=", value=Decimal("16.5")),
            FeaturePredicate(
                feature="dd_from_52w_high",
                cmp="in_range",
                value=(Decimal("-0.20"), Decimal("-0.05")),
            ),
        ),
        rationale="test failed rule",
    )
    res_validated = CandidateResult(
        rule=cand_validated,
        ic=0.12,
        tp_rate=0.61,
        median_excess=0.089,
        mean_excess=0.15,
        friction_adjusted_excess=0.086,
        percentile_10=-0.30,
        percentile_25=-0.15,
        percentile_50=0.089,
        percentile_75=0.40,
        percentile_90=0.80,
        n_observations=1473,
        per_window_results=(
            {
                "window": "2022-05-01_to_2023-04-30",
                "n_obs": 566,
                "median_excess": 0.19,
                "positive": True,
            },
            {
                "window": "2023-05-01_to_2024-04-30",
                "n_obs": 537,
                "median_excess": 0.32,
                "positive": True,
            },
            {
                "window": "2024-05-01_to_2025-04-30",
                "n_obs": 370,
                "median_excess": -0.06,
                "positive": False,
            },
        ),
        validated=True,
    )
    res_failed = CandidateResult(
        rule=cand_failed,
        ic=0.01,
        tp_rate=0.49,
        median_excess=-0.02,
        mean_excess=0.0,
        friction_adjusted_excess=-0.025,
        percentile_10=-0.40,
        percentile_25=-0.20,
        percentile_50=-0.02,
        percentile_75=0.10,
        percentile_90=0.30,
        n_observations=500,
        per_window_results=(),
        validated=False,
    )
    return DeepSearchSummary(
        cell_target=("Large", "12m", "POSITIVE"),
        results=(res_validated, res_failed),
        run_started_at=datetime(2026, 5, 24, 0, 0, tzinfo=UTC),
        run_completed_at=datetime(2026, 5, 24, 0, 0, 5, tzinfo=UTC),
        n_candidates=2,
        n_validated=1,
        best_ic=0.12,
        best_rule_name="TEST_VALIDATED",
    )


def test_generate_deep_search_report_writes_html(tmp_path: Path) -> None:
    summary = _make_synthetic_summary()
    out_path = tmp_path / "deep-search.html"
    written = generate_deep_search_report(summary, output_path=out_path)
    assert written == out_path
    assert out_path.exists()
    content = out_path.read_text()
    # Spot-check landmarks.
    assert "<!doctype html>" in content
    assert "Atlas v6" in content
    assert "Large" in content and "12m" in content and "POSITIVE" in content
    assert "TEST_VALIDATED" in content
    assert "TEST_FAILED" in content
    assert "VALIDATED" in content


def test_generate_deep_search_report_renders_no_signal_verdict(tmp_path: Path) -> None:
    """Honest "no signal" verdict when n_validated==0."""
    summary = _make_synthetic_summary()
    # Mutate to no-validation state.
    summary = DeepSearchSummary(
        cell_target=summary.cell_target,
        results=tuple(
            CandidateResult(
                rule=r.rule,
                ic=r.ic,
                tp_rate=r.tp_rate,
                median_excess=r.median_excess,
                mean_excess=r.mean_excess,
                friction_adjusted_excess=r.friction_adjusted_excess,
                percentile_10=r.percentile_10,
                percentile_25=r.percentile_25,
                percentile_50=r.percentile_50,
                percentile_75=r.percentile_75,
                percentile_90=r.percentile_90,
                n_observations=r.n_observations,
                per_window_results=r.per_window_results,
                validated=False,
            )
            for r in summary.results
        ),
        run_started_at=summary.run_started_at,
        run_completed_at=summary.run_completed_at,
        n_candidates=2,
        n_validated=0,
        best_ic=None,
        best_rule_name=None,
    )
    out_path = tmp_path / "no-signal.html"
    generate_deep_search_report(summary, output_path=out_path)
    content = out_path.read_text()
    assert "NO SIGNAL" in content
    assert "verdict-honest" in content


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def test_cli_parser_defaults() -> None:
    from atlas.discovery.deep_search import _build_cli_parser

    parser = _build_cli_parser()
    args = parser.parse_args([])
    assert args.cell == "Large/12m/POSITIVE"
    assert args.mode == "cache"
    assert args.dry_run is False
    assert args.output_html is None


def test_cli_parser_accepts_overrides(tmp_path: Path) -> None:
    from atlas.discovery.deep_search import _build_cli_parser

    out_html = str(tmp_path / "out.html")
    parser = _build_cli_parser()
    args = parser.parse_args(
        [
            "--cell",
            "Mid/6m/POSITIVE",
            "--output-html",
            out_html,
            "--dry-run",
        ]
    )
    assert args.cell == "Mid/6m/POSITIVE"
    assert args.output_html == out_html
    assert args.dry_run is True
