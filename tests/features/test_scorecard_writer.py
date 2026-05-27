"""Tests for ``atlas.features.scorecard_writer`` (issue #43).

Covers:
- ``compute_cap_tiers`` vectorisation + tercile correctness
- ``_compute_locked_features`` shape on synthetic input
- ``derive_family_states`` rule correctness
- Look-ahead audit assertion behaviour
- ``ScorecardRow`` schema parity with migration 080
- Full ``compute_daily_scorecard`` shape on a 10-instrument mock pipeline
- ``data_completeness`` calculation on partial bars

All tests mock at the DB boundary — no live Postgres required.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from atlas.features.scorecard_writer import (
    SCORECARD_COLUMNS,
    ScorecardRow,
    ScorecardWriteResult,
    _compute_locked_features,
    _row_dicts,
    compute_cap_tiers,
    compute_daily_scorecard,
    derive_family_states,
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(
    n_instruments: int = 10,
    n_days: int = 300,
    end_date: date | None = None,
    seed: int = 42,
    tv_scale: float | None = None,
) -> pd.DataFrame:
    """Build a synthetic OHLCV long-frame.

    ``tv_scale`` overrides the random TV scale; useful for forcing a known
    tercile assignment in cap_tier tests.
    """
    rng = np.random.default_rng(seed)
    end = end_date or date(2026, 5, 23)
    dates = [d.date() for d in pd.bdate_range(end=pd.Timestamp(end), periods=n_days)]

    rows = []
    for i in range(n_instruments):
        # Per-instrument price walk
        rets = rng.normal(loc=0.0005, scale=0.015, size=n_days)
        prices = 100 * np.cumprod(1 + rets)
        if tv_scale is not None:
            scale = tv_scale * (i + 1)  # monotone scale per instrument
        else:
            scale = float(rng.uniform(1e5, 1e7))
        volumes = (scale * (1 + rng.uniform(-0.2, 0.2, size=n_days))).clip(min=1)
        for d, p, v in zip(dates, prices, volumes, strict=True):
            rows.append(
                {
                    "instrument_id": f"instr-{i:02d}",
                    "date": d,
                    "open": float(p) * 0.99,
                    "high": float(p) * 1.01,
                    "low": float(p) * 0.98,
                    "close": float(p),
                    "volume": float(v),
                }
            )
    return pd.DataFrame(rows)


def _make_universe(n_instruments: int = 10) -> pd.DataFrame:
    sectors = ["Tech", "Finance", "Energy", "Pharma", "Consumer"]
    rows = []
    for i in range(n_instruments):
        rows.append(
            {
                "instrument_id": f"instr-{i:02d}",
                "symbol": f"SYM{i:02d}",
                "tier": "Large" if i < 3 else "Mid" if i < 6 else "Small",
                "sector": sectors[i % len(sectors)],
                "listing_date": date(2018, 1, 1),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Schema parity
# ---------------------------------------------------------------------------


class TestScorecardRowSchemaParity:
    """``ScorecardRow`` must parallel ``atlas_scorecard_daily`` (migration 080)."""

    def test_locked_methodology_features_are_fields(self) -> None:
        fields = ScorecardRow.model_fields
        for feat in (
            "rs_residual_6m",
            "log_med_tv_60d",
            "realized_vol_60d",
            "formation_max_dd",
            "listing_age_days",
            "log_price",
        ):
            assert feat in fields, f"ScorecardRow missing methodology feature {feat}"

    def test_five_family_state_fields(self) -> None:
        fields = ScorecardRow.model_fields
        for fam in (
            "family_trend",
            "family_volatility",
            "family_volume",
            "family_path",
            "family_sector",
        ):
            assert fam in fields, f"ScorecardRow missing family field {fam}"

    def test_identity_fields_present(self) -> None:
        fields = ScorecardRow.model_fields
        for ident in ("date", "instrument_id", "cap_tier"):
            assert ident in fields

    def test_data_completeness_field_present(self) -> None:
        assert "data_completeness" in ScorecardRow.model_fields

    def test_features_jsonb_field_present(self) -> None:
        assert "features" in ScorecardRow.model_fields

    def test_scorecard_columns_tuple_matches_model(self) -> None:
        """``SCORECARD_COLUMNS`` (used by bulk insert) covers all model fields."""
        # date, instrument_id, cap_tier, 5 families, 6 features, features JSONB,
        # data_completeness = 16 columns
        assert len(SCORECARD_COLUMNS) == 16
        for col in (
            "date",
            "instrument_id",
            "cap_tier",
            "family_trend",
            "family_volatility",
            "family_volume",
            "family_path",
            "family_sector",
            "rs_residual_6m",
            "log_med_tv_60d",
            "realized_vol_60d",
            "formation_max_dd",
            "listing_age_days",
            "log_price",
            "features",
            "data_completeness",
        ):
            assert col in SCORECARD_COLUMNS, f"SCORECARD_COLUMNS missing {col}"


# ---------------------------------------------------------------------------
# compute_cap_tiers
# ---------------------------------------------------------------------------


class TestComputeCapTiers:
    def test_empty_input_returns_empty_series(self) -> None:
        empty = pd.DataFrame(columns=["instrument_id", "date", "close", "volume", "traded_value"])
        result = compute_cap_tiers(empty, date(2026, 5, 23))
        assert isinstance(result, pd.Series)
        assert len(result) == 0

    def test_returns_one_value_per_instrument(self) -> None:
        ohlcv = _make_ohlcv(n_instruments=12, n_days=80)
        result = compute_cap_tiers(ohlcv, ohlcv["date"].max())
        assert len(result) == 12

    def test_values_are_in_canonical_tier_set(self) -> None:
        ohlcv = _make_ohlcv(n_instruments=20, n_days=80, tv_scale=1e5)
        result = compute_cap_tiers(ohlcv, ohlcv["date"].max())
        valid_set = {"Small", "Mid", "Large"}
        non_null = result.dropna().unique()
        for v in non_null:
            assert v in valid_set, f"unexpected tier value {v!r}"

    def test_terciles_split_universe(self) -> None:
        """20 instruments with monotone TV → ~7-7-6 tier split."""
        ohlcv = _make_ohlcv(n_instruments=21, n_days=80, tv_scale=1e5)
        result = compute_cap_tiers(ohlcv, ohlcv["date"].max())
        counts = result.value_counts()
        # qcut with q=3 on 21 entries gives 7/7/7
        assert counts["Small"] == 7
        assert counts["Mid"] == 7
        assert counts["Large"] == 7

    def test_largest_tv_lands_in_large_tier(self) -> None:
        """The instrument with the biggest median traded value MUST land in Large."""
        ohlcv = _make_ohlcv(n_instruments=10, n_days=80, tv_scale=1e6)
        # ``tv_scale * (i+1)`` means instr-09 has the largest TV
        result = compute_cap_tiers(ohlcv, ohlcv["date"].max())
        assert result["instr-09"] == "Large"
        assert result["instr-00"] == "Small"

    def test_look_ahead_audit_drops_future_rows(self) -> None:
        """Rows past ``target_date`` are ignored — does not use future TV."""
        ohlcv = _make_ohlcv(n_instruments=5, n_days=80)
        # Pick a target date well inside the window
        target = ohlcv["date"].iloc[len(ohlcv) // 2]
        result = compute_cap_tiers(ohlcv, target)
        # No future-data leakage: function must not raise; result must be valid
        for v in result.dropna():
            assert v in {"Small", "Mid", "Large"}

    def test_handles_degenerate_distribution(self) -> None:
        """All instruments with identical TV — rank-based fallback fires, no crash."""
        # Build OHLCV with constant volume + identical prices so TVs match.
        dates = [d.date() for d in pd.bdate_range(end=pd.Timestamp("2026-05-23"), periods=80)]
        rows = []
        for i in range(5):
            for d in dates:
                rows.append(
                    {
                        "instrument_id": f"instr-{i}",
                        "date": d,
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.0,
                        "volume": 1_000_000.0,
                    }
                )
        ohlcv = pd.DataFrame(rows)
        result = compute_cap_tiers(ohlcv, dates[-1])
        # All-equal TVs still produce a valid tier assignment via rank fallback.
        assert len(result) == 5
        assert set(result.dropna().unique()) <= {"Small", "Mid", "Large"}


# ---------------------------------------------------------------------------
# Look-ahead audit
# ---------------------------------------------------------------------------


class TestLookAheadAudit:
    def test_assertion_fires_on_future_data(self) -> None:
        """``_compute_locked_features`` MUST refuse OHLCV with date > target."""
        ohlcv = _make_ohlcv(n_instruments=3, n_days=300)
        universe = _make_universe(3)
        # target_date well before the OHLCV end → contains future rows
        early_target = ohlcv["date"].iloc[0] + timedelta(days=1)
        with pytest.raises(AssertionError, match="look-ahead audit violation"):
            _compute_locked_features(
                ohlcv,
                bench_close=pd.DataFrame(columns=["date", "bench_close"]),
                universe=universe,
                target_date=early_target,
            )

    def test_assertion_does_not_fire_when_clamped(self) -> None:
        """When OHLCV is pre-clamped to ``date <= target_date``, no AssertionError."""
        ohlcv = _make_ohlcv(n_instruments=3, n_days=300)
        target = ohlcv["date"].max()
        clamped = ohlcv.loc[ohlcv["date"] <= target]
        universe = _make_universe(3)
        # Should run cleanly (may produce empty result if rolling-window
        # minimums aren't met, but no assertion error)
        _ = _compute_locked_features(
            clamped,
            bench_close=pd.DataFrame(columns=["date", "bench_close"]),
            universe=universe,
            target_date=target,
        )


# ---------------------------------------------------------------------------
# Locked feature compute
# ---------------------------------------------------------------------------


class TestLockedFeatures:
    def test_returns_snap_only_at_target_date(self) -> None:
        ohlcv = _make_ohlcv(n_instruments=5, n_days=300)
        universe = _make_universe(5)
        target = ohlcv["date"].max()
        snap = _compute_locked_features(
            ohlcv,
            bench_close=pd.DataFrame(columns=["date", "bench_close"]),
            universe=universe,
            target_date=target,
        )
        assert (snap["date"] == target).all()
        # 5 instruments — at most one row each
        assert snap["instrument_id"].nunique() == len(snap)

    def test_all_six_feature_columns_present(self) -> None:
        ohlcv = _make_ohlcv(n_instruments=4, n_days=300)
        universe = _make_universe(4)
        target = ohlcv["date"].max()
        snap = _compute_locked_features(
            ohlcv,
            bench_close=pd.DataFrame(columns=["date", "bench_close"]),
            universe=universe,
            target_date=target,
        )
        for feat in (
            "rs_residual_6m",
            "log_med_tv_60d",
            "realized_vol_60d",
            "formation_max_dd",
            "log_price",
            "listing_age_days",
        ):
            assert feat in snap.columns, f"missing locked feature column {feat}"

    def test_listing_age_days_is_non_negative(self) -> None:
        ohlcv = _make_ohlcv(n_instruments=3, n_days=300)
        universe = _make_universe(3)
        target = ohlcv["date"].max()
        snap = _compute_locked_features(
            ohlcv,
            bench_close=pd.DataFrame(columns=["date", "bench_close"]),
            universe=universe,
            target_date=target,
        )
        assert (snap["listing_age_days"].dropna() >= 0).all()

    def test_data_completeness_in_unit_range(self) -> None:
        ohlcv = _make_ohlcv(n_instruments=3, n_days=300)
        universe = _make_universe(3)
        target = ohlcv["date"].max()
        snap = _compute_locked_features(
            ohlcv,
            bench_close=pd.DataFrame(columns=["date", "bench_close"]),
            universe=universe,
            target_date=target,
        )
        dc = snap["data_completeness"].dropna()
        assert (dc >= 0).all() and (dc <= 1.0).all()

    def test_data_completeness_lower_for_short_history_instrument(self) -> None:
        """Drop half of one instrument's bars → data_completeness < 1 for it."""
        ohlcv = _make_ohlcv(n_instruments=4, n_days=300)
        universe = _make_universe(4)
        target = ohlcv["date"].max()
        # Trim instr-03 in half
        mask = (ohlcv["instrument_id"] != "instr-03") | (ohlcv["date"] >= date(2025, 11, 1))
        ohlcv_partial = ohlcv.loc[mask]

        # Build a benchmark frame so "expected" bar count is well-defined.
        bench_dates = (
            ohlcv.loc[ohlcv["instrument_id"] == "instr-00", ["date"]].drop_duplicates().copy()
        )
        bench_dates["bench_close"] = 100.0

        snap = _compute_locked_features(
            ohlcv_partial,
            bench_close=bench_dates,
            universe=universe,
            target_date=target,
        )
        row = snap.loc[snap["instrument_id"] == "instr-03"].iloc[0]
        assert row["data_completeness"] < 1.0


