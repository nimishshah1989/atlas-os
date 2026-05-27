"""v6 /v1/rank.* endpoints — Fund + ETF scorecard rankings.

Two paginated list endpoints + two detail endpoints, all reading from
``atlas.atlas_etf_scorecard`` / ``atlas.atlas_fund_scorecard`` (migration
093). They mirror the envelope + cursor conventions established by
:mod:`atlas.api.screen`:

  GET /v1/rank.etfs?category=&min_aum_cr=&cursor=&limit=
  GET /v1/rank.funds?category=&style=&min_aum_cr=&cursor=&limit=
  GET /v1/rank.etfs/{iid}            — single-ETF detail
  GET /v1/rank.funds/{scheme_code}   — single-fund detail

Fund rows always include the disclaimer fields the API surface
contract requires:

  * survivorship_exposure_pct
  * nav_as_of / holdings_as_of
  * confidence_low
  * meta.degraded (true if the scorecard table is empty)

Cursor pagination uses an opaque base64-encoded tuple keyed on
``(composite_score_desc, primary_key_asc)`` so iteration is stable
under ties. Page-end is detected by len(data) == limit.
"""

# allow-large: four sibling endpoints sharing the same envelope helpers,
# cursor primitives, and response shapes. Splitting them across files
# would force duplication of the Pydantic shapes that define the
# scorecard contract.

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
from sqlalchemy.exc import OperationalError, ProgrammingError

from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["rank"])


# ---------------------------------------------------------------------------
# Pydantic shapes
# ---------------------------------------------------------------------------


class ETFRankRow(BaseModel):
    instrument_id: str
    isin: str | None
    ticker: str | None
    etf_name: str | None
    etf_category: str
    underlying_sector: str | None
    matrix_conviction_score: Decimal | None
    sector_strength_score: Decimal | None
    tracking_quality_score: Decimal | None
    aum_bracket_score: Decimal | None
    liquidity_score: Decimal | None
    expense_ratio_score: Decimal | None
    composite_score: Decimal
    rank_in_category: int | None
    category_size: int | None
    is_atlas_leader: bool
    eli5: str | None
    snapshot_date: date


class ETFRankListResponse(BaseModel):
    data: list[ETFRankRow]
    meta: dict[str, Any]


class ETFRankDetail(BaseModel):
    data: dict[str, Any]
    meta: dict[str, Any]


class FundRankRow(BaseModel):
    scheme_code: str
    isin: str | None
    fund_name: str | None
    fund_category: str
    fund_style: str | None
    amc: str | None
    risk_adjusted_return_score: Decimal | None
    holdings_conviction_score: Decimal | None
    style_sector_score: Decimal | None
    cost_manager_score: Decimal | None
    composite_score: Decimal
    rank_in_category: int | None
    category_size: int | None
    is_atlas_leader: bool
    is_avoid: bool
    # Disclaimers — MUST be present on every row.
    confidence_low: bool
    holdings_unjoinable: bool
    survivorship_exposure_pct: Decimal | None
    nav_as_of: date | None
    holdings_as_of: date | None
    eli5: str | None
    snapshot_date: date


class FundRankListResponse(BaseModel):
    data: list[FundRankRow]
    meta: dict[str, Any]


class FundRankDetail(BaseModel):
    data: dict[str, Any]
    meta: dict[str, Any]


# ---------------------------------------------------------------------------
# Cursor helpers — (composite_score, pk) tuple, base64-encoded JSON.
# ---------------------------------------------------------------------------


