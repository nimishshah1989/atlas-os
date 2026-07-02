# tests/tv/test_peer_matrix.py
"""Unit tests for atlas.tv.peer_matrix."""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch

import pytest
from atlas.tv.peer_matrix import (  # type: ignore[import]
    _classify_conviction,
    _classify_ema_slope,
    _classify_volume,
    get_peer_matrix,
)


@pytest.mark.parametrize(
    "ratio, expected",
    [
        (1.05, "Rising"),
        (1.021, "Rising"),
        (1.019, "Flat"),
        (1.00, "Flat"),
        (0.981, "Flat"),
        (0.979, "Declining"),
        (0.90, "Declining"),
        (None, "—"),
    ],
)
def test_classify_ema_slope(ratio, expected):
    assert _classify_ema_slope(ratio) == expected


@pytest.mark.parametrize(
    "vol_ratio, expected",
    [
        (1.50, "Expanding"),
        (1.31, "Expanding"),
        (1.30, "Stable"),
        (1.00, "Stable"),
        (0.81, "Stable"),
        (0.80, "Fading"),
        (0.79, "Fading"),
        (None, "—"),
    ],
)
def test_classify_volume(vol_ratio, expected):
    assert _classify_volume(vol_ratio) == expected


@pytest.mark.parametrize(
    "verdict, expected",
    [
        ("POSITIVE", "Bullish"),
        ("NEGATIVE", "Bearish"),
        ("NEUTRAL", "Neutral"),
        (None, "Neutral"),
        ("UNKNOWN", "Neutral"),
    ],
)
def test_classify_conviction(verdict, expected):
    assert _classify_conviction(verdict) == expected


def _mock_db_rows(rows: list[dict]):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.all.return_value = rows
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


def _make_row(**kwargs):
    defaults = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "is_parent": True,
        "state": "stage_2b",
        "dwell_days": 10,
        "conviction_verdict": "POSITIVE",
        "conviction_ic": 0.065,
        "rs_pctile_3m": 0.82,
        "ret_3m": 0.15,
        "ema_20_ratio": 1.03,
        "extension_pct": 0.05,
        "vol_ratio_63": 1.40,
        "effort_ratio_63": 0.95,
    }
    defaults.update(kwargs)
    return defaults


def test_get_peer_matrix_returns_correct_shape():
    rows = [
        _make_row(symbol="RELIANCE", is_parent=True),
        _make_row(symbol="ONGC", is_parent=False, conviction_verdict="NEUTRAL", rs_pctile_3m=0.55),
        _make_row(symbol="IOC", is_parent=False, conviction_verdict="NEGATIVE", rs_pctile_3m=0.40),
    ]
    result = get_peer_matrix("RELIANCE", engine=_mock_db_rows(rows))
    assert result["symbol"] == "RELIANCE"
    assert len(result["peers"]) == 3


def test_get_peer_matrix_parent_is_first_and_flagged():
    rows = [
        _make_row(symbol="RELIANCE", is_parent=True),
        _make_row(symbol="ONGC", is_parent=False),
    ]
    result = get_peer_matrix("RELIANCE", engine=_mock_db_rows(rows))
    assert result["peers"][0]["is_parent"] is True
    assert result["peers"][1]["is_parent"] is False


def test_get_peer_matrix_metric_classification():
    row = _make_row(
        ema_20_ratio=1.05,
        vol_ratio_63=1.50,
        conviction_verdict="POSITIVE",
        rs_pctile_3m=0.82,
        ret_3m=0.15,
        extension_pct=0.05,
    )
    result = get_peer_matrix("RELIANCE", engine=_mock_db_rows([row]))
    peer = result["peers"][0]
    assert peer["ema20_slope"] == "Rising"
    assert peer["volume"] == "Expanding"
    assert peer["conviction"] == "Bullish"
    assert peer["rs_vs_nifty"] == 82.0
    assert peer["ret_3m_pct"] == 15.0
    assert peer["extension_pct"] == 5.0


def test_get_peer_matrix_null_metrics_handled():
    row = _make_row(
        ema_20_ratio=None,
        vol_ratio_63=None,
        conviction_ic=None,
        rs_pctile_3m=None,
        ret_3m=None,
        extension_pct=None,
        conviction_verdict=None,
        state=None,
    )
    result = get_peer_matrix("RELIANCE", engine=_mock_db_rows([row]))
    peer = result["peers"][0]
    assert peer["ema20_slope"] == "—"
    assert peer["volume"] == "—"
    assert peer["conviction"] == "Neutral"
    assert peer["conviction_ic"] is None
    assert peer["rs_vs_nifty"] is None
    assert peer["ret_3m_pct"] is None
    assert peer["extension_pct"] is None
    assert peer["stage"] == "—"


def test_get_peer_matrix_returns_error_when_no_rows():
    result = get_peer_matrix("UNKNOWN", engine=_mock_db_rows([]))
    assert result["error"] == "no_data"
    assert result["symbol"] == "UNKNOWN"


def test_peer_matrix_route_returns_200():
    from atlas.api import app  # type: ignore[import]
    from fastapi.testclient import TestClient

    fake_result = {
        "symbol": "RELIANCE",
        "peers": [
            {
                "symbol": "RELIANCE",
                "company_name": "Reliance",
                "is_parent": True,
                "stage": "stage_2b",
                "conviction": "Bullish",
                "conviction_ic": 0.065,
                "rs_vs_nifty": 82.0,
                "ema20_slope": "Rising",
                "volume": "Expanding",
                "ret_3m_pct": 15.0,
                "extension_pct": 5.0,
            }
        ],
    }
    with patch("atlas.tv.routes.get_peer_matrix", return_value=fake_result):
        client = TestClient(app)
        resp = client.get("/v1/stocks/RELIANCE/peer-matrix")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["peers"][0]["is_parent"] is True
    assert body["meta"]["source"] == "atlas_universe_stocks + atlas_stock_metrics_daily"


def test_peer_matrix_route_returns_404_for_no_data():
    from atlas.api import app  # type: ignore[import]
    from fastapi.testclient import TestClient

    with patch(
        "atlas.tv.routes.get_peer_matrix", return_value={"error": "no_data", "symbol": "GHOST"}
    ):
        client = TestClient(app)
        resp = client.get("/v1/stocks/GHOST/peer-matrix")

    assert resp.status_code == 404
