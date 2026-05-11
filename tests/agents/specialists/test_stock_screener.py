"""Tests for the Stock Screener specialist."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.agents.specialists.stock_screener import StockScreener


def _mock_engine(rows: list[dict]) -> MagicMock:
    conn = MagicMock()
    result = MagicMock()
    mappings = MagicMock()
    mappings.fetchall.return_value = rows
    mappings.fetchone.return_value = rows[0] if rows else None
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
    response.usage = MagicMock(prompt_tokens=200, completion_tokens=120)
    return response


def test_stock_screener_returns_ranked_names() -> None:
    rows = [
        {
            "symbol": "TCS",
            "company_name": "Tata Consultancy",
            "sector": "NIFTY IT",
            "tier": "T1",
            "rs_state": "Leader",
            "rs_pctile_3m": Decimal("92.0"),
            "momentum_state": "Strong",
            "state_since_date": date(2026, 5, 1),
        },
        {
            "symbol": "INFY",
            "company_name": "Infosys",
            "sector": "NIFTY IT",
            "tier": "T1",
            "rs_state": "Leader",
            "rs_pctile_3m": Decimal("88.0"),
            "momentum_state": "Strong",
            "state_since_date": date(2026, 5, 2),
        },
    ]
    engine = _mock_engine(rows)

    client = MagicMock()
    final = (
        "TCS ranks highly with a 3-month RS percentile of 92 and appears in "
        "the leaders table. INFY ranks next with a percentile of 88. Both "
        "register Strong momentum. Data as of 2026-05-02."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_top_rs_stocks", {"n": 5, "sector": "IT"})]),
        _mock_response(final),
    ]

    agent = StockScreener()
    result = agent.invoke("Top RS stocks in IT", engine=engine, client=client)

    assert "TCS" in result.narrative
    assert "INFY" in result.narrative
    assert result.agent_name == "stock_screener"


def test_stock_screener_empty_match() -> None:
    engine = _mock_engine([])
    client = MagicMock()
    final = (
        "No stocks match the requested criteria — the leaders table is empty "
        "for that filter. Data as of 2026-05-12."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_top_rs_stocks", {"sector": "ZZZ"})]),
        _mock_response(final),
    ]

    agent = StockScreener()
    result = agent.invoke("Top stocks in ZZZ", engine=engine, client=client)
    assert "no stocks" in result.narrative.lower() or "empty" in result.narrative.lower()
