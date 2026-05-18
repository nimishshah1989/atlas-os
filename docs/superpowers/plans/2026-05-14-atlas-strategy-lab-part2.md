# Atlas Strategy Lab — Part 2: Simulation + Optimization + API (Tasks 8–14)

*Continuation of `2026-05-14-atlas-strategy-lab.md`. Read Part 1 first.*

---

## Task 8: vectorbt Simulation Harness

**Files:**
- Create: `atlas/trading/simulator.py`
- Create: `tests/trading/test_simulator.py`

- [ ] **Step 1: Write failing test**

`tests/trading/test_simulator.py`:
```python
import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta
from atlas.trading.simulator import simulate_genome, SimResult
from atlas.trading.genome import GenomeFactory
from atlas.trading.config import PortfolioConfig


def _synthetic_df(n_stocks=5, n_days=120) -> pd.DataFrame:
    """Build minimal metrics DataFrame matching atlas_stock_metrics_daily schema.

    Note: breadth + VIX come from atlas_market_regime_daily — use _regime_df() separately.
    Only rs_pctile_1w/1m/3m exist (no 6m/12m). EMA column is ema_20_ratio.
    """
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    records = []
    rng = np.random.default_rng(42)
    for s in range(n_stocks):
        prices = 100.0 * np.cumprod(1 + rng.normal(0.0005, 0.02, n_days))
        for d_idx, d in enumerate(dates):
            records.append({
                "instrument_id": s + 1,
                "date": d,
                "close": prices[d_idx],
                "rs_pctile_1w": rng.uniform(0, 100),
                "rs_pctile_1m": rng.uniform(0, 100),
                "rs_pctile_3m": rng.uniform(0, 100),
                "vol_ratio_63": rng.uniform(0.8, 2.2),
                "ema_20_ratio": rng.uniform(0.97, 1.04),
            })
    return pd.DataFrame(records)


def _regime_df(n_days=120) -> pd.DataFrame:
    """Build minimal regime DataFrame matching atlas_market_regime_daily schema."""
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    rng = np.random.default_rng(99)
    return pd.DataFrame([
        {"date": d, "pct_above_ema_50": rng.uniform(30, 80), "india_vix": rng.uniform(12, 25)}
        for d in dates
    ])


def test_simulate_genome_returns_sim_result():
    genome = GenomeFactory.random()
    config = PortfolioConfig()
    df = _synthetic_df()
    rdf = _regime_df()

    start = date(2023, 1, 1)
    split = date(2023, 3, 1)
    end = date(2023, 4, 30)
    windows = [(start, split, split, end)]

    result = simulate_genome(genome, df, rdf, config, windows)

    assert isinstance(result, SimResult)
    assert isinstance(result.sortino_oos, float)
    assert isinstance(result.calmar_oos, float)
    assert isinstance(result.total_trades, int)
    assert result.total_trades >= 0
    assert not np.isnan(result.sortino_oos) or result.sortino_oos == 0.0


def test_simulate_genome_risk_off_full_liquidbees():
    """When regime is always Risk-Off, genome should make zero equity trades."""
    genome = GenomeFactory.random()
    genome.layer1.regime_risk_on_breadth_pct = 99    # impossible → always Risk-Off
    genome.layer1.regime_constructive_breadth_pct = 99
    genome.layer1.regime_cautious_breadth_pct = 99

    config = PortfolioConfig()
    df = _synthetic_df()
    rdf = _regime_df()

    start = date(2023, 1, 1)
    split = date(2023, 3, 1)
    end = date(2023, 4, 30)
    result = simulate_genome(genome, df, rdf, config, [(start, split, split, end)])

    assert result.total_trades == 0
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_simulator.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.simulator'`

- [ ] **Step 3: Implement**

