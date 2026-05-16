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
                FROM atlas.atlas_strategy_leaderboard l
                JOIN atlas.atlas_strategy_genomes g ON g.id = l.genome_id
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
                FROM atlas.atlas_strategy_genomes
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
                FROM atlas.atlas_strategy_performance_daily
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
                FROM atlas.atlas_strategy_positions_daily p
                WHERE p.genome_id = :gid
                  AND p.date = (
                      SELECT MAX(date) FROM atlas.atlas_strategy_positions_daily
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


@router.get("/recommendations/today")
def get_recommendations_today(engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    """Today's recommendations across top-N genomes — persistent state for the lab.

    Returns the latest date's recommendations grouped by genome. If today's
    nightly hasn't run yet, the most recent date in the table is returned with
    its actual data_as_of timestamp so the UI can warn the user.
    """
    with engine.connect() as conn:
        latest_date_row = (
            conn.execute(
                text("SELECT MAX(date)::text AS d FROM atlas.atlas_strategy_recommendations_daily")
            )
            .mappings()
            .first()
        )
        if not latest_date_row or not latest_date_row["d"]:
            return _envelope([])
        latest_date = latest_date_row["d"]
        rows = (
            conn.execute(
                text("""
                SELECT r.date::text, r.genome_id::text, r.rank, r.instrument_id::text,
                       r.action, r.conviction, r.position_size_pct, r.stop_price,
                       r.genome_alpha_oos, r.genome_information_ratio,
                       r.genome_hit_rate, r.genome_t_stat, r.confidence_band,
                       l.strategy_name
                FROM atlas.atlas_strategy_recommendations_daily r
                JOIN atlas.atlas_strategy_leaderboard l ON l.genome_id = r.genome_id
                WHERE r.date = CAST(:d AS date)
                ORDER BY r.rank, r.conviction DESC
            """),
                {"d": latest_date},
            )
            .mappings()
            .all()
        )
    return _envelope([dict(r) for r in rows], data_as_of=latest_date)


@router.get("/proof/{genome_id}")
def get_proof(genome_id: str, engine: Engine = Depends(get_engine)) -> dict:  # type: ignore[type-arg, misc]  # noqa: B008
    """Year-by-year backtest validation for a genome — the goal-post proof.

    Returns the data behind the Proof tab on /strategies/lab. Includes
    strategy_return + benchmark_return per year so the frontend can render
    'beat the benchmark with lower drawdown'.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                SELECT year, strategy_return, benchmark_return, alpha,
                       max_drawdown, benchmark_max_drawdown, sortino,
                       n_trades, avg_positions_held, run_at::text
                FROM atlas.atlas_strategy_validation
                WHERE genome_id = CAST(:gid AS uuid)
                ORDER BY year
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
                FROM atlas.atlas_strategy_insights
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
                FROM atlas.atlas_strategy_genomes
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
                SELECT config_json FROM atlas.atlas_portfolio_config
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
        conn.execute(text("UPDATE atlas.atlas_portfolio_config SET is_active = FALSE"))
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_portfolio_config (config_json, is_active, label)
                VALUES (CAST(:cfg AS jsonb), TRUE, :label)
            """),
            {"cfg": json.dumps(cfg.to_json()), "label": body.get("label", "")},
        )
        conn.commit()
    return _envelope(cfg.to_json())
