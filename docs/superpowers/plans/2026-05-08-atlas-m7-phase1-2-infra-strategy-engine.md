# Atlas M7 — Phase 1+2: Infrastructure & Strategy Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core simulation infrastructure and 15-strategy paper trading engine so the nightly runner populates `strategy_paper_performance` after each Atlas compute run.

**Architecture:** Eight Alembic migrations create the DB schema; `signal_adapter.py` bridges JIP prices + Atlas signals into a `SignalMatrix`; `paper_trader.py` exposes pure functions (`apply_strategy_filter`, `compute_trades`) plus DB functions (`fetch_decisions`, `write_trades`); `runner.py` orchestrates the nightly pass — fetching decisions once per tier, looping strategies, bulk-writing results. All code is synchronous (psycopg2 + `open_compute_session()`).

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (sync), psycopg2, vectorbt 0.26.x, empyrical-reloaded, structlog, pytest, Alembic

---

## File Map

**New files — migrations:**
- `migrations/versions/013_create_strategy_configs.py`
- `migrations/versions/014_create_strategy_paper_portfolios.py`
- `migrations/versions/015_create_strategy_paper_trades.py`
- `migrations/versions/016_create_strategy_paper_performance.py`
- `migrations/versions/017_create_strategy_overlap_daily.py`
- `migrations/versions/018_create_strategy_backtest_results.py`
- `migrations/versions/019_create_strategy_optimization_runs.py`
- `migrations/versions/020_create_strategy_fm_custom_portfolios.py`

**New files — simulation core:**
- `atlas/simulation/__init__.py`
- `atlas/simulation/core/__init__.py`
- `atlas/simulation/core/signal_adapter.py`
- `atlas/simulation/core/paper_trader.py`
- `atlas/simulation/core/metrics.py`
- `atlas/simulation/core/overlap.py`
- `atlas/simulation/strategies/__init__.py`
- `atlas/simulation/strategies/loader.py`
- `atlas/simulation/strategies/runner.py`
- `atlas/simulation/strategies/configs/stocks_momentum_aggressive.yaml`
- `atlas/simulation/strategies/configs/stocks_momentum_moderate.yaml`
- `atlas/simulation/strategies/configs/stocks_momentum_conservative.yaml`
- `atlas/simulation/strategies/configs/stocks_sector_rotation_concentrated.yaml`
- `atlas/simulation/strategies/configs/stocks_sector_rotation_diversified.yaml`
- `atlas/simulation/strategies/configs/blend_momentum_60_40.yaml`
- `atlas/simulation/strategies/configs/blend_balanced_50_50.yaml`
- `atlas/simulation/strategies/configs/blend_etf_led.yaml`
- `atlas/simulation/strategies/configs/blend_defensive.yaml`
- `atlas/simulation/strategies/configs/blend_sector_rotation_etf.yaml`
- `atlas/simulation/strategies/configs/fund_l1_dominant.yaml`
- `atlas/simulation/strategies/configs/fund_l2_dominant.yaml`
- `atlas/simulation/strategies/configs/fund_l3_dominant.yaml`
- `atlas/simulation/strategies/configs/fund_balanced.yaml`
- `atlas/simulation/strategies/configs/fund_defensive.yaml`
- `atlas/simulation/backtest/__init__.py`
- `atlas/simulation/backtest/engine.py`
- `atlas/simulation/backtest/walk_forward.py`
- `atlas/simulation/backtest/report.py`

**New files — scripts:**
- `scripts/m7_daily.py`
- `scripts/m7_seed_mock_data.py`

**New files — tests:**
- `tests/unit/simulation/__init__.py`
- `tests/unit/simulation/test_paper_trader.py`
- `tests/unit/simulation/test_overlap.py`
- `tests/unit/simulation/test_walk_forward.py`
- `tests/unit/simulation/test_loader.py`
- `tests/integration/simulation/__init__.py`
- `tests/integration/simulation/test_paper_trader_integration.py`

---

## Task 1: Migrations 013-016 (strategy_configs + paper tables)

**Files:**
- Create: `migrations/versions/013_create_strategy_configs.py`
- Create: `migrations/versions/014_create_strategy_paper_portfolios.py`
- Create: `migrations/versions/015_create_strategy_paper_trades.py`
- Create: `migrations/versions/016_create_strategy_paper_performance.py`

- [ ] **Step 1: Write migration 013 — strategy_configs**

```python
# migrations/versions/013_create_strategy_configs.py
"""create strategy_configs

Revision ID: 013
Revises: 012
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            tier TEXT NOT NULL,
            archetype TEXT NOT NULL,
            variant TEXT NOT NULL,
            config JSONB NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_configs"))
```

- [ ] **Step 2: Write migration 014 — strategy_paper_portfolios**

```python
# migrations/versions/014_create_strategy_paper_portfolios.py
"""create strategy_paper_portfolios

Revision ID: 014
Revises: 013
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_paper_portfolios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            instrument_id TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            weight_pct NUMERIC(10,4) NOT NULL,
            entry_date DATE NOT NULL,
            entry_signal_type TEXT NOT NULL,
            notional_value NUMERIC(20,4) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(strategy_id, instrument_id)
        );
        CREATE INDEX idx_paper_portfolios_strategy
            ON atlas.strategy_paper_portfolios(strategy_id);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_paper_portfolios"))
```

- [ ] **Step 3: Write migration 015 — strategy_paper_trades**

```python
# migrations/versions/015_create_strategy_paper_trades.py
"""create strategy_paper_trades

Revision ID: 015
Revises: 014
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_paper_trades (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            instrument_id TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            action TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            price NUMERIC(20,4) NOT NULL,
            weight_pct NUMERIC(10,4) NOT NULL,
            notional_value NUMERIC(20,4) NOT NULL,
            trade_date DATE NOT NULL,
            regime_at_trade TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_paper_trades_strategy_date
            ON atlas.strategy_paper_trades(strategy_id, trade_date DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_paper_trades"))
```

- [ ] **Step 4: Write migration 016 — strategy_paper_performance**

```python
# migrations/versions/016_create_strategy_paper_performance.py
"""create strategy_paper_performance

Revision ID: 016
Revises: 015
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_paper_performance (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            date DATE NOT NULL,
            total_value NUMERIC(20,4) NOT NULL,
            daily_return NUMERIC(10,6) NOT NULL,
            benchmark_nifty500_return NUMERIC(10,6),
            benchmark_naive_atlas_return NUMERIC(10,6),
            regime TEXT NOT NULL,
            positions_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(strategy_id, date)
        );
        CREATE INDEX idx_paper_perf_strategy_date
            ON atlas.strategy_paper_performance(strategy_id, date DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_paper_performance"))
```

- [ ] **Step 5: Run migrations 013-016**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os
ssh jsl-wealth-server "cd atlas-os && alembic upgrade 016"
```

Expected: `Running upgrade 012 -> 013, 013 -> 014, 014 -> 015, 015 -> 016`

- [ ] **Step 6: Verify tables exist**

```bash
ssh jsl-wealth-server "cd atlas-os && python -c \"
from atlas.db import get_engine
from sqlalchemy import text
eng = get_engine()
with eng.connect() as conn:
    for t in ['strategy_configs','strategy_paper_portfolios','strategy_paper_trades','strategy_paper_performance']:
        r = conn.execute(text(f'SELECT COUNT(*) FROM atlas.{t}')).scalar()
        print(f'{t}: {r} rows')
\""
```

Expected: each table returns `0 rows` with no errors.

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/013_create_strategy_configs.py \
        migrations/versions/014_create_strategy_paper_portfolios.py \
        migrations/versions/015_create_strategy_paper_trades.py \
        migrations/versions/016_create_strategy_paper_performance.py
git commit -m "feat(M7): migrations 013-016 — strategy configs + paper trading tables"
```

---

## Task 2: Migrations 017-020 (overlap + backtest + optimizer + custom portfolios)

**Files:**
- Create: `migrations/versions/017_create_strategy_overlap_daily.py`
- Create: `migrations/versions/018_create_strategy_backtest_results.py`
- Create: `migrations/versions/019_create_strategy_optimization_runs.py`
- Create: `migrations/versions/020_create_strategy_fm_custom_portfolios.py`

- [ ] **Step 1: Write migration 017 — strategy_overlap_daily**

```python
# migrations/versions/017_create_strategy_overlap_daily.py
"""create strategy_overlap_daily

Revision ID: 017
Revises: 016
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_overlap_daily (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date DATE NOT NULL,
            strategy_a_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            strategy_b_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            jaccard_similarity NUMERIC(6,4) NOT NULL,
            common_instruments INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(date, strategy_a_id, strategy_b_id),
            CHECK (strategy_a_id < strategy_b_id)
        );
        CREATE INDEX idx_overlap_date
            ON atlas.strategy_overlap_daily(date DESC);
        CREATE INDEX idx_overlap_a
            ON atlas.strategy_overlap_daily(strategy_a_id, date DESC);
        CREATE INDEX idx_overlap_b
            ON atlas.strategy_overlap_daily(strategy_b_id, date DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_overlap_daily"))
```

- [ ] **Step 2: Write migration 018 — strategy_backtest_results**

```python
# migrations/versions/018_create_strategy_backtest_results.py
"""create strategy_backtest_results

Revision ID: 018
Revises: 017
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_backtest_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID REFERENCES atlas.strategy_configs(id),
            custom_portfolio_id UUID,
            backtest_type TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            sharpe_ratio NUMERIC(10,4),
            max_drawdown NUMERIC(10,4),
            total_return NUMERIC(10,4),
            alpha_vs_nifty500 NUMERIC(10,4),
            alpha_vs_naive_atlas NUMERIC(10,4),
            walk_forward_oos_sharpe NUMERIC(10,4),
            regime_breakdown JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_backtest_strategy
            ON atlas.strategy_backtest_results(strategy_id)
            WHERE strategy_id IS NOT NULL;
        CREATE INDEX idx_backtest_custom
            ON atlas.strategy_backtest_results(custom_portfolio_id)
            WHERE custom_portfolio_id IS NOT NULL;
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_backtest_results"))
```

- [ ] **Step 3: Write migration 019 — strategy_optimization_runs + optuna schema**

