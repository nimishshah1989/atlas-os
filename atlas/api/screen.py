"""v6 /v1 screen endpoints — stocks, etfs, funds, sectors.

These read from the daily conviction tape (``atlas_conviction_daily``)
plus the universe tables (``atlas_universe_stocks`` / ``atlas_universe_etfs``)
and return a Pydantic v2-shaped envelope per CLAUDE.md conventions:

    {"data": [...], "meta": {"data_as_of": ..., "fetched_at": ..., ...}}

All four endpoints share the same conviction-tape query primitive — they
just filter / project / join differently. Cursor pagination uses an
opaque base64-encoded ``(instrument_id, snapshot_date)`` tuple.
"""

# allow-large: four sibling endpoints with shared envelope shape, shared
# universe-tape join, and shared cursor primitive. Splitting them across
# files would duplicate the envelope helpers and dilute review focus on
# the single conviction-tape contract that this module enforces.

from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["screen"])


# ---------------------------------------------------------------------------
# Pydantic response shapes
# ---------------------------------------------------------------------------


class ConvictionByTenure(BaseModel):
    tenure: str
    verdict: str
    eli5: str | None
    ic: Decimal | None
    friction_adjusted_excess: Decimal | None
    conflict: bool


class StockRow(BaseModel):
    instrument_id: str
    symbol: str
    company_name: str | None
    sector: str
    cap_tier: str
    conviction: list[ConvictionByTenure]


class ScreenStocksResponse(BaseModel):
    data: list[StockRow]
    meta: dict[str, Any]


class ETFRow(BaseModel):
    ticker: str
    etf_name: str | None
    theme: str
    linked_sector: str | None
    conviction: list[ConvictionByTenure]


class ScreenETFsResponse(BaseModel):
    data: list[ETFRow]
    meta: dict[str, Any]


class FundRow(BaseModel):
    fund_id: str
    fund_name: str
    aum_inr_cr: Decimal | None
    avg_conviction_score: Decimal | None
    note: str | None


class ScreenFundsResponse(BaseModel):
    data: list[FundRow]
    meta: dict[str, Any]


class SectorRow(BaseModel):
    sector: str
    strength_rank: int | None
    breadth_pos: Decimal | None
    top_constituents: list[dict[str, Any]]


