# allow-large: comprehensive test suite for all 8 scoring modules
"""Tests for all six lens scorers, composite engine, and risk flags.

Covers: technical, fundamental, valuation, catalyst, flow, policy,
        risk_flags, and composite (including fractal roll-ups).
"""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pytest

from atlas.lenses.compute.technical import TechnicalResult, score_technical
from atlas.lenses.compute.fundamental import FundamentalResult, score_fundamental
from atlas.lenses.compute.valuation import ValuationResult, score_valuation
from atlas.lenses.compute.catalyst import CatalystResult, score_catalyst
from atlas.lenses.compute.flow import FlowResult, score_flow
from atlas.lenses.compute.policy import PolicyResult, score_policy
from atlas.lenses.compute.risk_flags import RiskFlagsResult, compute_risk_flags
from atlas.lenses.compute.composite import (
    CompositeResult,
    compute_composite,
    rollup_sector,
    rollup_holdings,
    rollup_index,
)


# ============================================================================
# Helpers
# ============================================================================

_EMPTY_TH: dict = {}


def _d(v: float | int) -> Decimal:
    return Decimal(str(v))


# ============================================================================
# Technical scorer
# ============================================================================


class TestTechnicalBullish:
    """Aligned EMAs, strong RS, tight ATR, high volume → score near 100."""

    def test_bullish_case(self) -> None:
        result = score_technical(
            ema_21=110.0, ema_50=105.0, ema_200=95.0,
            rsi_14=60.0,
            price=115.0, high_52w=120.0, low_52w=70.0,
            ret_1w=0.03,
            rs_1m_n500=1.20, rs_3m_n500=1.18, rs_6m_n500=1.12, rs_12m_n500=1.10,
            atr_14=1.5, bb_width=0.08,
            volume=1_000_000,
            avg_volume_30d=2_000_000, avg_volume_60d=1_500_000,
            rel_volume_10d=2.5,
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, TechnicalResult)
        assert result.score is not None
        # All four subcomponents should be non-None
        assert result.trend is not None
        assert result.relative_strength is not None
        assert result.vol_contraction is not None
        assert result.volume is not None
        # Score should be high — every sub near max
        assert result.score >= _d(80), f"Expected high score, got {result.score}"

    def test_subcomponent_ranges(self) -> None:
        result = score_technical(
            ema_21=110.0, ema_50=105.0, ema_200=95.0,
            rsi_14=60.0,
            price=115.0, high_52w=120.0, low_52w=70.0,
            ret_1w=0.03,
            rs_1m_n500=1.20, rs_3m_n500=1.18, rs_6m_n500=1.12, rs_12m_n500=1.10,
            atr_14=1.5, bb_width=0.08,
            volume=1_000_000,
            avg_volume_30d=2_000_000, avg_volume_60d=1_500_000,
            rel_volume_10d=2.5,
            thresholds=_EMPTY_TH,
        )
        # Each sub is 0-25
        for sub in (result.trend, result.relative_strength, result.vol_contraction, result.volume):
            assert sub is not None
            assert _d(0) <= sub <= _d(25)


class TestTechnicalBearish:
    """Inverted EMAs, weak RS → low score."""

    def test_bearish_case(self) -> None:
        result = score_technical(
            ema_21=90.0, ema_50=100.0, ema_200=110.0,  # inverted
            rsi_14=28.0,  # oversold
            price=85.0, high_52w=130.0, low_52w=80.0,
            ret_1w=-0.04,
            rs_1m_n500=0.80, rs_3m_n500=0.82, rs_6m_n500=0.85, rs_12m_n500=0.83,
            atr_14=6.0, bb_width=0.20,  # wide ATR
            volume=500_000,
            avg_volume_30d=400_000, avg_volume_60d=600_000,  # distribution
            rel_volume_10d=0.4,  # low
            thresholds=_EMPTY_TH,
        )
        assert result.score is not None
        assert result.score <= _d(40), f"Expected low score, got {result.score}"
        # Trend evidence should show inverted alignment
        assert result.evidence["trend"].get("ema_alignment") == "inverted"


class TestTechnicalPartialData:
    """Only trend data available → trend non-None, vol None."""

    def test_partial_data(self) -> None:
        result = score_technical(
            ema_21=110.0, ema_50=105.0, ema_200=95.0,
            rsi_14=55.0,
            price=112.0, high_52w=None, low_52w=None,
            ret_1w=0.01,
            rs_1m_n500=None, rs_3m_n500=None, rs_6m_n500=None, rs_12m_n500=None,
            atr_14=None, bb_width=None,
            volume=None,
            avg_volume_30d=None, avg_volume_60d=None,
            rel_volume_10d=None,
            thresholds=_EMPTY_TH,
        )
        assert result.trend is not None
        assert result.relative_strength is None
        assert result.vol_contraction is None
        assert result.volume is None
        # Score should still be computed from the one available sub
        assert result.score is not None


