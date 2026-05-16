"""Nightly incubator orchestrator — chains all atlas.trading modules.

Run as: python -m atlas.trading.incubator

Sequence:
  1. Load metrics from atlas_stock_metrics_daily + regime from atlas_market_regime_daily
  2. Run Optuna trials: simulate_genome → score
  3. DEAP breeding: crossover top performers, mutate top 5
  4. Tournament: evaluate top 10 candidates, promote survivors to leaderboard
  5. Insight generation: Groq narrates optimization deltas
  6. Persist insight bullets to atlas_strategy_insights
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from atlas.trading.config import PortfolioConfig
from atlas.trading.evolver import Evolver
from atlas.trading.genome import Genome
from atlas.trading.insight import generate_insights
from atlas.trading.optimizer import OptunaStudy
from atlas.trading.simulator import SimResult, simulate_genome
from atlas.trading.tournament import TournamentEvaluator, promote_to_leaderboard

log = structlog.get_logger()

_STRESS_PERIODS = {
    "covid_2020": (date(2020, 2, 1), date(2020, 5, 31)),
    "bear_2022": (date(2022, 1, 1), date(2022, 6, 30)),
    "bull_2023": (date(2023, 1, 1), date(2023, 12, 31)),
}

_N_TRIALS_PER_NIGHT = 200
_TARGET_POOL_SIZE = 120
_WALK_FORWARD_TRAIN_DAYS = 252
_WALK_FORWARD_TEST_DAYS = 90


def _load_metrics_df(conn, start_date: date, end_date: date) -> pd.DataFrame:
    log.info("loading_metrics", start=str(start_date), end=str(end_date))
    result = conn.execute(
        text(
            """
            SELECT
                m.instrument_id, m.date, m.close,
                m.rs_pctile_1w, m.rs_pctile_1m, m.rs_pctile_3m,
                m.vol_ratio_63, m.ema_20_ratio
            FROM atlas_stock_metrics_daily m
            WHERE m.date BETWEEN :start AND :end
            ORDER BY m.date, m.instrument_id
            """
        ),
        {"start": start_date, "end": end_date},
    )
    df = pd.DataFrame(result.mappings().all())
    log.info("metrics_loaded", rows=len(df))
    return df


def _load_regime_df(conn, start_date: date, end_date: date) -> pd.DataFrame:
    result = conn.execute(
        text(
            """
            SELECT date, pct_above_ema_50, india_vix
            FROM atlas_market_regime_daily
            WHERE date BETWEEN :start AND :end
            ORDER BY date
            """
        ),
        {"start": start_date, "end": end_date},
    )
    df = pd.DataFrame(result.mappings().all())
    log.info("regime_loaded", rows=len(df))
    return df


def _build_walk_forward_windows(
    start_date: date,
    end_date: date,
    train_days: int = _WALK_FORWARD_TRAIN_DAYS,
    test_days: int = _WALK_FORWARD_TEST_DAYS,
) -> list[tuple[date, date, date, date]]:
    windows = []
    cursor = start_date
    while cursor + timedelta(days=train_days + test_days) <= end_date:
        train_end = cursor + timedelta(days=train_days)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        windows.append((cursor, train_end, test_start, test_end))
        cursor += timedelta(days=test_days)
    return windows


def _load_active_config(conn) -> PortfolioConfig:
    row = (
        conn.execute(
            text(
                "SELECT config_json FROM atlas_portfolio_config "
                "WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if row:
        return PortfolioConfig.from_json(dict(row["config_json"]))
    return PortfolioConfig()


def run_nightly(conn, config: PortfolioConfig | None = None) -> dict[str, Any]:
    """Run the full nightly incubator cycle. Returns a summary dict."""
    if config is None:
        config = _load_active_config(conn)

    today = date.today()
    data_start = today - timedelta(days=365 * 12)
    metrics_df = _load_metrics_df(conn, data_start, today)
    regime_df = _load_regime_df(conn, data_start, today)

    if metrics_df.empty:
        log.error("no_metrics_data_abort")
        return {"status": "aborted", "reason": "no_metrics_data"}

    walk_forward_windows = _build_walk_forward_windows(
        start_date=today - timedelta(days=365 * 10),
        end_date=today,
    )
    if not walk_forward_windows:
        log.error("no_walk_forward_windows")
        return {"status": "aborted", "reason": "no_walk_forward_windows"}

    db_url = os.environ.get("ATLAS_DB_URL", "")
    study = OptunaStudy.production(db_url) if db_url else OptunaStudy("atlas_strategy_lab_v1")

    genome_scores: list[tuple[Genome, float, float]] = []

    def objective(genome: Genome) -> float:
        result = simulate_genome(genome, metrics_df, regime_df, config, walk_forward_windows)
        genome_scores.append((genome, result.sortino_oos, result.calmar_oos))
        return result.sortino_oos

    log.info("running_optuna_trials", n=_N_TRIALS_PER_NIGHT)
    study.run_trials(n_trials=_N_TRIALS_PER_NIGHT, objective_fn=objective)

    # DEAP breeding
    evolver = Evolver()
    survivors = evolver.select_survivors(genome_scores, target_pool=_TARGET_POOL_SIZE)
    offspring: list[Genome] = []
    if len(survivors) >= 2:
        child_a, child_b = evolver.crossover(survivors[0], survivors[1])
        offspring = [child_a, child_b]
        mutated = [evolver.mutate(g) for g in survivors[:5]]
        offspring.extend(mutated)
    log.info("breeding_complete", offspring=len(offspring))

    # Tournament evaluation
    evaluator = TournamentEvaluator(stress_periods=_STRESS_PERIODS)
    recent_end = today
    recent_start = today - timedelta(days=89)

    # half_test is constant across all tournament iterations — hoist to avoid B023
    _half_test = _WALK_FORWARD_TEST_DAYS // 2

    def _make_sim_fn(half: int):
        """Return a sim_fn that splits [start, end] into train+test windows."""

        def sim_fn(g: Genome, start: date, end: date) -> SimResult:
            w = [(start, end - timedelta(days=half), end - timedelta(days=half - 1), end)]
            return simulate_genome(g, metrics_df, regime_df, config, w)

        return sim_fn

    _sim_fn = _make_sim_fn(_half_test)

    promoted_count = 0
    for genome, *_ in genome_scores[:10]:
        result = evaluator.evaluate(
            genome, _sim_fn, recent_start=recent_start, recent_end=recent_end
        )
        if result.promoted and promoted_count < 5:
            promote_to_leaderboard(conn, genome, result, rank=promoted_count + 1)
            promoted_count += 1

    # Insight generation
    importance = study.get_parameter_importance()
    top_deltas = [{"genome_id": g.genome_id, "sortino": s} for g, s, _ in genome_scores[:5]]
    bullets = generate_insights(importance, top_deltas)

    if bullets:
        conn.execute(
            text(
                """
                INSERT INTO atlas_strategy_insights
                    (id, generated_at, insight_bullets, parameter_importance, top_genome_deltas)
                VALUES
                    (gen_random_uuid(), NOW(),
                     :bullets::jsonb, :importance::jsonb, :deltas::jsonb)
                """
            ),
            {
                "bullets": json.dumps(bullets),
                "importance": json.dumps({k: float(v) for k, v in importance.items()}),
                "deltas": json.dumps(top_deltas),
            },
        )

    summary = {
        "status": "ok",
        "trials_run": _N_TRIALS_PER_NIGHT,
        "genomes_evaluated": len(genome_scores),
        "promoted": promoted_count,
        "offspring": len(offspring),
        "insight_bullets": len(bullets),
        "windows": len(walk_forward_windows),
    }
    log.info("nightly_run_complete", **{k: v for k, v in summary.items() if k != "status"})
    return summary


if __name__ == "__main__":
    import structlog as sl

    sl.configure()
    _db_url = os.environ["ATLAS_DB_URL"]
    _engine = create_engine(_db_url)
    with _engine.connect() as _conn:
        run_nightly(_conn)
        _conn.commit()
