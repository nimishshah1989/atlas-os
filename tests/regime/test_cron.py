"""Tests for ``atlas.regime.cron`` — daily regime cron (#44).

Covers:

* The 4 input compute helpers (``compute_smallcap_rs_z``,
  ``compute_breadth_pct_above_200dma``, ``compute_vix_percentile``,
  ``compute_cross_sectional_dispersion``) on synthetic frames.
* The threshold resolver (``atlas_thresholds`` complete → resolved;
  partial / missing / empty → fallback).
* The full ``compute_daily_regime`` flow on a mocked DB engine — canned
  loaders, captured ``bulk_upsert`` call. Tests:
    - Risk-On classification on benign synthetic data.
    - Risk-Off classification on stressed synthetic data.
    - INSERT-OR-UPDATE semantics (two calls, one row, latest values).
    - VIX-NaN path — vix_valid=False threaded into classify.
    - ``write=False`` skips the DB write entirely.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.engine import Engine

from atlas.regime.classifier import RegimeState, RegimeThresholds
from atlas.regime.cron import (
    _resolve_thresholds,
    compute_breadth_pct_above_200dma,
    compute_cross_sectional_dispersion,
    compute_daily_regime,
    compute_smallcap_rs_z,
    compute_vix_percentile,
)

# ---------------------------------------------------------------------------
# Synthetic frame helpers
# ---------------------------------------------------------------------------


def _bdate_range(end: date, periods: int) -> list[date]:
    return [d.date() for d in pd.bdate_range(end=pd.Timestamp(end), periods=periods)]


def _index_frame(
    end: date,
    periods: int,
    start_close: float,
    drift: float,
    seed: int = 1,
) -> pd.DataFrame:
    """Synthetic (date, close) frame for a single index."""
    rng = np.random.default_rng(seed)
    dates = _bdate_range(end, periods)
    rets = rng.normal(loc=drift, scale=0.01, size=periods)
    closes = start_close * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes.astype("float64")})


def _universe_ohlcv(
    end: date,
    periods: int,
    n_instruments: int = 50,
    drift: float = 0.001,
    seed: int = 7,
    daily_vol: float = 0.003,
) -> pd.DataFrame:
    """Long-frame OHLCV for n_instruments × periods days.

    ``daily_vol`` controls per-instrument daily-return std. Default 0.003
    keeps cross-sectional 20-day dispersion under the 0.02 Elevated cutoff
    on synthetic data — equivalent to a quiet market with idiosyncratic
    noise. Tests that need a high-dispersion regime should pass a larger
    value.
    """
    rng = np.random.default_rng(seed)
    dates = _bdate_range(end, periods)
    rows: list[dict[str, Any]] = []
    for i in range(n_instruments):
        # Per-instrument idiosyncratic drift
        idio = drift + rng.normal(loc=0.0, scale=0.0005)
        rets = rng.normal(loc=idio, scale=daily_vol, size=periods)
        closes = 100 * np.cumprod(1 + rets)
        for d, c in zip(dates, closes, strict=True):
            rows.append(
                {
                    "instrument_id": f"instr-{i:03d}",
                    "date": d,
                    "close": float(c),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Compute helpers
# ---------------------------------------------------------------------------


def test_smallcap_rs_z_returns_scalar_on_benign_inputs() -> None:
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=300, start_close=20000.0, drift=0.0005, seed=11)
    smallcap = _index_frame(end, periods=300, start_close=12000.0, drift=0.0006, seed=12)
    z = compute_smallcap_rs_z(smallcap, broad, target_date=end)
    assert isinstance(z, float)
    assert not np.isnan(z)


def test_smallcap_rs_z_nan_when_missing_index() -> None:
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=300, start_close=20000.0, drift=0.0005, seed=11)
    empty = pd.DataFrame({"date": [], "close": []})
    assert np.isnan(compute_smallcap_rs_z(empty, broad, target_date=end))
    assert np.isnan(compute_smallcap_rs_z(broad, empty, target_date=end))


def test_smallcap_rs_z_negative_when_smallcap_underperforms() -> None:
    """Drive smallcap down vs broad — z-score at the tail should be negative."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.001, seed=21)
    # Smallcap recently slumps — synthesize a leg-down in the last 30 days.
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.001, seed=22)
    # Apply 30-day drawdown to smallcap close
    smallcap = smallcap.copy()
    n = len(smallcap)
    decay = np.ones(n)
    decay[-30:] = np.linspace(1.0, 0.80, 30)  # 20% slump over 30 days
    smallcap["close"] = smallcap["close"].to_numpy() * decay
    z = compute_smallcap_rs_z(smallcap, broad, target_date=end)
    assert z < 0