class ScreenSectorsResponse(BaseModel):
    data: list[SectorRow]
    meta: dict[str, Any]


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(instrument_id: str, snapshot_date: date) -> str:
    raw = json.dumps({"iid": instrument_id, "d": snapshot_date.isoformat()})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, date]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        obj = json.loads(decoded)
        return str(obj["iid"]), date.fromisoformat(obj["d"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid cursor: {exc!r}") from exc


# ---------------------------------------------------------------------------
# SQL primitives
# ---------------------------------------------------------------------------

_LATEST_SNAPSHOT_SQL = text(
    """
    SELECT MAX(snapshot_date) AS d FROM atlas.atlas_conviction_daily
    """
)


_CONVICTION_FOR_INSTRUMENTS_SQL = text(
    """
    SELECT
        c.instrument_id::text AS instrument_id,
        c.tenure,
        c.verdict,
        c.eli5,
        c.ic,
        c.friction_adjusted_excess,
        c.conflict
    FROM atlas.atlas_conviction_daily c
    WHERE c.snapshot_date = :snapshot_date
      AND c.instrument_id::text = ANY(:instrument_ids)
    """
)


_STOCKS_PAGE_SQL = text(
    """
    SELECT DISTINCT
        u.instrument_id::text AS instrument_id,
        u.symbol,
        u.company_name,
        u.sector,
        u.tier::text AS cap_tier
    FROM atlas.atlas_conviction_daily c
    JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = c.instrument_id
     AND u.effective_to IS NULL
    WHERE c.snapshot_date = :snapshot_date
      AND (:cap_tier_filter IS NULL OR u.tier::text = :cap_tier_filter)
      AND (:sector_filter IS NULL OR u.sector = :sector_filter)
      AND (:after_iid IS NULL OR u.instrument_id::text > :after_iid)
    ORDER BY u.instrument_id::text
    LIMIT :page_size
    """
)


def _meta(snapshot_date: date, **extra: Any) -> dict[str, Any]:
    return {
        "data_as_of": snapshot_date.isoformat(),
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "atlas_conviction_daily",
        **extra,
    }


def _fetch_conviction_rows(
    conn: Any, snapshot_date: date, instrument_ids: list[str]
) -> dict[str, list[ConvictionByTenure]]:
    """Pull conviction rows for a batch of instruments → per-iid list."""
    rows = conn.execute(
        _CONVICTION_FOR_INSTRUMENTS_SQL,
        {"snapshot_date": snapshot_date, "instrument_ids": instrument_ids},
    ).mappings()
    out: dict[str, list[ConvictionByTenure]] = {iid: [] for iid in instrument_ids}
    for r in rows:
        out.setdefault(r["instrument_id"], []).append(
            ConvictionByTenure(
                tenure=r["tenure"],
                verdict=r["verdict"],
                eli5=r["eli5"],
                ic=r["ic"],
                friction_adjusted_excess=r["friction_adjusted_excess"],
                conflict=r["conflict"],
            )
        )
    return out


def _latest_snapshot_date(conn: Any) -> date | None:
    row = conn.execute(_LATEST_SNAPSHOT_SQL).first()
    return row.d if row and row.d else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/screen.stocks", response_model=ScreenStocksResponse)
def screen_stocks(
    cap_tier: Annotated[str | None, Query(description="Large/Mid/Small filter")] = None,
    sector: Annotated[str | None, Query(description="Sector name filter")] = None,
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ScreenStocksResponse:
    """Paginated screen of stocks with per-tenure conviction verdicts."""
    after_iid: str | None = None
    if cursor:
        after_iid, _ = _decode_cursor(cursor)
    try:
        engine = get_engine()
        with engine.connect() as conn:
            snapshot = _latest_snapshot_date(conn)
            if snapshot is None:
                return ScreenStocksResponse(data=[], meta=_empty_meta())
            stock_rows = (
                conn.execute(
                    _STOCKS_PAGE_SQL,
                    {
                        "snapshot_date": snapshot,
                        "cap_tier_filter": cap_tier,
                        "sector_filter": sector,
                        "after_iid": after_iid,
                        "page_size": page_size,
                    },
                )
                .mappings()
                .all()
            )
            iids = [r["instrument_id"] for r in stock_rows]
            conviction_by_iid = _fetch_conviction_rows(conn, snapshot, iids) if iids else {}
    except OperationalError as exc:
        log.warning("screen_stocks_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    data = [
        StockRow(
            instrument_id=r["instrument_id"],
            symbol=r["symbol"],
            company_name=r["company_name"],
            sector=r["sector"],
            cap_tier=r["cap_tier"],
            conviction=conviction_by_iid.get(r["instrument_id"], []),
        )
        for r in stock_rows
    ]
    next_cursor: str | None = None
    if len(data) == page_size:
        next_cursor = _encode_cursor(data[-1].instrument_id, snapshot)
    return ScreenStocksResponse(
        data=data,
        meta=_meta(snapshot, next_cursor=next_cursor, page_size=page_size),
    )


@router.get("/screen.etfs", response_model=ScreenETFsResponse)
def screen_etfs() -> ScreenETFsResponse:
    """ETF screen — drops NEGATIVE-only rows.

    ETFs are identified by joining atlas_universe_etfs on its ticker
    against any matching instrument in the conviction tape. Many ETFs
    won't have conviction rows yet (no scorecard) — those still surface
    with an empty conviction list so the UI can show the universe.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            snapshot = _latest_snapshot_date(conn)
            etf_rows = (
                conn.execute(
                    text(
                        """
                    SELECT ticker, etf_name, theme, linked_sector
                    FROM atlas.atlas_universe_etfs
                    WHERE effective_to IS NULL
                    ORDER BY ticker
                    LIMIT 200
                    """
                    )
                )
                .mappings()
                .all()
            )
    except OperationalError as exc:
        log.warning("screen_etfs_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    # ETFs do not yet have scorecard rows — conviction lists are empty for now.
    data = [
        ETFRow(
            ticker=r["ticker"],
            etf_name=r["etf_name"],
            theme=r["theme"],
            linked_sector=r["linked_sector"],
            conviction=[],
        )
        for r in etf_rows
    ]
    return ScreenETFsResponse(
        data=data,
        meta=_meta(snapshot or date.today(), degraded=snapshot is None),
    )


@router.get("/screen.funds", response_model=ScreenFundsResponse)
def screen_funds() -> ScreenFundsResponse:
    """Fund screen — best-effort join via mutual-fund holdings.

    The v6 mutual-fund conviction model is not yet wired; this endpoint
    returns the funds with their AUM but the conviction score is null
    and ``meta.degraded`` is true. The endpoint exists so the frontend
    contract can be satisfied day-1.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Soft-probe atlas_mf_holdings_latest if it exists.
            fund_rows: list[Any] = []
            try:
                fund_rows = (
                    conn.execute(
                        text(
                            """
                        SELECT
                            fund_id::text AS fund_id,
                            fund_name,
                            aum_inr_cr
                        FROM atlas.atlas_mf_master
                        ORDER BY aum_inr_cr DESC NULLS LAST
                        LIMIT 100
                        """
                        )
                    )
                    .mappings()
                    .all()
                )
            except Exception as inner:
                log.info("screen_funds_table_missing", error=str(inner))
    except OperationalError as exc:
        log.warning("screen_funds_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    data = [
        FundRow(
            fund_id=r["fund_id"],
            fund_name=r["fund_name"],
            aum_inr_cr=r["aum_inr_cr"],
            avg_conviction_score=None,
            note="v6 mutual-fund conviction not yet wired",
        )
        for r in fund_rows
    ]
    return ScreenFundsResponse(data=data, meta=_meta(date.today(), degraded=True))


@router.get("/screen.sectors", response_model=ScreenSectorsResponse)
def screen_sectors() -> ScreenSectorsResponse:
    """Sector screen — ranked by sector_strength_rank if available."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            snapshot = _latest_snapshot_date(conn)
            # Try to read from atlas_sector_states_daily (SP02 MV).
            try:
                sector_rows = (
                    conn.execute(
                        text(
                            """
                        SELECT
                            sector,
                            sector_strength_rank,
                            sector_breadth_pos
                        FROM atlas.atlas_sector_states_daily
                        WHERE date = (SELECT MAX(date) FROM atlas.atlas_sector_states_daily)
                        ORDER BY sector_strength_rank NULLS LAST
                        LIMIT 30
                        """
                        )
                    )
                    .mappings()
                    .all()
                )
            except Exception as inner:
                log.info("screen_sectors_no_states_table", error=str(inner))
                sector_rows = []
    except OperationalError as exc:
        log.warning("screen_sectors_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    data = [
        SectorRow(
            sector=r["sector"],
            strength_rank=r["sector_strength_rank"],
            breadth_pos=r["sector_breadth_pos"],
            top_constituents=[],
        )
        for r in sector_rows
    ]
    return ScreenSectorsResponse(
        data=data,
        meta=_meta(snapshot or date.today(), degraded=not sector_rows),
    )


def _empty_meta() -> dict[str, Any]:
    return {
        "data_as_of": None,
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "atlas_conviction_daily",
        "degraded": True,
        "note": "no conviction-tape rows yet",
    }
