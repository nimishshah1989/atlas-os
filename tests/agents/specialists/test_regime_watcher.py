"""Tests for the Regime Watcher specialist."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.agents.specialists.regime_watcher import RegimeWatcher


def _mock_engine(regime_row: dict | None, history_rows: list[dict] | None = None) -> MagicMock:
    """Mock engine: fetchone returns ``regime_row``; fetchall returns history."""
    conn = MagicMock()
    history_rows = history_rows or []

    def _execute(sql, *args, **kwargs) -> MagicMock:
        text_sql = str(sql)
        result = MagicMock()
        mappings = MagicMock()
        if "atlas_market_regime_daily" in text_sql:
            mappings.fetchall.return_value = history_rows
            mappings.fetchone.return_value = history_rows[0] if history_rows else None
        elif "atlas_daily_briefs" in text_sql:
            mappings.fetchone.return_value = None
            mappings.fetchall.return_value = []
        else:
            mappings.fetchone.return_value = regime_row
            mappings.fetchall.return_value = [regime_row] if regime_row else []
        result.mappings.return_value = mappings
        return result

    conn.execute.side_effect = _execute
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
    response.usage = MagicMock(prompt_tokens=180, completion_tokens=90)
    return response


def test_regime_watcher_risk_on_path() -> None:
    regime_row = {
        "date": date(2026, 5, 8),
        "regime_state": "Risk-On",
        "deployment_multiplier": Decimal("1.10"),
        "dislocation_active": False,
        "india_vix": Decimal("13.2"),
        "pct_above_ema_50": Decimal("78.4"),
        "pct_above_ema_200": Decimal("65.0"),
        "pct_in_strong_states": Decimal("48.0"),
        "ad_ratio": Decimal("1.85"),
        "net_new_highs": 47,
        "mcclellan_oscillator": Decimal("45.2"),
    }
    engine = _mock_engine(regime_row)
    client = MagicMock()
    final = (
        "The market is classified as Risk-On with a deployment multiplier "
        "of 1.10x, which calibrates position sizing. Breadth signals strength: "
        "78.4% of the universe trades above the 50-day EMA. Data as of 2026-05-08."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_current_regime", {})]),
        _mock_response(final),
    ]

    agent = RegimeWatcher()
    result = agent.invoke("What is the regime?", engine=engine, client=client)

    assert "Risk-On" in result.narrative
    assert "1.10" in result.narrative
    assert result.data_as_of == date(2026, 5, 8)
    assert result.agent_name == "regime_watcher"


def test_regime_watcher_unknown_regime_fallback() -> None:
    """When the MV row is missing, the specialist explains the gap."""
    engine = _mock_engine(None)
    client = MagicMock()
    final = (
        "Market regime data is not available — mv_current_market_regime "
        "returned no rows. Run the nightly pipeline and refresh the view. "
        "Data as of 2026-05-12."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_current_regime", {})]),
        _mock_response(final),
    ]

    agent = RegimeWatcher()
    result = agent.invoke("regime?", engine=engine, client=client)
    assert "not available" in result.narrative.lower() or "no rows" in result.narrative.lower()
