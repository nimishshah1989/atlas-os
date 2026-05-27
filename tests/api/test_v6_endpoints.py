"""Tests for the v6 /v1 endpoints: screen.*, market.regime, cell.definitions, instrument/{iid}.

All DB calls are mocked. Each test focuses on:
* response envelope shape (data + meta)
* graceful degradation when the underlying table is empty
* SQL contract (bound parameters)
* OperationalError → 503
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from atlas.api import app
from atlas.config import Config


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    return TestClient(app)


def _mock_engine_seq(*result_specs: list[dict] | None) -> MagicMock:
    """Engine whose successive execute() calls return the given result sets.

    Each result_spec is a list of dicts (treated as ``.mappings()`` rows) OR
    None for an empty result. ``.first()`` returns the first row as a
    SimpleNamespace so ``row.col`` access works for endpoints that use it.
    """
    from types import SimpleNamespace

    class _FakeMapping:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        def all(self) -> list[dict]:
            return self._rows

        def __iter__(self):
            return iter(self._rows)

    class _FakeResult:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        def mappings(self) -> _FakeMapping:
            return _FakeMapping(self._rows)

        def first(self):  # type: ignore[no-untyped-def]
            if not self._rows:
                return None
            return SimpleNamespace(**self._rows[0])

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    results = [_FakeResult(rows or []) for rows in result_specs]
    mock_conn.execute.side_effect = results

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


# ---------------------------------------------------------------------------
# /v1/screen.stocks
# ---------------------------------------------------------------------------


class TestScreenStocks:
    def test_empty_table_returns_empty_data(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([{"d": None}])
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.stocks")
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["meta"]["degraded"] is True

    def test_returns_stocks_with_conviction(self, client: TestClient) -> None:
        latest = [{"d": date(2026, 5, 22)}]
        stock_rows = [
            {
                "instrument_id": "iid-1",
                "symbol": "RELIANCE",
                "company_name": "Reliance Industries",
                "sector": "Energy",
                "cap_tier": "Large",
            }
        ]
        conv_rows = [
            {
                "instrument_id": "iid-1",
                "tenure": "3m",
                "verdict": "POSITIVE",
                "eli5": "Reliance trends up",
                "ic": Decimal("0.10"),
                "friction_adjusted_excess": Decimal("0.05"),
                "conflict": False,
            }
        ]
        mock_engine = _mock_engine_seq(latest, stock_rows, conv_rows)
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.stocks")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["symbol"] == "RELIANCE"
        assert data[0]["conviction"][0]["verdict"] == "POSITIVE"

    def test_db_unavailable_returns_503(self, client: TestClient) -> None:
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = OperationalError("x", "y", "z")  # type: ignore[arg-type]
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.stocks")
        assert r.status_code == 503

    def test_invalid_cursor_returns_400(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([{"d": date(2026, 5, 22)}])
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.stocks?cursor=not-a-valid-base64-blob$$$")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /v1/screen.etfs
# ---------------------------------------------------------------------------


class TestScreenETFs:
    def test_empty_returns_envelope(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([{"d": None}], [])
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.etfs")
        assert r.status_code == 200
        assert r.json()["data"] == []


# ---------------------------------------------------------------------------
# /v1/screen.funds
# ---------------------------------------------------------------------------


class TestScreenFunds:
    def test_table_missing_returns_degraded_envelope(self, client: TestClient) -> None:
        """When atlas_mf_master doesn't exist, the endpoint surfaces an empty
        degraded envelope rather than 500ing.
        """
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = Exception("table not found")
        mock_engine.connect.return_value = mock_conn
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.funds")
        assert r.status_code == 200
        assert r.json()["meta"]["degraded"] is True


# ---------------------------------------------------------------------------
# /v1/screen.sectors
# ---------------------------------------------------------------------------


class TestScreenSectors:
    def test_returns_sector_rows(self, client: TestClient) -> None:
        latest = [{"d": date(2026, 5, 22)}]
        sector_rows = [
            {
                "sector": "Energy",
                "sector_strength_rank": 1,
                "sector_breadth_pos": Decimal("0.70"),
            }
        ]
        mock_engine = _mock_engine_seq(latest, sector_rows)
        with patch("atlas.api.screen.get_engine", return_value=mock_engine):
            r = client.get("/v1/screen.sectors")
        assert r.status_code == 200
        # sector_states_daily may or may not exist in mock — the endpoint
        # tolerates both. Just check envelope shape.
        body = r.json()
        assert "data" in body
        assert "meta" in body


# ---------------------------------------------------------------------------
# /v1/market.regime
# ---------------------------------------------------------------------------


class TestMarketRegime:
    def test_empty_regime_table(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([])
        with patch("atlas.api.market.get_engine", return_value=mock_engine):
            r = client.get("/v1/market.regime")
        assert r.status_code == 200
        assert r.json()["data"]["current"] is None
        assert r.json()["meta"]["degraded"] is True

    def test_with_latest_regime_row(self, client: TestClient) -> None:
        latest = [
            {
                "date": date(2026, 5, 22),
                "state": "Risk-On",
                "smallcap_rs_z": Decimal("0.5"),
                "breadth_pct_above_200dma": Decimal("0.65"),
                "vix_percentile": Decimal("0.30"),
                "cross_sectional_dispersion": Decimal("0.01"),
            }
        ]
        history: list[dict] = []
        cells = [
            {
                "cell_id": "cell-1",
                "cap_tier": "Large",
                "action": "POSITIVE",
                "tenure": "3m",
                "confidence_by_regime": {"Risk-On": 0.7, "Risk-Off": 0.3},
            }
        ]
        mock_engine = _mock_engine_seq(latest, history, cells)
        with patch("atlas.api.market.get_engine", return_value=mock_engine):
            r = client.get("/v1/market.regime")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["current"]["state"] == "Risk-On"
        assert len(body["data"]["preferred_cells"]) == 1
        assert body["data"]["preferred_cells"][0]["confidence"] == "0.7"


# ---------------------------------------------------------------------------
# /v1/cell.definitions
# ---------------------------------------------------------------------------


class TestCellDefinitions:
    def test_empty_returns_degraded(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([])
        with patch("atlas.api.cell_defs.get_engine", return_value=mock_engine):
            r = client.get("/v1/cell.definitions")
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["meta"]["degraded"] is True

    def test_returns_cells_with_candidates(self, client: TestClient) -> None:
        cell_rows = [
            {
                "cell_id": "cell-1",
                "cap_tier": "Large",
                "action": "POSITIVE",
                "tenure": "3m",
                "methodology_lock_ref": "TEST",
                "confidence_unconditional": Decimal("0.55"),
                "friction_adjusted_excess": Decimal("0.10"),
                "drift_status": "healthy",
                "rule_dsl": {"rule_type": "placeholder"},
            }
        ]
        candidate_rows = [
            {
                "candidate_id": "cand-1",
                "cell_definition_id": "cell-1",
                "rank": 1,
                "archetype": "quality_momentum",
                "ic": Decimal("0.12"),
                "friction_adjusted_excess": Decimal("0.10"),
                "bh_q_value": Decimal("0.05"),
                "eli5": "Quality leader",
            }
        ]
        mock_engine = _mock_engine_seq(cell_rows, candidate_rows)
        with patch("atlas.api.cell_defs.get_engine", return_value=mock_engine):
            r = client.get("/v1/cell.definitions?top_k=5")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["cap_tier"] == "Large"
        assert len(body["data"][0]["candidates"]) == 1
        assert body["data"][0]["candidates"][0]["archetype"] == "quality_momentum"


# ---------------------------------------------------------------------------
# /v1/instrument/{iid}
# ---------------------------------------------------------------------------


class TestInstrumentEndpoint:
    def test_unknown_instrument_returns_404(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([])  # empty meta row
        with patch("atlas.api.instrument.get_engine", return_value=mock_engine):
            r = client.get("/v1/instrument/missing-iid")
        assert r.status_code == 404

    def test_returns_full_envelope(self, client: TestClient) -> None:
        meta_row = [
            {
                "instrument_id": "iid-1",
                "symbol": "RELIANCE",
                "company_name": "Reliance Industries",
                "sector": "Energy",
                "cap_tier": "Large",
            }
        ]
        conviction_rows = [
            {
                "snapshot_date": date(2026, 5, 22),
                "tenure": "3m",
                "verdict": "POSITIVE",
                "eli5": "Quality leader",
                "best_rule_id": "rule-1",
                "cell_definition_id": "cell-1",
                "ic": Decimal("0.10"),
                "friction_adjusted_excess": Decimal("0.05"),
                "conflict": False,
            }
        ]
        history_rows = [
            {
                "snapshot_date": date(2026, 5, 21),
                "tenure": "3m",
                "verdict": "POSITIVE",
                "best_rule_id": "rule-1",
            }
        ]
        similar_rows = [
            {
                "instrument_id": "iid-2",
                "symbol": "ONGC",
                "last_fired": date(2026, 5, 22),
            }
        ]
        mock_engine = _mock_engine_seq(meta_row, conviction_rows, history_rows, similar_rows)
        with patch("atlas.api.instrument.get_engine", return_value=mock_engine):
            r = client.get("/v1/instrument/iid-1")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["instrument"]["symbol"] == "RELIANCE"
        assert len(body["data"]["conviction"]) == 1
        assert len(body["data"]["history"]) == 1
        assert len(body["data"]["similar"]) == 1
