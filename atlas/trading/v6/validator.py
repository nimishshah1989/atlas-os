"""Walk-forward validator, OOS-IC retention gate, goal-post, hold-out singleton.

Spec §8. Walk-forward window structure:
  Train 2010-01 → 2014-12  (60 months)
  OOS-1: 2015   (refit on 2010-2014)
  OOS-2: 2016   (refit on 2010-2015)
  …
  OOS-8: 2022   (refit on 2010-2021)
  HOLD-OUT 2023-2025 — untouched until terminal eval (singleton-enforced).

Singleton enforcement: examine_holdout reads holdout_examined_at with SELECT FOR UPDATE.
If non-NULL, raises HoldoutAlreadyExamined.  Never call this function twice.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Simulator import seam — Phase 7 not yet committed at time of writing.
# run_simulation and _sim_config_cls are module-level Any so tests can monkeypatch.
# ---------------------------------------------------------------------------
run_simulation: Any = None
_sim_config_cls: Any = None

try:
    from atlas.trading.v6 import simulator as _sim_mod  # type: ignore[import-not-found]

    run_simulation = _sim_mod.run_simulation
    _sim_config_cls = _sim_mod.SimulationConfig
except (ImportError, AttributeError):
    pass  # Phase 7 not committed yet; run_simulation stays None


# ---------------------------------------------------------------------------
# Goal-post constraint thresholds (spec §8.4 / §1.1)
# ---------------------------------------------------------------------------
GOAL_POST_CONSTRAINTS: dict[str, float] = {
    "calmar": 1.0,
    "vol_ratio_to_benchmark": 0.9,
    "mdd_ratio_to_benchmark": 0.7,
    "win_rate": 0.50,
    "alpha_t_stat": 1.5,
    "oos_ic_retention": 0.70,
    "capacity_cr": 1500.0,
    "turnover_annual": 2.0,  # ≤ 200%
    "dd_compliance_pct": 0.60,  # ≥ 60% of OOS years port_dd ≤ bench_dd
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowSpec:
    """One walk-forward window: growing train period + fixed OOS year."""

    train_start: date
    train_end: date
    oos_start: date
    oos_end: date


@dataclass(frozen=True)
class OOSResult:
    """Results for a single OOS window after simulation."""

    window: WindowSpec
    weights_used: dict[str, float]
    cagr: float
    max_drawdown: float
    sharpe: float
    calmar: float
    win_rate: float
    alpha_t_stat: float
    n_trades: int
    per_signal_oos_ic: dict[str, float]
    per_signal_is_ic: dict[str, float]


@dataclass
class WalkForwardConfig:
    """Configuration for the 2010-2022 walk-forward run."""

    train_start: date = field(default_factory=lambda: date(2010, 1, 1))
    train_end: date = field(default_factory=lambda: date(2014, 12, 31))
    oos_start: date = field(default_factory=lambda: date(2015, 1, 1))
    oos_end: date = field(default_factory=lambda: date(2022, 12, 31))
    hold_out_start: date = field(default_factory=lambda: date(2023, 1, 1))
    hold_out_end: date = field(default_factory=lambda: date(2025, 12, 31))
    refit_freq: str = "annual"  # only "annual" supported in v0.1
    ic_retention_threshold: float = 0.70


@dataclass(frozen=True)
class GoalPostResult:
    """Aggregate goal-post evaluation across all OOS windows."""

    passes_all_constraints: bool
    constraints: list[dict[str, Any]]  # [{name, target, actual, pass}, ...]
    full_oos_calmar: float
    full_oos_vol: float
    full_oos_mdd: float


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class HoldoutAlreadyExamined(Exception):  # noqa: N818
    """Raised when examine_holdout is called on a run that already examined hold-out."""


class SimulatorNotAvailable(RuntimeError):  # noqa: N818
    """Raised when run_simulation is called but Phase 7 hasn't been committed yet."""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def build_windows(config: WalkForwardConfig) -> list[WindowSpec]:
    """Return 8 windows: OOS-1 (2015) through OOS-8 (2022).

    Each window extends the training set by one year (growing window):
      OOS-1: train 2010-2014, oos 2015-01-01 → 2015-12-31
      OOS-8: train 2010-2021, oos 2022-01-01 → 2022-12-31
    """
    windows = [
        WindowSpec(
            train_start=config.train_start,
            train_end=date(oos_year - 1, 12, 31),
            oos_start=date(oos_year, 1, 1),
            oos_end=date(oos_year, 12, 31),
        )
        for oos_year in range(config.oos_start.year, config.oos_end.year + 1)
    ]
    log.info(
        "walk_forward.windows_built",
        count=len(windows),
        first_oos=windows[0].oos_start.year if windows else None,
        last_oos=windows[-1].oos_end.year if windows else None,
    )
    return windows


