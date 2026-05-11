"""Tests for the four query handlers.

Each handler is tested with:
- Happy path: mock returns realistic rows → verify SSE events emitted
- Empty path: mock returns no rows → verify graceful fallback message_chunk

DB is fully mocked — no live connection needed. We mock ``engine.connect()`` to
return a context manager whose ``execute().mappings().fetchall()/fetchone()``
returns controlled test data.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import MagicMock

from atlas.api.openbb.handlers.breakouts import handle_breakouts
from atlas.api.openbb.handlers.leaders import handle_leaders
from atlas.api.openbb.handlers.regime import handle_regime
from atlas.api.openbb.handlers.rotation import handle_rotation


def _collect(async_gen: AsyncGenerator[dict, None]) -> list[dict]:
    """Drain an async generator synchronously for test assertions."""

    async def _drain() -> list[dict]:
        return [item async for item in async_gen]

    return asyncio.new_event_loop().run_until_complete(_drain())


def _parse_events(events: list[dict]) -> list[dict]:
    """Parse the JSON ``data`` field from each SSE event dict."""
    return [json.loads(e["data"]) for e in events]


def _mock_engine(rows: Any, fetchone: bool = False) -> MagicMock:
    """Build a minimal SQLAlchemy engine mock."""
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    mappings = MagicMock()

    if fetchone:
        mappings.fetchone.return_value = rows
    else:
        mappings.fetchall.return_value = rows or []

    result.mappings.return_value = mappings
    conn.execute.return_value = result
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn
    return engine


class TestRegimeHandler:
    def test_happy_path_emits_table_event(self) -> None:
        row = {
            "date": date(2026, 5, 12),
            "regime_state": "Risk-On",
            "deployment_multiplier": "1.00",
            "dislocation_active": False,
            "india_vix": "13.5",
            "pct_above_ema_50": "0.72",
            "pct_above_ema_200": "0.65",
            "pct_in_strong_states": "0.48",
            "ad_ratio": "1.8",
            "net_new_highs": 42,
            "mcclellan_oscillator": "25.4",
        }
        engine = _mock_engine(row, fetchone=True)
        events = _collect(handle_regime(engine, "show me regime"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "reasoning_step" in types
        assert "message_chunk" in types
        assert "table" in types
        assert "done" in types

    def test_empty_view_emits_fallback_message(self) -> None:
        engine = _mock_engine(None, fetchone=True)
        events = _collect(handle_regime(engine, "regime"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "message_chunk" in types
        # No table event when view is empty
        assert "table" not in types

    def test_narrative_is_sebi_compliant(self) -> None:
        """Narrative must not contain banned investment verbs."""
        row = {
            "date": date(2026, 5, 12),
            "regime_state": "Risk-Off",
            "deployment_multiplier": "0.50",
            "dislocation_active": False,
            "india_vix": "22.0",
            "pct_above_ema_50": "0.30",
            "pct_above_ema_200": "0.28",
            "pct_in_strong_states": "0.12",
            "ad_ratio": "0.6",
            "net_new_highs": -15,
            "mcclellan_oscillator": "-40.1",
        }
        engine = _mock_engine(row, fetchone=True)
        events = _collect(handle_regime(engine, "regime"))
        all_text = " ".join(
            e["data"] for e in _parse_events(events) if e.get("type") == "message_chunk"
        )
        for banned in ("buy", "sell", "invest", "recommend", "advise"):
            assert banned not in all_text.lower(), f"SEBI violation: '{banned}' in narrative"


class TestLeadersHandler:
    def test_happy_path_emits_table(self) -> None:
        rows = [
            {
                "symbol": "TCS",
                "company_name": "Tata Consultancy Services",
                "sector": "IT",
                "tier": "Large",
                "rs_state": "Leader",
                "rs_pctile_3m": "0.95",
                "rs_3m_nifty500": "1.15",
                "momentum_state": "Strong Uptrend",
                "state_since_date": date(2026, 4, 1),
            },
            {
                "symbol": "INFY",
                "company_name": "Infosys",
                "sector": "IT",
                "tier": "Large",
                "rs_state": "Strong",
                "rs_pctile_3m": "0.88",
                "rs_3m_nifty500": "1.08",
                "momentum_state": "Uptrend",
                "state_since_date": date(2026, 4, 10),
            },
        ]
        engine = _mock_engine(rows)
        events = _collect(handle_leaders(engine, "top RS stocks"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "table" in types

    def test_empty_view_emits_fallback(self) -> None:
        engine = _mock_engine([])
        events = _collect(handle_leaders(engine, "leaders"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "message_chunk" in types
        assert "table" not in types


class TestRotationHandler:
    def test_happy_path_emits_table_and_chart(self) -> None:
        rows = [
            {
                "sector_name": "IT",
                "rrg_quadrant": "Leading",
                "rs_level": "1.05",
                "rs_velocity": "0.03",
                "rs_pctile_cross_sector": "0.85",
                "sector_state": "Overweight",
                "bottomup_rs_state": "Strong",
                "bottomup_momentum_state": "Strong",
                "participation_rs_pct": "0.72",
                "constituent_count": 38,
                "date": date(2026, 5, 12),
            },
            {
                "sector_name": "FMCG",
                "rrg_quadrant": "Lagging",
                "rs_level": "0.92",
                "rs_velocity": "-0.04",
                "rs_pctile_cross_sector": "0.15",
                "sector_state": "Underweight",
                "bottomup_rs_state": "Weak",
                "bottomup_momentum_state": "Downtrend",
                "participation_rs_pct": "0.18",
                "constituent_count": 12,
                "date": date(2026, 5, 12),
            },
        ]
        engine = _mock_engine(rows)
        events = _collect(handle_rotation(engine, "sector rotation"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "table" in types
        assert "chart" in types

    def test_empty_view_emits_fallback(self) -> None:
        engine = _mock_engine([])
        events = _collect(handle_rotation(engine, "rotation"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "message_chunk" in types
        assert "table" not in types


class TestBreakoutsHandler:
    def test_happy_path_emits_table(self) -> None:
        rows = [
            {
                "symbol": "RELIANCE",
                "company_name": "Reliance Industries",
                "sector": "Energy",
                "tier": "Large",
                "new_rs_state": "Leader",
                "prior_rs_state": "Strong",
                "rs_pctile_3m": "0.91",
                "rs_3m_nifty500": "1.12",
                "momentum_state": "Strong Uptrend",
                "state_since_date": date(2026, 5, 12),
            },
        ]
        engine = _mock_engine(rows)
        events = _collect(handle_breakouts(engine, "breakout candidates"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "table" in types

    def test_empty_view_emits_fallback(self) -> None:
        engine = _mock_engine([])
        events = _collect(handle_breakouts(engine, "breakouts"))
        parsed = _parse_events(events)
        types = [e["type"] for e in parsed]
        assert "message_chunk" in types
        assert "table" not in types
