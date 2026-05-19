"""HRP portfolio construction tests — spec §6.5.

Test order mirrors the TDD cycle: tests written first, implementation second.
All tests are pure-math (no DB), using hand-constructed returns panels so
expected values can be verified by inspection.
"""

from __future__ import annotations

import uuid

import numpy as np
import pandas as pd

from atlas.trading.v6.portfolio import HrpAllocator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_returns(n_instruments: int, n_days: int = 252, seed: int = 0) -> pd.DataFrame:
    """Synthetic daily returns panel — columns are UUID instrument IDs."""
    rng = np.random.default_rng(seed)
    ids = [uuid.uuid4() for _ in range(n_instruments)]
    data = rng.standard_normal((n_days, n_instruments)) * 0.015  # ~1.5% daily vol
    return pd.DataFrame(data, columns=ids)


def _all_same_sector(ids: list[uuid.UUID], sector: str = "IT") -> dict[uuid.UUID, str]:
    return {i: sector for i in ids}


def _all_same_group(ids: list[uuid.UUID], group: str = "GroupA") -> dict[uuid.UUID, str]:
    return {i: group for i in ids}


# ---------------------------------------------------------------------------
# Test 1: weights sum to 1.0
# ---------------------------------------------------------------------------


def test_weights_sum_to_one_five_names() -> None:
    """Output weights must sum to 1.0 ± 1e-6 on a 5-name cohort."""
    panel = _make_returns(5, seed=42)
    ids = list(panel.columns)
    allocator = HrpAllocator()
    result = allocator.allocate(
        returns_panel=panel,
        sector_map={i: f"S{k % 3}" for k, i in enumerate(ids)},
        issuer_group_map={i: f"G{k}" for k, i in enumerate(ids)},
    )
    assert (
        abs(result.weights.sum() - 1.0) < 1e-6
    ), f"Weights sum to {result.weights.sum():.8f}, expected 1.0"


def test_weights_sum_to_one_thirty_names() -> None:
    """Weights must sum to 1.0 ± 1e-6 on a 30-name cohort (realistic size)."""
    panel = _make_returns(30, seed=7)
    ids = list(panel.columns)
    allocator = HrpAllocator()
    result = allocator.allocate(
        returns_panel=panel,
        sector_map={i: f"S{k % 5}" for k, i in enumerate(ids)},
        issuer_group_map={i: f"G{k % 10}" for k, i in enumerate(ids)},
    )
    assert abs(result.weights.sum() - 1.0) < 1e-6


def test_weights_all_non_negative() -> None:
    """All weights must be non-negative after cap/floor processing."""
    panel = _make_returns(10, seed=99)
    ids = list(panel.columns)
    result = HrpAllocator().allocate(
        returns_panel=panel,
        sector_map={i: "IT" for i in ids},
        issuer_group_map={i: f"G{k}" for k, i in enumerate(ids)},
    )
    assert (result.weights >= 0).all(), "Negative weight found"


def test_weights_index_matches_columns() -> None:
    """Result weights are indexed by the same instrument_ids as panel columns."""
    panel = _make_returns(5, seed=1)
    ids = set(panel.columns)
    result = HrpAllocator().allocate(
        returns_panel=panel,
        sector_map={i: "Fin" for i in ids},
        issuer_group_map={i: "G1" for i in ids},
    )
    # Dropped instruments may not be present, but all present weights must be in ids
    assert set(result.weights.index).issubset(ids)


# ---------------------------------------------------------------------------
# Test 2: single-name cap binds
# ---------------------------------------------------------------------------


def test_single_name_cap_binds_and_redistributes() -> None:
    """When one name's HRP weight would exceed the cap, it is capped.

    We use a 20-name cohort where one instrument has very low vol (dominant
    inverse-variance weight). Cap at 15% — feasible since 20 × 0.15 = 3.0 ≥ 1.0.
    After convergence: max weight ≤ 0.15 and 'name' in caps_binding.
    Excess redistributes within cluster so weights still sum to 1.0.
    """
    rng = np.random.default_rng(123)
    n_days, n_inst = 252, 20
    ids = [uuid.uuid4() for _ in range(n_inst)]

    # Instrument 0: very low vol → dominant inverse-variance weight before cap
    data = rng.standard_normal((n_days, n_inst)) * 0.02
    data[:, 0] = rng.standard_normal(n_days) * 0.001  # very low vol → high HRP weight

    panel = pd.DataFrame(data, columns=ids)

    # 15% cap is feasible (20 × 0.15 = 3.0 > 1.0), so cap can be enforced
    allocator = HrpAllocator(
        single_name_cap=0.15, sector_cap=0.50, issuer_group_cap=0.50, weight_floor=0.0
    )
    result = allocator.allocate(
        returns_panel=panel,
        sector_map={i: "IT" for i in ids},
        issuer_group_map={i: f"G{k}" for k, i in enumerate(ids)},
    )

    # All present weights must respect cap
    assert (
        result.weights.max() <= 0.15 + 1e-9
    ), f"Max weight {result.weights.max():.4f} exceeds single-name cap"
    assert abs(result.weights.sum() - 1.0) < 1e-6
    # Cap must have bound (name cap was triggered)
    assert (
        "name" in result.caps_binding
    ), f"Expected 'name' in caps_binding, got {result.caps_binding}"


