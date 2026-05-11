"""Tests for the SP07 base SpecialistAgent loop."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from atlas.agents.specialists.base import (
    MAX_ITERS,
    AgentResult,
    SEBIComplianceError,
    SpecialistAgent,
    _extract_data_as_of,
    _scan_banned_words,
    _shrink_result,
)


class _Agent(SpecialistAgent):
    name = "test_agent"
    description = "fixture for tests"
    tool_names = ("get_current_regime",)

    def build_system_prompt(self) -> str:
        return "test preamble"


def _mock_choice(content: str | None, tool_calls: list[Any] | None = None) -> Any:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    return choice


def _mock_response(
    content: str | None,
    tool_calls: list[Any] | None = None,
    in_tok: int = 100,
    out_tok: int = 50,
) -> Any:
    response = MagicMock()
    response.choices = [_mock_choice(content, tool_calls)]
    response.usage = MagicMock(prompt_tokens=in_tok, completion_tokens=out_tok)
    return response


def _tool_call(name: str, args: dict, tc_id: str = "tc_1") -> Any:
    tc = MagicMock()
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _mock_engine_returning_regime() -> MagicMock:
    """Mock engine whose query_current_regime returns Risk-On data."""
    conn = MagicMock()
    result = MagicMock()
    mappings = MagicMock()
    mappings.fetchone.return_value = {
        "date": date(2026, 5, 8),
        "regime_state": "Risk-On",
        "deployment_multiplier": "1.00",
        "dislocation_active": False,
        "india_vix": "13.2",
        "pct_above_ema_50": "78.4",
        "pct_above_ema_200": "65.0",
        "pct_in_strong_states": "48.0",
        "ad_ratio": "1.85",
        "net_new_highs": 47,
        "mcclellan_oscillator": "45.2",
    }
    result.mappings.return_value = mappings
    conn.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def test_loop_terminates_on_first_non_tool_message() -> None:
    """A response with no tool_calls ends the loop in 1 iteration."""
    agent = _Agent()
    narrative = "The market sits in a Risk-On regime with breadth strong. Data as of 2026-05-08."
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response(narrative)

    result = agent.invoke("test question", engine=MagicMock(), client=client)

    assert isinstance(result, AgentResult)
    assert result.iterations == 1
    assert result.narrative.startswith("The market sits")
    assert client.chat.completions.create.call_count == 1


def test_loop_executes_tool_call_then_terminates() -> None:
    """First response calls a tool; second returns final message."""
    agent = _Agent()
    engine = _mock_engine_returning_regime()

    client = MagicMock()
    # First call: model wants get_current_regime; second call: final message.
    final_text = "The market is in Risk-On state and shows breadth strength. Data as of 2026-05-08."
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_tool_call("get_current_regime", {})]),
        _mock_response(final_text),
    ]

    result = agent.invoke("regime?", engine=engine, client=client)

    assert result.iterations == 2
    assert "Risk-On" in result.narrative
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool"] == "get_current_regime"
    assert result.data_as_of == date(2026, 5, 8)


def test_loop_caps_at_max_iters() -> None:
    """Model that infinitely requests tool calls is cut off at MAX_ITERS."""
    agent = _Agent()
    engine = _mock_engine_returning_regime()
    client = MagicMock()
    # Every response wants a tool call — but final loop just records last
    # assistant message which may be empty; loop should raise the
    # "no final narrative" error.
    client.chat.completions.create.return_value = _mock_response(
        None, [_tool_call("get_current_regime", {})]
    )

    with pytest.raises(RuntimeError, match="no final narrative"):
        agent.invoke("regime?", engine=engine, client=client)

    # Should have iterated exactly MAX_ITERS times.
    assert client.chat.completions.create.call_count == MAX_ITERS


def test_banned_word_raises_sebi_error() -> None:
    """Final narrative containing a banned verb fails the scan."""
    agent = _Agent()
    bad_narrative = (
        "The market is in Risk-On. You should buy TCS aggressively. Data as of 2026-05-08."
    )
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response(bad_narrative)

    with pytest.raises(SEBIComplianceError, match="buy"):
        agent.invoke("regime?", engine=MagicMock(), client=client)


def test_scan_banned_words_whole_word_match() -> None:
    """``invest`` matches as a word; ``investment`` does not (no plural form)."""
    assert "buy" in _scan_banned_words("you should buy this")
    assert "invest" in _scan_banned_words("please invest now")
    # "buying" is not in BANNED_WORDS; "buy" inside it should NOT match.
    assert "buy" not in _scan_banned_words("there are buyers in the market")
    # Multi-word phrase
    assert "target price" in _scan_banned_words("Set a target price of 1500")


def test_empty_question_raises() -> None:
    agent = _Agent()
    with pytest.raises(ValueError, match="non-empty"):
        agent.invoke("", engine=MagicMock(), client=MagicMock())
    with pytest.raises(ValueError, match="non-empty"):
        agent.invoke("   ", engine=MagicMock(), client=MagicMock())


def test_extract_data_as_of_finds_most_recent() -> None:
    """The data_as_of extractor scans every tool result for the most recent date."""
    messages = [
        {
            "role": "tool",
            "content": json.dumps({"date": "2026-05-08", "regime_state": "Risk-On"}),
        },
        {
            "role": "tool",
            "content": json.dumps([{"as_of": "2026-05-09"}, {"as_of": "2026-05-07"}]),
        },
    ]
    result = _extract_data_as_of([], messages)
    assert result == date(2026, 5, 9)


def test_shrink_result_truncates_long_lists() -> None:
    long = list(range(50))
    out = _shrink_result(long, max_items=10)
    assert len(out) == 11  # 10 + truncation marker
    assert out[-1]["_truncated"] == 40


def test_tool_error_is_surfaced_to_model() -> None:
    """A tool that raises is reported back to the model, loop continues."""
    agent = _Agent()
    engine = MagicMock()
    # Make build_registry return a tool whose fn raises.
    from atlas.agents.specialists import base as base_mod

    def boom(**kwargs: Any) -> Any:
        raise RuntimeError("simulated DB outage")

    orig_build = base_mod.build_registry

    def _patched(_eng: Any) -> dict:
        reg = orig_build(_eng)
        from atlas.agents.tools.registry import Tool

        reg["get_current_regime"] = Tool(
            name="get_current_regime",
            description="x",
            parameters={"type": "object", "properties": {}},
            fn=boom,
        )
        return reg

    base_mod.build_registry = _patched  # type: ignore[assignment]
    try:
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _mock_response(None, [_tool_call("get_current_regime", {})]),
            _mock_response("Tool failed, but data as of 2026-05-08."),
        ]
        result = agent.invoke("regime?", engine=engine, client=client)
        assert result.iterations == 2
        assert "data as of" in result.narrative.lower()
    finally:
        base_mod.build_registry = orig_build  # type: ignore[assignment]