class TestTechnicalAllNone:
    """All None inputs → score is None."""

    def test_all_none(self) -> None:
        result = score_technical(
            ema_21=None, ema_50=None, ema_200=None,
            rsi_14=None,
            price=None, high_52w=None, low_52w=None,
            ret_1w=None,
            rs_1m_n500=None, rs_3m_n500=None, rs_6m_n500=None, rs_12m_n500=None,
            atr_14=None, bb_width=None,
            volume=None,
            avg_volume_30d=None, avg_volume_60d=None,
            rel_volume_10d=None,
            thresholds=_EMPTY_TH,
        )
        assert result.score is None
        assert result.trend is None
        assert result.relative_strength is None
        assert result.vol_contraction is None
        assert result.volume is None


class TestTechnicalComposite:
    """Composite = average of non-None subs * 4."""

    def test_composite_formula(self) -> None:
        """When only trend+RS available, composite = avg(trend, rs) * 4."""
        result = score_technical(
            ema_21=110.0, ema_50=105.0, ema_200=95.0,
            rsi_14=60.0,
            price=115.0, high_52w=None, low_52w=None,
            ret_1w=0.03,
            rs_1m_n500=1.15, rs_3m_n500=1.10, rs_6m_n500=None, rs_12m_n500=None,
            atr_14=None, bb_width=None,
            volume=None,
            avg_volume_30d=None, avg_volume_60d=None,
            rel_volume_10d=None,
            thresholds=_EMPTY_TH,
        )
        assert result.trend is not None
        assert result.relative_strength is not None
        assert result.vol_contraction is None
        assert result.volume is None
        expected = (result.trend + result.relative_strength) / 2 * 4
        assert result.score == expected.quantize(Decimal("0.01"))


# ============================================================================
# Fundamental scorer
# ============================================================================


class TestFundamentalStrong:
    """High ROE, expanding margins, good growth, low debt → high score."""

    def test_strong_company(self) -> None:
        result = score_fundamental(
            roe=25.0, roa=12.0, roic=20.0,
            operating_margin=22.0, net_margin=18.0,
            gross_margin=45.0,
            revenue_growth_yoy=30.0, eps_growth_yoy=35.0,
            debt_to_equity=0.2, current_ratio=2.5, quick_ratio=2.0,
            revenue_ttm=5000.0, eps_diluted_ttm=50.0,
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, FundamentalResult)
        assert result.score is not None
        assert result.score >= _d(75), f"Expected high score, got {result.score}"
        # All five subcomponents should be present
        assert result.profitability is not None
        assert result.margin is not None
        assert result.growth is not None
        assert result.balance_sheet is not None
        assert result.op_leverage is not None


class TestFundamentalWeak:
    """Low ROE, declining margins, high debt → low score."""

    def test_weak_company(self) -> None:
        result = score_fundamental(
            roe=5.0, roa=2.0, roic=4.0,
            operating_margin=3.0, net_margin=1.0,
            gross_margin=15.0,
            revenue_growth_yoy=-5.0, eps_growth_yoy=-10.0,
            debt_to_equity=2.0, current_ratio=0.8, quick_ratio=0.3,
            revenue_ttm=1000.0, eps_diluted_ttm=5.0,
            thresholds=_EMPTY_TH,
        )
        assert result.score is not None
        assert result.score <= _d(40), f"Expected low score, got {result.score}"


class TestFundamentalPartial:
    """Only profitability available → still computes a score."""

    def test_partial_data(self) -> None:
        result = score_fundamental(
            roe=18.0, roa=None, roic=None,
            operating_margin=None, net_margin=None,
            gross_margin=None,
            revenue_growth_yoy=None, eps_growth_yoy=None,
            debt_to_equity=None, current_ratio=None, quick_ratio=None,
            revenue_ttm=None, eps_diluted_ttm=None,
            thresholds=_EMPTY_TH,
        )
        assert result.profitability is not None
        assert result.margin is None
        assert result.growth is None
        assert result.balance_sheet is None
        assert result.op_leverage is None
        # Score is renormalized to only the present subcomponent
        assert result.score is not None


class TestFundamentalAllNone:
    """All None inputs → score is None."""

    def test_all_none(self) -> None:
        result = score_fundamental(
            roe=None, roa=None, roic=None,
            operating_margin=None, net_margin=None,
            gross_margin=None,
            revenue_growth_yoy=None, eps_growth_yoy=None,
            debt_to_equity=None, current_ratio=None, quick_ratio=None,
            revenue_ttm=None, eps_diluted_ttm=None,
            thresholds=_EMPTY_TH,
        )
        assert result.score is None


class TestFundamentalNormalization:
    """Score is renormalized based on available subcomponents."""

    def test_two_subs_normalize(self) -> None:
        result = score_fundamental(
            roe=25.0, roa=None, roic=20.0,
            operating_margin=22.0, net_margin=18.0,
            gross_margin=None,
            revenue_growth_yoy=None, eps_growth_yoy=None,
            debt_to_equity=None, current_ratio=None, quick_ratio=None,
            revenue_ttm=None, eps_diluted_ttm=None,
            thresholds=_EMPTY_TH,
        )
        assert result.profitability is not None
        assert result.margin is not None
        assert result.growth is None
        # score = sum(present) * 100 / (20 * count_present)
        expected = (result.profitability + result.margin) * _d(100) / (_d(20) * _d(2))
        assert result.score == expected.quantize(_d("0.1"))


