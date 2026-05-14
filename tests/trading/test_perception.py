import numpy as np

from atlas.trading.genome import GenomeFactory
from atlas.trading.perception import (
    MOM_ACCELERATING,
    MOM_DECELERATING,
    MOM_NEUTRAL,
    REGIME_CAUTIOUS,
    REGIME_CONSTRUCTIVE,
    REGIME_RISK_OFF,
    REGIME_RISK_ON,
    RS_AVERAGE,
    RS_LAGGARD,
    RS_LEADER,
    RS_STRONG,
    RS_WEAK,
    VOL_ELEVATED,
    VOL_HIGH,
    VOL_NORMAL,
    compute_blended_rs_pctile,
    compute_rs_velocity,
    derive_momentum_state,
    derive_regime_state,
    derive_rs_state,
    derive_vol_state,
)


def _genome():
    g = GenomeFactory.random()
    g.layer1.rs_leader_cutoff_pct = 70
    g.layer1.rs_strong_cutoff_pct = 55
    g.layer1.rs_average_cutoff_pct = 35
    g.layer1.rs_weak_cutoff_pct = 20
    g.layer1.vol_elevated_ratio = 1.4
    g.layer1.vol_high_ratio = 1.75
    g.layer1.momentum_accel_ema_ratio = 1.02
    g.layer1.momentum_decel_ema_ratio = 0.985
    g.layer1.regime_risk_on_breadth_pct = 60
    g.layer1.regime_constructive_breadth_pct = 45
    g.layer1.regime_cautious_breadth_pct = 30
    g.layer1.regime_risk_on_vix_ceiling = 18.0
    g.layer1.state_velocity_lookback_days = 5
    return g


def test_rs_state_leader():
    g = _genome()
    rs = np.array([[85.0]])
    assert derive_rs_state(rs, g.layer1)[0, 0] == RS_LEADER


def test_rs_state_strong():
    g = _genome()
    rs = np.array([[60.0]])
    assert derive_rs_state(rs, g.layer1)[0, 0] == RS_STRONG


def test_rs_state_average():
    g = _genome()
    rs = np.array([[40.0]])
    assert derive_rs_state(rs, g.layer1)[0, 0] == RS_AVERAGE


def test_rs_state_weak():
    g = _genome()
    rs = np.array([[22.0]])
    assert derive_rs_state(rs, g.layer1)[0, 0] == RS_WEAK


def test_rs_state_laggard():
    g = _genome()
    rs = np.array([[10.0]])
    assert derive_rs_state(rs, g.layer1)[0, 0] == RS_LAGGARD


def test_regime_risk_on():
    g = _genome()
    breadth = np.array([65.0])
    vix = np.array([15.0])
    assert derive_regime_state(breadth, vix, g.layer1)[0] == REGIME_RISK_ON


def test_regime_constructive_vix_too_high():
    g = _genome()
    breadth = np.array([65.0])  # > risk_on threshold
    vix = np.array([20.0])  # > vix ceiling → not risk_on
    state = derive_regime_state(breadth, vix, g.layer1)[0]
    assert state == REGIME_CONSTRUCTIVE


def test_regime_cautious():
    g = _genome()
    breadth = np.array([35.0])
    vix = np.array([25.0])
    assert derive_regime_state(breadth, vix, g.layer1)[0] == REGIME_CAUTIOUS


def test_regime_risk_off():
    g = _genome()
    breadth = np.array([10.0])
    vix = np.array([30.0])
    assert derive_regime_state(breadth, vix, g.layer1)[0] == REGIME_RISK_OFF


def test_regime_vix_nan_still_classifies():
    g = _genome()
    breadth = np.array([65.0])
    vix = np.array([float("nan")])
    # NaN VIX: vix_calm = False, so risk_on requires valid calm VIX
    state = derive_regime_state(breadth, vix, g.layer1)[0]
    assert state == REGIME_CONSTRUCTIVE


def test_vol_normal():
    g = _genome()
    assert derive_vol_state(np.array([[1.2]]), g.layer1)[0, 0] == VOL_NORMAL


def test_vol_elevated():
    g = _genome()
    assert derive_vol_state(np.array([[1.5]]), g.layer1)[0, 0] == VOL_ELEVATED


def test_vol_high():
    g = _genome()
    assert derive_vol_state(np.array([[2.0]]), g.layer1)[0, 0] == VOL_HIGH


def test_momentum_accelerating():
    g = _genome()
    assert derive_momentum_state(np.array([[1.03]]), g.layer1)[0, 0] == MOM_ACCELERATING


def test_momentum_decelerating():
    g = _genome()
    assert derive_momentum_state(np.array([[0.98]]), g.layer1)[0, 0] == MOM_DECELERATING


def test_momentum_neutral():
    g = _genome()
    assert derive_momentum_state(np.array([[1.00]]), g.layer1)[0, 0] == MOM_NEUTRAL


def test_blended_rs_pctile_weights():
    arrays = {
        "1w": np.array([[80.0, 80.0]]),
        "1m": np.array([[60.0, 60.0]]),
        "3m": np.array([[40.0, 40.0]]),
    }
    weights = {"1w": 0.5, "1m": 0.3, "3m": 0.2}
    result = compute_blended_rs_pctile(arrays, weights)
    expected = 0.5 * 80.0 + 0.3 * 60.0 + 0.2 * 40.0  # 66.0
    assert abs(result[0, 0] - expected) < 1e-4


def test_rs_velocity_shape():
    rs_state = np.array([[0, 1, 1, 2, 2, 2]], dtype=np.int8)
    days_in, direction = compute_rs_velocity(rs_state, lookback=2)
    assert days_in.shape == rs_state.shape
    assert direction.shape == rs_state.shape
    assert days_in[0, 2] == 2  # state 1 repeated
    assert days_in[0, 4] == 2  # state 2 repeated (2nd time)
    assert direction[0, 4] == 1  # improved from 1 → 2 over lookback=2