def test_vix_percentile_high_when_today_is_max() -> None:
    end = date(2026, 5, 22)
    dates = _bdate_range(end, 252)
    # Monotonically increasing VIX → today is the max → percentile ~1.0
    closes = np.linspace(10.0, 35.0, 252)
    vix = pd.DataFrame({"date": dates, "close": closes})
    pct, valid = compute_vix_percentile(vix, target_date=end)
    assert valid is True
    assert pct > 0.95


def test_vix_percentile_invalid_when_empty() -> None:
    end = date(2026, 5, 22)
    empty = pd.DataFrame({"date": [], "close": []})
    pct, valid = compute_vix_percentile(empty, target_date=end)
    assert valid is False
    assert np.isnan(pct)


def test_breadth_pct_above_200dma_in_unit_interval() -> None:
    end = date(2026, 5, 22)
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=30, seed=33)
    frac, n = compute_breadth_pct_above_200dma(ohlcv, target_date=end)
    assert 0.0 <= frac <= 1.0
    assert n > 0


def test_breadth_pct_falls_when_universe_drifts_down() -> None:
    """Universe with negative drift should have a low breadth %."""
    end = date(2026, 5, 22)
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=-0.002, seed=44)
    frac, _ = compute_breadth_pct_above_200dma(ohlcv, target_date=end)
    assert frac < 0.5


def test_cross_sectional_dispersion_is_nonnegative_float() -> None:
    end = date(2026, 5, 22)
    ohlcv = _universe_ohlcv(end, periods=60, n_instruments=40, seed=55)
    disp = compute_cross_sectional_dispersion(ohlcv, target_date=end)
    assert isinstance(disp, float)
    assert disp >= 0


def test_cross_sectional_dispersion_nan_when_no_universe() -> None:
    end = date(2026, 5, 22)
    empty = pd.DataFrame({"instrument_id": [], "date": [], "close": []})
    assert np.isnan(compute_cross_sectional_dispersion(empty, target_date=end))


# ---------------------------------------------------------------------------
# Threshold resolver
# ---------------------------------------------------------------------------


def _full_threshold_map() -> dict[str, Decimal]:
    """Map covering all 7 keys with non-default values."""
    return {
        "regime.smallcap_rs_z.below_trend_threshold": Decimal("-0.8"),
        "regime.smallcap_rs_z.risk_off_threshold": Decimal("-1.7"),
        "regime.breadth.below_trend_threshold": Decimal("0.45"),
        "regime.breadth.risk_off_threshold": Decimal("0.25"),
        "regime.vix_percentile.elevated_threshold": Decimal("0.65"),
        "regime.vix_percentile.risk_off_threshold": Decimal("0.85"),
        "regime.dispersion.elevated_threshold": Decimal("0.018"),
    }


def test_resolve_thresholds_uses_atlas_thresholds_when_complete() -> None:
    th, src = _resolve_thresholds(_full_threshold_map())
    assert src == "atlas_thresholds"
    assert th.smallcap_rs_z_risk_off == pytest.approx(-1.7)
    assert th.breadth_below_trend == pytest.approx(0.45)
    assert th.vix_pct_elevated == pytest.approx(0.65)


def test_resolve_thresholds_falls_back_when_partial() -> None:
    """A single missing key → fall back to defaults entirely (no mixing)."""
    full = _full_threshold_map()
    del full["regime.dispersion.elevated_threshold"]
    th, src = _resolve_thresholds(full)
    assert src == "fallback"
    assert th == RegimeThresholds()


def test_resolve_thresholds_falls_back_on_empty_or_none() -> None:
    th_empty, src_empty = _resolve_thresholds({})
    th_none, src_none = _resolve_thresholds(None)
    assert src_empty == "fallback"
    assert src_none == "fallback"
    assert th_empty == RegimeThresholds()
    assert th_none == RegimeThresholds()


# ---------------------------------------------------------------------------
# Full cron with mocked DB
# ---------------------------------------------------------------------------


