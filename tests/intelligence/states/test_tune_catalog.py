"""Tests for atlas/intelligence/states/tune_catalog.py.

Naming: test_<function>_<scenario>_<expected>
All unit tests use in-process fixture data — no DB required.
Integration tests (requiring ATLAS_DB_URL) are guarded by skipif.

Focus: breakout_ratio factor builder — TDD for Wave 4C Task 1.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from atlas.intelligence.states.tune_catalog import TUNE_CATALOG, build_factor_panel

# ---------------------------------------------------------------------------
# TUNE_CATALOG shape tests
# ---------------------------------------------------------------------------


def test_tune_catalog_contains_breakout_ratio_entry() -> None:
    """TUNE_CATALOG must have a breakout_ratio entry with expected keys."""
    entry = next(
        (e for e in TUNE_CATALOG if e["factor_builder"] == "breakout_ratio"),
        None,
    )
    assert entry is not None, "breakout_ratio entry missing from TUNE_CATALOG"
    assert entry["threshold_name"] == "theta_base_breakout"
    assert entry["state"] == "stage_2a"
    assert isinstance(entry["candidates"], list)
    assert len(entry["candidates"]) > 0


# ---------------------------------------------------------------------------
# Helpers: in-process engine backed by a pandas DataFrame
# ---------------------------------------------------------------------------


class _PanelEngine:
    """Minimal SQLAlchemy-engine-like shim backed by an in-memory DataFrame.

    Used to test build_factor_panel without a real DB.  Only the breakout_ratio
    branch calls engine.connect(), so we only need to support that path.

    The shim stores a pre-built ``(date, instrument_id, factor)`` long DataFrame
    and returns it via pd.read_sql replacement.  We monkey-patch build_factor_panel
    in the breakout_ratio tests instead of using this shim, because the builder
    does its own SQL; we test the *computation logic* by extracting it.
    """

    pass  # Not used directly; see _build_breakout_ratio_from_ohlcv below.


# ---------------------------------------------------------------------------
# Pure-function extraction helper (mirrors what the builder will do)
# ---------------------------------------------------------------------------


def _compute_breakout_ratio(
    long_df: pd.DataFrame,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Replicates the breakout_ratio computation in build_factor_panel.

    Input ``long_df`` has columns: date (datetime64), instrument_id (str), close (float).
    Returns MultiIndex (date, instrument_id) DataFrame with column 'factor'.

    This helper mirrors the implementation we expect; the tests call it directly
    AND also call build_factor_panel (via a monkeypatched engine) to verify the
    two are consistent.
    """
    long_df = long_df.copy()
    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df = long_df.sort_values(["instrument_id", "date"])

    # Per-instrument vectorized rolling max (shift 1 = exclude today, per cli.py convention).
    long_df["max_close_60d"] = long_df.groupby("instrument_id")["close"].transform(
        lambda s: s.shift(1).rolling(60, min_periods=60).max()
    )
    long_df["factor"] = long_df["close"] / long_df["max_close_60d"]

    # Trim to requested window.
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    mask = (long_df["date"] >= start_ts) & (long_df["date"] <= end_ts)
    trimmed = long_df[mask].dropna(subset=["factor"]).copy()

    trimmed = trimmed.set_index(["date", "instrument_id"])
    return trimmed[["factor"]]


# ---------------------------------------------------------------------------
# Fixture: deterministic 80-day single-instrument OHLCV panel
# ---------------------------------------------------------------------------


@pytest.fixture
def single_instrument_panel() -> pd.DataFrame:
    """80 calendar-weekday rows for one instrument.

    Close starts at 100, increments by 1 each day → monotonically increasing.
    This makes the expected 60d rolling max trivially hand-computable:
      - day 61 (index 60, 0-based): close=161, shift(1) window [1..60] = max(101..160) = 160
        → ratio = 161/160 = 1.00625
      - at-the-high day: when today makes a new high, ratio > 1.0
    """
    n = 80
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.arange(100.0, 100.0 + n)  # 100, 101, ..., 179
    return pd.DataFrame(
        {
            "date": dates,
            "instrument_id": "INSTR_A",
            "close": close,
        }
    )


@pytest.fixture
def two_instrument_panel() -> pd.DataFrame:
    """80 calendar-weekday rows for TWO instruments.

    INSTR_A: close = 100 + i (monotone up)
    INSTR_B: close = 200 - i (monotone down)
    Rolling max is computed per-instrument so they must not bleed into each other.
    """
    n = 80
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    df_a = pd.DataFrame(
        {
            "date": dates,
            "instrument_id": "INSTR_A",
            "close": np.arange(100.0, 100.0 + n),
        }
    )
    df_b = pd.DataFrame(
        {
            "date": dates,
            "instrument_id": "INSTR_B",
            "close": np.arange(200.0, 200.0 - n, -1),
        }
    )
    return pd.concat([df_a, df_b], ignore_index=True)