def test_single_name_cap_no_binding_when_all_equal() -> None:
    """When all names have equal uncorrelated returns no cap should bind."""
    rng = np.random.default_rng(55)
    n_inst = 5
    ids = [uuid.uuid4() for _ in range(n_inst)]
    # All instruments: same vol (0.02), uncorrelated
    data = rng.standard_normal((252, n_inst)) * 0.02
    panel = pd.DataFrame(data, columns=ids)
    # With 5 equal-weight uncorrelated instruments, HRP weight ≈ 0.20 each
    # which is well above 5% single-name cap → cap WILL bind
    allocator = HrpAllocator(single_name_cap=0.25)  # use 25% cap so it doesn't bind
    result = allocator.allocate(
        returns_panel=panel,
        sector_map={i: "IT" for i in ids},
        issuer_group_map={i: f"G{k}" for k, i in enumerate(ids)},
    )
    assert "name" not in result.caps_binding


# ---------------------------------------------------------------------------
# Test 3: sector cap binds
# ---------------------------------------------------------------------------


def test_sector_cap_binds_at_25pct() -> None:
    """Sector cap at 25% applies when a sector's aggregate weight exceeds it.

    We put 5 highly correlated names in 'Banking' and 5 uncorrelated names
    in 4 other sectors. Banking will receive significant HRP weight (well above
    25%) due to correlation clustering. After sector cap: Banking ≤ 25%.

    With 10 instruments total and sector_cap=0.25, the cap is feasible
    (Banking at 25% + others at 75% = 100%).
    """
    rng = np.random.default_rng(7)
    # 5 Banking names (correlated) + 5 other-sector names
    banking_ids = [uuid.uuid4() for _ in range(5)]
    other_ids = [uuid.uuid4() for _ in range(5)]
    all_ids = banking_ids + other_ids

    factor = rng.standard_normal(252) * 0.015
    banking_data = np.column_stack([factor + rng.standard_normal(252) * 0.002 for _ in range(5)])
    other_data = rng.standard_normal((252, 5)) * 0.015

    data = np.hstack([banking_data, other_data])
    panel = pd.DataFrame(data, columns=all_ids)

    sector_map = {i: "Banking" for i in banking_ids}
    sector_map.update({other_ids[k]: f"Sector{k}" for k in range(5)})
    issuer_group_map = {i: f"G{k}" for k, i in enumerate(all_ids)}

    # single_name_cap large enough not to interfere (0.40), sector_cap=0.25
    allocator = HrpAllocator(
        sector_cap=0.25, single_name_cap=0.40, issuer_group_cap=0.50, weight_floor=0.0
    )
    result = allocator.allocate(
        returns_panel=panel,
        sector_map=sector_map,
        issuer_group_map=issuer_group_map,
    )

    present_ids = set(result.weights.index)
    banking_weight = sum(result.weights[i] for i in banking_ids if i in present_ids)
    assert (
        banking_weight <= 0.25 + 1e-6
    ), f"Banking sector weight {banking_weight:.6f} exceeds 25% cap"
    assert abs(result.weights.sum() - 1.0) < 1e-6
    assert (
        "sector" in result.caps_binding
    ), f"Expected 'sector' in caps_binding, got {result.caps_binding}"


def test_sector_cap_does_not_bind_when_diversified() -> None:
    """When instruments are in separate sectors with a generous cap, sector cap should not bind.

    We use a 50% sector cap (generous) and ensure each instrument is in its own
    sector. With 5 instruments, the max single-sector weight is < 50% by design.
    """
    rng = np.random.default_rng(22)
    n_inst = 5
    ids = [uuid.uuid4() for _ in range(n_inst)]
    data = rng.standard_normal((252, n_inst)) * 0.015
    panel = pd.DataFrame(data, columns=ids)
    # Each instrument in its own sector
    sector_map = {i: f"Sector{k}" for k, i in enumerate(ids)}
    issuer_group_map = {i: f"G{k}" for k, i in enumerate(ids)}
    # Use generous caps: single_name_cap=0.50 so it doesn't interfere,
    # sector_cap=0.50 so 5 instruments (max ~25-35%) won't hit it.
    allocator = HrpAllocator(single_name_cap=0.50, sector_cap=0.50, issuer_group_cap=0.50)
    result = allocator.allocate(
        returns_panel=panel,
        sector_map=sector_map,
        issuer_group_map=issuer_group_map,
    )
    # With 5 distinct sectors and 50% cap, no sector should be capped
    assert "sector" not in result.caps_binding


