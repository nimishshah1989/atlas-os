"""Smoke tests for `atlas-lab states classify`.

Unit tests run without a live DB. Integration test requires ATLAS_INTEGRATION_TESTS=1
and a live DB with atlas.atlas_stock_state_daily (migration 072 applied).
"""

from __future__ import annotations

import argparse
import os

import pandas as pd
import pytest

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


# ---------------------------------------------------------------------------
# Unit tests (no DB required)
# ---------------------------------------------------------------------------


def test_compute_features_for_stock_columns():
    """_compute_features_for_stock returns all required feature columns."""
    from atlas.trading.cli import _compute_features_for_stock

    n = 300  # enough rows to fill SMA-200 window
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    g = pd.DataFrame(
        {
            "instrument_id": "TEST",
            "date": dates,
            "close": 100.0 + pd.Series(range(n)) * 0.1,
            "high": 101.0 + pd.Series(range(n)) * 0.1,
            "low": 99.0 + pd.Series(range(n)) * 0.1,
            "volume": 1_000_000.0,
        }
    )
    out = _compute_features_for_stock(g)

    required_cols = [
        "instrument_id",
        "date",
        "close",
        "sma_50",
        "sma_150",
        "sma_200",
        "sma_50_slope",
        "sma_150_slope",
        "sma_200_slope",
        "atr_14",
        "atr_14_50d_avg",
        "volume",
        "volume_50d_avg",
        "max_close_60d",
        "distribution_days_25d",
        "distribution_days_5d",
        "ret_12m_raw",
        "low_252_age_days",
        "liquidity_score",
        "data_gap_count",
    ]
    missing = [c for c in required_cols if c not in out.columns]
    assert not missing, f"Missing feature columns: {missing}"
    assert len(out) == n


def test_compute_features_for_stock_sma200_nan_before_warmup():
    """SMA-200 is NaN for the first 199 rows (warm-up not yet full)."""
    from atlas.trading.cli import _compute_features_for_stock

    n = 250
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    g = pd.DataFrame(
        {
            "instrument_id": "TEST",
            "date": dates,
            "close": 100.0 + pd.Series(range(n)) * 0.05,
            "high": 101.0 + pd.Series(range(n)) * 0.05,
            "low": 99.0 + pd.Series(range(n)) * 0.05,
            "volume": 500_000.0,
        }
    )
    out = _compute_features_for_stock(g)
    assert bool(out["sma_200"].iloc[:199].isna().all()), "SMA-200 should be NaN before row 200"
    assert not pd.isna(out["sma_200"].iloc[199]), "SMA-200 should be valid at row 200"


def test_compute_features_for_stock_no_volume_column():
    """Falls back gracefully when volume column is absent (e.g., ETF path)."""
    from atlas.trading.cli import _compute_features_for_stock

    n = 60
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    g = pd.DataFrame(
        {
            "instrument_id": "TEST",
            "date": dates,
            "close": 100.0 + pd.Series(range(n)) * 0.1,
            "high": 101.0 + pd.Series(range(n)) * 0.1,
            "low": 99.0 + pd.Series(range(n)) * 0.1,
            # no volume column
        }
    )
    out = _compute_features_for_stock(g)
    assert "volume" in out.columns
    assert bool(out["volume"].isna().all()), "volume should be all-NaN when absent from input"


def test_states_classify_cmd_missing_db_url(monkeypatch):
    """_states_classify_cmd raises SystemExit when ATLAS_DB_URL is not set."""
    from atlas.trading.cli import _states_classify_cmd

    monkeypatch.delenv("ATLAS_DB_URL", raising=False)
    args = argparse.Namespace(
        start="2024-06-03",
        end="2024-06-07",
        universe="stocks_nifty500",
        classifier_version="v1.0",
    )
    with pytest.raises(SystemExit):
        _states_classify_cmd(args)


def test_states_tune_cmd_missing_db_url(monkeypatch):
    """_states_tune_cmd raises SystemExit when ATLAS_DB_URL is not set."""
    from atlas.trading.cli_states import _states_tune_cmd

    monkeypatch.delenv("ATLAS_DB_URL", raising=False)
    args = argparse.Namespace(
        start="2024-09-01",
        end="2024-10-31",
        as_of=None,
        dry_run=True,
        format="text",
    )
    with pytest.raises(SystemExit):
        _states_tune_cmd(args)