```python
# migrations/versions/019_create_strategy_optimization_runs.py
"""create strategy_optimization_runs + optuna schema

Revision ID: 019
Revises: 018
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS optuna"))
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_optimization_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regime TEXT NOT NULL,
            archetype TEXT NOT NULL,
            study_name TEXT NOT NULL,
            best_params JSONB NOT NULL,
            param_importances JSONB,
            oos_sharpe NUMERIC(10,4) NOT NULL,
            oos_alpha_vs_nifty500 NUMERIC(10,4),
            walk_forward_windows INT NOT NULL,
            trial_count INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT,
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_optim_status
            ON atlas.strategy_optimization_runs(status, created_at DESC);
        CREATE INDEX idx_optim_regime_archetype
            ON atlas.strategy_optimization_runs(regime, archetype, created_at DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_optimization_runs"))
```

- [ ] **Step 4: Write migration 020 — strategy_fm_custom_portfolios + FK backfill**

```python
# migrations/versions/020_create_strategy_fm_custom_portfolios.py
"""create strategy_fm_custom_portfolios + backfill FK on backtest_results

Revision ID: 020
Revises: 019
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_fm_custom_portfolios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            instruments JSONB NOT NULL,
            backtest_id UUID REFERENCES atlas.strategy_backtest_results(id),
            paper_trading_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (paper_trading_active = FALSE OR backtest_id IS NOT NULL)
        )
    """))
    # Add FK from backtest_results.custom_portfolio_id → this table
    op.create_foreign_key(
        "fk_backtest_custom_portfolio",
        "strategy_backtest_results",
        "strategy_fm_custom_portfolios",
        ["custom_portfolio_id"],
        ["id"],
        source_schema="atlas",
        referent_schema="atlas",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_backtest_custom_portfolio",
        "strategy_backtest_results",
        schema="atlas",
        type_="foreignkey",
    )
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_fm_custom_portfolios"))
```

- [ ] **Step 5: Run migrations 017-020**

```bash
ssh jsl-wealth-server "cd atlas-os && alembic upgrade head"
```

Expected: `Running upgrade 016 -> 017, 017 -> 018, 018 -> 019, 019 -> 020`

- [ ] **Step 6: Verify all 8 M7 tables exist**

```bash
ssh jsl-wealth-server "cd atlas-os && python -c \"
from atlas.db import get_engine
from sqlalchemy import text
eng = get_engine()
tables = [
    'strategy_configs','strategy_paper_portfolios','strategy_paper_trades',
    'strategy_paper_performance','strategy_overlap_daily',
    'strategy_backtest_results','strategy_optimization_runs',
    'strategy_fm_custom_portfolios'
]
with eng.connect() as conn:
    for t in tables:
        r = conn.execute(text(f'SELECT COUNT(*) FROM atlas.{t}')).scalar()
        print(f'OK: {t}')
\""
```

Expected: 8 `OK:` lines, no errors.

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/017_create_strategy_overlap_daily.py \
        migrations/versions/018_create_strategy_backtest_results.py \
        migrations/versions/019_create_strategy_optimization_runs.py \
        migrations/versions/020_create_strategy_fm_custom_portfolios.py
git commit -m "feat(M7): migrations 017-020 — overlap + backtest + optimizer + custom portfolios"
```

---

## Task 3: overlap.py (pure Jaccard math — start with tests)

**Files:**
- Create: `tests/unit/simulation/__init__.py`
- Create: `tests/unit/simulation/test_overlap.py`
- Create: `atlas/simulation/__init__.py`
- Create: `atlas/simulation/core/__init__.py`
- Create: `atlas/simulation/core/overlap.py`

- [ ] **Step 1: Create test init files**

```bash
mkdir -p tests/unit/simulation tests/integration/simulation
touch tests/unit/simulation/__init__.py tests/integration/simulation/__init__.py
mkdir -p atlas/simulation/core atlas/simulation/strategies atlas/simulation/backtest atlas/simulation/custom atlas/simulation/optimizer
touch atlas/simulation/__init__.py atlas/simulation/core/__init__.py
touch atlas/simulation/strategies/__init__.py atlas/simulation/backtest/__init__.py
touch atlas/simulation/custom/__init__.py atlas/simulation/optimizer/__init__.py
```

- [ ] **Step 2: Write failing tests for Jaccard math**

```python
# tests/unit/simulation/test_overlap.py
"""Unit tests for Jaccard overlap matrix — no DB required."""
from __future__ import annotations

import uuid
import pytest
from atlas.simulation.core.overlap import jaccard_similarity, upper_triangle_pairs


def test_jaccard_disjoint_sets_returns_zero():
    a = {"INFY", "TCS", "HDFC"}
    b = {"RELIANCE", "BAJFINANCE", "WIPRO"}
    assert jaccard_similarity(a, b) == 0.0


def test_jaccard_identical_sets_returns_one():
    a = {"INFY", "TCS", "HDFC"}
    assert jaccard_similarity(a, a) == 1.0


def test_jaccard_fifty_percent_overlap():
    a = {"INFY", "TCS"}
    b = {"INFY", "HDFC"}
    # |intersection| = 1, |union| = 3 → 1/3 ≈ 0.333
    result = jaccard_similarity(a, b)
    assert abs(result - 1 / 3) < 0.001


def test_jaccard_empty_sets_returns_zero():
    assert jaccard_similarity(set(), set()) == 0.0


def test_upper_triangle_pairs_count():
    ids = [uuid.uuid4() for _ in range(15)]
    pairs = upper_triangle_pairs(ids)
    # C(15, 2) = 105
    assert len(pairs) == 105


def test_upper_triangle_pairs_canonical_ordering():
    ids = [uuid.uuid4() for _ in range(5)]
    pairs = upper_triangle_pairs(ids)
    for a, b in pairs:
        assert str(a) < str(b), f"Pair not in canonical order: {a} < {b}"


def test_upper_triangle_pairs_no_self_pairs():
    ids = [uuid.uuid4() for _ in range(5)]
    pairs = upper_triangle_pairs(ids)
    for a, b in pairs:
        assert a != b
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/unit/simulation/test_overlap.py -v
```

Expected: `FAILED` (ImportError: `atlas.simulation.core.overlap` not found)

- [ ] **Step 4: Implement overlap.py**

```python
# atlas/simulation/core/overlap.py
"""Jaccard portfolio overlap matrix for 15 paper trading strategies."""
from __future__ import annotations

from uuid import UUID


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two instrument sets.

    Returns 0.0 for empty sets (both empty → no overlap).
    """
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union


def upper_triangle_pairs(ids: list[UUID]) -> list[tuple[UUID, UUID]]:
    """Return all C(n,2) pairs in canonical order (str(a) < str(b)).

    This ordering satisfies the CHECK constraint on strategy_overlap_daily.
    Always sort in Python before inserting — never rely on insertion order.
    """
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if str(a) < str(b):
                pairs.append((a, b))
            else:
                pairs.append((b, a))
    return pairs
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/unit/simulation/test_overlap.py -v
```

Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add tests/unit/simulation/__init__.py tests/integration/simulation/__init__.py \
        tests/unit/simulation/test_overlap.py \
        atlas/simulation/__init__.py atlas/simulation/core/__init__.py \
        atlas/simulation/strategies/__init__.py atlas/simulation/backtest/__init__.py \
        atlas/simulation/custom/__init__.py atlas/simulation/optimizer/__init__.py \
        atlas/simulation/core/overlap.py
git commit -m "feat(M7): overlap.py — Jaccard similarity + upper-triangle pairs"
```

---

## Task 4: walk_forward.py (with InsufficientHistoryError guard)

**Files:**
- Create: `tests/unit/simulation/test_walk_forward.py`
- Create: `atlas/simulation/backtest/walk_forward.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/simulation/test_walk_forward.py
"""Unit tests for walk-forward window generation — no DB, no vectorbt."""
from __future__ import annotations

from datetime import date, timedelta
import pytest
from atlas.simulation.backtest.walk_forward import (
    InsufficientHistoryError,
    generate_oos_windows,
)


def _date_range(months: int) -> tuple[date, date]:
    start = date(2024, 1, 1)
    end = start + timedelta(days=int(months * 30.44))
    return start, end


def test_raises_insufficient_history_below_547_days():
    start = date(2024, 1, 1)
    end = start + timedelta(days=546)
    with pytest.raises(InsufficientHistoryError, match="18 months"):
        generate_oos_windows(start, end)


def test_does_not_raise_at_exactly_547_days():
    start = date(2024, 1, 1)
    end = start + timedelta(days=547)
    windows = generate_oos_windows(start, end)
    assert len(windows) >= 1


def test_twelve_months_produces_four_oos_windows():
    start, end = _date_range(12)
    windows = generate_oos_windows(start, end)
    assert len(windows) == 4, f"Expected 4, got {len(windows)}"


def test_eighteen_months_produces_ten_oos_windows():
    start, end = _date_range(18)
    windows = generate_oos_windows(start, end)
    assert len(windows) == 10, f"Expected 10, got {len(windows)}"


def test_oos_windows_do_not_overlap_train_period():
    start, end = _date_range(18)
    windows = generate_oos_windows(start, end)
    for win in windows:
        # OOS start must be after train end
        assert win["oos_start"] > win["train_end"], \
            f"OOS start {win['oos_start']} <= train end {win['train_end']}"


def test_window_structure_has_required_keys():
    start, end = _date_range(18)
    windows = generate_oos_windows(start, end)
    required = {"train_start", "train_end", "oos_start", "oos_end", "window_idx"}
    for win in windows:
        assert required <= win.keys()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/unit/simulation/test_walk_forward.py -v
```

Expected: `FAILED` (ImportError)

- [ ] **Step 3: Implement walk_forward.py**

```python
# atlas/simulation/backtest/walk_forward.py
"""Walk-forward window generator for M7 optimizer.

Window: 6M train / 3M test, slide by 1M.
Minimum history: 547 days (≈18M) to produce ≥10 OOS windows.
Formula: windows = (total_months - train_months - test_months) / slide_months + 1
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TypedDict


class InsufficientHistoryError(ValueError):
    pass


_MONTH_DAYS = 30.44
_TRAIN_MONTHS = 6
_TEST_MONTHS = 3
_SLIDE_MONTHS = 1
_MIN_DAYS = 547  # ≈18M — ensures ≥10 OOS windows


class OOSWindow(TypedDict):
    window_idx: int
    train_start: date
    train_end: date
    oos_start: date
    oos_end: date


def _add_months(d: date, months: int) -> date:
    """Approximate month addition using 30.44 days/month."""
    import math
    return date.fromordinal(d.toordinal() + math.ceil(months * _MONTH_DAYS))


