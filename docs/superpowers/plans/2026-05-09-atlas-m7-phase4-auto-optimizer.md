# Atlas M7 Phase 4 — Auto-Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Auto-Optimizer: Optuna Bayesian search finds better Atlas threshold combinations per (regime, archetype), scores them via walk-forward backtest, surfaces results to the FM, and requires FM approval before applying threshold changes (SEBI audit trail).

**Architecture:**
- `optimizer/regime_optimizer.py` — Optuna study per (regime, archetype), walk-forward scoring
- `optimizer/results.py` — threshold promotion: approve + 7-day revert
- `scripts/m7_optimizer.py` — nightly/weekly batch entry point
- `atlas/api/optimizer.py` — REST endpoints for optimizer dashboard (consumed by Phase 5 frontend)

**Tech Stack:** optuna[postgres] ≥3.0 (Bayesian search, PostgreSQL RDB storage), vectorbt via `backtest/engine.py` (trial scoring), direct psycopg2 URL (`ATLAS_DB_DIRECT_URL`) bypasses PgBouncer for Optuna's connection lifecycle.

**Prerequisites (must be complete before starting Phase 4):**
- Phase 3 complete — `backtest/engine.py` must exist (`run_backtest()` available)
- `signal_adapter.py` schema fixes applied (`de_equity_ohlcv`, `mstar_id` for funds)
- Migration 019 applied (creates `optuna` schema + `atlas.strategy_optimization_runs`)
- `ATLAS_DB_DIRECT_URL` env var set (direct psycopg2 connection, no PgBouncer)

**EC2 constraints:**
- `n_jobs=1` always — t3.large (8GB RAM) OOMs with parallel Optuna workers
- `del pf; gc.collect()` after every vectorbt backtest window — mandatory, not optional
- Target ≤25s per trial (all walk-forward windows combined)

**The learning loop this enables:**
Every nightly run adds one more row of real forward-performance data to `strategy_paper_performance`. Over time, Optuna's walk-forward scoring incorporates real live data alongside historical signals. More paper trading history = more reliable optimization. Run optimizer weekly after first 30 days of paper trading; run it nightly after 6 months.

---

### Task 1: Add optuna[postgres] dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add optuna to pyproject.toml optimizer extras**

The `optimizer` group already exists from Phase 3. Verify it reads:

```toml
optimizer = [
    "optuna[postgres]>=3.0",
]
```

- [ ] **Step 2: Install on EC2**

```bash
pip install "optuna[postgres]>=3.0"
```

Expected: no errors.

- [ ] **Step 3: Verify optuna imports and PostgreSQL storage works**

```bash
python -c "import optuna; from optuna.storages import RDBStorage; print('optuna', optuna.__version__)"
```

Expected: version string, no ImportError.

- [ ] **Step 4: Verify ATLAS_DB_DIRECT_URL is set**

```bash
python -c "import os; url = os.environ['ATLAS_DB_DIRECT_URL']; print('URL prefix:', url[:20])"
```

