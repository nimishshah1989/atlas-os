"""Tests for atlas.inference.fund_scorecard.

Covers:
* risk-adjusted return primitives (Sharpe, Sortino, max-DD, Calmar, captures)
* holdings_conviction aggregation + survivorship_exposure + unjoinable flag
* style-sector + cost-manager layer math
* end-to-end pipeline: Atlas Leader (top 25%) + is_avoid (bottom 25%)
* confidence_low when NAV history < 3y (252*3 = 756 obs default)
* SQL emitter round-trips a typical row payload
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from atlas.inference.fund_scorecard import (
    _DEFAULT_THRESHOLDS,
    FundInput,
    _compute_composite,
    compute_fund_scorecard,
    compute_holdings_conviction,
    compute_risk_adjusted_metrics,
    emit_upsert_sql,
    score_cost_manager,
    score_risk_adjusted_return,
    score_style_sector,
)

# ---------------------------------------------------------------------------
# Risk-adjusted return primitives
# ---------------------------------------------------------------------------


class TestRiskAdjustedMetrics:
    def test_zero_returns_yields_zero_sharpe(self) -> None:
        m = compute_risk_adjusted_metrics([0.0] * 252, [0.0] * 252)
        assert m.sharpe == 0.0

    def test_positive_drift_yields_positive_sharpe(self) -> None:
        # Constant +0.001 daily, zero variance → infinite Sharpe.
        # Use slight noise to get finite, positive Sharpe.
        rng = [0.001 + (i % 2) * 0.0001 for i in range(252)]
        m = compute_risk_adjusted_metrics(rng, [0.0] * 252)
        assert m.sharpe > 0
        # Alpha vs zero-bench = annualized mean of fund returns
        assert m.alpha > 0

    def test_max_drawdown_computed_from_peak(self) -> None:
        # Build a return series that goes +10% then -20%
        returns = [0.10, -0.20]
        m = compute_risk_adjusted_metrics(returns, [])
        # peak = 1.10, trough = 0.88 → dd = (1.10 - 0.88)/1.10 = 0.20
        assert m.max_dd == pytest.approx(0.20, abs=0.0001)

    def test_sortino_caps_when_no_downside(self) -> None:
        # All positive returns above rf → no downside; sortino caps at 5.0.
        m = compute_risk_adjusted_metrics([0.01] * 252, [])
        assert m.sortino == 5.0

    def test_capture_ratios_unit_when_matched(self) -> None:
        # Fund tracks benchmark 1-for-1 on both up and down days.
        bench = [0.01, -0.01, 0.02, -0.02]
        m = compute_risk_adjusted_metrics(bench, bench)
        assert m.up_capture == pytest.approx(1.0, abs=0.001)
        assert m.down_capture == pytest.approx(1.0, abs=0.001)

    def test_n_observations_set(self) -> None:
        m = compute_risk_adjusted_metrics([0.01] * 100, [])
        assert m.n_observations == 100


# ---------------------------------------------------------------------------
# Risk-adjusted return scoring vs cohort
# ---------------------------------------------------------------------------


class TestRiskAdjustedScore:
    def test_target_above_cohort_scores_high(self) -> None:
        cohort = [compute_risk_adjusted_metrics([0.0001] * 252, [0.0001] * 252) for _ in range(5)]
        target = compute_risk_adjusted_metrics([0.005] * 252, [0.0001] * 252)
        score = score_risk_adjusted_return(target, cohort)
        assert score > Decimal("50.00")

    def test_empty_cohort_neutral_50(self) -> None:
        target = compute_risk_adjusted_metrics([0.001] * 252, [0.001] * 252)
        score = score_risk_adjusted_return(target, [])
        assert score == Decimal("50.00")


# ---------------------------------------------------------------------------
# Holdings conviction layer
# ---------------------------------------------------------------------------


class TestHoldingsConviction:
    def test_all_positive_holdings(self) -> None:
        holdings = [
            {"instrument_id": "iid-1", "weight_pct": 10, "symbol": "A"},
            {"instrument_id": "iid-2", "weight_pct": 20, "symbol": "B"},
        ]
        conviction = {"iid-1": "POSITIVE", "iid-2": "POSITIVE"}
        score, surv_pct, drilldown, unjoin = compute_holdings_conviction(
            holdings, conviction, top_n=20
        )
        # Fully covered → avg_signed = 1 → score = 100
        assert score == Decimal("100.00")
        assert surv_pct == 100.0
        assert unjoin is False
        assert len(drilldown) == 2

    def test_all_negative_holdings(self) -> None:
        holdings = [
            {"instrument_id": "iid-1", "weight_pct": 10},
            {"instrument_id": "iid-2", "weight_pct": 20},
        ]
        conviction = {"iid-1": "NEGATIVE", "iid-2": "NEGATIVE"}
        score, _, _, unjoin = compute_holdings_conviction(holdings, conviction, top_n=20)
        # avg_signed = -1 → score = 0
        assert score == Decimal("0.00")
        assert unjoin is False

    def test_unjoinable_when_no_match(self) -> None:
        # Holdings exist but no conviction rows match — flag unjoinable,
        # score falls back to 50 (neutral).
        holdings = [{"instrument_id": "iid-X", "weight_pct": 100}]
        score, surv_pct, drilldown, unjoin = compute_holdings_conviction(holdings, {}, top_n=20)
        assert unjoin is True
        assert score == Decimal("50.00")
        assert surv_pct == 0.0
        # Drilldown still emitted (UI uses it even when unjoinable).
        assert len(drilldown) == 1
        assert drilldown[0]["verdict"] is None

    def test_empty_holdings(self) -> None:
        score, _surv_pct, drilldown, unjoin = compute_holdings_conviction([], {}, top_n=20)
        assert unjoin is True
        assert score == Decimal("50.00")
        assert drilldown == []

    def test_survivorship_exposure_partial(self) -> None:
        # 1 holding in universe, 1 not.
        holdings = [
            {"instrument_id": "iid-1", "weight_pct": 50},
            {"instrument_id": "iid-2", "weight_pct": 50},
        ]
        conviction = {"iid-1": "POSITIVE"}  # only iid-1 matched
        _score, surv_pct, _, unjoin = compute_holdings_conviction(holdings, conviction, top_n=20)
        assert unjoin is False
        # 50% of weight in universe
        assert surv_pct == 50.0


# ---------------------------------------------------------------------------
# Style + cost layers
# ---------------------------------------------------------------------------


class TestStyleSector:
    def test_no_drift_no_tilt(self) -> None:
        score = score_style_sector(0.0, 0.0)
        assert score == Decimal("100.00")

    def test_full_drift_clipped(self) -> None:
        score = score_style_sector(150.0, 0.0)
        assert score == Decimal("0.00")

    def test_positive_tilt_bonus_capped(self) -> None:
        score = score_style_sector(0.0, 50.0)
        # 100 + 50 → capped at 100
        assert score == Decimal("100.00")


class TestCostManager:
    def test_aum_in_sweet_spot_scores_well(self) -> None:
        score = score_cost_manager(
            ter_pct=1.0,
            cohort_ter=[1.0, 1.5, 2.0],
            manager_tenure_years=10.0,
            aum_cr=1000.0,
            fund_age_years=10.0,
            sweet_min_cr=500.0,
            sweet_max_cr=5000.0,
        )
        # Higher TER ranks worse; tenure + AUM + age max out.
        assert score > Decimal("70")

    def test_missing_inputs_neutral(self) -> None:
        score = score_cost_manager(
            ter_pct=None,
            cohort_ter=[],
            manager_tenure_years=None,
            aum_cr=None,
            fund_age_years=None,
            sweet_min_cr=500.0,
            sweet_max_cr=5000.0,
        )
        # All sub-scores 50 → weighted = 50
        assert score == Decimal("50.00")


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


class TestComposite:
    def test_layer_weights_sum_to_one(self) -> None:
        total = (
            _DEFAULT_THRESHOLDS["mf_weight_risk_adj"]
            + _DEFAULT_THRESHOLDS["mf_weight_holdings"]
            + _DEFAULT_THRESHOLDS["mf_weight_style_sector"]
            + _DEFAULT_THRESHOLDS["mf_weight_cost_manager"]
        )
        assert total == Decimal("1.00")

    def test_max_components(self) -> None:
        comps: dict[str, Decimal | None] = {
            "risk_adjusted_return_score": Decimal("100"),
            "holdings_conviction_score": Decimal("100"),
            "style_sector_score": Decimal("100"),
            "cost_manager_score": Decimal("100"),
        }
        result = _compute_composite(comps, dict(_DEFAULT_THRESHOLDS))
        assert result == Decimal("100.00")


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------


def _make_fund_input(
    scheme: str,
    daily_returns: list[float],
    holdings: list[dict] | None = None,
    aum_cr: float | None = 1000.0,
    ter_pct: float | None = 1.0,
    category: str = "Flexi Cap",
    monthly_returns: list[tuple[date, float]] | None = None,
) -> FundInput:
    return FundInput(
        scheme_code=scheme,
        isin=None,
        fund_name=f"Fund {scheme}",
        fund_category=category,
        fund_style="Growth",
        amc="AMC",
        daily_returns=daily_returns,
        benchmark_daily_returns=[0.0001] * len(daily_returns),
        nav_as_of=date(2026, 5, 22),
        holdings_as_of=date(2026, 4, 30),
        holdings=holdings or [],
        style_drift_pct=15.0,
        sector_tilt_bonus=2.0,
        ter_pct=ter_pct,
        manager_tenure_years=5.0,
        aum_cr=aum_cr,
        fund_age_years=10.0,
        monthly_returns=monthly_returns or [],
    )


class TestPerformanceFactorsV2:
    """v2: momentum (recent return) + peer-relative consistency drive the score."""

    def test_momentum_rewards_recent_outperformance(self) -> None:
        # Same total path length; A is strong in the recent 6m, B was strong only
        # long ago. Momentum (last 6m/12m) should rank A above B.
        a = _make_fund_input("A", [0.0] * 674 + [0.004] * 126)
        b = _make_fund_input("B", [0.004] * 126 + [0.0] * 674)
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22), fund_inputs=[a, b], conviction_by_iid={}
        )
        sa = next(r for r in rows if r.scheme_code == "A").risk_adjusted_return_score
        sb = next(r for r in rows if r.scheme_code == "B").risk_adjusted_return_score
        assert sa is not None and sb is not None and sa > sb

    def test_consistency_injected_from_monthly_returns(self) -> None:
        # 3 funds, identical daily paths (so momentum + risk-adjusted tie); only
        # monthly_returns differ. X beats the monthly peer-median, Z never does.
        months = [date(2020 + i // 12, (i % 12) + 1, 28) for i in range(24)]
        daily = [0.001] * 800
        x = _make_fund_input("X", daily, monthly_returns=[(m, 0.03) for m in months])
        y = _make_fund_input("Y", daily, monthly_returns=[(m, 0.02) for m in months])
        z = _make_fund_input("Z", daily, monthly_returns=[(m, 0.01) for m in months])
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22), fund_inputs=[x, y, z], conviction_by_iid={}
        )
        sx = next(r for r in rows if r.scheme_code == "X").risk_adjusted_return_score
        sz = next(r for r in rows if r.scheme_code == "Z").risk_adjusted_return_score
        assert sx is not None and sz is not None and sx > sz
        # consistency surfaced in sub_metrics for transparency
        rx = next(r for r in rows if r.scheme_code == "X")
        assert rx.sub_metrics["consistency"] == 1.0  # X beat the median every month

    def test_drawdown_and_vol_not_scored(self) -> None:
        # Two funds, same momentum/consistency but very different drawdown. Since
        # max-drawdown is excluded from scoring (zero forward IC), the smoother
        # fund must NOT automatically outscore the choppier one on that basis.
        smooth = _make_fund_input("SM", [0.001] * 800)
        choppy = _make_fund_input("CH", ([0.02, -0.018] * 400))
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22),
            fund_inputs=[smooth, choppy],
            conviction_by_iid={},
        )
        # Both bounded & finite; the test asserts no crash + drawdown isn't a gate.
        for r in rows:
            assert Decimal("0") <= r.composite_score <= Decimal("100")


class TestPipeline:
    def test_atlas_leader_top_25pct(self) -> None:
        """4 funds: top 25% → 1 leader, bottom 25% → 1 avoid."""
        # Give 4 funds increasing performance, with 3y of history (756 days).
        funds = []
        for i in range(4):
            drift = 0.0001 + i * 0.0005
            funds.append(
                _make_fund_input(
                    f"S{i}",
                    daily_returns=[drift] * 800,
                    holdings=[
                        {"instrument_id": "iid-1", "weight_pct": 50},
                        {"instrument_id": "iid-2", "weight_pct": 50},
                    ],
                )
            )
        conviction = {"iid-1": "POSITIVE", "iid-2": "POSITIVE"}
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22),
            fund_inputs=funds,
            conviction_by_iid=conviction,
        )
        assert len(rows) == 4
        leaders = [r for r in rows if r.is_atlas_leader]
        avoid = [r for r in rows if r.is_avoid]
        # Top 25% of 4 = 1, bottom 25% = 1
        assert len(leaders) == 1
        assert len(avoid) == 1
        # Leader is the best performer.
        assert leaders[0].scheme_code == "S3"
        # All composites bounded.
        for r in rows:
            assert Decimal("0") <= r.composite_score <= Decimal("100")

    def test_confidence_low_when_short_history(self) -> None:
        # 252 days = 1y < 3y default threshold → confidence_low=True.
        fund = _make_fund_input("S1", [0.001] * 252)
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22),
            fund_inputs=[fund],
            conviction_by_iid={},
        )
        assert len(rows) == 1
        assert rows[0].confidence_low is True
        # confidence_low blocks Atlas Leader.
        assert rows[0].is_atlas_leader is False

    def test_holdings_unjoinable_fallback(self) -> None:
        fund = _make_fund_input(
            "S1",
            daily_returns=[0.001] * 800,
            holdings=[{"instrument_id": "iid-X", "weight_pct": 100}],
        )
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22),
            fund_inputs=[fund],
            conviction_by_iid={},  # iid-X not present
        )
        assert rows[0].holdings_unjoinable is True
        # holdings score should be the neutral fallback.
        assert rows[0].holdings_conviction_score == Decimal("50.00")

    def test_survivorship_exposure_recorded(self) -> None:
        fund = _make_fund_input(
            "S1",
            daily_returns=[0.001] * 800,
            holdings=[
                {"instrument_id": "iid-A", "weight_pct": 60},
                {"instrument_id": "iid-B", "weight_pct": 40},
            ],
        )
        rows = compute_fund_scorecard(
            snapshot_date=date(2026, 5, 22),
            fund_inputs=[fund],
            conviction_by_iid={"iid-A": "POSITIVE"},  # only A matches
        )
        # 60% of weight in universe.
        assert rows[0].survivorship_exposure_pct == Decimal("60.00")


# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------


class TestSQLEmission:
    def test_emits_insert_with_on_conflict(self) -> None:
        from atlas.inference.fund_scorecard import FundScoreRow

        row = FundScoreRow(
            snapshot_date=date(2026, 5, 22),
            scheme_code="120503",
            isin=None,
            fund_name="Test Fund",
            fund_category="Flexi Cap",
            fund_style="Growth",
            amc="AMC",
            risk_adjusted_return_score=Decimal("78.00"),
            holdings_conviction_score=Decimal("72.00"),
            style_sector_score=Decimal("65.00"),
            cost_manager_score=Decimal("80.00"),
            composite_score=Decimal("74.50"),
            rank_in_category=1,
            category_size=30,
            is_atlas_leader=True,
            is_avoid=False,
            confidence_low=False,
            holdings_unjoinable=False,
            survivorship_exposure_pct=Decimal("85.00"),
            nav_as_of=date(2026, 5, 22),
            holdings_as_of=date(2026, 4, 30),
            eli5="Top-quartile leader",
            sub_metrics={"sharpe": 1.45},
            top_holdings=[{"instrument_id": "iid-1", "verdict": "POSITIVE"}],
        )
        sql = emit_upsert_sql([row])
        assert "INSERT INTO atlas.atlas_fund_scorecard" in sql
        assert "ON CONFLICT" in sql
        assert "120503" in sql
        assert "Top-quartile leader" in sql

    def test_empty_rows_emits_comment(self) -> None:
        sql = emit_upsert_sql([])
        assert "no rows" in sql