def test_states_tune_help():
    """CLI help text for 'states tune' includes expected arguments."""
    import subprocess
    import sys

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "atlas.trading.cli", "states", "tune", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "ATLAS_DB_URL": "postgresql://placeholder"},
    )
    assert result.returncode == 0
    assert "--start" in result.stdout
    assert "--end" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--as-of" in result.stdout
    assert "--format" in result.stdout


def test_states_classify_help():
    """CLI help text includes 'states' and 'classify' subcommands."""
    import subprocess
    import sys

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "atlas.trading.cli", "states", "classify", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "ATLAS_DB_URL": "postgresql://placeholder"},
    )
    assert result.returncode == 0
    assert "--start" in result.stdout
    assert "--end" in result.stdout
    assert "--universe" in result.stdout
    assert "--classifier-version" in result.stdout


# ---------------------------------------------------------------------------
# Unit tests for _apply_dwell_and_urgency vectorized path (no DB required)
# ---------------------------------------------------------------------------


def _build_synthetic_panel():  # type: ignore[return]
    """Minimal DataFrames matching the DB schema for dwell/urgency tests."""
    from datetime import date

    d0 = date(2026, 1, 5)
    meta = pd.DataFrame(
        {
            "instrument_id": ["A", "B", "C"],
            "in_nifty_100": [True, False, False],
            "in_nifty_500": [True, True, False],
            "sector": ["financials", "it", "energy"],
        }
    )
    baselines = pd.DataFrame(
        {
            "cohort_key": ["large_cap", "mid_cap", "small_cap"],
            "state": ["Stage2", "Stage2", "Stage2"],
            "median_dwell_days": [30, 25, 20],
            "p25_dwell_days": [10, 8, 6],
            "p75_dwell_days": [50, 40, 35],
            "p95_dwell_days": [80, 70, 60],
        }
    )
    vol_df = pd.DataFrame(
        {
            "instrument_id": ["A", "B", "C"],
            "date": [d0, d0, d0],
            "realized_vol_63": [0.20, 0.25, 0.30],
        }
    )
    panel = pd.DataFrame(
        {
            "instrument_id": ["A", "B", "C"],
            "date": [d0, d0, d0],
            "state": ["Stage2", "Stage2", "Stage2"],
            "dwell_days": [45, 20, 10],
            "rs_rank_12m": [0.8, 0.6, None],
            "dwell_percentile": [None, None, None],
            "urgency_score": ["n/a", "n/a", "n/a"],
            "within_state_rank": [None, None, None],
        }
    )
    return panel, baselines, meta, vol_df


def _make_mock_eng(baselines, meta, vol_df):  # type: ignore[return]
    """MagicMock engine whose pd.read_sql returns supplied frames in order."""
    from unittest.mock import MagicMock

    call_idx: dict[str, int] = {"n": 0}
    returns = [baselines, meta, vol_df]

    def _fake_sql(_q, _c, **_kw):  # type: ignore[return]
        r = returns[call_idx["n"]]
        call_idx["n"] += 1
        return r

    conn = MagicMock()
    conn.__enter__ = lambda s: conn
    conn.__exit__ = MagicMock(return_value=False)
    eng = MagicMock()
    eng.connect.return_value = conn
    return eng, _fake_sql


def test_apply_dwell_vectorized_dwell_percentile():
    """dwell_percentile is computed correctly by the vectorized path."""
    from unittest.mock import patch

    panel, baselines, meta, vol_df = _build_synthetic_panel()
    eng, fake_sql = _make_mock_eng(baselines, meta, vol_df)
    # A: large_cap Stage2, p25=10, p95=80, dwell=45 -> (45-10)/70 = 0.5
    expected_a = round(35 / 70, 4)

    with patch("pandas.read_sql", side_effect=fake_sql):
        from atlas.trading.cli_states import _apply_dwell_and_urgency

        out = _apply_dwell_and_urgency(panel, eng)

    row_a = out.loc[out["instrument_id"] == "A"].iloc[0]
    assert abs(float(row_a["dwell_percentile"]) - expected_a) < 1e-4


def test_apply_dwell_vectorized_within_rank():
    """within_state_rank = 0.4*fresh + 0.3*rs + 0.3*vol_rank holds numerically."""
    from unittest.mock import patch

    panel, baselines, meta, vol_df = _build_synthetic_panel()
    eng, fake_sql = _make_mock_eng(baselines, meta, vol_df)

    with patch("pandas.read_sql", side_effect=fake_sql):
        from atlas.trading.cli_states import _apply_dwell_and_urgency

        out = _apply_dwell_and_urgency(panel, eng)

    # A: dp=0.5, fresh=0.5, rs=0.8, vol_rank=1/3 (lowest vol -> rank pct 1/3)
    row_a = out.loc[out["instrument_id"] == "A"].iloc[0]
    dp_a = float(row_a["dwell_percentile"])
    expected = round(0.4 * (1.0 - dp_a) + 0.3 * 0.8 + 0.3 * (1 / 3), 4)
    assert abs(float(row_a["within_state_rank"]) - expected) < 1e-3


