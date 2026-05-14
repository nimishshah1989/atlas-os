# Uses Groq Llama 3.3 70B (already in project via SP07) — zero API cost at Atlas volume.
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 700

_SYSTEM = """\
You are a senior equity analyst at a top-tier institutional research firm. You write signal notes \
that portfolio managers read in 45 seconds and immediately understand the setup.

STYLE (non-negotiable):
• Open with a bold, specific verdict: "The setup in TICKER is unambiguously bullish." or \
"This is a textbook stage-2 breakout with Atlas confirmation." or \
"TICKER has completed a six-month inverse head-and-shoulders base."
• Name the chart pattern explicitly using institutional vocabulary: inverse head & shoulders, \
cup-and-handle, false breakdown / shake-out, higher-high/higher-low uptrend confirmation, \
stage-2 breakout, stage-3 topping, ascending triangle, bull flag, saucer base, three-weeks-tight.
• Cite specific numbers assertively. Not "strong RS" → "RS at the 94th percentile of the Nifty 500."
• Cross-reference the TV trigger with Atlas intelligence in every note. \
If dual-confirmed: say both layers agree and why. \
If TV-only: name the gap (e.g., "conviction sits below the 6/10 Atlas threshold") and what \
closes it.
• State a forward expectation with a specific price structure or condition: \
"A weekly close above the prior swing high would confirm the larger base breakout." \
"Watch for a volume expansion on the next up-bar to validate the move."
• Never hedge without resolving: "may" and "could" only if immediately followed by the \
specific condition that resolves the uncertainty.

FORMAT: Three tight paragraphs, ~180 words total. Dense, zero padding.
  Para 1: Pattern diagnosis + TV trigger interpretation.
  Para 2: Atlas intelligence cross-reference (conviction, CTS stage, RS rank, regime context).
  Para 3: Forward expectation — what happens next, what confirms, what invalidates.

FIELD INTERPRETATIONS (use these translations in your prose):
ema_alignment:
  all_bullish → "price above the 20/50/200-day EMA stack — textbook stage-2 alignment"
  bullish → "price above the 50 and 200-day EMAs, intermediate trend intact"
  mixed → "EMAs not yet aligned — pending confirmation"
  bearish / all_bearish → "price below the EMA stack — distribution phase"

hh_hl_state:
  confirmed_uptrend / HH+HL → "confirmed higher-high/higher-low uptrend structure on daily bars"
  neutral / mixed → "swing structure not yet resolved — watch for the next HH"
  confirmed_downtrend / LL+LH → "lower-low/lower-high downtrend structure — distribution"

macd_signal:
  bullish_cross_above_zero → "MACD bullish crossover above zero — momentum firmly net positive"
  bullish_cross → "MACD bullish crossover — momentum inflecting upward"
  bearish_cross → "MACD bearish crossover — momentum rolling over"
  bullish / positive → "MACD positive — underlying bid present"
  neutral → "MACD near zero — momentum ambiguous"

cts_state (pre-translated to label before being passed to you):
  "CTS Stage 1 — early accumulation" → high risk/reward entry zone, patient accumulation area
  "CTS Stage 2 — mid-cycle" → institutional accumulation well underway, price action confirming
  "CTS Stage 3 — momentum phase" → late-cycle momentum, tight stops warranted
  "CTS Stage 4 — distribution / avoid" → distribution underway — bearish divergence from
    TV buy trigger; flag this conflict explicitly
  not available → CTS data unavailable, do not fabricate CTS context

confirmation_level:
  dual → "Atlas dual-confirmed: the quantitative layer agrees with the TV trigger"
  tv_only → "TV trigger only — not yet Atlas-dual-confirmed; conviction or RS needs to strengthen"

RS percentile:
  ≥90 → "top-decile RS — the stock is leading the market"
  ≥75 → "top-quartile RS — clear market leadership"
  ≥60 → "above-median RS — modest relative strength"
  <60 → "below-median RS — relative underperformer"

conviction_score (displayed 0–10, stored as 0–1 fraction × 10):
  ≥8 → "high-conviction (industry-grade)"
  ≥6 → "moderate-conviction"
  ≥4 → "low-conviction"
  <4 → "sub-threshold conviction — do not overweight the signal"

RS percentile (displayed 0–100):
  ≥90 → "top-decile RS — the stock is leading the market"
  ≥75 → "top-quartile RS — clear market leadership"
  ≥60 → "above-median RS — modest relative strength"
  <60 → "below-median RS — relative underperformer"

conviction_quality field:
  "industry_grade" → add "(industry-grade)" to conviction description
  "baseline" → baseline conviction model
"""