def generate_oos_windows(start: date, end: date) -> list[OOSWindow]:
    """Generate walk-forward OOS windows from [start, end].

    Raises InsufficientHistoryError if (end - start).days < 547.
    """
    total_days = (end - start).days
    if total_days < _MIN_DAYS:
        raise InsufficientHistoryError(
            f"Signal history {total_days} days < {_MIN_DAYS} required (≈18 months). "
            "Need at least 18 months of Atlas signals for reliable optimizer scoring."
        )

    windows: list[OOSWindow] = []
    idx = 0
    train_start = start

    while True:
        train_end = _add_months(train_start, _TRAIN_MONTHS)
        oos_start = train_end + __import__("datetime").timedelta(days=1)
        oos_end = _add_months(oos_start, _TEST_MONTHS)

        if oos_end > end:
            break

        windows.append(
            OOSWindow(
                window_idx=idx,
                train_start=train_start,
                train_end=train_end,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )

        train_start = _add_months(train_start, _SLIDE_MONTHS)
        idx += 1

    return windows
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/simulation/test_walk_forward.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/unit/simulation/test_walk_forward.py \
        atlas/simulation/backtest/__init__.py \
        atlas/simulation/backtest/walk_forward.py
git commit -m "feat(M7): walk_forward.py — OOS window generator with 547-day guard"
```

---

## Task 5: signal_adapter.py (JIP prices + Atlas signals → SignalMatrix)

**Files:**
- Create: `atlas/simulation/core/signal_adapter.py`

> No unit tests for signal_adapter — it's a DB read layer. Integration test in Task 13.

- [ ] **Step 1: Create signal_adapter.py**

```python
# atlas/simulation/core/signal_adapter.py
"""Bridges JIP prices and Atlas signals into a SignalMatrix for vectorbt.

Joins de_ohlcv_daily (JIP) + atlas_*_decisions_daily (Atlas) on (instrument_id, date).
Instruments with no JIP price data are excluded with a structlog warning (never silent).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

log = structlog.get_logger()


class StaleJIPDataError(RuntimeError):
    pass


@dataclass
class SignalMatrix:
    prices: np.ndarray        # shape (n_dates, n_instruments), float64
    entries: np.ndarray       # shape (n_dates, n_instruments), bool
    exits: np.ndarray         # shape (n_dates, n_instruments), bool
    dates: pd.DatetimeIndex
    instruments: list[str]

    def to_vectorbt(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.prices, self.entries, self.exits


def check_jip_staleness(engine: Engine, today: date) -> None:
    """Raise StaleJIPDataError if JIP data hasn't landed for today."""
    with open_compute_session(engine) as conn:
        jip_max = conn.execute(
            text("SELECT MAX(date) FROM de_ohlcv_daily")
        ).scalar()
    if jip_max is None or jip_max < today:
        raise StaleJIPDataError(
            f"JIP data last updated {jip_max}, expected {today}. "
            "Aborting — will retry tomorrow."
        )


def build_stock_etf_signal_matrix(
    engine: Engine,
    instrument_ids: list[str],
    start_date: date,
    end_date: date,
    decisions_table: str,  # 'atlas_stock_decisions_daily' or 'atlas_etf_decisions_daily'
) -> SignalMatrix:
    """Load stock or ETF signals + JIP prices into a SignalMatrix.

    Args:
        decisions_table: 'atlas_stock_decisions_daily' for stocks,
                         'atlas_etf_decisions_daily' for ETFs.
    """
    ids_csv = ", ".join(f"'{i}'" for i in instrument_ids)

    query = text(f"""
        SELECT
            d.date,
            d.instrument_id,
            p.close                                              AS price,
            (d.transition_trigger OR d.breakout_trigger)        AS entry_signal,
            (
                d.exit_market_riskoff OR d.exit_rs_deteriorate
                OR d.exit_momentum_collapse OR d.exit_volume_distrib
                OR d.exit_sector_avoid OR d.exit_stop_loss
            )                                                    AS exit_signal
        FROM atlas.{decisions_table} d
        JOIN de_ohlcv_daily p
            ON p.instrument_id = d.instrument_id AND p.date = d.date
        WHERE d.instrument_id IN ({ids_csv})
          AND d.date BETWEEN :start_date AND :end_date
        ORDER BY d.date, d.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(query, conn, params={"start_date": start_date, "end_date": end_date})

    if df.empty:
        log.warning(
            "signal_adapter_empty",
            decisions_table=decisions_table,
            instruments=len(instrument_ids),
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )

    missing_price = df[df["price"].isna()]["instrument_id"].unique()
    if len(missing_price) > 0:
        log.warning(
            "signal_adapter_missing_prices",
            instruments=list(missing_price),
            count=len(missing_price),
        )
    df = df.dropna(subset=["price"])

    pivot_price = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    pivot_entry = df.pivot(index="date", columns="instrument_id", values="entry_signal").sort_index().fillna(False)
    pivot_exit = df.pivot(index="date", columns="instrument_id", values="exit_signal").sort_index().fillna(False)

    instruments = list(pivot_price.columns)
    dates = pd.DatetimeIndex(pivot_price.index)

    return SignalMatrix(
        prices=pivot_price.values.astype(np.float64),
        entries=pivot_entry.values.astype(bool),
        exits=pivot_exit.values.astype(bool),
        dates=dates,
        instruments=instruments,
    )


def build_fund_signal_matrix(
    engine: Engine,
    instrument_ids: list[str],
    start_date: date,
    end_date: date,
) -> SignalMatrix:
    """Load fund signals + NAV prices into a SignalMatrix."""
    ids_csv = ", ".join(f"'{i}'" for i in instrument_ids)

    query = text(f"""
        SELECT
            d.date,
            d.instrument_id,
            n.nav                  AS price,
            d.entry_trigger        AS entry_signal,
            d.exit_trigger         AS exit_signal
        FROM atlas.atlas_fund_decisions_daily d
        JOIN de_mf_nav_history n
            ON n.instrument_id = d.instrument_id AND n.date = d.date
        WHERE d.instrument_id IN ({ids_csv})
          AND d.date BETWEEN :start_date AND :end_date
        ORDER BY d.date, d.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(query, conn, params={"start_date": start_date, "end_date": end_date})

    if df.empty:
        return SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )

    missing_nav = df[df["price"].isna()]["instrument_id"].unique()
    if len(missing_nav) > 0:
        log.warning("signal_adapter_missing_nav", instruments=list(missing_nav))
    df = df.dropna(subset=["price"])

    pivot_price = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    pivot_entry = df.pivot(index="date", columns="instrument_id", values="entry_signal").sort_index().fillna(False)
    pivot_exit = df.pivot(index="date", columns="instrument_id", values="exit_signal").sort_index().fillna(False)

    return SignalMatrix(
        prices=pivot_price.values.astype(np.float64),
        entries=pivot_entry.values.astype(bool),
        exits=pivot_exit.values.astype(bool),
        dates=pd.DatetimeIndex(pivot_price.index),
        instruments=list(pivot_price.columns),
    )
```

- [ ] **Step 2: Smoke-test the adapter against the real DB**

```bash
ssh jsl-wealth-server "cd atlas-os && python -c \"
from datetime import date
from atlas.db import get_engine
from atlas.simulation.core.signal_adapter import check_jip_staleness, build_stock_etf_signal_matrix
from sqlalchemy import text

eng = get_engine()

# Get a sample of stock instrument IDs
with eng.connect() as conn:
    ids = [r[0] for r in conn.execute(text(
        'SELECT instrument_id FROM atlas.atlas_universe_stocks LIMIT 10'
    )).fetchall()]

print('Testing with instruments:', ids[:3])
sm = build_stock_etf_signal_matrix(
    eng, ids,
    date(2025, 1, 1), date(2025, 3, 31),
    'atlas_stock_decisions_daily'
)
print('SignalMatrix shape:', sm.prices.shape)
print('Instruments:', sm.instruments[:3])
\""
```

Expected: prints a non-empty shape like `(60, 10)`.

- [ ] **Step 3: Commit**

```bash
git add atlas/simulation/core/signal_adapter.py
git commit -m "feat(M7): signal_adapter.py — JIP prices + Atlas signals → SignalMatrix"
```

---

## Task 6: paper_trader.py pure functions (TDD — business logic heart of M7)

**Files:**
- Create: `tests/unit/simulation/test_paper_trader.py`
- Create: `atlas/simulation/core/paper_trader.py` (pure functions only in this task)

- [ ] **Step 1: Write failing tests for pure functions**

```python
# tests/unit/simulation/test_paper_trader.py
"""Unit tests for paper_trader pure functions — no DB required.

Tests cover:
- apply_strategy_filter: threshold overrides, state filter
- compute_trades: regime stances, exit priority, cold start
"""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass, field
import pandas as pd
import pytest

from atlas.simulation.core.paper_trader import (
    Holding,
    Trade,
    apply_strategy_filter,
    compute_trades,
)


@dataclass
class MockStrategyConfig:
    name: str = "test_strategy"
    tier: str = "stocks_only"
    archetype: str = "momentum_pure"
    variant: str = "aggressive"
    state_filter: list[str] = field(default_factory=lambda: ["leader"])
    regime_stance: str = "pause_risk_off"
    position_sizing: str = "equal_weight"
    max_positions: int = 10
    max_sector_pct: float = 40.0
    rebalance_trigger: str = "signal_change"
    threshold_overrides: dict = field(default_factory=dict)


def _make_decisions_df(
    instruments: list[str],
    rs_states: list[str],
    transition_triggers: list[bool],
    breakout_triggers: list[bool],
    exit_rs: list[bool] | None = None,
) -> pd.DataFrame:
    n = len(instruments)
    return pd.DataFrame({
        "instrument_id": instruments,
        "rs_state": rs_states,
        "transition_trigger": transition_triggers,
        "breakout_trigger": breakout_triggers,
        "exit_rs_deteriorate": exit_rs or [False] * n,
        "exit_market_riskoff": [False] * n,
        "exit_momentum_collapse": [False] * n,
        "exit_volume_distrib": [False] * n,
        "exit_sector_avoid": [False] * n,
        "exit_stop_loss": [False] * n,
    })


# --- apply_strategy_filter tests ---

def test_apply_filter_returns_leader_entries_only():
    decisions = _make_decisions_df(
        instruments=["INFY", "TCS", "WIPRO"],
        rs_states=["Leader", "Strong", "Leader"],
        transition_triggers=[True, True, True],
        breakout_triggers=[False, False, False],
    )
    config = MockStrategyConfig(state_filter=["leader"])
    entries, exits = apply_strategy_filter(decisions, config, {})
    # TCS is Strong, not Leader — excluded despite transition_trigger
    assert entries == {"INFY", "WIPRO"}
    assert exits == set()


def test_apply_filter_includes_strong_with_state_filter_strong():
    decisions = _make_decisions_df(
        instruments=["INFY", "TCS"],
        rs_states=["Leader", "Strong"],
        transition_triggers=[True, True],
        breakout_triggers=[False, False],
    )
    config = MockStrategyConfig(state_filter=["leader", "strong"])
    entries, exits = apply_strategy_filter(decisions, config, {})
    assert entries == {"INFY", "TCS"}


def test_apply_filter_no_entry_without_trigger():
    decisions = _make_decisions_df(
        instruments=["INFY"],
        rs_states=["Leader"],
        transition_triggers=[False],
        breakout_triggers=[False],
    )
    config = MockStrategyConfig(state_filter=["leader"])
    entries, exits = apply_strategy_filter(decisions, config, {})
    assert entries == set()


def test_apply_filter_exit_rs_deteriorate_detected():
    decisions = _make_decisions_df(
        instruments=["INFY"],
        rs_states=["Laggard"],
        transition_triggers=[False],
        breakout_triggers=[False],
        exit_rs=[True],
    )
    config = MockStrategyConfig()
    entries, exits = apply_strategy_filter(decisions, config, {})
    assert "INFY" in exits


# --- compute_trades tests ---

def test_compute_trades_cold_start_produces_entries_only():
    entries = {"INFY", "TCS"}
    exits = set()
    holdings: dict[str, Holding] = {}  # empty = cold start
    config = MockStrategyConfig(regime_stance="pause_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-On", config)
    actions = {t.action for t in trades}
    assert "exit" not in actions
    entry_instruments = {t.instrument_id for t in trades if t.action == "enter"}
    assert entry_instruments == {"INFY", "TCS"}


def test_compute_trades_pause_risk_off_blocks_new_entries():
    entries = {"WIPRO"}  # new entry candidate
    exits = set()
    holdings = {"INFY": Holding("INFY", "stock", 50.0, date(2025, 1, 1), "transition", 500_000)}
    config = MockStrategyConfig(regime_stance="pause_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-Off", config)
    # No new entries allowed in Risk-Off + pause_risk_off
    entry_instruments = {t.instrument_id for t in trades if t.action == "enter"}
    assert "WIPRO" not in entry_instruments


def test_compute_trades_hold_risk_off_allows_entries():
    entries = {"WIPRO"}
    exits = set()
    holdings: dict[str, Holding] = {}
    config = MockStrategyConfig(regime_stance="hold_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-Off", config)
    entry_instruments = {t.instrument_id for t in trades if t.action == "enter"}
    assert "WIPRO" in entry_instruments


def test_compute_trades_exits_are_generated():
    entries = set()
    exits = {"INFY"}
    holdings = {"INFY": Holding("INFY", "stock", 50.0, date(2025, 1, 1), "transition", 500_000)}
    config = MockStrategyConfig()
    trades = compute_trades(holdings, entries, exits, "Risk-On", config)
    exit_instruments = {t.instrument_id for t in trades if t.action == "exit"}
    assert "INFY" in exit_instruments


def test_compute_trades_scale_risk_off_marks_rebalance():
    entries = set()
    exits = set()
    holdings = {
        "INFY": Holding("INFY", "stock", 60.0, date(2025, 1, 1), "transition", 600_000),
    }
    config = MockStrategyConfig(regime_stance="scale_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-Off", config)
    rebalances = [t for t in trades if t.action == "rebalance"]
    # Should scale INFY from 60% to 60% * 0.4 = 24%
    assert len(rebalances) == 1
    assert abs(rebalances[0].weight_pct - 24.0) < 0.01
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/unit/simulation/test_paper_trader.py -v
```

Expected: `FAILED` (ImportError)

- [ ] **Step 3: Implement paper_trader.py pure functions**

```python
# atlas/simulation/core/paper_trader.py
"""Paper trading state machine — sync, psycopg2-backed.

Pure functions (apply_strategy_filter, compute_trades) have no DB calls
and are the primary unit-test targets. DB functions (fetch_decisions,
write_trades, etc.) are called by runner.py.
"""
from __future__ import annotations

import gc
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, open_compute_session

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

_RISK_OFF_SCALE = 0.4


@dataclass
class Holding:
    instrument_id: str
    instrument_type: str
    weight_pct: float
    entry_date: date
    entry_signal_type: str
    notional_value: float


@dataclass
class Trade:
    instrument_id: str
    instrument_type: str
    action: str          # enter | exit | rebalance
    signal_type: str
    weight_pct: float
    notional_value: float


class MissingAtlasDecisionsError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Pure functions — testable without DB
# ---------------------------------------------------------------------------

_STATE_FILTER_MAP = {
    "leader":    {"Leader"},
    "strong":    {"Leader", "Strong"},
    "emerging":  {"Leader", "Strong", "Emerging"},
    "investable": None,  # None = accept any rs_state when is_investable=TRUE
}

_EXIT_COLUMNS = [
    "exit_market_riskoff",
    "exit_rs_deteriorate",
    "exit_momentum_collapse",
    "exit_volume_distrib",
    "exit_sector_avoid",
    "exit_stop_loss",
]


def apply_strategy_filter(
    decisions: pd.DataFrame,
    config: object,  # StrategyConfig or MockStrategyConfig
    threshold_overrides: dict[str, float],
) -> tuple[set[str], set[str]]:
    """Pure function: decisions DataFrame + config → (entry_set, exit_set).

    No DB calls. Applies state_filter and entry trigger logic in-memory.
    threshold_overrides are applied by runner.py before calling this function
    (re-querying with overridden thresholds is runner's responsibility).
    """
    entry_set: set[str] = set()
    exit_set: set[str] = set()

    allowed_states: set[str] | None = set()
    for sf in getattr(config, "state_filter", ["leader"]):
        mapped = _STATE_FILTER_MAP.get(sf.lower())
        if mapped is None:
            allowed_states = None  # investable = any state
            break
        allowed_states |= mapped

    for row in decisions.itertuples(index=False):
        instrument_id = row.instrument_id

        # Check exits first (highest priority)
        for col in _EXIT_COLUMNS:
            if getattr(row, col, False):
                exit_set.add(instrument_id)
                break

        if instrument_id in exit_set:
            continue

        # Check entry conditions
        has_trigger = getattr(row, "transition_trigger", False) or getattr(row, "breakout_trigger", False)
        if not has_trigger:
            # Also check fund entry_trigger
            has_trigger = getattr(row, "entry_trigger", False)

        if not has_trigger:
            continue

        rs_state = getattr(row, "rs_state", "")
        if allowed_states is None or rs_state in allowed_states:
            entry_set.add(instrument_id)

    return entry_set, exit_set


def compute_trades(
    current_holdings: dict[str, Holding],
    entries: set[str],
    exits: set[str],
    regime: str,
    config: object,
) -> list[Trade]:
    """Pure function: holdings + signals + regime → trade list.

    Applies regime_stance logic:
    - pause_risk_off: block new entries in Risk-Off; allow exits
    - scale_risk_off: scale all holdings by 0.4× in Risk-Off; rebalance trades
    - hold_risk_off: no behavior change
    """
    trades: list[Trade] = []
    is_risk_off = regime == "Risk-Off"
    regime_stance = getattr(config, "regime_stance", "pause_risk_off")
    max_positions = getattr(config, "max_positions", 20)

    # 1. Exit trades
    for inst_id in exits:
        if inst_id in current_holdings:
            h = current_holdings[inst_id]
            trades.append(Trade(
                instrument_id=inst_id,
                instrument_type=h.instrument_type,
                action="exit",
                signal_type="exit_signal",
                weight_pct=0.0,
                notional_value=0.0,
            ))

    # 2. Rebalance for scale_risk_off
    if is_risk_off and regime_stance == "scale_risk_off":
        for inst_id, h in current_holdings.items():
            if inst_id in exits:
                continue
            scaled_weight = h.weight_pct * _RISK_OFF_SCALE
            if abs(scaled_weight - h.weight_pct) > 0.01:
                trades.append(Trade(
                    instrument_id=inst_id,
                    instrument_type=h.instrument_type,
                    action="rebalance",
                    signal_type="regime_scale",
                    weight_pct=scaled_weight,
                    notional_value=h.notional_value * _RISK_OFF_SCALE,
                ))

    # 3. New entry trades
    if is_risk_off and regime_stance == "pause_risk_off":
        return trades  # Block all new entries

    new_entries = entries - set(current_holdings.keys()) - exits
    if len(current_holdings) + len(new_entries) > max_positions:
        new_entries = set(list(new_entries)[: max_positions - len(current_holdings)])

    equal_weight = 100.0 / max(len(new_entries) + len(current_holdings), 1)
    for inst_id in new_entries:
        trades.append(Trade(
            instrument_id=inst_id,
            instrument_type="stock",  # runner sets correct type from decisions
            action="enter",
            signal_type="entry_signal",
            weight_pct=equal_weight,
            notional_value=equal_weight * 100_000,  # placeholder; runner sets from price
        ))

    return trades


# ---------------------------------------------------------------------------
# DB functions — called by runner.py
# ---------------------------------------------------------------------------

def fetch_decisions(conn: object, tier: str, today: date) -> pd.DataFrame:
    """Load full decision universe for one tier on today. One DB call.

    Args:
        tier: 'stocks' | 'etf' | 'fund'
        today: the date to load decisions for

    Returns:
        DataFrame with all instruments and their signals for today.
    """
    table_map = {
        "stocks": "atlas_stock_decisions_daily",
        "etf": "atlas_etf_decisions_daily",
        "fund": "atlas_fund_decisions_daily",
    }
    if tier not in table_map:
        raise ValueError(f"Unknown tier: {tier}. Must be stocks | etf | fund")

    table = table_map[tier]

    if tier in ("stocks", "etf"):
        query = text(f"""
            SELECT d.instrument_id, s.rs_state,
                   d.transition_trigger, d.breakout_trigger,
                   d.exit_market_riskoff, d.exit_rs_deteriorate,
                   d.exit_momentum_collapse, d.exit_volume_distrib,
                   d.exit_sector_avoid, d.exit_stop_loss
            FROM atlas.{table} d
            JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = d.instrument_id AND s.date = d.date
            WHERE d.date = :today
        """)
    else:
        query = text(f"""
            SELECT instrument_id,
                   entry_trigger, exit_trigger,
                   reduce_trigger, add_trigger
            FROM atlas.{table}
            WHERE date = :today
        """)

    return pd.read_sql(query, conn, params={"today": today})


def check_decisions_exist(engine: Engine, tier: str, today: date) -> None:
    """Raise MissingAtlasDecisionsError if no decisions for today."""
    table_map = {
        "stocks": "atlas_stock_decisions_daily",
        "etf": "atlas_etf_decisions_daily",
        "fund": "atlas_fund_decisions_daily",
    }
    table = table_map[tier]
    with open_compute_session(engine) as conn:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM atlas.{table} WHERE date = :d"),
            {"d": today},
        ).scalar()
    if count == 0:
        raise MissingAtlasDecisionsError(
            f"No {tier} decisions found for {today} — Atlas compute may have failed."
        )


