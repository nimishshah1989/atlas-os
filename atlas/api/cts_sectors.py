"""GET /api/v1/cts/sectors — Sector-level CTS momentum snapshot.

Returns the most recent date's sector pivot data with conviction metrics.
Derives momentum label: Bullish (pivot_balance >= 0.10), Bearish (<= -0.10), else Neutral.
"""

from __future__ import annotations

import asyncio
from datetime import date

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/cts", tags=["cts"])


class SectorCTSRow(BaseModel):
    sector: str
    date: date
    ppc_count: int
    npc_count: int
    total_tradeable: int
    stage2_count: int
    stage2_pct: float | None
    avg_ppc_conviction: float | None
    action_alert_count: int
    pivot_balance: float | None
    momentum: str  # "Bullish" | "Bearish" | "Neutral"


class SectorCTSResponse(BaseModel):
    data: list[SectorCTSRow]
    as_of_date: str


def _fetch_sector_pivot() -> list[dict]:
    engine = get_engine()
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT
                    sector,
                    date,
                    ppc_count,
                    npc_count,
                    total_tradeable,
                    COALESCE(stage2_count, 0)       AS stage2_count,
                    stage2_pct,
                    avg_ppc_conviction,
                    COALESCE(action_alert_count, 0) AS action_alert_count,
                    pivot_balance
                FROM atlas.atlas_cts_sector_pivot_daily
                WHERE date = (SELECT MAX(date) FROM atlas.atlas_cts_sector_pivot_daily)
                ORDER BY COALESCE(pivot_balance, 0) DESC
            """)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def _derive_momentum(pb: float | None) -> str:
    if pb is None:
        return "Neutral"
    if pb >= 0.10:
        return "Bullish"
    if pb <= -0.10:
        return "Bearish"
    return "Neutral"


@router.get("/sectors", response_model=SectorCTSResponse)
async def get_sector_cts() -> SectorCTSResponse:
    rows = await asyncio.to_thread(_fetch_sector_pivot)
    if not rows:
        raise HTTPException(status_code=404, detail="No sector pivot data available")

    as_of = str(rows[0]["date"])
    data = [
        SectorCTSRow(
            sector=r["sector"],
            date=r["date"],
            ppc_count=int(r["ppc_count"]),
            npc_count=int(r["npc_count"]),
            total_tradeable=int(r["total_tradeable"]),
            stage2_count=int(r["stage2_count"]),
            stage2_pct=float(r["stage2_pct"]) if r["stage2_pct"] is not None else None,
            avg_ppc_conviction=(
                float(r["avg_ppc_conviction"]) if r["avg_ppc_conviction"] is not None else None
            ),
            action_alert_count=int(r["action_alert_count"]),
            pivot_balance=float(r["pivot_balance"]) if r["pivot_balance"] is not None else None,
            momentum=_derive_momentum(
                float(r["pivot_balance"]) if r["pivot_balance"] is not None else None
            ),
        )
        for r in rows
    ]
    return SectorCTSResponse(data=data, as_of_date=as_of)
