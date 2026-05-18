from atlas.intelligence.states.classifier import (
    classify_stage_4,
    classify_uninvestable,
)

# ---------------------------------------------------------------------------
# Uninvestable
# ---------------------------------------------------------------------------


def _uninv_th(liq=100_000, gap=20, min_price=10.0):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_liq", "uninvestable"): ThresholdValue(float(liq), None, None),
        ("theta_gap", "uninvestable"): ThresholdValue(float(gap), None, None),
        ("theta_min_price", "uninvestable"): ThresholdValue(float(min_price), None, None),
    }


def test_uninvestable_low_liquidity():
    """50d avg ₹ volume below θ_liq → uninvestable."""
    assert (
        classify_uninvestable(
            liquidity_score=50_000,
            data_gap_count=0,
            close=100.0,
            thresholds=_uninv_th(),
        )
        is True
    )


def test_uninvestable_too_many_data_gaps():
    """Too many missing trading days in 252d → uninvestable."""
    assert (
        classify_uninvestable(
            liquidity_score=500_000,
            data_gap_count=25,
            close=100.0,
            thresholds=_uninv_th(),
        )
        is True
    )


def test_uninvestable_penny_stock():
    """Price below θ_min_price → uninvestable."""
    assert (
        classify_uninvestable(
            liquidity_score=500_000,
            data_gap_count=0,
            close=5.0,
            thresholds=_uninv_th(),
        )
        is True
    )


def test_uninvestable_healthy_stock():
    assert (
        classify_uninvestable(
            liquidity_score=500_000,
            data_gap_count=2,
            close=300.0,
            thresholds=_uninv_th(),
        )
        is False
    )


# ---------------------------------------------------------------------------
# Stage 4 — Decline
# ---------------------------------------------------------------------------


def _stage_4_th(floor=0.90):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {("theta_decline_floor", "stage_4"): ThresholdValue(float(floor), None, None)}


def test_stage_4_downtrend():
    """close < SMA_150 < SMA_200 AND SMA_150 sloping down AND close < 0.9*SMA_200 → Stage 4."""
    assert (
        classify_stage_4(
            close=80.0,
            sma_150=100.0,
            sma_200=110.0,
            sma_150_slope=-0.01,
            thresholds=_stage_4_th(),
        )
        is True
    )


def test_stage_4_negated_by_uptrend_ma_order():
    """If MA stack is uptrend-aligned (SMA_150 > SMA_200), NOT stage 4."""
    assert (
        classify_stage_4(
            close=120.0,
            sma_150=110.0,
            sma_200=100.0,
            sma_150_slope=0.01,
            thresholds=_stage_4_th(),
        )
        is False
    )


def test_stage_4_negated_by_flat_slope():
    """SMA_150 slope >= 0 disqualifies Stage 4."""
    assert (
        classify_stage_4(
            close=80.0,
            sma_150=100.0,
            sma_200=110.0,
            sma_150_slope=0.0,
            thresholds=_stage_4_th(),
        )
        is False
    )


def test_stage_4_negated_by_close_above_floor():
    """close >= floor * SMA_200 disqualifies even with MA-stack inversion."""
    # SMA_200 = 110, floor = 0.90 → floor * SMA_200 = 99
    # close = 105 (above 99), Stage 4 should NOT fire.
    assert (
        classify_stage_4(
            close=105.0,
            sma_150=100.0,
            sma_200=110.0,
            sma_150_slope=-0.01,
            thresholds=_stage_4_th(),
        )
        is False
    )


def test_stage_4_nan_inputs_return_false():
    """NaN in any input returns False (not Stage 4)."""
    assert (
        classify_stage_4(
            close=float("nan"),
            sma_150=100.0,
            sma_200=110.0,
            sma_150_slope=-0.01,
            thresholds=_stage_4_th(),
        )
        is False
    )
