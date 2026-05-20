# allow-large: single cohesive test module for the state classifier; covers all 7
# state predicates + the panel orchestrator in one file for discoverability.
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


def _stage_1_th(tightness=0.10, contraction=0.95, min_recovery=30):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_base_tightness", "stage_1"): ThresholdValue(float(tightness), None, None),
        ("theta_contraction", "stage_1"): ThresholdValue(float(contraction), None, None),
        ("theta_min_recovery_days", "stage_1"): ThresholdValue(float(min_recovery), None, None),
    }


def test_stage_1_consolidation():
    """close near SMA_150, ATR contraction, recovered from 252d low → Stage 1.

    atr_14=2.0, atr_14_252d_avg=3.0 → ratio=0.667 < 0.95 (contraction fires).
    """
    assert (
        classify_stage_1(
            close=100.0,
            sma_150=99.0,
            atr_14=2.0,
            atr_14_252d_avg=3.0,
            low_252_age_days=60,
            thresholds=_stage_1_th(),
        )
        is True
    )


def test_stage_1_negated_by_vol_expansion():
    """ATR above atr_252d_avg × theta_contraction → not stage 1 (vol expanded)."""
    # atr_14=3.5, atr_14_252d_avg=3.0 → ratio=1.167 >= 0.95 → fails contraction
    assert (
        classify_stage_1(
            close=100.0,
            sma_150=99.0,
            atr_14=3.5,
            atr_14_252d_avg=3.0,
            low_252_age_days=60,
            thresholds=_stage_1_th(),
        )
        is False
    )


def test_stage_1_nan_atr_252d_avg_returns_false():
    """NaN atr_14_252d_avg → Stage 1 returns False (NaN guard)."""
    assert (
        classify_stage_1(
            close=100.0,
            sma_150=99.0,
            atr_14=2.0,
            atr_14_252d_avg=float("nan"),
            low_252_age_days=60,
            thresholds=_stage_1_th(),
        )
        is False
    )


# ---------------------------------------------------------------------------
# Stage 2A — Fresh Breakout
# ---------------------------------------------------------------------------


def _stage_2a_th(slope_days=30, rs=70, fresh_days=21):
    # theta_base_breakout removed: IC-validated INVALID (IR 0.107/0.145, below 0.2 weak
    # floor; top-breakout-quintile underperforms bottom). Gate removed in Wave 4C Task 3.
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_slope_days", "stage_2a"): ThresholdValue(float(slope_days), None, None),
        ("theta_rs", "stage_2a"): ThresholdValue(float(rs), None, None),
        ("theta_fresh_days", "stage_2a"): ThresholdValue(float(fresh_days), None, None),
    }


def test_stage_2a_fresh_breakout():
    """All conditions for a fresh Stage 2A breakout (no volume requirement)."""
    assert (
        classify_stage_2a(
            prior_state="stage_1",
            close=110.0,
            sma_50=105.0,
            sma_150=100.0,
            sma_200=95.0,
            sma_200_slope=0.001,
            max_close_60d=107.0,
            rs_rank_12m=0.80,
            days_in_stage_2=5,
            thresholds=_stage_2a_th(),
        )
        is True
    )


def test_stage_2a_admits_below_60d_high_after_breakout_gate_removed():
    """Stock below the 60-day high is still admitted to Stage 2A.

    Wave 4C Task 3: the breakout gate (close >= theta_base_breakout * max_close_60d)
    was removed after IC validation showed IR 0.107/0.145 (below the 0.2 weak floor)
    and that the top-breakout-ratio quintile *underperforms* the bottom.

    Fixture: close=100.0, max_close_60d=108.0 — clearly below the 60-day high.
    All other validated gates pass (prior_state, MA stack, rising SMA-200, RS, fresh).
    Expected: stage_2a fires (True).
    """
    assert (
        classify_stage_2a(
            prior_state="stage_1",
            close=100.0,  # below 60-day high of 108 → old gate: 100 < 1.00*108 → FAIL
            sma_50=98.0,  # MA stack: close > sma_50 > sma_150 > sma_200
            sma_150=95.0,
            sma_200=90.0,
            sma_200_slope=0.002,  # rising SMA-200
            max_close_60d=108.0,  # 60-day high above close
            rs_rank_12m=0.75,  # rs_rank_12m * 100 = 75 >= theta_rs=70
            days_in_stage_2=3,  # within fresh window
            thresholds=_stage_2a_th(),
        )
        is True
    )