# ============================================================================
# Valuation scorer
# ============================================================================


class TestValuationDeepValue:
    """PE=6, P/B=0.8, EV/EBITDA=5 → score ≥ 75, zone=DEEP_VALUE, mult=1.15."""

    def test_deep_value(self) -> None:
        result = score_valuation(
            pe_ttm=6.0, pb_fbs=0.8, ev_ebitda=5.0,
            price=50.0, high_52w=80.0, low_52w=40.0,
            ema_200=55.0,
            sector_median_pe=18.0,
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, ValuationResult)
        assert result.score is not None
        assert result.score >= _d(75), f"Expected ≥75, got {result.score}"
        assert result.zone == "DEEP_VALUE"
        assert result.multiplier == _d("1.15")


class TestValuationOvervalued:
    """PE=60, P/B=8, EV/EBITDA=25 → score <20, zone=OVERVALUED, mult=0.75."""

    def test_overvalued(self) -> None:
        result = score_valuation(
            pe_ttm=60.0, pb_fbs=8.0, ev_ebitda=25.0,
            price=95.0, high_52w=100.0, low_52w=50.0,
            ema_200=70.0,
            sector_median_pe=20.0,
            thresholds=_EMPTY_TH,
        )
        assert result.score is not None
        assert result.score < _d(20), f"Expected <20, got {result.score}"
        assert result.zone == "OVERVALUED"
        assert result.multiplier == _d("0.75")


class TestValuationFairValue:
    """PE=20, P/B=3, EV/EBITDA=12 → zone=FAIR."""

    def test_fair_value(self) -> None:
        result = score_valuation(
            pe_ttm=20.0, pb_fbs=3.0, ev_ebitda=12.0,
            price=65.0, high_52w=100.0, low_52w=40.0,
            ema_200=60.0,
            sector_median_pe=22.0,
            thresholds=_EMPTY_TH,
        )
        assert result.zone == "FAIR"
        assert result.multiplier == _d("1.00")


class TestValuationNoData:
    """All None → score=35, zone=FAIR (default)."""

    def test_no_data_default(self) -> None:
        result = score_valuation(
            pe_ttm=None, pb_fbs=None, ev_ebitda=None,
            price=None, high_52w=None, low_52w=None,
            ema_200=None, sector_median_pe=None,
            thresholds=_EMPTY_TH,
        )
        assert result.score == _d(35)
        assert result.zone == "FAIR"
        assert result.evidence.get("imputation") == "no_data_default_fair"


class TestValuationPartialData:
    """Only PE available → imputation at 60%."""

    def test_partial_imputation(self) -> None:
        result = score_valuation(
            pe_ttm=10.0, pb_fbs=None, ev_ebitda=None,
            price=None, high_52w=None, low_52w=None,
            ema_200=None, sector_median_pe=None,
            thresholds=_EMPTY_TH,
        )
        assert result.score is not None
        assert result.evidence.get("imputation") == "partial_60pct"
        # abs_pe for PE=10 → 18 pts; max=25; imputed = 75 * (18/25) * 0.6 = 32.4
        # total = 18 + 32.4 = 50.4
        assert result.absolute_pe == _d(18)


class TestValuationDimensions:
    """Check individual dimension scores."""

    def test_pe_vs_sector_discount(self) -> None:
        """PE is half the sector median → 25 pts."""
        result = score_valuation(
            pe_ttm=9.0, pb_fbs=None, ev_ebitda=None,
            price=None, high_52w=None, low_52w=None,
            ema_200=None, sector_median_pe=20.0,
            thresholds=_EMPTY_TH,
        )
        assert result.pe_vs_sector == _d(25)


# ============================================================================
# Catalyst scorer
# ============================================================================


