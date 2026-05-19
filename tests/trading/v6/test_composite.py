"""Tests for atlas.trading.v6.composite — composite scorer + selection + buffer zones.

Eight tests covering:
1. test_composite_zero_when_signal_at_sector_mean
2. test_composite_winsorizes_extremes
3. test_composite_weighted_sum_correct
4. test_select_entries_respect_enter_cutoff
5. test_select_buffer_holds_yesterday_winners
6. test_select_exits_rank_above_50
7. test_select_governance_exclusions_force_exit
8. test_select_trend_gate_blocks_new_entries
"""

from __future__ import annotations

import uuid

import pandas as pd

from atlas.trading.v6.composite import (
    SelectionResult,
    SignalWeights,
    compute_composite,
    select,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_panel(
    ids: list[uuid.UUID],
    sectors: list[str],
    signal_values: dict[str, list[float]],
) -> pd.DataFrame:
    """Build a signals_panel DataFrame indexed by instrument_id."""
    data = {"sector": sectors, **signal_values}
    return pd.DataFrame(data, index=ids)


def _make_ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


# ---------------------------------------------------------------------------
# Test 1 — z=0 when signal equals sector mean
# ---------------------------------------------------------------------------


def test_composite_zero_when_signal_at_sector_mean() -> None:
    """Any instrument whose every signal equals the sector mean gets composite = 0."""
    ids = _make_ids(3)
    # All three are in the same sector, all have the same signal value → mean = value → z = 0
    panel = _make_panel(
        ids=ids,
        sectors=["Tech", "Tech", "Tech"],
        signal_values={
            "natr_14": [1.0, 1.0, 1.0],
            "beta_alpha_63d": [0.5, 0.5, 0.5],
            "mom_low_vol": [0.3, 0.3, 0.3],
            "residual_momentum": [0.2, 0.2, 0.2],
            "proximity_52wh": [0.8, 0.8, 0.8],
            "industry_rs": [0.1, 0.1, 0.1],
            "fip_smoothness": [0.4, 0.4, 0.4],
            "bab": [0.6, 0.6, 0.6],
            "quality_proxy": [0.7, 0.7, 0.7],
        },
    )
    weights = SignalWeights()
    result = compute_composite(panel, weights=weights)

    assert isinstance(result, pd.Series)
    assert len(result) == 3
    # All at sector mean → composite = 0 for all
    for iid in ids:
        assert abs(result[iid]) < 1e-9, f"Expected 0 for {iid}, got {result[iid]}"


# ---------------------------------------------------------------------------
# Test 2 — winsorization at ±3
# ---------------------------------------------------------------------------


def test_composite_winsorizes_extremes() -> None:
    """Extreme signal outlier is capped at winsorize_z=3 standard deviations.

    Design: 20 instruments in one sector, 19 with natr_14=0 and 1 with natr_14=10.
    With ddof=1, z for the outlier ≈ 4.25 > 3 → clipped to 3.0.
    All other signals are 0 for every instrument → z=0 → no contribution.
    Expected composite for outlier = normalized_weight(natr_14) * 3.0.
    """
    n = 20
    ids = _make_ids(n)
    # 19 zeros, 1 extreme outlier for natr_14; all other signals = 0 throughout
    natr_values = [0.0] * (n - 1) + [10.0]
    signal_values = {
        "natr_14": natr_values,
        "beta_alpha_63d": [0.0] * n,
        "mom_low_vol": [0.0] * n,
        "residual_momentum": [0.0] * n,
        "proximity_52wh": [0.0] * n,
        "industry_rs": [0.0] * n,
        "fip_smoothness": [0.0] * n,
        "bab": [0.0] * n,
        "quality_proxy": [0.0] * n,
    }
    panel = _make_panel(
        ids=ids,
        sectors=["A"] * n,
        signal_values=signal_values,
    )
    result = compute_composite(panel, winsorize_z=3.0)

    # The outlier at ids[-1] has z ≈ 4.25 (clipped to 3.0); all other signals contribute 0
    w = SignalWeights()
    # After normalization: weight(natr_14) = 0.15 / 0.99
    norm_natr = w.natr_14 / sum(w.as_dict().values())
    expected_outlier = norm_natr * 3.0  # ≈ 0.4545

    assert abs(result[ids[-1]] - expected_outlier) < 1e-6, (
        f"Expected {expected_outlier:.6f}, got {result[ids[-1]]:.6f}"
    )
    # All 19 zero-value instruments must have negative composite (they are below sector mean)
    for iid in ids[:-1]:
        assert result[iid] < 0.0, "Below-mean instrument should have negative composite"


# ---------------------------------------------------------------------------
# Test 3 — weighted sum arithmetic
# ---------------------------------------------------------------------------


def test_composite_weighted_sum_correct() -> None:
    """Verify weight × z arithmetic on a synthetic panel with known z-scores.

    Setup: two sectors A and B, each with 2 instruments.
    All signal values: sector A: [10, 0], sector B: [10, 0].
    With ddof=1: mean=5, std=sqrt(50)=7.0711, so z for 10 = (10-5)/7.0711 = +0.7071.
    Weights are normalized to sum=1.0, so expected composite = 1.0 × 0.7071 = 0.7071.
    """
    ids = _make_ids(4)
    signal_cols = [
        "natr_14",
        "beta_alpha_63d",
        "mom_low_vol",
        "residual_momentum",
        "proximity_52wh",
        "industry_rs",
        "fip_smoothness",
        "bab",
        "quality_proxy",
    ]
    signal_values = {col: [10.0, 0.0, 10.0, 0.0] for col in signal_cols}
    panel = _make_panel(
        ids=ids,
        sectors=["A", "A", "B", "B"],
        signal_values=signal_values,
    )
    w = SignalWeights()
    result = compute_composite(panel, weights=w)

    # sector A: mean=5, std(ddof=1)=7.0711; z(10)=+0.7071, z(0)=-0.7071
    # normalized weights sum to 1.0 → composite = 1.0 × 0.7071
    import math

    expected_high = math.sqrt(0.5)  # = 1/sqrt(2) ≈ 0.7071
    expected_low = -expected_high

    # ids[0] and ids[2] are the "high" instruments (value=10)
    assert abs(result[ids[0]] - expected_high) < 1e-6, (
        f"ids[0] expected {expected_high:.6f}, got {result[ids[0]]:.6f}"
    )
    assert abs(result[ids[2]] - expected_high) < 1e-6, (
        f"ids[2] expected {expected_high:.6f}, got {result[ids[2]]:.6f}"
    )
    # ids[1] and ids[3] are the "low" instruments (value=0)
    assert abs(result[ids[1]] - expected_low) < 1e-6, (
        f"ids[1] expected {expected_low:.6f}, got {result[ids[1]]:.6f}"
    )
    assert abs(result[ids[3]] - expected_low) < 1e-6, (
        f"ids[3] expected {expected_low:.6f}, got {result[ids[3]]:.6f}"
    )


# ---------------------------------------------------------------------------
# Test 4 — entries respect enter_rank_cutoff=30
# ---------------------------------------------------------------------------


def test_select_entries_respect_enter_cutoff() -> None:
    """Names ranked 1..30 enter; names ranked 31+ are NOT entered (unless held)."""
    n = 60
    ids = _make_ids(n)
    # Composite scores: rank 1 = highest. Use descending float values.
    scores = {iid: float(n - i) for i, iid in enumerate(ids)}
    composite = pd.Series(scores)

    result = select(
        composite=composite,
        governance_excluded=set(),
        trend_gate_pass=set(ids),  # all pass trend gate
        held_yesterday=set(),
        enter_rank_cutoff=30,
        stay_rank_cutoff=50,
    )

    assert isinstance(result, SelectionResult)
    # Exactly top 30 should enter
    expected_entered = set(ids[:30])
    assert set(result.entered) == expected_entered, (
        f"Expected entered={expected_entered}, got {set(result.entered)}"
    )
    assert len(result.held) == 0
    assert len(result.exited) == 0


# ---------------------------------------------------------------------------
# Test 5 — buffer zone holds yesterday's winners
# ---------------------------------------------------------------------------


def test_select_buffer_holds_yesterday_winners() -> None:
    """Name at rank 35 (between enter=30 and stay=50) stays if held yesterday, else bench_hold."""
    n = 60
    ids = _make_ids(n)
    scores = {iid: float(n - i) for i, iid in enumerate(ids)}
    composite = pd.Series(scores)

    rank_35_id = ids[34]  # 0-indexed → rank 35 (1-indexed)

    # Case A: rank-35 name was held yesterday → should be in 'held'
    result_a = select(
        composite=composite,
        governance_excluded=set(),
        trend_gate_pass=set(ids),
        held_yesterday={rank_35_id},
        enter_rank_cutoff=30,
        stay_rank_cutoff=50,
    )
    assert rank_35_id in result_a.held, "rank-35 held yesterday should stay in held"
    assert rank_35_id not in result_a.exited
    assert rank_35_id not in result_a.entered

    # Case B: rank-35 name NOT held yesterday AND passes trend gate → bench_hold
    # (rank > 30 so can't enter even though trend gate passes)
    result_b = select(
        composite=composite,
        governance_excluded=set(),
        trend_gate_pass=set(ids),
        held_yesterday=set(),
        enter_rank_cutoff=30,
        stay_rank_cutoff=50,
    )
    assert rank_35_id in result_b.bench_hold, (
        f"rank-35 not held, passes trend gate → bench_hold; "
        f"entered={result_b.entered}, bench_hold={result_b.bench_hold}"
    )


# ---------------------------------------------------------------------------
# Test 6 — exit when rank > stay_cutoff
# ---------------------------------------------------------------------------


def test_select_exits_rank_above_50() -> None:
    """Names at rank > stay_rank_cutoff (50) exit even if held yesterday."""
    n = 60
    ids = _make_ids(n)
    scores = {iid: float(n - i) for i, iid in enumerate(ids)}
    composite = pd.Series(scores)

    rank_55_id = ids[54]  # rank 55 — beyond stay cutoff
    rank_3_id = ids[2]  # rank 3 — should enter

    result = select(
        composite=composite,
        governance_excluded=set(),
        trend_gate_pass=set(ids),
        held_yesterday={rank_55_id},  # was held
        enter_rank_cutoff=30,
        stay_rank_cutoff=50,
    )

    assert rank_55_id in result.exited, (
        f"rank-55 held yesterday must exit; got exited={result.exited}"
    )
    assert rank_55_id not in result.held
    assert rank_55_id not in result.entered

    # rank-3 name should enter
    assert rank_3_id in result.entered


# ---------------------------------------------------------------------------
# Test 7 — governance exclusion forces exit regardless of rank
# ---------------------------------------------------------------------------


def test_select_governance_exclusions_force_exit() -> None:
    """Held name in governance_excluded exits regardless of how high its composite is."""
    n = 60
    ids = _make_ids(n)
    scores = {iid: float(n - i) for i, iid in enumerate(ids)}
    composite = pd.Series(scores)

    top_id = ids[0]  # rank 1 — best composite

    # Hold the best name yesterday but governance-exclude it today
    result = select(
        composite=composite,
        governance_excluded={top_id},
        trend_gate_pass=set(ids),
        held_yesterday={top_id},
        enter_rank_cutoff=30,
        stay_rank_cutoff=50,
    )

    assert top_id in result.exited, (
        f"Governance-excluded held name must exit; got exited={result.exited}"
    )
    assert top_id not in result.entered
    assert top_id not in result.held
    # top_id should not appear in rank 1 since composite → -inf
    # So next best (ids[1]) should enter
    assert ids[1] in result.entered


# ---------------------------------------------------------------------------
# Test 8 — trend gate blocks new entries
# ---------------------------------------------------------------------------


def test_select_trend_gate_blocks_new_entries() -> None:
    """Name at rank 5 not passing the trend gate is NOT entered; goes to bench_hold instead."""
    n = 60
    ids = _make_ids(n)
    scores = {iid: float(n - i) for i, iid in enumerate(ids)}
    composite = pd.Series(scores)

    rank_5_id = ids[4]  # rank 5 — would normally enter

    # trend_gate_pass excludes rank_5_id
    trend_passing = set(ids) - {rank_5_id}

    result = select(
        composite=composite,
        governance_excluded=set(),
        trend_gate_pass=trend_passing,
        held_yesterday=set(),
        enter_rank_cutoff=30,
        stay_rank_cutoff=50,
    )

    assert rank_5_id not in result.entered, (
        f"rank-5 blocked by trend gate must not enter; entered={result.entered}"
    )
    assert rank_5_id in result.bench_hold, (
        f"rank-5 blocked by trend gate should be bench_hold; bench_hold={result.bench_hold}"
    )
    # All other top-30 names (that pass trend gate) should enter
    top_30_passing = [iid for iid in ids[:30] if iid != rank_5_id]
    for iid in top_30_passing:
        assert iid in result.entered, f"{iid} should enter (rank <= 30, passes trend gate)"