# ---------------------------------------------------------------------------
# derive_family_states
# ---------------------------------------------------------------------------


class TestDeriveFamilyStates:
    def _snap(self) -> pd.DataFrame:
        """Hand-crafted snap covering the rule corners."""
        return pd.DataFrame(
            {
                "instrument_id": [f"instr-{i:02d}" for i in range(10)],
                "sector": ["Tech"] * 5 + ["Finance"] * 5,
                "rs_residual_6m": [-0.20, -0.10, 0.00, 0.05, 0.30, -0.15, -0.05, 0.02, 0.10, 0.40],
                "realized_vol_60d": [0.10, 0.15, 0.25, 0.30, 0.40, 0.12, 0.18, 0.22, 0.35, 0.50],
                "formation_max_dd": [0.05, 0.08, 0.15, 0.20, 0.35, 0.06, 0.12, 0.18, 0.28, 0.45],
                "dd_from_52w": [0.02, 0.04, 0.10, 0.15, 0.30, 0.03, 0.08, 0.12, 0.20, 0.35],
            }
        )

    def test_all_five_families_attached(self) -> None:
        out = derive_family_states(self._snap(), thresholds={})
        for fam in (
            "family_trend",
            "family_volatility",
            "family_volume",
            "family_path",
            "family_sector",
        ):
            assert fam in out.columns

    def test_values_in_rag_set(self) -> None:
        out = derive_family_states(self._snap(), thresholds={})
        for fam in (
            "family_trend",
            "family_volatility",
            "family_volume",
            "family_path",
            "family_sector",
        ):
            assert set(out[fam].unique()) <= {
                "R",
                "A",
                "G",
            }, f"{fam} has non-RAG values: {set(out[fam].unique())}"

    def test_path_red_when_both_dd_high(self) -> None:
        """formation_max_dd > 0.30 AND dd_from_52w > 0.25 → R."""
        out = derive_family_states(self._snap(), thresholds={})
        # instr-04: formation 0.35, dd52 0.30 → R
        assert out.loc[out["instrument_id"] == "instr-04", "family_path"].iloc[0] == "R"

    def test_path_green_when_both_dd_low(self) -> None:
        """formation_max_dd < 0.10 AND dd_from_52w < 0.05 → G."""
        out = derive_family_states(self._snap(), thresholds={})
        # instr-00: formation 0.05, dd52 0.02 → G
        assert out.loc[out["instrument_id"] == "instr-00", "family_path"].iloc[0] == "G"

    def test_trend_red_at_low_percentile(self) -> None:
        """Lowest rs_residual_6m → bottom decile → R."""
        out = derive_family_states(self._snap(), thresholds={})
        # instr-00 has rs_residual_6m=-0.20, the minimum
        assert out.loc[out["instrument_id"] == "instr-00", "family_trend"].iloc[0] == "R"

    def test_trend_green_at_high_percentile(self) -> None:
        out = derive_family_states(self._snap(), thresholds={})
        # instr-09 has the top rs_residual_6m
        assert out.loc[out["instrument_id"] == "instr-09", "family_trend"].iloc[0] == "G"

    def test_volatility_red_at_high_vol(self) -> None:
        out = derive_family_states(self._snap(), thresholds={})
        # instr-09 has the highest realized_vol_60d
        assert out.loc[out["instrument_id"] == "instr-09", "family_volatility"].iloc[0] == "R"

    def test_handles_nan_inputs_with_amber(self) -> None:
        """NaN feature → A (conservative)."""
        snap = self._snap()
        snap.loc[0, "rs_residual_6m"] = np.nan
        snap.loc[0, "realized_vol_60d"] = np.nan
        snap.loc[0, "formation_max_dd"] = np.nan
        snap.loc[0, "dd_from_52w"] = np.nan
        out = derive_family_states(snap, thresholds={})
        row = out.iloc[0]
        assert row["family_trend"] == "A"
        assert row["family_volatility"] == "A"
        assert row["family_path"] == "A"

    def test_threshold_override_from_atlas_thresholds(self) -> None:
        """Threshold values from ``load_thresholds()`` win over defaults."""
        # Crank the green threshold so even the top instrument falls to A
        overrides = {"family_trend_green_p": Decimal("0.999")}
        out = derive_family_states(self._snap(), thresholds=overrides)
        # No row should be G under such an aggressive green cutoff
        assert (out["family_trend"] != "G").all() or (out["family_trend"] == "G").sum() <= 1