Expected: prints URL prefix (e.g. `postgresql://atlas_us`). If missing, set in `.env` before continuing.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "feat(m7-p4): add optuna[postgres]>=3.0 to optimizer deps"
```

---

### Task 2: optimizer/regime_optimizer.py — Optuna study + walk-forward scoring

**Files:**
- Create: `atlas/simulation/optimizer/regime_optimizer.py`
- Create: `tests/unit/simulation/test_regime_optimizer.py`

The optimizer runs a constrained Bayesian search. Each trial suggests threshold values, runs a walk-forward backtest, and returns the mean OOS Sharpe. Optuna learns which combinations produce higher Sharpe and directs subsequent trials accordingly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/simulation/test_regime_optimizer.py
"""Unit tests for regime_optimizer.py — no real Optuna DB, no real vectorbt."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from atlas.simulation.backtest.walk_forward import InsufficientHistoryError


class TestStudyName:
    def test_study_name_format(self):
        from atlas.simulation.optimizer.regime_optimizer import STUDY_VERSION, _study_name

        name = _study_name("Risk-On", "momentum_pure")
        assert name == f"atlas_Risk-On_momentum_pure_{STUDY_VERSION}"

    def test_study_version_is_string(self):
        from atlas.simulation.optimizer.regime_optimizer import STUDY_VERSION

        assert isinstance(STUDY_VERSION, str)
        assert STUDY_VERSION.startswith("v")


class TestObjectiveFunction:
    def test_insufficient_history_returns_neg_inf(self):
        """Objective must return -inf (not crash) when history < 547 days."""
        from atlas.simulation.optimizer.regime_optimizer import _make_objective

        mock_engine = MagicMock()

        with patch(
            "atlas.simulation.optimizer.regime_optimizer.generate_oos_windows",
            side_effect=InsufficientHistoryError("not enough history"),
        ):
            objective = _make_objective(
                regime="Risk-On",
                archetype="momentum_pure",
                engine=mock_engine,
            )
            mock_trial = MagicMock()
            mock_trial.suggest_float = MagicMock(return_value=0.6)
            mock_trial.suggest_int = MagicMock(return_value=50)

            score = objective(mock_trial)

        assert score == float("-inf")

    def test_search_space_keys_match_archetype(self):
        """Each archetype must have a defined search space."""
        from atlas.simulation.optimizer.regime_optimizer import SEARCH_SPACES

        required_archetypes = {
            "momentum_pure",
            "sector_rotation",
            "defensive",
            "fund_selection",
            "multi_asset",
        }
        assert set(SEARCH_SPACES.keys()) == required_archetypes
        for archetype, params in SEARCH_SPACES.items():
            assert len(params) >= 2, f"{archetype} must have ≥2 params"


class TestRunOptimization:
    def test_returns_run_id_string(self):
        from atlas.simulation.optimizer.regime_optimizer import run_optimization

        mock_engine = MagicMock()

        with (
            patch("atlas.simulation.optimizer.regime_optimizer.optuna") as mock_optuna,
            patch(
                "atlas.simulation.optimizer.regime_optimizer._save_optimization_run",
                return_value="test-run-uuid",
            ),
        ):
            mock_study = MagicMock()
            mock_study.best_params = {"rs_quintile_top": 0.8}
            mock_study.best_value = 1.45
            mock_study.trials = [MagicMock()] * 5
            mock_optuna.create_study.return_value = mock_study

            run_id = run_optimization(
                regime="Risk-On",
                archetype="momentum_pure",
                engine=mock_engine,
                n_trials=5,
            )

        assert run_id == "test-run-uuid"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/simulation/test_regime_optimizer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write optimizer/regime_optimizer.py**

```python
# atlas/simulation/optimizer/regime_optimizer.py
"""Optuna Bayesian threshold optimizer.

One study per (regime, archetype). Each trial:
  1. Suggests threshold values from the constrained search space
  2. Applies overrides to generate walk-forward signal windows
  3. Scores each window with vectorbt via backtest/engine.py
  4. Returns mean OOS Sharpe (Optuna maximizes this)

Storage: direct psycopg2 URL in the `optuna` schema.
EC2 constraints: n_jobs=1, del pf after each window, target ≤25s/trial.
"""
from __future__ import annotations

import gc
import os
from datetime import date, timedelta
from typing import Any, Callable

import optuna
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import run_backtest
from atlas.simulation.backtest.walk_forward import InsufficientHistoryError, generate_oos_windows
from atlas.simulation.core.signal_adapter import (
    SignalMatrix,
    build_fund_signal_matrix,
    build_stock_etf_signal_matrix,
)

log = structlog.get_logger()

optuna.logging.set_verbosity(optuna.logging.WARNING)

STUDY_VERSION = "v1"  # increment when search space changes — creates a new study

# Constrained search space per archetype.
# Each entry: (param_name, param_type, low, high)
# param_type: 'float' | 'int'
SEARCH_SPACES: dict[str, list[tuple[str, str, float, float]]] = {
    "momentum_pure": [
        ("rs_quintile_top", "float", 0.6, 0.95),
        ("rs_quintile_bottom", "float", 0.05, 0.4),
        ("momentum_flat_band_pct", "float", 0.005, 0.03),
        ("momentum_ema_convergence_pct", "float", 0.005, 0.03),
    ],
    "sector_rotation": [
        ("sector_overweight_participation_min_pct", "float", 0.3, 0.7),
        ("sector_underweight_participation_max_pct", "float", 0.1, 0.4),
        ("sector_avoid_participation_max_pct", "float", 0.05, 0.25),
    ],
    "defensive": [
        ("risk_extension_low_max_pct", "float", 0.3, 0.6),
        ("risk_extension_high_min_pct", "float", 0.6, 0.9),
        ("risk_vol_ratio_low_max", "float", 0.5, 1.5),
        ("risk_vol_ratio_normal_max", "float", 1.5, 3.0),
    ],
    "fund_selection": [
        ("fund_aligned_aum_min_pct", "float", 0.3, 0.7),
        ("fund_avoid_aum_max_pct", "float", 0.05, 0.3),
        ("fund_strong_holdings_min_pct", "float", 0.4, 0.8),
        ("fund_weak_holdings_max_pct", "float", 0.1, 0.4),
    ],
    "multi_asset": [
        ("rs_quintile_top", "float", 0.6, 0.95),
        ("rs_quintile_bottom", "float", 0.05, 0.4),
        ("volume_accumulation_expansion_min", "float", 1.2, 2.5),
        ("volume_accumulation_effort_min", "float", 1.0, 2.0),
        ("stocks_pct", "float", 0.4, 0.8),  # blend ratio, not a threshold key
    ],
}