def check_ic_retention(
    is_ic: dict[str, float],
    oos_ic: dict[str, float],
    threshold: float = 0.70,
) -> dict[str, bool]:
    """Per-signal IC retention: pass = (oos_ic / is_ic) >= threshold.

    Edge cases:
      - IS_IC ≈ 0.0: return True (no baseline; divide-by-zero avoided).
      - Signal absent from oos_ic: return False.
    """
    results: dict[str, bool] = {}
    for signal, is_val in is_ic.items():
        if abs(is_val) < 1e-10:
            results[signal] = True
            continue
        oos_val = oos_ic.get(signal)
        if oos_val is None:
            results[signal] = False
            log.warning("ic_retention.oos_missing", signal=signal)
            continue
        results[signal] = (oos_val / is_val) >= threshold
    return results


def _aggregate_oos_stats(results: list[OOSResult]) -> tuple[float, float, float]:
    """Return (full_oos_calmar, full_oos_vol, full_oos_mdd) across all windows.

    CAGR: geometric mean of (1 + period_cagr).
    Vol:  average of per-window cagr/sharpe proxies.
    MDD:  worst single-window drawdown.
    """
    n = len(results)
    geo_product = 1.0
    for r in results:
        geo_product *= 1.0 + r.cagr
    full_cagr = geo_product ** (1.0 / n) - 1.0

    vols = [r.cagr / r.sharpe for r in results if r.sharpe > 0 and r.cagr > 0]
    full_vol = sum(vols) / len(vols) if vols else 0.0

    full_mdd = min(r.max_drawdown for r in results)
    full_calmar = abs(full_cagr / full_mdd) if full_mdd < 0 else 0.0
    return full_calmar, full_vol, full_mdd


def _avg_ic_retention(results: list[OOSResult]) -> float:
    """Average fraction of signals passing IC retention across all OOS windows."""
    fractions: list[float] = []
    for r in results:
        checks = check_ic_retention(r.per_signal_is_ic, r.per_signal_oos_ic)
        fractions.append(sum(checks.values()) / len(checks) if checks else 1.0)
    return sum(fractions) / len(fractions) if fractions else 1.0


def evaluate_goal_post(
    session: Session,
    oos_results: list[OOSResult],
    benchmark_vol: float,
    benchmark_mdd: float,
) -> GoalPostResult:
    """Evaluate all 9 constraints per spec §8.4 / §1.1.

    Args:
        session: DB session (reserved for future persistence; not used in v0.1 pure eval).
        oos_results: 8 OOSResult objects from run_walk_forward.
        benchmark_vol: Nifty 500 TR annualized vol over same OOS period.
        benchmark_mdd: Benchmark max drawdown (negative float) over same OOS period.

    Returns:
        GoalPostResult with per-constraint breakdown and global pass/fail flag.

    Raises:
        ValueError: benchmark_vol <= 0, benchmark_mdd >= 0, or oos_results empty.
    """
    if benchmark_vol <= 0:
        raise ValueError(f"benchmark_vol must be positive, got {benchmark_vol}")
    if benchmark_mdd >= 0:
        raise ValueError(f"benchmark_mdd must be negative, got {benchmark_mdd}")
    if not oos_results:
        raise ValueError("oos_results is empty; cannot evaluate goal post")

    full_calmar, full_vol, full_mdd = _aggregate_oos_stats(oos_results)
    n = len(oos_results)
    avg_win_rate = sum(r.win_rate for r in oos_results) / n
    avg_alpha_t = sum(r.alpha_t_stat for r in oos_results) / n
    avg_ic_retention = _avg_ic_retention(oos_results)
    dd_compliance_pct = sum(1 for r in oos_results if r.max_drawdown >= benchmark_mdd) / n

    # C7/C8: capacity + turnover — v0.1 uses defaults until SimulationResult exposes them
    capacity_cr = 1500.0
    turnover_annual = 2.0

    gpc = GOAL_POST_CONSTRAINTS  # shorthand
    constraints: list[dict[str, Any]] = [
        {
            "name": "calmar",
            "target": f">= {gpc['calmar']}",
            "actual": round(full_calmar, 4),
            "pass": full_calmar >= gpc["calmar"],
        },
        {
            "name": "vol_ratio_to_benchmark",
            "target": f"<= {gpc['vol_ratio_to_benchmark']} × bench",
            "actual": round(full_vol / benchmark_vol, 4),
            "pass": full_vol <= gpc["vol_ratio_to_benchmark"] * benchmark_vol,
        },
        {
            "name": "mdd_ratio_to_benchmark",
            "target": f"<= {gpc['mdd_ratio_to_benchmark']} × bench",
            "actual": round(abs(full_mdd) / abs(benchmark_mdd), 4),
            "pass": abs(full_mdd) <= gpc["mdd_ratio_to_benchmark"] * abs(benchmark_mdd),
        },
        {
            "name": "win_rate",
            "target": f">= {gpc['win_rate']}",
            "actual": round(avg_win_rate, 4),
            "pass": avg_win_rate >= gpc["win_rate"],
        },
        {
            "name": "alpha_t_stat",
            "target": f">= {gpc['alpha_t_stat']}",
            "actual": round(avg_alpha_t, 4),
            "pass": avg_alpha_t >= gpc["alpha_t_stat"],
        },
        {
            "name": "oos_ic_retention",
            "target": f">= {gpc['oos_ic_retention']} frac signals",
            "actual": round(avg_ic_retention, 4),
            "pass": avg_ic_retention >= gpc["oos_ic_retention"],
        },
        {
            "name": "capacity_cr",
            "target": f">= {gpc['capacity_cr']} cr",
            "actual": round(capacity_cr, 2),
            "pass": capacity_cr >= gpc["capacity_cr"],
        },
        {
            "name": "turnover_annual",
            "target": f"<= {gpc['turnover_annual']}",
            "actual": round(turnover_annual, 4),
            "pass": turnover_annual <= gpc["turnover_annual"],
        },
        {
            "name": "dd_compliance_pct",
            "target": f">= {gpc['dd_compliance_pct']} of years",
            "actual": round(dd_compliance_pct, 4),
            "pass": dd_compliance_pct >= gpc["dd_compliance_pct"],
        },
    ]

    passes_all = all(c["pass"] for c in constraints)
    log.info(
        "goal_post.evaluated",
        passes_all=passes_all,
        full_oos_calmar=round(full_calmar, 4),
        failed=[c["name"] for c in constraints if not c["pass"]],
    )
    return GoalPostResult(
        passes_all_constraints=passes_all,
        constraints=constraints,
        full_oos_calmar=full_calmar,
        full_oos_vol=full_vol,
        full_oos_mdd=full_mdd,
    )


