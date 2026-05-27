"""Tests for atlas.ingest.macro.fii_dii_monthly_ingest.

TDD: tests written before/alongside implementation.
Source: Bundled monthly FII/DII net cash-equity flows (SEBI/NSE public data).
Tests use fixture JSON file — no real DB or network calls.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# get_bundled_fii_dii_monthly
# ---------------------------------------------------------------------------


def test_get_bundled_fii_dii_monthly_returns_dataframe():
    """get_bundled_fii_dii_monthly must return a non-empty DataFrame."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import get_bundled_fii_dii_monthly

    df = get_bundled_fii_dii_monthly()

    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_get_bundled_fii_dii_monthly_has_expected_columns():
    """DataFrame must have year, month, fii_net_cr, dii_net_cr columns."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import get_bundled_fii_dii_monthly

    df = get_bundled_fii_dii_monthly()

    assert "year" in df.columns
    assert "month" in df.columns
    assert "fii_net_cr" in df.columns
    assert "dii_net_cr" in df.columns


def test_get_bundled_fii_dii_monthly_uses_verified_daily_bootstrap():
    """Bundled monthly data must aggregate from the verified Moneycontrol daily JSON.
    Historical 2016-01 backfill is a deferred follow-up; this test asserts the
    CURRENT verified bundle covers the months present in the bootstrap JSON.
    """
    from atlas.ingest.macro.fii_dii_monthly_ingest import get_bundled_fii_dii_monthly

    df = get_bundled_fii_dii_monthly()

    # At minimum, must have the 2 months from the Moneycontrol bootstrap (2026-04, 2026-05).
    assert len(df) >= 2, f"Expected >=2 verified months, got {len(df)}"

    # Latest month must be recent (within the last 6 months from bootstrap date 2026-05-27).
    latest_year_month = (df["year"].max(), df.loc[df["year"] == df["year"].max(), "month"].max())
    assert latest_year_month >= (
        2026,
        4,
    ), f"Expected latest month >= 2026-04, got {latest_year_month}"


def test_get_bundled_fii_dii_monthly_no_null_values():
    """Bundled data must not have NULL fii_net_cr or dii_net_cr."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import get_bundled_fii_dii_monthly

    df = get_bundled_fii_dii_monthly()

    assert df["fii_net_cr"].notna().all(), "fii_net_cr has NULL values"
    assert df["dii_net_cr"].notna().all(), "dii_net_cr has NULL values"


# ---------------------------------------------------------------------------
# upsert_fii_dii_monthly
# ---------------------------------------------------------------------------


def test_upsert_fii_dii_monthly_returns_row_count():
    """upsert_fii_dii_monthly must return count of months processed."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import upsert_fii_dii_monthly

    df = pd.DataFrame(
        [
            {"year": 2023, "month": 1, "fii_net_cr": -28854.0, "dii_net_cr": 28490.0},
            {"year": 2023, "month": 2, "fii_net_cr": -5294.0, "dii_net_cr": 10830.0},
        ]
    )

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    count = upsert_fii_dii_monthly(df, engine=mock_engine)

    assert count == 2


def test_upsert_fii_dii_monthly_stores_decimal_not_float():
    """DB writes must use Decimal values, not raw float."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import upsert_fii_dii_monthly

    df = pd.DataFrame([{"year": 2023, "month": 3, "fii_net_cr": 7937.0, "dii_net_cr": 2510.0}])

    executed_params: list[dict] = []

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    upsert_fii_dii_monthly(df, engine=mock_engine)

    assert len(executed_params) == 1
    assert isinstance(executed_params[0]["fii"], Decimal), "fii must be Decimal"
    assert isinstance(executed_params[0]["dii"], Decimal), "dii must be Decimal"


def test_upsert_fii_dii_monthly_passes_correct_month_range():
    """UPDATE must use correct first-of-month and first-of-next-month params."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import upsert_fii_dii_monthly

    df = pd.DataFrame([{"year": 2023, "month": 5, "fii_net_cr": 43838.0, "dii_net_cr": -19850.0}])

    executed_params: list[dict] = []

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    upsert_fii_dii_monthly(df, engine=mock_engine)

    assert len(executed_params) == 1
    assert executed_params[0]["start"] == "2023-05-01"
    assert executed_params[0]["end"] == "2023-06-01"


def test_upsert_fii_dii_monthly_december_wraps_to_jan():
    """December month must wrap to January of next year (start=2023-12-01, end=2024-01-01)."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import upsert_fii_dii_monthly

    df = pd.DataFrame([{"year": 2023, "month": 12, "fii_net_cr": 66135.0, "dii_net_cr": -31800.0}])

    executed_params: list[dict] = []

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    upsert_fii_dii_monthly(df, engine=mock_engine)

    assert executed_params[0]["start"] == "2023-12-01"
    assert executed_params[0]["end"] == "2024-01-01"


def test_upsert_fii_dii_monthly_empty_returns_zero():
    """Empty DataFrame returns 0 without touching the DB."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import upsert_fii_dii_monthly

    df = pd.DataFrame(columns=["year", "month", "fii_net_cr", "dii_net_cr"])
    mock_engine = MagicMock()

    count = upsert_fii_dii_monthly(df, engine=mock_engine)

    assert count == 0
    mock_engine.begin.assert_not_called()


def test_upsert_fii_dii_monthly_correct_fii_values():
    """FII Decimal value must match original float (rounded to 4dp)."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import upsert_fii_dii_monthly

    df = pd.DataFrame(
        [{"year": 2023, "month": 6, "fii_net_cr": 47148.5678, "dii_net_cr": -21720.1234}]
    )

    executed_params: list[dict] = []

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    upsert_fii_dii_monthly(df, engine=mock_engine)

    fii_val = executed_params[0]["fii"]
    dii_val = executed_params[0]["dii"]
    assert float(fii_val) == pytest.approx(47148.5678, abs=0.01)
    assert float(dii_val) == pytest.approx(-21720.1234, abs=0.01)


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------


def test_run_all_returns_integer_count():
    """run_all must return an integer count of months processed."""
    from atlas.ingest.macro.fii_dii_monthly_ingest import run_all

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    result = run_all(engine=mock_engine)

    assert isinstance(result, int)
    assert result > 0, "Expected > 0 months from bundled data"


def test_run_all_processes_all_verified_bundle_months():
    """run_all must process exactly the months present in the verified daily bootstrap.
    The historical 2016-01 backfill is deferred (paid vendor needed); this test
    asserts the current verified bundle drives run_all's row count.
    """
    from atlas.ingest.macro.fii_dii_monthly_ingest import (
        get_bundled_fii_dii_monthly,
        run_all,
    )

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    expected = len(get_bundled_fii_dii_monthly())
    result = run_all(engine=mock_engine)

    assert result == expected, f"Expected {expected} months from verified bundle, got {result}"


# ---------------------------------------------------------------------------
# Fixture validation
# ---------------------------------------------------------------------------


def test_fixture_file_loads_correctly():
    """Fixture JSON file must load into valid DataFrame matching schema."""
    fixture_path = FIXTURES_DIR / "fii_dii_monthly_sample.json"
    assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

    with open(fixture_path) as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    assert "year" in df.columns
    assert "month" in df.columns
    assert "fii_net_cr" in df.columns
    assert "dii_net_cr" in df.columns
    assert len(df) >= 10