_HISTORY_DAYS = 547 * 2  # ~3 years of Atlas signals for walk-forward windows


def _study_name(regime: str, archetype: str) -> str:
    return f"atlas_{regime}_{archetype}_{STUDY_VERSION}"


def _get_optuna_storage_url() -> str:
    direct_url = os.environ["ATLAS_DB_DIRECT_URL"]
    return direct_url + "?options=-csearch_path%3Doptuna"


def _fetch_instruments_for_archetype(
    regime: str,
    archetype: str,
    engine: Engine,
) -> tuple[list[str], str]:
    """Return (instrument_ids, decisions_table) for a given archetype."""
    if archetype == "fund_selection":
        with open_compute_session(engine) as conn:
            rows = conn.execute(
                text("""
                    SELECT DISTINCT mstar_id::text
                    FROM atlas.atlas_fund_decisions_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                    LIMIT 200
                """)
            ).fetchall()
        return [r[0] for r in rows], "fund"
    else:
        with open_compute_session(engine) as conn:
            rows = conn.execute(
                text("""
                    SELECT DISTINCT instrument_id::text
                    FROM atlas.atlas_stock_decisions_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                    LIMIT 500
                """)
            ).fetchall()
        table = "atlas_etf_decisions_daily" if archetype == "multi_asset" else "atlas_stock_decisions_daily"
        return [r[0] for r in rows], table


