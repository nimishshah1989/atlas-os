# tests/tv/test_routes.py
import datetime
import os
from decimal import Decimal

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from atlas.api import app  # type: ignore[import]

client = TestClient(app)


def _mock_conn(first_return):
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = first_return
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = conn
    return mock_engine


def test_tv_metrics_returns_200():
    fake_row = {
        "symbol": "RELIANCE",
        "instrument_id": "uuid-1",
        "fetched_at": "2026-05-28T21:00:00+05:30",
        "tv_recommend_label": "BUY",
        "recommend_all": Decimal("0.35"),
        "rsi_14": Decimal("58.0"),
        "price": Decimal("2820.0"),
        "high_52w": Decimal("3000.0"),
        "low_52w": Decimal("2400.0"),
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
    stale_fetched_at = (
        datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=4)
    ).isoformat()
    fake_row = {
        "symbol": "TCS",
        "instrument_id": "uuid-2",
        "fetched_at": stale_fetched_at,
        "tv_recommend_label": "NEUTRAL",
        "recommend_all": Decimal("0.0"),
        "rsi_14": Decimal("50.0"),
        "price": Decimal("3500.0"),
        "high_52w": Decimal("3800.0"),
        "low_52w": Decimal("3000.0"),
    }
    with patch("atlas.tv.routes.get_engine", return_value=_mock_conn(fake_row)):
        resp = client.get("/v1/tv/metrics/TCS")
    assert resp.status_code == 200
    assert resp.json()["meta"]["is_stale"] is True


def test_trigger_screener_returns_ok():
    with patch("atlas.tv.routes.fetch_and_upsert_all") as mock_run:
        resp = client.post("/v1/tv/internal/run-screener")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_run.assert_called_once()


def test_trigger_screener_returns_500_on_exception():
    with patch("atlas.tv.routes.fetch_and_upsert_all", side_effect=RuntimeError("boom")):
        resp = client.post("/v1/tv/internal/run-screener")
    assert resp.status_code == 500


def test_portfolio_analytics_returns_200():
    fake_analytics = {
        "portfolio_id": "pid-1",
        "sharpe": 1.2,
        "sortino": 1.8,
        "calmar": 2.1,
        "beta": 0.85,
        "alpha": 0.12,
        "max_drawdown": 0.08,
        "twr": 0.35,
        "annualised_return": 0.22,
        "observation_days": 252,
        "risk_free_rate_used": 0.065,
        "daily_returns": [
            {"date": "2026-01-02", "portfolio_return": 0.005, "nifty50_return": 0.003}
        ],
    }
    with patch("atlas.tv.routes.compute_portfolio_analytics", return_value=fake_analytics):
        resp = client.get("/v1/portfolios/pid-1/analytics")
    assert resp.status_code == 200
    assert resp.json()["data"]["sharpe"] == 1.2


def test_portfolio_analytics_returns_404_for_no_data():
    with patch(
        "atlas.tv.routes.compute_portfolio_analytics",
        return_value={"error": "no_data", "portfolio_id": "pid-x"},
    ):
        resp = client.get("/v1/portfolios/pid-x/analytics")
    assert resp.status_code == 404