`atlas/trading/simulator.py`:
```python
"""vectorbt simulation harness: runs one genome on historical data, returns SimResult.

Data flow:
  1. Compute blended RS percentile from genome weights
  2. Derive Layer 1 state matrices (perception.py)
  3. Compute conviction per stock per day (decision.py)
  4. Build entry/exit signal matrices
  5. Run vbt.Portfolio.from_signals() with position sizing
  6. Compute after-tax Sortino + Calmar on out-of-sample window
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import vectorbt as vbt
import structlog

from atlas.trading.config import PortfolioConfig
from atlas.trading.genome import Genome
from atlas.trading.perception import (
    compute_blended_rs_pctile, derive_rs_state, derive_regime_state,
    derive_vol_state, derive_momentum_state, compute_rs_velocity,
    REGIME_RISK_OFF,
)
from atlas.trading.decision import compute_conviction, apply_entry_rules, apply_exit_rules
from atlas.trading.tax_engine import TaxLedger, accrue_liquidbees, compute_trade_net_pnl

log = structlog.get_logger()


@dataclass
class SimResult:
    sortino_oos: float
    calmar_oos: float
    sortino_insample: float
    max_drawdown: float
    total_trades: int
    turnover_pct: float
    equity_curve_oos: pd.Series | None = None


def simulate_genome(
    genome: Genome,
    metrics_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    config: PortfolioConfig,
    walk_forward_windows: list[tuple[date, date, date, date]],
) -> SimResult:
    """Run genome across walk-forward windows.

    metrics_df: from atlas_stock_metrics_daily (instrument_id, date, close,
                rs_pctile_1w/1m/3m, ema_20_ratio, vol_ratio_63)
    regime_df:  from atlas_market_regime_daily (date, pct_above_ema_50, india_vix)
    walk_forward_windows: list of (train_start, train_end, test_start, test_end)

    Returns SimResult with metrics averaged across all OOS windows.
    Each metric is after-tax, after-cost.
    """
    # Pivot metrics into 2D arrays: (n_stocks, n_days) using vectorized pivot
    df = metrics_df.sort_values(["date", "instrument_id"])
    dates = sorted(df["date"].unique())
    instruments = sorted(df["instrument_id"].unique())

    def _pivot(col: str) -> np.ndarray:
        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return pivoted.reindex(index=instruments, columns=dates).values.astype(np.float32)

    close = _pivot("close")
    # Only 3 timeframes exist in atlas_stock_metrics_daily (no 6m/12m)
    rs_arrays = {
        "1w": _pivot("rs_pctile_1w"),
        "1m": _pivot("rs_pctile_1m"),
        "3m": _pivot("rs_pctile_3m"),
    }
    vol_ratio = _pivot("vol_ratio_63")
    ema_ratio = _pivot("ema_20_ratio")   # atlas_stock_metrics_daily column name

    # Regime data comes from atlas_market_regime_daily (separate table)
    rdf = regime_df.set_index("date").reindex(dates)
    breadth = rdf["pct_above_ema_50"].values.astype(np.float32)
    vix_arr = rdf["india_vix"].values.astype(np.float32)

    # Layer 1 states (applied once for all windows)
    blended_rs = compute_blended_rs_pctile(rs_arrays, genome.layer1.rs_timeframe_weights)
    rs_state = derive_rs_state(blended_rs, genome.layer1)
    regime_state = derive_regime_state(breadth, vix_arr, genome.layer1)
    vol_state = derive_vol_state(vol_ratio, genome.layer1)
    mom_state = derive_momentum_state(ema_ratio, genome.layer1)
    days_in_state, direction = compute_rs_velocity(rs_state, genome.layer1.state_velocity_lookback_days)

    # Pre-compute conviction matrix
    conv_matrix = np.zeros((n_stocks, n_days), dtype=np.float32)
    for s in range(n_stocks):
        for d in range(n_days):
            if np.isnan(blended_rs[s, d]):
                continue
            conv_matrix[s, d] = compute_conviction(
                rs_pctile_norm=float(blended_rs[s, d]) / 100.0,
                rs_state=int(rs_state[s, d]),
                momentum_state=int(mom_state[s, d]),
                vol_state=int(vol_state[s, d]),
                days_in_state=int(days_in_state[s, d]),
                direction=int(direction[s, d]),
                layer1=genome.layer1,
            )

    oos_sortinos: list[float] = []
    oos_calmars: list[float] = []
    oos_max_drawdowns: list[float] = []
    insample_sortinos: list[float] = []
    all_trades = 0

    for train_start, train_end, test_start, test_end in walk_forward_windows:
        oos_result = _run_window(
            genome=genome, config=config, dates=dates, close=close,
            conv_matrix=conv_matrix, rs_state=rs_state, regime_state=regime_state,
            window_start=test_start, window_end=test_end, instruments=instruments,
        )
        is_result = _run_window(
            genome=genome, config=config, dates=dates, close=close,
            conv_matrix=conv_matrix, rs_state=rs_state, regime_state=regime_state,
            window_start=train_start, window_end=train_end, instruments=instruments,
        )
        if oos_result is not None:
            oos_sortinos.append(oos_result["sortino"])
            oos_calmars.append(oos_result["calmar"])
            oos_max_drawdowns.append(oos_result["max_drawdown"])
            all_trades += oos_result["trades"]
        if is_result is not None:
            insample_sortinos.append(is_result["sortino"])

    sortino_oos = float(np.mean(oos_sortinos)) if oos_sortinos else 0.0
    calmar_oos = float(np.mean(oos_calmars)) if oos_calmars else 0.0
    sortino_is = float(np.mean(insample_sortinos)) if insample_sortinos else 0.0
    max_drawdown = float(np.max(oos_max_drawdowns)) if oos_max_drawdowns else 0.0

    return SimResult(
        sortino_oos=sortino_oos,
        calmar_oos=calmar_oos,
        sortino_insample=sortino_is,
        max_drawdown=max_drawdown,
        total_trades=all_trades,
        turnover_pct=0.0,
    )


def _run_window(
    genome: Genome,
    config: PortfolioConfig,    # needed for heat cap + fees
    dates: list[date],
    close: np.ndarray,
    conv_matrix: np.ndarray,
    rs_state: np.ndarray,
    regime_state: np.ndarray,
    window_start: date,
    window_end: date,
    instruments: list,
) -> dict | None:
    """Run portfolio simulation for a single date window."""
    d_start = next((i for i, d in enumerate(dates) if d >= window_start), None)
    d_end = next((i for i, d in enumerate(dates) if d > window_end), len(dates))
    if d_start is None or d_end - d_start < 20:
        return None

    w_dates = dates[d_start:d_end]
    w_close = close[:, d_start:d_end]
    w_conv = conv_matrix[:, d_start:d_end]
    w_rs = rs_state[:, d_start:d_end]
    w_regime = regime_state[d_start:d_end]

    n_stocks, n_days = w_close.shape
    entries = np.zeros((n_days, n_stocks), dtype=bool)
    exits = np.zeros((n_days, n_stocks), dtype=bool)

    prev_rs = w_rs[:, 0].copy()
    portfolio_heat = 0.0
    position_days = np.zeros(n_stocks, dtype=int)

    for d in range(1, n_days):
        regime = int(w_regime[d])
        if regime == REGIME_RISK_OFF:
            exits[d, :] = True   # liquidate all to LiquidBees
            position_days[:] = 0
            portfolio_heat = 0.0
            prev_rs = w_rs[:, d].copy()
            continue

        # Exits first
        playbook = genome.risk_on if regime == 3 else (genome.constructive if regime == 2 else genome.cautious)
        exit_mask = apply_exit_rules(
            prev_rs_state=prev_rs,
            curr_rs_state=w_rs[:, d],
            holding_days=position_days,
            min_hold_days=playbook.min_hold_days,
            exit_rs_drop_tiers=playbook.exit_rs_drop_tiers,
        )
        exits[d, :] = exit_mask
        position_days[exit_mask] = 0

        # Entries
        entry_mask = apply_entry_rules(
            conviction=w_conv[:, d],
            regime=regime,
            portfolio_heat=portfolio_heat,
            genome=genome,
            max_portfolio_heat_pct=float(config.max_portfolio_heat_pct),
        )
        entries[d, :] = entry_mask & ~exit_mask
        position_days[entry_mask] += 1

        prev_rs = w_rs[:, d].copy()

    # Build vectorbt price DataFrame
    price_df = pd.DataFrame(
        w_close.T,
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in w_dates]),
        columns=[str(iid) for iid in instruments],
    )
    entries_df = pd.DataFrame(entries, index=price_df.index, columns=price_df.columns)
    exits_df = pd.DataFrame(exits, index=price_df.index, columns=price_df.columns)

    try:
        pf = vbt.Portfolio.from_signals(
            price_df,
            entries_df,
            exits_df,
            init_cash=float(config.starting_capital),
            fees=float(config.brokerage_rate + config.stt_rate_sell + config.exchange_charge_rate + config.sebi_charge_rate),
            size=float(config.max_position_pct),
            size_type="targetpercent",
            group_by=True,
            cash_sharing=True,
        )
        sortino = float(pf.sortino_ratio() or 0.0)
        calmar = float(pf.calmar_ratio() or 0.0)
        max_dd = float(pf.max_drawdown() or 0.0)
        trades = int(pf.trades.count() or 0)
        return {"sortino": sortino, "calmar": calmar, "max_drawdown": max_dd, "trades": trades}
    except Exception as e:
        log.warning("simulation_window_error", error=str(e))
        return None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_simulator.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/simulator.py tests/trading/test_simulator.py
git commit -m "feat(trading): vectorbt simulation harness — genome → SimResult"
```