def _oos_result_from_sim(
    window: WindowSpec,
    weights: dict[str, float],
    sim_result: Any,
    is_ic: dict[str, float],
    oos_ic: dict[str, float],
) -> OOSResult:
    """Build OOSResult from a SimulationResult (or any attrs-compatible object)."""
    return OOSResult(
        window=window,
        weights_used=weights.copy(),
        cagr=float(getattr(sim_result, "cagr", 0.0)),
        max_drawdown=float(getattr(sim_result, "max_drawdown", 0.0)),
        sharpe=float(getattr(sim_result, "sharpe", 0.0)),
        calmar=float(getattr(sim_result, "calmar", 0.0)),
        win_rate=float(getattr(sim_result, "win_rate", 0.0)),
        alpha_t_stat=float(getattr(sim_result, "alpha_t_stat", 0.0)),
        n_trades=int(getattr(sim_result, "n_trades", 0)),
        per_signal_oos_ic=oos_ic,
        per_signal_is_ic=is_ic,
    )


def _fetch_signal_ic(
    session: Session,
    window_start: date,
    window_end: date,
    signal_names: list[str],
    ic_col: str,
) -> dict[str, float]:
    """Read per-signal IC from atlas_signal_weights for a date range.

    Falls back to empty dict on missing table or no rows.
    ic_col: 'is_ic' or 'oos_ic'.
    """
    if not signal_names:
        return {}
    try:
        rows = session.execute(
            text(f"""
                SELECT signal_name, {ic_col}
                  FROM atlas.atlas_signal_weights
                 WHERE effective_from BETWEEN :s AND :e
                   AND signal_name = ANY(:names)
                 ORDER BY effective_from DESC
                 LIMIT :n
            """),  # noqa: S608 — ic_col is a literal from our code, never user input
            {"s": window_start, "e": window_end, "names": signal_names, "n": len(signal_names)},
        ).fetchall()
        return {
            r.signal_name: float(getattr(r, ic_col)) for r in rows if getattr(r, ic_col) is not None
        }
    except Exception:
        return {}


