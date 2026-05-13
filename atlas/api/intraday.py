"""Intraday data endpoints: RS leaders + ingester status.
# allow-large: 6 tightly-coupled endpoints (rs-leaders, status, nifty, sector-movers,
# prices, indices) share one router, one engine, and one OperationalError guard pattern.
# Splitting would duplicate the guard and engine import across multiple files with no
# cohesion gain — the single-responsibility boundary is the intraday domain, not the file.

SP08/SP10: Live intraday market state surface.

Endpoints:
    GET /api/v1/intraday/rs-leaders   — top N stocks by intraday RS percentile
    GET /api/v1/intraday/status       — KiteConnect session + last bar health
    GET /api/v1/intraday/nifty          — latest Nifty 50 intraday bar
    GET /api/v1/intraday/sector-movers  — sector return-since-open ranked
    GET /api/v1/intraday/prices         — {instrument_id: close} dict for all tracked stocks
    GET /api/v1/intraday/indices        — latest bar for all tracked NSE indices

All routes carry the ``/v1`` prefix and are therefore exempt from
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
    return_since_open: Decimal | None
    bar_time: datetime


class IntradayLeadersResponse(BaseModel):
    data: list[IntradayLeader]
    meta: dict[str, Any]


class IntradayStatusResponse(BaseModel):
    data: dict[str, Any]
    meta: dict[str, Any]


class NiftyBar(BaseModel):
    bar_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    return_since_open: Decimal | None
    pct_change_since_open: Decimal | None


class NiftyResponse(BaseModel):
    data: NiftyBar | None
    meta: dict[str, Any]


class SectorMover(BaseModel):
    sector: str
    avg_return_since_open: Decimal
    stock_count: int


class SectorMoversResponse(BaseModel):
    data: list[SectorMover]
    meta: dict[str, Any]


class IntradayPricesResponse(BaseModel):
    data: dict[str, Decimal]
    meta: dict[str, Any]


class IndexBar(BaseModel):
    symbol: str
    bar_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    return_since_open: Decimal | None
    pct_change_since_open: float | None  # return_since_open * 100 for display


class IndicesResponse(BaseModel):
    data: list[IndexBar]
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
    return_since_open,
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

_NIFTY_LATEST_SQL = """
SELECT bar_time, open, high, low, close, return_since_open
FROM atlas.atlas_nifty_intraday
ORDER BY bar_time DESC
LIMIT 1
"""

_SECTOR_MOVERS_SQL = """
SELECT
    sector,
    AVG(return_since_open) AS avg_return,
    COUNT(*) AS stock_count,
    MAX(bar_time) AS data_as_of
