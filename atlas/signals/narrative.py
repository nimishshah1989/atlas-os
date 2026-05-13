# Uses Groq Llama 3.3 70B (already in project via SP07) — zero API cost at Atlas volume.
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 300

_PROMPT_TEMPLATE = (
    "You are an experienced equity analyst writing a one-paragraph investment brief.\n"
    'Be direct and opinionated. Lead with a clear verdict ("The setup appears bullish"'
    ' or "This chart is flashing a warning").\n'
    "Explain what the technical trigger means in the context of the stock's"
    " quantitative profile.\n"
    "Do not hedge excessively. Reference specific numbers. 3-4 sentences maximum.\n"
    "\n"
    "Stock: {ticker} ({company_name})\n"
    "Trigger: {condition_label}\n"
    "{conviction_line}\n"
    "{cts_line}\n"
    "{rs_line}\n"
    "Sector: {sector} — {sector_regime}\n"
    "Market: {market_regime}\n"
    "RSI(14): {rsi_14:.1f}\n"
    "MACD: {macd_signal}\n"
    "EMA Alignment: {ema_alignment}\n"
    "HH/HL State: {hh_hl_state}\n"
    "Volume vs 20-day avg: {volume_vs_avg:.1f}x\n"
    "Performance vs Nifty (YTD): {perf_vs_nifty_ytd:+.1f}%"
)


def _build_prompt(ctx: dict) -> str:
    conviction_line = (
        f"Conviction: {ctx['conviction_score']}/10" f" ({ctx.get('conviction_trend', 'stable')})"
        if ctx.get("conviction_score") is not None
        else "Conviction: not available"
    )
    cts_line = (
        f"CTS State: {ctx['cts_state']}" if ctx.get("cts_state") else "CTS State: not available"
    )
    rs_line = (
        f"RS Rank: #{ctx['rs_rank']} of {ctx['rs_rank_total']}"
        f" ({ctx['rs_percentile']:.1f}th percentile)"
        if ctx.get("rs_rank") is not None
        else "RS Rank: not available"
    )
    return _PROMPT_TEMPLATE.format(
        ticker=ctx.get("ticker", ""),
        company_name=ctx.get("company_name", ""),
        condition_label=ctx.get("condition_label", ""),
        conviction_line=conviction_line,
        cts_line=cts_line,
        rs_line=rs_line,
        sector=ctx.get("sector", "Unknown"),
        sector_regime=ctx.get("sector_regime", "Unknown"),
        market_regime=ctx.get("market_regime", "Unknown"),
        rsi_14=ctx.get("rsi_14", 50.0),
        macd_signal=ctx.get("macd_signal", "neutral"),
        ema_alignment=ctx.get("ema_alignment", "mixed"),
        hh_hl_state=ctx.get("hh_hl_state", "neutral"),
        volume_vs_avg=ctx.get("volume_vs_avg", 1.0),
        perf_vs_nifty_ytd=ctx.get("perf_vs_nifty_ytd", 0.0),
    )


def _get_client() -> Any:
    """Return an OpenAI-compatible client pointed at Groq's API.

    Uses the same pattern as atlas.agents.specialists.base._make_groq_client —
    openai SDK with Groq base URL. The groq SDK is not installed; openai is.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai SDK not installed. Run: pip install 'openai>=1.50'") from e
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Get one at console.groq.com.")
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


async def generate_narrative(ctx: dict) -> str:
    prompt = _build_prompt(ctx)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        log.exception("narrative_generation_failed", ticker=ctx.get("ticker"))
        label = ctx.get("condition_label", "technical signal")
        ticker = ctx.get("ticker", "")
        return (
            f"Technical signal for {ticker}: {label}. "
            "Atlas intelligence layer shows additional context in the metrics above."
        )
