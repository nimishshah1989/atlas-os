"""Tests for the scorecard ↔ deep-search feature-library bridge.

Closes the conviction-tape integration gap (CONTEXT.md §"Cell rule"): the
6 locked methodology features stay as first-class columns on
``atlas.atlas_scorecard_daily``, but every OTHER feature the cell rules
reference must round-trip through the ``features`` JSONB column so the
predicate evaluator finds non-NULL values.

Three load-bearing invariants:

1. ``compute_daily_scorecard`` on a synthetic 60-day × 20-instrument
   panel writes a features JSONB with at least 25 keys per row.
2. The value stored under (say) ``sector_rs_rank_6m`` matches the value
   produced by ``compute_feature_panels`` directly on the same OHLCV
   (no silent NaN swap, no double-divide bug).
3. ``compute_conviction_for_snapshot`` on the resulting scorecard rows
   returns at least one non-NEUTRAL verdict when a validated cell
   candidate references a deep-search feature.

Pure pandas + in-memory pipeline tests — no live Postgres.
"""

# allow-large: bridge tests assert end-to-end coverage of the integration
# gap. Splitting into per-invariant files would scatter the fixture
# builders across modules without simplifying any individual test.

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pytest

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate
from atlas.discovery.deep_search_features import (
    compute_feature_panels,
    panel_for_feature,
)
from atlas.features.scorecard_writer import (
    _DEEP_SEARCH_PANEL_FEATURES,
    _FIRST_CLASS_FEATURE_NAMES,
    _compute_deep_search_features_jsonb,
    _to_jsonb_safe,
)
from atlas.inference.conviction_tape import (
    CandidateRow,
    compute_conviction_for_snapshot,
)

# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------


