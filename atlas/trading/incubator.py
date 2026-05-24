"""Nightly incubator orchestrator — chains all atlas.trading modules.

Run as: python -m atlas.trading.incubator

Sequence:
  1. Load metrics from atlas.atlas_stock_metrics_daily + regime from atlas.atlas_market_regime_daily
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

_N_TRIALS_PER_NIGHT_DEFAULT = 200
_TARGET_POOL_SIZE = 120
_WALK_FORWARD_TRAIN_DAYS = 252
_WALK_FORWARD_TEST_DAYS = 90


def _n_trials_per_night() -> int:
    """Trial count for this run — env-override for Phase 0 burn-in (one-shot 2k–5k)."""
    raw = os.environ.get("ATLAS_INCUBATOR_TRIALS")
    if raw is None:
        return _N_TRIALS_PER_NIGHT_DEFAULT
    try:
        n = int(raw)
        return n if n > 0 else _N_TRIALS_PER_NIGHT_DEFAULT
    except ValueError:
        return _N_TRIALS_PER_NIGHT_DEFAULT


def _n_jobs() -> int:
    """Optuna n_jobs — thread pool size for parallel trial evaluation.

    Default 1 (sequential). Override via ATLAS_INCUBATOR_N_JOBS for burn-in
    runs on bigger instances. Suggested values:
      t3.2xlarge (8 vCPU):   n_jobs=4-6   (current)
      c6i.8xlarge (32 vCPU): n_jobs=16-24
      c6i.16xlarge (64 vCPU): n_jobs=32-48
    """
    raw = os.environ.get("ATLAS_INCUBATOR_N_JOBS")
    if raw is None:
        return 1
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        return 1


def _load_metrics_df(conn, start_date: date, end_date: date) -> pd.DataFrame:
    """Load derived metrics joined with raw close prices for vectorbt simulation.

    atlas.atlas_stock_metrics_daily holds only derived signals (RS, vol, EMA);
    raw close prices come from public.de_equity_ohlcv — the JIP data lake.
    Reading the lake directly is permitted (it's the shared data substrate,
    not another bounded context's internals).
    """
    log.info("loading_metrics", start=str(start_date), end=str(end_date))
    result = conn.execute(
        text(
            """
            SELECT
                m.instrument_id, m.date,
                COALESCE(p.close_adj, p.close) AS close,
                p.high, p.low,  -- for NATR (Normalized ATR — IR_IC 0.83, Q5-Q1 +9.33% OOS)
                m.rs_pctile_1w, m.rs_pctile_1m, m.rs_pctile_3m,
                m.vol_ratio_63, m.ema_20_ratio,
                m.ret_12m, m.realized_vol_63  -- inputs for mom_low_vol synthetic signal
            FROM atlas.atlas_stock_metrics_daily m
            JOIN public.de_equity_ohlcv p
              ON p.instrument_id = m.instrument_id
             AND p.date = m.date
            WHERE m.date BETWEEN :start AND :end
              AND COALESCE(p.close_adj, p.close) IS NOT NULL
            ORDER BY m.date, m.instrument_id
            """
        ),
        {"start": start_date, "end": end_date},
    )
    df = pd.DataFrame(result.mappings().all())
    log.info("metrics_loaded", rows=len(df))
    return df


def _load_corp_actions(conn, start_date: date, end_date: date) -> set[tuple[str, date]]:
    """Load split/bonus ex-dates so the simulator exempts them from masking.

    Returns a set of (instrument_id_str, ex_date) pairs. The sanitizer treats
    >50% one-day jumps as artifacts UNLESS the day is in this set.
    """
    result = conn.execute(
        text(
            """
            SELECT instrument_id::text AS iid, ex_date
            FROM public.de_corporate_actions
            WHERE action_type IN ('split', 'bonus')
              AND ratio_from IS NOT NULL
              AND ex_date BETWEEN :start AND :end
            """
        ),
        {"start": start_date, "end": end_date},
    )
    pairs = {(row["iid"], row["ex_date"]) for row in result.mappings()}
    log.info("corp_actions_loaded", rows=len(pairs))
    return pairs


def _load_regime_df(conn, start_date: date, end_date: date) -> pd.DataFrame:
    """Load regime state + Nifty 500 close for alpha-vs-benchmark computation.

    nifty500_close is the benchmark price series used by the simulator to
    compute per-window alpha (portfolio return minus Nifty 500 return).
    Per the goal post: optimize alpha, not absolute Sortino.
    """
    result = conn.execute(
        text(
            """
            SELECT date, pct_above_ema_50, india_vix, nifty500_close
            FROM atlas.atlas_market_regime_daily
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
                "SELECT config_json FROM atlas.atlas_portfolio_config "
                "WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if row:
        return PortfolioConfig.from_json(dict(row["config_json"]))
    return PortfolioConfig()


_DATA_CACHE_DIR = "/tmp/atlas_strategy_lab"


def _dump_data_for_workers(
    metrics_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    corp_actions: set,
    config: PortfolioConfig,
    walk_forward_windows: list,
) -> str:
    """Coordinator dumps data to /tmp/ files so workers can mmap-read without DB.

    Returns path to the journal file workers should use as Optuna storage.
    """
    import pickle

    os.makedirs(_DATA_CACHE_DIR, exist_ok=True)
    # Pickle instead of parquet: pyarrow is an optional dep we don't want to
    # require for the burn-in. DataFrames pickle fine; ~150MB on disk for the
    # 1.4M-row metrics_df, mmap-readable from each worker.
    metrics_df.to_pickle(f"{_DATA_CACHE_DIR}/metrics.pkl")
    regime_df.to_pickle(f"{_DATA_CACHE_DIR}/regime.pkl")
    with open(f"{_DATA_CACHE_DIR}/corp_actions.pkl", "wb") as f:
        pickle.dump(corp_actions, f)
    with open(f"{_DATA_CACHE_DIR}/config.pkl", "wb") as f:
        pickle.dump(config, f)
    with open(f"{_DATA_CACHE_DIR}/windows.pkl", "wb") as f:
        pickle.dump(walk_forward_windows, f)
    journal_path = f"{_DATA_CACHE_DIR}/study.log"
    # Fresh journal per burn-in — old trials shouldn't influence new study state.
    if os.path.exists(journal_path):
        os.remove(journal_path)
    log.info(
        "data_cached_for_workers",
        metrics_rows=len(metrics_df),
        regime_rows=len(regime_df),
        corp_actions=len(corp_actions),
        journal=journal_path,
    )
    return journal_path


def _load_data_in_worker() -> tuple:
    """Worker reads data from /tmp/ cache (no DB connections)."""
    import pickle

    metrics_df = pd.read_pickle(f"{_DATA_CACHE_DIR}/metrics.pkl")
    regime_df = pd.read_pickle(f"{_DATA_CACHE_DIR}/regime.pkl")
    with open(f"{_DATA_CACHE_DIR}/corp_actions.pkl", "rb") as f:
        corp_actions = pickle.load(f)
    with open(f"{_DATA_CACHE_DIR}/config.pkl", "rb") as f:
        config = pickle.load(f)
    with open(f"{_DATA_CACHE_DIR}/windows.pkl", "rb") as f:
        walk_forward_windows = pickle.load(f)
    return metrics_df, regime_df, corp_actions, config, walk_forward_windows


def _run_distributed_trials(n_trials: int, n_workers: int) -> None:
    """Spawn N worker subprocesses; each runs n_trials/N trials of its own.

    Workers share an Optuna RDB study (Postgres) so they pull and push trials
    to a single coordinated optimization. Each worker is a separate Python
    interpreter → no GIL contention; uses 1 core fully.
    """
    import subprocess
    import sys

    import time

    trials_per_worker = max(1, n_trials // n_workers)
    extra = n_trials - (trials_per_worker * n_workers)
    log_dir = os.path.expanduser("~/logs/strategy_lab_workers")
    os.makedirs(log_dir, exist_ok=True)
    procs = []
    for i in range(n_workers):
        env = os.environ.copy()
        env["ATLAS_INCUBATOR_WORKER_MODE"] = "1"
        env["ATLAS_INCUBATOR_TRIALS"] = str(trials_per_worker + (1 if i < extra else 0))
        env["ATLAS_INCUBATOR_N_JOBS"] = "1"
        env["ATLAS_INCUBATOR_WORKER_ID"] = str(i)
        # Capture per-worker stderr so failures surface for diagnosis.
        log_path = os.path.join(log_dir, f"worker_{i:02d}.log")
        log_file = open(log_path, "w")  # noqa: SIM115 — kept open for subprocess
        proc = subprocess.Popen(
            [sys.executable, "-m", "atlas.trading.incubator"],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        procs.append((proc, log_file, log_path))
        log.info(
            "worker_spawned",
            worker=i,
            trials=env["ATLAS_INCUBATOR_TRIALS"],
            pid=proc.pid,
            log=log_path,
        )
        # Stagger startups to avoid 24 simultaneous DB connection storms
        # (Optuna study creation + metrics_df load). Empirically, 0.3s spacing
        # is enough for Supabase to absorb the wave.
        time.sleep(0.3)

    failed = 0
    failed_logs: list[str] = []
    for i, (proc, log_file, log_path) in enumerate(procs):
        rc = proc.wait()
        log_file.close()
        if rc != 0:
            failed += 1
            failed_logs.append(log_path)
            log.warning("worker_nonzero_exit", worker=i, rc=rc, log=log_path)
        else:
            log.info("worker_done", worker=i)
    log.info(
        "all_workers_done",
        n_workers=n_workers,
        failed=failed,
        failed_logs=failed_logs[:3],
    )


def _reconstruct_genome_scores_from_study(
    study: OptunaStudy,
) -> list[tuple[Genome, float, float, float]]:
    """Read completed trials from the shared study, rebuild (genome, alpha, IR, sortino).

    Workers set user_attrs["ir"] and user_attrs["sortino"] on each trial; this
    reader pulls them back so the coordinator can rank survivors without
    re-running the simulations.
    """
    import optuna

    from atlas.trading.genome import GenomeFactory

    scores: list[tuple[Genome, float, float, float]] = []
    for trial in study._study.trials:
        if trial.state != optuna.trial.TrialState.COMPLETE or trial.value is None:
            continue
        try:
            genome = GenomeFactory.from_optuna_trial(optuna.trial.FixedTrial(trial.params))
        except Exception:
            continue  # malformed/old trial — skip
        alpha = float(trial.value)
        ir = float(trial.user_attrs.get("ir", 0.0))
        sortino = float(trial.user_attrs.get("sortino", 0.0))
        scores.append((genome, alpha, ir, sortino))
    # Best alpha first
    scores.sort(key=lambda t: t[1], reverse=True)
    return scores


def run_nightly(conn, config: PortfolioConfig | None = None) -> dict[str, Any]:
    """Run the full nightly incubator cycle. Returns a summary dict."""
    if config is None:
        config = _load_active_config(conn)

    today = date.today()
    data_start = today - timedelta(days=365 * 12)
    worker_mode = os.environ.get("ATLAS_INCUBATOR_WORKER_MODE") == "1"

    if worker_mode:
        # Worker mode: load data from coordinator's parquet cache. No DB.
        log.info("worker_loading_cached_data")
        metrics_df, regime_df, corp_actions, config_from_cache, walk_forward_windows = (
            _load_data_in_worker()
        )
        config = config_from_cache
    else:
        metrics_df = _load_metrics_df(conn, data_start, today)
        regime_df = _load_regime_df(conn, data_start, today)
        corp_actions = _load_corp_actions(conn, data_start, today)
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

    # Study: file-based JournalStorage when n_jobs > 1 (multi-process) so
    # workers don't need DB connections. Single-process path uses Postgres RDB.
    n_jobs = _n_jobs()
    if worker_mode or n_jobs > 1:
        journal_path = f"{_DATA_CACHE_DIR}/study.log"
        study = OptunaStudy.journal(journal_path)
    else:
        db_url = os.environ.get("ATLAS_DB_URL", "")
        study = (
            OptunaStudy.production(db_url) if db_url else OptunaStudy("atlas_strategy_lab_v1")
        )

    # Tuple shape: (genome, alpha_oos, information_ratio, sortino_oos)
    # Alpha is the primary score (Optuna objective). IR + Sortino are kept for
    # downstream ranking + diagnostics. Order matters: index 1 is the score.
    genome_scores: list[tuple[Genome, float, float, float]] = []

    def objective(genome: Genome, trial=None) -> float:
        """Optimize alpha vs Nifty 500. Goal post: maximize alpha with confidence.

        Sets trial.user_attrs so multi-process workers can persist IR + Sortino
        to the shared Optuna RDB study; coordinator reconstructs genome_scores
        from those attrs after workers finish.
        """
        result = simulate_genome(
            genome,
            metrics_df,
            regime_df,
            config,
            walk_forward_windows,
            corp_actions=corp_actions,
        )
        if trial is not None:
            trial.set_user_attr("ir", float(result.information_ratio))
            trial.set_user_attr("sortino", float(result.sortino_oos))
        genome_scores.append(
            (genome, result.alpha_oos, result.information_ratio, result.sortino_oos)
        )
        return result.alpha_oos

    n_trials = _n_trials_per_night()
    n_jobs = _n_jobs()
    worker_mode = os.environ.get("ATLAS_INCUBATOR_WORKER_MODE") == "1"

    if worker_mode:
        # Worker mode: just run our share of trials, exit. Coordinator will
        # spawn N of these in parallel and reconstruct results from the
        # shared Optuna RDB study after all workers complete.
        log.info("worker_mode_running_trials", n_trials=n_trials)
        study.run_trials(n_trials=n_trials, objective_fn=objective, n_jobs=1)
        log.info("worker_mode_done", trials=n_trials)
        return {"status": "worker_done", "trials_run": n_trials}

    if n_jobs > 1:
        # Coordinator mode: dump data to /tmp parquet so workers don't need DB,
        # then spawn N subprocess workers. Workers share a file-locked
        # JournalStorage Optuna study (zero DB connections during trials).
        log.info("coordinator_dumping_data_for_workers")
        _dump_data_for_workers(
            metrics_df, regime_df, corp_actions, config, walk_forward_windows
        )
        log.info("coordinator_spawning_workers", n_workers=n_jobs, total_trials=n_trials)
        _run_distributed_trials(n_trials, n_jobs)
        # Reload study from journal (workers' results live there)
        study = OptunaStudy.journal(f"{_DATA_CACHE_DIR}/study.log")
        genome_scores = _reconstruct_genome_scores_from_study(study)
        log.info("coordinator_reconstructed_scores", n=len(genome_scores))
    else:
        # Single-process legacy path
        log.info("running_optuna_trials", n=n_trials, n_jobs=n_jobs)
        study.run_trials(n_trials=n_trials, objective_fn=objective, n_jobs=n_jobs)

    if not genome_scores:
        # Every trial raised inside simulate_genome — surface this distinctly
        # from "trials ran but nothing was good enough to promote" so an
        # operator can tell whether the engine is broken vs the genes are bad.
        log.error("all_trials_failed_no_scores", n_trials=n_trials)
        return {"status": "aborted", "reason": "all_trials_failed", "trials_run": n_trials}

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
            return simulate_genome(g, metrics_df, regime_df, config, w, corp_actions=corp_actions)

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

    # Insight generation — surface the goal-post metrics to the LLM narrator.
    # Sortino can be ±Infinity when std-of-returns is 0 (degenerate genome with
    # all-equal returns or no trades). JSON can't serialize Infinity into JSONB.
    # NaN can also leak through. Replace both with None before passing to LLM/DB.
    def _finite(v: float) -> float | None:
        if v != v:  # NaN
            return None
        if v == float("inf") or v == float("-inf"):
            return None
        return float(v)

    importance = study.get_parameter_importance()
    top_deltas = [
        {
            "genome_id": g.genome_id,
            "alpha": _finite(alpha),
            "ir": _finite(ir),
            "sortino": _finite(sortino),
        }
        for g, alpha, ir, sortino in genome_scores[:5]
    ]
    bullets = generate_insights(importance, top_deltas)

    if bullets:
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_strategy_insights
                    (id, generated_at, insight_bullets, parameter_importance, top_genome_deltas)
                VALUES
                    (gen_random_uuid(), NOW(),
                     CAST(:bullets AS jsonb),
                     CAST(:importance AS jsonb),
                     CAST(:deltas AS jsonb))
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
        "trials_run": n_trials,
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
    # Worker-mode and coordinator both run from this entrypoint. Sized at
    # pool_size=1, max_overflow=0 so each worker holds at most 1 DB
    # connection in addition to Optuna's own (also 1). That keeps total
    # under Supabase pooler's 15-connection limit even with 6+ workers.
    _engine = create_engine(_db_url, pool_size=1, max_overflow=0, pool_pre_ping=True)
    with _engine.connect() as _conn:
        run_nightly(_conn)
        _conn.commit()