def test_stage_2a_still_rejected_when_rs_too_low():
    """Removing the breakout gate must not weaken the RS gate.

    A stock that satisfies every gate including being below the 60-day high, but
    has rs_rank_12m * 100 = 40 < theta_rs=70, must NOT be classified stage_2a.
    """
    assert (
        classify_stage_2a(
            prior_state="stage_1",
            close=100.0,
            sma_50=98.0,
            sma_150=95.0,
            sma_200=90.0,
            sma_200_slope=0.002,
            max_close_60d=108.0,
            rs_rank_12m=0.40,  # rs_rank_12m * 100 = 40 < theta_rs=70 → FAIL
            days_in_stage_2=3,
            thresholds=_stage_2a_th(),
        )
        is False
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


def _stage_3_th(distribution=5, obv_slope_neg=0.0):
    from atlas.intelligence.states.thresholds import ThresholdValue

    return {
        ("theta_distribution", "stage_3"): ThresholdValue(float(distribution), None, None),
        ("theta_obv_slope_neg", "stage_3"): ThresholdValue(float(obv_slope_neg), None, None),
    }


def test_stage_3_topping():
    """Was stage 2x, now close<SMA50 OR SMA50_slope<0, enough distribution."""
    assert (
        classify_stage_3(
            prior_state="stage_2b",
            close=98.0,
            sma_50=100.0,
            sma_50_slope=-0.001,
            distribution_days_25d=6,
            obv_slope_50d=0.5,
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
            obv_slope_50d=0.5,
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
            obv_slope_50d=0.5,
            thresholds=_stage_3_th(),
        )
        is False
    )


def test_stage_3_fires_via_obv_slope_alone():
    """OBV slope < theta_obv_slope_neg fires Stage 3 even when price condition is false.

    Price condition (close > sma_50 AND sma_50_slope >= 0) is NOT met for the
    traditional trigger, but negative OBV slope provides the topping signal.
    """
    assert (
        classify_stage_3(
            prior_state="stage_2b",
            close=105.0,  # close > sma_50 → price condition false
            sma_50=100.0,
            sma_50_slope=0.001,  # slope positive → price condition false
            distribution_days_25d=6,  # enough distribution
            obv_slope_50d=-0.001,  # negative OBV slope → fires the OBV topping signal
            thresholds=_stage_3_th(obv_slope_neg=0.0),
        )
        is True
    )


def test_stage_3_not_fired_when_obv_slope_positive_and_price_ok():
    """Positive OBV slope AND price above SMA50 AND positive SMA50 slope → not Stage 3."""
    assert (
        classify_stage_3(
            prior_state="stage_2b",
            close=105.0,
            sma_50=100.0,
            sma_50_slope=0.001,
            distribution_days_25d=6,
            obv_slope_50d=0.5,  # positive OBV → no topping signal
            thresholds=_stage_3_th(obv_slope_neg=0.0),
        )
        is False
    )


# ---------------------------------------------------------------------------
# classify_state_panel orchestrator (Task 1.6)
# ---------------------------------------------------------------------------

import pandas as pd  # noqa: E402

from atlas.intelligence.states.classifier import classify_state_panel  # noqa: E402
from atlas.intelligence.states.thresholds import ThresholdValue  # noqa: E402


def _full_thresholds():
    """Return a thresholds dict with the active thresholds after migration 078.

    Changes from migration 076/077:
    - theta_low_vol (stage_1) removed; replaced by theta_contraction (stage_1)
    - theta_vol_mult (stage_2a) removed (volume requirement dropped)
    - theta_obv_slope_neg (stage_3) added
    """
    tv = lambda v: ThresholdValue(float(v), None, None)  # noqa: E731
    return {
        # Uninvestable
        ("theta_liq", "uninvestable"): tv(100_000),
        ("theta_gap", "uninvestable"): tv(20),
        ("theta_min_price", "uninvestable"): tv(10.0),
        # Stage 1 — theta_low_vol replaced by theta_contraction (migration 078)
        ("theta_base_tightness", "stage_1"): tv(0.10),
        ("theta_contraction", "stage_1"): tv(0.95),
        ("theta_min_recovery_days", "stage_1"): tv(30),
        # Stage 2A — theta_vol_mult removed (migration 078);
        # theta_base_breakout removed (Wave 4C Task 3: IC-invalid, IR 0.107/0.145).
        # The row remains dormant in atlas_thresholds DB (no migration to delete it).
        ("theta_slope_days", "stage_2a"): tv(30),
        ("theta_rs", "stage_2a"): tv(70.0),
        ("theta_fresh_days", "stage_2a"): tv(21),
        # Stage 2B
        ("theta_confirmed_days", "stage_2b"): tv(126),
        # Stage 2C
        ("theta_extension", "stage_2c"): tv(1.10),
        ("theta_atr_expansion", "stage_2c"): tv(1.40),
        # Stage 3 — theta_obv_slope_neg added (migration 078)
        ("theta_distribution", "stage_3"): tv(5),
        ("theta_obv_slope_neg", "stage_3"): tv(0.0),
        # Stage 4
        ("theta_decline_floor", "stage_4"): tv(0.90),
        # Risk gates (unused by classifier itself)
        ("theta_dd_halt", "risk_gate"): tv(15.0),
        ("theta_sector_cap", "risk_gate"): tv(5),
    }


def _synthetic_features_panel(n_days: int = 30) -> pd.DataFrame:
    """3-stock synthetic panel: one healthy uptrend (s1), one in decline (s2),
    one penny stock (s3).

    Includes the new feature columns added in migration 078:
      - atr_14_252d_avg: ATR contraction denominator
      - obv_slope_50d: OBV slope over 50 days
    """
    rows = []
    base_date = pd.Timestamp("2026-01-01")
    for d in range(n_days):
        dt = (base_date + pd.Timedelta(days=d)).date()
        # s1: healthy uptrend — close above MAs, slope positive
        rows.append(
            {
                "instrument_id": "s1",
                "date": dt,
                "close": 200.0 + d,
                "sma_50": 195.0,
                "sma_150": 190.0,
                "sma_200": 185.0,
                "sma_50_slope": 0.001,
                "sma_150_slope": 0.001,
                "sma_200_slope": 0.001,
                "atr_14": 3.0,
                "atr_14_50d_avg": 3.0,
                "atr_14_252d_avg": 4.0,  # atr_14/atr_14_252d_avg = 0.75 < 0.95 (contraction)
                "obv_slope_50d": 0.001,  # positive OBV slope (healthy)
                "volume": 200_000,
                "volume_50d_avg": 100_000,
                "max_close_60d": 195.0,
                "rs_rank_12m": 0.85,
                "distribution_days_25d": 0,
                "distribution_days_5d": 0,
                "low_252_age_days": 100,
                "liquidity_score": 5_000_000,
                "data_gap_count": 0,
            }
        )
        # s2: decline — close < SMA stack, slopes negative
        rows.append(
            {
                "instrument_id": "s2",
                "date": dt,
                "close": 70.0,
                "sma_50": 90.0,
                "sma_150": 100.0,
                "sma_200": 110.0,
                "sma_50_slope": -0.001,
                "sma_150_slope": -0.001,
                "sma_200_slope": -0.001,
                "atr_14": 4.0,
                "atr_14_50d_avg": 4.0,
                "atr_14_252d_avg": 3.5,  # atr_14/atr_14_252d_avg = 1.14 >= 0.95 (expanded)
                "obv_slope_50d": -0.001,  # negative OBV slope (declining)
                "volume": 200_000,
                "volume_50d_avg": 100_000,
                "max_close_60d": 100.0,
                "rs_rank_12m": 0.10,
                "distribution_days_25d": 10,
                "distribution_days_5d": 2,
                "low_252_age_days": 5,
                "liquidity_score": 500_000,
                "data_gap_count": 2,
            }
        )
        # s3: penny stock — uninvestable
        rows.append(
            {
                "instrument_id": "s3",
                "date": dt,
                "close": 5.0,
                "sma_50": 5.0,
                "sma_150": 5.0,
                "sma_200": 5.0,
                "sma_50_slope": 0.0,
                "sma_150_slope": 0.0,
                "sma_200_slope": 0.0,
                "atr_14": 0.2,
                "atr_14_50d_avg": 0.2,
                "atr_14_252d_avg": 0.3,  # contraction ratio = 0.67 < 0.95
                "obv_slope_50d": 0.0,  # neutral OBV slope
                "volume": 200_000,
                "volume_50d_avg": 100_000,
                "max_close_60d": 5.0,
                "rs_rank_12m": 0.5,
                "distribution_days_25d": 0,
                "distribution_days_5d": 0,
                "low_252_age_days": 100,
                "liquidity_score": 500_000,
                "data_gap_count": 0,
            }
        )
    return pd.DataFrame(rows)


def test_classify_state_panel_returns_dataframe_with_required_columns():
    panel = classify_state_panel(_synthetic_features_panel(5), _full_thresholds(), "v1.0-test")
    required = {
        "instrument_id",
        "date",
        "state",
        "prior_state",
        "state_since_date",
        "dwell_days",
        "classifier_version",
        "rs_rank_12m",
        "close_vs_sma_50",
        "close_vs_sma_150",
        "close_vs_sma_200",
        "sma_200_slope",
        "volume_ratio_50d",
        "distribution_days",
    }
    assert required <= set(panel.columns)


def test_classify_state_panel_state_values_valid():
    panel = classify_state_panel(_synthetic_features_panel(5), _full_thresholds(), "v1.0-test")
    valid_states = {
        "uninvestable",
        "stage_1",
        "stage_2a",
        "stage_2b",
        "stage_2c",
        "stage_3",
        "stage_4",
    }
    assert panel["state"].isin(valid_states).all()


def test_classify_state_panel_uninvestable_for_penny_stock():
    """Stock 3 (penny stock) → all days uninvestable."""
    panel = classify_state_panel(_synthetic_features_panel(10), _full_thresholds(), "v1.0-test")
    s3 = panel[panel["instrument_id"] == "s3"]
    assert (s3["state"] == "uninvestable").all()


def test_classify_state_panel_dwell_increments_within_same_state():
    """When a stock stays in the same state across days, dwell_days increases."""
    panel = classify_state_panel(_synthetic_features_panel(10), _full_thresholds(), "v1.0-test")
    s1 = panel[panel["instrument_id"] == "s1"].sort_values("date").reset_index(drop=True)
    # First row has dwell_days = 0 (state just started)
    assert s1.iloc[0]["dwell_days"] == 0
    # Later rows have dwell_days > 0 IF state didn't change
    later_dwell = s1.iloc[-1]["dwell_days"]
    # Either dwell_days grew, or the state changed (in which case dwell reset)
    if s1.iloc[0]["state"] == s1.iloc[-1]["state"]:
        assert later_dwell > 0


def test_classify_state_panel_classifier_version_propagated():
    panel = classify_state_panel(_synthetic_features_panel(3), _full_thresholds(), "v9.9.9-custom")
    assert (panel["classifier_version"] == "v9.9.9-custom").all()


def test_classify_state_panel_state_since_date_resets_on_transition():
    """When state changes, state_since_date updates to the transition date."""
    # Construct a panel where stock transitions Stage 1 → Stage 2A on day 5
    rows = []
    base = pd.Timestamp("2026-01-01")
    for d in range(10):
        dt = (base + pd.Timedelta(days=d)).date()
        if d < 5:
            # Stage 1 conditions
            row = {
                "instrument_id": "x",
                "date": dt,
                "close": 100.0,
                "sma_50": 99.0,
                "sma_150": 100.0,
                "sma_200": 99.0,
                "sma_50_slope": 0.0,
                "sma_150_slope": 0.0,
                "sma_200_slope": 0.0,
                "atr_14": 1.0,
                "atr_14_50d_avg": 1.0,
                "atr_14_252d_avg": 2.0,  # contraction ratio = 0.5 < 0.95
                "obv_slope_50d": 0.0,
                "volume": 100_000,
                "volume_50d_avg": 100_000,
                "max_close_60d": 100.0,
                "rs_rank_12m": 0.5,
                "distribution_days_25d": 0,
                "distribution_days_5d": 0,
                "low_252_age_days": 100,
                "liquidity_score": 500_000,
                "data_gap_count": 0,
            }
        else:
            # Stage 2A breakout conditions
            row = {
                "instrument_id": "x",
                "date": dt,
                "close": 130.0,
                "sma_50": 110.0,
                "sma_150": 105.0,
                "sma_200": 100.0,
                "sma_50_slope": 0.001,
                "sma_150_slope": 0.001,
                "sma_200_slope": 0.001,
                "atr_14": 2.0,
                "atr_14_50d_avg": 2.0,
                "atr_14_252d_avg": 3.0,  # contraction ratio = 0.67 < 0.95
                "obv_slope_50d": 0.001,
                "volume": 300_000,
                "volume_50d_avg": 100_000,
                "max_close_60d": 115.0,
                "rs_rank_12m": 0.90,
                "distribution_days_25d": 0,
                "distribution_days_5d": 0,
                "low_252_age_days": 100,
                "liquidity_score": 5_000_000,
                "data_gap_count": 0,
            }
        rows.append(row)
    panel = classify_state_panel(pd.DataFrame(rows), _full_thresholds(), "v1.0-test")
    # On day 5 the state should change. Verify state_since_date updates.
    by_day = panel.sort_values("date").reset_index(drop=True)
    # State on day 5 should differ from day 4
    assert by_day.iloc[5]["state"] != by_day.iloc[4]["state"]
    # state_since_date on day 5 should equal day-5 date (just transitioned)
    assert by_day.iloc[5]["state_since_date"] == by_day.iloc[5]["date"]


# ---------------------------------------------------------------------------
# Task 4: Stage 2B/2C reachability — mid-trend admission (Wave 4C)
# ---------------------------------------------------------------------------
# A stock observed for the first time (or returning after a data gap) when its
# structural indicators already show a confirmed uptrend must be admitted directly
# to Stage 2B or 2C without being forced through a 21-day Stage-2A holding period.
#
# The gap: in_stage_2 = is_currently_in_2 and trend_ok. When prior = "stage_1"
# (default cold-start), is_currently_in_2 = False, so in_stage_2 = False, which
# blocks 2B/2C regardless of structural conditions. The stock lands in 2A (days=0)
# and must wait 21 days before advancing — misclassifying a stock already deep
# in a confirmed uptrend.


def _mid_trend_2b_row(instrument_id: str = "mid_trend") -> dict:
    """A single-row feature dict for a stock clearly in a 2B confirmed uptrend.

    Structural conditions satisfied:
      - Full uptrend MA stack: close > sma_50 > sma_150 > sma_200
      - sma_200_slope > 0 (rising long-term trend)
      - rs_rank_12m * 100 = 80 >= theta_rs=70
      - distribution_days_5d = 0 (no distribution)
      - close > sma_50 (price above short MA)
      - NOT price-extended (close/sma_50 = 105/100 = 1.05, well below theta_extension=1.10)
      - NOT ATR-expanded (atr_14/atr_14_50d_avg = 1.0, below theta_atr_expansion=1.40)

    This stock has been in an uptrend for 100+ days but the classifier has no
    prior stage-2 history — prior_state defaults to "stage_1".
    """
    return {
        "instrument_id": instrument_id,
        "date": pd.Timestamp("2026-03-01").date(),
        "close": 105.0,
        "sma_50": 100.0,
        "sma_150": 95.0,
        "sma_200": 90.0,
        "sma_50_slope": 0.002,
        "sma_150_slope": 0.001,
        "sma_200_slope": 0.001,
        "atr_14": 2.0,
        "atr_14_50d_avg": 2.0,  # ratio = 1.0 < 1.40 (not expanded → not 2C via ATR)
        "atr_14_252d_avg": 3.0,  # atr/252d = 0.67 < 0.95 (contraction satisfied)
        "obv_slope_50d": 0.001,
        "volume": 500_000,
        "volume_50d_avg": 200_000,
        "max_close_60d": 106.0,
        "rs_rank_12m": 0.80,  # 80 >= theta_rs=70
        "distribution_days_25d": 0,
        "distribution_days_5d": 0,  # no distribution → 2B condition met
        "low_252_age_days": 120,
        "liquidity_score": 5_000_000,
        "data_gap_count": 0,
    }


def _mid_trend_2c_row(instrument_id: str = "mid_trend_2c") -> dict:
    """A single-row feature dict for a stock clearly in a 2C mature uptrend.

    Structural 2C trigger: close / sma_50 = 120/100 = 1.20 > theta_extension=1.10
    (price-extended — would be 2C regardless of days counter).
    MA stack and RS conditions still met.
    """
    return {
        "instrument_id": instrument_id,
        "date": pd.Timestamp("2026-03-01").date(),
        "close": 120.0,
        "sma_50": 100.0,
        "sma_150": 95.0,
        "sma_200": 90.0,
        "sma_50_slope": 0.003,
        "sma_150_slope": 0.002,
        "sma_200_slope": 0.001,
        "atr_14": 2.0,
        "atr_14_50d_avg": 2.0,
        "atr_14_252d_avg": 3.0,
        "obv_slope_50d": 0.001,
        "volume": 500_000,
        "volume_50d_avg": 200_000,
        "max_close_60d": 118.0,
        "rs_rank_12m": 0.80,
        "distribution_days_25d": 0,
        "distribution_days_5d": 0,
        "low_252_age_days": 120,
        "liquidity_score": 5_000_000,
        "data_gap_count": 0,
    }


def test_stage_2b_direct_admission_from_cold_start():
    """Task 4 fix: a stock with a confirmed uptrend MA structure first observed
    without prior stage-2 history (cold start / prior_state effectively stage_1)
    must be admitted to Stage 2B directly, without spending 21 days in Stage 2A.

    Structural conditions (all met by fixture):
      - close > sma_50 > sma_150 > sma_200 (full uptrend MA stack)
      - distribution_days_5d == 0 (no recent selling pressure)
      - close > sma_50 (price above short MA)
      - NOT price-extended (close/sma_50 = 1.05 < theta_extension=1.10)
      - NOT ATR-expanded (ratio = 1.0 < theta_atr_expansion=1.40)

    Expected state: stage_2b (not stage_2a, not stage_1).
    """
    panel = classify_state_panel(
        pd.DataFrame([_mid_trend_2b_row()]), _full_thresholds(), "v1.0-test"
    )
    assert (
        panel.iloc[0]["state"] == "stage_2b"
    ), f"Expected stage_2b for cold-start mid-trend stock, got {panel.iloc[0]['state']}"


def test_stage_2c_direct_admission_from_cold_start():
    """Task 4 fix: a price-extended stock (close/sma_50 > theta_extension) first
    observed without prior stage-2 history must be admitted to Stage 2C directly.

    Structural 2C trigger used: extension (close/sma_50 = 1.20 > theta_extension=1.10).
    Expected state: stage_2c (not stage_2a, not stage_2b, not stage_1).
    """
    panel = classify_state_panel(
        pd.DataFrame([_mid_trend_2c_row()]), _full_thresholds(), "v1.0-test"
    )
    assert (
        panel.iloc[0]["state"] == "stage_2c"
    ), f"Expected stage_2c for cold-start price-extended stock, got {panel.iloc[0]['state']}"


def test_stage_2b_normal_progression_from_stage_1_still_goes_through_2a():
    """Regression: a stock transitioning from a genuine Stage-1 base (not a
    confirmed uptrend) still enters Stage 2A first, not 2B directly.

    Stage 1 structural conditions met on day 1 (tightness, contraction, recovery).
    On day 2, uptrend conditions suddenly met — but days_in_stage_2 = 0 and this
    is a fresh breakout → must be classified stage_2a, NOT stage_2b.

    This test ensures the mid-trend admission path does NOT admit a genuinely fresh
    breakout directly to 2B, bypassing the 2A freshness window.
    """
    base = pd.Timestamp("2026-01-01")
    rows = [
        # Day 1: genuine Stage 1 base (close near sma_150, vol contracted)
        {
            "instrument_id": "fresh_break",
            "date": base.date(),
            "close": 100.5,  # tightness = 0.005 < 0.10
            "sma_50": 100.0,
            "sma_150": 100.0,
            "sma_200": 99.0,
            "sma_50_slope": 0.0,
            "sma_150_slope": 0.0,
            "sma_200_slope": 0.001,
            "atr_14": 1.5,
            "atr_14_50d_avg": 1.5,
            "atr_14_252d_avg": 2.5,  # ratio = 0.6 < 0.95 → contraction
            "obv_slope_50d": 0.0,
            "volume": 100_000,
            "volume_50d_avg": 100_000,
            "max_close_60d": 101.0,
            "rs_rank_12m": 0.75,
            "distribution_days_25d": 0,
            "distribution_days_5d": 0,
            "low_252_age_days": 60,
            "liquidity_score": 2_000_000,
            "data_gap_count": 0,
        },
        # Day 2: fresh breakout — uptrend MA stack, but only 1 day into stage 2
        {
            "instrument_id": "fresh_break",
            "date": (base + pd.Timedelta(days=1)).date(),
            "close": 115.0,
            "sma_50": 108.0,
            "sma_150": 104.0,
            "sma_200": 100.0,
            "sma_50_slope": 0.002,
            "sma_150_slope": 0.001,
            "sma_200_slope": 0.001,
            "atr_14": 2.0,
            "atr_14_50d_avg": 2.0,
            "atr_14_252d_avg": 3.0,
            "obv_slope_50d": 0.001,
            "volume": 500_000,
            "volume_50d_avg": 100_000,
            "max_close_60d": 112.0,
            "rs_rank_12m": 0.80,
            "distribution_days_25d": 0,
            "distribution_days_5d": 0,
            "low_252_age_days": 61,
            "liquidity_score": 5_000_000,
            "data_gap_count": 0,
        },
    ]
    panel = classify_state_panel(pd.DataFrame(rows), _full_thresholds(), "v1.0-test")
    by_day = panel.sort_values("date").reset_index(drop=True)
    # Day 2 (index 1): must be stage_2a, NOT stage_2b — this is a fresh breakout
    assert (
        by_day.iloc[1]["state"] == "stage_2a"
    ), f"Fresh breakout must enter 2A first, got {by_day.iloc[1]['state']}"
