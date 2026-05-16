"""Read-only FastAPI endpoints for Atlas Strategy Lab.

All endpoints return the Atlas standard envelope:
  {"data": ..., "meta": {"data_as_of": <str|None>, "fetched_at": <str>}}

POST /api/trading/config is the only write — it upserts active PortfolioConfig.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/trading", tags=["trading"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _envelope(data: object, data_as_of: str | None = None) -> dict:  # type: ignore[type-arg]
    return {"data": data, "meta": {"data_as_of": data_as_of, "fetched_at": _now()}}


@router.get("/leaderboard")
def get_leaderboard(engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                SELECT l.rank, l.genome_id::text, l.strategy_name,
                       l.promoted_at::text, l.sortino_oos, l.calmar_oos,
                       l.alpha_30d, l.regime_breakdown,
                       g.genome_json, g.generation
                FROM atlas_strategy_leaderboard l
                JOIN atlas_strategy_genomes g ON g.id = l.genome_id
                ORDER BY l.rank
            """)
            )
            .mappings()
            .all()
        )
    return _envelope([dict(r) for r in rows])


@router.get("/genome/{genome_id}")
def get_genome(genome_id: str, engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("""
                SELECT id::text, genome_json, born_at::text, generation,
                       status, parent_ids::text[]
                FROM atlas_strategy_genomes
                WHERE id = :gid
            """),
                {"gid": genome_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Genome not found")

        perf = (
            conn.execute(
                text("""
                SELECT date::text, sortino_oos, calmar_oos, alpha_vs_nifty500,
                       max_drawdown, total_trades
                FROM atlas_strategy_performance_daily
                WHERE genome_id = :gid
                ORDER BY date DESC LIMIT 90
            """),
                {"gid": genome_id},
            )
            .mappings()
            .all()
        )

    return _envelope({"genome": dict(row), "performance": [dict(p) for p in perf]})


@router.get("/genome/{genome_id}/positions")
def get_positions(genome_id: str, engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                SELECT p.date::text, p.instrument_id::text, p.position_type,
                       p.entry_date::text, p.entry_price, p.shares,
                       p.current_value, p.unrealized_pnl,
                       p.holding_days, p.tax_status, p.entry_signals
                FROM atlas_strategy_positions_daily p
                WHERE p.genome_id = :gid
                  AND p.date = (
                      SELECT MAX(date) FROM atlas_strategy_positions_daily
                      WHERE genome_id = :gid
                  )
                ORDER BY p.current_value DESC
            """),
                {"gid": genome_id},
            )
            .mappings()
            .all()
        )
    return _envelope([dict(r) for r in rows])


@router.get("/insights/latest")
def get_latest_insights(engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("""
                SELECT generated_at::text, insight_bullets,
                       parameter_importance, top_genome_deltas
                FROM atlas_strategy_insights
                ORDER BY generated_at DESC LIMIT 1
            """)
            )
            .mappings()
            .first()
        )
    if not row:
        return _envelope({"bullets": [], "parameter_importance": {}})
    return _envelope(dict(row), data_as_of=row["generated_at"])


@router.get("/gene-pool/health")
def get_gene_pool_health(engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    with engine.connect() as conn:
        stats = (
            conn.execute(
                text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'active')   AS active_count,
                    COUNT(*) FILTER (WHERE status = 'killed')   AS killed_count,
                    COUNT(*) FILTER (WHERE status = 'promoted') AS promoted_count,
                    MAX(born_at)::text                          AS last_born_at
                FROM atlas_strategy_genomes
            """)
            )
            .mappings()
            .first()
        )
    return _envelope(dict(stats) if stats else {})


@router.get("/config")
def get_config(engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("""
                SELECT config_json FROM atlas_portfolio_config
                WHERE is_active = TRUE
                ORDER BY created_at DESC LIMIT 1
            """)
            )
            .mappings()
            .first()
        )
    if not row:
        from atlas.trading.config import PortfolioConfig

        return _envelope(PortfolioConfig().to_json())
    return _envelope(dict(row["config_json"]))


@router.post("/config")
def save_config(body: dict, engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    from atlas.trading.config import PortfolioConfig

    try:
        cfg = PortfolioConfig.from_json(body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with engine.connect() as conn:
        conn.execute(text("UPDATE atlas_portfolio_config SET is_active = FALSE"))
        conn.execute(
            text("""
                INSERT INTO atlas_portfolio_config (config_json, is_active, label)
                VALUES (CAST(:cfg AS jsonb), TRUE, :label)
            """),
            {"cfg": json.dumps(cfg.to_json()), "label": body.get("label", "")},
        )
        conn.commit()
    return _envelope(cfg.to_json())