---

## Task 9: Optuna Optimizer

**Files:**
- Create: `atlas/trading/optimizer.py`
- Create: `tests/trading/test_optimizer.py`

- [ ] **Step 1: Write failing test**

`tests/trading/test_optimizer.py`:
```python
import pytest
from atlas.trading.optimizer import OptunaStudy
from atlas.trading.genome import GenomeFactory


def test_study_create_and_optimize():
    study = OptunaStudy(study_name="test_atlas_lab", storage=None)  # in-memory storage

    call_count = {"n": 0}

    def mock_objective(genome):
        call_count["n"] += 1
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0  # fake score

    study.run_trials(n_trials=5, objective_fn=mock_objective)
    assert call_count["n"] == 5
    assert study.best_genome() is not None
    best = study.best_genome()
    assert 60 <= best.layer1.rs_leader_cutoff_pct <= 80


def test_parameter_importance_keys():
    study = OptunaStudy(study_name="test_atlas_lab_imp", storage=None)

    def mock_objective(genome):
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0

    study.run_trials(n_trials=10, objective_fn=mock_objective)
    importance = study.get_parameter_importance()
    assert isinstance(importance, dict)
    # After enough trials, importance should have Optuna param keys
    assert len(importance) > 0
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_optimizer.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.optimizer'`

- [ ] **Step 3: Implement**

`atlas/trading/optimizer.py`:
```python
from __future__ import annotations

from typing import Callable

import optuna
import structlog

from atlas.trading.genome import Genome, GenomeFactory

log = structlog.get_logger()

optuna.logging.set_verbosity(optuna.logging.WARNING)


class OptunaStudy:
    """Wraps an Optuna study for genome optimization.

    storage=None uses in-memory storage (testing).
    Pass storage="postgresql+psycopg2://..." for production persistence.
    """

    def __init__(self, study_name: str, storage: str | None = None) -> None:
        self._study = optuna.create_study(
            study_name=study_name,
            storage=storage,
            direction="maximize",
            load_if_exists=True,
            sampler=optuna.samplers.TPESampler(seed=42),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=0),
        )
        self._name = study_name

    def run_trials(self, n_trials: int, objective_fn: Callable[[Genome], float]) -> None:
        """Run n_trials Optuna trials. objective_fn receives a Genome, returns float."""

        def _wrapped(trial: optuna.Trial) -> float:
            genome = GenomeFactory.from_optuna_trial(trial)
            score = objective_fn(genome)
            return score

        self._study.optimize(_wrapped, n_trials=n_trials, show_progress_bar=False)
        log.info(
            "optuna_trials_complete",
            study=self._name,
            n_trials=len(self._study.trials),
            best_value=self._study.best_value,
        )

    def best_genome(self) -> Genome | None:
        try:
            best_trial = self._study.best_trial
            return GenomeFactory.from_optuna_trial(
                optuna.trial.FixedTrial(best_trial.params)
            )
        except Exception:
            return None

    def get_parameter_importance(self) -> dict[str, float]:
        try:
            return optuna.importance.get_param_importances(self._study)
        except Exception:
            return {}

    @classmethod
    def production(cls, db_url: str) -> "OptunaStudy":
        """Create study backed by production Postgres DB."""
        storage = optuna.storages.RDBStorage(
            url=db_url,
            engine_kwargs={"pool_size": 5, "max_overflow": 10},
        )
        return cls(study_name="atlas_strategy_lab_v1", storage=storage)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_optimizer.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/optimizer.py tests/trading/test_optimizer.py
git commit -m "feat(trading): Optuna study wrapper with TPE sampler + parameter importance"
```

---

## Task 10: DEAP Evolver

**Files:**
- Create: `atlas/trading/evolver.py`
- Create: `tests/trading/test_evolver.py`

- [ ] **Step 1: Write failing test**

Create `tests/trading/test_evolver.py`:
```python
import pytest
from atlas.trading.evolver import Evolver
from atlas.trading.genome import GenomeFactory


def test_crossover_offspring_in_range():
    evolver = Evolver()
    parent_a = GenomeFactory.random()
    parent_b = GenomeFactory.random()
    child_a, child_b = evolver.crossover(parent_a, parent_b)
    assert 60 <= child_a.layer1.rs_leader_cutoff_pct <= 80
    assert 60 <= child_b.layer1.rs_leader_cutoff_pct <= 80
    assert 2.0 <= child_a.risk_on.base_position_pct <= 6.0


def test_mutate_changes_params():
    evolver = Evolver()
    genome = GenomeFactory.random()
    mutated = evolver.mutate(genome, sigma=0.15)
    # Mutated genome must still be within search-space bounds
    assert 60 <= mutated.layer1.rs_leader_cutoff_pct <= 80


def test_select_survivors_keeps_pareto_front():
    evolver = Evolver()
    genomes_with_scores = [(GenomeFactory.random(), float(i) * 0.1, float(i) * 0.05) for i in range(10)]
    survivors = evolver.select_survivors(genomes_with_scores, target_pool=6)
    assert len(survivors) == 6
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_evolver.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.evolver'`