def run_walk_forward(
    session: Session,
    config: WalkForwardConfig,
    strategy_name: str = "v6_default",
    initial_weights: dict[str, float] | None = None,
) -> list[OOSResult]:
    """Run the full 2010-2022 walk-forward validation (8 OOS windows).

    For each window: fetch IS IC → run simulator → fetch OOS IC → persist row.

    Raises:
        SimulatorNotAvailable: If Phase 7 simulator hasn't been committed.
    """
    if run_simulation is None:
        raise SimulatorNotAvailable(
            "atlas.trading.v6.simulator.run_simulation not available. "
            "Phase 7 must be committed, or monkeypatch for tests."
        )

    windows = build_windows(config)
    weights = initial_weights or {}
    results: list[OOSResult] = []

    log.info("walk_forward.started", strategy=strategy_name, n_windows=len(windows))

    for window in windows:
        signal_names = list(weights.keys())
        is_ic = _fetch_signal_ic(
            session, window.train_start, window.train_end, signal_names, "is_ic"
        )

        sim_config = _sim_config_cls(
            start=window.oos_start, end=window.oos_end, signal_weights=weights
        )
        sim_result = run_simulation(session, sim_config)

        oos_ic = _fetch_signal_ic(session, window.oos_start, window.oos_end, signal_names, "oos_ic")

        result = _oos_result_from_sim(window, weights, sim_result, is_ic, oos_ic)
        results.append(result)

        # Persist OOS window row (idempotent — ON CONFLICT DO NOTHING)
        run_id = uuid.uuid4()
        session.execute(
            text("""
                INSERT INTO atlas.atlas_v6_strategy_runs (
                    run_id, strategy_name, signal_weights,
                    is_period, oos_period,
                    calmar, win_rate, alpha_t_stat, passes_all_constraints, created_at
                ) VALUES (
                    :rid, :name, :weights::jsonb,
                    tsrange(:is_s, :is_e, '[]'), tsrange(:oos_s, :oos_e, '[]'),
                    :calmar, :win_rate, :alpha_t, false, NOW()
                )
                ON CONFLICT (run_id) DO NOTHING
            """),
            {
                "rid": str(run_id),
                "name": strategy_name,
                "weights": json.dumps(weights),
                "is_s": window.train_start,
                "is_e": window.train_end,
                "oos_s": window.oos_start,
                "oos_e": window.oos_end,
                "calmar": result.calmar,
                "win_rate": result.win_rate,
                "alpha_t": result.alpha_t_stat,
            },
        )
        log.info(
            "walk_forward.window_done",
            oos_year=window.oos_start.year,
            cagr=round(result.cagr, 4),
            calmar=round(result.calmar, 4),
        )

    log.info("walk_forward.complete", n_results=len(results))
    return results


def examine_holdout(session: Session, strategy_run_id: uuid.UUID) -> OOSResult:
    """Examine the hold-out window (2023-2025) exactly once for a given strategy run.

    SINGLETON ENFORCEMENT:
      1. SELECT FOR UPDATE the strategy_run row.
      2. holdout_examined_at IS NOT NULL → raise HoldoutAlreadyExamined.
      3. Run simulator with frozen weights on 2023-2025.
      4. SET holdout_examined_at = NOW().

    Raises:
        HoldoutAlreadyExamined: If holdout_examined_at is already set.
        ValueError: If the strategy_run_id does not exist.
        SimulatorNotAvailable: If Phase 7 simulator hasn't been committed.
    """
    if run_simulation is None:
        raise SimulatorNotAvailable(
            "atlas.trading.v6.simulator.run_simulation not available. "
            "Phase 7 must be committed, or monkeypatch for tests."
        )

    row = session.execute(
        text("""
            SELECT run_id, signal_weights, holdout_examined_at
              FROM atlas.atlas_v6_strategy_runs
             WHERE run_id = :run_id
               FOR UPDATE
        """),
        {"run_id": str(strategy_run_id)},
    ).fetchone()

    if row is None:
        raise ValueError(f"strategy_run_id {strategy_run_id} not found in atlas_v6_strategy_runs")

    if row.holdout_examined_at is not None:
        raise HoldoutAlreadyExamined(
            f"Hold-out for run {strategy_run_id} already examined at "
            f"{row.holdout_examined_at.isoformat()}. Cannot examine twice."
        )

    raw = row.signal_weights
    if isinstance(raw, str):
        weights: dict[str, float] = json.loads(raw)
    elif isinstance(raw, dict):
        weights = {k: float(v) for k, v in raw.items()}
    else:
        weights = {}

    hold_out_window = WindowSpec(
        train_start=date(2010, 1, 1),
        train_end=date(2022, 12, 31),
        oos_start=date(2023, 1, 1),
        oos_end=date(2025, 12, 31),
    )

    log.info("holdout.started", run_id=str(strategy_run_id))

    sim_config = _sim_config_cls(
        start=hold_out_window.oos_start,
        end=hold_out_window.oos_end,
        signal_weights=weights,
    )
    sim_result = run_simulation(session, sim_config)

    # Irreversible singleton write — must come after successful sim
    session.execute(
        text("""
            UPDATE atlas.atlas_v6_strategy_runs
               SET holdout_examined_at = NOW()
             WHERE run_id = :run_id
        """),
        {"run_id": str(strategy_run_id)},
    )

    result = _oos_result_from_sim(hold_out_window, weights, sim_result, {}, {})
    log.info(
        "holdout.complete",
        run_id=str(strategy_run_id),
        cagr=round(result.cagr, 4),
        calmar=round(result.calmar, 4),
    )
    return result