def test_apply_dwell_vectorized_no_meta():
    """Instrument absent from meta -> urgency='n/a', numeric cols None/NaN."""
    from datetime import date
    from unittest.mock import patch

    d0 = date(2026, 1, 5)
    panel = pd.DataFrame(
        {
            "instrument_id": ["UNKNOWN"],
            "date": [d0],
            "state": ["Stage2"],
            "dwell_days": [20],
            "rs_rank_12m": [0.5],
            "dwell_percentile": [None],
            "urgency_score": ["n/a"],
            "within_state_rank": [None],
        }
    )
    _meta_cols: list[str] = ["instrument_id", "in_nifty_100", "in_nifty_500", "sector"]
    empty_meta = pd.DataFrame({"_": pd.Series([], dtype=str)}).drop(columns=["_"])
    empty_meta = empty_meta.reindex(columns=_meta_cols)
    _bl_cols: list[str] = [
        "cohort_key",
        "state",
        "median_dwell_days",
        "p25_dwell_days",
        "p75_dwell_days",
        "p95_dwell_days",
    ]
    empty_bl = pd.DataFrame({"_": pd.Series([], dtype=str)}).drop(columns=["_"])
    empty_bl = empty_bl.reindex(columns=_bl_cols)
    _vol_cols: list[str] = ["instrument_id", "date", "realized_vol_63"]
    empty_vol = pd.DataFrame({"_": pd.Series([], dtype=str)}).drop(columns=["_"])
    empty_vol = empty_vol.reindex(columns=_vol_cols)
    eng, fake_sql = _make_mock_eng(empty_bl, empty_meta, empty_vol)

    with patch("pandas.read_sql", side_effect=fake_sql):
        from atlas.trading.cli_states import _apply_dwell_and_urgency

        out = _apply_dwell_and_urgency(panel, eng)

    row = out.iloc[0]
    assert row["urgency_score"] == "n/a"
    assert row["dwell_percentile"] is None or bool(pd.isna(row["dwell_percentile"]))
    assert row["within_state_rank"] is None or bool(pd.isna(row["within_state_rank"]))


def test_apply_dwell_vectorized_return_shape():
    """Output has three patched columns; no helper columns leak into the result."""
    from unittest.mock import patch

    panel, baselines, meta, vol_df = _build_synthetic_panel()
    eng, fake_sql = _make_mock_eng(baselines, meta, vol_df)

    with patch("pandas.read_sql", side_effect=fake_sql):
        from atlas.trading.cli_states import _apply_dwell_and_urgency

        out = _apply_dwell_and_urgency(panel, eng)

    for col in ("dwell_percentile", "urgency_score", "within_state_rank"):
        assert col in out.columns, f"Missing patched column: {col}"

    leaked = [
        c
        for c in out.columns
        if c.startswith("_") or c in ("in_nifty_100", "in_nifty_500", "sector", "cohort_key")
    ]
    assert not leaked, f"Helper columns leaked into output: {leaked}"
    assert len(out) == len(panel)


# ---------------------------------------------------------------------------
# Integration test (live DB required)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_states_classify_writes_rows():
    """End-to-end smoke: CLI classifies a 1-week window for stocks and writes rows."""
    from sqlalchemy import create_engine, text

    from atlas.trading.cli import _states_classify_cmd

    args = argparse.Namespace(
        start="2024-06-03",
        end="2024-06-07",
        universe="stocks_nifty500",
        classifier_version="v1.0-smoke",
    )
    rc = _states_classify_cmd(args)
    assert rc == 0, "Expected return code 0 from _states_classify_cmd"

    # Verify rows were written.
    db_url = (
        os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    )
    eng = create_engine(db_url)
    with eng.connect() as c:
        n = c.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_stock_state_daily"
                " WHERE classifier_version = 'v1.0-smoke'"
            )
        ).scalar()
    assert n is not None and n > 0, f"Expected some rows for v1.0-smoke, got {n}"

    # Cleanup so re-runs are idempotent on the test table.
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_stock_state_daily WHERE classifier_version = 'v1.0-smoke'"
            )
        )