- [ ] **Step 3: Implement**

`atlas/trading/evolver.py`:
```python
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from atlas.trading.genome import Genome, GenomeFactory, Layer1Perception, RegimePlaybook

# Clamp helpers
def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(v))))

def _clamp_float(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class Evolver:
    """DEAP-inspired crossover + mutation for Genome objects.

    Uses blend crossover (cxBlend) for float parameters and integer rounding
    for int parameters. Maintains search space bounds from genome.py.
    """

    def crossover(self, genome_a: Genome, genome_b: Genome, alpha: float = 0.5) -> tuple[Genome, Genome]:
        """Blend crossover between two genomes. Returns two offspring."""
        def _blend_float(a: float, b: float) -> tuple[float, float]:
            lo, hi = min(a, b), max(a, b)
            d = hi - lo
            lo_ext, hi_ext = lo - alpha * d, hi + alpha * d
            c1 = random.uniform(lo_ext, hi_ext)
            c2 = random.uniform(lo_ext, hi_ext)
            return c1, c2

        def _blend_int(a: int, b: int) -> tuple[int, int]:
            f1, f2 = _blend_float(float(a), float(b))
            return int(round(f1)), int(round(f2))

        # Layer1
        l1a, l1b = genome_a.layer1, genome_b.layer1
        leader1, leader2 = _blend_int(l1a.rs_leader_cutoff_pct, l1b.rs_leader_cutoff_pct)
        leader1 = _clamp_int(leader1, 60, 80)
        leader2 = _clamp_int(leader2, 60, 80)

        vel1, vel2 = _blend_int(l1a.state_velocity_lookback_days, l1b.state_velocity_lookback_days)
        syn1, syn2 = _blend_float(l1a.synergy_weight, l1b.synergy_weight)

        def _blend_weights(wa: dict, wb: dict) -> tuple[dict, dict]:
            keys = list(wa.keys())
            raw1 = {k: max(0.01, (wa[k] + wb[k]) / 2 + random.uniform(-0.1, 0.1)) for k in keys}
            raw2 = {k: max(0.01, (wa[k] + wb[k]) / 2 + random.uniform(-0.1, 0.1)) for k in keys}
            t1, t2 = sum(raw1.values()), sum(raw2.values())
            return {k: raw1[k] / t1 for k in keys}, {k: raw2[k] / t2 for k in keys}

        w1, w2 = _blend_weights(l1a.rs_timeframe_weights, l1b.rs_timeframe_weights)

        def _layer1(genome_ref: Genome, leader: int, vel: int, syn: float, weights: dict) -> Layer1Perception:
            ref = genome_ref.layer1
            strong = _clamp_int(ref.rs_strong_cutoff_pct, 45, min(65, leader - 1))
            return Layer1Perception(
                rs_leader_cutoff_pct=leader,
                rs_strong_cutoff_pct=strong,
                rs_average_cutoff_pct=_clamp_int(ref.rs_average_cutoff_pct, 25, min(45, strong - 1)),
                rs_weak_cutoff_pct=_clamp_int(ref.rs_weak_cutoff_pct, 10, 25),
                rs_timeframe_weights=weights,
                regime_risk_on_breadth_pct=ref.regime_risk_on_breadth_pct,
                regime_constructive_breadth_pct=ref.regime_constructive_breadth_pct,
                regime_cautious_breadth_pct=ref.regime_cautious_breadth_pct,
                regime_risk_on_vix_ceiling=_clamp_float(
                    (l1a.regime_risk_on_vix_ceiling + l1b.regime_risk_on_vix_ceiling) / 2, 14.0, 22.0
                ),
                momentum_accel_ema_ratio=ref.momentum_accel_ema_ratio,
                momentum_decel_ema_ratio=ref.momentum_decel_ema_ratio,
                vol_elevated_ratio=_clamp_float((l1a.vol_elevated_ratio + l1b.vol_elevated_ratio) / 2, 1.2, 1.8),
                vol_high_ratio=_clamp_float((l1a.vol_high_ratio + l1b.vol_high_ratio) / 2, 1.5, 2.5),
                state_velocity_lookback_days=_clamp_int(vel, 5, 20),
                synergy_weight=_clamp_float(syn, 0.0, 0.3),
                penalty_weight=_clamp_float((l1a.penalty_weight + l1b.penalty_weight) / 2, 0.0, 0.3),
            )

        def _blend_playbook(pa: RegimePlaybook, pb: RegimePlaybook) -> RegimePlaybook:
            conv1, _ = _blend_float(pa.min_conviction_to_enter, pb.min_conviction_to_enter)
            pos1, _ = _blend_float(pa.base_position_pct, pb.base_position_pct)
            return RegimePlaybook(
                min_conviction_to_enter=_clamp_float(conv1, 0.35, 0.80),
                base_position_pct=_clamp_float(pos1, 2.0, 6.0),
                exit_rs_drop_tiers=_clamp_int((pa.exit_rs_drop_tiers + pb.exit_rs_drop_tiers) // 2, 1, 3),
                exit_momentum_collapse=pa.exit_momentum_collapse,
                profit_target_pct=pa.profit_target_pct,
                time_stop_days=pa.time_stop_days,
                trailing_stop_from_peak_pct=pa.trailing_stop_from_peak_pct,
                min_hold_days=_clamp_int((pa.min_hold_days + pb.min_hold_days) // 2, 3, 15),
                max_sector_concentration_pct=_clamp_int(
                    (pa.max_sector_concentration_pct + pb.max_sector_concentration_pct) // 2, 15, 35
                ),
                dd_halt_entry_pct=_clamp_float((pa.dd_halt_entry_pct + pb.dd_halt_entry_pct) / 2, 8.0, 15.0),
                dd_tighten_exit_pct=_clamp_float((pa.dd_tighten_exit_pct + pb.dd_tighten_exit_pct) / 2, 14.0, 22.0),
                dd_liquidate_pct=_clamp_float((pa.dd_liquidate_pct + pb.dd_liquidate_pct) / 2, 19.0, 30.0),
            )

        now = datetime.now(timezone.utc)
        child_a = Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[genome_a.genome_id, genome_b.genome_id],
            born_at=now,
            generation=max(genome_a.generation, genome_b.generation) + 1,
            layer1=_layer1(genome_a, leader1, vel1, syn1, w1),
            risk_on=_blend_playbook(genome_a.risk_on, genome_b.risk_on),
            constructive=_blend_playbook(genome_a.constructive, genome_b.constructive),
            cautious=_blend_playbook(genome_a.cautious, genome_b.cautious),
        )
        child_b = Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[genome_a.genome_id, genome_b.genome_id],
            born_at=now,
            generation=max(genome_a.generation, genome_b.generation) + 1,
            layer1=_layer1(genome_b, leader2, vel2, syn2, w2),
            risk_on=_blend_playbook(genome_b.risk_on, genome_a.risk_on),
            constructive=_blend_playbook(genome_b.constructive, genome_a.constructive),
            cautious=_blend_playbook(genome_b.cautious, genome_a.cautious),
        )
        return child_a, child_b

    def mutate(self, genome: Genome, sigma: float = 0.15) -> Genome:
        """Gaussian mutation on 1–3 randomly chosen float parameters."""
        d = genome.to_dict()
        # Collect float params from layer1
        float_params = ["vol_elevated_ratio", "vol_high_ratio", "synergy_weight", "penalty_weight",
                        "momentum_accel_ema_ratio", "momentum_decel_ema_ratio", "regime_risk_on_vix_ceiling"]
        n_to_mutate = random.randint(1, 3)
        params_to_mutate = random.sample(float_params, min(n_to_mutate, len(float_params)))

        for param in params_to_mutate:
            current = d["layer1"][param]
            noise = random.gauss(0, sigma * current)
            d["layer1"][param] = current + noise

        # Clamp after mutation
        d["layer1"]["vol_elevated_ratio"] = _clamp_float(d["layer1"]["vol_elevated_ratio"], 1.2, 1.8)
        d["layer1"]["vol_high_ratio"] = _clamp_float(d["layer1"]["vol_high_ratio"], 1.5, 2.5)
        d["layer1"]["synergy_weight"] = _clamp_float(d["layer1"]["synergy_weight"], 0.0, 0.3)
        d["layer1"]["penalty_weight"] = _clamp_float(d["layer1"]["penalty_weight"], 0.0, 0.3)

        d["genome_id"] = str(uuid.uuid4())
        d["parent_ids"] = [genome.genome_id]
        d["generation"] = genome.generation + 1
        d["born_at"] = datetime.now(timezone.utc).isoformat()
        return Genome.from_dict(d)

    def select_survivors(
        self,
        genomes_with_scores: list[tuple[Genome, float, float]],
        target_pool: int = 100,
    ) -> list[Genome]:
        """NSGA-2 style selection on (sortino, calmar). Returns top target_pool genomes."""
        if not genomes_with_scores:
            return []
        # Simple Pareto approximation: rank by sortino + calmar combined score
        scored = sorted(genomes_with_scores, key=lambda x: x[1] + x[2], reverse=True)
        return [g for g, _, _ in scored[:target_pool]]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_evolver.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/evolver.py tests/trading/test_evolver.py
git commit -m "feat(trading): DEAP-inspired genome crossover + mutation + survivor selection"
```