def load_current_holdings(conn: object, strategy_id: UUID) -> dict[str, Holding]:
    """Read current atlas.strategy_paper_portfolios for one strategy."""
    rows = conn.execute(
        text("""
            SELECT instrument_id, instrument_type, weight_pct,
                   entry_date, entry_signal_type, notional_value
            FROM atlas.strategy_paper_portfolios
            WHERE strategy_id = :sid
        """),
        {"sid": str(strategy_id)},
    ).fetchall()
    return {
        r.instrument_id: Holding(
            instrument_id=r.instrument_id,
            instrument_type=r.instrument_type,
            weight_pct=float(r.weight_pct),
            entry_date=r.entry_date,
            entry_signal_type=r.entry_signal_type,
            notional_value=float(r.notional_value),
        )
        for r in rows
    }


def write_trades(
    engine: Engine,
    trades: list[Trade],
    strategy_id: UUID,
    today: date,
    regime: str,
    prices: dict[str, float],
) -> None:
    """Bulk-insert trades to atlas.strategy_paper_trades."""
    if not trades:
        return
    rows = [
        (
            str(strategy_id),
            t.instrument_id,
            t.instrument_type,
            t.action,
            t.signal_type,
            prices.get(t.instrument_id, 0.0),
            t.weight_pct,
            t.notional_value,
            today,
            regime,
        )
        for t in trades
    ]
    bulk_upsert(
        engine=engine,
        table="atlas.strategy_paper_trades",
        columns=[
            "strategy_id", "instrument_id", "instrument_type",
            "action", "signal_type", "price", "weight_pct",
            "notional_value", "trade_date", "regime_at_trade",
        ],
        rows=rows,
        pk_columns=["strategy_id", "instrument_id", "trade_date", "action"],
    )