FROM atlas.mv_rs_intraday
WHERE return_since_open IS NOT NULL
GROUP BY sector
ORDER BY avg_return DESC NULLS LAST
"""

_PRICES_SQL = """
SELECT instrument_id::text, close, MAX(bar_time) OVER () AS data_as_of
FROM atlas.mv_rs_intraday
"""

_NIFTY_RETURN_FOR_RS_SQL = """
SELECT return_since_open
FROM atlas.atlas_nifty_intraday
WHERE symbol = 'NIFTY 50'
ORDER BY bar_time DESC
LIMIT 1
"""

_INDICES_SQL = """
SELECT symbol, bar_time, open, high, low, close, return_since_open
FROM atlas.atlas_nifty_intraday
WHERE (symbol, bar_time) IN (
    SELECT symbol, MAX(bar_time)
    FROM atlas.atlas_nifty_intraday
    GROUP BY symbol
)
ORDER BY symbol
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
            nifty_row = conn.execute(text(_NIFTY_RETURN_FOR_RS_SQL)).fetchone()
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

    nifty_return_since_open: Decimal | None = (
        Decimal(str(nifty_row[0])) if nifty_row and nifty_row[0] is not None else None
    )

    row_count = len(rows)
    log.debug("rs_leaders_fetched", row_count=row_count, n=n, sector=sector)

    if not rows:
        meta: dict[str, Any] = {
            "note": "Market closed or no intraday data yet",
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "mv_rs_intraday",
            "nifty_return_since_open": None,
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
                return_since_open=Decimal(str(row[9])) if row[9] is not None else None,
                bar_time=row[10],
            )
        )

    data_as_of: str = leaders[0].bar_time.isoformat()

    meta = {
        "data_as_of": data_as_of,
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "mv_rs_intraday",
        "row_count": row_count,
        "nifty_return_since_open": nifty_return_since_open,
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


@router.get(
    "/nifty",
    response_model=NiftyResponse,
    summary="Latest Nifty 50 intraday bar",
)
def get_nifty_bar(response: Response) -> NiftyResponse:
    """Return the most recent Nifty 50 intraday bar from atlas_nifty_intraday.

    Returns the last-known bar whether market is open or closed. Returns
    ``data: null`` with an explanatory note when the table is empty (pre-first
    bar or table not yet populated by migration 058).

    Args:
        response: FastAPI Response — used to set Cache-Control header.

    Returns:
        NiftyResponse with the latest bar or null + meta envelope.
    """
    engine = get_engine()

    try:
        with engine.connect() as conn:
            row = conn.execute(text(_NIFTY_LATEST_SQL)).fetchone()
    except OperationalError as exc:
        if "has not been populated" in str(exc):
            log.warning("atlas_nifty_intraday_not_populated")
            response.headers["Cache-Control"] = "public, max-age=30"
            return NiftyResponse(
                data=None,
                meta={
                    "note": "atlas_nifty_intraday not yet populated — first bar after market open",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "atlas_nifty_intraday",
                },
            )
        raise

    response.headers["Cache-Control"] = "public, max-age=30"

    if row is None:
        log.debug("nifty_bar_empty")
        return NiftyResponse(
            data=None,
            meta={
                "note": "No Nifty intraday data yet — table empty or pre-market",
                "fetched_at": datetime.now(UTC).isoformat(),
                "source": "atlas_nifty_intraday",
            },
        )

    bar_time: datetime = row[0]
    open_price = Decimal(str(row[1]))
    close_price = Decimal(str(row[4]))
    return_since_open = Decimal(str(row[5])) if row[5] is not None else None

    # pct_change_since_open = return_since_open * 100 for display convenience
    pct_change = (return_since_open * Decimal("100")) if return_since_open is not None else None

    log.debug("nifty_bar_fetched", bar_time=bar_time.isoformat())

    return NiftyResponse(
        data=NiftyBar(
            bar_time=bar_time,
            open=open_price,
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=close_price,
            return_since_open=return_since_open,
            pct_change_since_open=pct_change,
        ),
        meta={
            "data_as_of": bar_time.isoformat(),
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "atlas_nifty_intraday",
        },
    )


@router.get(
    "/sector-movers",
    response_model=SectorMoversResponse,
    summary="Sector return-since-open sorted best to worst",
)
def get_sector_movers(response: Response) -> SectorMoversResponse:
    """Return all sectors ranked by average return-since-open.

    Queries ``mv_rs_intraday`` — the same view used by rs-leaders — grouping
    by sector and averaging return_since_open across all stocks in the sector.

    Returns an empty list with a note when the view is empty (market closed
    or no data yet).

    Args:
        response: FastAPI Response — used to set Cache-Control header.

    Returns:
        SectorMoversResponse with sector list sorted best → worst + meta.
    """
    engine = get_engine()

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(_SECTOR_MOVERS_SQL)).fetchall()
    except OperationalError as exc:
        if "has not been populated" in str(exc):
            log.warning("mv_rs_intraday_not_populated")
            response.headers["Cache-Control"] = "public, max-age=30"
            return SectorMoversResponse(
                data=[],
                meta={
                    "note": "Intraday MV not yet populated — first bar after market open",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "mv_rs_intraday",
                },
            )
        raise

    response.headers["Cache-Control"] = "public, max-age=30"

    if not rows:
        log.debug("sector_movers_empty")
        return SectorMoversResponse(
            data=[],
            meta={
                "note": "No intraday data — market closed or MV not yet populated",
                "fetched_at": datetime.now(UTC).isoformat(),
                "source": "mv_rs_intraday",
            },
        )

    movers: list[SectorMover] = [
        SectorMover(
            sector=str(row[0]),
            avg_return_since_open=Decimal(str(row[1])),
            stock_count=int(row[2]),
        )
        for row in rows
    ]

    data_as_of_raw = rows[0][3] if rows else None
    data_as_of_str = data_as_of_raw.isoformat() if data_as_of_raw is not None else None

    log.debug("sector_movers_fetched", sector_count=len(movers))

    return SectorMoversResponse(
        data=movers,
        meta={
            "data_as_of": data_as_of_str,
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "mv_rs_intraday",
            "sector_count": len(movers),
        },
    )