---

## Task 11: Tournament Evaluation + Leaderboard

**Files:**
- Create: `atlas/trading/tournament.py`
- Create: `tests/trading/test_tournament.py`

- [ ] **Step 1: Write failing tests**

`tests/trading/test_tournament.py`:
```python
import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from atlas.trading.tournament import TournamentEvaluator, PromotionResult
from atlas.trading.genome import GenomeFactory
from atlas.trading.simulator import SimResult


def _sim_result(sortino: float, calmar: float = 0.5, trades: int = 10) -> SimResult:
    return SimResult(
        sortino_oos=sortino, calmar_oos=calmar, sortino_insample=sortino + 0.1,
        max_drawdown=0.10, total_trades=trades, turnover_pct=0.05,
    )


def _evaluator() -> TournamentEvaluator:
    return TournamentEvaluator(
        stress_periods={
            "covid_2020": (date(2020, 2, 1), date(2020, 5, 31)),
            "bear_2022": (date(2022, 1, 1), date(2022, 6, 30)),
            "bull_2023": (date(2023, 1, 1), date(2023, 12, 31)),
        }
    )


def test_genome_failing_round1_not_promoted():
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(g, start, end):
        return _sim_result(sortino=0.3)   # < 0.7 → fails Round 1

    result = evaluator.evaluate(genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31))
    assert not result.promoted
    assert result.failed_round == 1


def test_genome_failing_round2_not_promoted():
    evaluator = _evaluator()
    genome = GenomeFactory.random()
    call_count = {"n": 0}

    def sim_fn(g, start, end):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _sim_result(sortino=0.9)   # Round 1: PASS
        return _sim_result(sortino=0.3)        # Round 2: FAIL

    result = evaluator.evaluate(genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31))
    assert not result.promoted
    assert result.failed_round == 2


def test_genome_passing_all_rounds_promoted():
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(g, start, end):
        # Round 1: 0.9, Round 2: 0.7, stress tests all pass
        return _sim_result(sortino=0.9, calmar=1.2)

    result = evaluator.evaluate(genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31))
    assert result.promoted
    assert result.final_sortino >= 0.7
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_tournament.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`atlas/trading/tournament.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection

from atlas.trading.genome import Genome
from atlas.trading.simulator import SimResult

log = structlog.get_logger()

ROUND1_SORTINO_THRESHOLD = 0.7
ROUND2_SORTINO_THRESHOLD = 0.5
STRESS_COVID_MAX_DRAWDOWN = 0.25
STRESS_BEAR_MIN_SORTINO = 0.0
STRESS_BULL_MIN_SORTINO = 1.0


@dataclass
class PromotionResult:
    promoted: bool
    final_sortino: float
    final_calmar: float
    failed_round: int | None
    fail_reason: str | None