def _patch_cron_io(
    *,
    smallcap: pd.DataFrame,
    broad: pd.DataFrame,
    vix: pd.DataFrame,
    ohlcv: pd.DataFrame,
    thresholds: dict[str, Decimal] | None = None,
    bulk_upsert_calls: list[dict[str, Any]] | None = None,
):
    """Context-manager-like helper returning the set of patchers to enter.

    Patches:
        - ``_load_index_close`` — routes by ``index_code`` to one of the 3 frames.
        - ``_load_universe_ohlcv`` — returns the canned long frame.
        - ``load_thresholds`` (re-exported into atlas.regime.cron) — returns
          the canned threshold map (default: empty → fallback).
        - ``bulk_upsert`` — records the call and returns rows-written.
    """
    if thresholds is None:
        thresholds = {}

    def _fake_load_index_close(_engine, *, index_code, start, end):  # type: ignore[no-untyped-def]
        if index_code == "NIFTY SMLCAP 250":
            return smallcap
        if index_code == "NIFTY 500":
            return broad
        if index_code == "INDIA VIX":
            return vix
        return pd.DataFrame({"date": [], "close": []})

    def _fake_load_universe_ohlcv(_engine, *, start, end):  # type: ignore[no-untyped-def]
        return ohlcv

    def _fake_load_thresholds(*args, **kwargs):  # type: ignore[no-untyped-def]
        return thresholds

    def _fake_bulk_upsert(_engine, *, table, columns, rows, pk_columns, **kwargs):  # type: ignore[no-untyped-def]
        if bulk_upsert_calls is not None:
            bulk_upsert_calls.append(
                {
                    "table": table,
                    "columns": list(columns),
                    "rows": list(rows),
                    "pk_columns": list(pk_columns),
                }
            )
        return len(rows)

    return [
        patch("atlas.regime.cron._load_index_close", side_effect=_fake_load_index_close),
        patch(
            "atlas.regime.cron._load_universe_ohlcv",
            side_effect=_fake_load_universe_ohlcv,
        ),
        patch("atlas.regime.cron.load_thresholds", side_effect=_fake_load_thresholds),
        patch("atlas.regime.cron.bulk_upsert", side_effect=_fake_bulk_upsert),
    ]


def _enter_all(patchers):  # type: ignore[no-untyped-def]
    for p in patchers:
        p.start()


def _exit_all(patchers):  # type: ignore[no-untyped-def]
    for p in reversed(patchers):
        p.stop()


def test_cron_risk_on_benign_scenario() -> None:
    """Benign synthetic data → Risk-On, 1 row written."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=101)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=102)
    # VIX is dropping steadily → today percentile is low
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(30.0, 12.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=0.001, seed=103)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap, broad=broad, vix=vix, ohlcv=ohlcv, bulk_upsert_calls=calls
    )
    _enter_all(patchers)
    try:
        result = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    assert result.state is RegimeState.RISK_ON
    assert result.rows_written == 1
    assert result.threshold_source == "fallback"
    assert result.vix_valid is True
    assert result.universe_size == 40
    assert result.breadth_eligible_count > 0
    # 1 bulk_upsert call, 1 row, correct table & pk
    assert len(calls) == 1
    assert calls[0]["table"] == "atlas.atlas_regime_daily"
    assert calls[0]["pk_columns"] == ["date"]
    assert len(calls[0]["rows"]) == 1
    row = calls[0]["rows"][0]
    # Row tuple: (date, state, smallcap_rs_z, breadth, vix_pct, dispersion)
    assert row[0] == end
    assert row[1] == "Risk-On"


def test_cron_risk_off_via_breadth_collapse() -> None:
    """Universe drifting down → breadth collapse → Risk-Off."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=201)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=202)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    # Universe with very negative drift → most stocks below 200d SMA
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=-0.004, seed=203)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap, broad=broad, vix=vix, ohlcv=ohlcv, bulk_upsert_calls=calls
    )
    _enter_all(patchers)
    try:
        result = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    assert result.state is RegimeState.RISK_OFF
    assert result.breadth_pct_above_200dma is not None
    assert result.breadth_pct_above_200dma < 0.40


def test_cron_insert_or_update_on_repeat_call() -> None:
    """Calling for the same target_date twice should still touch one row via UPSERT."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=301)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=302)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=0.001, seed=303)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap, broad=broad, vix=vix, ohlcv=ohlcv, bulk_upsert_calls=calls
    )
    _enter_all(patchers)
    try:
        result_1 = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
        result_2 = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    assert result_1.target_date == end
    assert result_2.target_date == end
    assert result_1.state == result_2.state  # deterministic on same inputs
    # Two upsert calls, but each writes exactly one row keyed on date —
    # ON CONFLICT(date) DO UPDATE semantics means one row in the table.
    assert len(calls) == 2
    assert len(calls[0]["rows"]) == 1
    assert len(calls[1]["rows"]) == 1
    assert calls[0]["pk_columns"] == calls[1]["pk_columns"] == ["date"]


def test_cron_vix_nan_path_propagates_vix_valid_false() -> None:
    """Empty VIX frame → vix_valid=False, regime still classifies cleanly."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=401)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=402)
    vix_empty = pd.DataFrame({"date": [], "close": []})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=0.001, seed=403)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap,
        broad=broad,
        vix=vix_empty,
        ohlcv=ohlcv,
        bulk_upsert_calls=calls,
    )
    _enter_all(patchers)
    try:
        result = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    assert result.vix_valid is False
    assert result.vix_percentile is None
    # Missing VIX did NOT silently force a non-Risk-On state — benign drivers → Risk-On.
    assert result.state is RegimeState.RISK_ON
    # Row written with NULL vix_percentile (Decimal/None → None at the boundary)
    row = calls[0]["rows"][0]
    assert row[4] is None  # vix_percentile slot