def update_holdings(
    engine: Engine,
    trades: list[Trade],
    strategy_id: UUID,
    today: date,
) -> None:
    """Apply trades to atlas.strategy_paper_portfolios."""
    with open_compute_session(engine) as conn:
        for t in trades:
            if t.action == "exit":
                conn.execute(
                    text("""
                        DELETE FROM atlas.strategy_paper_portfolios
                        WHERE strategy_id = :sid AND instrument_id = :iid
                    """),
                    {"sid": str(strategy_id), "iid": t.instrument_id},
                )
            elif t.action == "enter":
                conn.execute(
                    text("""
                        INSERT INTO atlas.strategy_paper_portfolios
                            (strategy_id, instrument_id, instrument_type,
                             weight_pct, entry_date, entry_signal_type, notional_value)
                        VALUES (:sid, :iid, :itype, :wpct, :edate, :esig, :nval)
                        ON CONFLICT (strategy_id, instrument_id) DO UPDATE SET
                            weight_pct = EXCLUDED.weight_pct,
                            notional_value = EXCLUDED.notional_value,
                            updated_at = now()
                    """),
                    {
                        "sid": str(strategy_id),
                        "iid": t.instrument_id,
                        "itype": t.instrument_type,
                        "wpct": t.weight_pct,
                        "edate": today,
                        "esig": t.signal_type,
                        "nval": t.notional_value,
                    },
                )
            elif t.action == "rebalance":
                conn.execute(
                    text("""
                        UPDATE atlas.strategy_paper_portfolios
                        SET weight_pct = :wpct, notional_value = :nval, updated_at = now()
                        WHERE strategy_id = :sid AND instrument_id = :iid
                    """),
                    {
                        "sid": str(strategy_id),
                        "iid": t.instrument_id,
                        "wpct": t.weight_pct,
                        "nval": t.notional_value,
                    },
                )
        conn.commit()


