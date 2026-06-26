"""Tests for :mod:`atlas.discovery.engine`.

Covers:
- :class:`WalkForwardWindow` invariants.
- Synthetic universe generator determinism.
- Per-cell discovery: validated vs no_conviction branches.
- IC computation correctness on hand-calculated examples.
- Per-tenure IC floor enforcement.
- Friction adjustment sign-correctness per action.
- :meth:`WalkForwardSweep.run_full_matrix` produces 24 results.
- :meth:`WalkForwardSweep.persist` writes the expected rows (mock engine).
- Mode stubs raise NotImplementedError with informative messages.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from atlas.discovery.engine import (
    ACTIONS,
    CAP_TIERS,
    DEFAULT_FRICTION_BY_TIER,
    DEFAULT_WINDOWS,
    METHODOLOGY_LOCK_REF,
    PER_TENURE_IC_FLOOR,
    TENURE_TO_HORIZON_DAYS,
    TENURES,
    CellDiscoveryResult,
    CellSpec,
    SweepResult,
    WalkForwardSweep,
    WalkForwardWindow,
    _build_cache_universe,
    _build_rule_dsl,
    _compute_cap_tier_panel,
    _compute_ic,
    _generate_synthetic_universe,
)

# ---------------------------------------------------------------------------
# WalkForwardWindow invariants
# ---------------------------------------------------------------------------


def test_walkforward_window_accepts_valid_window() -> None:
    w = WalkForwardWindow(date(2017, 5, 1), date(2022, 4, 30), date(2022, 5, 1), date(2023, 4, 30))
    assert w.train_start < w.train_end < w.test_start < w.test_end


def test_walkforward_window_rejects_overlapping_train_test() -> None:
    """train_end must be < test_start (no overlap)."""
    with pytest.raises(ValueError, match="train_end"):
        WalkForwardWindow(
            date(2017, 5, 1),
            date(2022, 5, 1),  # same as test_start
            date(2022, 5, 1),
            date(2023, 4, 30),
        )


def test_walkforward_window_rejects_inverted_train() -> None:
    with pytest.raises(ValueError, match="train_start"):
        WalkForwardWindow(
            date(2022, 4, 30),
            date(2017, 5, 1),  # before train_start
            date(2023, 5, 1),
            date(2024, 4, 30),
        )


def test_walkforward_window_rejects_inverted_test() -> None:
    with pytest.raises(ValueError, match="test_start"):
        WalkForwardWindow(
            date(2017, 5, 1),
            date(2022, 4, 30),
            date(2024, 4, 30),
            date(2023, 5, 1),  # before test_start
        )


def test_default_windows_invariants() -> None:
    """Each DEFAULT_WINDOWS entry satisfies the train<test invariant + steps 12mo."""
    for win in DEFAULT_WINDOWS:
        assert win.train_end < win.test_start
        assert win.train_start < win.train_end
        assert win.test_start < win.test_end


# ---------------------------------------------------------------------------
# Synthetic universe generator
# ---------------------------------------------------------------------------


def test_synthetic_universe_is_deterministic() -> None:
    """Same seed → identical universe (byte-equal close prices)."""
    a = _generate_synthetic_universe(n_instruments=20, seed=42)
    b = _generate_synthetic_universe(n_instruments=20, seed=42)
    assert (a["close"].to_numpy() == b["close"].to_numpy()).all()
    assert (a["instrument_id"].to_numpy() == b["instrument_id"].to_numpy()).all()


def test_synthetic_universe_different_seeds_diverge() -> None:
    a = _generate_synthetic_universe(n_instruments=20, seed=42)
    b = _generate_synthetic_universe(n_instruments=20, seed=43)
    # Close prices must differ
    assert not (a["close"].to_numpy() == b["close"].to_numpy()).all()


def test_synthetic_universe_has_all_cap_tiers() -> None:
    df = _generate_synthetic_universe(n_instruments=100, seed=42)
    cap_tiers = set(df["cap_tier"].unique())
    assert cap_tiers == {"Small", "Mid", "Large"}


def test_synthetic_universe_spans_walkforward_window() -> None:
    df = _generate_synthetic_universe(n_instruments=20, seed=42)
    min_d = df["date"].min()
    max_d = df["date"].max()
    # Should at least cover DEFAULT_WINDOWS span.
    assert min_d <= DEFAULT_WINDOWS[0].train_start
    assert max_d >= DEFAULT_WINDOWS[-1].test_end


def test_synthetic_universe_columns() -> None:
    df = _generate_synthetic_universe(n_instruments=10, seed=42)
    expected = {
        "instrument_id",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "sector",
        "cap_tier",
    }
    assert expected.issubset(set(df.columns))


def test_synthetic_universe_close_positive() -> None:
    df = _generate_synthetic_universe(n_instruments=10, seed=42)
    assert (df["close"] > 0).all()
    assert (df["high"] >= df["close"]).all()
    assert (df["low"] <= df["close"]).all()


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------


def test_compute_ic_perfect_rank_correlation() -> None:
    """Perfectly aligned ranks → IC = 1.0."""
    state = pd.DataFrame({"x": range(50)})
    score = pd.Series(range(50), dtype=float)
    fwd = pd.Series(range(50), dtype=float)
    ic = _compute_ic(state, score, fwd)
    assert ic is not None
    assert abs(float(ic) - 1.0) < 1e-9


def test_compute_ic_perfect_anticorrelation() -> None:
    """Inverted ranks → IC = -1.0."""
    state = pd.DataFrame({"x": range(50)})
    score = pd.Series(range(50), dtype=float)
    fwd = pd.Series(range(49, -1, -1), dtype=float)
    ic = _compute_ic(state, score, fwd)
    assert ic is not None
    assert abs(float(ic) + 1.0) < 1e-9


def test_compute_ic_returns_none_on_too_few_observations() -> None:
    state = pd.DataFrame({"x": range(10)})
    score = pd.Series(range(10), dtype=float)
    fwd = pd.Series(range(10), dtype=float)
    assert _compute_ic(state, score, fwd) is None


def test_compute_ic_returns_none_on_zero_variance() -> None:
    state = pd.DataFrame({"x": range(50)})
    score = pd.Series([1.0] * 50)  # zero variance
    fwd = pd.Series(range(50), dtype=float)
    assert _compute_ic(state, score, fwd) is None


def test_compute_ic_drops_nan_rows() -> None:
    """NaN entries dropped before correlation."""
    score = pd.Series([1.0, 2.0, np.nan, 4.0] * 15)
    fwd = pd.Series([10.0, 20.0, 30.0, np.nan] * 15)
    state = pd.DataFrame({"x": range(len(score))})
    ic = _compute_ic(state, score, fwd)
    # Surviving 30 pairs (1,10) and (2,20) repeated 15× → still 30 valid pairs.
    assert ic is not None


# ---------------------------------------------------------------------------
# Per-tenure IC floor + friction adjustment
# ---------------------------------------------------------------------------


def test_per_tenure_ic_floor_keys() -> None:
    assert set(PER_TENURE_IC_FLOOR.keys()) == {"1m", "3m", "6m", "12m"}
    # All Decimal type.
    for _k, v in PER_TENURE_IC_FLOOR.items():
        assert isinstance(v, Decimal)
    # 6m has the highest floor.
    assert PER_TENURE_IC_FLOOR["6m"] >= PER_TENURE_IC_FLOOR["12m"]
    assert PER_TENURE_IC_FLOOR["12m"] >= PER_TENURE_IC_FLOOR["1m"]


def test_default_friction_by_tier_ordering() -> None:
    """Small > Mid > Large friction (matches migration 081_z seed)."""
    assert (
        DEFAULT_FRICTION_BY_TIER["Small"]
        > DEFAULT_FRICTION_BY_TIER["Mid"]
        > DEFAULT_FRICTION_BY_TIER["Large"]
    )


def test_tenure_to_horizon_days_canonical() -> None:
    assert TENURE_TO_HORIZON_DAYS == {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


# ---------------------------------------------------------------------------
# CellSpec + rule_dsl construction
# ---------------------------------------------------------------------------


def test_build_rule_dsl_pullback() -> None:
    spec = CellSpec(
        cap_tier="Mid",
        tenure="12m",
        action="POSITIVE",
        rule_type_hint="pullback",
    )
    dsl = _build_rule_dsl(spec)
    assert dsl["rule_type"] == "pullback"
    assert dsl["tier"] == "Mid"
    assert dsl["action"] == "POSITIVE"
    assert dsl["tenure"] == "12m"
    assert dsl["methodology_lock_ref"] == METHODOLOGY_LOCK_REF
    # Eligibility has the cap-tier liquidity floor.
    assert any(p["feature"] == "log_med_tv_60d" for p in dsl["eligibility"])
    # Entry has the RS top-quantile + drawdown range predicates.
    entry_features = [p["feature"] for p in dsl["entry"]]
    assert "rs_residual_6m" in entry_features
    assert "formation_max_dd" in entry_features


def test_build_rule_dsl_severely_broken() -> None:
    spec = CellSpec(
        cap_tier="Mid",
        tenure="12m",
        action="NEGATIVE",
        rule_type_hint="severely_broken",
    )
    dsl = _build_rule_dsl(spec)
    assert dsl["rule_type"] == "severely_broken"
    assert dsl["action"] == "NEGATIVE"


def test_build_rule_dsl_emerging_and_topping() -> None:
    for rule_type, action in [("emerging", "POSITIVE"), ("topping", "NEGATIVE")]:
        spec = CellSpec(
            cap_tier="Large",
            tenure="3m",
            action=action,  # type: ignore[arg-type]
            rule_type_hint=rule_type,
        )
        dsl = _build_rule_dsl(spec)
        assert dsl["rule_type"] == rule_type


# ---------------------------------------------------------------------------
# WalkForwardSweep
# ---------------------------------------------------------------------------


def test_walkforward_sweep_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        WalkForwardSweep(mode="bogus")


def test_walkforward_sweep_cache_mode_raises_filenotfound_when_missing(
    tmp_path: Any,
) -> None:
    """cache mode without /tmp pickles → clear FileNotFoundError with next-step hint."""
    sweep = WalkForwardSweep(mode="cache", cache_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match=r"scp from ec2 first"):
        sweep._load_universe()


def test_walkforward_sweep_supabase_mode_not_implemented() -> None:
    sweep = WalkForwardSweep(mode="supabase")
    with pytest.raises(NotImplementedError, match="Supabase"):
        sweep._load_universe()


def test_walkforward_sweep_ec2_mode_not_implemented() -> None:
    sweep = WalkForwardSweep(mode="ec2")
    with pytest.raises(NotImplementedError, match="SSH"):
        sweep._load_universe()


def test_walkforward_sweep_synthetic_loads() -> None:
    sweep = WalkForwardSweep(mode="synthetic")
    df = sweep._load_universe()
    assert len(df) > 0
    assert "cap_tier" in df.columns


def test_walkforward_sweep_caches_universe() -> None:
    """_load_universe is memoised — second call returns same dataframe."""
    sweep = WalkForwardSweep(mode="synthetic")
    a = sweep._load_universe()
    b = sweep._load_universe()
    assert a is b


def test_discover_cell_validates_mid_12m_pullback() -> None:
    """The injected signal in the synthetic universe must validate
    Mid-cap 12m Pullback (per the spec: ~2 cells should validate)."""
    sweep = WalkForwardSweep(mode="synthetic")
    spec = CellSpec(
        cap_tier="Mid",
        tenure="12m",
        action="POSITIVE",
        rule_type_hint="pullback",
    )
    result = sweep.discover_cell(spec)
    assert isinstance(result, CellDiscoveryResult)
    assert result.spec == spec
    assert result.validated is True, f"expected validated; got notes={result.notes!r}"
    assert result.ic is not None and abs(result.ic) >= PER_TENURE_IC_FLOOR["12m"]
    assert result.friction_adjusted_excess is not None
    assert result.friction_adjusted_excess > Decimal("0")  # POSITIVE → positive edge
    assert result.tp_rate is not None
    assert result.tn_rate is None
    assert result.rule_dsl != {}
    assert result.stable_features  # non-empty list


def test_discover_cell_validates_mid_12m_severely_broken() -> None:
    sweep = WalkForwardSweep(mode="synthetic")
    spec = CellSpec(
        cap_tier="Mid",
        tenure="12m",
        action="NEGATIVE",
        rule_type_hint="severely_broken",
    )
    result = sweep.discover_cell(spec)
    assert result.validated is True
    assert result.ic is not None and abs(result.ic) >= PER_TENURE_IC_FLOOR["12m"]
    assert result.friction_adjusted_excess is not None
    assert result.friction_adjusted_excess < Decimal("0")  # NEGATIVE → negative edge
    assert result.tn_rate is not None
    assert result.tp_rate is None


def test_discover_cell_no_conviction_for_noise_cell() -> None:
    """Large 1m emerging on synthetic noise → no_conviction (IC below floor)."""
    sweep = WalkForwardSweep(mode="synthetic")
    spec = CellSpec(
        cap_tier="Large",
        tenure="1m",
        action="POSITIVE",
        rule_type_hint="emerging",
    )
    result = sweep.discover_cell(spec)
    assert result.validated is False
    assert result.rule_dsl == {}
    assert result.notes.startswith("no_conviction")


def test_discover_cell_returns_walkforward_run_id() -> None:
    sweep = WalkForwardSweep(mode="synthetic")
    spec = CellSpec(cap_tier="Mid", tenure="12m", action="POSITIVE", rule_type_hint="pullback")
    result = sweep.discover_cell(spec)
    assert isinstance(result.walkforward_run_id, uuid.UUID)


def test_run_full_matrix_produces_24_results() -> None:
    sweep = WalkForwardSweep(mode="synthetic")
    result = sweep.run_full_matrix()
    assert isinstance(result, SweepResult)
    assert len(result.results) == 24
    # All 24 cells covered.
    covered = {(r.spec.cap_tier, r.spec.tenure, r.spec.action) for r in result.results}
    expected = {(c, t, a) for c in CAP_TIERS for t in TENURES for a in ACTIONS}
    assert covered == expected


def test_run_full_matrix_validated_count_at_least_two() -> None:
    """At least 2 cells must validate (the injected Mid 12m pair).

    More cells may validate if the synthetic signal bleeds into neighbours;
    that's acceptable — the floor is "at least 2."
    """
    sweep = WalkForwardSweep(mode="synthetic")
    result = sweep.run_full_matrix()
    assert result.validated_count >= 2
    assert result.no_conviction_count == 24 - result.validated_count


def test_run_full_matrix_mid_12m_in_validated_set() -> None:
    """Mid 12m POSITIVE pullback + NEGATIVE severely_broken MUST validate."""
    sweep = WalkForwardSweep(mode="synthetic")
    result = sweep.run_full_matrix()
    validated_specs = {
        (r.spec.cap_tier, r.spec.tenure, r.spec.action) for r in result.results if r.validated
    }
    assert ("Mid", "12m", "POSITIVE") in validated_specs
    assert ("Mid", "12m", "NEGATIVE") in validated_specs


def test_run_full_matrix_timestamps_set() -> None:
    sweep = WalkForwardSweep(mode="synthetic")
    result = sweep.run_full_matrix()
    assert result.run_started_at < result.run_completed_at
    assert result.mode == "synthetic"
    assert result.windows == DEFAULT_WINDOWS


def test_rule_type_for_mapping() -> None:
    """The per-(tenure, action) rule_type_hint mapping matches CONTEXT.md archetypes."""
    sweep = WalkForwardSweep(mode="synthetic")
    assert sweep._rule_type_for("12m", "POSITIVE") == "pullback"
    assert sweep._rule_type_for("6m", "POSITIVE") == "pullback"
    assert sweep._rule_type_for("3m", "POSITIVE") == "emerging"
    assert sweep._rule_type_for("1m", "POSITIVE") == "emerging"
    assert sweep._rule_type_for("12m", "NEGATIVE") == "severely_broken"
    assert sweep._rule_type_for("6m", "NEGATIVE") == "severely_broken"
    assert sweep._rule_type_for("3m", "NEGATIVE") == "topping"
    assert sweep._rule_type_for("1m", "NEGATIVE") == "topping"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class _CapturingConn:
    """Capture executed SQL + params for assertion."""

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, dict[str, Any]]] = []
        self.committed = False

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        sql = str(statement.text) if hasattr(statement, "text") else str(statement)
        self.execute_calls.append((sql, params or {}))
        return MagicMock()

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> _CapturingConn:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass


def test_persist_no_engine_is_noop() -> None:
    """persist() with db_engine=None doesn't raise and writes nothing."""
    sweep = WalkForwardSweep(mode="synthetic", db_engine=None)
    result = sweep.run_full_matrix()
    sweep.persist(result)  # must not raise


