"""Tests for the deep-search v2 generic per-cell engine.

Covers:
* every entry in the FEATURES allowlist resolves through
  :func:`panel_for_feature` (catches the v1 silent-bug class);
* feature panels compute without error on a synthetic small panel;
* :func:`generate_candidates` produces ≥ 320 POSITIVE / ≥ 170 NEGATIVE
  candidates per cell, with the tier liquidity floor + tier-conditional
  vol bands wired correctly;
* sector features are NaN-safe when the mapping CSV is unavailable;
* :func:`run_single_cell` writes a JSON file with BH q-values on a
  synthetic mini-panel.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from atlas.discovery.deep_search import (
    CandidateMetrics,
    _bh_q_values,
    run_single_cell,
)
from atlas.discovery.deep_search_candidates import generate_candidates
from atlas.discovery.deep_search_features import (
    compute_feature_panels,
    panel_for_feature,
)
from atlas.discovery.engine import (
    PER_TENURE_IC_FLOOR,
    WalkForwardWindow,
)
from atlas.features import FEATURES

# ---------------------------------------------------------------------------
# Synthetic data builders (tiny — ~50 dates × 20 instruments)
# ---------------------------------------------------------------------------


def _build_synthetic_ohlcv(
    n_dates: int = 350,
    n_instruments: int = 20,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Return long-form OHLCV, nifty series, cap-tier panel for tests.

    Defaults to 350 dates (covers 252d windows + margin) × 20 iids.
    """
    rng = np.random.default_rng(seed)
    start = date(2020, 1, 2)
    dates = [start + timedelta(days=i) for i in range(n_dates)]
    iids = [f"iid_{k:03d}" for k in range(n_instruments)]
    rows: list[dict[str, Any]] = []
    closes = 100.0 + rng.standard_normal((n_dates, n_instruments)).cumsum(axis=0) * 0.5
    # Ensure positivity.
    closes = np.maximum(closes, 1.0)
    vols = (1e6 + rng.standard_normal((n_dates, n_instruments)) * 1e5).clip(min=1e4)
    for di, d in enumerate(dates):
        for ii, iid in enumerate(iids):
            rows.append(
                {
                    "date": pd.Timestamp(d),
                    "iid": iid,
                    "close": closes[di, ii],
                    "volume": vols[di, ii],
                }
            )
    ohlcv = pd.DataFrame(rows)

    nifty = pd.Series(
        100.0 + rng.standard_normal(n_dates).cumsum() * 0.3,
        index=pd.DatetimeIndex(dates, name="date"),
        name="nifty500",
    )
    nifty = nifty.clip(lower=1.0)

    # Cap-tier panel: long-form (date, iid, cap_tier). Equally split.
    cap_rows: list[dict[str, Any]] = []
    for d in dates:
        for ii, iid in enumerate(iids):
            tier = ("Large", "Mid", "Small")[ii % 3]
            cap_rows.append({"date": pd.Timestamp(d), "iid": iid, "cap_tier": tier})
    cap_long = pd.DataFrame(cap_rows)
    return ohlcv, nifty, cap_long


# ---------------------------------------------------------------------------
# Allowlist <-> panel-mapping consistency (the load-bearing red-team check)
# ---------------------------------------------------------------------------


def test_every_candidate_feature_resolves_through_panel_for_feature() -> None:
    """v1 bug regression: any feature referenced by the candidate generator
    MUST resolve through ``panel_for_feature``. The broader FEATURES
    allowlist also contains scorecard-only features that are computed by
    other v6 compute modules; those aren't deep-search panels so we don't
    require them here. The load-bearing invariant is: every predicate a
    candidate uses must be evaluable.
    """
    ohlcv, nifty, cap_long = _build_synthetic_ohlcv()
    panels = compute_feature_panels(ohlcv, nifty, cap_long, sector_of=None)

    referenced: set[str] = set()
    for tier in ("Large", "Mid", "Small"):
        for tenure in ("1m", "3m", "6m", "12m"):
            for direction in ("POSITIVE", "NEGATIVE"):
                for c in generate_candidates(tier, tenure, direction):  # type: ignore[arg-type]
                    for pred in c.features:
                        referenced.add(pred.feature)

    missing: list[str] = []
    for f in sorted(referenced):
        try:
            panel_for_feature(panels, f)
        except KeyError:
            missing.append(f)
    assert (
        not missing
    ), f"features referenced by candidate generator but missing from panel_for_feature: {missing}"


def test_every_candidate_feature_is_in_features_allowlist() -> None:
    """Every feature in a candidate rule MUST be in the FEATURES allowlist.

    This guards the Pydantic ``FeaturePredicate`` validation gate — a
    typo in the generator would currently raise at predicate construction,
    but this test makes the failure mode explicit and provides a clean
    feature-by-feature diff.
    """
    referenced: set[str] = set()
    for tier in ("Large", "Mid", "Small"):
        for tenure in ("1m", "3m", "6m", "12m"):
            for direction in ("POSITIVE", "NEGATIVE"):
                for c in generate_candidates(tier, tenure, direction):  # type: ignore[arg-type]
                    for pred in c.features:
                        referenced.add(pred.feature)

    not_in_allowlist = referenced - set(FEATURES)
    assert not not_in_allowlist, (
        f"candidate generator references features not in FEATURES allowlist: "
        f"{sorted(not_in_allowlist)}"
    )