_USER_TEMPLATE = """\
Generate a signal note for the following setup:

INSTRUMENT: {ticker} ({company_name}) — {exchange}
TRIGGER: {condition_label}
CONFIRMATION: {confirmation_level}
VERDICT: {verdict}

--- ATLAS INTELLIGENCE ---
Conviction: {conviction_score_str}
CTS State: {cts_state_str}
RS Rank: {rs_rank_str}
Market Regime: {market_regime}
Sector ({sector}): {sector_regime}

--- TECHNICAL SNAPSHOT ---
RSI(14): {rsi_14:.1f}
MACD: {macd_signal}
EMA Alignment: {ema_alignment}
Structure: {hh_hl_state}
Volume vs 20d avg: {volume_vs_avg:.1f}×

--- PERFORMANCE ---
1M: {perf_1m}  |  3M: {perf_3m}  |  6M: {perf_6m}  |  YTD: {perf_ytd}
vs Nifty 1M: {perf_vs_nifty_1m}  |  vs Nifty YTD: {perf_vs_nifty_ytd}
"""


def _fmt_pct(v: Any, decimals: int = 1) -> str:
    if v is None:
        return "n/a"
    try:
        n = float(v)
        return f"{n:+.{decimals}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _build_prompt(ctx: dict) -> str:
    # conviction_score is stored 0–1; display as 0–10
    conviction_score = ctx.get("conviction_score")
    conviction_quality = ctx.get(
        "conviction_trend", ""
    )  # field is confidence_label: "industry_grade"/"baseline"
    if conviction_score is not None:
        score_10 = float(conviction_score) * 10
        quality_str = f" ({conviction_quality})" if conviction_quality else ""
        conviction_score_str = f"{score_10:.1f}/10{quality_str}"
    else:
        conviction_score_str = "not available"

    cts_state = ctx.get("cts_state")
    cts_state_str = cts_state if cts_state else "not available"

    # rs_percentile is stored 0–1; display as 0–100
    rs_rank = ctx.get("rs_rank")
    rs_rank_total = ctx.get("rs_rank_total")
    rs_percentile = ctx.get("rs_percentile")
    if rs_rank is not None and rs_percentile is not None:
        pct_100 = float(rs_percentile) * 100
        total_str = f" of {rs_rank_total}" if rs_rank_total else ""
        rs_rank_str = f"#{rs_rank}{total_str} ({pct_100:.0f}th percentile)"
    elif rs_percentile is not None:
        pct_100 = float(rs_percentile) * 100
        rs_rank_str = f"{pct_100:.0f}th percentile"
    else:
        rs_rank_str = "not available"

    return _USER_TEMPLATE.format(
        ticker=ctx.get("ticker", ""),
        company_name=ctx.get("company_name", ""),
        exchange=ctx.get("exchange", "NSE"),
        condition_label=ctx.get("condition_label", ""),
        confirmation_level=ctx.get("confirmation_level", "tv_only"),
        verdict=ctx.get("verdict", "watch"),
        conviction_score_str=conviction_score_str,
        cts_state_str=cts_state_str,
        rs_rank_str=rs_rank_str,
        market_regime=ctx.get("market_regime") or "unknown",
        sector=ctx.get("sector") or "Unknown",
        sector_regime=ctx.get("sector_regime") or "unknown",
        rsi_14=float(ctx.get("rsi_14") or 50.0),
        macd_signal=ctx.get("macd_signal") or "neutral",
        ema_alignment=ctx.get("ema_alignment") or "mixed",
        hh_hl_state=ctx.get("hh_hl_state") or "neutral",
        volume_vs_avg=float(ctx.get("volume_vs_avg") or 1.0),
        perf_1m=_fmt_pct(ctx.get("perf_1m")),
        perf_3m=_fmt_pct(ctx.get("perf_3m")),
        perf_6m=_fmt_pct(ctx.get("perf_6m")),
        perf_ytd=_fmt_pct(ctx.get("perf_ytd")),
        perf_vs_nifty_1m=_fmt_pct(ctx.get("perf_vs_nifty_1m")),
        perf_vs_nifty_ytd=_fmt_pct(ctx.get("perf_vs_nifty_ytd")),
    )


def _get_client() -> Any:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai SDK not installed. Run: pip install 'openai>=1.50'") from e
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


async def generate_narrative(ctx: dict) -> str:
    user_msg = _build_prompt(ctx)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
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
