# tests/tv/test_rs_ratios.py
"""Unit tests for atlas.tv.rs_ratios."""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from atlas.tv.rs_ratios import (  # type: ignore[import]
    _classify_rs_status,
    compute_rs_ratios,
)


def _make_engine(sector_return, stock_rows, index_rows):
    def _execute(sql, params=None):
        m = MagicMock()
        sql_str = str(sql)
        if "de_equity_ohlcv" in sql_str:
            m.mappings.return_value.all.return_value = stock_rows
        elif "de_index_prices" in sql_str:
            m.mappings.return_value.all.return_value = index_rows
        else:
            if sector_return is not None:
                m.mappings.return_value.first.return_value = {"sector": sector_return}
            else:
                m.mappings.return_value.first.return_value = None
        return m

    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.side_effect = _execute
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


@pytest.mark.parametrize(
    "pct, expected",
    [
        (0.0, "BREAKING_OUT"),
        (-0.029, "BREAKING_OUT"),
        (-0.03, "BREAKING_OUT"),
        (-0.031, "AT_RESISTANCE"),
        (-0.08, "AT_RESISTANCE"),
        (-0.081, "BELOW_RESISTANCE"),
        (-0.5, "BELOW_RESISTANCE"),
    ],
)
def test_classify_rs_status_boundary_values(pct: float, expected: str) -> None:
    assert _classify_rs_status(pct) == expected


def test_compute_rs_ratios_returns_vs_nifty50():
    dates = pd.date_range("2025-06-01", periods=10)
    stock_prices = [100 + i for i in range(10)]
    nifty_prices = [200 + i * 2 for i in range(10)]
    energy_prices = [180 + i for i in range(10)]

    stock_rows = [{"date": d.date(), "close": p} for d, p in zip(dates, stock_prices, strict=False)]
    index_rows = [
        {"date": d.date(), "index_code": "NIFTY 50", "close": p}
        for d, p in zip(dates, nifty_prices, strict=False)
    ] + [
        {"date": d.date(), "index_code": "NIFTY ENERGY", "close": p}
        for d, p in zip(dates, energy_prices, strict=False)
    ]

    engine = _make_engine("Energy", stock_rows, index_rows)
    result = compute_rs_ratios("RELIANCE", days=30, engine=engine)

    assert result.get("error") is None
    assert "vs_nifty50" in result
    assert len(result["vs_nifty50"]) == 10
    assert "vs_nifty50_resistance" in result
    assert "vs_nifty50_status" in result
    point = result["vs_nifty50"][0]
    assert "date" in point
    assert "ratio" in point


def test_compute_rs_ratios_returns_vs_sector():
    dates = pd.date_range("2025-01-01", periods=5)
    stock_rows = [{"date": d.date(), "close": 100.0} for d in dates]
    index_rows = [{"date": d.date(), "index_code": "NIFTY 50", "close": 200.0} for d in dates] + [
        {"date": d.date(), "index_code": "NIFTY IT", "close": 150.0} for d in dates
    ]
    engine = _make_engine("Information Technology", stock_rows, index_rows)
    result = compute_rs_ratios("TCS", days=30, engine=engine)

    assert "vs_sector" in result
    assert len(result["vs_sector"]) == 5
    assert result["sector_index_code"] == "NIFTY IT"


def test_compute_rs_ratios_breaking_out_when_at_peak():
    dates = pd.date_range("2025-01-01", periods=5)
    stock_rows = [{"date": d.date(), "close": 100 + i * 10} for i, d in enumerate(dates)]
    index_rows = [{"date": d.date(), "index_code": "NIFTY 50", "close": 100.0} for d in dates] + [
        {"date": d.date(), "index_code": "NIFTY ENERGY", "close": 100.0} for d in dates
    ]
    engine = _make_engine("Energy", stock_rows, index_rows)
    result = compute_rs_ratios("RELIANCE", days=30, engine=engine)

    assert result["vs_nifty50_status"] == "BREAKING_OUT"


def test_compute_rs_ratios_below_resistance():
    dates = pd.date_range("2025-01-01", periods=10)
    closes = [100.0 if i == 0 else 50.0 for i in range(10)]
    stock_rows = [{"date": d.date(), "close": c} for d, c in zip(dates, closes, strict=False)]
    index_rows = [{"date": d.date(), "index_code": "NIFTY 50", "close": 100.0} for d in dates] + [
        {"date": d.date(), "index_code": "NIFTY ENERGY", "close": 100.0} for d in dates
    ]
    engine = _make_engine("Energy", stock_rows, index_rows)
    result = compute_rs_ratios("RELIANCE", days=30, engine=engine)

    assert result["vs_nifty50_status"] == "BELOW_RESISTANCE"


def test_compute_rs_ratios_returns_error_when_no_price_data():
    engine = _make_engine("Energy", [], [])
    result = compute_rs_ratios("UNKNOWN", days=30, engine=engine)
    assert result["error"] == "no_data"
    assert result["symbol"] == "UNKNOWN"


def test_compute_rs_ratios_unknown_sector_falls_back_to_nifty50():
    dates = pd.date_range("2025-01-01", periods=3)
    stock_rows = [{"date": d.date(), "close": 100.0} for d in dates]
    index_rows = [{"date": d.date(), "index_code": "NIFTY 50", "close": 200.0} for d in dates]
    engine = _make_engine("UnknownSector", stock_rows, index_rows)
    result = compute_rs_ratios("XYZ", days=30, engine=engine)

    assert result["sector_index_code"] == "NIFTY 50"
    assert len(result["vs_nifty50"]) == 3


def test_rs_ratios_route_returns_200():
    from fastapi.testclient import TestClient

    from atlas.api import app  # type: ignore[import]

    fake_result = {
        "symbol": "RELIANCE",
        "sector": "Energy",
        "sector_index_code": "NIFTY ENERGY",
        "vs_sector": [{"date": "2026-01-02", "ratio": 0.55}],
        "vs_sector_resistance": 0.60,
        "vs_sector_status": "BELOW_RESISTANCE",
        "vs_nifty50": [{"date": "2026-01-02", "ratio": 0.45}],
        "vs_nifty50_resistance": 0.50,
        "vs_nifty50_status": "BELOW_RESISTANCE",
    }

    with patch("atlas.tv.routes.compute_rs_ratios", return_value=fake_result):
        client = TestClient(app)
        resp = client.get("/v1/stocks/RELIANCE/rs-ratios")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert body["data"]["symbol"] == "RELIANCE"
    assert body["meta"]["source"] == "de_equity_ohlcv + de_index_prices"


def test_rs_ratios_route_returns_404_for_no_data():
    from fastapi.testclient import TestClient

    from atlas.api import app  # type: ignore[import]

    with patch(
        "atlas.tv.routes.compute_rs_ratios",
        return_value={"error": "no_data", "symbol": "GHOST"},
    ):
        client = TestClient(app)
        resp = client.get("/v1/stocks/GHOST/rs-ratios")

    assert resp.status_code == 404