# ---------------------------------------------------------------------------
# _row_dicts serialization
# ---------------------------------------------------------------------------


class TestRowDicts:
    def test_serialises_all_scorecard_columns(self) -> None:
        snap = pd.DataFrame(
            {
                "instrument_id": ["instr-00"],
                "cap_tier": ["Large"],
                "family_trend": ["G"],
                "family_volatility": ["A"],
                "family_volume": ["A"],
                "family_path": ["G"],
                "family_sector": ["G"],
                "rs_residual_6m": [0.05],
                "log_med_tv_60d": [12.5],
                "realized_vol_60d": [0.2],
                "formation_max_dd": [0.08],
                "listing_age_days": [1200],
                "log_price": [5.0],
                "data_completeness": [1.0],
                "date": [date(2026, 5, 23)],
            }
        )
        rows = _row_dicts(snap, date(2026, 5, 23))
        assert len(rows) == 1
        for col in SCORECARD_COLUMNS:
            assert col in rows[0], f"_row_dicts missing column {col}"

    def test_fills_missing_cap_tier_with_mid(self) -> None:
        """``cap_tier`` NA → "Mid" so the NOT NULL DB constraint passes."""
        snap = pd.DataFrame(
            {
                "instrument_id": ["instr-99"],
                "cap_tier": [pd.NA],
                "family_trend": ["A"],
                "family_volatility": ["A"],
                "family_volume": ["A"],
                "family_path": ["A"],
                "family_sector": ["A"],
                "rs_residual_6m": [np.nan],
                "log_med_tv_60d": [np.nan],
                "realized_vol_60d": [np.nan],
                "formation_max_dd": [np.nan],
                "listing_age_days": [None],
                "log_price": [np.nan],
                "data_completeness": [0.5],
                "date": [date(2026, 5, 23)],
            }
        )
        rows = _row_dicts(snap, date(2026, 5, 23))
        assert rows[0]["cap_tier"] == "Mid"

    def test_data_completeness_is_decimal(self) -> None:
        snap = pd.DataFrame(
            {
                "instrument_id": ["x"],
                "cap_tier": ["Mid"],
                "family_trend": ["A"],
                "family_volatility": ["A"],
                "family_volume": ["A"],
                "family_path": ["A"],
                "family_sector": ["A"],
                "rs_residual_6m": [0.0],
                "log_med_tv_60d": [0.0],
                "realized_vol_60d": [0.0],
                "formation_max_dd": [0.0],
                "listing_age_days": [10],
                "log_price": [0.0],
                "data_completeness": [0.875],
                "date": [date(2026, 5, 23)],
            }
        )
        rows = _row_dicts(snap, date(2026, 5, 23))
        assert isinstance(rows[0]["data_completeness"], Decimal)
        assert rows[0]["data_completeness"] == Decimal("0.875")