def _encode_cursor(composite_score: Decimal | float, pk: str) -> str:
    """Encode cursor as opaque base64 — caller treats it as a string."""
    payload = {"s": str(composite_score), "k": pk}
    raw = json.dumps(payload, sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[Decimal, str]:
    """Parse an opaque cursor back into (composite_score, pk)."""
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        obj = json.loads(decoded)
        return Decimal(str(obj["s"])), str(obj["k"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid cursor: {exc!r}") from exc


# ---------------------------------------------------------------------------
# SQL primitives
# ---------------------------------------------------------------------------

_LATEST_ETF_SNAPSHOT = text("SELECT MAX(snapshot_date) AS d FROM atlas.atlas_etf_scorecard")
_LATEST_FUND_SNAPSHOT = text("SELECT MAX(snapshot_date) AS d FROM atlas.atlas_fund_scorecard")


# Pagination strategy: ORDER BY (composite_score DESC, pk ASC). Cursor =
# (last_score, last_pk). Next page: where (score < last_score) OR
# (score = last_score AND pk > last_pk).
_ETF_PAGE_SQL = text(
    """
    SELECT
        s.snapshot_date,
        s.instrument_id::text AS instrument_id,
        s.isin,
        s.ticker,
        s.etf_name,
        s.etf_category,
        s.underlying_sector,
        s.matrix_conviction_score,
        s.sector_strength_score,
        s.tracking_quality_score,
        s.aum_bracket_score,
        s.liquidity_score,
        s.expense_ratio_score,
        s.composite_score,
        s.rank_in_category,
        s.category_size,
        s.is_atlas_leader,
        s.eli5,
        s.raw_metrics
    FROM atlas.atlas_etf_scorecard s
    WHERE s.snapshot_date = :snapshot_date
      AND (:category IS NULL OR s.etf_category = :category)
      AND (
        :cursor_score IS NULL
        OR s.composite_score < :cursor_score
        OR (s.composite_score = :cursor_score AND s.instrument_id::text > :cursor_pk)
      )
      AND (
        :min_aum_cr IS NULL
        OR COALESCE((s.raw_metrics->>'aum_cr')::numeric, 0) >= :min_aum_cr
      )
    ORDER BY s.composite_score DESC, s.instrument_id::text ASC
    LIMIT :page_size
    """
)


_FUND_PAGE_SQL = text(
    """
    SELECT
        s.snapshot_date,
        s.scheme_code,
        s.isin,
        s.fund_name,
        s.fund_category,
        s.fund_style,
        s.amc,
        s.risk_adjusted_return_score,
        s.holdings_conviction_score,
        s.style_sector_score,
        s.cost_manager_score,
        s.composite_score,
        s.rank_in_category,
        s.category_size,
        s.is_atlas_leader,
        s.is_avoid,
        s.confidence_low,
        s.holdings_unjoinable,
        s.survivorship_exposure_pct,
        s.nav_as_of,
        s.holdings_as_of,
        s.eli5,
        s.sub_metrics
    FROM atlas.atlas_fund_scorecard s
    WHERE s.snapshot_date = :snapshot_date
      AND (:category IS NULL OR s.fund_category = :category)
      AND (:style IS NULL OR s.fund_style = :style)
      AND (
        :cursor_score IS NULL
        OR s.composite_score < :cursor_score
        OR (s.composite_score = :cursor_score AND s.scheme_code > :cursor_pk)
      )
      AND (
        :min_aum_cr IS NULL
        OR COALESCE((s.sub_metrics->>'aum_cr')::numeric, 0) >= :min_aum_cr
      )
    ORDER BY s.composite_score DESC, s.scheme_code ASC
    LIMIT :page_size
    """
)


_ETF_DETAIL_SQL = text(
    """
    SELECT
        s.snapshot_date,
        s.instrument_id::text AS instrument_id,
        s.isin,
        s.ticker,
        s.etf_name,
        s.etf_category,
        s.underlying_sector,
        s.matrix_conviction_score,
        s.sector_strength_score,
        s.tracking_quality_score,
        s.aum_bracket_score,
        s.liquidity_score,
        s.expense_ratio_score,
        s.composite_score,
        s.rank_in_category,
        s.category_size,
        s.is_atlas_leader,
        s.eli5,
        s.raw_metrics
    FROM atlas.atlas_etf_scorecard s
    WHERE s.instrument_id::text = :iid
    ORDER BY s.snapshot_date DESC
    LIMIT 1
    """
)


_FUND_DETAIL_SQL = text(
    """
    SELECT
        s.snapshot_date,
        s.scheme_code,
        s.isin,
        s.fund_name,
        s.fund_category,
        s.fund_style,
        s.amc,
        s.risk_adjusted_return_score,
        s.holdings_conviction_score,
        s.style_sector_score,
        s.cost_manager_score,
        s.composite_score,
        s.rank_in_category,
        s.category_size,
        s.is_atlas_leader,
        s.is_avoid,
        s.confidence_low,
        s.holdings_unjoinable,
        s.survivorship_exposure_pct,
        s.nav_as_of,
        s.holdings_as_of,
        s.eli5,
        s.sub_metrics,
        s.top_holdings
    FROM atlas.atlas_fund_scorecard s
    WHERE s.scheme_code = :scheme_code
    ORDER BY s.snapshot_date DESC
    LIMIT 1
    """
)


# ---------------------------------------------------------------------------
# Meta envelope helpers
# ---------------------------------------------------------------------------


def _meta(
    snapshot_date: date | None,
    source: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "data_as_of": snapshot_date.isoformat() if snapshot_date else None,
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": source,
        **extra,
    }


def _empty_meta(source: str, note: str) -> dict[str, Any]:
    return {
        "data_as_of": None,
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": source,
        "degraded": True,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Internal handlers — wrapped in OperationalError → 503; ProgrammingError
# (table missing) → degraded envelope.
# ---------------------------------------------------------------------------


def _latest_etf_snapshot(conn: Any) -> date | None:
    row = conn.execute(_LATEST_ETF_SNAPSHOT).first()
    return row.d if row and row.d else None


def _latest_fund_snapshot(conn: Any) -> date | None:
    row = conn.execute(_LATEST_FUND_SNAPSHOT).first()
    return row.d if row and row.d else None


def _build_etf_row(r: dict[str, Any]) -> ETFRankRow:
    return ETFRankRow(
        instrument_id=r["instrument_id"],
        isin=r.get("isin"),
        ticker=r.get("ticker"),
        etf_name=r.get("etf_name"),
        etf_category=r["etf_category"],
        underlying_sector=r.get("underlying_sector"),
        matrix_conviction_score=r.get("matrix_conviction_score"),
        sector_strength_score=r.get("sector_strength_score"),
        tracking_quality_score=r.get("tracking_quality_score"),
        aum_bracket_score=r.get("aum_bracket_score"),
        liquidity_score=r.get("liquidity_score"),
        expense_ratio_score=r.get("expense_ratio_score"),
        composite_score=r["composite_score"],
        rank_in_category=r.get("rank_in_category"),
        category_size=r.get("category_size"),
        is_atlas_leader=r.get("is_atlas_leader", False),
        eli5=r.get("eli5"),
        snapshot_date=r["snapshot_date"],
    )


def _build_fund_row(r: dict[str, Any]) -> FundRankRow:
    return FundRankRow(
        scheme_code=r["scheme_code"],
        isin=r.get("isin"),
        fund_name=r.get("fund_name"),
        fund_category=r["fund_category"],
        fund_style=r.get("fund_style"),
        amc=r.get("amc"),
        risk_adjusted_return_score=r.get("risk_adjusted_return_score"),
        holdings_conviction_score=r.get("holdings_conviction_score"),
        style_sector_score=r.get("style_sector_score"),
        cost_manager_score=r.get("cost_manager_score"),
        composite_score=r["composite_score"],
        rank_in_category=r.get("rank_in_category"),
        category_size=r.get("category_size"),
        is_atlas_leader=r.get("is_atlas_leader", False),
        is_avoid=r.get("is_avoid", False),
        confidence_low=r.get("confidence_low", False),
        holdings_unjoinable=r.get("holdings_unjoinable", False),
        survivorship_exposure_pct=r.get("survivorship_exposure_pct"),
        nav_as_of=r.get("nav_as_of"),
        holdings_as_of=r.get("holdings_as_of"),
        eli5=r.get("eli5"),
        snapshot_date=r["snapshot_date"],
    )


# ---------------------------------------------------------------------------
# /v1/rank.etfs  (list)
# ---------------------------------------------------------------------------


@router.get("/rank.etfs", response_model=ETFRankListResponse)
def rank_etfs(
    category: Annotated[
        str | None,
        Query(description="Filter by etf_category (broad_index, sector, ...)"),
    ] = None,
    min_aum_cr: Annotated[
        Decimal | None,
        Query(description="Minimum AUM in INR crore (filters raw_metrics.aum_cr)"),
    ] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ETFRankListResponse:
    """Paginated ETF ranking by composite score (descending)."""
    cursor_score: Decimal | None = None
    cursor_pk: str | None = None
    if cursor:
        cursor_score, cursor_pk = _decode_cursor(cursor)
    try:
        engine = get_engine()
        with engine.connect() as conn:
            try:
                snapshot = _latest_etf_snapshot(conn)
            except ProgrammingError as exc:
                log.info("rank_etfs_table_missing", error=str(exc))
                return ETFRankListResponse(
                    data=[],
                    meta=_empty_meta(
                        "atlas_etf_scorecard",
                        "atlas_etf_scorecard not yet present — apply migration 093",
                    ),
                )
            if snapshot is None:
                return ETFRankListResponse(
                    data=[],
                    meta=_empty_meta(
                        "atlas_etf_scorecard",
                        "no etf_scorecard rows yet — run backfill",
                    ),
                )
            rows = (
                conn.execute(
                    _ETF_PAGE_SQL,
                    {
                        "snapshot_date": snapshot,
                        "category": category,
                        "min_aum_cr": min_aum_cr,
                        "cursor_score": cursor_score,
                        "cursor_pk": cursor_pk,
                        "page_size": limit,
                    },
                )
                .mappings()
                .all()
            )
    except OperationalError as exc:
        log.warning("rank_etfs_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    data = [_build_etf_row(dict(r)) for r in rows]
    next_cursor: str | None = None
    if len(data) == limit:
        last = data[-1]
        next_cursor = _encode_cursor(last.composite_score, last.instrument_id)
    return ETFRankListResponse(
        data=data,
        meta=_meta(
            snapshot,
            "atlas_etf_scorecard",
            page_size=limit,
            next_cursor=next_cursor,
            filters={"category": category, "min_aum_cr": str(min_aum_cr) if min_aum_cr else None},
        ),
    )


# ---------------------------------------------------------------------------
# /v1/rank.funds (list)
# ---------------------------------------------------------------------------


@router.get("/rank.funds", response_model=FundRankListResponse)
def rank_funds(
    category: Annotated[
        str | None,
        Query(description="Filter by fund_category (Flexi Cap, Large Cap, ...)"),
    ] = None,
    style: Annotated[str | None, Query(description="Filter by fund_style")] = None,
    min_aum_cr: Annotated[
        Decimal | None,
        Query(description="Minimum AUM in INR crore (filters sub_metrics.aum_cr)"),
    ] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FundRankListResponse:
    """Paginated mutual fund ranking by composite score (descending).

    Every row carries the four caveat fields the contract requires:
    survivorship_exposure_pct, nav_as_of, holdings_as_of, confidence_low.
    """
    cursor_score: Decimal | None = None
    cursor_pk: str | None = None
    if cursor:
        cursor_score, cursor_pk = _decode_cursor(cursor)
    try:
        engine = get_engine()
        with engine.connect() as conn:
            try:
                snapshot = _latest_fund_snapshot(conn)
            except ProgrammingError as exc:
                log.info("rank_funds_table_missing", error=str(exc))
                return FundRankListResponse(
                    data=[],
                    meta=_empty_meta(
                        "atlas_fund_scorecard",
                        "atlas_fund_scorecard not yet present — apply migration 093",
                    ),
                )
            if snapshot is None:
                return FundRankListResponse(
                    data=[],
                    meta=_empty_meta(
                        "atlas_fund_scorecard",
                        "no fund_scorecard rows yet — run backfill",
                    ),
                )
            rows = (
                conn.execute(
                    _FUND_PAGE_SQL,
                    {
                        "snapshot_date": snapshot,
                        "category": category,
                        "style": style,
                        "min_aum_cr": min_aum_cr,
                        "cursor_score": cursor_score,
                        "cursor_pk": cursor_pk,
                        "page_size": limit,
                    },
                )
                .mappings()
                .all()
            )
    except OperationalError as exc:
        log.warning("rank_funds_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    data = [_build_fund_row(dict(r)) for r in rows]
    next_cursor: str | None = None
    if len(data) == limit:
        last = data[-1]
        next_cursor = _encode_cursor(last.composite_score, last.scheme_code)
    return FundRankListResponse(
        data=data,
        meta=_meta(
            snapshot,
            "atlas_fund_scorecard",
            page_size=limit,
            next_cursor=next_cursor,
            filters={
                "category": category,
                "style": style,
                "min_aum_cr": str(min_aum_cr) if min_aum_cr else None,
            },
            disclaimers=[
                "Holdings conviction inherits survivorship caveat from the 24-cell matrix.",
                "NAV staleness: T-1 to T-3 typical for Indian MFs.",
                "Holdings disclosure: 30-day SEBI lag.",
                "Style drift penalty softened for sub-₹500Cr AUM funds.",
                "confidence_low=true means < 3y track record.",
            ],
        ),
    )


# ---------------------------------------------------------------------------
# /v1/rank.etfs/{iid} (detail)
# ---------------------------------------------------------------------------


@router.get("/rank.etfs/{iid}", response_model=ETFRankDetail)
def rank_etfs_detail(iid: str) -> ETFRankDetail:
    """Single-ETF detail.

    Returns the full scorecard row plus the raw_metrics blob (which
    carries the per-component reasons, AUM/TER, tracking error series
    when present, etc.). UI uses raw_metrics to render the per-component
    breakdown + sparkline series.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            try:
                row = conn.execute(_ETF_DETAIL_SQL, {"iid": iid}).mappings().first()
            except ProgrammingError as exc:
                log.info("rank_etfs_detail_table_missing", error=str(exc))
                raise HTTPException(
                    status_code=503,
                    detail="atlas_etf_scorecard not yet present — apply migration 093",
                ) from exc
    except OperationalError as exc:
        log.warning("rank_etfs_detail_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    if row is None:
        raise HTTPException(status_code=404, detail=f"ETF {iid} not in scorecard")

    scorecard = _build_etf_row(dict(row)).model_dump(mode="json")
    raw_metrics = dict(row).get("raw_metrics") or {}
    return ETFRankDetail(
        data={
            "scorecard": scorecard,
            "raw_metrics": raw_metrics,
            # Placeholders — the underlying tracking-error series + sector
            # overlay can be wired in when SP02 MV publishes them. The API
            # contract surfaces the keys today so consumers don't break
            # when the data arrives.
            "tracking_error_series": [],
            "sector_overlay": {},
        },
        meta={
            "data_as_of": row["snapshot_date"].isoformat(),
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "atlas_etf_scorecard",
        },
    )


# ---------------------------------------------------------------------------
# /v1/rank.funds/{scheme_code} (detail)
# ---------------------------------------------------------------------------


@router.get("/rank.funds/{scheme_code}", response_model=FundRankDetail)
def rank_funds_detail(scheme_code: str) -> FundRankDetail:
    """Single-fund detail.

    Returns the full scorecard row + sub_metrics (per-layer raw numbers)
    + top_holdings (drill-down with per-holding conviction verdicts).
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            try:
                row = (
                    conn.execute(_FUND_DETAIL_SQL, {"scheme_code": scheme_code}).mappings().first()
                )
            except ProgrammingError as exc:
                log.info("rank_funds_detail_table_missing", error=str(exc))
                raise HTTPException(
                    status_code=503,
                    detail="atlas_fund_scorecard not yet present — apply migration 093",
                ) from exc
    except OperationalError as exc:
        log.warning("rank_funds_detail_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    if row is None:
        raise HTTPException(status_code=404, detail=f"fund {scheme_code} not in scorecard")

    row_dict = dict(row)
    scorecard = _build_fund_row(row_dict).model_dump(mode="json")
    sub_metrics = row_dict.get("sub_metrics") or {}
    top_holdings = row_dict.get("top_holdings") or []
    return FundRankDetail(
        data={
            "scorecard": scorecard,
            "sub_metrics": sub_metrics,
            "top_holdings": top_holdings,
            # Same as ETF detail — UI placeholder; filled when SP02 MVs
            # publish 3y rolling Sharpe series and holdings-by-sector
            # rollups.
            "rolling_sharpe_3y": [],
            "holdings_by_sector": {},
        },
        meta={
            "data_as_of": row_dict["snapshot_date"].isoformat(),
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "atlas_fund_scorecard",
            "disclaimers": [
                "Holdings conviction inherits survivorship caveat from the 24-cell matrix.",
                "NAV staleness: T-1 to T-3 typical for Indian MFs.",
                "Holdings disclosure: 30-day SEBI lag.",
                "Style drift penalty softened for sub-₹500Cr AUM funds.",
                "confidence_low=true means < 3y track record.",
            ],
        },
    )
