from unittest.mock import MagicMock, patch

import pytest

from atlas.signals.narrative import _build_prompt, generate_narrative


def _context(**overrides) -> dict:
    base = {
        "ticker": "HDFCBANK",
        "company_name": "HDFC Bank Ltd.",
        "condition_label": "52-week high breakout with 1.5x volume",
        "conviction_score": 8.4,
        "conviction_trend": "rising",
        "cts_state": "BUY Stage 2",
        "rs_rank": 12,
        "rs_rank_total": 487,
        "rs_percentile": 97.5,
        "sector": "Banking",
        "sector_regime": "Bullish Expansion",
        "market_regime": "Risk-On",
        "rsi_14": 61.2,
        "macd_signal": "above_zero",
        "ema_alignment": "all_bullish",
        "hh_hl_state": "confirmed_uptrend",
        "volume_vs_avg": 2.3,
        "perf_vs_nifty_ytd": 22.7,
    }
    base.update(overrides)
    return base


def test_build_prompt_contains_ticker():
    prompt = _build_prompt(_context())
    assert "HDFCBANK" in prompt
    assert "HDFC Bank Ltd." in prompt


def test_build_prompt_contains_condition():
    prompt = _build_prompt(_context())
    assert "52-week high breakout" in prompt


def test_build_prompt_handles_missing_conviction():
    ctx = _context(
        conviction_score=None,
        cts_state=None,
        rs_rank=None,
        rs_rank_total=None,
        rs_percentile=None,
    )
    prompt = _build_prompt(ctx)
    assert "HDFCBANK" in prompt
    assert "not available" in prompt


@pytest.mark.asyncio
async def test_generate_narrative_calls_llm_and_returns_string():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "The setup appears bullish. HDFC Bank has broken out."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = MagicMock(return_value=mock_response)

    with patch("atlas.signals.narrative._get_client", return_value=mock_client):
        result = await generate_narrative(_context())

    assert isinstance(result, str)
    assert len(result) > 10


@pytest.mark.asyncio
async def test_generate_narrative_returns_fallback_on_error():
    with patch("atlas.signals.narrative._get_client", side_effect=Exception("API down")):
        result = await generate_narrative(_context())
    assert result.startswith("Technical signal")
