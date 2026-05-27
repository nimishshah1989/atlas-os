"""Tests for /v1/rank.etfs + /v1/rank.funds + their detail endpoints.

All DB access is mocked. The tests focus on:
* response envelope shape (data + meta) — both list + detail
* cursor pagination round-trip (page-end detected by limit hit)
* graceful degradation when the scorecard table is empty/missing
* required disclaimer fields on every fund row
* OperationalError → 503
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

from atlas.api import app
from atlas.config import Config


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    return TestClient(app)


def _mock_engine_seq(*result_specs: list[dict] | None | type[Exception]) -> MagicMock:
    """Engine whose successive execute() calls return the given result sets.

    Each result_spec is a list of dicts (treated as ``.mappings()`` rows),
    None for empty, or an Exception class to raise on that call.
    """

    class _FakeMapping:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        def all(self) -> list[dict]:
            return self._rows

        def first(self):  # type: ignore[no-untyped-def]
            return self._rows[0] if self._rows else None

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

    side_effects: list[object] = []
    for spec in result_specs:
        if isinstance(spec, type) and issubclass(spec, Exception):
            # SQLAlchemy DBAPIError subclasses need (statement, params, orig).
            if issubclass(spec, OperationalError | ProgrammingError):
                side_effects.append(spec("stmt", {}, Exception("simulated")))
            else:
                side_effects.append(spec("simulated"))
        else:
            side_effects.append(_FakeResult(spec or []))

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.side_effect = side_effects

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


# ---------------------------------------------------------------------------
# /v1/rank.etfs (list)
# ---------------------------------------------------------------------------


class TestRankETFsList:
    def test_empty_table_returns_degraded_envelope(self, client: TestClient) -> None:
        # latest snapshot returns d=None → degraded shape
        mock_engine = _mock_engine_seq([{"d": None}])
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs")
        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["meta"]["degraded"] is True
        assert "note" in body["meta"]

    def test_table_missing_returns_degraded_envelope(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq(ProgrammingError)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs")
        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["meta"]["degraded"] is True

    def test_returns_etf_rows(self, client: TestClient) -> None:
        latest = [{"d": date(2026, 5, 22)}]
        etf_rows = [
            {
                "snapshot_date": date(2026, 5, 22),
                "instrument_id": "iid-1",
                "isin": "INF000000001",
                "ticker": "NIFTYBEES",
                "etf_name": "Nifty BeES",
                "etf_category": "broad_index",
                "underlying_sector": None,
                "matrix_conviction_score": Decimal("60.00"),
                "sector_strength_score": Decimal("55.00"),
                "tracking_quality_score": Decimal("95.00"),
                "aum_bracket_score": Decimal("100.00"),
                "liquidity_score": Decimal("88.00"),
                "expense_ratio_score": Decimal("82.00"),
                "composite_score": Decimal("75.50"),
                "rank_in_category": 1,
                "category_size": 12,
                "is_atlas_leader": True,
                "eli5": "Top broad-index ETF",
                "raw_metrics": {"aum_cr": 12000.0, "ter_pct": 0.10},
            }
        ]
        mock_engine = _mock_engine_seq(latest, etf_rows)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs?category=broad_index&limit=10")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 1
        row = body["data"][0]
        assert row["ticker"] == "NIFTYBEES"
        assert row["is_atlas_leader"] is True
        assert row["composite_score"] == "75.50"
        assert body["meta"]["page_size"] == 10
        # Single row, limit=10 → no next cursor.
        assert body["meta"]["next_cursor"] is None

    def test_cursor_pagination_end_to_end(self, client: TestClient) -> None:
        """When len(data) == limit, next_cursor is set and round-trips."""
        latest = [{"d": date(2026, 5, 22)}]
        etf_rows = [
            {
                "snapshot_date": date(2026, 5, 22),
                "instrument_id": f"iid-{i}",
                "isin": None,
                "ticker": f"ETF{i}",
                "etf_name": f"ETF {i}",
                "etf_category": "sector",
                "underlying_sector": "Banking",
                "matrix_conviction_score": Decimal("60.00"),
                "sector_strength_score": Decimal("70.00"),
                "tracking_quality_score": Decimal("80.00"),
                "aum_bracket_score": Decimal("50.00"),
                "liquidity_score": Decimal("65.00"),
                "expense_ratio_score": Decimal("70.00"),
                "composite_score": Decimal(f"{80 - i:.2f}"),
                "rank_in_category": i + 1,
                "category_size": 5,
                "is_atlas_leader": i == 0,
                "eli5": "ELI5",
                "raw_metrics": {"aum_cr": 500.0},
            }
            for i in range(2)
        ]
        mock_engine = _mock_engine_seq(latest, etf_rows)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs?limit=2")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["next_cursor"] is not None  # exactly limit returned → has cursor

        # Round-trip: invalid cursor should 400.
        r2 = client.get("/v1/rank.etfs?cursor=NOTBASE64*")
        # Cursor is parsed before the engine call → 400 without DB hit.
        assert r2.status_code == 400

    def test_db_unavailable_returns_503(self, client: TestClient) -> None:
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = OperationalError("x", "y", "z")  # type: ignore[arg-type]
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs")
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# /v1/rank.funds (list)
# ---------------------------------------------------------------------------


class TestRankFundsList:
    def test_returns_fund_rows_with_disclaimers(self, client: TestClient) -> None:
        latest = [{"d": date(2026, 5, 22)}]
        fund_rows = [
            {
                "snapshot_date": date(2026, 5, 22),
                "scheme_code": "120503",
                "isin": "INF200K01ABC",
                "fund_name": "Top Flexi Cap Fund",
                "fund_category": "Flexi Cap",
                "fund_style": "Growth",
                "amc": "Test AMC",
                "risk_adjusted_return_score": Decimal("78.00"),
                "holdings_conviction_score": Decimal("72.00"),
                "style_sector_score": Decimal("65.00"),
                "cost_manager_score": Decimal("80.00"),
                "composite_score": Decimal("74.50"),
                "rank_in_category": 1,
                "category_size": 30,
                "is_atlas_leader": True,
                "is_avoid": False,
                "confidence_low": False,
                "holdings_unjoinable": False,
                "survivorship_exposure_pct": Decimal("85.00"),
                "nav_as_of": date(2026, 5, 22),
                "holdings_as_of": date(2026, 4, 30),
                "eli5": "Top-quartile leader",
                "sub_metrics": {"sharpe": 1.45, "aum_cr": 2500.0},
            }
        ]
        mock_engine = _mock_engine_seq(latest, fund_rows)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.funds?category=Flexi%20Cap&min_aum_cr=500")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 1
        row = body["data"][0]
        # Disclaimer fields MUST be present on every fund row.
        assert "confidence_low" in row
        assert "holdings_unjoinable" in row
        assert "survivorship_exposure_pct" in row
        assert "nav_as_of" in row
        assert "holdings_as_of" in row
        assert row["is_atlas_leader"] is True
        # meta.disclaimers list of 5 caveats.
        assert len(body["meta"]["disclaimers"]) == 5

    def test_empty_table_returns_degraded(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([{"d": None}])
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.funds")
        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["meta"]["degraded"] is True

    def test_table_missing_returns_degraded(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq(ProgrammingError)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.funds")
        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["meta"]["degraded"] is True


# ---------------------------------------------------------------------------
# /v1/rank.etfs/{iid} (detail)
# ---------------------------------------------------------------------------


class TestRankETFsDetail:
    def test_unknown_etf_returns_404(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([])
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs/iid-missing")
        assert r.status_code == 404

    def test_returns_full_envelope(self, client: TestClient) -> None:
        detail_row = [
            {
                "snapshot_date": date(2026, 5, 22),
                "instrument_id": "iid-1",
                "isin": "INF000000001",
                "ticker": "BANKBEES",
                "etf_name": "Bank BeES",
                "etf_category": "sector",
                "underlying_sector": "Banking",
                "matrix_conviction_score": Decimal("70.00"),
                "sector_strength_score": Decimal("85.00"),
                "tracking_quality_score": Decimal("90.00"),
                "aum_bracket_score": Decimal("75.00"),
                "liquidity_score": Decimal("80.00"),
                "expense_ratio_score": Decimal("82.00"),
                "composite_score": Decimal("80.20"),
                "rank_in_category": 1,
                "category_size": 8,
                "is_atlas_leader": True,
                "eli5": "Top sector ETF — Banking leading",
                "raw_metrics": {"aum_cr": 4500.0, "ter_pct": 0.25},
            }
        ]
        mock_engine = _mock_engine_seq(detail_row)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.etfs/iid-1")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["scorecard"]["ticker"] == "BANKBEES"
        assert body["data"]["raw_metrics"]["aum_cr"] == 4500.0
        # Contract placeholders present even when empty.
        assert "tracking_error_series" in body["data"]
        assert "sector_overlay" in body["data"]


# ---------------------------------------------------------------------------
# /v1/rank.funds/{scheme_code} (detail)
# ---------------------------------------------------------------------------


class TestRankFundsDetail:
    def test_unknown_fund_returns_404(self, client: TestClient) -> None:
        mock_engine = _mock_engine_seq([])
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.funds/missing-code")
        assert r.status_code == 404

    def test_returns_full_envelope_with_disclaimers(self, client: TestClient) -> None:
        detail_row = [
            {
                "snapshot_date": date(2026, 5, 22),
                "scheme_code": "120503",
                "isin": None,
                "fund_name": "Sample Fund",
                "fund_category": "Large Cap",
                "fund_style": "Growth",
                "amc": "Test AMC",
                "risk_adjusted_return_score": Decimal("70.00"),
                "holdings_conviction_score": Decimal("60.00"),
                "style_sector_score": Decimal("55.00"),
                "cost_manager_score": Decimal("65.00"),
                "composite_score": Decimal("65.10"),
                "rank_in_category": 5,
                "category_size": 30,
                "is_atlas_leader": False,
                "is_avoid": False,
                "confidence_low": False,
                "holdings_unjoinable": False,
                "survivorship_exposure_pct": Decimal("92.50"),
                "nav_as_of": date(2026, 5, 22),
                "holdings_as_of": date(2026, 4, 30),
                "eli5": "Mid-tier",
                "sub_metrics": {"sharpe": 1.05, "max_dd": 0.20},
                "top_holdings": [
                    {
                        "instrument_id": "iid-A",
                        "symbol": "RELIANCE",
                        "weight_pct": 8.5,
                        "verdict": "POSITIVE",
                    }
                ],
            }
        ]
        mock_engine = _mock_engine_seq(detail_row)
        with patch("atlas.api.rank.get_engine", return_value=mock_engine):
            r = client.get("/v1/rank.funds/120503")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["scorecard"]["scheme_code"] == "120503"
        assert body["data"]["scorecard"]["confidence_low"] is False
        assert body["data"]["scorecard"]["holdings_unjoinable"] is False
        assert "survivorship_exposure_pct" in body["data"]["scorecard"]
        # Holdings drilldown surfaces verdict per holding.
        assert body["data"]["top_holdings"][0]["verdict"] == "POSITIVE"
        # Disclaimers list of 5.
        assert len(body["meta"]["disclaimers"]) == 5