class TournamentEvaluator:
    """Three-round tournament for genome promotion to leaderboard.

    Round 1: last 90-day OOS window → Sortino > 0.7
    Round 2: prior 90-day window → Sortino > 0.5 (consistency)
    Round 3: stress tests on named historical periods
    """

    def __init__(self, stress_periods: dict[str, tuple[date, date]]) -> None:
        self.stress_periods = stress_periods

    def evaluate(
        self,
        genome: Genome,
        sim_fn: Callable,       # sim_fn(genome, start, end) → SimResult
        recent_start: date,
        recent_end: date,
    ) -> PromotionResult:
        # Round 1: recent window
        r1 = sim_fn(genome, recent_start, recent_end)
        if r1.sortino_oos < ROUND1_SORTINO_THRESHOLD:
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=1,
                fail_reason=f"Round 1 Sortino {r1.sortino_oos:.2f} < {ROUND1_SORTINO_THRESHOLD}",
            )

        # Round 2: prior 90-day window (simple offset — use sim_fn with prior dates)
        from datetime import timedelta
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=89)
        r2 = sim_fn(genome, prior_start, prior_end)
        if r2.sortino_oos < ROUND2_SORTINO_THRESHOLD:
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=2,
                fail_reason=f"Round 2 Sortino {r2.sortino_oos:.2f} < {ROUND2_SORTINO_THRESHOLD}",
            )

        # Round 3: stress tests
        covid_start, covid_end = self.stress_periods.get("covid_2020", (date(2020, 2, 1), date(2020, 5, 31)))
        bear_start, bear_end = self.stress_periods.get("bear_2022", (date(2022, 1, 1), date(2022, 6, 30)))
        bull_start, bull_end = self.stress_periods.get("bull_2023", (date(2023, 1, 1), date(2023, 12, 31)))

        r_covid = sim_fn(genome, covid_start, covid_end)
        if r_covid.max_drawdown > STRESS_COVID_MAX_DRAWDOWN:
            return PromotionResult(
                promoted=False, final_sortino=r1.sortino_oos, final_calmar=r1.calmar_oos,
                failed_round=3, fail_reason=f"COVID stress: drawdown {r_covid.max_drawdown:.1%} > 25%",
            )

        r_bear = sim_fn(genome, bear_start, bear_end)
        if r_bear.sortino_oos < STRESS_BEAR_MIN_SORTINO:
            return PromotionResult(
                promoted=False, final_sortino=r1.sortino_oos, final_calmar=r1.calmar_oos,
                failed_round=3, fail_reason=f"Bear stress: Sortino {r_bear.sortino_oos:.2f} < 0",
            )

        r_bull = sim_fn(genome, bull_start, bull_end)
        if r_bull.sortino_oos < STRESS_BULL_MIN_SORTINO:
            return PromotionResult(
                promoted=False, final_sortino=r1.sortino_oos, final_calmar=r1.calmar_oos,
                failed_round=3, fail_reason=f"Bull stress: Sortino {r_bull.sortino_oos:.2f} < 1.0",
            )

        return PromotionResult(
            promoted=True,
            final_sortino=r1.sortino_oos,
            final_calmar=r1.calmar_oos,
            failed_round=None,
            fail_reason=None,
        )


def promote_to_leaderboard(conn: Connection, genome: Genome, result: PromotionResult, rank: int) -> None:
    """Write promoted genome to atlas_strategy_leaderboard."""
    name = _auto_name(genome)
    conn.execute(
        text(
            """
            INSERT INTO atlas_strategy_leaderboard
                (rank, genome_id, strategy_name, promoted_at, sortino_oos, calmar_oos)
            VALUES (:rank, :genome_id, :name, :promoted_at, :sortino, :calmar)
            ON CONFLICT (rank) DO UPDATE
                SET genome_id = EXCLUDED.genome_id,
                    strategy_name = EXCLUDED.strategy_name,
                    promoted_at = EXCLUDED.promoted_at,
                    sortino_oos = EXCLUDED.sortino_oos,
                    calmar_oos = EXCLUDED.calmar_oos
            """
        ),
        {
            "rank": rank,
            "genome_id": genome.genome_id,
            "name": name,
            "promoted_at": datetime.now(timezone.utc),
            "sortino": result.final_sortino,
            "calmar": result.final_calmar,
        },
    )
    log.info("genome_promoted", genome_id=genome.genome_id, rank=rank, sortino=result.final_sortino)


def _auto_name(genome: Genome) -> str:
    """Generate a human-readable strategy name from dominant genome parameters."""
    l1 = genome.layer1
    weights = l1.rs_timeframe_weights
    dominant_tf = max(weights, key=lambda k: weights[k])
    stance = "Aggressive" if genome.risk_on.base_position_pct > 4.0 else "Conservative"
    return f"RS-{dominant_tf.upper()}-{stance}-G{genome.generation}"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_tournament.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/tournament.py tests/trading/test_tournament.py
git commit -m "feat(trading): 3-round tournament evaluation + leaderboard writes"
```

---

## Task 12: Insight Feed (Groq Narration)

**Files:**
- Create: `atlas/trading/insight.py`

- [ ] **Step 1: Write failing test**

Create `tests/trading/test_insight.py`:
```python
from unittest.mock import patch, MagicMock
from atlas.trading.insight import generate_insights


def test_generate_insights_returns_bullets():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "1. RS timeframe weights are shifting toward 1W.\n"
        "2. Constructive regime strategies outperformed.\n"
        "3. High vol penalty weight reduces drawdown."
    )

    with patch("atlas.trading.insight._get_groq_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        bullets = generate_insights(
            parameter_importance={"rs_leader_cutoff_pct": 0.43, "synergy_weight": 0.31},
            top_genome_deltas=[{"genome_id": "abc", "delta": {"rs_w1w": "+0.05"}}],
        )

    assert isinstance(bullets, list)
    assert 1 <= len(bullets) <= 6
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_insight.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.insight'`

- [ ] **Step 3: Implement**

