# tests/tv/test_routes.py
import datetime
import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from atlas.api import app  # type: ignore[import]

client = TestClient(app)


def _mock_conn(first_return):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.first.return_value = first_return
    mock_engine = MagicMock()
    mock_engine.connect.return_value = conn
    return mock_engine


def test_tv_metrics_returns_200():
    fake_row = {
        "symbol": "RELIANCE",
        "instrument_id": "uuid-1",
        "fetched_at": "2026-05-28T21:00:00+05:30",
        "tv_recommend_label": "BUY",
        "recommend_all": 0.35,
        "rsi_14": 58.0,
        "price": 2820.0,
        "high_52w": 3000.0,
        "low_52w": 2400.0,
    }
    with patch("atlas.tv.routes.get_engine", return_value=_mock_conn(fake_row)):
        resp = client.get("/v1/tv/metrics/RELIANCE")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["symbol"] == "RELIANCE"
    assert data["tv_recommend_label"] == "BUY"


def test_tv_metrics_returns_404_for_unknown_symbol():
    with patch("atlas.tv.routes.get_engine", return_value=_mock_conn(None)):
        resp = client.get("/v1/tv/metrics/DOESNOTEXIST")
    assert resp.status_code == 404


def test_tv_metrics_stale_flag():
    stale_fetched_at = (datetime.datetime.utcnow() - datetime.timedelta(days=4)).isoformat()
    fake_row = {
        "symbol": "TCS",
        "instrument_id": "uuid-2",
        "fetched_at": stale_fetched_at,
        "tv_recommend_label": "NEUTRAL",
        "recommend_all": 0.0,
        "rsi_14": 50.0,
        "price": 3500.0,
        "high_52w": 3800.0,
        "low_52w": 3000.0,
    }
    with patch("atlas.tv.routes.get_engine", return_value=_mock_conn(fake_row)):
        resp = client.get("/v1/tv/metrics/TCS")
    assert resp.status_code == 200
    assert resp.json()["meta"]["is_stale"] is True