class TestCatalystPositive:
    """Credit upgrade + dividend → positive score."""

    def test_positive_filings(self) -> None:
        filings = [
            {
                "filing_date": date(2026, 6, 1),
                "category_bucket": "earnings",
                "subject_text": "Credit Rating Upgrade by CRISIL",
            },
            {
                "filing_date": date(2026, 6, 10),
                "category_bucket": "capital",
                "subject_text": "Dividend - Final dividend of Rs 5 per share",
            },
        ]
        result = score_catalyst(filings, as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        assert isinstance(result, CatalystResult)
        assert result.score is not None
        assert result.score > _d(0)
        assert result.earnings_strategy is not None
        assert result.capital_action is not None


class TestCatalystNegative:
    """Auditor change + CFO resignation → negative governance."""

    def test_negative_filings(self) -> None:
        filings = [
            {
                "filing_date": date(2026, 6, 5),
                "category_bucket": "governance",
                "subject_text": "Auditor change - mid-term replacement",
            },
            {
                "filing_date": date(2026, 6, 8),
                "category_bucket": "governance",
                "subject_text": "Cessation of CFO Mr. Sharma",
            },
        ]
        result = score_catalyst(filings, as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        assert result.score is not None
        # Governance bucket is negative but clamped to 0
        assert result.governance == _d(0)


class TestCatalystRecency:
    """Old filings contribute less."""

    def test_recency_weighting(self) -> None:
        recent_filing = [
            {
                "filing_date": date(2026, 6, 1),
                "category_bucket": "capital",
                "subject_text": "Buyback of shares",
            },
        ]
        old_filing = [
            {
                "filing_date": date(2025, 6, 1),  # > 365 days ago
                "category_bucket": "capital",
                "subject_text": "Buyback of shares",
            },
        ]
        recent_result = score_catalyst(recent_filing, as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        old_result = score_catalyst(old_filing, as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        assert recent_result.score is not None
        assert old_result.score is not None
        assert recent_result.score > old_result.score


class TestCatalystEmpty:
    """Empty filings → score=None."""

    def test_empty(self) -> None:
        result = score_catalyst([], as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        assert result.score is None
        assert result.earnings_strategy is None
        assert result.capital_action is None
        assert result.governance is None


class TestCatalystBucketWeights:
    """Earnings strategy bucket has 55% weight by default."""

    def test_weights(self) -> None:
        filings = [
            {
                "filing_date": date(2026, 6, 1),
                "category_bucket": "earnings",
                "subject_text": "Press release - order win from Ministry",
            },
        ]
        result = score_catalyst(filings, as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        # order win = 10 pts * 1.0 recency = 10 → earnings_strategy=10
        # composite = 10 * 0.55 + 0 * 0.30 + 0 * 0.15 = 5.5
        assert result.earnings_strategy == _d("10.0")
        assert result.score == _d("5.5")


# ============================================================================
# Flow scorer
# ============================================================================


class TestFlowPromoterBuying:
    """Multiple open_market_buy with high value → high promoter score."""

    def test_strong_promoter_buying(self) -> None:
        transactions = [
            {"signal_type": "open_market_buy", "value_cr": 6.0},
            {"signal_type": "open_market_buy", "value_cr": 7.0},
            {"signal_type": "open_market_buy", "value_cr": 5.5},
        ]
        result = score_flow(
            insider_transactions=transactions,
            shareholding_current=None,
            shareholding_previous=None,
            bulk_deals=[],
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, FlowResult)
        assert result.promoter is not None
        assert result.promoter > _d(0)
        assert result.score is not None
        assert result.score > _d(0)


class TestFlowPledgeIncrease:
    """Pledge increase → negative contribution."""

    def test_pledge_increase(self) -> None:
        transactions = [
            {"signal_type": "pledge_increase", "value_cr": 10.0, "pledge_pct_after": 30},
        ]
        result = score_flow(
            insider_transactions=transactions,
            shareholding_current=None,
            shareholding_previous=None,
            bulk_deals=[],
            thresholds=_EMPTY_TH,
        )
        # pledge_increase has base weight -8 → negative but clamped to 0 in promoter
        assert result.promoter == _d(0)


class TestFlowSmartMoney:
    """Superstar entry → positive."""

    def test_superstar_entry(self) -> None:
        bulk_deals = [
            {"buy_sell": "buy", "is_superstar": True, "is_institutional": False},
        ]
        result = score_flow(
            insider_transactions=[],
            shareholding_current=None,
            shareholding_previous=None,
            bulk_deals=bulk_deals,
            thresholds=_EMPTY_TH,
        )
        assert result.smart_money is not None
        assert result.smart_money > _d(0)
        assert result.evidence["smart_money"]["signals"] == ["superstar_new_entry"]


class TestFlowNoData:
    """No data → None scores."""

    def test_no_data(self) -> None:
        result = score_flow(
            insider_transactions=[],
            shareholding_current=None,
            shareholding_previous=None,
            bulk_deals=[],
            thresholds=_EMPTY_TH,
        )
        assert result.promoter is None
        assert result.institutional is None
        assert result.smart_money is None
        assert result.score is None


class TestFlowCompositeWeights:
    """Default weights: 70% promoter + 30% smart money."""

    def test_composite_calculation(self) -> None:
        transactions = [
            {"signal_type": "open_market_buy", "value_cr": 3.0},
        ]
        result = score_flow(
            insider_transactions=transactions,
            shareholding_current=None,
            shareholding_previous=None,
            bulk_deals=[],
            thresholds=_EMPTY_TH,
        )
        # sm_raw = 0 (no bulk deals, no shareholding)
        # sm_scaled = (0 + 10) / 25 * 100 = 40
        # composite = promoter * 0.70 + 40 * 0.30
        promo = float(result.promoter)
        expected = promo * 0.70 + 40.0 * 0.30
        assert abs(float(result.score) - expected) < 0.1


class TestFlowInstitutionalAccumulation:
    """Shareholding QoQ change → institutional accumulation signal."""

    def test_institutional_accumulation(self) -> None:
        result = score_flow(
            insider_transactions=[],
            shareholding_current={"promoter_pct": 48.0},  # inst = 52%
            shareholding_previous={"promoter_pct": 50.0},  # inst = 50%
            bulk_deals=[],
            thresholds=_EMPTY_TH,
        )
        # delta = 52 - 50 = 2 >= 1.0 → strong accumulation (+6)
        assert result.smart_money is not None
        assert "inst_accumulation_strong" in result.evidence["smart_money"]["signals"]


# ============================================================================
# Policy scorer
# ============================================================================


class TestPolicyMatch:
    """Pharma company matches PLI pharma → score > 0."""

    def test_pharma_pli(self) -> None:
        policies = [
            {
                "id": "pli-pharma",
                "name": "PLI Scheme for Pharmaceuticals",
                "beneficiary_sectors": ["Pharmaceuticals"],
                "beneficiary_keywords": ["pharma", "api"],
                "impact": "HIGH",
            },
        ]
        result = score_policy(
            sector="Pharmaceuticals",
            industry="API Manufacturing",
            policies=policies,
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, PolicyResult)
        assert result.score is not None
        assert result.score > _d(0)
        assert len(result.matching_policies) == 1
        assert result.matching_policies[0]["priority"] == "HIGH"


class TestPolicyNoMatch:
    """Non-matching sector → score = 0."""

    def test_no_match(self) -> None:
        policies = [
            {
                "id": "pli-pharma",
                "name": "PLI for Pharma",
                "beneficiary_sectors": ["Pharmaceuticals"],
                "beneficiary_keywords": ["pharma"],
                "impact": "HIGH",
            },
        ]
        result = score_policy(
            sector="Information Technology",
            industry="Software Services",
            policies=policies,
            thresholds=_EMPTY_TH,
        )
        assert result.score == _d(0)
        assert len(result.matching_policies) == 0


class TestPolicyNoSector:
    """No sector/industry → None."""

    def test_no_sector(self) -> None:
        result = score_policy(
            sector=None,
            industry=None,
            policies=[{"id": "x", "beneficiary_sectors": ["IT"]}],
            thresholds=_EMPTY_TH,
        )
        assert result.score is None
        assert result.tailwind is None


class TestPolicyNoPolicies:
    """No policies in registry → score = 0."""

    def test_empty_registry(self) -> None:
        result = score_policy(
            sector="IT",
            industry="Software",
            policies=[],
            thresholds=_EMPTY_TH,
        )
        assert result.score == _d(0)


class TestPolicyMultipleMatches:
    """Multiple matching policies → scores accumulate."""

    def test_accumulation(self) -> None:
        policies = [
            {"id": "p1", "name": "PLI Electronics", "beneficiary_sectors": ["Electronics"],
             "beneficiary_keywords": [], "impact": "HIGH"},
            {"id": "p2", "name": "PLI Semiconductors", "beneficiary_sectors": [],
             "beneficiary_keywords": ["semiconductor"], "impact": "MEDIUM"},
        ]
        result = score_policy(
            sector="Electronics",
            industry="Semiconductor Manufacturing",
            policies=policies,
            thresholds=_EMPTY_TH,
        )
        assert result.score == _d(25)  # HIGH=15 + MEDIUM=10
        assert len(result.matching_policies) == 2


# ============================================================================
# Risk flags
# ============================================================================


class TestRiskFlagsClean:
    """Clean company: no flags → degradation=0."""

    def test_clean(self) -> None:
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[],
            annual_financials={},
            filings=[],
            price=100.0,
            ema_200=90.0,
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, RiskFlagsResult)
        assert result.degradation_score == _d(0)
        assert result.is_degrading is False
        assert result.flags_firing == 0
        assert result.flags == []


class TestRiskFlagsDegrading:
    """Multiple flags → score ≤ -15, is_degrading=True."""

    def test_degrading(self) -> None:
        result = compute_risk_flags(
            insider_signals=[
                {"type": "sell", "amount_cr": 5, "name": "A"},
                {"type": "sell", "amount_cr": 3, "name": "B"},
                {"type": "sell", "amount_cr": 2, "name": "C"},
                {"type": "pledge_increase", "amount_cr": 0},
            ],
            quarterly_margins=[8.0, 9.0, 10.0, 11.0],  # declining: 8 < 9 < 10 < 11
            annual_financials={
                "revenue": 900, "revenue_prev": 1000,
                "debt_to_equity": 1.5, "debt_to_equity_prev": 1.0,
                "ebitda_margin": 10, "ebitda_margin_prev": 15,
            },
            filings=[
                {"subject": "auditor change replacement"},
                {"subject": "cfo resign from position"},
            ],
            price=70.0,
            ema_200=100.0,
            thresholds=_EMPTY_TH,
        )
        assert result.degradation_score <= _d(-15)
        assert result.is_degrading is True
        assert result.flags_firing >= 3


class TestRiskFlagsIndividual:
    """Individual flag detection tests."""

    def test_net_insider_selling(self) -> None:
        result = compute_risk_flags(
            insider_signals=[
                {"type": "sell", "amount_cr": 2, "name": "X"},
            ],
            quarterly_margins=[],
            annual_financials={},
            filings=[],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "net_insider_selling" in flag_names

    def test_pledge_increasing(self) -> None:
        result = compute_risk_flags(
            insider_signals=[{"type": "pledge_increase"}],
            quarterly_margins=[],
            annual_financials={},
            filings=[],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "pledge_increasing" in flag_names

    def test_revenue_declining(self) -> None:
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[],
            annual_financials={"revenue": 80, "revenue_prev": 100},
            filings=[],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "revenue_declining" in flag_names

    def test_price_below_200dma(self) -> None:
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[],
            annual_financials={},
            filings=[],
            price=80.0,
            ema_200=100.0,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "price_below_200dma" in flag_names

    def test_auditor_change_filing(self) -> None:
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[],
            annual_financials={},
            filings=[{"subject": "Change of auditor mid-term"}],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "auditor_change" in flag_names

    def test_credit_downgrade(self) -> None:
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[],
            annual_financials={},
            filings=[{"subject": "Credit Rating downgrade by ICRA"}],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "credit_downgrade" in flag_names

    def test_leverage_up_margins_down(self) -> None:
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[],
            annual_financials={
                "debt_to_equity": 1.5, "debt_to_equity_prev": 1.0,
                "ebitda_margin": 10, "ebitda_margin_prev": 15,
            },
            filings=[],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "leverage_up_margins_down" in flag_names

    def test_margin_declining(self) -> None:
        # quarterly_margins is listed newest-first in the code;
        # _margin_declining checks valid[i] < valid[i+1] from index 0
        result = compute_risk_flags(
            insider_signals=[],
            quarterly_margins=[8.0, 10.0, 12.0],  # declining: 8 < 10 < 12
            annual_financials={},
            filings=[],
            price=None,
            ema_200=None,
            thresholds=_EMPTY_TH,
        )
        flag_names = [f["name"] for f in result.flags]
        assert "margin_declining" in flag_names


class TestRiskFlagsDegradationFloor:
    """Score is floored at -30 by default."""

    def test_floor(self) -> None:
        result = compute_risk_flags(
            insider_signals=[
                {"type": "sell", "amount_cr": 10, "name": "A"},
                {"type": "sell", "amount_cr": 10, "name": "B"},
                {"type": "sell", "amount_cr": 10, "name": "C"},
                {"type": "pledge_increase"},
            ],
            quarterly_margins=[5.0, 8.0, 11.0],
            annual_financials={
                "revenue": 70, "revenue_prev": 100,
                "debt_to_equity": 2.0, "debt_to_equity_prev": 1.0,
                "ebitda_margin": 5, "ebitda_margin_prev": 15,
            },
            filings=[
                {"subject": "auditor change"},
                {"subject": "cfo resign"},
                {"subject": "Credit Rating downgrade announced"},
            ],
            price=50.0,
            ema_200=100.0,
            thresholds=_EMPTY_TH,
        )
        assert result.degradation_score >= _d(-30)


# ============================================================================
# Composite engine
# ============================================================================


class TestCompositeFullCoverage:
    """All 5 lenses active → coverage_factor = 1.0."""

    def test_full_coverage(self) -> None:
        result = compute_composite(
            technical=70.0,
            fundamental=65.0,
            valuation_score=55.0,
            catalyst=60.0,
            flow=50.0,
            policy=40.0,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert isinstance(result, CompositeResult)
        assert result.lenses_active == 5
        # sum of default weights = 0.20+0.20+0.25+0.25+0.10 = 1.0
        assert result.coverage_factor == _d("1.00")


class TestCompositePartialCoverage:
    """3 lenses → coverage_factor = sqrt(weight_sum)."""

    def test_partial_coverage(self) -> None:
        # technical=0.20, fundamental=0.20, catalyst=0.25 → sum=0.65
        result = compute_composite(
            technical=60.0,
            fundamental=55.0,
            valuation_score=None,
            catalyst=50.0,
            flow=None,
            policy=None,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert result.lenses_active == 3
        expected_cf = round(math.sqrt(0.65), 4)
        assert abs(float(result.coverage_factor) - expected_cf) < 0.01


class TestCompositeConvergence:
    """4 lenses above 40 → 1.15x multiplier."""

    def test_convergence_bonus(self) -> None:
        # High raw scores so that rescaled values are >= 40
        result = compute_composite(
            technical=60.0,
            fundamental=60.0,
            valuation_score=60.0,
            catalyst=60.0,
            flow=60.0,
            policy=None,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        # All rescaled scores should be well above 40
        converging = sum(1 for v in result.rescaled.values() if float(v) >= 40)
        assert converging >= 4
        assert result.convergence_multiplier == _d("1.15")


class TestCompositeConvictionTiers:
    """High score + 3 lenses → HIGHEST; low score → BELOW_THRESHOLD."""

    def test_highest_conviction(self) -> None:
        result = compute_composite(
            technical=90.0,
            fundamental=85.0,
            valuation_score=80.0,
            catalyst=75.0,
            flow=70.0,
            policy=60.0,
            valuation_multiplier=1.15,
            smart_money_score=5.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert result.conviction_tier == "HIGHEST"
        assert result.final_score >= _d(70)

    def test_below_threshold(self) -> None:
        result = compute_composite(
            technical=5.0,
            fundamental=3.0,
            valuation_score=None,
            catalyst=2.0,
            flow=None,
            policy=None,
            valuation_multiplier=0.75,
            smart_money_score=-5.0,
            degradation_score=-20.0,
            thresholds=_EMPTY_TH,
        )
        assert result.conviction_tier == "BELOW_THRESHOLD"

    def test_zero_lenses(self) -> None:
        result = compute_composite(
            technical=None,
            fundamental=None,
            valuation_score=None,
            catalyst=None,
            flow=None,
            policy=None,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert result.lenses_active == 0
        assert result.conviction_tier == "BELOW_THRESHOLD"
        assert result.final_score == _d(0)


class TestCompositeModifiers:
    """Valuation multiplier, smart money, degradation applied correctly."""

    def test_valuation_multiplier_applied(self) -> None:
        base_result = compute_composite(
            technical=30.0, fundamental=30.0, valuation_score=30.0,
            catalyst=30.0, flow=30.0, policy=30.0,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        boosted_result = compute_composite(
            technical=30.0, fundamental=30.0, valuation_score=30.0,
            catalyst=30.0, flow=30.0, policy=30.0,
            valuation_multiplier=1.15,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert boosted_result.final_score > base_result.final_score

    def test_degradation_reduces_score(self) -> None:
        clean_result = compute_composite(
            technical=60.0, fundamental=60.0, valuation_score=60.0,
            catalyst=60.0, flow=60.0, policy=60.0,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        degraded_result = compute_composite(
            technical=60.0, fundamental=60.0, valuation_score=60.0,
            catalyst=60.0, flow=60.0, policy=60.0,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=-20.0,
            thresholds=_EMPTY_TH,
        )
        assert degraded_result.final_score < clean_result.final_score

    def test_smart_money_boost(self) -> None:
        base_result = compute_composite(
            technical=30.0, fundamental=30.0, valuation_score=30.0,
            catalyst=30.0, flow=30.0, policy=30.0,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        sm_result = compute_composite(
            technical=30.0, fundamental=30.0, valuation_score=30.0,
            catalyst=30.0, flow=30.0, policy=30.0,
            valuation_multiplier=1.0,
            smart_money_score=10.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert sm_result.final_score > base_result.final_score

    def test_final_score_clamped(self) -> None:
        """Final score is clamped to [0, 100]."""
        result = compute_composite(
            technical=100.0, fundamental=100.0, valuation_score=100.0,
            catalyst=100.0, flow=100.0, policy=100.0,
            valuation_multiplier=1.15,
            smart_money_score=15.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        assert result.final_score <= _d(100)

        result_neg = compute_composite(
            technical=1.0, fundamental=1.0, valuation_score=None,
            catalyst=1.0, flow=None, policy=None,
            valuation_multiplier=0.75,
            smart_money_score=-10.0,
            degradation_score=-30.0,
            thresholds=_EMPTY_TH,
        )
        assert result_neg.final_score >= _d(0)


class TestCompositeCustomThresholds:
    """Test with custom threshold overrides."""

    def test_custom_weights(self) -> None:
        custom_th = {
            "lens_weights": {
                "technical": 0.50,
                "fundamental": 0.10,
                "catalyst": 0.10,
                "flow": 0.10,
                "policy": 0.20,
            },
        }
        result = compute_composite(
            technical=90.0,
            fundamental=10.0,
            valuation_score=None,
            catalyst=10.0,
            flow=10.0,
            policy=10.0,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=custom_th,
        )
        # Technical has 50% weight — should dominate
        assert result.final_score > _d(40)


# ============================================================================
# Fractal roll-up tests
# ============================================================================


class TestRollupSector:
    """3 stocks with different caps → weighted average."""

    def test_cap_weighted(self) -> None:
        stocks = [
            {"market_cap": 1000, "final_score": 80, "technical": 70, "fundamental": 60},
            {"market_cap": 500, "final_score": 40, "technical": 30, "fundamental": 50},
            {"market_cap": 200, "final_score": 60, "technical": 55, "fundamental": 45},
        ]
        result = rollup_sector(stocks)
        assert result["stock_count"] == 3
        assert result["total_market_cap"] == 1700.0
        # weighted_final = (80*1000 + 40*500 + 60*200) / 1700 = 112000/1700 ≈ 65.88
        assert abs(result["weighted_final_score"] - 65.88) < 0.1
        assert "technical" in result["lens_averages"]
        assert "fundamental" in result["lens_averages"]
        # Breadth: 2/3 above 50
        assert result["breadth"]["count"] == 3
        assert abs(result["breadth"]["breadth_above_50"] - 2 / 3) < 0.01

    def test_empty_sector(self) -> None:
        result = rollup_sector([])
        assert result["stock_count"] == 0
        assert result["weighted_final_score"] == 0.0


class TestRollupHoldings:
    """With benchmark → active tilt computed."""

    def test_with_benchmark(self) -> None:
        holdings = [
            {"weight": 0.5, "final_score": 70, "technical": 65, "fundamental": 55},
            {"weight": 0.3, "final_score": 50, "technical": 40, "fundamental": 60},
            {"weight": 0.2, "final_score": 80, "technical": 75, "fundamental": 50},
        ]
        benchmark = {"technical": 50.0, "fundamental": 50.0}
        result = rollup_holdings(holdings, benchmark_scores=benchmark)
        assert result["holding_count"] == 3
        assert "active_tilt" in result
        # Active tilt should show lens_avg - benchmark
        assert "technical" in result["active_tilt"]
        assert "fundamental" in result["active_tilt"]
        # Technical avg = (65*0.5 + 40*0.3 + 75*0.2) / 1.0 = 59.5
        # Active tilt for technical = 59.5 - 50 = 9.5
        assert abs(result["active_tilt"]["technical"] - 9.5) < 0.1

    def test_without_benchmark(self) -> None:
        holdings = [
            {"weight": 0.6, "final_score": 70, "technical": 65},
            {"weight": 0.4, "final_score": 50, "technical": 45},
        ]
        result = rollup_holdings(holdings)
        assert "active_tilt" not in result
        assert result["holding_count"] == 2


class TestRollupIndex:
    """Basic constituent roll-up."""

    def test_index_rollup(self) -> None:
        constituents = [
            {"weight": 0.10, "final_score": 90, "technical": 80},
            {"weight": 0.05, "final_score": 60, "technical": 50},
            {"weight": 0.03, "final_score": 40, "technical": 30},
        ]
        result = rollup_index(constituents)
        assert result["constituent_count"] == 3
        assert result["total_weight"] > 0
        # weighted_final = (90*0.10 + 60*0.05 + 40*0.03) / 0.18
        # = (9 + 3 + 1.2) / 0.18 = 73.33
        assert abs(result["weighted_final_score"] - 73.33) < 0.1
        assert result["breadth"]["count"] == 3

    def test_empty_index(self) -> None:
        result = rollup_index([])
        assert result["constituent_count"] == 0
        assert result["weighted_final_score"] == 0.0


# ============================================================================
# Edge cases and integration-level tests
# ============================================================================


class TestCompositeValuationExcludedFromAvg:
    """Valuation is in rescaled but not in weighted average (5 LENS_NAMES)."""

    def test_valuation_as_modifier_only(self) -> None:
        # Valuation score present but should NOT affect lenses_active count
        # (it's in _ALL_LENS_NAMES but not _LENS_NAMES)
        result = compute_composite(
            technical=None, fundamental=None,
            valuation_score=80.0,
            catalyst=None, flow=None, policy=None,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=_EMPTY_TH,
        )
        # Valuation is rescaled but no core lens is active
        assert result.lenses_active == 0
        assert "valuation" in result.rescaled


class TestTechnicalThresholdOverrides:
    """Custom thresholds override coded defaults."""

    def test_custom_ema_aligned(self) -> None:
        # Give a huge bonus for aligned EMAs
        custom_th = {"ema_aligned_all": 20}
        result = score_technical(
            ema_21=110.0, ema_50=105.0, ema_200=95.0,
            rsi_14=None, price=115.0, high_52w=None, low_52w=None,
            ret_1w=None,
            rs_1m_n500=None, rs_3m_n500=None, rs_6m_n500=None, rs_12m_n500=None,
            atr_14=None, bb_width=None, volume=None,
            avg_volume_30d=None, avg_volume_60d=None, rel_volume_10d=None,
            thresholds=custom_th,
        )
        # With ema_aligned_all=20 + price_above_ema200=5, trend = cap(25) = 25
        assert result.trend == _d(25)


class TestFundamentalROICBonus:
    """ROIC bonus adds 2 pts to profitability when ROIC > 15."""

    def test_roic_bonus(self) -> None:
        no_roic = score_fundamental(
            roe=18.0, roa=None, roic=None,
            operating_margin=None, net_margin=None, gross_margin=None,
            revenue_growth_yoy=None, eps_growth_yoy=None,
            debt_to_equity=None, current_ratio=None, quick_ratio=None,
            revenue_ttm=None, eps_diluted_ttm=None,
            thresholds=_EMPTY_TH,
        )
        with_roic = score_fundamental(
            roe=18.0, roa=None, roic=20.0,
            operating_margin=None, net_margin=None, gross_margin=None,
            revenue_growth_yoy=None, eps_growth_yoy=None,
            debt_to_equity=None, current_ratio=None, quick_ratio=None,
            revenue_ttm=None, eps_diluted_ttm=None,
            thresholds=_EMPTY_TH,
        )
        assert with_roic.profitability > no_roic.profitability


class TestCatalystStringDates:
    """Filing dates as ISO strings should also work."""

    def test_string_date(self) -> None:
        filings = [
            {
                "filing_date": "2026-06-01",
                "category_bucket": "capital",
                "subject_text": "Buyback of shares",
            },
        ]
        result = score_catalyst(filings, as_of_date=date(2026, 6, 20), thresholds=_EMPTY_TH)
        assert result.score is not None
        assert result.score > _d(0)