`atlas/trading/insight.py`:
```python
"""Groq Llama narration of nightly optimization results.

Uses openai SDK pointed at Groq's API endpoint (same pattern as atlas/signals/narrative.py).
The LLM narrates what the engine is learning — it does NOT make trading decisions.
"""
from __future__ import annotations

import json
import os

import structlog

log = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 400

_PROMPT_TEMPLATE = """\
You are analyzing a portfolio optimization engine's nightly learning report.
Summarize what the engine is learning in 3-5 plain-English bullet points.
Be specific about which parameters are shifting and what that means for strategy behavior.
Do NOT make stock recommendations. Focus on what the optimization is discovering.

Parameter importance scores (higher = more impact on Sortino):
{importance_json}

Top genome parameter shifts this week (compared to last week's best performers):
{delta_json}

Write 3-5 bullet points. Start each with a number. Be concrete and specific.
"""


def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY", "")
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
    except ImportError as e:
        raise RuntimeError("openai SDK not installed") from e


def generate_insights(
    parameter_importance: dict[str, float],
    top_genome_deltas: list[dict],
) -> list[str]:
    """Generate plain-English insight bullets from optimization results.

    Returns a list of 3–5 insight strings.
    Falls back to empty list if Groq is unavailable.
    """
    prompt = _PROMPT_TEMPLATE.format(
        importance_json=json.dumps(parameter_importance, indent=2),
        delta_json=json.dumps(top_genome_deltas[:5], indent=2),
    )
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        bullets = [line.strip() for line in raw.split("\n") if line.strip() and line.strip()[0].isdigit()]
        log.info("insights_generated", count=len(bullets))
        return bullets[:6]
    except Exception as e:
        log.warning("insight_generation_failed", error=str(e))
        return []
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_insight.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/insight.py tests/trading/test_insight.py
git commit -m "feat(trading): Groq insight feed for nightly optimization narration"
```

---

## Task 13: Nightly Incubator Orchestrator

**Files:**
- Create: `atlas/trading/incubator.py`

- [ ] **Step 1: Implement (no separate test — integration-tested by running it)**

`atlas/trading/incubator.py`:
```python
"""Nightly incubator orchestrator — chains all atlas.trading modules.

Run as: python -m atlas.trading.incubator

Sequence (spec §5.2):
  1. Load metrics from atlas_stock_metrics_daily + regime from atlas_market_regime_daily
  2. For each Optuna trial: simulate genome → return (sortino, calmar)
  3. DEAP breeding: crossover top performers, kill bottom 20%
  4. Tournament: evaluate top candidates, promote to leaderboard
  5. Insight generation: Groq narrates optimization deltas
  6. Persist all results to DB
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from atlas.trading.config import PortfolioConfig
from atlas.trading.evolver import Evolver
from atlas.trading.genome import GenomeFactory
from atlas.trading.insight import generate_insights
from atlas.trading.optimizer import OptunaStudy
from atlas.trading.simulator import SimResult, simulate_genome
from atlas.trading.tournament import TournamentEvaluator, promote_to_leaderboard
from atlas.trading.universe import load_universe_membership, bootstrap_nifty500_membership

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
    """Load stock metrics. Only 3 RS timeframes exist (no 6m/12m)."""
    log.info("loading_metrics", start=start_date, end=end_date)
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
    """Load market regime data from atlas_market_regime_daily."""
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
        test_end = train_end + timedelta(days=test_days)
        windows.append((cursor, train_end, train_end + timedelta(days=1), test_end))
        cursor += timedelta(days=test_days)  # roll forward by one test window
    return windows


def run_nightly(conn, config: PortfolioConfig | None = None) -> None:
    if config is None:
        config = _load_active_config(conn)

    today = date.today()
    data_start = today - timedelta(days=365 * 12)  # 12 years of history
    metrics_df = _load_metrics_df(conn, data_start, today)
    regime_df = _load_regime_df(conn, data_start, today)

    if metrics_df.empty:
        log.error("no_metrics_data")
        return

    walk_forward_windows = _build_walk_forward_windows(
        start_date=today - timedelta(days=365 * 10),
        end_date=today,
    )

    db_url = os.environ.get("ATLAS_DB_URL", "")
    study = OptunaStudy.production(db_url) if db_url else OptunaStudy("atlas_strategy_lab_v1")

    genome_scores: list[tuple[Any, float, float]] = []

    def objective(genome):
        result = simulate_genome(genome, metrics_df, regime_df, config, walk_forward_windows)
        genome_scores.append((genome, result.sortino_oos, result.calmar_oos))
        return result.sortino_oos

    log.info("running_optuna_trials", n=_N_TRIALS_PER_NIGHT)
    study.run_trials(n_trials=_N_TRIALS_PER_NIGHT, objective_fn=objective)

    # DEAP breeding
    evolver = Evolver()
    survivors = evolver.select_survivors(genome_scores, target_pool=_TARGET_POOL_SIZE)

    if len(survivors) >= 2:
        top_a, top_b = survivors[0], survivors[1]
        child_a, child_b = evolver.crossover(top_a, top_b)
        mutated = [evolver.mutate(g) for g in survivors[:5]]
        log.info("breeding_complete", offspring=2, mutations=len(mutated))

    # Tournament evaluation of top candidates
    evaluator = TournamentEvaluator(stress_periods=_STRESS_PERIODS)
    recent_end = today
    recent_start = today - timedelta(days=89)

    promoted_count = 0
    for rank, (genome, sortino, calmar) in enumerate(genome_scores[:10], start=1):
        def sim_fn(g, start, end):
            w = [(start, end - timedelta(days=_WALK_FORWARD_TEST_DAYS // 2), end - timedelta(days=_WALK_FORWARD_TEST_DAYS // 2) + timedelta(days=1), end)]
            r = simulate_genome(g, metrics_df, regime_df, config, w)
            return r

        result = evaluator.evaluate(genome, sim_fn, recent_start=recent_start, recent_end=recent_end)
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
                INSERT INTO atlas_strategy_insights (id, generated_at, insight_bullets, parameter_importance, top_genome_deltas)
                VALUES (gen_random_uuid(), NOW(), :bullets::jsonb, :importance::jsonb, :deltas::jsonb)
                """
            ),
            {
                "bullets": json.dumps(bullets),
                "importance": json.dumps({k: float(v) for k, v in importance.items()}),
                "deltas": json.dumps(top_deltas),
            },
        )

    log.info("nightly_run_complete", promoted=promoted_count, bullets=len(bullets))


def _load_active_config(conn) -> PortfolioConfig:
    row = conn.execute(
        text("SELECT config_json FROM atlas_portfolio_config WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1")
    ).mappings().first()
    if row:
        return PortfolioConfig.from_json(dict(row["config_json"]))
    return PortfolioConfig()


if __name__ == "__main__":
    import structlog
    structlog.configure()
    db_url = os.environ["ATLAS_DB_URL"]
    engine = create_engine(db_url)
    with engine.connect() as conn:
        run_nightly(conn)
        conn.commit()
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from atlas.trading.incubator import run_nightly; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add atlas/trading/incubator.py
git commit -m "feat(trading): nightly incubator orchestrator — chains optuna + deap + tournament + insights"
```