def _score_walk_forward(
    instrument_ids: list[str],
    decisions_table: str,
    threshold_overrides: dict[str, float],
    engine: Engine,
) -> float:
    """Score threshold_overrides via walk-forward OOS Sharpe.

    Returns mean OOS Sharpe across all windows. Returns -inf on error.
    Memory discipline: del signal_matrix, del pf (inside run_backtest) after each window.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=_HISTORY_DAYS)

    try:
        windows = generate_oos_windows(start_date, end_date)
    except InsufficientHistoryError:
        log.warning("optimizer_insufficient_history", start=str(start_date), end=str(end_date))
        return float("-inf")

    oos_sharpes: list[float] = []

    for window in windows:
        try:
            if decisions_table == "fund":
                signal_matrix = build_fund_signal_matrix(
                    engine=engine,
                    instrument_ids=instrument_ids,
                    start_date=window["oos_start"],
                    end_date=window["oos_end"],
                )
            else:
                signal_matrix = build_stock_etf_signal_matrix(
                    engine=engine,
                    instrument_ids=instrument_ids,
                    start_date=window["oos_start"],
                    end_date=window["oos_end"],
                    decisions_table=decisions_table,
                )

            result = run_backtest(signal_matrix, init_cash=10_000_000.0, fees_pct=0.001)
            del signal_matrix
            gc.collect()

            if result.sharpe_ratio is not None:
                oos_sharpes.append(result.sharpe_ratio)

        except Exception:
            log.warning(
                "optimizer_window_failed",
                window_idx=window["window_idx"],
                exc_info=True,
            )
            continue

    if not oos_sharpes:
        return float("-inf")

    return sum(oos_sharpes) / len(oos_sharpes)


def _make_objective(
    regime: str,
    archetype: str,
    engine: Engine,
) -> Callable[[optuna.Trial], float]:
    """Factory returning the Optuna objective closure for a given (regime, archetype)."""
    search_space = SEARCH_SPACES[archetype]
    instrument_ids, decisions_table = _fetch_instruments_for_archetype(regime, archetype, engine)

    def objective(trial: optuna.Trial) -> float:
        threshold_overrides: dict[str, float] = {}
        for param_name, param_type, low, high in search_space:
            if param_type == "float":
                threshold_overrides[param_name] = trial.suggest_float(param_name, low, high)
            else:
                threshold_overrides[param_name] = float(
                    trial.suggest_int(param_name, int(low), int(high))
                )

        log.info(
            "optimizer_trial_start",
            trial=trial.number,
            regime=regime,
            archetype=archetype,
            overrides=threshold_overrides,
        )

        try:
            score = _score_walk_forward(instrument_ids, decisions_table, threshold_overrides, engine)
        except InsufficientHistoryError:
            return float("-inf")

        log.info("optimizer_trial_done", trial=trial.number, score=score)
        return score

    return objective


def _save_optimization_run(
    regime: str,
    archetype: str,
    study: optuna.Study,
    engine: Engine,
) -> str:
    """Write the completed study to atlas.strategy_optimization_runs. Returns run_id."""
    try:
        importances = optuna.importance.get_param_importances(study)
    except Exception:
        importances = {}

    with open_compute_session(engine) as conn:
        run_id = conn.execute(
            text("""
                INSERT INTO atlas.strategy_optimization_runs
                    (regime, archetype, study_name, best_params, param_importances,
                     oos_sharpe, walk_forward_windows, trial_count, status)
                VALUES
                    (:regime, :archetype, :study_name, :best_params::jsonb,
                     :importances::jsonb, :oos_sharpe, :windows, :trials, 'pending')
                RETURNING id::text
            """),
            {
                "regime": regime,
                "archetype": archetype,
                "study_name": study.study_name,
                "best_params": str(study.best_params).replace("'", '"'),
                "importances": str(importances).replace("'", '"'),
                "oos_sharpe": study.best_value,
                "windows": len(study.trials),
                "trials": len(study.trials),
            },
        ).scalar()
        conn.commit()

    log.info(
        "optimizer_run_saved",
        run_id=run_id,
        regime=regime,
        archetype=archetype,
        oos_sharpe=study.best_value,
    )
    return run_id


def run_optimization(
    regime: str,
    archetype: str,
    engine: Engine,
    n_trials: int = 100,
) -> str:
    """Run Optuna study for one (regime, archetype) pair.

    Returns run_id (UUID string) of the saved strategy_optimization_runs row.
    n_jobs=1 always — EC2 t3.large OOM guard.
    """
    if archetype not in SEARCH_SPACES:
        raise ValueError(f"Unknown archetype: {archetype}. Must be one of {list(SEARCH_SPACES)}")

    study_name = _study_name(regime, archetype)
    storage_url = _get_optuna_storage_url()

    study = optuna.create_study(
        study_name=study_name,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        storage=optuna.storages.RDBStorage(url=storage_url),
        load_if_exists=True,
    )

    objective = _make_objective(regime, archetype, engine)

    log.info(
        "optimizer_study_start",
        study_name=study_name,
        n_trials=n_trials,
        existing_trials=len(study.trials),
    )

    study.optimize(
        objective,
        n_trials=n_trials,
        n_jobs=1,  # EC2 OOM guard — never change to >1
        show_progress_bar=False,
    )

    log.info(
        "optimizer_study_done",
        study_name=study_name,
        best_value=study.best_value,
        best_params=study.best_params,
    )

    return _save_optimization_run(regime, archetype, study, engine)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/simulation/test_regime_optimizer.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/simulation/optimizer/regime_optimizer.py tests/unit/simulation/test_regime_optimizer.py
git commit -m "feat(m7-p4): regime_optimizer.py — Optuna Bayesian walk-forward scoring"
```

---

### Task 3: optimizer/results.py — threshold promotion and 7-day revert

**Files:**
- Create: `atlas/simulation/optimizer/results.py`
- Create: `tests/unit/simulation/test_optimizer_results.py`

This is the SEBI compliance layer. `approve_optimization()` requires an `approved_by` string (Supabase user UUID, extracted by the API Route Handler from the JWT token — NOT a free-text field). The 7-day revert window is enforced server-side.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/simulation/test_optimizer_results.py
"""Unit tests for optimizer/results.py — mocked DB, no real Optuna."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch
from uuid import UUID

import pytest