def test_cron_write_false_skips_db_write() -> None:
    """``write=False`` should skip the ``bulk_upsert`` call entirely."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=501)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=502)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=0.001, seed=503)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap, broad=broad, vix=vix, ohlcv=ohlcv, bulk_upsert_calls=calls
    )
    _enter_all(patchers)
    try:
        result = compute_daily_regime(
            target_date=end, db_engine=cast(Engine, MagicMock()), write=False
        )
    finally:
        _exit_all(patchers)

    assert result.state is not None
    assert result.rows_written == 0
    assert calls == []


def test_cron_uses_loaded_thresholds_when_complete() -> None:
    """Complete atlas_thresholds map → threshold_source='atlas_thresholds'."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=601)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=602)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=0.001, seed=603)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap,
        broad=broad,
        vix=vix,
        ohlcv=ohlcv,
        thresholds=_full_threshold_map(),
        bulk_upsert_calls=calls,
    )
    _enter_all(patchers)
    try:
        result = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    assert result.threshold_source == "atlas_thresholds"


def test_cron_threshold_load_failure_does_not_block_write() -> None:
    """If ``load_thresholds`` raises, we fall back to defaults and still write."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=701)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=702)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=40, drift=0.001, seed=703)

    def _fake_load_index_close(_engine, *, index_code, start, end):  # type: ignore[no-untyped-def]
        return {
            "NIFTY SMLCAP 250": smallcap,
            "NIFTY 500": broad,
            "INDIA VIX": vix,
        }.get(index_code, pd.DataFrame({"date": [], "close": []}))

    def _fake_load_universe_ohlcv(_engine, *, start, end):  # type: ignore[no-untyped-def]
        return ohlcv

    calls: list[dict[str, Any]] = []

    def _fake_bulk_upsert(_engine, *, table, columns, rows, pk_columns, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"table": table, "rows": list(rows)})
        return len(rows)

    with (
        patch("atlas.regime.cron._load_index_close", side_effect=_fake_load_index_close),
        patch(
            "atlas.regime.cron._load_universe_ohlcv",
            side_effect=_fake_load_universe_ohlcv,
        ),
        patch(
            "atlas.regime.cron.load_thresholds",
            side_effect=RuntimeError("simulated table missing"),
        ),
        patch("atlas.regime.cron.bulk_upsert", side_effect=_fake_bulk_upsert),
    ):
        result = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))

    assert result.threshold_source == "fallback"
    assert result.state is not None
    assert result.rows_written == 1


def test_cron_runtime_field_populated() -> None:
    """``runtime_seconds`` should be > 0 after a real (mocked) call."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=801)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=802)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=20, drift=0.001, seed=803)

    patchers = _patch_cron_io(
        smallcap=smallcap, broad=broad, vix=vix, ohlcv=ohlcv, bulk_upsert_calls=[]
    )
    _enter_all(patchers)
    try:
        result = compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    assert result.runtime_seconds >= 0.0


def test_cron_serialises_decimal_with_correct_precision() -> None:
    """Numeric columns serialise to Decimal with the schema's precision/scale."""
    end = date(2026, 5, 22)
    broad = _index_frame(end, periods=400, start_close=20000.0, drift=0.0008, seed=901)
    smallcap = _index_frame(end, periods=400, start_close=12000.0, drift=0.0008, seed=902)
    vix_dates = _bdate_range(end, 252)
    vix = pd.DataFrame({"date": vix_dates, "close": np.linspace(15.0, 14.0, 252)})
    ohlcv = _universe_ohlcv(end, periods=300, n_instruments=20, drift=0.001, seed=903)

    calls: list[dict[str, Any]] = []
    patchers = _patch_cron_io(
        smallcap=smallcap, broad=broad, vix=vix, ohlcv=ohlcv, bulk_upsert_calls=calls
    )
    _enter_all(patchers)
    try:
        compute_daily_regime(target_date=end, db_engine=cast(Engine, MagicMock()))
    finally:
        _exit_all(patchers)

    row = calls[0]["rows"][0]
    # smallcap_rs_z slot — Decimal(10,4)
    assert row[2] is None or isinstance(row[2], Decimal)
    # breadth — Decimal(6,4)
    assert row[3] is None or isinstance(row[3], Decimal)
    # dispersion — Decimal(10,6)
    assert row[5] is None or isinstance(row[5], Decimal)