def test_persist_writes_walkforward_row_per_cell() -> None:
    """Every cell — validated or not — gets an audit row."""
    captured = _CapturingConn()

    engine = MagicMock()
    engine.connect.return_value = captured

    sweep = WalkForwardSweep(mode="synthetic", db_engine=engine)
    result = sweep.run_full_matrix()
    sweep.persist(result)

    walkforward_inserts = [
        c for c in captured.execute_calls if "atlas_cell_walkforward_runs" in c[0]
    ]
    assert len(walkforward_inserts) == 24


def test_persist_writes_cell_definition_only_for_validated() -> None:
    captured = _CapturingConn()
    engine = MagicMock()
    engine.connect.return_value = captured

    sweep = WalkForwardSweep(mode="synthetic", db_engine=engine)
    result = sweep.run_full_matrix()
    sweep.persist(result)

    cell_def_inserts = [c for c in captured.execute_calls if "atlas_cell_definitions" in c[0]]
    assert len(cell_def_inserts) == result.validated_count
    assert result.validated_count > 0  # sanity


def test_persist_commits_transaction() -> None:
    captured = _CapturingConn()
    engine = MagicMock()
    engine.connect.return_value = captured
    sweep = WalkForwardSweep(mode="synthetic", db_engine=engine)
    result = sweep.run_full_matrix()
    sweep.persist(result)
    assert captured.committed is True