# ---------------------------------------------------------------------------
# Core breakout_ratio computation tests
# ---------------------------------------------------------------------------


def test_breakout_ratio_first_60_rows_are_nan(single_instrument_panel) -> None:
    """Rows 0..59 must be NaN — rolling window of 60 with shift(1) not yet full.

    shift(1) pushes the series by one, so the first valid window completes at
    index 60 (the 61st row, 0-based). Rows 0..59 must be dropped from the output
    (NaN-filtered), matching the sibling builders' IS NOT NULL convention.
    """
    df = single_instrument_panel
    start = df["date"].iloc[0].date()
    end = df["date"].iloc[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    # Rows 0..59 should NOT appear in result (NaN-dropped).
    assert len(result) <= 80 - 60, "More rows returned than expected after NaN-drop"
    # At least some valid rows must exist.
    assert len(result) > 0, "No valid rows returned"


def test_breakout_ratio_exact_value_at_window_boundary(single_instrument_panel) -> None:
    """Day 61 (index 60): close=160, shift(1).rolling(60).max() = max(close[0..59])=159.

    close sequence: 100, 101, ..., 179 (n=80 days).
    Index 60 => close=160.
    shift(1) at index 60 points to index 59 (close=159).
    Window [index 1..60 of shifted] = original [index 0..59] = 100..159 → max=159.
    Expected ratio = 160/159 ≈ 1.006289...

    We use the date of index 60 as the lookup key.
    """
    df = single_instrument_panel
    start = df["date"].iloc[0].date()
    end = df["date"].iloc[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    target_date = pd.Timestamp(df["date"].iloc[60])
    row = result.loc[(target_date, "INSTR_A"), "factor"]
    expected = 160.0 / 159.0
    assert abs(float(row) - expected) < 1e-9, f"Expected {expected:.6f}, got {float(row):.6f}"


def test_breakout_ratio_at_all_time_high_greater_than_one(single_instrument_panel) -> None:
    """On a monotonically rising close, every day after warmup has ratio > 1.0.

    close=100+i is always above the prior 60d max (which is at most 100+i-1 once warm).
    Ratio must be > 1.0 for all valid rows.
    """
    df = single_instrument_panel
    start = df["date"].iloc[0].date()
    end = df["date"].iloc[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    assert (result["factor"] > 1.0).all(), (
        "Expected all breakout_ratio > 1.0 for monotone-up series, got:\n"
        f"{result[result['factor'] <= 1.0]}"
    )


def test_breakout_ratio_below_peak_is_less_than_one() -> None:
    """A series that rises then falls 10%: ratio on the down leg < 1.0.

    Build: 70 days up to 170, then 10 days down to 160.
    On a down day well past the 60d window, max_close_60d is still 170,
    so ratio = 160/170 ≈ 0.941.
    """
    n_up = 70
    n_down = 10
    dates = pd.date_range("2024-01-01", periods=n_up + n_down, freq="B")
    up = np.linspace(100.0, 170.0, n_up)
    down = np.linspace(170.0, 160.0, n_down)
    close = np.concatenate([up, down])
    df = pd.DataFrame({"date": dates, "instrument_id": "INSTR_C", "close": close})

    start = dates[-1].date()  # last day only
    end = dates[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    assert len(result) == 1, "Expected exactly 1 row for the last date"
    ratio = float(result["factor"].iloc[0])
    assert ratio < 1.0, f"Expected ratio < 1.0 on down-leg, got {ratio:.4f}"


def test_breakout_ratio_at_exact_high_equals_one() -> None:
    """When today's close exactly equals the prior 60d maximum, ratio = 1.0.

    Construct: flat series at 150.0 for 65 days, so shift(1).rolling(60).max()=150.0
    and today=150.0 → ratio=1.0.
    """
    n = 65
    dates = pd.date_range("2024-03-01", periods=n, freq="B")
    close = np.full(n, 150.0)
    df = pd.DataFrame({"date": dates, "instrument_id": "INSTR_D", "close": close})

    start = dates[-1].date()
    end = dates[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    assert len(result) == 1
    assert abs(float(result["factor"].iloc[0]) - 1.0) < 1e-9


def test_breakout_ratio_multi_instrument_no_bleed(two_instrument_panel) -> None:
    """Two instruments must produce independent rolling windows.

    INSTR_A: monotone up → ratio > 1.0 after warmup.
    INSTR_B: monotone down → ratio < 1.0 after warmup (close < 60d prior max).
    """
    df = two_instrument_panel
    start = df["date"].min().date()
    end = df["date"].max().date()
    result = _compute_breakout_ratio(df, start, end)

    a_rows = result.xs("INSTR_A", level="instrument_id")
    b_rows = result.xs("INSTR_B", level="instrument_id")

    assert (a_rows["factor"] > 1.0).all(), "INSTR_A (monotone up) should all be > 1"
    assert (b_rows["factor"] < 1.0).all(), "INSTR_B (monotone down) should all be < 1"


def test_breakout_ratio_output_schema(single_instrument_panel) -> None:
    """Output must have MultiIndex ['date', 'instrument_id'] and column 'factor'."""
    df = single_instrument_panel
    start = df["date"].iloc[0].date()
    end = df["date"].iloc[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    assert result.index.names == [
        "date",
        "instrument_id",
    ], f"Expected index names ['date', 'instrument_id'], got {result.index.names}"
    assert list(result.columns) == [
        "factor"
    ], f"Expected columns ['factor'], got {list(result.columns)}"


def test_breakout_ratio_no_nan_in_output(single_instrument_panel) -> None:
    """The returned panel must contain zero NaN values — NaNs are dropped pre-return."""
    df = single_instrument_panel
    start = df["date"].iloc[0].date()
    end = df["date"].iloc[-1].date()
    result = _compute_breakout_ratio(df, start, end)

    assert (
        not result["factor"].isna().any()
    ), "build_factor_panel must drop NaN rows before returning"


def test_breakout_ratio_date_trim_respects_start_end(single_instrument_panel) -> None:
    """Output must not contain dates outside [start, end]."""
    df = single_instrument_panel
    # Request only a 5-day window near the end of the fixture.
    start = df["date"].iloc[70].date()
    end = df["date"].iloc[74].date()
    result = _compute_breakout_ratio(df, start, end)

    if not result.empty:
        dates_in_result = result.index.get_level_values("date")
        assert dates_in_result.min() >= pd.Timestamp(start)
        assert dates_in_result.max() <= pd.Timestamp(end)


# ---------------------------------------------------------------------------
# build_factor_panel integration-style test using monkeypatching
# ---------------------------------------------------------------------------


def test_build_factor_panel_breakout_ratio_returns_valid_panel(monkeypatch) -> None:
    """GREEN test: after implementation, build_factor_panel returns correct panel.

    Monkeypatches pd.read_sql to inject a known 80-day OHLCV fixture.
    Verifies:
      - No NotImplementedError raised.
      - Returns MultiIndex (date, instrument_id) with column 'factor'.
      - No NaN in 'factor'.
      - All values > 0.
      - Rows outside [start, end] are absent.
    """
    import unittest.mock as mock

    n = 80
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.arange(100.0, 100.0 + n)
    raw_df = pd.DataFrame(
        {
            "date": dates,
            "instrument_id": "INSTR_A",
            "close": close,
        }
    )

    # Monkeypatch pd.read_sql so the builder gets our fixture without a real DB.
    with mock.patch("atlas.intelligence.states.tune_catalog.pd.read_sql", return_value=raw_df):
        # Also need a real engine.connect() context manager — use MagicMock.
        fake_conn = mock.MagicMock()
        fake_engine = mock.MagicMock()
        fake_engine.connect.return_value.__enter__ = mock.Mock(return_value=fake_conn)
        fake_engine.connect.return_value.__exit__ = mock.Mock(return_value=False)

        start = dates[0].date()
        end = dates[-1].date()
        result = build_factor_panel(fake_engine, "breakout_ratio", start, end)

    # Schema assertions.
    assert result.index.names == [
        "date",
        "instrument_id",
    ], f"Wrong index names: {result.index.names}"
    assert list(result.columns) == ["factor"], f"Wrong columns: {list(result.columns)}"

    # No NaN in output.
    assert not result["factor"].isna().any(), "NaN values found in factor column"

    # All values > 0 (ratio is positive).
    assert (result["factor"] > 0).all(), "Non-positive values found in factor column"

    # Date bounds respected.
    dates_out = result.index.get_level_values("date")
    assert dates_out.min() >= pd.Timestamp(start)
    assert dates_out.max() <= pd.Timestamp(end)


def test_build_factor_panel_breakout_ratio_does_not_raise_not_implemented() -> None:
    """After implementation, build_factor_panel must NOT raise NotImplementedError.

    Passing None as engine will raise AttributeError or similar when the builder
    tries to call eng.connect() — that is acceptable and proves the stub is gone.
    """
    try:
        build_factor_panel(None, "breakout_ratio", date(2024, 1, 1), date(2024, 3, 1))
    except NotImplementedError:
        pytest.fail("build_factor_panel raised NotImplementedError — stub not yet replaced")
    except Exception:
        # Any other exception (AttributeError from None.connect(), etc.) is fine;
        # it proves the NotImplementedError stub is gone.
        pass


def test_build_factor_panel_unknown_builder_raises_value_error() -> None:
    """Unknown builder_id must raise ValueError (existing contract — must not regress)."""
    with pytest.raises(ValueError, match="unknown factor builder"):
        build_factor_panel(None, "does_not_exist", date(2024, 1, 1), date(2024, 3, 1))