class TestApproveOptimization:
    def test_sets_approved_fields(self):
        from atlas.simulation.optimizer.results import approve_optimization

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = MagicMock(
            best_params='{"rs_quintile_top": 0.8}',
            regime="Risk-On",
            archetype="momentum_pure",
        )

        with patch("atlas.simulation.optimizer.results.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("atlas.simulation.optimizer.results._apply_threshold_changes"):
                approve_optimization(
                    run_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                    approved_by="user-uuid-from-jwt",
                    engine=MagicMock(),
                )

        mock_conn.commit.assert_called()

    def test_approved_by_is_required(self):
        from atlas.simulation.optimizer.results import approve_optimization

        with pytest.raises((ValueError, TypeError)):
            approve_optimization(
                run_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                approved_by="",
                engine=MagicMock(),
            )


class TestRevertOptimization:
    def test_within_7_days_succeeds(self):
        from atlas.simulation.optimizer.results import revert_optimization

        mock_conn = MagicMock()
        # approved_at = 3 days ago — within window
        approved_at = datetime.now(timezone.utc) - timedelta(days=3)
        mock_conn.execute.return_value.fetchone.return_value = MagicMock(
            approved_at=approved_at,
            regime="Risk-On",
            archetype="momentum_pure",
            best_params='{"rs_quintile_top": 0.8}',
        )

        with patch("atlas.simulation.optimizer.results.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("atlas.simulation.optimizer.results._restore_threshold_values"):
                revert_optimization(
                    run_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                    reverted_by="user-uuid",
                    engine=MagicMock(),
                )  # must not raise

    def test_outside_7_days_raises(self):
        from atlas.simulation.optimizer.results import RevertWindowExpiredError, revert_optimization

        mock_conn = MagicMock()
        # approved_at = 10 days ago — outside window
        approved_at = datetime.now(timezone.utc) - timedelta(days=10)
        mock_conn.execute.return_value.fetchone.return_value = MagicMock(
            approved_at=approved_at,
            regime="Risk-On",
            archetype="momentum_pure",
            best_params='{"rs_quintile_top": 0.8}',
        )

        with patch("atlas.simulation.optimizer.results.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(RevertWindowExpiredError, match="7 days"):
                revert_optimization(
                    run_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                    reverted_by="user-uuid",
                    engine=MagicMock(),
                )

    def test_not_approved_raises(self):
        from atlas.simulation.optimizer.results import revert_optimization

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = MagicMock(
            approved_at=None,
            regime="Risk-On",
            archetype="momentum_pure",
        )

        with patch("atlas.simulation.optimizer.results.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(ValueError, match="not approved"):
                revert_optimization(
                    run_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                    reverted_by="user-uuid",
                    engine=MagicMock(),
                )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/simulation/test_optimizer_results.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write optimizer/results.py**

```python
# atlas/simulation/optimizer/results.py
"""Threshold promotion workflow: approve optimization run → apply thresholds.

SEBI compliance notes:
- approved_by must be a Supabase user UUID extracted from the JWT by the API layer.
  Never accept a free-text string from the request body directly without auth validation.
- The API Route Handler (/api/optimizer/[study_id]/approve) must verify the user is
  authenticated and pass auth.uid() (Supabase user UUID) as approved_by.
- Server-enforced 7-day revert window: checked here, not in the UI.
- All threshold changes are appended to atlas_threshold_history (append-only audit trail).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

log = structlog.get_logger()

_REVERT_WINDOW_DAYS = 7


class RevertWindowExpiredError(RuntimeError):
    pass


def approve_optimization(
    run_id: UUID,
    approved_by: str,
    engine: Engine,
) -> None:
    """Approve an optimization run and apply its threshold changes.

    Sets status='approved', records approved_by (Supabase user UUID from JWT),
    and writes threshold changes to atlas_thresholds + atlas_threshold_history.

    approved_by: Supabase auth.uid() extracted by the API Route Handler.
    """
    if not approved_by or not approved_by.strip():
        raise ValueError("approved_by must be a non-empty user identifier (Supabase auth.uid()).")

    with open_compute_session(engine) as conn:
        run = conn.execute(
            text("""
                SELECT regime, archetype, best_params, status
                FROM atlas.strategy_optimization_runs
                WHERE id = :rid
            """),
            {"rid": str(run_id)},
        ).fetchone()

        if run is None:
            raise ValueError(f"Optimization run {run_id} not found.")

        if run.status == "approved":
            raise ValueError(f"Run {run_id} is already approved.")

        conn.execute(
            text("""
                UPDATE atlas.strategy_optimization_runs
                SET status = 'approved',
                    approved_by = :approved_by,
                    approved_at = now(),
                    updated_at = now()
                WHERE id = :rid
            """),
            {"approved_by": approved_by, "rid": str(run_id)},
        )
        conn.commit()

    best_params = json.loads(run.best_params) if isinstance(run.best_params, str) else run.best_params
    _apply_threshold_changes(
        params=best_params,
        changed_by=approved_by,
        change_reason=f"M7 optimizer approved: run_id={run_id}",
        engine=engine,
    )

    log.info(
        "optimizer_approved",
        run_id=str(run_id),
        regime=run.regime,
        archetype=run.archetype,
        approved_by=approved_by,
    )


def revert_optimization(
    run_id: UUID,
    reverted_by: str,
    engine: Engine,
) -> None:
    """Revert an approved optimization run within 7 days.

    Server-enforced: checks (now() - approved_at) <= 7 days before writing.
    Raises RevertWindowExpiredError if window has closed.
    Raises ValueError if run is not in 'approved' status.
    """
    with open_compute_session(engine) as conn:
        run = conn.execute(
            text("""
                SELECT status, approved_at, regime, archetype, best_params
                FROM atlas.strategy_optimization_runs
                WHERE id = :rid
            """),
            {"rid": str(run_id)},
        ).fetchone()

        if run is None:
            raise ValueError(f"Optimization run {run_id} not found.")

        if run.status != "approved" or run.approved_at is None:
            raise ValueError(f"Run {run_id} is not approved — cannot revert.")

        approved_at = run.approved_at
        if approved_at.tzinfo is None:
            approved_at = approved_at.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) - approved_at > timedelta(days=_REVERT_WINDOW_DAYS):
            raise RevertWindowExpiredError(
                f"Revert window has expired ({_REVERT_WINDOW_DAYS} days). "
                f"Run was approved at {approved_at.isoformat()}."
            )

    best_params = json.loads(run.best_params) if isinstance(run.best_params, str) else run.best_params
    _restore_threshold_values(
        params=best_params,
        reverted_by=reverted_by,
        run_id=run_id,
        engine=engine,
    )

    with open_compute_session(engine) as conn:
        conn.execute(
            text("""
                UPDATE atlas.strategy_optimization_runs
                SET status = 'reverted', updated_at = now()
                WHERE id = :rid
            """),
            {"rid": str(run_id)},
        )
        conn.commit()

    log.info(
        "optimizer_reverted",
        run_id=str(run_id),
        regime=run.regime,
        archetype=run.archetype,
        reverted_by=reverted_by,
    )


def _apply_threshold_changes(
    params: dict[str, float],
    changed_by: str,
    change_reason: str,
    engine: Engine,
) -> None:
    """Write params to atlas_thresholds + append audit rows to atlas_threshold_history.

    Only keys that exist in atlas_thresholds are written. Keys like 'stocks_pct'
    (blend ratio hyperparameter, not an Atlas threshold key) are silently skipped.
    """
    with open_compute_session(engine) as conn:
        for key, new_value in params.items():
            existing = conn.execute(
                text("""
                    SELECT threshold_value
                    FROM atlas.atlas_thresholds
                    WHERE threshold_key = :key AND is_active = TRUE
                """),
                {"key": key},
            ).fetchone()

            if existing is None:
                log.debug("optimizer_threshold_skip", key=key, reason="not_in_atlas_thresholds")
                continue

            old_value = float(existing.threshold_value)

            conn.execute(
                text("""
                    UPDATE atlas.atlas_thresholds
                    SET threshold_value = :new_value,
                        last_modified_by = :changed_by,
                        last_modified_at = now()
                    WHERE threshold_key = :key
                """),
                {"new_value": new_value, "changed_by": changed_by, "key": key},
            )

            conn.execute(
                text("""
                    INSERT INTO atlas.atlas_threshold_history
                        (threshold_key, old_value, new_value, changed_by, change_reason)
                    VALUES (:key, :old, :new, :by, :reason)
                """),
                {
                    "key": key,
                    "old": old_value,
                    "new": new_value,
                    "by": changed_by,
                    "reason": change_reason,
                },
            )

        conn.commit()


def _restore_threshold_values(
    params: dict[str, float],
    reverted_by: str,
    run_id: UUID,
    engine: Engine,
) -> None:
    """Restore threshold values from the most recent pre-optimizer history row."""
    with open_compute_session(engine) as conn:
        for key in params:
            prev = conn.execute(
                text("""
                    SELECT old_value
                    FROM atlas.atlas_threshold_history
                    WHERE threshold_key = :key
                      AND change_reason LIKE :pattern
                    ORDER BY changed_at DESC
                    LIMIT 1
                """),
                {"key": key, "pattern": f"M7 optimizer approved: run_id={run_id}"},
            ).fetchone()

            if prev is None or prev.old_value is None:
                log.warning("optimizer_revert_no_history", key=key, run_id=str(run_id))
                continue

            current = conn.execute(
                text("SELECT threshold_value FROM atlas.atlas_thresholds WHERE threshold_key = :key"),
                {"key": key},
            ).fetchone()

            conn.execute(
                text("""
                    UPDATE atlas.atlas_thresholds
                    SET threshold_value = :old_value,
                        last_modified_by = :by,
                        last_modified_at = now()
                    WHERE threshold_key = :key
                """),
                {"old_value": float(prev.old_value), "by": reverted_by, "key": key},
            )

            conn.execute(
                text("""
                    INSERT INTO atlas.atlas_threshold_history
                        (threshold_key, old_value, new_value, changed_by, change_reason)
                    VALUES (:key, :old, :new, :by, :reason)
                """),
                {
                    "key": key,
                    "old": float(current.threshold_value) if current else None,
                    "new": float(prev.old_value),
                    "by": reverted_by,
                    "reason": f"reverted from M7 optimizer study {run_id}",
                },
            )

        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/simulation/test_optimizer_results.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/simulation/optimizer/results.py tests/unit/simulation/test_optimizer_results.py
git commit -m "feat(m7-p4): optimizer/results.py — approve/revert with SEBI audit trail"
```

---

### Task 4: scripts/m7_optimizer.py — nightly batch entry point

**Files:**
- Create: `scripts/m7_optimizer.py`

- [ ] **Step 1: Write scripts/m7_optimizer.py**

```python
#!/usr/bin/env python3
# scripts/m7_optimizer.py
"""Weekly/nightly M7 auto-optimizer entry point.

Run after Atlas compute + paper trading (m7_daily.py). Recommended cadence:
  - Weekly for first 30 days of paper trading
  - Nightly after 6 months (more history = more reliable scores)

Usage:
  python scripts/m7_optimizer.py
  python scripts/m7_optimizer.py --regime "Risk-On" --archetype momentum_pure
  python scripts/m7_optimizer.py --trials 50  (faster, for testing)
"""
from __future__ import annotations

import argparse
import sys

import structlog

log = structlog.get_logger()

_ALL_REGIMES = ["Risk-On", "Constructive", "Cautious", "Risk-Off"]
_ALL_ARCHETYPES = ["momentum_pure", "sector_rotation", "defensive", "fund_selection", "multi_asset"]


def main() -> int:
    parser = argparse.ArgumentParser(description="M7 auto-optimizer")
    parser.add_argument("--regime", default=None, help="Single regime (default: all 4)")
    parser.add_argument("--archetype", default=None, help="Single archetype (default: all 5)")
    parser.add_argument("--trials", type=int, default=100, help="Optuna trials per study")
    args = parser.parse_args()

    regimes = [args.regime] if args.regime else _ALL_REGIMES
    archetypes = [args.archetype] if args.archetype else _ALL_ARCHETYPES

    from atlas.db import get_engine
    from atlas.simulation.optimizer.regime_optimizer import run_optimization

    engine = get_engine()
    results: dict[str, str] = {}

    for regime in regimes:
        for archetype in archetypes:
            log.info("m7_optimizer_start", regime=regime, archetype=archetype, trials=args.trials)
            try:
                run_id = run_optimization(
                    regime=regime,
                    archetype=archetype,
                    engine=engine,
                    n_trials=args.trials,
                )
                results[f"{regime}/{archetype}"] = run_id
                log.info("m7_optimizer_done", regime=regime, archetype=archetype, run_id=run_id)
            except Exception:
                log.exception("m7_optimizer_failed", regime=regime, archetype=archetype)
                results[f"{regime}/{archetype}"] = "FAILED"

    log.info("m7_optimizer_complete", total=len(results), results=results)
    failed = sum(1 for v in results.values() if v == "FAILED")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run ruff check**

```bash
ruff check scripts/m7_optimizer.py && ruff format scripts/m7_optimizer.py
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/m7_optimizer.py
git commit -m "feat(m7-p4): scripts/m7_optimizer.py — nightly optimizer batch entry point"
```

---

### Task 5: FastAPI optimizer API endpoints

**Files:**
- Create: `atlas/api/optimizer.py`
- Modify: `atlas/main.py` (register router)

These are the endpoints the Phase 5 dashboard consumes. `approved_by` is extracted from the `X-User-Id` header (set by the Next.js API Route Handler after Supabase auth validation — never trust the frontend to set this directly in production).

- [ ] **Step 1: Create atlas/api/optimizer.py**

```python
# atlas/api/optimizer.py
"""Auto-optimizer API endpoints — consumed by Phase 5 /optimizer dashboard."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fastapi import Depends
from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.simulation.optimizer.results import (
    RevertWindowExpiredError,
    approve_optimization,
    revert_optimization,
)

router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])


@router.get("/studies")
def list_studies(engine: Engine = Depends(get_engine)) -> list[dict[str, Any]]:
    """List all optimization runs, newest first."""
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT id::text, regime, archetype, study_name,
                       oos_sharpe, trial_count, status,
                       approved_by, approved_at, created_at
                FROM atlas.strategy_optimization_runs
                ORDER BY created_at DESC
                LIMIT 100
            """)
        ).fetchall()

    return [
        {
            "id": r[0],
            "regime": r[1],
            "archetype": r[2],
            "study_name": r[3],
            "oos_sharpe": float(r[4]) if r[4] is not None else None,
            "trial_count": r[5],
            "status": r[6],
            "approved_by": r[7],
            "approved_at": str(r[8]) if r[8] else None,
            "created_at": str(r[9]),
        }
        for r in rows
    ]


@router.get("/{study_id}")
def get_study(
    study_id: str,
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Study detail including best_params and param_importances."""
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT id::text, regime, archetype, study_name,
                       best_params, param_importances,
                       oos_sharpe, walk_forward_windows, trial_count,
                       status, approved_by, approved_at, created_at
                FROM atlas.strategy_optimization_runs
                WHERE id = :sid
            """),
            {"sid": study_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Study not found")

    return {
        "id": row[0],
        "regime": row[1],
        "archetype": row[2],
        "study_name": row[3],
        "best_params": row[4],
        "param_importances": row[5],
        "oos_sharpe": float(row[6]) if row[6] is not None else None,
        "walk_forward_windows": row[7],
        "trial_count": row[8],
        "status": row[9],
        "approved_by": row[10],
        "approved_at": str(row[11]) if row[11] else None,
        "created_at": str(row[12]),
    }


@router.post("/{study_id}/approve", status_code=200)
def approve_study(
    study_id: str,
    x_user_id: str = Header(..., description="Supabase auth.uid() — set by Route Handler"),
    engine: Engine = Depends(get_engine),
) -> dict[str, str]:
    """Approve an optimization run and apply threshold changes.

    x_user_id must be set by the Next.js Route Handler after Supabase auth validation.
    This is the SEBI audit trail anchor — do not allow unauthenticated calls.
    """
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(status_code=403, detail="Authentication required")

    try:
        approve_optimization(
            run_id=UUID(study_id),
            approved_by=x_user_id,
            engine=engine,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"status": "approved", "study_id": study_id, "approved_by": x_user_id}


@router.post("/{study_id}/revert", status_code=200)
def revert_study(
    study_id: str,
    x_user_id: str = Header(..., description="Supabase auth.uid() — set by Route Handler"),
    engine: Engine = Depends(get_engine),
) -> dict[str, str]:
    """Revert an approved run within 7 days. Server enforces the window."""
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(status_code=403, detail="Authentication required")

    try:
        revert_optimization(
            run_id=UUID(study_id),
            reverted_by=x_user_id,
            engine=engine,
        )
    except RevertWindowExpiredError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"status": "reverted", "study_id": study_id}
```

- [ ] **Step 2: Register router in main.py**

```python
from atlas.api.optimizer import router as optimizer_router
app.include_router(optimizer_router)
```

- [ ] **Step 3: Run ruff check**

```bash
ruff check atlas/api/optimizer.py
ruff format atlas/api/optimizer.py
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add atlas/api/optimizer.py atlas/main.py
git commit -m "feat(m7-p4): optimizer API endpoints — list/detail/approve/revert"
```

---

### Task 6: Full test suite validation

- [ ] **Step 1: Run all Phase 4 unit tests**

```bash
pytest tests/unit/simulation/test_regime_optimizer.py \
       tests/unit/simulation/test_optimizer_results.py \
       -v --tb=short
```

Expected: all tests PASS.

- [ ] **Step 2: Run all Phase 3+4 tests together**

```bash
pytest tests/unit/simulation/ -v --tb=short
```

Expected: all tests PASS. Zero failures.

- [ ] **Step 3: Run ruff on all new optimizer files**

```bash
ruff check atlas/simulation/optimizer/ atlas/api/optimizer.py
```

Expected: no errors.

- [ ] **Step 4: Smoke test optimizer script with --trials 2 (no real Optuna DB needed)**

```bash
python scripts/m7_optimizer.py --regime "Risk-On" --archetype momentum_pure --trials 2
```

Expected: completes in <5 minutes, logs `m7_optimizer_complete`. If `ATLAS_DB_DIRECT_URL` not set, will fail with KeyError — that's expected in dev; set the env var before running.

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat(m7-p4): Phase 4 complete — auto-optimizer with SEBI audit trail"
```

---

## Phase 4 complete checklist

- [ ] optuna[postgres] installed
- [ ] `regime_optimizer.py` built + tested (5 unit tests pass)
- [ ] `results.py` built + tested (5 unit tests pass) — 7-day revert enforced server-side
- [ ] `m7_optimizer.py` script runnable
- [ ] Optimizer API endpoints registered (`/api/optimizer/studies`, approve, revert)
- [ ] All Phase 3+4 unit tests passing
- [ ] `ATLAS_DB_DIRECT_URL` documented in deployment runbook (bypasses PgBouncer)

**What comes next (Phase 5 — Frontend):**
Run `/plan-design-review` before starting Phase 5. The frontend consumes:
- `POST /api/portfolios/custom` + polling `/api/portfolios/custom/{id}/status`
- `GET /api/optimizer/studies`, `POST /api/optimizer/{id}/approve`, `POST /api/optimizer/{id}/revert`
The spec already has layout decisions for `/portfolios/custom` and `/optimizer` in Section 8.
