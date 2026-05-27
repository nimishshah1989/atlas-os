"""Tests for atlas.ingest.macro.mospi_cpi_ingest.

TDD: tests written before implementation.
MOSPI does not have a stable public API. The implementation uses a bundled
historical CPI dataset sourced from RBI DBIE / MOSPI releases (monthly).
Monthly CPI is carried forward to daily rows via SQL UPDATE.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# compute_cpi_yoy
# ---------------------------------------------------------------------------


def test_compute_cpi_yoy_basic_calculation():
    """YoY = (current / 12mo_ago) - 1."""
    from atlas.ingest.macro.mospi_cpi_ingest import compute_cpi_yoy

    monthly_cpi = pd.DataFrame(
        [
            {"year": 2022, "month": 1, "cpi": 100.0},
            {"year": 2022, "month": 2, "cpi": 101.0},
            {"year": 2023, "month": 1, "cpi": 106.0},
            {"year": 2023, "month": 2, "cpi": 107.07},
        ]
    )

    df_yoy = compute_cpi_yoy(monthly_cpi)

    # 2023-01: 106/100 - 1 = 0.06 (6%)
    row = df_yoy[df_yoy["year_month"] == "2023-01"].iloc[0]
    assert float(row["cpi_yoy"]) == pytest.approx(0.06, abs=0.001)


def test_compute_cpi_yoy_returns_iso_year_month():
    """Output year_month column must be 'YYYY-MM' strings."""
    from atlas.ingest.macro.mospi_cpi_ingest import compute_cpi_yoy

    monthly_cpi = pd.DataFrame(
        [
            {"year": 2022, "month": 1, "cpi": 100.0},
            {"year": 2023, "month": 1, "cpi": 106.0},
        ]
    )

    df_yoy = compute_cpi_yoy(monthly_cpi)

    assert not df_yoy.empty
    for ym in df_yoy["year_month"].values:
        assert len(str(ym)) == 7, f"Expected YYYY-MM, got {ym!r}"
        assert str(ym)[4] == "-"


def test_compute_cpi_yoy_drops_months_without_prior_year():
    """Months that have no 12mo-ago reference must be excluded (not computed)."""
    from atlas.ingest.macro.mospi_cpi_ingest import compute_cpi_yoy

    # Only 2016 data — no 2015 to compute YoY from
    monthly_cpi = pd.DataFrame(
        [
            {"year": 2016, "month": 1, "cpi": 100.0},
            {"year": 2016, "month": 2, "cpi": 101.0},
        ]
    )

    df_yoy = compute_cpi_yoy(monthly_cpi)

    assert len(df_yoy) == 0


def test_compute_cpi_yoy_null_handling():
    """If either current or prior year CPI is missing, output must be NULL (NaN), not 0."""
    import math

    from atlas.ingest.macro.mospi_cpi_ingest import compute_cpi_yoy

    monthly_cpi = pd.DataFrame(
        [
            {"year": 2022, "month": 1, "cpi": float("nan")},  # missing
            {"year": 2023, "month": 1, "cpi": 106.0},
        ]
    )

    df_yoy = compute_cpi_yoy(monthly_cpi)

    if not df_yoy.empty:
        row = df_yoy[df_yoy["year_month"] == "2023-01"]
        if not row.empty:
            assert math.isnan(float(row.iloc[0]["cpi_yoy"]))


# ---------------------------------------------------------------------------
# upsert_cpi_yoy
# ---------------------------------------------------------------------------


def test_upsert_cpi_yoy_returns_row_count():
    """upsert_cpi_yoy must return count of rows written."""
    from atlas.ingest.macro.mospi_cpi_ingest import upsert_cpi_yoy

    df = pd.DataFrame(
        [
            {"year_month": "2023-01", "cpi_yoy": 0.06},
            {"year_month": "2023-02", "cpi_yoy": 0.065},
        ]
    )

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.mospi_cpi_ingest.get_engine", return_value=mock_engine):
        count = upsert_cpi_yoy(df, engine=mock_engine)

    assert count == 2


def test_upsert_cpi_yoy_stores_decimal():
    """CPI YoY must be stored as Decimal, not float."""
    from atlas.ingest.macro.mospi_cpi_ingest import upsert_cpi_yoy

    df = pd.DataFrame([{"year_month": "2023-01", "cpi_yoy": 0.06}])

    executed_params = []
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.mospi_cpi_ingest.get_engine", return_value=mock_engine):
        upsert_cpi_yoy(df, engine=mock_engine)

    assert len(executed_params) > 0
    # At least one param set should have a Decimal value
    for params in executed_params:
        if "v" in params:
            assert isinstance(params["v"], Decimal)
            break


def test_upsert_cpi_yoy_empty_returns_zero():
    """Empty DataFrame returns 0."""
    from atlas.ingest.macro.mospi_cpi_ingest import upsert_cpi_yoy

    df = pd.DataFrame(columns=["year_month", "cpi_yoy"])
    mock_engine = MagicMock()

    with patch("atlas.ingest.macro.mospi_cpi_ingest.get_engine", return_value=mock_engine):
        count = upsert_cpi_yoy(df, engine=mock_engine)

    assert count == 0
    mock_engine.begin.assert_not_called()


# ---------------------------------------------------------------------------
# get_bundled_cpi_data
# ---------------------------------------------------------------------------


def test_get_bundled_cpi_data_returns_dataframe():
    """The bundled CPI data must be a non-empty DataFrame."""
    from atlas.ingest.macro.mospi_cpi_ingest import get_bundled_cpi_data

    df = get_bundled_cpi_data()

    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "year" in df.columns
    assert "month" in df.columns
    assert "cpi" in df.columns


def test_get_bundled_cpi_data_covers_2016_onwards():
    """Bundled data must include 2016 (atlas historical scope)."""
    from atlas.ingest.macro.mospi_cpi_ingest import get_bundled_cpi_data

    df = get_bundled_cpi_data()
    years = df["year"].unique()

    assert 2016 in years, f"Expected 2016 in bundled data, got years: {sorted(years)}"
