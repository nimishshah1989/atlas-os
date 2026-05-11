"""Tests for the Claude wrapper. The Anthropic SDK is mocked; no network."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from atlas.intelligence.briefs.context import DailyMarketContext
from atlas.intelligence.briefs.generator import DailyBrief, generate_brief
from atlas.intelligence.briefs.prompts import PROMPT_VERSION, SYSTEM_PROMPT


def _sample_context() -> DailyMarketContext:
    return DailyMarketContext(
        as_of=date(2026, 5, 12),
        regime="Risk-On",
        regime_delta="unchanged",
        deployment_multiplier=Decimal("1.00"),
        breadth={
            "pct_above_ema_50": Decimal("78.4"),
            "mcclellan_oscillator": Decimal("45.2"),
            "ad_ratio": Decimal("1.85"),
            "net_new_highs": 47,
            "india_vix": Decimal("13.2"),
        },
        top_sectors=["NIFTY IT", "NIFTY AUTO", "NIFTY BANK"],
        rotating_out=["NIFTY PSE", "NIFTY FMCG", "NIFTY PHARMA"],
        new_breakouts=[
            {
                "symbol": "TCS",
                "company_name": "Tata Consultancy",
                "sector": "NIFTY IT",
                "new_rs_state": "Leader",
            },
        ],
        new_deteriorations=[
            {
                "symbol": "HUL",
                "company_name": "Hindustan Unilever",
                "sector": "NIFTY FMCG",
                "prior_rs_state": "Strong",
            },
        ],
    )


def _mock_anthropic_client(
    narrative_text: str,
    themes: list[str],
    summary: str,
    sectors: list[str],
    in_tok: int = 1200,
    out_tok: int = 380,
) -> MagicMock:
    """Build a mocked Anthropic Messages client whose .messages.create()
    returns a response with a tool_use content block carrying the structured
    output, plus a usage stub."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "emit_brief"
    tool_use_block.input = {
        "narrative": narrative_text,
        "key_themes": themes,
        "regime_summary": summary,
        "top_sector_mentions": sectors,
    }
    response = MagicMock()
    response.content = [tool_use_block]
    response.model = "claude-sonnet-4-6"
    response.usage = MagicMock(input_tokens=in_tok, output_tokens=out_tok)

    client = MagicMock()
    client.messages.create.return_value = response
    return client


def test_generate_brief_returns_dataclass() -> None:
    ctx = _sample_context()
    narrative = (
        "The market sits in a Risk-On regime with a deployment multiplier of "
        "1.00x, which calibrates position sizing toward full deployment. "
        "Breadth signals strength: 78.4% of the universe trades above its "
        "50-day EMA, the McClellan Oscillator registers a positive 45.2, "
        "and net new highs print at 47. NIFTY IT ranks highly in the RS "
        "framework alongside NIFTY AUTO and NIFTY BANK; Tata Consultancy "
        "appears in the breakouts list after transitioning into a Leader "
        "RS state. On the other side, NIFTY PSE, FMCG, and PHARMA show "
        "deterioration in relative-strength velocity, and Hindustan "
        "Unilever drops from a Strong classification. Notably, while "
        "breadth signals strength, India VIX has ticked up to 13.2, "
        "which historically precedes consolidation rather than expansion. "
        "The framework keeps deployment multiplier at 1.00x - full "
        "calibration to the current breadth and momentum readings."
    )
    client = _mock_anthropic_client(
        narrative_text=narrative,
        themes=[
            "Risk-On breadth confirmed",
            "IT and AUTO lead RS",
            "VIX uptick warrants attention",
        ],
        summary="bullish",
        sectors=["NIFTY IT", "NIFTY AUTO", "NIFTY BANK", "NIFTY PSE", "NIFTY FMCG"],
    )

    brief = generate_brief(ctx, client=client)

    assert isinstance(brief, DailyBrief)
    assert brief.narrative.startswith("The market sits")
    assert len(brief.key_themes) == 3
    assert brief.regime_summary == "bullish"
    assert "NIFTY IT" in brief.top_sector_mentions
    assert brief.model == "claude-sonnet-4-6"
    assert brief.prompt_version == PROMPT_VERSION
    assert brief.input_tokens == 1200
    assert brief.output_tokens == 380


def test_generator_sends_system_prompt_and_tool() -> None:
    ctx = _sample_context()
    client = _mock_anthropic_client(
        narrative_text="x " * 220,
        themes=["a", "b", "c"],
        summary="neutral",
        sectors=["NIFTY IT"],
    )

    generate_brief(ctx, client=client)

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 400
    # System prompt is the SEBI artifact, passed as a list block w/ cache_control
    system = kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["text"] == SYSTEM_PROMPT
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # Tool is the emit_brief schema
    tools = kwargs["tools"]
    assert tools[0]["name"] == "emit_brief"


def test_generator_user_message_includes_context_facts() -> None:
    ctx = _sample_context()
    client = _mock_anthropic_client(
        narrative_text="x " * 220,
        themes=["a", "b", "c"],
        summary="neutral",
        sectors=["NIFTY IT"],
    )

    generate_brief(ctx, client=client)

    kwargs = client.messages.create.call_args.kwargs
    user_text = kwargs["messages"][0]["content"]
    # The structured context must be in the message - JSON or labelled prose
    assert "Risk-On" in user_text
    assert "1.00" in user_text
    assert "NIFTY IT" in user_text
    assert "TCS" in user_text


def test_banned_words_enumerated_in_prompt() -> None:
    """The system prompt itself must list each banned word so Claude knows
    the SEBI ban explicitly."""
    lower = SYSTEM_PROMPT.lower()
    for word in ("buy", "sell", "invest", "recommend"):
        assert word in lower, f"prompt must enumerate ban for '{word}'"


def test_generator_output_contains_no_banned_phrasing() -> None:
    """If Claude returns banned words, the generator raises rather than
    silently persisting non-compliant prose."""
    ctx = _sample_context()
    bad_narrative = (
        "The market sits in a Risk-On regime. Investors should buy IT names "
        "aggressively today; we recommend overweight allocation."
    )
    client = _mock_anthropic_client(
        narrative_text=bad_narrative,
        themes=["a", "b", "c"],
        summary="bullish",
        sectors=["NIFTY IT"],
    )
    with pytest.raises(ValueError, match="banned"):
        generate_brief(ctx, client=client)


def test_generator_rejects_empty_context() -> None:
    empty_ctx = DailyMarketContext(
        as_of=date(2026, 5, 12),
        regime="Unknown",
        regime_delta="unchanged",
        deployment_multiplier=Decimal("0"),
        breadth={},
        top_sectors=[],
        rotating_out=[],
        new_breakouts=[],
        new_deteriorations=[],
    )
    client = MagicMock()
    with pytest.raises(ValueError, match="empty"):
        generate_brief(empty_ctx, client=client)
    client.messages.create.assert_not_called()