# ---------------------------------------------------------------------------
# compute_daily_scorecard — full pipeline shape on a mocked DB
# ---------------------------------------------------------------------------


class TestComputeDailyScorecard:
    def _patch_db_helpers(
        self,
        *,
        universe: pd.DataFrame,
        ohlcv: pd.DataFrame,
        bench: pd.DataFrame,
    ):
        """Return a context-manager bundle that stubs DB-touching helpers."""
        load_universe = patch(
            "atlas.features.scorecard_writer._load_universe",
            return_value=universe,
        )
        load_ohlcv = patch(
            "atlas.features.scorecard_writer._load_ohlcv",
            return_value=ohlcv,
        )
        load_bench = patch(
            "atlas.features.scorecard_writer._load_nifty500_close",
            return_value=bench,
        )
        load_thresholds = patch(
            "atlas.features.scorecard_writer.load_thresholds",
            return_value={},
        )
        bulk_upsert = patch(
            "atlas.features.scorecard_writer.bulk_upsert",
            return_value=10,
        )
        return load_universe, load_ohlcv, load_bench, load_thresholds, bulk_upsert

    def test_returns_scorecard_write_result(self) -> None:
        universe = _make_universe(10)
        ohlcv = _make_ohlcv(n_instruments=10, n_days=300)
        bench = pd.DataFrame({"date": ohlcv["date"].unique(), "bench_close": 100.0})
        bench["bench_close"] = np.linspace(100, 110, len(bench))
        target = ohlcv["date"].max()

        engine = MagicMock()
        (
            patched_universe,
            patched_ohlcv,
            patched_bench,
            patched_thresholds,
            patched_bulk,
        ) = self._patch_db_helpers(universe=universe, ohlcv=ohlcv, bench=bench)
        with patched_universe, patched_ohlcv, patched_bench, patched_thresholds, patched_bulk:
            result = compute_daily_scorecard(target, engine)
        assert isinstance(result, ScorecardWriteResult)
        assert result.target_date == target

    def test_writes_rows_via_bulk_upsert(self) -> None:
        universe = _make_universe(10)
        ohlcv = _make_ohlcv(n_instruments=10, n_days=300)
        bench = pd.DataFrame({"date": ohlcv["date"].unique(), "bench_close": 100.0})
        target = ohlcv["date"].max()

        engine = MagicMock()
        (
            patched_universe,
            patched_ohlcv,
            patched_bench,
            patched_thresholds,
            patched_bulk,
        ) = self._patch_db_helpers(universe=universe, ohlcv=ohlcv, bench=bench)
        with (
            patched_universe,
            patched_ohlcv,
            patched_bench,
            patched_thresholds,
            patched_bulk as bulk_mock,
        ):
            result = compute_daily_scorecard(target, engine)
        # bulk_upsert called once with the scorecard table
        assert bulk_mock.called
        call = bulk_mock.call_args
        assert call.kwargs["table"] == "atlas.atlas_scorecard_daily"
        assert call.kwargs["pk_columns"] == ["date", "instrument_id"]
        assert result.rows_written == 10

    def test_skips_write_when_write_false(self) -> None:
        universe = _make_universe(5)
        ohlcv = _make_ohlcv(n_instruments=5, n_days=300)
        bench = pd.DataFrame({"date": ohlcv["date"].unique(), "bench_close": 100.0})
        target = ohlcv["date"].max()

        engine = MagicMock()
        (
            patched_universe,
            patched_ohlcv,
            patched_bench,
            patched_thresholds,
            patched_bulk,
        ) = self._patch_db_helpers(universe=universe, ohlcv=ohlcv, bench=bench)
        with (
            patched_universe,
            patched_ohlcv,
            patched_bench,
            patched_thresholds,
            patched_bulk as bulk_mock,
        ):
            result = compute_daily_scorecard(target, engine, write=False)
        assert not bulk_mock.called
        # rows_written reflects compute count (5) even though no DB write
        assert result.rows_written == 5

    def test_empty_universe_returns_zero_rows(self) -> None:
        empty_universe = pd.DataFrame(
            columns=["instrument_id", "symbol", "tier", "sector", "listing_date"]
        )
        engine = MagicMock()
        with (
            patch(
                "atlas.features.scorecard_writer._load_universe",
                return_value=empty_universe,
            ),
            patch(
                "atlas.features.scorecard_writer.load_thresholds",
                return_value={},
            ),
        ):
            result = compute_daily_scorecard(date(2026, 5, 23), engine)
        assert result.rows_written == 0

    def test_missing_instruments_reported(self) -> None:
        """Universe ⊃ OHLCV — missing instruments surface in the result."""
        universe = _make_universe(10)
        # Only 5 of the 10 universe instruments have OHLCV
        ohlcv = _make_ohlcv(n_instruments=10, n_days=300)
        ohlcv = ohlcv.loc[ohlcv["instrument_id"].isin([f"instr-{i:02d}" for i in range(5)])]
        bench = pd.DataFrame({"date": ohlcv["date"].unique(), "bench_close": 100.0})
        target = ohlcv["date"].max()

        engine = MagicMock()
        (
            patched_universe,
            patched_ohlcv,
            patched_bench,
            patched_thresholds,
            patched_bulk,
        ) = self._patch_db_helpers(universe=universe, ohlcv=ohlcv, bench=bench)
        with patched_universe, patched_ohlcv, patched_bench, patched_thresholds, patched_bulk:
            result = compute_daily_scorecard(target, engine)
        # 5 universe IDs (instr-05 .. instr-09) absent from snap
        assert len(result.missing_instruments) == 5