def record_daily_performance(
    engine: Engine,
    strategy_id: UUID,
    today: date,
    total_value: float,
    daily_return: float,
    regime: str,
    positions_count: int,
    benchmark_nifty500: float | None = None,
    benchmark_naive_atlas: float | None = None,
) -> None:
    """Write one row to atlas.strategy_paper_performance."""
    bulk_upsert(
        engine=engine,
        table="atlas.strategy_paper_performance",
        columns=[
            "strategy_id", "date", "total_value", "daily_return",
            "benchmark_nifty500_return", "benchmark_naive_atlas_return",
            "regime", "positions_count",
        ],
        rows=[(
            str(strategy_id),
            today,
            total_value,
            daily_return,
            benchmark_nifty500,
            benchmark_naive_atlas,
            regime,
            positions_count,
        )],
        pk_columns=["strategy_id", "date"],
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/simulation/test_paper_trader.py -v
```

Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/unit/simulation/test_paper_trader.py \
        atlas/simulation/core/paper_trader.py
git commit -m "feat(M7): paper_trader.py — pure functions + DB functions (sync psycopg2)"
```

---

## Task 7: 15 Strategy YAML configs

**Files:**
- Create: `atlas/simulation/strategies/configs/*.yaml` (15 files)

- [ ] **Step 1: Create stocks_momentum_aggressive.yaml**

```yaml
# atlas/simulation/strategies/configs/stocks_momentum_aggressive.yaml
strategy:
  id: stocks_momentum_aggressive
  name: "Momentum Aggressive (Stocks)"
  tier: stocks_only
  archetype: momentum_pure
  variant: aggressive
  threshold_overrides:
    rs_quintile_top: 0.85
    rs_quintile_bottom: 0.15
  state_filter: [leader]
  regime_stance: pause_risk_off
  position_sizing: rs_proportional
  max_positions: 20
  max_sector_pct: 40.0
  rebalance_trigger: signal_change
```

- [ ] **Step 2: Create remaining 14 YAML configs**

```yaml
# atlas/simulation/strategies/configs/stocks_momentum_moderate.yaml
strategy:
  id: stocks_momentum_moderate
  name: "Momentum Moderate (Stocks)"
  tier: stocks_only
  archetype: momentum_pure
  variant: moderate
  threshold_overrides:
    rs_quintile_top: 0.80
  state_filter: [leader, strong]
  regime_stance: scale_risk_off
  position_sizing: rs_proportional
  max_positions: 25
  max_sector_pct: 35.0
  rebalance_trigger: signal_change
```

```yaml
# atlas/simulation/strategies/configs/stocks_momentum_conservative.yaml
strategy:
  id: stocks_momentum_conservative
  name: "Momentum Conservative (Stocks)"
  tier: stocks_only
  archetype: momentum_pure
  variant: conservative
  threshold_overrides:
    rs_quintile_top: 0.75
  state_filter: [leader, strong, emerging]
  regime_stance: scale_risk_off
  position_sizing: regime_scaled
  max_positions: 30
  max_sector_pct: 30.0
  rebalance_trigger: signal_change
```

```yaml
# atlas/simulation/strategies/configs/stocks_sector_rotation_concentrated.yaml
strategy:
  id: stocks_sector_rotation_concentrated
  name: "Sector Rotation Concentrated (Stocks)"
  tier: stocks_only
  archetype: sector_rotation
  variant: concentrated
  threshold_overrides:
    sector_overweight_participation_min_pct: 55
  state_filter: [leader, strong]
  regime_stance: pause_risk_off
  position_sizing: equal_weight
  max_positions: 20
  max_sector_pct: 60.0
  top_sectors: 2
  rebalance_trigger: weekly
```

```yaml
# atlas/simulation/strategies/configs/stocks_sector_rotation_diversified.yaml
strategy:
  id: stocks_sector_rotation_diversified
  name: "Sector Rotation Diversified (Stocks)"
  tier: stocks_only
  archetype: sector_rotation
  variant: diversified
  threshold_overrides:
    sector_overweight_participation_min_pct: 50
  state_filter: [leader, strong]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 30
  max_sector_pct: 30.0
  top_sectors: 4
  rebalance_trigger: weekly
```

```yaml
# atlas/simulation/strategies/configs/blend_momentum_60_40.yaml
strategy:
  id: blend_momentum_60_40
  name: "Blend Momentum 60/40"
  tier: stocks_etf
  archetype: multi_asset
  variant: momentum_60_40
  threshold_overrides: {}
  state_filter: [leader]
  regime_stance: scale_risk_off
  position_sizing: rs_proportional
  max_positions: 25
  max_sector_pct: 35.0
  stocks_pct: 0.60
  rebalance_trigger: signal_change
```

```yaml
# atlas/simulation/strategies/configs/blend_balanced_50_50.yaml
strategy:
  id: blend_balanced_50_50
  name: "Blend Balanced 50/50"
  tier: stocks_etf
  archetype: multi_asset
  variant: balanced_50_50
  threshold_overrides: {}
  state_filter: [leader, strong]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 30
  max_sector_pct: 30.0
  stocks_pct: 0.50
  rebalance_trigger: signal_change
```

```yaml
# atlas/simulation/strategies/configs/blend_etf_led.yaml
strategy:
  id: blend_etf_led
  name: "Blend ETF-Led"
  tier: stocks_etf
  archetype: multi_asset
  variant: etf_led
  threshold_overrides: {}
  state_filter: [leader, strong]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 25
  max_sector_pct: 40.0
  stocks_pct: 0.30
  rebalance_trigger: weekly
```

```yaml
# atlas/simulation/strategies/configs/blend_defensive.yaml
strategy:
  id: blend_defensive
  name: "Blend Defensive"
  tier: stocks_etf
  archetype: defensive
  variant: risk_gated
  threshold_overrides:
    risk_extension_low_max_pct: 20
  state_filter: [leader, strong]
  regime_stance: pause_risk_off
  position_sizing: equal_weight
  max_positions: 20
  max_sector_pct: 25.0
  stocks_pct: 0.50
  rebalance_trigger: signal_change
```

```yaml
# atlas/simulation/strategies/configs/blend_sector_rotation_etf.yaml
strategy:
  id: blend_sector_rotation_etf
  name: "Blend Sector Rotation (ETF-Led)"
  tier: stocks_etf
  archetype: sector_rotation
  variant: etf_sector
  threshold_overrides:
    sector_overweight_participation_min_pct: 52
  state_filter: [leader, strong]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 20
  max_sector_pct: 40.0
  stocks_pct: 0.40
  rebalance_trigger: weekly
```

```yaml
# atlas/simulation/strategies/configs/fund_l1_dominant.yaml
strategy:
  id: fund_l1_dominant
  name: "Fund L1 Dominant (NAV)"
  tier: mf_only
  archetype: fund_selection
  variant: l1_dominant
  threshold_overrides:
    fund_aligned_aum_min_pct: 72
  state_filter: [investable]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 15
  max_sector_pct: 50.0
  lens_weights: {nav: 0.60, composition: 0.25, holdings: 0.15}
  rebalance_trigger: monthly
```

```yaml
# atlas/simulation/strategies/configs/fund_l2_dominant.yaml
strategy:
  id: fund_l2_dominant
  name: "Fund L2 Dominant (Composition)"
  tier: mf_only
  archetype: fund_selection
  variant: l2_dominant
  threshold_overrides: {}
  state_filter: [investable]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 15
  max_sector_pct: 50.0
  lens_weights: {nav: 0.30, composition: 0.50, holdings: 0.20}
  rebalance_trigger: monthly
```

```yaml
# atlas/simulation/strategies/configs/fund_l3_dominant.yaml
strategy:
  id: fund_l3_dominant
  name: "Fund L3 Dominant (Holdings)"
  tier: mf_only
  archetype: fund_selection
  variant: l3_dominant
  threshold_overrides: {}
  state_filter: [investable]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 15
  max_sector_pct: 50.0
  lens_weights: {nav: 0.30, composition: 0.20, holdings: 0.50}
  rebalance_trigger: monthly
```

```yaml
# atlas/simulation/strategies/configs/fund_balanced.yaml
strategy:
  id: fund_balanced
  name: "Fund Balanced (Equal Lens)"
  tier: mf_only
  archetype: fund_selection
  variant: balanced
  threshold_overrides: {}
  state_filter: [investable]
  regime_stance: scale_risk_off
  position_sizing: equal_weight
  max_positions: 20
  max_sector_pct: 40.0
  lens_weights: {nav: 0.333, composition: 0.333, holdings: 0.334}
  rebalance_trigger: monthly
```

```yaml
# atlas/simulation/strategies/configs/fund_defensive.yaml
strategy:
  id: fund_defensive
  name: "Fund Defensive"
  tier: mf_only
  archetype: fund_selection
  variant: defensive
  threshold_overrides:
    fund_avoid_aum_max_pct: 8
  state_filter: [investable]
  regime_stance: pause_risk_off
  position_sizing: equal_weight
  max_positions: 10
  max_sector_pct: 40.0
  lens_weights: {nav: 0.333, composition: 0.333, holdings: 0.334}
  rebalance_trigger: monthly
```

- [ ] **Step 3: Verify 15 YAML files exist**

```bash
ls atlas/simulation/strategies/configs/*.yaml | wc -l
```

Expected: `15`

- [ ] **Step 4: Commit**

```bash
git add atlas/simulation/strategies/configs/
git commit -m "feat(M7): 15 strategy YAML config files (5 stocks + 5 blend + 5 fund)"
```

---

## Task 8: loader.py + populate_strategy_configs()

**Files:**
- Create: `tests/unit/simulation/test_loader.py`
- Create: `atlas/simulation/strategies/loader.py`

- [ ] **Step 1: Write failing tests for loader**

```python
# tests/unit/simulation/test_loader.py
"""Unit tests for strategy config loader — validates YAML loading and seeding."""
from __future__ import annotations

import pytest
from atlas.simulation.strategies.loader import (
    StrategyConfig,
    load_all_configs,
    validate_config,
)


def test_load_all_configs_returns_15():
    configs = load_all_configs()
    assert len(configs) == 15, f"Expected 15, got {len(configs)}"


def test_load_all_configs_names_are_unique():
    configs = load_all_configs()
    names = [c.name for c in configs]
    assert len(names) == len(set(names)), "Duplicate strategy names found"


def test_each_config_has_required_fields():
    configs = load_all_configs()
    required = ["name", "tier", "archetype", "variant", "state_filter",
                "regime_stance", "max_positions"]
    for c in configs:
        for field in required:
            assert hasattr(c, field), f"Config {c.name} missing field {field}"


def test_invalid_tier_raises():
    with pytest.raises(ValueError, match="tier"):
        validate_config({"strategy": {
            "id": "bad", "name": "bad", "tier": "invalid_tier",
            "archetype": "x", "variant": "y", "state_filter": [],
            "regime_stance": "pause_risk_off", "max_positions": 10,
            "max_sector_pct": 40.0, "rebalance_trigger": "signal_change",
        }})


def test_valid_config_loads_without_error():
    validate_config({"strategy": {
        "id": "test", "name": "Test", "tier": "stocks_only",
        "archetype": "momentum_pure", "variant": "aggressive",
        "state_filter": ["leader"], "regime_stance": "pause_risk_off",
        "max_positions": 20, "max_sector_pct": 40.0,
        "rebalance_trigger": "signal_change",
        "threshold_overrides": {},
    }})
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/unit/simulation/test_loader.py -v
```

Expected: `FAILED` (ImportError)

- [ ] **Step 3: Implement loader.py**

```python
# atlas/simulation/strategies/loader.py
"""Loads strategy YAML configs and seeds atlas.strategy_configs DB table.

Deploy sequence: alembic upgrade head → populate_thresholds() → populate_strategy_configs()
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()

_CONFIGS_DIR = Path(__file__).parent / "configs"
_VALID_TIERS = {"stocks_only", "stocks_etf", "mf_only"}
_VALID_REGIME_STANCES = {"pause_risk_off", "scale_risk_off", "hold_risk_off"}


@dataclass
class StrategyConfig:
    name: str
    tier: str
    archetype: str
    variant: str
    config: dict[str, Any]  # full raw config
    state_filter: list[str] = field(default_factory=list)
    regime_stance: str = "pause_risk_off"
    position_sizing: str = "equal_weight"
    max_positions: int = 20
    max_sector_pct: float = 40.0
    rebalance_trigger: str = "signal_change"
    threshold_overrides: dict[str, float] = field(default_factory=dict)


def validate_config(raw: dict) -> StrategyConfig:
    """Validate raw YAML dict and return a StrategyConfig."""
    s = raw["strategy"]
    tier = s.get("tier", "")
    if tier not in _VALID_TIERS:
        raise ValueError(
            f"Invalid tier '{tier}'. Must be one of {_VALID_TIERS}"
        )
    stance = s.get("regime_stance", "pause_risk_off")
    if stance not in _VALID_REGIME_STANCES:
        raise ValueError(
            f"Invalid regime_stance '{stance}'. Must be one of {_VALID_REGIME_STANCES}"
        )
    return StrategyConfig(
        name=s["id"],
        tier=tier,
        archetype=s["archetype"],
        variant=s["variant"],
        config=s,
        state_filter=s.get("state_filter", ["leader"]),
        regime_stance=stance,
        position_sizing=s.get("position_sizing", "equal_weight"),
        max_positions=int(s.get("max_positions", 20)),
        max_sector_pct=float(s.get("max_sector_pct", 40.0)),
        rebalance_trigger=s.get("rebalance_trigger", "signal_change"),
        threshold_overrides=s.get("threshold_overrides", {}),
    )


def load_all_configs() -> list[StrategyConfig]:
    """Load and validate all 15 YAML strategy configs from configs/."""
    yamls = sorted(_CONFIGS_DIR.glob("*.yaml"))
    configs = []
    for yml in yamls:
        raw = yaml.safe_load(yml.read_text())
        configs.append(validate_config(raw))
    return configs


def populate_strategy_configs(engine: Engine | None = None) -> int:
    """Seed atlas.strategy_configs from configs/*.yaml. Idempotent.

    ON CONFLICT (name) DO UPDATE SET config, tier, archetype, variant, updated_at.
    Does NOT reset is_active — FM may have deactivated a strategy.
    Returns count of configs upserted (always 15 on a clean run).
    """
    eng = engine or get_engine()
    configs = load_all_configs()
    if len(configs) != 15:
        raise AssertionError(f"Expected 15 strategy configs, found {len(configs)}")

    sql = text("""
        INSERT INTO atlas.strategy_configs
            (name, tier, archetype, variant, config)
        VALUES (:name, :tier, :archetype, :variant, :config::jsonb)
        ON CONFLICT (name) DO UPDATE SET
            tier = EXCLUDED.tier,
            archetype = EXCLUDED.archetype,
            variant = EXCLUDED.variant,
            config = EXCLUDED.config,
            updated_at = now()
    """)

    with open_compute_session(eng) as conn:
        for c in configs:
            conn.execute(sql, {
                "name": c.name,
                "tier": c.tier,
                "archetype": c.archetype,
                "variant": c.variant,
                "config": json.dumps(c.config),
            })
        conn.commit()

    log.info("strategy_configs_seeded", count=len(configs))
    return len(configs)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/simulation/test_loader.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Seed the DB**

```bash
ssh jsl-wealth-server "cd atlas-os && python -c \"
from atlas.simulation.strategies.loader import populate_strategy_configs
n = populate_strategy_configs()
print(f'Seeded {n} strategy configs')
\""
```

Expected: `Seeded 15 strategy configs`

- [ ] **Step 6: Commit**

```bash
git add tests/unit/simulation/test_loader.py \
        atlas/simulation/strategies/loader.py
git commit -m "feat(M7): loader.py + populate_strategy_configs() — idempotent YAML → DB seed"
```

---

## Task 9: runner.py (nightly orchestration)

**Files:**
- Create: `atlas/simulation/strategies/runner.py`

- [ ] **Step 1: Create runner.py**

```python
# atlas/simulation/strategies/runner.py
"""Nightly paper trading runner — orchestrates all 15 strategies.

Calls fetch_decisions once per tier (3 DB reads total),
then loops strategies applying pure functions + writing results.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.simulation.core.overlap import jaccard_similarity, upper_triangle_pairs
from atlas.simulation.core.paper_trader import (
    MissingAtlasDecisionsError,
    apply_strategy_filter,
    check_decisions_exist,
    compute_trades,
    fetch_decisions,
    load_current_holdings,
    record_daily_performance,
    update_holdings,
    write_trades,
)
from atlas.simulation.strategies.loader import StrategyConfig, load_all_configs

log = structlog.get_logger()

_INIT_CASH = 10_000_000  # ₹1 crore notional per strategy


def _get_current_regime(conn: object, today: date) -> str:
    """Fetch today's regime_state from atlas_market_regime_daily."""
    row = conn.execute(
        text("""
            SELECT regime_state
            FROM atlas.atlas_market_regime_daily
            WHERE date = :d
            ORDER BY date DESC LIMIT 1
        """),
        {"d": today},
    ).fetchone()
    return row.regime_state if row else "Constructive"


def _get_today_prices(conn: object, instrument_ids: list[str], today: date) -> dict[str, float]:
    """Fetch close prices for instrument_ids from de_ohlcv_daily."""
    if not instrument_ids:
        return {}
    ids_csv = ", ".join(f"'{i}'" for i in instrument_ids)
    rows = conn.execute(
        text(f"""
            SELECT instrument_id, close FROM de_ohlcv_daily
            WHERE instrument_id IN ({ids_csv}) AND date = :d
        """),
        {"d": today},
    ).fetchall()
    return {r.instrument_id: float(r.close) for r in rows}


def _get_benchmark_return(conn: object, today: date) -> float | None:
    """Fetch Nifty500 daily return from atlas_benchmark_returns_cache."""
    row = conn.execute(
        text("""
            SELECT daily_return FROM atlas.atlas_benchmark_returns_cache
            WHERE benchmark_code = 'NIFTY500' AND date = :d
        """),
        {"d": today},
    ).fetchone()
    return float(row.daily_return) if row else None


def _get_strategy_id(conn: object, strategy_name: str) -> UUID | None:
    """Look up strategy UUID by name."""
    row = conn.execute(
        text("SELECT id FROM atlas.strategy_configs WHERE name = :n AND is_active = TRUE"),
        {"n": strategy_name},
    ).fetchone()
    return UUID(str(row.id)) if row else None


def run_paper_trading_pass(engine: Engine | None = None, today: date | None = None) -> dict:
    """Execute nightly paper trading pass for all 15 active strategies.

    Returns summary dict: {strategy_name: {'trades': int, 'holdings': int}}
    """
    eng = engine or get_engine()
    today = today or date.today()

    log.info("paper_trading_start", date=str(today))

    # Preflight: check decisions exist for all tiers
    for tier in ("stocks", "etf", "fund"):
        try:
            check_decisions_exist(eng, tier, today)
        except MissingAtlasDecisionsError as exc:
            log.error("paper_trading_preflight_failed", tier=tier, error=str(exc))
            raise

    configs = load_all_configs()

    with open_compute_session(eng) as conn:
        regime = _get_current_regime(conn, today)
        benchmark_return = _get_benchmark_return(conn, today)

        # Fetch decisions ONCE per tier — not once per strategy
        decisions_stocks = fetch_decisions(conn, "stocks", today)
        decisions_etf = fetch_decisions(conn, "etf", today)
        decisions_fund = fetch_decisions(conn, "fund", today)

    tier_decisions = {
        "stocks_only": decisions_stocks,
        "stocks_etf": (decisions_stocks, decisions_etf),
        "mf_only": decisions_fund,
    }

    summary = {}
    strategy_holdings: dict[str, set[str]] = {}  # for overlap calc

    for config in configs:
        with open_compute_session(eng) as conn:
            strategy_id = _get_strategy_id(conn, config.name)
            if strategy_id is None:
                log.warning("strategy_not_in_db", name=config.name)
                continue

            holdings = load_current_holdings(conn, strategy_id)

        # Select decisions for this tier
        if config.tier == "stocks_only":
            decisions = decisions_stocks
        elif config.tier == "mf_only":
            decisions = decisions_fund
        else:  # stocks_etf
            decisions = pd.concat([decisions_stocks, decisions_etf], ignore_index=True)

        entries, exits = apply_strategy_filter(decisions, config, config.threshold_overrides)
        trades = compute_trades(holdings, entries, exits, regime, config)

        # Get prices for instruments in trades
        all_instruments = list({t.instrument_id for t in trades} | set(holdings.keys()))
        with open_compute_session(eng) as conn:
            prices = _get_today_prices(conn, all_instruments, today)

        write_trades(eng, trades, strategy_id, today, regime, prices)
        update_holdings(eng, trades, strategy_id, today)

        # Recalculate portfolio value
        with open_compute_session(eng) as conn:
            updated_holdings = load_current_holdings(conn, strategy_id)

        total_value = sum(
            h.weight_pct / 100.0 * prices.get(inst, h.notional_value / (h.weight_pct / 100.0 or 1))
            for inst, h in updated_holdings.items()
        ) or _INIT_CASH

        prev_value = sum(h.notional_value for h in holdings.values()) or _INIT_CASH
        daily_return = (total_value - prev_value) / prev_value if prev_value else 0.0

        record_daily_performance(
            engine=eng,
            strategy_id=strategy_id,
            today=today,
            total_value=total_value,
            daily_return=daily_return,
            regime=regime,
            positions_count=len(updated_holdings),
            benchmark_nifty500=benchmark_return,
        )

        strategy_holdings[config.name] = set(updated_holdings.keys())
        summary[config.name] = {
            "trades": len(trades),
            "holdings": len(updated_holdings),
            "regime": regime,
        }
        log.info("strategy_complete", name=config.name, **summary[config.name])

    # Compute Jaccard overlap matrix (once, after all strategies processed)
    _write_overlap(eng, strategy_holdings, today, configs)

    log.info("paper_trading_complete", date=str(today), strategies=len(summary))
    return summary


def _write_overlap(
    engine: Engine,
    holdings: dict[str, set[str]],
    today: date,
    configs: list[StrategyConfig],
) -> None:
    """Compute and write 105-row overlap matrix for today."""
    # Build name → strategy_id mapping
    with open_compute_session(engine) as conn:
        id_map: dict[str, UUID] = {}
        for c in configs:
            sid = _get_strategy_id(conn, c.name)
            if sid:
                id_map[c.name] = sid

    ids = list(id_map.values())
    names = list(id_map.keys())
    pairs = upper_triangle_pairs(ids)

    rows = []
    for a_id, b_id in pairs:
        # Map back to names to look up holdings
        a_name = names[list(ids).index(a_id)]
        b_name = names[list(ids).index(b_id)]
        a_holds = holdings.get(a_name, set())
        b_holds = holdings.get(b_name, set())
        j = jaccard_similarity(a_holds, b_holds)
        common = len(a_holds & b_holds)
        rows.append((today, str(a_id), str(b_id), j, common))

    from atlas.compute._session import bulk_upsert
    bulk_upsert(
        engine=engine,
        table="atlas.strategy_overlap_daily",
        columns=["date", "strategy_a_id", "strategy_b_id", "jaccard_similarity", "common_instruments"],
        rows=rows,
        pk_columns=["date", "strategy_a_id", "strategy_b_id"],
    )
    log.info("overlap_written", pairs=len(rows), date=str(today))
```

- [ ] **Step 2: Commit**

```bash
git add atlas/simulation/strategies/runner.py
git commit -m "feat(M7): runner.py — nightly paper trading pass with per-tier decision fetch"
```

---

## Task 10: scripts/m7_daily.py + metrics.py

**Files:**
- Create: `atlas/simulation/core/metrics.py`
- Create: `scripts/m7_daily.py`

- [ ] **Step 1: Create metrics.py (regime-split P&L)**

```python
# atlas/simulation/core/metrics.py
"""Regime-split P&L analytics using empyrical-reloaded.

Receives pd.Series of daily returns (indexed by date).
Splits by atlas_market_regime_daily.regime_state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import empyrical as ep
import pandas as pd
import structlog

log = structlog.get_logger()


@dataclass
class RegimePerformance:
    regime: str
    sharpe: float | None
    total_return: float | None
    max_drawdown: float | None
    days_in_regime: int
    alpha_vs_nifty500: float | None
    alpha_vs_naive_atlas: float | None


def split_by_regime(
    portfolio_returns: pd.Series,    # daily returns, DatetimeIndex
    regime_history: pd.Series,       # date → regime_state (atlas_market_regime_daily.regime_state)
    benchmark_returns: pd.Series | None = None,
    naive_atlas_returns: pd.Series | None = None,
) -> dict[str, RegimePerformance]:
    """Split portfolio returns by market regime and compute per-regime metrics.

    Args:
        portfolio_returns: daily return series (float), DatetimeIndex
        regime_history: date → regime value ('Risk-On' | 'Constructive' | 'Cautious' | 'Risk-Off')
        benchmark_returns: Nifty500 daily returns for alpha computation
        naive_atlas_returns: naive Atlas baseline daily returns

    Returns:
        dict keyed by regime name.
    """
    result: dict[str, RegimePerformance] = {}

    # Align regime history to portfolio dates
    regime_aligned = regime_history.reindex(portfolio_returns.index)

    for regime_name in ["Risk-On", "Constructive", "Cautious", "Risk-Off"]:
        mask = regime_aligned == regime_name
        regime_returns = portfolio_returns[mask]

        if len(regime_returns) == 0:
            result[regime_name] = RegimePerformance(
                regime=regime_name,
                sharpe=None,
                total_return=None,
                max_drawdown=None,
                days_in_regime=0,
                alpha_vs_nifty500=None,
                alpha_vs_naive_atlas=None,
            )
            continue

        sharpe = ep.sharpe_ratio(regime_returns, annualization=252) if len(regime_returns) > 2 else None
        total_return = ep.cum_returns_final(regime_returns) if len(regime_returns) > 0 else None
        max_dd = ep.max_drawdown(regime_returns) if len(regime_returns) > 2 else None

        alpha_nifty = None
        if benchmark_returns is not None:
            bm = benchmark_returns.reindex(regime_returns.index).fillna(0)
            try:
                alpha_nifty, _ = ep.alpha_beta(regime_returns, bm, annualization=252)
            except Exception:
                pass

        alpha_naive = None
        if naive_atlas_returns is not None:
            na = naive_atlas_returns.reindex(regime_returns.index).fillna(0)
            try:
                alpha_naive, _ = ep.alpha_beta(regime_returns, na, annualization=252)
            except Exception:
                pass

        result[regime_name] = RegimePerformance(
            regime=regime_name,
            sharpe=float(sharpe) if sharpe is not None else None,
            total_return=float(total_return) if total_return is not None else None,
            max_drawdown=float(max_dd) if max_dd is not None else None,
            days_in_regime=len(regime_returns),
            alpha_vs_nifty500=float(alpha_nifty) if alpha_nifty is not None else None,
            alpha_vs_naive_atlas=float(alpha_naive) if alpha_naive is not None else None,
        )

    return result
```

- [ ] **Step 2: Create scripts/m7_daily.py**

```python
#!/usr/bin/env python3
"""Atlas M7 nightly paper trading script.

Called by the Atlas compute orchestration after m3_daily.py / m4_daily.py / m5_daily.py
complete successfully. Runs the 15-strategy paper trading pass for today.

Usage:
    python scripts/m7_daily.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import structlog

log = structlog.get_logger()


def main() -> int:
    parser = argparse.ArgumentParser(description="M7 nightly paper trading pass")
    parser.add_argument("--date", default=None, help="Override date (YYYY-MM-DD)")
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()

    from atlas.db import get_engine
    from atlas.simulation.core.signal_adapter import StaleJIPDataError, check_jip_staleness
    from atlas.simulation.strategies.runner import run_paper_trading_pass

    eng = get_engine()

    try:
        check_jip_staleness(eng, today)
    except StaleJIPDataError as exc:
        log.error("m7_daily_stale_jip", error=str(exc))
        return 1

    try:
        summary = run_paper_trading_pass(eng, today)
        log.info("m7_daily_complete", date=str(today), strategies=len(summary))
        for name, stats in summary.items():
            log.info("strategy_summary", name=name, **stats)
        return 0
    except Exception as exc:
        log.error("m7_daily_failed", error=str(exc), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Test the script dry-run (without executing the paper pass)**

```bash
ssh jsl-wealth-server "cd atlas-os && python scripts/m7_daily.py --help"
```

Expected: shows `--date` help text with no errors.

- [ ] **Step 4: Commit**

```bash
git add atlas/simulation/core/metrics.py scripts/m7_daily.py
git commit -m "feat(M7): metrics.py (regime-split P&L) + scripts/m7_daily.py (nightly runner)"
```

---

## Task 11: scripts/m7_seed_mock_data.py (unblock frontend dev)

**Files:**
- Create: `scripts/m7_seed_mock_data.py`

- [ ] **Step 1: Create mock data seeder**

```python
#!/usr/bin/env python3
"""Seed one week of synthetic paper performance data for frontend dev.

This is for DEVELOPMENT ONLY. Never run against production.
Purge with: DELETE FROM atlas.strategy_paper_performance WHERE created_at < now()
            (or re-run this script with --purge to delete its rows)

Usage:
    python scripts/m7_seed_mock_data.py [--purge]
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from uuid import UUID

import structlog

log = structlog.get_logger()

_REGIMES = ["Risk-On", "Constructive", "Cautious", "Risk-Off"]
_INIT_VALUE = 10_000_000  # ₹1 crore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purge", action="store_true", help="Remove seeded rows and exit")
    args = parser.parse_args()

    from atlas.db import get_engine
    from atlas.compute._session import open_compute_session, bulk_upsert
    from sqlalchemy import text

    eng = get_engine()

    if args.purge:
        with open_compute_session(eng) as conn:
            conn.execute(text(
                "DELETE FROM atlas.strategy_paper_performance WHERE positions_count = -999"
            ))
            conn.commit()
        log.info("mock_data_purged")
        return 0

    # Load strategy IDs
    with open_compute_session(eng) as conn:
        rows = conn.execute(
            text("SELECT id, name FROM atlas.strategy_configs WHERE is_active = TRUE")
        ).fetchall()

    if not rows:
        log.error("no_strategies_in_db — run populate_strategy_configs() first")
        return 1

    today = date.today()
    random.seed(42)
    perf_rows = []

    for row in rows:
        strategy_id = str(row.id)
        value = _INIT_VALUE
        for i in range(7):
            d = today - timedelta(days=7 - i)
            daily_ret = random.gauss(0.001, 0.012)
            value = value * (1 + daily_ret)
            perf_rows.append((
                strategy_id,
                d,
                round(value, 4),
                round(daily_ret, 6),
                round(random.gauss(0.0008, 0.010), 6),  # nifty500
                round(random.gauss(0.0009, 0.011), 6),  # naive atlas
                random.choice(_REGIMES),
                -999,  # sentinel to identify mock rows
            ))

    bulk_upsert(
        engine=eng,
        table="atlas.strategy_paper_performance",
        columns=[
            "strategy_id", "date", "total_value", "daily_return",
            "benchmark_nifty500_return", "benchmark_naive_atlas_return",
            "regime", "positions_count",
        ],
        rows=perf_rows,
        pk_columns=["strategy_id", "date"],
    )
    log.info("mock_data_seeded", rows=len(perf_rows), strategies=len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run against dev DB to verify**

```bash
ssh jsl-wealth-server "cd atlas-os && python scripts/m7_seed_mock_data.py"
```

Expected: `mock_data_seeded rows=105 strategies=15`

- [ ] **Step 3: Commit**

```bash
git add scripts/m7_seed_mock_data.py
git commit -m "feat(M7): m7_seed_mock_data.py — synthetic paper performance for frontend dev"
```

---

## Task 12: Integration tests

**Files:**
- Create: `tests/integration/simulation/test_paper_trader_integration.py`

- [ ] **Step 1: Create integration test**

```python
# tests/integration/simulation/test_paper_trader_integration.py
"""Integration tests for paper_trader — uses transaction-rollback fixture.

These tests hit the real DB (never persist data). They verify:
- MissingAtlasDecisionsError is raised for a future date with no decisions
- fetch_decisions returns a DataFrame with expected columns
- populate_strategy_configs seeded 15 rows

Run: pytest tests/integration/simulation/ -v --tb=short
Requires: real DB connection (run on EC2 or with VPN to Supabase)
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.simulation.core.paper_trader import MissingAtlasDecisionsError, check_decisions_exist, fetch_decisions
from atlas.simulation.strategies.loader import populate_strategy_configs
from atlas.compute._session import open_compute_session


@pytest.fixture(scope="module")
def engine():
    return get_engine()


def test_strategy_configs_seeded(engine):
    """populate_strategy_configs() produces 15 rows in the DB."""
    populate_strategy_configs(engine)
    with open_compute_session(engine) as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM atlas.strategy_configs WHERE is_active = TRUE")
        ).scalar()
    assert count == 15, f"Expected 15 strategy configs, got {count}"


def test_fetch_decisions_returns_dataframe(engine):
    """fetch_decisions for a recent date returns a non-empty DataFrame."""
    # Use a date 30 days ago (likely has decisions)
    test_date = date.today() - timedelta(days=30)
    with open_compute_session(engine) as conn:
        df = fetch_decisions(conn, "stocks", test_date)
    assert not df.empty, f"No stock decisions found for {test_date}"
    assert "instrument_id" in df.columns
    assert "rs_state" in df.columns
    assert "transition_trigger" in df.columns


def test_check_decisions_exist_raises_for_future_date(engine):
    """MissingAtlasDecisionsError raised for a date with no decisions."""
    future_date = date.today() + timedelta(days=365)
    with pytest.raises(MissingAtlasDecisionsError):
        check_decisions_exist(engine, "stocks", future_date)


def test_fetch_decisions_etf_returns_dataframe(engine):
    """fetch_decisions for ETF tier returns a DataFrame."""
    test_date = date.today() - timedelta(days=30)
    with open_compute_session(engine) as conn:
        df = fetch_decisions(conn, "etf", test_date)
    # ETF universe may be smaller but should not error
    assert "instrument_id" in df.columns
```

- [ ] **Step 2: Run integration tests on EC2**

```bash
ssh jsl-wealth-server "cd atlas-os && pytest tests/integration/simulation/ -v --tb=short"
```

Expected: `4 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/integration/simulation/__init__.py \
        tests/integration/simulation/test_paper_trader_integration.py
git commit -m "test(M7): integration tests for paper trader + strategy config seeding"
```

---

## Task 13: End-to-end smoke test (first real nightly run)

- [ ] **Step 1: Run the first nightly pass on EC2**

```bash
ssh jsl-wealth-server "cd atlas-os && python scripts/m7_daily.py --date $(date +%Y-%m-%d)"
```

Expected: logs show `paper_trading_complete strategies=15` and `overlap_written pairs=105`

- [ ] **Step 2: Verify rows in key tables**

```bash
ssh jsl-wealth-server "cd atlas-os && python -c \"
from atlas.db import get_engine
from sqlalchemy import text
from datetime import date
eng = get_engine()
today = date.today().isoformat()
with eng.connect() as conn:
    perf = conn.execute(text(f'SELECT COUNT(*) FROM atlas.strategy_paper_performance WHERE date = :d'), {'d': today}).scalar()
    trades = conn.execute(text(f'SELECT COUNT(*) FROM atlas.strategy_paper_trades WHERE trade_date = :d'), {'d': today}).scalar()
    overlap = conn.execute(text(f'SELECT COUNT(*) FROM atlas.strategy_overlap_daily WHERE date = :d'), {'d': today}).scalar()
    print(f'performance rows: {perf}')  # expect 15
    print(f'trade rows: {trades}')       # expect > 0
    print(f'overlap rows: {overlap}')   # expect 105
\""
```

Expected: `performance rows: 15`, `trade rows: (some number > 0)`, `overlap rows: 105`

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat(M7): Phase 1+2 complete — infrastructure + strategy engine running

All 8 migrations applied. 15 strategies seeded. First nightly paper trading
pass producing 15 performance rows and 105 overlap rows per night.

Phase 1+2 deliverables:
- Migrations 013-020 (8 M7 tables)
- signal_adapter.py, paper_trader.py, runner.py, metrics.py, overlap.py
- walk_forward.py with 547-day guard
- 15 strategy YAML configs + loader.py + populate_strategy_configs()
- scripts/m7_daily.py (nightly runner)
- scripts/m7_seed_mock_data.py (dev fixture)
- Unit tests: test_paper_trader, test_overlap, test_walk_forward, test_loader
- Integration tests: test_paper_trader_integration

Next: Phase 3 (Custom Portfolio Builder) and Phase 5 (Frontend) can proceed
in parallel. Phase 4 (Optimizer) requires 547 days of strategy performance data."
```

---

## Summary

Phase 1+2 complete when:
- [ ] All 8 migrations applied (`alembic upgrade head` succeeds)
- [ ] `populate_strategy_configs()` seeds 15 rows
- [ ] `python scripts/m7_daily.py` exits 0 and produces 15 performance rows + 105 overlap rows
- [ ] `pytest tests/unit/simulation/ -v` shows all unit tests passing
- [ ] `pytest tests/integration/simulation/ -v` shows all integration tests passing

**Next plans to write:**
- `2026-05-08-atlas-m7-phase3-portfolio-builder.md`
- `2026-05-08-atlas-m7-phase4-optimizer.md`
- `2026-05-08-atlas-m7-phase5-frontend.md`