@router.get(
    "/prices",
    response_model=IntradayPricesResponse,
    summary="Latest close price for all tracked instruments",
)
def get_intraday_prices(response: Response) -> IntradayPricesResponse:
    """Return a dict of instrument_id → latest close price.

    Queries ``mv_rs_intraday`` for all instruments. Returns an empty dict
    when the view is empty (market closed or no data yet).

    Intended for the StockScreener live-price column: the frontend fetches
    this once on load and every 30 s, then cross-joins locally by instrument_id.

    Args:
        response: FastAPI Response — used to set Cache-Control header.

    Returns:
        IntradayPricesResponse with {instrument_id: close} dict + meta.
    """
    engine = get_engine()

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(_PRICES_SQL)).fetchall()
    except OperationalError as exc:
        if "has not been populated" in str(exc):
            log.warning("mv_rs_intraday_not_populated")
            response.headers["Cache-Control"] = "public, max-age=30"
            return IntradayPricesResponse(
                data={},
                meta={
                    "note": "Intraday MV not yet populated — first bar after market open",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "mv_rs_intraday",
                },
            )
        raise

    response.headers["Cache-Control"] = "public, max-age=30"

    if not rows:
        log.debug("intraday_prices_empty")
        return IntradayPricesResponse(
            data={},
            meta={
                "note": "No intraday data — market closed or MV not yet populated",
                "fetched_at": datetime.now(UTC).isoformat(),
                "source": "mv_rs_intraday",
            },
        )

    data_as_of_raw = rows[0][2] if rows else None
    data_as_of_str = data_as_of_raw.isoformat() if data_as_of_raw is not None else None

    prices: dict[str, Decimal] = {str(row[0]): Decimal(str(row[1])) for row in rows}

    log.debug("intraday_prices_fetched", instrument_count=len(prices))

    return IntradayPricesResponse(
        data=prices,
        meta={
            "data_as_of": data_as_of_str,
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "mv_rs_intraday",
            "instrument_count": len(prices),
        },
    )


@router.get(
    "/indices",
    response_model=IndicesResponse,
    summary="Latest bar for all tracked NSE indices",
)
def get_indices(response: Response) -> IndicesResponse:
    """Return the most recent bar for each tracked NSE index.

    Queries ``atlas.atlas_nifty_intraday`` for the latest (symbol, bar_time) row
    per symbol. Returns all five tracked indices: NIFTY 50, NIFTY BANK,
    NIFTY MID100, NIFTY SMLCAP, NIFTY IT.

    Returns an empty list with an explanatory note when the table has no rows
    (pre-first bar or migration 059 not yet applied).

    Args:
        response: FastAPI Response — used to set Cache-Control header.

    Returns:
        IndicesResponse with one IndexBar per symbol (or empty list) + meta.
    """
    engine = get_engine()

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(_INDICES_SQL)).fetchall()
    except OperationalError as exc:
        if "has not been populated" in str(exc):
            log.warning("atlas_nifty_intraday_not_populated")
            response.headers["Cache-Control"] = "public, max-age=30"
            return IndicesResponse(
                data=[],
                meta={
                    "note": "atlas_nifty_intraday not yet populated — first bar after market open",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "atlas_nifty_intraday",
                },
            )
        raise

    response.headers["Cache-Control"] = "public, max-age=30"

    if not rows:
        log.debug("indices_empty")
        return IndicesResponse(
            data=[],
            meta={
                "note": "No index intraday data yet — table empty or pre-market",
                "fetched_at": datetime.now(UTC).isoformat(),
                "source": "atlas_nifty_intraday",
            },
        )

    bars: list[IndexBar] = []
    for row in rows:
        ret = Decimal(str(row[6])) if row[6] is not None else None
        bars.append(
            IndexBar(
                symbol=str(row[0]),
                bar_time=row[1],
                open=Decimal(str(row[2])),
                high=Decimal(str(row[3])),
                low=Decimal(str(row[4])),
                close=Decimal(str(row[5])),
                return_since_open=ret,
                pct_change_since_open=float(ret * 100) if ret is not None else None,
            )
        )

    data_as_of_str = bars[0].bar_time.isoformat() if bars else None
    log.debug("indices_fetched", symbol_count=len(bars))

    return IndicesResponse(
        data=bars,
        meta={
            "data_as_of": data_as_of_str,
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "atlas_nifty_intraday",
            "symbol_count": len(bars),
        },
    )
