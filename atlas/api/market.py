"""v6 /v1/market.regime endpoint.

Reads atlas_regime_daily for the latest state + 252-day history and the
preferred cells under the current regime (derived from
atlas_cell_definitions.confidence_by_regime).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["market"])


class RegimePoint(BaseModel):
    date: date
    state: str
    smallcap_rs_z: Decimal | None
    breadth_pct_above_200dma: Decimal | None
    vix_percentile: Decimal | None


class RegimePreferredCell(BaseModel):
    cell_id: str
    cap_tier: str
    action: str
    tenure: str
    confidence: Decimal | None


class MarketRegimeResponse(BaseModel):
    data: dict[str, Any]
    meta: dict[str, Any]


_LATEST_REGIME_SQL = text(
    """
    SELECT date, state::text AS state, smallcap_rs_z, breadth_pct_above_200dma,
           vix_percentile, cross_sectional_dispersion
    FROM atlas.atlas_regime_daily
    ORDER BY date DESC
    LIMIT 1
    """
)

_REGIME_HISTORY_SQL = text(
    """
    SELECT date, state::text AS state, smallcap_rs_z, breadth_pct_above_200dma,
           vix_percentile
    FROM atlas.atlas_regime_daily
    WHERE date >= (SELECT MAX(date) FROM atlas.atlas_regime_daily) - INTERVAL '252 days'
    ORDER BY date
    """
)

_PREFERRED_CELLS_SQL = text(
    """
    SELECT
        cell_id::text AS cell_id,
        cap_tier::text AS cap_tier,
        action::text AS action,
        tenure::text AS tenure,
        confidence_by_regime
    FROM atlas.atlas_cell_definitions
    WHERE deprecated_at IS NULL
      AND action = 'POSITIVE'
    """
)


@router.get("/market.regime", response_model=MarketRegimeResponse)
def market_regime() -> MarketRegimeResponse:
    """Return latest regime + 252d history + cells preferred under current state."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            latest_row = conn.execute(_LATEST_REGIME_SQL).first()
            if latest_row is None:
                return MarketRegimeResponse(
                    data={"current": None, "history": [], "preferred_cells": []},
                    meta={
                        "data_as_of": None,
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "degraded": True,
                        "note": "no regime rows yet",
                    },
                )
            current_state = latest_row.state
            history_rows = conn.execute(_REGIME_HISTORY_SQL).mappings().all()
            cell_rows = conn.execute(_PREFERRED_CELLS_SQL).mappings().all()
    except OperationalError as exc:
        log.warning("market_regime_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    preferred: list[RegimePreferredCell] = []
    for row in cell_rows:
        cbr = row["confidence_by_regime"] or {}
        conf = cbr.get(current_state) if isinstance(cbr, dict) else None
        if conf is None:
            continue
        preferred.append(
            RegimePreferredCell(
                cell_id=row["cell_id"],
                cap_tier=row["cap_tier"],
                action=row["action"],
                tenure=row["tenure"],
                confidence=Decimal(str(conf)),
            )
        )
    preferred.sort(key=lambda c: float(c.confidence or 0), reverse=True)

    history = [
        RegimePoint(
            date=r["date"],
            state=r["state"],
            smallcap_rs_z=r["smallcap_rs_z"],
            breadth_pct_above_200dma=r["breadth_pct_above_200dma"],
            vix_percentile=r["vix_percentile"],
        )
        for r in history_rows
    ]
    return MarketRegimeResponse(
        data={
            "current": {
                "date": latest_row.date.isoformat(),
                "state": current_state,
                "smallcap_rs_z": (
                    str(latest_row.smallcap_rs_z) if latest_row.smallcap_rs_z is not None else None
                ),
                "breadth_pct_above_200dma": (
                    str(latest_row.breadth_pct_above_200dma)
                    if latest_row.breadth_pct_above_200dma is not None
                    else None
                ),
                "vix_percentile": (
                    str(latest_row.vix_percentile)
                    if latest_row.vix_percentile is not None
                    else None
                ),
            },
            "history": [h.model_dump(mode="json") for h in history],
            "preferred_cells": [p.model_dump(mode="json") for p in preferred[:24]],
        },
        meta={
            "data_as_of": latest_row.date.isoformat(),
            "fetched_at": datetime.now(UTC).isoformat(),
            "history_points": len(history),
        },
    )
