"""Intraday data endpoints: RS leaders + ingester status.

SP08: Live intraday market state surface.

Endpoints:
    GET /api/v1/intraday/rs-leaders   — top N stocks by intraday RS percentile
    GET /api/v1/intraday/status       — KiteConnect session + last bar health

Both routes carry the ``/v1`` prefix and are therefore exempt from
JWTAuthMiddleware (atlas.api.auth._EXEMPT_PREFIXES includes "/v1").
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/intraday", tags=["intraday"])

_MAX_LEADERS = 50


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class IntradayLeader(BaseModel):
    instrument_id: str
    symbol: str
    sector: str
    tier: str
    close: Decimal
    ema_20: Decimal | None
    ema_50: Decimal | None
    rs_vs_nifty: Decimal | None
    rs_pctile_intraday: Decimal | None
    bar_time: datetime


class IntradayLeadersResponse(BaseModel):
    data: list[IntradayLeader]
    meta: dict[str, Any]


class IntradayStatusResponse(BaseModel):
    data: dict[str, Any]
    meta: dict[str, Any]


# ---------------------------------------------------------------------------
# SQL fragments
# ---------------------------------------------------------------------------

_RS_LEADERS_BASE_SQL = """
SELECT
    instrument_id::text,
    symbol,
    sector,
    tier,
    close,
    ema_20,
    ema_50,
    rs_vs_nifty,
    rs_pctile_intraday,
    bar_time
FROM atlas.mv_rs_intraday
WHERE rs_vs_nifty IS NOT NULL
"""

_RS_LEADERS_ORDER_LIMIT = """
ORDER BY rs_pctile_intraday DESC NULLS LAST
LIMIT :n
"""

_SESSION_SQL = """
SELECT session_type, login_time, expires_at
FROM atlas.atlas_kite_session
ORDER BY login_time DESC
LIMIT 1
"""

_LAST_BAR_SQL = """
SELECT MAX(bar_time), COUNT(*)
FROM atlas.atlas_stock_metrics_intraday
WHERE bar_time > NOW() - INTERVAL '1 hour'
"""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/rs-leaders",
    response_model=IntradayLeadersResponse,
    summary="Top N stocks by intraday RS percentile",
)
def get_rs_leaders(
    response: Response,
    n: Annotated[int, Query(ge=1, le=_MAX_LEADERS, description="Number of leaders to return")] = 20,
    sector: Annotated[
        str | None,
        Query(description="Optional sector substring filter (case-insensitive)", max_length=100),
    ] = None,
) -> IntradayLeadersResponse:
    """Return the top N intraday RS leaders from the materialized view.

    The view ``atlas.mv_rs_intraday`` is refreshed approximately every 15
    minutes during market hours. When the market is closed the view is empty;
    the endpoint returns an empty list with an explanatory note rather than
    an error.

    Args:
        response: FastAPI Response object — used to set Cache-Control header.
        n: Number of results to return (1–50). Defaults to 20.
        sector: Optional case-insensitive substring match on the sector column.

    Returns:
        IntradayLeadersResponse with data list and meta envelope.
    """
    engine = get_engine()

    # Build SQL with optional sector filter
    if sector:
        sql_str = (
            _RS_LEADERS_BASE_SQL
            + "  AND LOWER(sector) LIKE :sector_pattern\n"
            + _RS_LEADERS_ORDER_LIMIT
        )
        params: dict[str, Any] = {"n": n, "sector_pattern": f"%{sector.lower()}%"}
    else:
        sql_str = _RS_LEADERS_BASE_SQL + _RS_LEADERS_ORDER_LIMIT
        params = {"n": n}

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql_str), params).fetchall()
    except OperationalError as exc:
        if "has not been populated" in str(exc):
            log.warning("mv_rs_intraday_not_populated")
            response.headers["Cache-Control"] = "public, max-age=30"
            return IntradayLeadersResponse(
                data=[],
                meta={
                    "note": "Intraday MV not yet populated — first bar after market open",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "mv_rs_intraday",
                },
            )
        raise

    row_count = len(rows)
    log.debug("rs_leaders_fetched", row_count=row_count, n=n, sector=sector)

    if not rows:
        meta: dict[str, Any] = {
            "note": "Market closed or no intraday data yet",
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "mv_rs_intraday",
        }
        response.headers["Cache-Control"] = "public, max-age=30"
        return IntradayLeadersResponse(data=[], meta=meta)

    leaders: list[IntradayLeader] = []
    for row in rows:
        leaders.append(
            IntradayLeader(
                instrument_id=str(row[0]),
                symbol=str(row[1]),
                sector=str(row[2]),
                tier=str(row[3]),
                close=Decimal(str(row[4])),
                ema_20=Decimal(str(row[5])) if row[5] is not None else None,
                ema_50=Decimal(str(row[6])) if row[6] is not None else None,
                rs_vs_nifty=Decimal(str(row[7])) if row[7] is not None else None,
                rs_pctile_intraday=Decimal(str(row[8])) if row[8] is not None else None,
                bar_time=row[9],
            )
        )

    data_as_of: str = leaders[0].bar_time.isoformat()

    meta = {
        "data_as_of": data_as_of,
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "mv_rs_intraday",
        "row_count": row_count,
    }

    response.headers["Cache-Control"] = "public, max-age=30"
    return IntradayLeadersResponse(data=leaders, meta=meta)


@router.get(
    "/status",
    response_model=IntradayStatusResponse,
    summary="KiteConnect session health + last bar info",
)
def get_intraday_status() -> IntradayStatusResponse:
    """Return a health snapshot of the intraday ingester.

    Queries:
    - ``atlas.atlas_kite_session`` for the most recent session row.
    - ``atlas.atlas_stock_metrics_intraday`` for the last bar time and
      the instrument count in the past hour.

    Returns:
        IntradayStatusResponse with session state and bar freshness.
    """
    engine = get_engine()
    fetched_at = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        session_row = conn.execute(text(_SESSION_SQL)).fetchone()
        bar_row = conn.execute(text(_LAST_BAR_SQL)).fetchone()

    # Session data — may be None if no session row exists yet
    if session_row is not None:
        session_type: str | None = session_row[0]
        token_valid_until: str | None = (
            session_row[2].isoformat() if session_row[2] is not None else None
        )
    else:
        session_type = None
        token_valid_until = None

    # Bar data — MAX returns NULL when table is empty / no recent bars
    last_bar_time: str | None = None
    instruments_in_last_bar: int = 0

    if bar_row is not None:
        last_bar_time = bar_row[0].isoformat() if bar_row[0] is not None else None
        instruments_in_last_bar = int(bar_row[1]) if bar_row[1] is not None else 0

    log.debug(
        "intraday_status_fetched",
        session_type=session_type,
        last_bar_time=last_bar_time,
        instruments_in_last_bar=instruments_in_last_bar,
    )

    return IntradayStatusResponse(
        data={
            "session_type": session_type,
            "token_valid_until": token_valid_until,
            "last_bar_time": last_bar_time,
            "instruments_in_last_bar": instruments_in_last_bar,
        },
        meta={
            "fetched_at": fetched_at,
            "source": "atlas_kite_session",
        },
    )