# ---------------------------------------------------------------------------
# Test 4: issuer-group cap binds (Adani group scenario)
# ---------------------------------------------------------------------------


def test_issuer_group_cap_binds_adani_scenario() -> None:
    """Multiple names in same issuer group (e.g. Adani) get capped at 25%.

    Cohort: 3 Adani names + 2 independent names (5 total, 3 groups).
    Cap = 0.25 is feasible: 3 groups × 0.25 = 0.75 < 1.0, so the remaining
    0.25 flows to uncapped single-name groups.

    Adani names are highly correlated (near-zero idiosyncratic vol) so HRP
    gives the Adani cluster ~50-70% before capping. After cap: Adani ≤ 0.25.

    Post-cap: sum=1.0, Adani total ≤ 0.25, 'group' in caps_binding.
    """
    rng = np.random.default_rng(42)
    adani_ids = [uuid.uuid4() for _ in range(3)]
    # 10 single-name groups → 11 groups total.
    # issuer_group_cap=0.20 is feasible: 11 × 0.20 = 2.2 > 1.0
    other_ids = [uuid.uuid4() for _ in range(10)]
    all_ids = adani_ids + other_ids

    # Adani: highly correlated, very low idiosyncratic vol → dominant HRP weight
    adani_factor = rng.standard_normal(252) * 0.015
    adani_data = np.column_stack(
        [adani_factor + rng.standard_normal(252) * 0.0005 for _ in range(3)]
    )
    # Others: independent, higher vol → lower inverse-var weight
    other_data = rng.standard_normal((252, 10)) * 0.025

    data = np.hstack([adani_data, other_data])
    panel = pd.DataFrame(data, columns=all_ids)

    # 11 groups: Adani (3 names) + 10 single-name groups
    issuer_group_map: dict[uuid.UUID, str] = {i: "Adani" for i in adani_ids}
    issuer_group_map.update({other_ids[k]: f"Co{k}" for k in range(10)})
    sector_map: dict[uuid.UUID, str] = {i: f"S{k % 3}" for k, i in enumerate(all_ids)}

    # issuer_group_cap=0.20 is feasible: 11 groups × 0.20 = 2.2 > 1.0
    # Adani naturally gets ~50-60% (3 low-vol correlated names) so cap definitely binds.
    allocator = HrpAllocator(
        issuer_group_cap=0.20,
        single_name_cap=0.50,
        sector_cap=0.80,
        weight_floor=0.0,
    )
    result = allocator.allocate(
        returns_panel=panel,
        sector_map=sector_map,
        issuer_group_map=issuer_group_map,
    )

    present_ids = set(result.weights.index)
    adani_weight = sum(result.weights[i] for i in adani_ids if i in present_ids)
    assert (
        adani_weight <= 0.20 + 1e-6
    ), f"Adani group weight {adani_weight:.6f} exceeds 20% issuer-group cap"
    assert abs(result.weights.sum() - 1.0) < 1e-6
    assert (
        "group" in result.caps_binding
    ), f"Expected 'group' in caps_binding, got {result.caps_binding}"


# ---------------------------------------------------------------------------
# Test 5: below-floor names dropped
# ---------------------------------------------------------------------------


def test_below_floor_dropped_and_renormalized() -> None:
    """Names with weight < 0.5% after caps are dropped.

    We force the scenario by using a large cohort (15 names) with a very
    tight single-name cap (5%) which pushes many names to small weights.
    After floor=0.5% drop, remaining weights re-normalize to 1.0.
    """
    rng = np.random.default_rng(31415)
    n_inst = 15
    ids = [uuid.uuid4() for _ in range(n_inst)]
    data = rng.standard_normal((252, n_inst)) * 0.015
    panel = pd.DataFrame(data, columns=ids)
    sector_map = {i: f"S{k % 5}" for k, i in enumerate(ids)}
    issuer_group_map = {i: f"G{k}" for k, i in enumerate(ids)}

    # With 15 instruments and 5% single-name cap, several will be near/below floor
    allocator = HrpAllocator(
        single_name_cap=0.05,
        sector_cap=0.25,
        issuer_group_cap=0.05,
        weight_floor=0.005,
    )
    result = allocator.allocate(
        returns_panel=panel,
        sector_map=sector_map,
        issuer_group_map=issuer_group_map,
    )

    # All surviving weights must be at or above floor
    assert (
        result.weights >= 0.005 - 1e-9
    ).all(), f"Weight below floor: {result.weights[result.weights < 0.005]}"
    # Weights still sum to 1.0
    assert abs(result.weights.sum() - 1.0) < 1e-6
    # dropped_below_floor is a list of UUIDs (may be empty if none dropped)
    assert isinstance(result.dropped_below_floor, list)
    if result.dropped_below_floor:
        # Every dropped UUID was in the original cohort
        assert all(u in set(ids) for u in result.dropped_below_floor)