@_SKIP_INTEGRATION
def test_baselines_refresh_writes_rows():
    """`states baselines-refresh` reads classified rows + writes dwell stats."""
    from sqlalchemy import create_engine, text

    from atlas.trading.cli import _states_classify_cmd
    from atlas.trading.cli_states import _states_baselines_refresh_cmd

    db_url = (
        os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    )
    eng = create_engine(db_url)

    # Seed some classified rows; baselines-refresh reads from atlas_stock_state_daily.
    classify_args = argparse.Namespace(
        start="2024-06-03",
        end="2024-06-07",
        universe="stocks_nifty500",
        classifier_version="v1.0-baselines-test",
    )
    rc = _states_classify_cmd(classify_args)
    assert rc == 0, "classify must succeed before baselines-refresh"

    try:
        refresh_args = argparse.Namespace()
        rc = _states_baselines_refresh_cmd(refresh_args)
        assert rc == 0, "baselines-refresh should return 0"

        with eng.connect() as c:
            n = c.execute(
                text(
                    "SELECT COUNT(*) FROM atlas.atlas_state_dwell_statistics"
                    " WHERE as_of_date = CURRENT_DATE"
                )
            ).scalar()
        assert n is not None and n > 0, f"Expected baselines rows for today, got {n}"
    finally:
        with eng.begin() as c:
            c.execute(
                text(
                    "DELETE FROM atlas.atlas_stock_state_daily"
                    " WHERE classifier_version = 'v1.0-baselines-test'"
                )
            )


@_SKIP_INTEGRATION
def test_classify_with_real_urgency():
    """After classify with cohort baselines present, urgency_score has real categories."""
    from sqlalchemy import create_engine, text

    from atlas.trading.cli import _states_classify_cmd

    db_url = (
        os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    )
    eng = create_engine(db_url)

    args = argparse.Namespace(
        start="2024-06-03",
        end="2024-06-07",
        universe="stocks_nifty500",
        classifier_version="v1.0-urgency-test",
    )
    rc = _states_classify_cmd(args)
    assert rc == 0

    try:
        with eng.connect() as c:
            rows = c.execute(
                text("""
                    SELECT urgency_score, COUNT(*) AS n
                    FROM atlas.atlas_stock_state_daily
                    WHERE classifier_version = 'v1.0-urgency-test'
                    GROUP BY urgency_score
                """)
            ).fetchall()
        urgencies = {r.urgency_score for r in rows}
        # At minimum some urgency category must be present.
        # 'n/a' is guaranteed for Stage 1 / 4 / uninvestable.
        assert len(urgencies) > 0, "Expected at least one urgency category"
        assert "n/a" in urgencies, "Expected 'n/a' for uninvestable/Stage1/Stage4 rows"
    finally:
        with eng.begin() as c:
            c.execute(
                text(
                    "DELETE FROM atlas.atlas_stock_state_daily"
                    " WHERE classifier_version = 'v1.0-urgency-test'"
                )
            )


@_SKIP_INTEGRATION
def test_states_tune_dry_run():
    """`states tune --dry-run` computes IC across catalog without persisting thresholds."""
    from sqlalchemy import create_engine, text

    from atlas.trading.cli import _states_classify_cmd
    from atlas.trading.cli_states import _states_tune_cmd

    # Seed classified rows so the factor panels have data to pull.
    classify_args = argparse.Namespace(
        start="2024-09-01",
        end="2024-10-31",
        universe="stocks_nifty500",
        classifier_version="v1.0-tune-test",
    )
    rc = _states_classify_cmd(classify_args)
    assert rc == 0, "classify must succeed before tune"

    db_url = (
        os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    )
    try:
        tune_args = argparse.Namespace(
            start="2024-09-01",
            end="2024-10-31",
            as_of="2024-10-31",
            dry_run=True,
            format="text",
        )
        rc = _states_tune_cmd(tune_args)
        assert rc == 0, "states tune --dry-run should return 0"

        # Dry-run must NOT have written any threshold rows for this as_of date.
        eng = create_engine(db_url)
        with eng.connect() as c:
            n = c.execute(
                text(
                    "SELECT COUNT(*) FROM atlas.atlas_state_thresholds"
                    " WHERE as_of_date = '2024-10-31'"
                )
            ).scalar()
        assert n == 0, f"dry-run should not persist threshold rows; got {n}"
    finally:
        with create_engine(db_url).begin() as c:
            c.execute(
                text(
                    "DELETE FROM atlas.atlas_stock_state_daily"
                    " WHERE classifier_version = 'v1.0-tune-test'"
                )
            )