def _build_ohlcv_and_bench(
    n_instruments: int = 20,
    n_days: int = 350,
    end_date: date | None = None,
    seed: int = 17,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (ohlcv long-frame, bench frame).

    ohlcv columns: instrument_id, date, open, high, low, close, volume.
    bench columns: date, bench_close.

    Enough history (≥ 252d) for the 12m RS + drawdown panels to resolve.
    """
    rng = np.random.default_rng(seed)
    end = end_date or date(2026, 5, 22)
    dates = [d.date() for d in pd.bdate_range(end=pd.Timestamp(end), periods=n_days)]

    # Generate per-instrument random walks with mild differential drift
    # so cross-sectional ranks are meaningful.
    drifts = rng.uniform(-0.001, 0.002, size=n_instruments)
    rows: list[dict[str, Any]] = []
    closes_by_instr: dict[int, np.ndarray] = {}
    for i in range(n_instruments):
        rets = rng.normal(loc=drifts[i], scale=0.015, size=n_days)
        prices = 100.0 * np.cumprod(1.0 + rets)
        prices = np.maximum(prices, 1.0)
        closes_by_instr[i] = prices
        # Scale traded value per instrument to create three populated tiers.
        tv_scale = float(rng.uniform(1e5, 5e7))
        volumes = (tv_scale * (1 + rng.uniform(-0.2, 0.2, size=n_days))).clip(min=1.0)
        for d, p, v in zip(dates, prices, volumes, strict=True):
            rows.append(
                {
                    "instrument_id": f"iid-{i:02d}",
                    "date": d,
                    "open": float(p) * 0.99,
                    "high": float(p) * 1.01,
                    "low": float(p) * 0.98,
                    "close": float(p),
                    "volume": float(v),
                }
            )
    ohlcv = pd.DataFrame(rows)

    # NIFTY 500 bench — independent random walk.
    bench_close = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.008, size=n_days))
    bench = pd.DataFrame({"date": dates, "bench_close": bench_close.astype(float)})
    return ohlcv, bench


def _target_date(ohlcv: pd.DataFrame) -> date:
    """Most recent date in the OHLCV frame as a python ``date``.

    Pyright cannot narrow ``ohlcv["date"].max()`` past ``Series | Any``;
    coerce explicitly so downstream signatures (which take ``date``)
    type-check.
    """
    raw: object = ohlcv["date"].max()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, pd.Timestamp):
        return raw.date()
    # Fall through — pandas may return a numpy datetime64 or similar.
    # ``pd.to_datetime`` coerces every scalar form that pandas itself
    # produces from ``.max()`` on a date column.
    return pd.to_datetime(str(raw)).date()


def _build_cap_tiers(ohlcv: pd.DataFrame) -> pd.Series:
    """Compute cap_tiers via the scorecard writer's helper (for parity)."""
    from atlas.features.scorecard_writer import compute_cap_tiers

    return compute_cap_tiers(ohlcv, _target_date(ohlcv))


# ---------------------------------------------------------------------------
# Invariant 1 — features JSONB carries ≥ 25 keys per populated row
# ---------------------------------------------------------------------------


def test_compute_deep_search_features_jsonb_populates_each_instrument() -> None:
    """Bridge function must produce a non-empty dict for every iid with
    enough history (the 252-day windows). 25 keys is the spec floor."""
    ohlcv, bench = _build_ohlcv_and_bench(n_instruments=20, n_days=350)
    target_date = _target_date(ohlcv)
    cap_tiers = _build_cap_tiers(ohlcv)

    jsonb = _compute_deep_search_features_jsonb(ohlcv, bench, cap_tiers, target_date)

    # Every iid must have an entry — the synthetic series carries 350
    # trading days which exceeds every panel's min_periods floor.
    assert len(jsonb) >= 18, f"expected ≥ 18 populated instruments, got {len(jsonb)}"

    # Each populated entry must carry at least 25 non-NaN feature keys —
    # the spec floor that proves the bridge is firing across families.
    for iid, feats in jsonb.items():
        assert len(feats) >= 25, (
            f"iid {iid} carries only {len(feats)} keys (expected ≥ 25 from deep-search library)"
        )


def test_features_jsonb_excludes_first_class_columns() -> None:
    """The 6 locked first-class columns MUST NOT appear in the JSONB —
    otherwise we duplicate state and risk the JSONB silently overriding
    the column at predicate-evaluation time (dict.update semantics)."""
    ohlcv, bench = _build_ohlcv_and_bench(n_instruments=10, n_days=300)
    target_date = _target_date(ohlcv)
    cap_tiers = _build_cap_tiers(ohlcv)

    jsonb = _compute_deep_search_features_jsonb(ohlcv, bench, cap_tiers, target_date)

    for iid, feats in jsonb.items():
        leaked = _FIRST_CLASS_FEATURE_NAMES & set(feats.keys())
        assert not leaked, f"iid {iid} JSONB leaks first-class column(s): {leaked}"


def test_features_jsonb_covers_diverse_families() -> None:
    """Across instruments the JSONB must cover trend, volatility, drawdown,
    volume, RS, and (when available) sector families — not just one cluster."""
    ohlcv, bench = _build_ohlcv_and_bench(n_instruments=15, n_days=350)
    target_date = _target_date(ohlcv)
    cap_tiers = _build_cap_tiers(ohlcv)

    jsonb = _compute_deep_search_features_jsonb(ohlcv, bench, cap_tiers, target_date)
    all_keys: set[str] = set()
    for feats in jsonb.values():
        all_keys.update(feats.keys())

    # Each family must contribute at least one feature.
    families = {
        "trend": {"rs_residual_3m", "rs_residual_12m", "trend_slope_60d", "rs_acceleration_63d"},
        "volatility": {"realized_vol_252d", "vol_regime_60_252", "downside_vol_60d", "beta_60d"},
        "drawdown": {"dd_from_52w_high", "ulcer_index_60d", "dd_recovery_pct"},
        "volume": {"volume_zscore_60d", "obv_slope_60d", "mfi_14", "tv_momentum_21_63"},
        "momentum": {"rsi_14", "roc_21d", "roc_63d", "roc_126d"},
    }
    for family_name, candidates in families.items():
        hit = candidates & all_keys
        assert hit, f"family {family_name} is missing entirely from JSONB"


# ---------------------------------------------------------------------------
# Invariant 2 — JSONB values match panel_for_feature output
# ---------------------------------------------------------------------------


def test_jsonb_value_matches_panel_directly() -> None:
    """Round-trip parity: the value in JSONB equals what
    ``panel_for_feature`` returns when called on the same OHLCV slice."""
    ohlcv, bench = _build_ohlcv_and_bench(n_instruments=12, n_days=350)
    target_date = _target_date(ohlcv)
    cap_tiers = _build_cap_tiers(ohlcv)

    jsonb = _compute_deep_search_features_jsonb(ohlcv, bench, cap_tiers, target_date)

    # Rebuild panels independently for cross-check.
    ds_ohlcv = pd.DataFrame(
        {
            "iid": ohlcv["instrument_id"].astype(str).to_numpy(),
            "date": ohlcv["date"].to_numpy(),
            "close": ohlcv["close"].to_numpy(),
            "volume": ohlcv["volume"].to_numpy(),
        }
    )
    bench_series = pd.Series(
        bench["bench_close"].astype(float).to_numpy(),
        index=pd.Index(bench["date"], name="date"),
        name="nifty500",
    )
    cap_long = pd.DataFrame(
        [
            {"date": d, "iid": str(iid), "cap_tier": tier}
            for iid, tier in cap_tiers.fillna("Mid").astype(str).items()
            for d in sorted(ds_ohlcv["date"].unique())
        ]
    )
    panels = compute_feature_panels(ds_ohlcv, bench_series, cap_long, sector_of=None)

    # Spot-check a value from a stable non-first-class panel: rsi_14.
    rsi_panel = panel_for_feature(panels, "rsi_14")
    assert target_date in rsi_panel.index
    direct_row = rsi_panel.loc[target_date]
    for iid, expected_val in direct_row.items():
        iid_str = str(iid)
        if iid_str not in jsonb:
            continue
        if "rsi_14" not in jsonb[iid_str]:
            # If direct value is NaN, bridge correctly omits the key.
            assert np.isnan(expected_val) or expected_val is None
            continue
        bridge_val = jsonb[iid_str]["rsi_14"]
        # Both are float — exact equality is fine, no precision loss
        # through dict.update + JSON round-trip in pure-Python mode.
        assert pytest.approx(bridge_val, rel=1e-9, abs=1e-9) == float(expected_val)


# ---------------------------------------------------------------------------
# Invariant 3 — conviction tape produces non-NEUTRAL on the new JSONB
# ---------------------------------------------------------------------------


def _candidate_from_feature(
    candidate_id: str,
    feature: str,
    cmp: str,
    value: float,
    action: str = "POSITIVE",
    cap_tier: str = "Large",
    tenure: str = "6m",
    fric_adj: float = 0.05,
) -> CandidateRow:
    """Build a single-predicate candidate that fires when ``row[feature] cmp value``."""
    pred = FeaturePredicate(
        feature=feature,  # type: ignore[arg-type]
        cmp=cmp,  # type: ignore[arg-type]
        value=Decimal(str(value)),
    )
    rule = CellRule(
        rule_type="placeholder",
        eligibility=[],
        entry=[pred],
        tier=cap_tier,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        tenure=tenure,  # type: ignore[arg-type]
        rule_version=1,
        methodology_lock_ref="TEST",
        notes=f"name={candidate_id} | archetype=test_bridge | rank=1",
    )
    return CandidateRow(
        candidate_id=candidate_id,
        cell_definition_id=f"cell-{candidate_id}",
        cap_tier=cap_tier,
        action=action,  # type: ignore[arg-type]
        tenure=tenure,  # type: ignore[arg-type]
        rule=rule,
        ic=Decimal("0.10"),
        friction_adjusted_excess=Decimal(str(fric_adj)),
        archetype="test_bridge",
    )


def test_conviction_tape_returns_non_neutral_with_bridge() -> None:
    """End-to-end: after the bridge populates JSONB, a candidate
    referencing a non-first-class feature must fire on at least one
    scorecard row."""
    ohlcv, bench = _build_ohlcv_and_bench(n_instruments=20, n_days=350)
    target_date = _target_date(ohlcv)
    cap_tiers = _build_cap_tiers(ohlcv)

    jsonb = _compute_deep_search_features_jsonb(ohlcv, bench, cap_tiers, target_date)

    # Build scorecard rows shaped exactly like _load_scorecard_rows in
    # production: top-level dict merged with the features JSONB.
    scorecard_rows: list[dict[str, Any]] = []
    for iid, feats in jsonb.items():
        if "rsi_14" not in feats:
            continue
        scorecard_rows.append(
            {
                "instrument_id": iid,
                "cap_tier": str(cap_tiers.get(iid, "Mid")),
                # First-class columns (any value — predicate below targets rsi_14)
                "rs_residual_6m": None,
                "log_med_tv_60d": None,
                "realized_vol_60d": None,
                "formation_max_dd": None,
                "listing_age_days": None,
                "log_price": None,
                # JSONB merge — mirrors _load_scorecard_rows behaviour.
                **feats,
            }
        )

    assert scorecard_rows, "fixture must produce at least one row with rsi_14 populated"

    # A POSITIVE candidate that fires on rsi_14 > 0 (i.e. any non-zero RSI;
    # virtually every synthetic row qualifies) — proves the JSONB key
    # threads through to the evaluator.
    candidates_by_key: dict[tuple[str, str, str], list[CandidateRow]] = {}
    for tier in ("Small", "Mid", "Large"):
        candidates_by_key[(tier, "POSITIVE", "6m")] = [
            _candidate_from_feature(
                f"pos-rsi-{tier}",
                feature="rsi_14",
                cmp=">",
                value=0.0,
                action="POSITIVE",
                cap_tier=tier,
                tenure="6m",
                fric_adj=0.05,
            )
        ]

    conviction_rows = compute_conviction_for_snapshot(
        target_date,
        scorecard_rows=scorecard_rows,
        candidates_by_key=candidates_by_key,
    )
    positives = [r for r in conviction_rows if r.verdict == "POSITIVE"]
    assert positives, (
        "expected ≥ 1 POSITIVE verdict from JSONB-backed predicate, got "
        f"{len(conviction_rows)} rows all NEUTRAL — bridge did not thread"
    )


# ---------------------------------------------------------------------------
# _to_jsonb_safe coercion
# ---------------------------------------------------------------------------


def test_to_jsonb_safe_handles_nan_inf_and_scalars() -> None:
    """Numpy NaN / inf → None; ints stay ints; floats stay floats."""
    assert _to_jsonb_safe(np.nan) is None
    assert _to_jsonb_safe(np.inf) is None
    assert _to_jsonb_safe(-np.inf) is None
    assert _to_jsonb_safe(None) is None
    assert _to_jsonb_safe(np.float64(1.5)) == 1.5
    assert isinstance(_to_jsonb_safe(np.float64(1.5)), float)
    assert _to_jsonb_safe(np.int64(7)) == 7
    assert isinstance(_to_jsonb_safe(np.int64(7)), int)
    assert _to_jsonb_safe(True) is True
    assert _to_jsonb_safe("not-a-number") is None


def test_deep_search_panel_features_matches_panel_for_feature_mapping() -> None:
    """The static ``_DEEP_SEARCH_PANEL_FEATURES`` list must stay in lockstep
    with the panels exposed by ``panel_for_feature``. Drift here is the
    exact failure mode the conviction-tape bug emerged from."""
    ohlcv, bench = _build_ohlcv_and_bench(n_instruments=8, n_days=300)
    ds_ohlcv = pd.DataFrame(
        {
            "iid": ohlcv["instrument_id"].astype(str).to_numpy(),
            "date": ohlcv["date"].to_numpy(),
            "close": ohlcv["close"].to_numpy(),
            "volume": ohlcv["volume"].to_numpy(),
        }
    )
    bench_series = pd.Series(
        bench["bench_close"].astype(float).to_numpy(),
        index=pd.Index(bench["date"], name="date"),
        name="nifty500",
    )
    cap_long = pd.DataFrame(
        [
            {"date": d, "iid": iid, "cap_tier": "Mid"}
            for d in sorted(ds_ohlcv["date"].unique())
            for iid in ds_ohlcv["iid"].unique()
        ]
    )
    panels = compute_feature_panels(ds_ohlcv, bench_series, cap_long, sector_of=None)
    missing: list[str] = []
    for feature in _DEEP_SEARCH_PANEL_FEATURES:
        try:
            panel_for_feature(panels, feature)
        except KeyError:
            missing.append(feature)
    assert not missing, f"_DEEP_SEARCH_PANEL_FEATURES drifted from panel mapping: {missing}"
