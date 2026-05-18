from atlas.intelligence.states.classifier import (
    classify_stage_1,
    classify_stage_2a,
    classify_stage_2b,
    classify_stage_2c,
    classify_stage_3,
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


# ---------------------------------------------------------------------------
# Stage 1 — Base / Consolidation
# ---------------------------------------------------------------------------


def _stage_1_th(tightness=0.10, low_vol=0.035, min_recovery=30):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_base_tightness", "stage_1"): ThresholdValue(float(tightness), None, None),
        ("theta_low_vol", "stage_1"): ThresholdValue(float(low_vol), None, None),
        ("theta_min_recovery_days", "stage_1"): ThresholdValue(float(min_recovery), None, None),
    }


def test_stage_1_consolidation():
    """close near SMA_150, low ATR, recovered from 252d low → Stage 1."""
    assert (
        classify_stage_1(
            close=100.0,
            sma_150=99.0,
            atr_14=2.0,
            low_252_age_days=60,
            thresholds=_stage_1_th(),
        )
        is True
    )


def test_stage_1_negated_by_high_vol():
    """ATR/close above θ_low_vol → not stage 1."""
    assert (
        classify_stage_1(
            close=100.0,
            sma_150=99.0,
            atr_14=10.0,
            low_252_age_days=60,
            thresholds=_stage_1_th(),
        )
        is False
    )


# ---------------------------------------------------------------------------
# Stage 2A — Fresh Breakout
# ---------------------------------------------------------------------------


def _stage_2a_th(slope_days=30, breakout=1.02, vol_mult=1.5, rs=70, fresh_days=21):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_slope_days", "stage_2a"): ThresholdValue(float(slope_days), None, None),
        ("theta_base_breakout", "stage_2a"): ThresholdValue(float(breakout), None, None),
        ("theta_vol_mult", "stage_2a"): ThresholdValue(float(vol_mult), None, None),
        ("theta_rs", "stage_2a"): ThresholdValue(float(rs), None, None),
        ("theta_fresh_days", "stage_2a"): ThresholdValue(float(fresh_days), None, None),
    }


def test_stage_2a_fresh_breakout():
    """All conditions for a fresh Stage 2A breakout."""
    assert (
        classify_stage_2a(
            prior_state="stage_1",
            close=110.0,
            sma_50=105.0,
            sma_150=100.0,
            sma_200=95.0,
            sma_200_slope=0.001,
            max_close_60d=107.0,
            volume_today=200_000,
            volume_50d_avg=100_000,
            rs_rank_12m=0.80,
            days_in_stage_2=5,
            thresholds=_stage_2a_th(),
        )
        is True
    )


def test_stage_2a_negated_when_prior_is_stage_2x():
    """prior_state must be 1 or 4 for 2A to fire (transition gate)."""
    assert (
        classify_stage_2a(
            prior_state="stage_2b",
            close=110.0,
            sma_50=105.0,
            sma_150=100.0,
            sma_200=95.0,
            sma_200_slope=0.001,
            max_close_60d=107.0,
            volume_today=200_000,
            volume_50d_avg=100_000,
            rs_rank_12m=0.80,
            days_in_stage_2=5,
            thresholds=_stage_2a_th(),
        )
        is False
    )


# ---------------------------------------------------------------------------
# Stage 2B — Confirmed
# ---------------------------------------------------------------------------


def _stage_2b_th(fresh_days=21, confirmed_days=126):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_fresh_days", "stage_2a"): ThresholdValue(float(fresh_days), None, None),
        ("theta_confirmed_days", "stage_2b"): ThresholdValue(float(confirmed_days), None, None),
    }


def test_stage_2b_confirmed():
    """In stage 2, 22-126 days in, no distribution, close > SMA50."""
    assert (
        classify_stage_2b(
            in_stage_2=True,
            days_in_stage_2=45,
            distribution_days_5d=0,
            close=110.0,
            sma_50=105.0,
            thresholds=_stage_2b_th(),
        )
        is True
    )


def test_stage_2b_negated_by_distribution():
    """Distribution days in last 5 disqualify Stage 2B."""
    assert (
        classify_stage_2b(
            in_stage_2=True,
            days_in_stage_2=45,
            distribution_days_5d=1,
            close=110.0,
            sma_50=105.0,
            thresholds=_stage_2b_th(),
        )
        is False
    )


# ---------------------------------------------------------------------------
# Stage 2C — Mature
# ---------------------------------------------------------------------------


def _stage_2c_th(confirmed_days=126, extension=1.10, atr_expansion=1.40):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_confirmed_days", "stage_2b"): ThresholdValue(float(confirmed_days), None, None),
        ("theta_extension", "stage_2c"): ThresholdValue(float(extension), None, None),
        ("theta_atr_expansion", "stage_2c"): ThresholdValue(float(atr_expansion), None, None),
    }


def test_stage_2c_mature_by_days():
    """In stage 2 beyond θ_confirmed_days → Stage 2C."""
    assert (
        classify_stage_2c(
            in_stage_2=True,
            days_in_stage_2=200,
            close=110.0,
            sma_50=105.0,
            atr_14=2.0,
            atr_14_50d_avg=2.0,
            thresholds=_stage_2c_th(),
        )
        is True
    )


def test_stage_2c_mature_by_extension():
    """Close > 1.1*SMA_50 (extended) → Stage 2C even before confirmed_days."""
    assert (
        classify_stage_2c(
            in_stage_2=True,
            days_in_stage_2=80,
            close=120.0,
            sma_50=100.0,
            atr_14=2.0,
            atr_14_50d_avg=2.0,
            thresholds=_stage_2c_th(),
        )
        is True
    )


def test_stage_2c_negated_when_not_in_stage_2():
    """Must be in stage 2 to be classified 2C."""
    assert (
        classify_stage_2c(
            in_stage_2=False,
            days_in_stage_2=200,
            close=120.0,
            sma_50=100.0,
            atr_14=2.0,
            atr_14_50d_avg=2.0,
            thresholds=_stage_2c_th(),
        )
        is False
    )


# ---------------------------------------------------------------------------
# Stage 3 — Top
# ---------------------------------------------------------------------------


def _stage_3_th(distribution=5):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {("theta_distribution", "stage_3"): ThresholdValue(float(distribution), None, None)}


def test_stage_3_topping():
    """Was stage 2x, now close<SMA50 OR SMA50_slope<0, enough distribution."""
    assert (
        classify_stage_3(
            prior_state="stage_2b",
            close=98.0,
            sma_50=100.0,
            sma_50_slope=-0.001,
            distribution_days_25d=6,
            thresholds=_stage_3_th(),
        )
        is True
    )


def test_stage_3_negated_by_low_distribution():
    """Not enough distribution days → not stage 3 yet."""
    assert (
        classify_stage_3(
            prior_state="stage_2b",
            close=98.0,
            sma_50=100.0,
            sma_50_slope=-0.001,
            distribution_days_25d=2,
            thresholds=_stage_3_th(),
        )
        is False
    )


def test_stage_3_negated_when_prior_is_not_stage_2x():
    """Stage 3 can only follow Stage 2 (any sub-state)."""
    assert (
        classify_stage_3(
            prior_state="stage_1",
            close=98.0,
            sma_50=100.0,
            sma_50_slope=-0.001,
            distribution_days_25d=6,
            thresholds=_stage_3_th(),
        )
        is False
    )
