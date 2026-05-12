"""POST /api/v1/stocks/{symbol}/cts_brief

Builds context from Atlas conviction + CTS signals and calls the Hermes
LLM agent to produce a one-paragraph decision brief. SEBI guard: no forward
return predictions, no explicit buy/sell instructions.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/stocks", tags=["cts"])

SEBI_GUARD = (
    "You are a research assistant for a SEBI-registered portfolio manager. "
    "You MUST NOT make explicit buy or sell recommendations. "
    "You MUST NOT predict forward returns. "
    "Describe the observable signal state only."
)

BRIEF_PROMPT = """\
Given the following data for {symbol}, write ONE paragraph (4-6 sentences) describing
the current technical and quantitative state. Focus on: Stage, recent CTS signal,
Atlas conviction tier, sector alignment, and RS rank. Do not recommend action.

Atlas data:
- Conviction tier: {conviction_tier}
- RS cross-sector percentile: {rs_pctile:.0%}
- Sector state: {sector_state}
- Market regime: {regime}

CTS signals (today):
- Weinstein stage: {stage}
- SMA 150 slope: {sma_slope_direction}
- Latest PPC: {last_ppc}
- Is contraction: {is_contraction} {trigger_info}
- TRP ratio: {trp_ratio:.2f}x avg

Sector PPC/NPC balance: {pivot_balance}
"""


class CTSBriefResponse(BaseModel):
    symbol: str
    brief: str
    context: dict


@router.post("/{symbol}/cts_brief", response_model=CTSBriefResponse)
async def get_cts_brief(symbol: str) -> CTSBriefResponse:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT
                    u.symbol,
                    c.conviction_score,
                    c.tier,
                    m.rs_pctile_3m,
                    sec.sector_state,
                    r.regime_state,
                    s.stage,
                    s.sma_150_slope,
                    s.is_ppc,
                    s.is_npc,
                    s.is_contraction,
                    s.trigger_level,
                    s.trp_ratio,
                    s.ppc_strength,
                    sp.pivot_balance
                FROM atlas.atlas_universe_stocks u
                LEFT JOIN atlas.atlas_stock_conviction_daily c
                    ON c.instrument_id = u.instrument_id
                    AND c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
                LEFT JOIN atlas.atlas_stock_metrics_daily m
                    ON m.instrument_id = u.instrument_id
                    AND m.date = (SELECT MAX(date) FROM atlas.atlas_stock_metrics_daily)
                LEFT JOIN atlas.atlas_cts_signals_daily s
                    ON s.instrument_id = u.instrument_id
                    AND s.date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
                LEFT JOIN atlas.atlas_market_regime_daily r
                    ON r.date = (SELECT MAX(date) FROM atlas.atlas_market_regime_daily)
                LEFT JOIN atlas.atlas_sector_states_daily sec
                    ON sec.sector_name = u.sector
                    AND sec.date = (SELECT MAX(date) FROM atlas.atlas_sector_states_daily)
                LEFT JOIN LATERAL (
                    SELECT p.pivot_balance
                    FROM atlas.atlas_cts_sector_pivot_daily p
                    WHERE p.sector = u.sector
                      AND p.date = (SELECT MAX(date) FROM atlas.atlas_cts_sector_pivot_daily)
                    LIMIT 1
                ) sp ON TRUE
                WHERE UPPER(u.symbol) = UPPER(:sym)
                  AND u.effective_to IS NULL
                LIMIT 1
            """),
            {"sym": symbol},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    ctx = dict(row._mapping)

    slope_dir = "rising" if (ctx.get("sma_150_slope") or 0) > 0 else "flat/declining"
    last_ppc = "None in recent window"
    if ctx.get("is_ppc"):
        last_ppc = f"Today (strength {float(ctx.get('ppc_strength') or 0):.2f})"

    trigger_info = ""
    if ctx.get("is_contraction") and ctx.get("trigger_level"):
        trigger_info = f"(trigger ₹{float(ctx['trigger_level']):.2f})"

    pivot = ctx.get("pivot_balance")
    pivot_str = f"{float(pivot) * 100:+.0f}%" if pivot else "no data"

    prompt = BRIEF_PROMPT.format(
        symbol=symbol.upper(),
        conviction_tier=ctx.get("tier") or "Not ranked",
        rs_pctile=float(ctx.get("rs_pctile_3m") or 0),
        sector_state=ctx.get("sector_state") or "Unknown",
        regime=ctx.get("regime_state") or "Unknown",
        stage=ctx.get("stage") or "N/A",
        sma_slope_direction=slope_dir,
        last_ppc=last_ppc,
        is_contraction=bool(ctx.get("is_contraction")),
        trigger_info=trigger_info,
        trp_ratio=float(ctx.get("trp_ratio") or 1.0),
        pivot_balance=pivot_str,
    )

    try:
        from atlas.agents.specialists.base import call_groq

        brief_text = await call_groq(system=SEBI_GUARD, user=prompt)
    except Exception as e:
        log.error("cts_brief_llm_failed", symbol=symbol, error=str(e))
        brief_text = "Brief unavailable — please try again."

    return CTSBriefResponse(symbol=symbol.upper(), brief=brief_text, context=ctx)