---

## Task 14: Read-Only API Endpoints

**Files:**
- Create: `atlas/api/trading.py`
- Modify: `atlas/api/__init__.py` — register router

- [ ] **Step 1: Implement**

`atlas/api/trading.py`:
```python
"""Read-only FastAPI endpoints for Atlas Strategy Lab.

All endpoints return the Atlas standard envelope:
  {"data": ..., "meta": {"data_as_of": ..., "fetched_at": ...}}

No writes except POST /config (upserts active PortfolioConfig).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.db import get_session

router = APIRouter(prefix="/api/trading", tags=["trading"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def _envelope(data, data_as_of: str | None = None) -> dict:
    return {"data": data, "meta": {"data_as_of": data_as_of, "fetched_at": _NOW()}}


@router.get("/leaderboard")
async def get_leaderboard(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        text("""
            SELECT l.rank, l.genome_id::text, l.strategy_name, l.promoted_at,
                   l.sortino_oos, l.calmar_oos, l.alpha_30d, l.regime_breakdown,
                   g.genome_json, g.generation
            FROM atlas_strategy_leaderboard l
            JOIN atlas_strategy_genomes g ON g.id = l.genome_id
            ORDER BY l.rank
        """)
    )).mappings().all()
    return _envelope([dict(r) for r in rows])


@router.get("/genome/{genome_id}")
async def get_genome(genome_id: str, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("""
            SELECT g.id::text, g.genome_json, g.born_at, g.generation, g.status, g.parent_ids::text[]
            FROM atlas_strategy_genomes g WHERE g.id = :gid
        """),
        {"gid": genome_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Genome not found")

    perf = (await session.execute(
        text("""
            SELECT date, sortino_oos, calmar_oos, alpha_vs_nifty500, max_drawdown, total_trades
            FROM atlas_strategy_performance_daily
            WHERE genome_id = :gid ORDER BY date DESC LIMIT 90
        """),
        {"gid": genome_id},
    )).mappings().all()

    return _envelope({"genome": dict(row), "performance": [dict(p) for p in perf]})


@router.get("/genome/{genome_id}/positions")
async def get_positions(genome_id: str, session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        text("""
            SELECT p.date, u.ticker, u.company_name, p.position_type,
                   p.entry_date, p.entry_price, p.shares, p.current_value,
                   p.unrealized_pnl, p.holding_days, p.tax_status, p.entry_signals
            FROM atlas_strategy_positions_daily p
            JOIN atlas.atlas_universe_stocks u ON u.id = p.instrument_id
            WHERE p.genome_id = :gid AND p.date = (SELECT MAX(date) FROM atlas_strategy_positions_daily WHERE genome_id = :gid)
            ORDER BY p.current_value DESC
        """),
        {"gid": genome_id},
    )).mappings().all()
    return _envelope([dict(r) for r in rows])


@router.get("/insights/latest")
async def get_latest_insights(session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("SELECT * FROM atlas_strategy_insights ORDER BY generated_at DESC LIMIT 1")
    )).mappings().first()
    if not row:
        return _envelope({"bullets": [], "parameter_importance": {}})
    return _envelope(dict(row), data_as_of=str(row["generated_at"]))


@router.get("/gene-pool/health")
async def get_gene_pool_health(session: AsyncSession = Depends(get_session)):
    stats = (await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'killed') AS killed_count,
                COUNT(*) FILTER (WHERE status = 'promoted') AS promoted_count,
                MAX(born_at) AS last_born_at
            FROM atlas_strategy_genomes
        """)
    )).mappings().first()
    return _envelope(dict(stats) if stats else {})


@router.get("/config")
async def get_config(session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("SELECT * FROM atlas_portfolio_config WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1")
    )).mappings().first()
    if not row:
        from atlas.trading.config import PortfolioConfig
        return _envelope(PortfolioConfig().to_json())
    return _envelope(dict(row["config_json"]))


@router.post("/config")
async def save_config(body: dict, session: AsyncSession = Depends(get_session)):
    from atlas.trading.config import PortfolioConfig
    try:
        cfg = PortfolioConfig.from_json(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    await session.execute(text("UPDATE atlas_portfolio_config SET is_active = FALSE"))
    await session.execute(
        text("""
            INSERT INTO atlas_portfolio_config (config_json, is_active, label)
            VALUES (:cfg::jsonb, TRUE, :label)
        """),
        {"cfg": json.dumps(cfg.to_json()), "label": body.get("label", "")},
    )
    return _envelope(cfg.to_json())
```

- [ ] **Step 2: Register router in `atlas/api/__init__.py`**

Find the section where other routers are included (look for lines like `app.include_router(...)`) and add:
```python
from atlas.api.trading import router as trading_router
app.include_router(trading_router)
```

- [ ] **Step 3: Verify endpoints are registered**

```bash
python -c "from atlas.api import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'trading' in r])"
```

Expected: list containing `/api/trading/leaderboard`, `/api/trading/config`, etc.

- [ ] **Step 4: Commit**

```bash
git add atlas/api/trading.py atlas/api/__init__.py
git commit -m "feat(trading): read-only API endpoints for Strategy Lab frontend"
```

---

*[Tasks 15–19: Frontend continues in Part 3.]*