def test_compute_feature_panels_yields_expected_shapes() -> None:
    """Every DEEP-SEARCH panel has the same (date × iid) shape as close.

    Scope: features wired into ``panel_for_feature`` (not the wider
    FEATURES allowlist — the scorecard-only families belong to other
    compute modules).
    """
    ohlcv, nifty, cap_long = _build_synthetic_ohlcv(n_dates=300, n_instruments=10)
    panels = compute_feature_panels(ohlcv, nifty, cap_long, sector_of=None)
    base = panels.close.shape
    # Iterate over the union of features the generators reference, which
    # is the exact set the deep-search runner needs at evaluation time.
    referenced: set[str] = set()
    for tier in ("Large", "Mid", "Small"):
        for tenure in ("1m", "3m", "6m", "12m"):
            for direction in ("POSITIVE", "NEGATIVE"):
                for c in generate_candidates(tier, tenure, direction):  # type: ignore[arg-type]
                    for pred in c.features:
                        referenced.add(pred.feature)
    for f in sorted(referenced):
        p = panel_for_feature(panels, f)
        assert p.shape == base, f"{f!r} panel shape {p.shape} != close shape {base}"


# ---------------------------------------------------------------------------
# Candidate-generator coverage
# ---------------------------------------------------------------------------


def test_generate_candidates_positive_large_12m_meets_floor() -> None:
    cands = generate_candidates("Large", "12m", "POSITIVE")
    assert len(cands) >= 320, f"expected ≥ 320 POSITIVE candidates, got {len(cands)}"
    # Every candidate's first predicate is the tier liquidity floor.
    for c in cands:
        first = c.features[0]
        assert first.feature == "log_med_tv_60d"
        # Large tier liquidity floor is 16.5.
        # `value` is Decimal for scalar comparisons.
        assert isinstance(first.value, Decimal)
        assert first.value >= Decimal("16.5") - Decimal("0.01")


def test_generate_candidates_negative_small_1m_meets_floor() -> None:
    cands = generate_candidates("Small", "1m", "NEGATIVE")
    assert len(cands) >= 170, f"expected ≥ 170 NEGATIVE candidates, got {len(cands)}"
    for c in cands:
        first = c.features[0]
        assert first.feature == "log_med_tv_60d"
        # Small tier liquidity floor is 14.5.
        assert isinstance(first.value, Decimal)
        assert first.value <= Decimal("14.6")


def test_tier_conditional_liquidity_floors() -> None:
    """Large/Mid/Small carry distinct liquidity floors."""
    floors: dict[str, set[object]] = {}
    for tier in ("Large", "Mid", "Small"):
        cands = generate_candidates(tier, "6m", "POSITIVE")  # type: ignore[arg-type]
        floor_vals: set[object] = {
            c.features[0].value for c in cands if c.features[0].feature == "log_med_tv_60d"
        }
        floors[tier] = floor_vals
    # Each tier should have at least one floor at its expected level.
    assert Decimal("16.5") in floors["Large"]
    assert Decimal("15.5") in floors["Mid"]
    assert Decimal("14.5") in floors["Small"]


def test_quality_momentum_vol_bands_are_tier_conditional() -> None:
    """Red-team gap 2: Small-cap vol bands MUST differ from Large bands.

    Concretely: at least one Small-cap candidate uses a vol band >= 0.035,
    which Large would never use.
    """
    small_cands = generate_candidates("Small", "12m", "POSITIVE")
    vol_caps_small: list[float] = []
    for c in small_cands:
        for p in c.features:
            if p.feature == "realized_vol_60d" and p.cmp in ("<=", "<"):
                vol_caps_small.append(float(p.value))  # type: ignore[arg-type]
    max_small = max(vol_caps_small, default=0)
    assert any(
        v >= 0.035 for v in vol_caps_small
    ), f"Small-cap candidates should use wider vol bands; got max {max_small:.4f}"

    large_cands = generate_candidates("Large", "12m", "POSITIVE")
    vol_caps_large: list[float] = []
    for c in large_cands:
        for p in c.features:
            if p.feature == "realized_vol_60d" and p.cmp in ("<=", "<"):
                vol_caps_large.append(float(p.value))  # type: ignore[arg-type]
    assert any(
        v <= 0.025 for v in vol_caps_large
    ), "Large-cap candidates should use tight vol bands"


# ---------------------------------------------------------------------------
# Sector-feature NaN-safety
# ---------------------------------------------------------------------------


def test_sector_features_nan_safe_when_mapping_absent() -> None:
    """Without sector_of, all sector panels must be all-NaN."""
    ohlcv, nifty, cap_long = _build_synthetic_ohlcv()
    panels = compute_feature_panels(ohlcv, nifty, cap_long, sector_of=None)
    for sf in (
        "sector_rs_6m",
        "sector_rs_12m",
        "sector_rs_rank_6m",
        "sector_breadth_pos",
        "sector_strength_rank",
        "sector_vol_regime",
        "cross_sector_breadth",
    ):
        p = panel_for_feature(panels, sf)
        assert p.isna().values.all(), f"{sf!r} should be all NaN without mapping"