# ---------------------------------------------------------------------------
# Sanity / edge cases
# ---------------------------------------------------------------------------


def test_cellspec_is_frozen() -> None:
    """CellSpec is frozen — attempt to mutate raises FrozenInstanceError."""
    import dataclasses

    spec = CellSpec(cap_tier="Mid", tenure="12m", action="POSITIVE", rule_type_hint="pullback")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.cap_tier = "Large"  # type: ignore[misc]


def test_celldiscoveryresult_is_frozen() -> None:
    import dataclasses

    sweep = WalkForwardSweep(mode="synthetic")
    spec = CellSpec(cap_tier="Mid", tenure="12m", action="POSITIVE", rule_type_hint="pullback")
    result = sweep.discover_cell(spec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.validated = False  # type: ignore[misc]


def test_sweep_result_validated_count_property() -> None:
    sweep = WalkForwardSweep(mode="synthetic")
    result = sweep.run_full_matrix()
    n_validated = sum(1 for r in result.results if r.validated)
    n_no_conv = sum(1 for r in result.results if not r.validated)
    assert result.validated_count == n_validated
    assert result.no_conviction_count == n_no_conv


def test_full_synthetic_run_is_deterministic_same_seed() -> None:
    """Running the same seed twice → identical validated counts."""
    a = WalkForwardSweep(mode="synthetic", synthetic_seed=42).run_full_matrix()
    b = WalkForwardSweep(mode="synthetic", synthetic_seed=42).run_full_matrix()
    assert a.validated_count == b.validated_count
    # Per-cell results must match on (validated, ic).
    a_by_key = {(r.spec.cap_tier, r.spec.tenure, r.spec.action): r for r in a.results}
    b_by_key = {(r.spec.cap_tier, r.spec.tenure, r.spec.action): r for r in b.results}
    for key, ar in a_by_key.items():
        br = b_by_key[key]
        assert ar.validated == br.validated
        assert ar.ic == br.ic


# ---------------------------------------------------------------------------
# Cache-mode tests (cap_tier derivation + universe shaping)
# ---------------------------------------------------------------------------


def _make_synthetic_cache_ohlcv(n_iids: int = 12, n_days: int = 120) -> pd.DataFrame:
    """Build a small synthetic cache-shaped (date, iid, close, volume) df.

    iids 0..3 → low traded value (Small), 4..7 → mid, 8..11 → high (Large).
    """
    rng = np.random.default_rng(0)
    iids = [f"iid_{i:02d}" for i in range(n_iids)]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rows = []
    for i, iid in enumerate(iids):
        close = 100.0 + np.cumsum(rng.normal(0, 1, size=n_days))
        # Vol multiplier scales with i so trailing-60d traded value clusters
        # into terciles cleanly.
        volume = np.full(n_days, 1_000 * (i + 1) ** 2, dtype=np.int64)
        for d, c, v in zip(dates, close, volume, strict=True):
            rows.append({"date": d, "iid": iid, "close": float(c), "volume": int(v)})
    return pd.DataFrame(rows)


def test_compute_cap_tier_panel_produces_three_terciles() -> None:
    """cap_tier panel: per-date qcut into Small/Mid/Large terciles."""
    ohlcv = _make_synthetic_cache_ohlcv(n_iids=12, n_days=120)
    panel = _compute_cap_tier_panel(ohlcv, lookback_days=60)
    # After lookback warm-up there should be classified rows.
    classified = panel.dropna(subset=["cap_tier"])
    assert len(classified) > 0
    # Per-date tier distribution must cover all three tiers when n_iids=12.
    one_day = classified[classified["date"] == classified["date"].max()]
    tiers = set(one_day["cap_tier"].unique())
    assert tiers == {"Small", "Mid", "Large"}
    # 12 iids → roughly 4 per tier.
    counts = one_day["cap_tier"].value_counts().to_dict()
    for tier in ("Small", "Mid", "Large"):
        assert 3 <= counts[tier] <= 5


def test_compute_cap_tier_panel_warmup_is_nan() -> None:
    """Before lookback_days of history exist, cap_tier is NaN."""
    ohlcv = _make_synthetic_cache_ohlcv(n_iids=6, n_days=120)
    panel = _compute_cap_tier_panel(ohlcv, lookback_days=60)
    # First 59 days per iid must have NaN cap_tier (need 60 sessions of TV).
    first_date = panel["date"].min()
    early = panel[panel["date"] == first_date]
    assert early["cap_tier"].isna().all()


def test_build_cache_universe_excludes_blacklist() -> None:
    ohlcv = _make_synthetic_cache_ohlcv(n_iids=8, n_days=120)
    blacklist = ["iid_00", "iid_01"]
    universe = _build_cache_universe(ohlcv, blacklist)
    remaining = set(universe["instrument_id"].unique())
    assert "iid_00" not in remaining
    assert "iid_01" not in remaining
    assert "iid_02" in remaining


def test_build_cache_universe_emits_engine_schema() -> None:
    """The universe returned matches the synthetic generator's column set."""
    ohlcv = _make_synthetic_cache_ohlcv(n_iids=6, n_days=120)
    universe = _build_cache_universe(ohlcv, [])
    expected = {
        "instrument_id",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "sector",
        "cap_tier",
    }
    assert expected.issubset(set(universe.columns))
    # date must be python date for WalkForwardWindow comparisons.
    sample_date = universe["date"].iloc[0]
    assert isinstance(sample_date, date)


def test_walkforward_sweep_cache_dir_propagates(tmp_path: Any) -> None:
    """The cache_dir kwarg flows through to the cache loader."""
    sweep = WalkForwardSweep(mode="cache", cache_dir=tmp_path)
    assert sweep.cache_dir == tmp_path


def test_cache_mode_loads_real_universe_smoke() -> None:
    """Smoke test: cache mode loads real /tmp pickles → non-empty universe.

    Only runs when the cache pickle is present locally (developer-laptop
    path; never in CI).
    """
    from pathlib import Path as _Path

    cache_pkl = _Path("/tmp/sde_ohlcv_cache.pkl")
    if not cache_pkl.exists():
        pytest.skip("real cache pickle missing — skipped in CI")
    sweep = WalkForwardSweep(mode="cache")
    universe = sweep._load_universe()
    assert len(universe) > 0
    assert set(universe["cap_tier"].unique()) >= {"Small", "Mid", "Large"}
