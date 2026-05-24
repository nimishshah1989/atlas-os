"""v6 /v1/instrument/{iid} endpoint.

Per-instrument deep view: full 4-tenure conviction at latest snapshot
plus 30-day history of cell firings plus a list of similar instruments
that fired the same best rule_id in the last 30 days.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["instrument"])


class TenureConviction(BaseModel):
    tenure: str
    verdict: str
    eli5: str | None
    best_rule_id: str | None
    cell_definition_id: str | None
    ic: Decimal | None
    friction_adjusted_excess: Decimal | None
    conflict: bool


class HistoryPoint(BaseModel):
    snapshot_date: str
    tenure: str
    verdict: str
    best_rule_id: str | None


class SimilarInstrument(BaseModel):
    instrument_id: str
    symbol: str | None
    last_fired: str


class InstrumentResponse(BaseModel):
    data: dict[str, Any]
    meta: dict[str, Any]


_INSTRUMENT_META_SQL = text(
    """
    SELECT
        instrument_id::text AS instrument_id,
        symbol,
        company_name,
        sector,
        tier::text AS cap_tier
    FROM atlas.atlas_universe_stocks
    WHERE instrument_id::text = :iid
      AND effective_to IS NULL
    """
)

_LATEST_CONVICTION_SQL = text(
    """
    SELECT
        snapshot_date,
        tenure,
        verdict,
        eli5,
        best_rule_id::text AS best_rule_id,
        cell_definition_id::text AS cell_definition_id,
        ic,
        friction_adjusted_excess,
        conflict
    FROM atlas.atlas_conviction_daily
    WHERE instrument_id::text = :iid
      AND snapshot_date = (
          SELECT MAX(snapshot_date) FROM atlas.atlas_conviction_daily
          WHERE instrument_id::text = :iid
      )
    """
)

_HISTORY_SQL = text(
    """
    SELECT snapshot_date, tenure, verdict, best_rule_id::text AS best_rule_id
    FROM atlas.atlas_conviction_daily
    WHERE instrument_id::text = :iid
      AND snapshot_date >= :cutoff
    ORDER BY snapshot_date DESC, tenure
    """
)

_SIMILAR_SQL = text(
    """
    SELECT
        c.instrument_id::text AS instrument_id,
        u.symbol,
        MAX(c.snapshot_date) AS last_fired
    FROM atlas.atlas_conviction_daily c
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = c.instrument_id
     AND u.effective_to IS NULL
    WHERE c.best_rule_id::text = ANY(:rule_ids)
      AND c.snapshot_date >= :cutoff
      AND c.instrument_id::text <> :iid
    GROUP BY c.instrument_id, u.symbol
    ORDER BY last_fired DESC
    LIMIT 20
    """
)


@router.get("/instrument/{iid}", response_model=InstrumentResponse)
def get_instrument(iid: str) -> InstrumentResponse:
    """Return latest conviction, 30-day history, and similar instruments."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            meta_row = conn.execute(_INSTRUMENT_META_SQL, {"iid": iid}).first()
            if meta_row is None:
                raise HTTPException(status_code=404, detail=f"instrument_id {iid} not found")
            conviction_rows = conn.execute(_LATEST_CONVICTION_SQL, {"iid": iid}).mappings().all()
            if not conviction_rows:
                return InstrumentResponse(
                    data={
                        "instrument": {
                            "instrument_id": meta_row.instrument_id,
                            "symbol": meta_row.symbol,
                            "company_name": meta_row.company_name,
                            "sector": meta_row.sector,
                            "cap_tier": meta_row.cap_tier,
                        },
                        "conviction": [],
                        "history": [],
                        "similar": [],
                    },
                    meta={
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "degraded": True,
                        "note": "no conviction rows for this instrument yet",
                    },
                )
            latest_snapshot = conviction_rows[0]["snapshot_date"]
            cutoff = latest_snapshot - timedelta(days=30)
            history_rows = (
                conn.execute(_HISTORY_SQL, {"iid": iid, "cutoff": cutoff}).mappings().all()
            )
            rule_ids = [r["best_rule_id"] for r in conviction_rows if r["best_rule_id"]]
            similar_rows: list[Any] = []
            if rule_ids:
                similar_rows = (
                    conn.execute(
                        _SIMILAR_SQL,
                        {"rule_ids": rule_ids, "cutoff": cutoff, "iid": iid},
                    )
                    .mappings()
                    .all()
                )
    except OperationalError as exc:
        log.warning("instrument_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    conviction = [
        TenureConviction(
            tenure=r["tenure"],
            verdict=r["verdict"],
            eli5=r["eli5"],
            best_rule_id=r["best_rule_id"],
            cell_definition_id=r["cell_definition_id"],
            ic=r["ic"],
            friction_adjusted_excess=r["friction_adjusted_excess"],
            conflict=r["conflict"],
        ).model_dump(mode="json")
        for r in conviction_rows
    ]
    history = [
        HistoryPoint(
            snapshot_date=r["snapshot_date"].isoformat(),
            tenure=r["tenure"],
            verdict=r["verdict"],
            best_rule_id=r["best_rule_id"],
        ).model_dump(mode="json")
        for r in history_rows
    ]
    similar = [
        SimilarInstrument(
            instrument_id=r["instrument_id"],
            symbol=r["symbol"],
            last_fired=r["last_fired"].isoformat(),
        ).model_dump(mode="json")
        for r in similar_rows
    ]

    return InstrumentResponse(
        data={
            "instrument": {
                "instrument_id": meta_row.instrument_id,
                "symbol": meta_row.symbol,
                "company_name": meta_row.company_name,
                "sector": meta_row.sector,
                "cap_tier": meta_row.cap_tier,
            },
            "conviction": conviction,
            "history": history,
            "similar": similar,
        },
        meta={
            "data_as_of": latest_snapshot.isoformat(),
            "fetched_at": datetime.now(UTC).isoformat(),
            "history_days": 30,
        },
    )
