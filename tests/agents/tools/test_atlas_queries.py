"""Smoke tests for atlas_queries — mocked engine, no DB roundtrip."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.agents.tools.atlas_queries import (
    _to_jsonable,
    query_current_regime,
    query_sector_rotation_quadrants,
    query_top_rs_stocks,
)


def _mock_engine_for_rows(rows: list[dict]) -> MagicMock:
    """Build a MagicMock engine whose connect().execute().mappings().fetchall()
    returns ``rows`` and fetchone() returns the first row (or None)."""
    conn = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    result.fetchone.return_value = rows[0] if rows else None
    mappings = MagicMock()
    mappings.fetchall.return_value = rows
    mappings.fetchone.return_value = rows[0] if rows else None
    result.mappings.return_value = mappings
    conn.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def test_to_jsonable_handles_decimal_and_date() -> None:
    assert _to_jsonable(Decimal("1.234")) == "1.234"
    assert _to_jsonable(date(2026, 5, 12)) == "2026-05-12"
    assert _to_jsonable(None) is None
    assert _to_jsonable(42) == 42
    assert _to_jsonable("foo") == "foo"


def test_current_regime_returns_available_false_on_empty() -> None:
    engine = _mock_engine_for_rows([])
    result = query_current_regime(engine)
    assert result == {"available": False, "reason": "mv_current_market_regime is empty"}


def test_current_regime_returns_dict_with_decimal_to_str() -> None:
    rows = [
        {
            "date": date(2026, 5, 8),
            "regime_state": "Risk-On",
            "deployment_multiplier": Decimal("1.10"),
            "dislocation_active": False,
            "india_vix": Decimal("13.2"),
            "pct_above_ema_50": Decimal("78.4"),
            "pct_above_ema_200": Decimal("65.1"),
            "pct_in_strong_states": Decimal("48.0"),
            "ad_ratio": Decimal("1.85"),
            "net_new_highs": 47,
            "mcclellan_oscillator": Decimal("45.2"),
        }
    ]
    engine = _mock_engine_for_rows(rows)
    result = query_current_regime(engine)
    assert result["available"] is True
    assert result["regime_state"] == "Risk-On"
    assert result["deployment_multiplier"] == "1.10"  # Decimal -> str
    assert result["date"] == "2026-05-08"  # date -> ISO


def test_sector_rotation_quadrants_groups_correctly() -> None:
    rows = [
        {
            "sector_name": "NIFTY IT",
            "rrg_quadrant": "Leading",
            "rs_level": Decimal("85.0"),
            "rs_velocity": Decimal("0.5"),
            "rs_pctile_cross_sector": Decimal("92.0"),
            "sector_state": "Leader",
            "date": date(2026, 5, 8),
        },
        {
            "sector_name": "NIFTY FMCG",
            "rrg_quadrant": "Lagging",
            "rs_level": Decimal("20.0"),
            "rs_velocity": Decimal("-0.3"),
            "rs_pctile_cross_sector": Decimal("8.0"),
            "sector_state": "Laggard",
            "date": date(2026, 5, 8),
        },
    ]
    engine = _mock_engine_for_rows(rows)
    result = query_sector_rotation_quadrants(engine)
    assert result["available"] is True
    assert result["n_sectors"] == 2
    assert result["as_of"] == "2026-05-08"
    assert len(result["quadrants"]["Leading"]) == 1
    assert result["quadrants"]["Leading"][0]["sector"] == "NIFTY IT"
    assert len(result["quadrants"]["Lagging"]) == 1
    assert len(result["quadrants"]["Improving"]) == 0


def test_top_rs_stocks_clamps_n_to_50() -> None:
    """``n`` over 50 should clamp; we verify by inspecting the bind param."""
    engine = _mock_engine_for_rows([])
    query_top_rs_stocks(engine, n=999)
    # First positional call to conn.execute had a {"lim": 50} bind param.
    conn = engine.connect.return_value.__enter__.return_value
    args, _kwargs = conn.execute.call_args
    assert len(args) == 2
    bound = args[1]
    assert bound["lim"] == 50


def test_top_rs_stocks_clamps_n_to_at_least_1() -> None:
    engine = _mock_engine_for_rows([])
    query_top_rs_stocks(engine, n=0)
    conn = engine.connect.return_value.__enter__.return_value
    args, _ = conn.execute.call_args
    assert args[1]["lim"] == 1
