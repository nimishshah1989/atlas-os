# pragma: finance-critical
"""TradingView webhook receiver and signal report feed.

Endpoints:
  POST /api/v1/tv/signal         — receive TV alert webhook
  GET  /api/v1/tv/signals        — paginated feed of signal reports
  GET  /api/v1/tv/signals/{id}   — single report detail
  POST /api/v1/tv/generate-report — ad-hoc report for any ticker (internal)
"""

from __future__ import annotations

import os
import pathlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import text

from atlas.config import Config
from atlas.db import get_engine
from atlas.signals.models import TVSignalPayload

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/tv", tags=["tv-signals"])

_DEDUP_WINDOW_MINUTES = 60


def _is_duplicate(ticker: str, condition_code: str, chart_type: str) -> bool:
    """Return True if an identical signal was received within the dedup window."""
    cutoff = datetime.now(UTC) - timedelta(minutes=_DEDUP_WINDOW_MINUTES)
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM tv_signal_reports "
                "WHERE ticker = :ticker AND condition_code = :code AND chart_type = :chart "
                "AND triggered_at > :cutoff LIMIT 1"
            ),
            {"ticker": ticker, "code": condition_code, "chart": chart_type, "cutoff": cutoff},
        ).fetchone()
    return row is not None


async def process_signal(payload: TVSignalPayload) -> None:
    """Hand off the validated payload to the signal processing pipeline."""
    from atlas.signals.processor import run_signal_pipeline  # deferred — optional dep

    await run_signal_pipeline(payload)


@router.post("/signal")
async def receive_tv_signal(
    payload: TVSignalPayload,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Receive a TradingView alert webhook.

    Validates the shared secret, deduplicates within 60 minutes, then
    queues the pipeline in a background task so the webhook ACKs fast.
    """
    if payload.secret is not None and payload.secret != Config.TV_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if _is_duplicate(payload.ticker, payload.code, payload.chart):
        log.info(
            "tv_signal_deduplicated",
            ticker=payload.ticker,
            code=payload.code,
            chart=payload.chart,
        )
        return {"status": "duplicate"}

    log.info("tv_signal_received", ticker=payload.ticker, tier=payload.tier, code=payload.code)
    background_tasks.add_task(process_signal, payload)
    return {"status": "accepted"}


@router.get("/signals")
async def list_signal_reports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tier: int | None = Query(default=None),
    confirmation: str | None = Query(default=None),
) -> dict:
    """Return a paginated feed of active signal reports, newest first."""
    conditions = ["is_active = TRUE"]
    params: dict = {"limit": limit, "offset": offset}

    if tier is not None:
        conditions.append("condition_tier = :tier")
        params["tier"] = tier
    if confirmation is not None:
        conditions.append("confirmation_level = :confirmation")
        params["confirmation"] = confirmation

    where = " AND ".join(conditions)

    # Column names and WHERE clause are built from constants and parameterised values only.
    # No user input flows into identifiers — safe to interpolate.
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT id, ticker, company_name, condition_tier, condition_code, "  # noqa: S608
                f"condition_label, confirmation_level, verdict, conviction_score, "
                f"triggered_at, created_at "
                f"FROM tv_signal_reports WHERE {where} "
                f"ORDER BY triggered_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        ).fetchall()
        total_row = conn.execute(
            text(f"SELECT COUNT(*) FROM tv_signal_reports WHERE {where}"),  # noqa: S608
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        ).fetchone()

    reports = [dict(r._mapping) for r in rows]
    return {"reports": reports, "total": total_row[0] if total_row else 0}


@router.get("/signals/{report_id}")
async def get_signal_report(report_id: str) -> dict:
    """Return a single signal report by UUID."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM tv_signal_reports WHERE id = :rid LIMIT 1"),
            {"rid": report_id},
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return dict(row._mapping)


@router.get("/screenshot")
async def serve_screenshot(
    request: Request,
    path: str = Query(..., description="Absolute path to PNG file on this server"),
) -> FileResponse:
    """Serve a signal screenshot PNG from the local filesystem.

    Protected by the internal secret header — only the frontend proxy calls this.
    The ``path`` parameter must fall within SIGNAL_SCREENSHOT_DIR.
    """
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != Config.ATLAS_INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    allowed_base = pathlib.Path(
        os.environ.get("SIGNAL_SCREENSHOT_DIR", "/data/signals/screenshots")
    ).resolve()
    resolved = pathlib.Path(path).resolve()

    if not str(resolved).startswith(str(allowed_base)):
        raise HTTPException(status_code=403, detail="Forbidden path")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(
        str(resolved), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )


@router.post("/generate-report")
async def generate_report_adhoc(
    body: dict,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    """Generate a signal report on demand for any ticker (internal use only).

    Requires ``X-Internal-Secret`` header matching ``Config.ATLAS_INTERNAL_SECRET``.
    """
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != Config.ATLAS_INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ticker = body.get("ticker", "").upper().strip()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker required")

    synthetic = TVSignalPayload(
        tier=0,
        code="adhoc",
        chart="vs_nifty",
        ticker=ticker,
        exchange="NSE",
        close=Decimal("0"),
        volume=0,
        time="",
        secret=Config.TV_WEBHOOK_SECRET,
    )
    background_tasks.add_task(process_signal, synthetic)
    return {"status": "accepted", "ticker": ticker}