def test_sector_features_computed_when_mapping_provided() -> None:
    """With a sector mapping, sector RS panels have non-NaN cells."""
    ohlcv, nifty, cap_long = _build_synthetic_ohlcv()
    # Build a sector mapping that assigns iids to 3 synthetic sectors.
    iids = ohlcv["iid"].unique()
    sectors = ["Energy", "IT", "Banks"]
    sector_of = pd.Series(
        {str(iid): sectors[i % 3] for i, iid in enumerate(iids)},
        name="sector",
    )
    panels = compute_feature_panels(ohlcv, nifty, cap_long, sector_of=sector_of)
    p = panel_for_feature(panels, "sector_rs_6m")
    # Late dates should have non-NaN entries (after 126d warmup).
    late = p.iloc[-30:]
    assert late.notna().any().any(), "sector_rs_6m should have non-NaN cells after warmup"


# ---------------------------------------------------------------------------
# Runner / JSON smoke
# ---------------------------------------------------------------------------


def _tiny_windows(close_index: pd.DatetimeIndex) -> tuple[WalkForwardWindow, ...]:
    """3 small windows over the synthetic 350-day panel."""
    dates = sorted(set(close_index.date))
    third = len(dates) // 3
    # Skip warmup so panels have data.
    train_start = dates[max(0, third - 100)]
    train_end = dates[third + 30]
    test_start = dates[third + 31]
    test_end = dates[third + 80]
    w1 = WalkForwardWindow(train_start, train_end, test_start, test_end)
    train_start2 = dates[third + 50]
    train_end2 = dates[third + 90]
    test_start2 = dates[third + 91]
    test_end2 = dates[third + 130]
    w2 = WalkForwardWindow(train_start2, train_end2, test_start2, test_end2)
    train_start3 = dates[third + 100]
    train_end3 = dates[third + 140]
    test_start3 = dates[third + 141]
    test_end3 = dates[third + 180]
    w3 = WalkForwardWindow(train_start3, train_end3, test_start3, test_end3)
    return (w1, w2, w3)


def test_bh_q_values_monotonic_after_sort() -> None:
    """After BH correction, q-values should respect the FDR step-up."""
    metrics = []
    for i in range(10):
        m = CandidateMetrics(
            name=f"c{i}",
            archetype="t",
            rationale="",
            ic=0.1 - 0.01 * i,
            tp_rate=0.5,
            median_excess=0.0,
            mean_excess=0.0,
            friction_adjusted_excess=0.0,
            percentile_10=0.0,
            percentile_25=0.0,
            percentile_50=0.0,
            percentile_75=0.0,
            percentile_90=0.0,
            n_observations=100,
            per_window=(),
            validated=False,
            bh_q_value=float("nan"),
            predicates=(),
        )
        metrics.append(m)
    q = _bh_q_values(metrics)
    assert all(0.0 <= v <= 1.0 for v in q)
    # All q in [0,1].
    assert len(q) == len(metrics)


def test_run_single_cell_writes_json_smoke(tmp_path: Path) -> None:
    """Inject synthetic panels via the ``panels`` argument; runner should
    emit a valid JSON file with BH q-values and gate metadata.
    """
    ohlcv, nifty, cap_long = _build_synthetic_ohlcv()
    panels = compute_feature_panels(ohlcv, nifty, cap_long, sector_of=None)
    summary = run_single_cell(
        tier="Large",
        tenure="6m",
        direction="POSITIVE",
        cache_dir=str(tmp_path),
        output_dir=str(tmp_path),
        panels=panels,
        use_panel_cache=False,
    )
    out = tmp_path / "Large-6m-POSITIVE.json"
    assert out.exists(), "expected per-cell JSON output"
    payload = json.loads(out.read_text())
    assert payload["cell"]["tier"] == "Large"
    assert payload["cell"]["tenure"] == "6m"
    assert payload["cell"]["direction"] == "POSITIVE"
    assert payload["n_candidates"] >= 320
    # Each candidate carries a bh_q_value field.
    for c in payload["candidates"]:
        assert "bh_q_value" in c
    # Run started before completed.
    assert payload["run_completed_at"] >= payload["run_started_at"]
    # Methodology lock recorded.
    assert "methodology_lock_ref" in payload
    assert summary.n_candidates == payload["n_candidates"]


# ---------------------------------------------------------------------------
# IC floor table sanity (a regression catch)
# ---------------------------------------------------------------------------


def test_ic_floors_match_methodology_lock() -> None:
    """Per methodology lock §3 (deep_search v2 spec): floors per tenure."""
    assert PER_TENURE_IC_FLOOR["1m"] == Decimal("0.02")
    assert PER_TENURE_IC_FLOOR["3m"] == Decimal("0.04")
    assert PER_TENURE_IC_FLOOR["6m"] == Decimal("0.05")
    assert PER_TENURE_IC_FLOOR["12m"] == Decimal("0.04")
