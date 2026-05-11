"""Tests for the Sector Rotation Analyst specialist."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.agents.specialists.sector_rotation import SectorRotationAnalyst


def _mock_engine(rotation_rows: list[dict]) -> MagicMock:
    """Mock engine: every fetchall returns ``rotation_rows``, fetchone -> first."""
    conn = MagicMock()
    result = MagicMock()
    mappings = MagicMock()
    mappings.fetchall.return_value = rotation_rows
    mappings.fetchone.return_value = rotation_rows[0] if rotation_rows else None
    result.mappings.return_value = mappings
    conn.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def _mock_tool_call(name: str, args: dict, tc_id: str = "tc_1") -> MagicMock:
    tc = MagicMock()
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _mock_response(content: str | None, tool_calls: list | None = None) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=200, completion_tokens=80)
    return response


def test_sector_rotation_happy_path() -> None:
    """Mock tools returning 2 sectors; specialist produces a SEBI-safe narrative."""
    rotation_rows = [
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
    engine = _mock_engine(rotation_rows)

    client = MagicMock()
    final = (
        "NIFTY IT ranks highly in the RS framework and sits in the Leading "
        "quadrant. NIFTY FMCG shows deterioration and appears in the Lagging "
        "quadrant. Data as of 2026-05-08."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_sector_rotation_quadrants", {})]),
        _mock_response(final),
    ]

    agent = SectorRotationAnalyst()
    result = agent.invoke("Which sectors are leading?", engine=engine, client=client)

    assert "NIFTY IT" in result.narrative
    assert "Leading" in result.narrative
    assert result.agent_name == "sector_rotation"
    assert result.iterations == 2
    assert any(tc["tool"] == "get_sector_rotation_quadrants" for tc in result.tool_calls)


def test_sector_rotation_empty_mv_path() -> None:
    """When the MV returns no rows, the specialist still produces a clean
    narrative explaining data unavailability."""
    engine = _mock_engine([])

    client = MagicMock()
    final = (
        "Sector rotation data is not available — mv_sector_rotation_state "
        "returned no rows. The materialized view may require a refresh. "
        "Data as of 2026-05-08."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_sector_rotation_quadrants", {})]),
        _mock_response(final),
    ]

    agent = SectorRotationAnalyst()
    result = agent.invoke("Which sectors are rotating?", engine=engine, client=client)
    assert "not available" in result.narrative.lower() or "no rows" in result.narrative.lower()
    assert result.agent_name == "sector_rotation"