def test_below_floor_dropped_ids_are_in_result() -> None:
    """dropped_below_floor UUIDs are actually absent from the final weights."""
    rng = np.random.default_rng(2718)
    n_inst = 20
    ids = [uuid.uuid4() for _ in range(n_inst)]
    data = rng.standard_normal((252, n_inst)) * 0.015
    panel = pd.DataFrame(data, columns=ids)
    sector_map = {i: "IT" for i in ids}
    issuer_group_map = {i: f"G{k}" for k, i in enumerate(ids)}

    allocator = HrpAllocator(
        single_name_cap=0.05,
        sector_cap=0.25,
        issuer_group_cap=0.10,
        weight_floor=0.005,
    )
    result = allocator.allocate(
        returns_panel=panel,
        sector_map=sector_map,
        issuer_group_map=issuer_group_map,
    )

    for dropped_id in result.dropped_below_floor:
        assert (
            dropped_id not in result.weights.index
        ), f"Dropped instrument {dropped_id} still appears in weights"


# ---------------------------------------------------------------------------
# Test 6: cluster assignment populated
# ---------------------------------------------------------------------------


def test_cluster_assignment_populated() -> None:
    """cluster_assignment maps each surviving instrument to 'C1', 'C2', etc."""
    panel = _make_returns(8, seed=5)
    ids = list(panel.columns)
    result = HrpAllocator().allocate(
        returns_panel=panel,
        sector_map={i: "IT" for i in ids},
        issuer_group_map={i: f"G{k}" for k, i in enumerate(ids)},
    )
    assert isinstance(result.cluster_assignment, dict)
    # All surviving instruments must have a cluster label
    for iid in result.weights.index:
        assert iid in result.cluster_assignment, f"{iid} not in cluster_assignment"
    # Cluster labels must be of the form 'C<int>'
    for label in result.cluster_assignment.values():
        assert label.startswith("C") and label[1:].isdigit(), f"Bad cluster label: {label}"


# ---------------------------------------------------------------------------
# Test 7: single instrument edge case
# ---------------------------------------------------------------------------


def test_single_instrument_gets_full_weight() -> None:
    """A cohort of one instrument must receive weight 1.0."""
    iid = uuid.uuid4()
    rng = np.random.default_rng(0)
    panel = pd.DataFrame(
        rng.standard_normal((252, 1)) * 0.015,
        columns=[iid],
    )
    result = HrpAllocator().allocate(
        returns_panel=panel,
        sector_map={iid: "IT"},
        issuer_group_map={iid: "TataGroup"},
    )
    assert abs(result.weights[iid] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 8: two-instrument symmetry
# ---------------------------------------------------------------------------


def test_two_instruments_equal_vol_near_equal_weights() -> None:
    """Two instruments with identical vol and no cap interference get ≈ 50/50.

    HRP for 2 instruments with equal realized variance: cluster_variance is the
    same for each singleton cluster → alpha = 0.5 exactly → 50/50 split.
    We use generous caps (50%) so they don't interfere with the pure HRP output.
    """
    rng = np.random.default_rng(3)
    ids = [uuid.uuid4(), uuid.uuid4()]
    data = np.column_stack(
        [
            rng.standard_normal(252) * 0.015,
            rng.standard_normal(252) * 0.015,
        ]
    )
    panel = pd.DataFrame(data, columns=ids)
    # Use generous caps so they don't interfere with the 50/50 HRP result
    result = HrpAllocator(
        single_name_cap=0.90,
        sector_cap=0.90,
        issuer_group_cap=0.90,
        weight_floor=0.0,
    ).allocate(
        returns_panel=panel,
        sector_map={i: f"S{k}" for k, i in enumerate(ids)},
        issuer_group_map={i: f"G{k}" for k, i in enumerate(ids)},
    )
    w0 = result.weights.get(ids[0], 0.0)
    w1 = result.weights.get(ids[1], 0.0)
    # HRP for 2 equal-vol instruments: weights should be ~50/50
    # Allow tolerance of 20% given sample variance in realized vol
    assert abs(w0 - 0.5) < 0.20, f"Expected ~0.5, got {w0:.4f}"
    assert abs(w1 - 0.5) < 0.20, f"Expected ~0.5, got {w1:.4f}"
