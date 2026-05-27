"""Tests for atlas.ingest.macro.nse_bhavcopy_ingest.

TDD: tests written before implementation.
Source: NSE FII/DII Historical Activity CSV.
Tests use fixture CSV files — no real NSE calls.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# parse_fii_dii_csv
# ---------------------------------------------------------------------------


def test_parse_fii_dii_csv_returns_expected_columns():
    """Parsed DataFrame must have date, fii_net_cr, dii_net_cr columns."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import parse_fii_dii_csv

    fixture_path = FIXTURES_DIR / "fii_dii_sample.csv"
    df = parse_fii_dii_csv(str(fixture_path))

    assert "date" in df.columns
    assert "fii_net_cr" in df.columns
    assert "dii_net_cr" in df.columns


def test_parse_fii_dii_csv_net_values_are_correct():
    """FII net = Buy - Sell; DII net = Buy - Sell (in Crore)."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import parse_fii_dii_csv

    fixture_path = FIXTURES_DIR / "fii_dii_sample.csv"
    df = parse_fii_dii_csv(str(fixture_path))

    # Row 0: FII net = 12345.67 - 11234.56 = 1111.11
    # Row 1: FII net = 11000 - 12000 = -1000
    assert len(df) == 3
    row0 = df[df["date"] == "2024-01-01"].iloc[0]
    assert float(row0["fii_net_cr"]) == pytest.approx(1111.11, abs=0.1)


def test_parse_fii_dii_csv_date_format_converted_to_iso():
    """NSE dates are DD-Mon-YYYY; output must be YYYY-MM-DD strings."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import parse_fii_dii_csv

    fixture_path = FIXTURES_DIR / "fii_dii_sample.csv"
    df = parse_fii_dii_csv(str(fixture_path))

    # All dates must be ISO format (YYYY-MM-DD)
    for dt_str in df["date"].values:
        assert len(str(dt_str)) == 10, f"Expected ISO date, got {dt_str!r}"
        assert str(dt_str)[4] == "-", f"Expected YYYY-MM-DD, got {dt_str!r}"


def test_parse_fii_dii_csv_handles_empty_rows():
    """Empty rows in the CSV must be silently skipped."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import parse_fii_dii_csv

    # Write a temp CSV with an empty row in the middle
    csv_content = (
        "Date,Buy Value,Sell Value,Net Value,Buy Value.1,Sell Value.1,Net Value.1\n"
        "01-Jan-2024,12345.67,11234.56,1111.11,8765.43,7654.32,1111.11\n"
        "\n"  # empty row
        "03-Jan-2024,10500.00,9500.00,1000.00,8500.00,9000.00,-500.00\n"
    )
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        tmp_path = f.name

    try:
        df = parse_fii_dii_csv(tmp_path)
        assert len(df) == 2
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# upsert_fii_dii
# ---------------------------------------------------------------------------


def test_upsert_fii_dii_returns_row_count():
    """upsert_fii_dii must return count of rows written."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import upsert_fii_dii

    df = pd.DataFrame(
        [
            {"date": "2024-01-01", "fii_net_cr": 1111.11, "dii_net_cr": 1111.11},
            {"date": "2024-01-02", "fii_net_cr": -1000.0, "dii_net_cr": 1000.0},
        ]
    )

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.nse_bhavcopy_ingest.get_engine", return_value=mock_engine):
        count = upsert_fii_dii(df, engine=mock_engine)

    assert count == 2


def test_upsert_fii_dii_stores_decimal_not_float():
    """DB writes must use Decimal values, not raw float."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import upsert_fii_dii

    df = pd.DataFrame([{"date": "2024-01-01", "fii_net_cr": 1111.11, "dii_net_cr": 222.22}])

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

    with patch("atlas.ingest.macro.nse_bhavcopy_ingest.get_engine", return_value=mock_engine):
        upsert_fii_dii(df, engine=mock_engine)

    assert len(executed_params) == 1
    assert isinstance(executed_params[0]["fii"], Decimal)
    assert isinstance(executed_params[0]["dii"], Decimal)


def test_upsert_fii_dii_empty_returns_zero():
    """Empty DataFrame returns 0 without touching the DB."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import upsert_fii_dii

    df = pd.DataFrame(columns=["date", "fii_net_cr", "dii_net_cr"])
    mock_engine = MagicMock()

    with patch("atlas.ingest.macro.nse_bhavcopy_ingest.get_engine", return_value=mock_engine):
        count = upsert_fii_dii(df, engine=mock_engine)

    assert count == 0
    mock_engine.begin.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_fii_dii_csv (network layer)
# ---------------------------------------------------------------------------


def test_fetch_fii_dii_csv_downloads_and_returns_path():
    """fetch_fii_dii_csv downloads content and returns local path."""
    from atlas.ingest.macro.nse_bhavcopy_ingest import fetch_fii_dii_csv

    csv_bytes = b"Date,Buy Value,Sell Value,Net Value,Buy Value.1,Sell Value.1,Net Value.1\n"

    with patch("atlas.ingest.macro.nse_bhavcopy_ingest.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.content = csv_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = fetch_fii_dii_csv(dest_dir=tmpdir)
            assert path is not None
            assert os.path.exists(path)
