# Atlas State Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a state-defined engine of relative strength based instrument identification, with pure P+V inputs, stock as atomic element, and sector/MF/ETF/country views emerging bottom-up — replacing the empirically-broken state primitives surfaced by the 2026-05-18 state validator findings.

**Architecture:** One state classifier (`atlas/intelligence/states/classifier.py`) applies a rule-skeleton with IC-validated thresholds to OHLCV data, producing 7 states per (stock, day). Same classifier reused on sector/ETF/MF/country wrappers. Breadth-counting computes constituent state distributions. Dwell-tracking and urgency emerge from cohort baselines. Action engine maps state transitions to BUY/HOLD/TRIM/EXIT with within-state-rank-driven position sizing.

**Tech Stack:** Python 3.12, pandas, numpy, scipy, SQLAlchemy 2.0 async, alembic, postgres (atlas schema on Supabase), structlog, pandas-ta, pytest (+pytest-asyncio).

**Source spec:** [docs/superpowers/specs/2026-05-18-atlas-state-engine-design.md](../specs/2026-05-18-atlas-state-engine-design.md)

**Hard constraints:**
- File size limit: **400 LOC per source file** (pre-commit hook enforces; tighter than CLAUDE.md's 600).
- Decimal for money, tz-aware datetimes (global hooks enforce).
- All learned thresholds persisted to DB (`atlas_state_thresholds`), never hardcoded.
- No fundamentals. Pure P+V only.
- Coexist with V5; do not modify atlas/trading/lab.py's V5 behavior.
- Goal-post (`atlas-lab goal-post --rank 1`) must stay `met:true` throughout build.

---

## File Structure

```
atlas/intelligence/states/                          # NEW bounded context
├── __init__.py                                     # public exports
├── features.py             ~350 LOC                # derived metric calculators (SMA/EMA/ATR/OBV/RS-rank/breakouts/distribution days/breadth)
├── classifier.py           ~380 LOC                # 7-state rule application + within-state rank
├── dwell.py                ~200 LOC                # dwell_days + cohort baselines + urgency_score
├── aggregation.py          ~300 LOC                # sector/country breadth; ETF/MF direct + breadth
├── actions.py              ~250 LOC                # state-transition → action mapping + risk gates
├── thresholds.py           ~150 LOC                # load active θ from atlas_state_thresholds
├── threshold_optimizer.py  ~300 LOC                # IC-validation grid sweep + persistence
├── persistence.py          ~200 LOC                # writes atlas_stock_state_daily + action log
└── cohorts.py              ~100 LOC                # cohort key derivation (large/mid/small/sector)

tests/intelligence/states/                          # mirrors atlas/intelligence/states/
├── __init__.py
├── test_features.py
├── test_classifier.py
├── test_dwell.py
├── test_aggregation.py
├── test_actions.py
├── test_thresholds.py
├── test_threshold_optimizer.py
├── test_persistence.py
├── test_cohorts.py
└── conftest.py             # synthetic OHLCV fixtures + cohort fixtures

migrations/versions/
├── 072_atlas_stock_state_daily.py
├── 073_atlas_state_dwell_statistics.py
├── 074_atlas_state_thresholds.py
├── 075_atlas_state_action_log.py
└── 076_seed_initial_state_thresholds.py

atlas/trading/cli.py                                # MODIFY: add `atlas-lab states` subcommands
                                                    #   states classify --start YYYY-MM-DD --end YYYY-MM-DD
                                                    #   states tune --as-of YYYY-MM-DD
                                                    #   states aggregate --as-of YYYY-MM-DD
                                                    #   states recommend --date YYYY-MM-DD
```

Code that DOES NOT change in this plan:
- `atlas/trading/lab.py` — V5 stays as-is. State engine is a separate strategy.
- `atlas/trading/goal_post.py` — engine-agnostic; reads from leaderboard regardless of producer.
- `atlas/intelligence/validation/ic_engine.py`, `forward_returns.py`, `persistence.py` — reused as-is.
- Existing `atlas_stock_states_daily` table — stays alive for backwards-compat.

---

# PHASE 0 — Pre-build (1 week)

Sets up DB schema and seed data so Phase 1 can write.

### Task 0.1: Migration 072 — atlas_stock_state_daily

**Files:**
- Create: `migrations/versions/072_atlas_stock_state_daily.py`
- Test: `tests/migrations/test_072_state_daily.py`

- [ ] **Step 1: Write the failing migration test**

```python
# tests/migrations/test_072_state_daily.py
from sqlalchemy import create_engine, text
import pytest

def test_atlas_stock_state_daily_columns_present(db_engine):
    """Migration 072 creates the table with all required columns."""
    with db_engine.connect() as c:
        cols = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='atlas' AND table_name='atlas_stock_state_daily'
        """)).fetchall()
    names = {r[0] for r in cols}
    required = {
        "instrument_id","date","state","prior_state","state_since_date",
        "dwell_days","dwell_percentile","urgency_score","within_state_rank",
        "rs_rank_12m","close_vs_sma_50","close_vs_sma_150","close_vs_sma_200",
        "sma_200_slope","volume_ratio_50d","distribution_days",
        "classifier_version","created_at",
    }
    missing = required - names
    assert not missing, f"missing columns: {missing}"

def test_atlas_stock_state_daily_check_constraints(db_engine):
    """State + urgency_score values are constrained."""
    with db_engine.connect() as c:
        with pytest.raises(Exception, match="ck_state_value"):
            c.execute(text(
                "INSERT INTO atlas.atlas_stock_state_daily "
                "(instrument_id, date, state, state_since_date, dwell_days, urgency_score, classifier_version) "
                "VALUES (gen_random_uuid(), '2026-01-01', 'bogus_state', '2026-01-01', 0, 'normal', 'v1')"
            ))
            c.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/migrations/test_072_state_daily.py -v`
Expected: FAIL — table doesn't exist yet.

- [ ] **Step 3: Write the migration**

```python
# migrations/versions/072_atlas_stock_state_daily.py
"""State Engine — per-stock daily state classification.

Revision ID: 072
Revises: 071
Create Date: 2026-05-18
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_stock_state_daily",
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("prior_state", sa.String(length=24), nullable=True),
        sa.Column("state_since_date", sa.Date(), nullable=False),
        sa.Column("dwell_days", sa.Integer(), nullable=False),
        sa.Column("dwell_percentile", sa.Numeric(5, 4), nullable=True),
        sa.Column("urgency_score", sa.String(length=12), nullable=False),
        sa.Column("within_state_rank", sa.Numeric(5, 4), nullable=True),
        sa.Column("rs_rank_12m", sa.Numeric(5, 4), nullable=True),
        sa.Column("close_vs_sma_50", sa.Numeric(8, 4), nullable=True),
        sa.Column("close_vs_sma_150", sa.Numeric(8, 4), nullable=True),
        sa.Column("close_vs_sma_200", sa.Numeric(8, 4), nullable=True),
        sa.Column("sma_200_slope", sa.Numeric(8, 6), nullable=True),
        sa.Column("volume_ratio_50d", sa.Numeric(6, 3), nullable=True),
        sa.Column("distribution_days", sa.Integer(), nullable=True),
        sa.Column("classifier_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id", "date"),
        sa.CheckConstraint(
            "state IN ('uninvestable','stage_1','stage_2a','stage_2b','stage_2c','stage_3','stage_4')",
            name="ck_state_value",
        ),
        sa.CheckConstraint(
            "urgency_score IN ('urgent','normal','late','n/a')",
            name="ck_urgency_value",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_stock_state_daily_date",
        "atlas_stock_state_daily", ["date"], schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_stock_state_daily_date_state",
        "atlas_stock_state_daily", ["date", "state"], schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_atlas_stock_state_daily_date_state",
                  table_name="atlas_stock_state_daily", schema=_SCHEMA)
    op.drop_index("ix_atlas_stock_state_daily_date",
                  table_name="atlas_stock_state_daily", schema=_SCHEMA)
    op.drop_table("atlas_stock_state_daily", schema=_SCHEMA)
```

- [ ] **Step 4: Apply + test**

```bash
.venv/bin/alembic upgrade head
pytest tests/migrations/test_072_state_daily.py -v
```
Expected: PASS on both tests.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/072_atlas_stock_state_daily.py tests/migrations/test_072_state_daily.py
git commit -m "feat(states): migration 072 — atlas_stock_state_daily"
```

### Task 0.2: Migration 073 — atlas_state_dwell_statistics

**Files:**
- Create: `migrations/versions/073_atlas_state_dwell_statistics.py`
- Test: `tests/migrations/test_073_dwell_statistics.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dwell_statistics_table_exists(db_engine):
    with db_engine.connect() as c:
        cols = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='atlas' AND table_name='atlas_state_dwell_statistics'
        """)).fetchall()
    required = {"cohort_key","state","mean_dwell_days","median_dwell_days",
                "p25_dwell_days","p75_dwell_days","p95_dwell_days",
                "n_observations","as_of_date","refreshed_at"}
    assert required <= {r[0] for r in cols}
```

- [ ] **Step 2: Run + fail.** `pytest tests/migrations/test_073_dwell_statistics.py -v`

- [ ] **Step 3: Write migration**

```python
revision = "073"
down_revision = "072"

def upgrade() -> None:
    op.create_table(
        "atlas_state_dwell_statistics",
        sa.Column("cohort_key", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("mean_dwell_days", sa.Numeric(8, 2), nullable=True),
        sa.Column("median_dwell_days", sa.Integer(), nullable=True),
        sa.Column("p25_dwell_days", sa.Integer(), nullable=True),
        sa.Column("p75_dwell_days", sa.Integer(), nullable=True),
        sa.Column("p95_dwell_days", sa.Integer(), nullable=True),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("cohort_key", "state", "as_of_date"),
        schema=_SCHEMA,
    )

def downgrade() -> None:
    op.drop_table("atlas_state_dwell_statistics", schema=_SCHEMA)
```

- [ ] **Step 4: Apply + test pass.** `alembic upgrade head && pytest tests/migrations/test_073_dwell_statistics.py -v`

- [ ] **Step 5: Commit.**

```bash
git add migrations/versions/073_atlas_state_dwell_statistics.py tests/migrations/test_073_dwell_statistics.py
git commit -m "feat(states): migration 073 — atlas_state_dwell_statistics"
```

### Task 0.3: Migration 074 — atlas_state_thresholds

**Files:**
- Create: `migrations/versions/074_atlas_state_thresholds.py`
- Test: `tests/migrations/test_074_thresholds.py`

- [ ] **Step 1: Test.** Same pattern as Task 0.1/0.2: check columns, check constraints. Required columns: `threshold_name, state_or_gate, threshold_value, ic_at_threshold, ic_ir_at_threshold, q5_q1_spread, as_of_date, active, tuned_at`.

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write migration**

```python
revision = "074"
down_revision = "073"

def upgrade() -> None:
    op.create_table(
        "atlas_state_thresholds",
        sa.Column("threshold_name", sa.String(length=64), nullable=False),
        sa.Column("state_or_gate", sa.String(length=24), nullable=False),
        sa.Column("threshold_value", sa.Numeric(12, 6), nullable=False),
        sa.Column("ic_at_threshold", sa.Numeric(8, 4), nullable=True),
        sa.Column("ic_ir_at_threshold", sa.Numeric(8, 4), nullable=True),
        sa.Column("q5_q1_spread", sa.Numeric(8, 4), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("tuned_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("threshold_name", "state_or_gate", "as_of_date"),
        schema=_SCHEMA,
    )
    # Partial unique index: only one row per (threshold_name, state_or_gate) may have active=true
    op.execute("""
        CREATE UNIQUE INDEX uq_state_thresholds_active
          ON atlas.atlas_state_thresholds (threshold_name, state_or_gate)
          WHERE active = TRUE
    """)

def downgrade() -> None:
    op.drop_index("uq_state_thresholds_active",
                  table_name="atlas_state_thresholds", schema=_SCHEMA)
    op.drop_table("atlas_state_thresholds", schema=_SCHEMA)
```

- [ ] **Step 4: Apply + test pass.**

- [ ] **Step 5: Commit.**

### Task 0.4: Migration 075 — atlas_state_action_log

**Files:**
- Create: `migrations/versions/075_atlas_state_action_log.py`
- Test: `tests/migrations/test_075_action_log.py`

- [ ] **Step 1: Test.** Required columns: `instrument_id, date, transition, action, suppressed_by, position_size, within_state_rank, urgency_score, created_at`. Action CHECK: `BUY|HOLD|TRIM|EXIT|WATCH|FORCE_EXIT`.

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write migration**

```python
revision = "075"
down_revision = "074"

def upgrade() -> None:
    op.create_table(
        "atlas_state_action_log",
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("transition", sa.String(length=48), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("suppressed_by", sa.String(length=32), nullable=True),
        sa.Column("position_size", sa.Numeric(8, 4), nullable=True),
        sa.Column("within_state_rank", sa.Numeric(5, 4), nullable=True),
        sa.Column("urgency_score", sa.String(length=12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id", "date", "transition"),
        sa.CheckConstraint(
            "action IN ('BUY','HOLD','TRIM','EXIT','WATCH','FORCE_EXIT')",
            name="ck_action_value",
        ),
        schema=_SCHEMA,
    )

def downgrade() -> None:
    op.drop_table("atlas_state_action_log", schema=_SCHEMA)
```

- [ ] **Step 4-5: Apply + test + commit.**

### Task 0.5: Migration 076 — seed initial threshold defaults

**Files:**
- Create: `migrations/versions/076_seed_initial_state_thresholds.py`
- Test: `tests/migrations/test_076_seed.py`

These are the hand-set defensible defaults. They get IC-tuned in Phase 2 but Phase 1 needs them to run.

- [ ] **Step 1: Write the test**

```python
def test_initial_thresholds_seeded(db_engine):
    with db_engine.connect() as c:
        rows = c.execute(text("""
            SELECT threshold_name, state_or_gate, threshold_value
            FROM atlas.atlas_state_thresholds
            WHERE active = TRUE
            ORDER BY state_or_gate, threshold_name
        """)).fetchall()
    assert len(rows) >= 12, "should seed at least 12 active thresholds across the 7 states + risk gates"
    # Spot-check a few
    expected = {
        ("theta_rs", "stage_2a"): 70.0,
        ("theta_vol_mult", "stage_2a"): 1.5,
        ("theta_fresh_days", "stage_2a"): 21,
        ("theta_confirmed_days", "stage_2b"): 126,
        ("theta_distribution", "stage_3"): 5,
    }
    actual = {(r.threshold_name, r.state_or_gate): float(r.threshold_value) for r in rows}
    for key, val in expected.items():
        assert key in actual, f"missing threshold: {key}"
        assert abs(actual[key] - val) < 1e-6, f"{key}: expected {val}, got {actual[key]}"
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write migration**

```python
revision = "076"
down_revision = "075"

_SEED = [
    # (threshold_name, state_or_gate, value)
    # Uninvestable
    ("theta_liq", "uninvestable", 100000.0),       # min 50d avg ₹ volume
    ("theta_gap", "uninvestable", 20),              # max missing trading days in 252d
    ("theta_min_price", "uninvestable", 10.0),      # min close price
    # Stage 1
    ("theta_base_tightness", "stage_1", 0.10),
    ("theta_low_vol", "stage_1", 0.035),
    ("theta_min_recovery_days", "stage_1", 30),
    # Stage 2A
    ("theta_slope_days", "stage_2a", 30),
    ("theta_base_breakout", "stage_2a", 1.02),
    ("theta_vol_mult", "stage_2a", 1.5),
    ("theta_rs", "stage_2a", 70.0),
    ("theta_fresh_days", "stage_2a", 21),
    # Stage 2B
    ("theta_confirmed_days", "stage_2b", 126),
    # Stage 2C
    ("theta_extension", "stage_2c", 1.10),
    ("theta_atr_expansion", "stage_2c", 1.40),
    # Stage 3
    ("theta_distribution", "stage_3", 5),
    # Stage 4
    ("theta_decline_floor", "stage_4", 0.90),
    # Risk gates
    ("theta_dd_halt", "risk_gate", 15.0),           # halt entries when portfolio DD >= 15%
    ("theta_sector_cap", "risk_gate", 5),           # max stocks per sector
]

def upgrade() -> None:
    today = sa.func.current_date()
    for tname, sg, val in _SEED:
        op.execute(sa.text(
            "INSERT INTO atlas.atlas_state_thresholds "
            "(threshold_name, state_or_gate, threshold_value, as_of_date, active) "
            "VALUES (:tn, :sg, :v, CURRENT_DATE, TRUE) "
            "ON CONFLICT (threshold_name, state_or_gate, as_of_date) DO NOTHING"
        ).bindparams(tn=tname, sg=sg, v=val))

def downgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM atlas.atlas_state_thresholds WHERE active = TRUE"
    ))
```

- [ ] **Step 4: Apply + test pass.**

- [ ] **Step 5: Commit.**

```bash
git add migrations/versions/076_seed_initial_state_thresholds.py tests/migrations/test_076_seed.py
git commit -m "feat(states): seed initial defensible threshold defaults"
```

---

# PHASE 1 — Classifier MVP (2 weeks)

### Task 1.1: features.py — derived metric calculators

**Files:**
- Create: `atlas/intelligence/states/__init__.py`
- Create: `atlas/intelligence/states/features.py`
- Create: `tests/intelligence/states/__init__.py`
- Create: `tests/intelligence/states/conftest.py`
- Create: `tests/intelligence/states/test_features.py`

- [ ] **Step 1: Write conftest fixtures**

```python
# tests/intelligence/states/conftest.py
import numpy as np
import pandas as pd
import pytest

@pytest.fixture
def trending_up_ohlcv() -> pd.DataFrame:
    """500 trading days of a steadily uptrending stock."""
    rng = np.random.default_rng(42)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="B").date
    drift = 0.0012  # ~30% annual
    shocks = rng.normal(0, 0.012, n)
    close = 100.0 * np.cumprod(1 + drift + shocks)
    return pd.DataFrame({
        "date": dates, "open": close * 0.998, "high": close * 1.012,
        "low": close * 0.988, "close": close,
        "volume": rng.integers(50_000, 200_000, n),
    })

@pytest.fixture
def benchmark_ohlcv() -> pd.DataFrame:
    """500 trading days of benchmark (gentle uptrend)."""
    rng = np.random.default_rng(7)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="B").date
    close = 10_000.0 * np.cumprod(1 + 0.0004 + rng.normal(0, 0.008, n))
    return pd.DataFrame({
        "date": dates, "open": close, "high": close, "low": close,
        "close": close, "volume": np.zeros(n, dtype=int),
    })
```

- [ ] **Step 2: Write the failing test**

```python
# tests/intelligence/states/test_features.py
import numpy as np
import pandas as pd
from atlas.intelligence.states.features import (
    sma, atr_14, distribution_days_25d, percent_off_52w_high,
    up_down_volume_ratio_50d, base_depth, base_length,
)

def test_sma_50(trending_up_ohlcv):
    s = sma(trending_up_ohlcv["close"], 50)
    assert s.iloc[:49].isna().all()
    assert not np.isnan(s.iloc[49])
    # SMA should be below current price in an uptrend after 60+ days
    assert s.iloc[60] < trending_up_ohlcv["close"].iloc[60]

def test_atr_14_positive(trending_up_ohlcv):
    a = atr_14(trending_up_ohlcv["high"], trending_up_ohlcv["low"], trending_up_ohlcv["close"])
    assert a.iloc[:13].isna().all()
    assert (a.iloc[14:].dropna() > 0).all()

def test_distribution_days_window_25d(trending_up_ohlcv):
    # On a clean uptrend with random low volume, distribution days should mostly be 0
    dd = distribution_days_25d(trending_up_ohlcv["close"], trending_up_ohlcv["volume"])
    assert dd.iloc[25:].max() <= 25

def test_percent_off_52w_high(trending_up_ohlcv):
    pct = percent_off_52w_high(trending_up_ohlcv["close"])
    # In an uptrend, % off high should mostly be small (within 0-25%)
    assert pct.iloc[252:].mean() < 0.25
```

- [ ] **Step 3: Run + fail.** `pytest tests/intelligence/states/test_features.py -v` → ImportError.

- [ ] **Step 4: Write features.py**

```python
# atlas/intelligence/states/features.py
"""Derived metric calculators for the state classifier.

Pure functions of OHLCV (price + volume). No I/O. All return pandas Series
indexed identically to input. NaN where the rolling window isn't full.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average over `window` periods."""
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average (span = span periods)."""
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def slope(series: pd.Series, window: int) -> pd.Series:
    """Linear regression slope of `series` over `window` periods.

    Returned in 'fractional change per period' units (multiply by window to get
    'fractional change over the window').
    """
    def _fit(arr: np.ndarray) -> float:
        if np.isnan(arr).any():
            return float("nan")
        x = np.arange(len(arr), dtype=float)
        return float(np.polyfit(x, arr, 1)[0]) / arr.mean() if arr.mean() else 0.0
    return series.rolling(window, min_periods=window).apply(_fit, raw=True)


def atr_14(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Average true range over 14 periods."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(14, min_periods=14).mean()


def distribution_days_25d(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Count distribution days in trailing 25 trading days.

    A 'distribution day' = close down >= 0.2% AND volume > previous day's volume.
    """
    daily_ret = close.pct_change()
    vol_up = volume > volume.shift(1)
    is_dd = (daily_ret <= -0.002) & vol_up
    return is_dd.rolling(25, min_periods=1).sum().astype("Int64")


def percent_off_52w_high(close: pd.Series) -> pd.Series:
    """(52w_high - close) / 52w_high — 0 means at high, 0.3 means 30% off."""
    high_252 = close.rolling(252, min_periods=252).max()
    return (high_252 - close) / high_252


def percent_off_52w_low(close: pd.Series) -> pd.Series:
    """(close - 52w_low) / 52w_low."""
    low_252 = close.rolling(252, min_periods=252).min()
    return (close - low_252) / low_252


def up_down_volume_ratio_50d(close: pd.Series, volume: pd.Series) -> pd.Series:
    """sum(volume on up-days) / sum(volume on down-days), trailing 50 days."""
    daily_ret = close.pct_change()
    up_vol = volume.where(daily_ret > 0, 0.0)
    down_vol = volume.where(daily_ret < 0, 0.0)
    up_sum = up_vol.rolling(50, min_periods=50).sum()
    down_sum = down_vol.rolling(50, min_periods=50).sum()
    return up_sum / down_sum.replace(0, np.nan)


def base_depth(close: pd.Series, window: int = 60) -> pd.Series:
    """Depth of current base = (highest_window - lowest_window) / highest_window.

    Small values (<0.15) indicate tight consolidation = good Stage 1 base.
    """
    high_w = close.rolling(window, min_periods=window).max()
    low_w = close.rolling(window, min_periods=window).min()
    return (high_w - low_w) / high_w


def base_length(close: pd.Series, threshold: float = 0.15) -> pd.Series:
    """Number of trailing days that the price has stayed within `threshold`
    of the trailing 60d high. Long base = high value."""
    high_60 = close.rolling(60, min_periods=60).max()
    within = (close / high_60) > (1 - threshold)
    # rolling sum of consecutive 'within' days
    # reset counter when within becomes False
    grp = (~within).cumsum()
    return within.groupby(grp).cumsum().astype("Int64")


def rs_rank_12m(stock_close: pd.Series, universe_returns: pd.DataFrame) -> pd.Series:
    """12-month total return ranked cross-sectionally against universe.

    universe_returns: DataFrame indexed by date, columns are instrument_ids,
    values are 12m total returns.
    stock_close: this stock's close series, same date index.

    Returns 0..1 percentile rank (1 = top performer in universe).
    """
    stock_12m = stock_close / stock_close.shift(252) - 1
    # For each date, rank stock's 12m return against universe
    ranks = pd.Series(index=stock_close.index, dtype=float)
    for dt in stock_close.index:
        if dt not in universe_returns.index:
            ranks.loc[dt] = float("nan")
            continue
        universe_day = universe_returns.loc[dt].dropna()
        if len(universe_day) < 10 or pd.isna(stock_12m.loc[dt]):
            ranks.loc[dt] = float("nan")
            continue
        rank = (universe_day < stock_12m.loc[dt]).sum() / len(universe_day)
        ranks.loc[dt] = rank
    return ranks


def breadth_above_ma(universe_closes: pd.DataFrame, ma_window: int) -> pd.Series:
    """% of universe above their `ma_window`-period SMA, per date.

    universe_closes: DataFrame indexed by date, columns are instrument_ids.
    Returns Series indexed by date, values in 0..1.
    """
    ma = universe_closes.rolling(ma_window, min_periods=ma_window).mean()
    above = (universe_closes > ma).astype(float)
    return above.mean(axis=1, skipna=True)
```

- [ ] **Step 5: Run tests pass.** `pytest tests/intelligence/states/test_features.py -v`

- [ ] **Step 6: Commit.**

```bash
git add atlas/intelligence/states/features.py tests/intelligence/states/ \
        atlas/intelligence/states/__init__.py
git commit -m "feat(states): features.py — pure-P+V metric calculators with tests"
```

### Task 1.2: cohorts.py — cohort key derivation

**Files:**
- Create: `atlas/intelligence/states/cohorts.py`
- Create: `tests/intelligence/states/test_cohorts.py`

- [ ] **Step 1: Test**

```python
# tests/intelligence/states/test_cohorts.py
from atlas.intelligence.states.cohorts import cohort_for_stock

def test_cohort_large_cap_by_nifty_100():
    """Stock in Nifty 100 → large_cap cohort regardless of sector."""
    assert cohort_for_stock(in_nifty_100=True, in_nifty_500=True, sector="IT") == "large_cap"

def test_cohort_mid_cap():
    """Stock in Nifty 500 but not Nifty 100 → mid_cap."""
    assert cohort_for_stock(in_nifty_100=False, in_nifty_500=True, sector="IT") == "mid_cap"

def test_cohort_small_cap():
    """Stock outside Nifty 500 → small_cap."""
    assert cohort_for_stock(in_nifty_100=False, in_nifty_500=False, sector="IT") == "small_cap"

def test_cohort_sector_key_orthogonal():
    """Sector cohort is a separate axis."""
    from atlas.intelligence.states.cohorts import sector_cohort_key
    assert sector_cohort_key("Information Technology") == "sector_information_technology"
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write cohorts.py**

```python
# atlas/intelligence/states/cohorts.py
"""Cohort key derivation for dwell baselines.

Two orthogonal cohort axes:
  - market_cap: large_cap / mid_cap / small_cap (from Nifty index membership)
  - sector: per-sector key (lowercased + underscored)
"""
from __future__ import annotations


def cohort_for_stock(in_nifty_100: bool, in_nifty_500: bool, sector: str) -> str:
    """Map index-membership flags to market-cap cohort."""
    if in_nifty_100:
        return "large_cap"
    if in_nifty_500:
        return "mid_cap"
    return "small_cap"


def sector_cohort_key(sector_name: str | None) -> str:
    """Normalize sector name to a cohort key."""
    if not sector_name:
        return "sector_unknown"
    normalized = sector_name.lower().replace(" ", "_").replace("-", "_")
    return f"sector_{normalized}"
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.3: thresholds.py — load active θ from DB

**Files:**
- Create: `atlas/intelligence/states/thresholds.py`
- Create: `tests/intelligence/states/test_thresholds.py`

- [ ] **Step 1: Test**

```python
from atlas.intelligence.states.thresholds import load_active_thresholds, ThresholdValue

def test_load_active_thresholds_returns_dict(db_engine):
    thresholds = load_active_thresholds(db_engine)
    assert isinstance(thresholds, dict)
    # After migration 076 seed: stage_2a has theta_rs=70
    assert ("theta_rs", "stage_2a") in thresholds
    assert thresholds[("theta_rs", "stage_2a")].value == 70.0

def test_thresholds_only_active(db_engine):
    """Only rows with active=TRUE are returned."""
    thresholds = load_active_thresholds(db_engine)
    # The seed creates 18 active rows
    assert len(thresholds) >= 18
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write thresholds.py**

```python
# atlas/intelligence/states/thresholds.py
"""Load active threshold values from atlas.atlas_state_thresholds.

The classifier never hardcodes thresholds. Every θ comes from the DB.
The threshold optimizer (Phase 2) writes new values; the classifier reads
the active row per (threshold_name, state_or_gate).
"""
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ThresholdValue:
    value: float
    ic_at_threshold: float | None
    ic_ir_at_threshold: float | None


def load_active_thresholds(engine: Engine) -> dict[tuple[str, str], ThresholdValue]:
    """Return {(threshold_name, state_or_gate): ThresholdValue} for all active rows."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT threshold_name, state_or_gate, threshold_value,
                   ic_at_threshold, ic_ir_at_threshold
            FROM atlas.atlas_state_thresholds
            WHERE active = TRUE
        """)).fetchall()
    return {
        (r.threshold_name, r.state_or_gate): ThresholdValue(
            value=float(r.threshold_value),
            ic_at_threshold=float(r.ic_at_threshold) if r.ic_at_threshold else None,
            ic_ir_at_threshold=float(r.ic_ir_at_threshold) if r.ic_ir_at_threshold else None,
        )
        for r in rows
    }


def get(thresholds: dict, name: str, state: str, default: float | None = None) -> float:
    """Convenience: thresholds[name, state].value or default."""
    key = (name, state)
    if key in thresholds:
        return thresholds[key].value
    if default is None:
        raise KeyError(f"missing threshold: {key}")
    return default
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.4: classifier.py — Uninvestable + Stage 4

Build classifier state-by-state. Start with the simplest (Uninvestable filter) and the structurally-similar Stage 4.

**Files:**
- Create: `atlas/intelligence/states/classifier.py`
- Create: `tests/intelligence/states/test_classifier.py`

- [ ] **Step 1: Test (Uninvestable + Stage 4)**

```python
from atlas.intelligence.states.classifier import classify_uninvestable, classify_stage_4

def test_uninvestable_low_liquidity():
    """50d avg ₹ volume below θ_liq → uninvestable."""
    is_uninv = classify_uninvestable(
        liquidity_score=50_000,    # ₹50k/day — below 100k threshold
        data_gap_count=0,
        close=100.0,
        thresholds={
            ("theta_liq", "uninvestable"): 100_000,
            ("theta_gap", "uninvestable"): 20,
            ("theta_min_price", "uninvestable"): 10.0,
        },
    )
    assert is_uninv is True

def test_uninvestable_healthy_stock():
    is_uninv = classify_uninvestable(
        liquidity_score=500_000, data_gap_count=2, close=300.0,
        thresholds={
            ("theta_liq", "uninvestable"): 100_000,
            ("theta_gap", "uninvestable"): 20,
            ("theta_min_price", "uninvestable"): 10.0,
        },
    )
    assert is_uninv is False

def test_stage_4_downtrend():
    """close < SMA_150 < SMA_200, SMA_150 sloping down → Stage 4."""
    is_s4 = classify_stage_4(
        close=80.0, sma_150=100.0, sma_200=110.0,
        sma_150_slope=-0.01,
        thresholds={("theta_decline_floor", "stage_4"): 0.90},
    )
    assert is_s4 is True

def test_stage_4_negated_by_uptrend_ma():
    is_s4 = classify_stage_4(
        close=120.0, sma_150=110.0, sma_200=100.0, sma_150_slope=0.01,
        thresholds={("theta_decline_floor", "stage_4"): 0.90},
    )
    assert is_s4 is False
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write classifier.py (this task: Uninvestable + Stage 4 only)**

```python
# atlas/intelligence/states/classifier.py
"""State classifier — applies rule-skeleton with DB-loaded θ thresholds.

Public API:
  classify_state_panel(features_df, thresholds) -> DataFrame(date, instrument_id, state, ...)

Each state has its own predicate (classify_uninvestable, classify_stage_4, etc.).
The orchestrator (classify_state_panel) calls them in priority order and assigns
the first matching state.
"""
from __future__ import annotations

from atlas.intelligence.states.thresholds import get as get_threshold


def classify_uninvestable(
    liquidity_score: float, data_gap_count: int, close: float, thresholds: dict
) -> bool:
    """Filter: stock unsuitable for trading. Returns True if uninvestable."""
    if liquidity_score < get_threshold(thresholds, "theta_liq", "uninvestable"):
        return True
    if data_gap_count > get_threshold(thresholds, "theta_gap", "uninvestable"):
        return True
    if close < get_threshold(thresholds, "theta_min_price", "uninvestable"):
        return True
    return False


def classify_stage_4(
    close: float, sma_150: float, sma_200: float, sma_150_slope: float,
    thresholds: dict,
) -> bool:
    """Stage 4 (Decline): close < SMA_150 < SMA_200, SMA_150 sloping down."""
    if any(v is None or v != v for v in (close, sma_150, sma_200, sma_150_slope)):
        return False
    floor = get_threshold(thresholds, "theta_decline_floor", "stage_4")
    return (
        close < sma_150 < sma_200
        and sma_150_slope < 0
        and close < floor * sma_200
    )
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.5: classifier.py — Stage 1, Stage 2A, 2B, 2C, Stage 3

Continue building state classifiers. Tests follow the same pattern as 1.4 — positive case (state holds), negative case (it doesn't).

**Files:**
- Modify: `atlas/intelligence/states/classifier.py`
- Modify: `tests/intelligence/states/test_classifier.py`

- [ ] **Step 1: Tests for each state** — one positive + one negative per state (Stage 1, 2A, 2B, 2C, 3). Same pattern as Task 1.4.

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Add classifier functions**

```python
# atlas/intelligence/states/classifier.py (additions)

def classify_stage_1(
    close: float, sma_150: float, atr_14: float, low_252_age_days: int,
    thresholds: dict,
) -> bool:
    """Stage 1 (Base): consolidation. NOT in Stage 2/3/4; tight basing.

    NOTE: caller is responsible for testing that the stock is NOT already in
    Stage 2, 3, or 4 before calling this. Stage 1 is the residual.
    """
    if any(v != v for v in (close, sma_150, atr_14)):
        return False
    tightness = abs(close - sma_150) / sma_150 if sma_150 > 0 else 1.0
    low_vol = atr_14 / close if close > 0 else 1.0
    return (
        tightness < get_threshold(thresholds, "theta_base_tightness", "stage_1")
        and low_vol < get_threshold(thresholds, "theta_low_vol", "stage_1")
        and low_252_age_days >= get_threshold(thresholds, "theta_min_recovery_days", "stage_1")
    )


def classify_stage_2a(
    prior_state: str, close: float,
    sma_50: float, sma_150: float, sma_200: float, sma_200_slope: float,
    max_close_60d: float, volume_today: float, volume_50d_avg: float,
    rs_rank_12m: float, days_in_stage_2: int,
    thresholds: dict,
) -> bool:
    """Stage 2A (Fresh Breakout): just entered stage 2, all conditions confirm."""
    if prior_state not in ("stage_1", "stage_4"):
        return False
    if any(v != v for v in (close, sma_50, sma_150, sma_200, sma_200_slope,
                              volume_today, volume_50d_avg, rs_rank_12m)):
        return False
    return (
        close > sma_50 > sma_150 > sma_200
        and sma_200_slope > 0
        and close >= get_threshold(thresholds, "theta_base_breakout", "stage_2a") * max_close_60d
        and volume_today > get_threshold(thresholds, "theta_vol_mult", "stage_2a") * volume_50d_avg
        and rs_rank_12m * 100 >= get_threshold(thresholds, "theta_rs", "stage_2a")
        and days_in_stage_2 <= get_threshold(thresholds, "theta_fresh_days", "stage_2a")
    )


def classify_stage_2b(
    in_stage_2: bool, days_in_stage_2: int, distribution_days_5d: int,
    close: float, sma_50: float, thresholds: dict,
) -> bool:
    """Stage 2B (Confirmed): in stage 2 between 22-126 days, healthy."""
    if not in_stage_2 or close != close or sma_50 != sma_50:
        return False
    fresh = get_threshold(thresholds, "theta_fresh_days", "stage_2a")
    confirmed = get_threshold(thresholds, "theta_confirmed_days", "stage_2b")
    return (
        fresh < days_in_stage_2 <= confirmed
        and distribution_days_5d == 0
        and close > sma_50
    )


def classify_stage_2c(
    in_stage_2: bool, days_in_stage_2: int,
    close: float, sma_50: float, atr_14: float, atr_14_50d_avg: float,
    thresholds: dict,
) -> bool:
    """Stage 2C (Mature): in stage 2 beyond confirmed_days OR extended."""
    if not in_stage_2:
        return False
    confirmed = get_threshold(thresholds, "theta_confirmed_days", "stage_2b")
    extension = get_threshold(thresholds, "theta_extension", "stage_2c")
    atr_expansion = get_threshold(thresholds, "theta_atr_expansion", "stage_2c")
    overextended = (close / sma_50 > extension) if sma_50 > 0 else False
    vol_expanded = (atr_14 / atr_14_50d_avg > atr_expansion) if atr_14_50d_avg > 0 else False
    return days_in_stage_2 > confirmed or overextended or vol_expanded


def classify_stage_3(
    prior_state: str, close: float, sma_50: float, sma_50_slope: float,
    distribution_days_25d: int, thresholds: dict,
) -> bool:
    """Stage 3 (Top): was in stage 2, now showing topping signs."""
    if prior_state not in ("stage_2a", "stage_2b", "stage_2c"):
        return False
    if any(v != v for v in (close, sma_50, sma_50_slope)):
        return False
    topping_price = close < sma_50 or sma_50_slope < 0
    enough_distribution = distribution_days_25d >= get_threshold(
        thresholds, "theta_distribution", "stage_3"
    )
    return topping_price and enough_distribution
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.6: classifier.py — orchestrator (classify_state_panel)

Compose the per-state predicates into the full state classifier that takes a panel of features and returns per-(stock, day) states.

**Files:**
- Modify: `atlas/intelligence/states/classifier.py`
- Modify: `tests/intelligence/states/test_classifier.py`

- [ ] **Step 1: Test**

```python
import pandas as pd
from atlas.intelligence.states.classifier import classify_state_panel

def test_classify_state_panel_returns_dataframe():
    """Panel input → DataFrame with one row per (instrument, date) and a 'state' column."""
    # synthetic 3-stock × 60-day panel with one stock clearly in stage 2 trend
    features = _make_3_stock_panel()
    thresholds = _seed_thresholds()
    out = classify_state_panel(features, thresholds, classifier_version="v1.0")
    required_cols = {"instrument_id","date","state","prior_state","state_since_date",
                     "dwell_days","classifier_version"}
    assert required_cols <= set(out.columns)
    assert out["state"].isin({"uninvestable","stage_1","stage_2a","stage_2b","stage_2c",
                                "stage_3","stage_4"}).all()
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write orchestrator**

```python
# atlas/intelligence/states/classifier.py (orchestrator addition)

import pandas as pd


def classify_state_panel(
    features: pd.DataFrame, thresholds: dict, classifier_version: str
) -> pd.DataFrame:
    """Apply state classifier to a panel of (instrument_id, date) features.

    features columns required:
      instrument_id, date, close, sma_50, sma_150, sma_200, sma_50_slope,
      sma_200_slope, atr_14, atr_14_50d_avg, volume, volume_50d_avg,
      max_close_60d, rs_rank_12m, distribution_days_25d, distribution_days_5d,
      low_252_age_days, liquidity_score, data_gap_count

    Returns DataFrame with columns:
      instrument_id, date, state, prior_state, state_since_date, dwell_days,
      classifier_version + carry-through of feature columns for the explanation
      pane (rs_rank_12m, close_vs_sma_*, etc.).
    """
    rows = []
    # Sort so we can carry prior_state forward per instrument
    features = features.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    prior_state_per_instr: dict[str, str] = {}
    state_since_per_instr: dict[str, pd.Timestamp] = {}
    days_in_stage_2_per_instr: dict[str, int] = {}

    for _, r in features.iterrows():
        iid = r["instrument_id"]
        prior = prior_state_per_instr.get(iid, "stage_1")

        # Track days_in_stage_2 for cumulative Stage 2 classification
        days_in_stage_2 = days_in_stage_2_per_instr.get(iid, 0)
        if prior in ("stage_2a", "stage_2b", "stage_2c"):
            days_in_stage_2 += 1
        else:
            days_in_stage_2 = 0

        # Classify in priority order
        if classify_uninvestable(r["liquidity_score"], int(r["data_gap_count"]),
                                  r["close"], thresholds):
            state = "uninvestable"
        elif classify_stage_4(r["close"], r["sma_150"], r["sma_200"],
                               r["sma_150_slope"], thresholds):
            state = "stage_4"
        elif classify_stage_3(prior, r["close"], r["sma_50"], r["sma_50_slope"],
                               int(r["distribution_days_25d"]), thresholds):
            state = "stage_3"
        elif classify_stage_2a(prior, r["close"], r["sma_50"], r["sma_150"], r["sma_200"],
                                r["sma_200_slope"], r["max_close_60d"], r["volume"],
                                r["volume_50d_avg"], r["rs_rank_12m"], days_in_stage_2,
                                thresholds):
            state = "stage_2a"
        else:
            # In_stage_2 = TRUE if prior was 2x and trend stack still holds
            trend_stack_ok = (
                r["close"] > r["sma_50"] > r["sma_150"] > r["sma_200"]
                if all(not pd.isna(v) for v in (r["close"], r["sma_50"],
                                                  r["sma_150"], r["sma_200"]))
                else False
            )
            in_stage_2 = prior in ("stage_2a", "stage_2b", "stage_2c") and trend_stack_ok

            if classify_stage_2c(in_stage_2, days_in_stage_2, r["close"], r["sma_50"],
                                  r["atr_14"], r["atr_14_50d_avg"], thresholds):
                state = "stage_2c"
            elif classify_stage_2b(in_stage_2, days_in_stage_2,
                                     int(r["distribution_days_5d"]), r["close"],
                                     r["sma_50"], thresholds):
                state = "stage_2b"
            elif classify_stage_1(r["close"], r["sma_150"], r["atr_14"],
                                    int(r["low_252_age_days"]), thresholds):
                state = "stage_1"
            else:
                # Default: stay in prior actionable state if any, else stage_1
                state = "stage_1"

        # State-transition bookkeeping
        if state != prior:
            state_since = pd.to_datetime(r["date"])
            days_in_stage_2 = 1 if state in ("stage_2a", "stage_2b", "stage_2c") else 0
        else:
            state_since = state_since_per_instr.get(iid, pd.to_datetime(r["date"]))

        dwell = (pd.to_datetime(r["date"]) - state_since).days

        rows.append({
            "instrument_id": iid,
            "date": r["date"],
            "state": state,
            "prior_state": prior,
            "state_since_date": state_since.date(),
            "dwell_days": dwell,
            "classifier_version": classifier_version,
            "rs_rank_12m": r.get("rs_rank_12m"),
            "close_vs_sma_50": (r["close"] / r["sma_50"] - 1) if r["sma_50"] else None,
            "close_vs_sma_150": (r["close"] / r["sma_150"] - 1) if r["sma_150"] else None,
            "close_vs_sma_200": (r["close"] / r["sma_200"] - 1) if r["sma_200"] else None,
            "sma_200_slope": r.get("sma_200_slope"),
            "volume_ratio_50d": (r["volume"] / r["volume_50d_avg"]) if r["volume_50d_avg"] else None,
            "distribution_days": int(r["distribution_days_25d"]) if not pd.isna(r["distribution_days_25d"]) else None,
        })
        prior_state_per_instr[iid] = state
        state_since_per_instr[iid] = state_since
        days_in_stage_2_per_instr[iid] = days_in_stage_2

    return pd.DataFrame(rows)
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.7: dwell.py — dwell + cohort baselines + urgency

**Files:**
- Create: `atlas/intelligence/states/dwell.py`
- Create: `tests/intelligence/states/test_dwell.py`

- [ ] **Step 1: Tests**

```python
import pandas as pd
from atlas.intelligence.states.dwell import (
    compute_cohort_dwell_baselines,
    derive_urgency,
)

def test_cohort_dwell_baselines_aggregates_per_state():
    """Given a panel of historical state classifications, produce per-cohort
    per-state dwell statistics."""
    panel = pd.DataFrame([
        # 3 historical stage_2a episodes for large_cap
        {"instrument_id": "a", "state": "stage_2a", "dwell_days": 5, "cohort_key": "large_cap"},
        {"instrument_id": "b", "state": "stage_2a", "dwell_days": 8, "cohort_key": "large_cap"},
        {"instrument_id": "c", "state": "stage_2a", "dwell_days": 3, "cohort_key": "large_cap"},
    ])
    stats = compute_cohort_dwell_baselines(panel)
    row = stats[(stats["cohort_key"] == "large_cap") & (stats["state"] == "stage_2a")].iloc[0]
    assert row["n_observations"] == 3
    assert row["median_dwell_days"] in (5, 6)  # median of [3,5,8]

def test_derive_urgency_stage_2a_fresh():
    """Stage 2A with dwell_days = p25 → URGENT."""
    urgency = derive_urgency(
        state="stage_2a", dwell_days=2,
        cohort_baseline={"median": 5, "p25": 3, "p75": 8, "p95": 14},
    )
    assert urgency == "urgent"

def test_derive_urgency_stage_2a_late():
    """Stage 2A beyond p75 → LATE."""
    urgency = derive_urgency(
        state="stage_2a", dwell_days=10,
        cohort_baseline={"median": 5, "p25": 3, "p75": 8, "p95": 14},
    )
    assert urgency == "late"

def test_derive_urgency_stage_4_not_actionable():
    urgency = derive_urgency(
        state="stage_4", dwell_days=50,
        cohort_baseline={"median": 30, "p25": 15, "p75": 60, "p95": 120},
    )
    assert urgency == "n/a"
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write dwell.py**

```python
# atlas/intelligence/states/dwell.py
"""Dwell-time tracking + cohort baselines + urgency derivation.

Public API:
  compute_cohort_dwell_baselines(historical_panel) -> DataFrame
  derive_urgency(state, dwell_days, cohort_baseline) -> str
"""
from __future__ import annotations
import pandas as pd

# Urgency rules per state. Each rule maps a state to:
#   (when_short_dwell, when_long_dwell)
# where the categorization triggers off p25/p75 of cohort dwell.
_URGENCY_RULES: dict[str, tuple[str, str]] = {
    "stage_2a": ("urgent", "late"),     # fresh → buy now; late → window expired
    "stage_2b": ("normal", "late"),     # normal early; late → transition imminent
    "stage_2c": ("late", "urgent"),     # late = reversion soon; urgent = trim
    "stage_3":  ("normal", "urgent"),   # normal = confirm first; urgent = exit
    "stage_1":  ("n/a", "n/a"),         # not actionable
    "stage_4":  ("n/a", "n/a"),
    "uninvestable": ("n/a", "n/a"),
}


def compute_cohort_dwell_baselines(historical_panel: pd.DataFrame) -> pd.DataFrame:
    """Group a historical state panel by (cohort_key, state) and compute statistics.

    Input columns required: cohort_key, state, dwell_days, instrument_id.

    Output columns: cohort_key, state, mean_dwell_days, median_dwell_days,
                    p25_dwell_days, p75_dwell_days, p95_dwell_days, n_observations.
    """
    # For each (instrument, state-episode), use the MAX dwell_days as the episode length
    # Group: contiguous days in the same state for the same instrument.
    panel = historical_panel.copy()
    if "episode_id" not in panel.columns:
        # Detect episodes via state-change boundaries
        panel = panel.sort_values(["instrument_id", "dwell_days"])
        panel["episode_id"] = (
            panel["instrument_id"].astype(str) + "::" +
            (panel["dwell_days"] == 0).cumsum().astype(str)
        )
    # Episode length = max dwell_days within each episode
    episodes = panel.groupby(["episode_id", "cohort_key", "state"])["dwell_days"].max().reset_index()

    agg = episodes.groupby(["cohort_key", "state"])["dwell_days"].agg(
        mean_dwell_days="mean",
        median_dwell_days="median",
        p25_dwell_days=lambda s: s.quantile(0.25),
        p75_dwell_days=lambda s: s.quantile(0.75),
        p95_dwell_days=lambda s: s.quantile(0.95),
        n_observations="count",
    ).reset_index()
    # Cast quantiles to int
    for col in ("median_dwell_days", "p25_dwell_days", "p75_dwell_days", "p95_dwell_days"):
        agg[col] = agg[col].round().astype("Int64")
    return agg


def derive_urgency(state: str, dwell_days: int, cohort_baseline: dict) -> str:
    """Map (state, dwell_days, cohort_baseline) → urgency label.

    cohort_baseline dict must have keys: p25, p75 (median, p95 informational).
    Returns one of: 'urgent' | 'normal' | 'late' | 'n/a'.
    """
    short_label, long_label = _URGENCY_RULES.get(state, ("n/a", "n/a"))
    if short_label == "n/a":
        return "n/a"
    if dwell_days <= cohort_baseline.get("p25", 999):
        return short_label
    if dwell_days >= cohort_baseline.get("p75", 0):
        return long_label
    return "normal"
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.8: persistence.py — write to atlas_stock_state_daily

**Files:**
- Create: `atlas/intelligence/states/persistence.py`
- Create: `tests/intelligence/states/test_persistence.py`

- [ ] **Step 1: Test**

```python
def test_persist_state_panel_writes_rows(db_engine):
    panel = pd.DataFrame([{
        "instrument_id": "uuid_a", "date": pd.Timestamp("2026-05-15"),
        "state": "stage_2a", "prior_state": "stage_1",
        "state_since_date": pd.Timestamp("2026-05-14").date(),
        "dwell_days": 1, "urgency_score": "urgent", "within_state_rank": 0.95,
        "classifier_version": "v1.0",
        # explanation columns
        "rs_rank_12m": 0.92, "close_vs_sma_50": 0.05,
        "close_vs_sma_150": 0.12, "close_vs_sma_200": 0.18,
        "sma_200_slope": 0.0008, "volume_ratio_50d": 1.8,
        "distribution_days": 0, "dwell_percentile": 0.25,
    }])
    from atlas.intelligence.states.persistence import persist_state_panel
    persist_state_panel(db_engine, panel)
    with db_engine.connect() as c:
        rows = c.execute(text(
            "SELECT instrument_id, state, dwell_days FROM atlas.atlas_stock_state_daily "
            "WHERE date = '2026-05-15'"
        )).fetchall()
    assert len(rows) == 1
    assert rows[0].state == "stage_2a"
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Write persistence.py**

```python
# atlas/intelligence/states/persistence.py
"""Persist state-panel DataFrames to atlas.atlas_stock_state_daily."""
from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


_UPSERT_SQL = """
INSERT INTO atlas.atlas_stock_state_daily
    (instrument_id, date, state, prior_state, state_since_date,
     dwell_days, dwell_percentile, urgency_score, within_state_rank,
     rs_rank_12m, close_vs_sma_50, close_vs_sma_150, close_vs_sma_200,
     sma_200_slope, volume_ratio_50d, distribution_days, classifier_version)
VALUES
    (:instrument_id, :date, :state, :prior_state, :state_since_date,
     :dwell_days, :dwell_percentile, :urgency_score, :within_state_rank,
     :rs_rank_12m, :close_vs_sma_50, :close_vs_sma_150, :close_vs_sma_200,
     :sma_200_slope, :volume_ratio_50d, :distribution_days, :classifier_version)
ON CONFLICT (instrument_id, date) DO UPDATE SET
    state=EXCLUDED.state, prior_state=EXCLUDED.prior_state,
    state_since_date=EXCLUDED.state_since_date, dwell_days=EXCLUDED.dwell_days,
    dwell_percentile=EXCLUDED.dwell_percentile, urgency_score=EXCLUDED.urgency_score,
    within_state_rank=EXCLUDED.within_state_rank, rs_rank_12m=EXCLUDED.rs_rank_12m,
    close_vs_sma_50=EXCLUDED.close_vs_sma_50, close_vs_sma_150=EXCLUDED.close_vs_sma_150,
    close_vs_sma_200=EXCLUDED.close_vs_sma_200, sma_200_slope=EXCLUDED.sma_200_slope,
    volume_ratio_50d=EXCLUDED.volume_ratio_50d, distribution_days=EXCLUDED.distribution_days,
    classifier_version=EXCLUDED.classifier_version
"""


def persist_state_panel(engine: Engine, panel: pd.DataFrame) -> int:
    """Upsert panel rows into atlas_stock_state_daily. Returns row count written."""
    params = panel.to_dict(orient="records")
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), params)
    return len(params)
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.9: CLI subcommand `atlas-lab states classify`

Wire it up. Reads OHLCV from public.de_equity_ohlcv + atlas.atlas_universe_stocks, computes features, applies classifier, persists.

**Files:**
- Modify: `atlas/trading/cli.py`
- Create: `tests/cli/test_states_classify.py`

- [ ] **Step 1: Test (smoke)**

```python
def test_states_classify_writes_rows(db_engine):
    from atlas.trading.cli import _states_classify_cmd
    import argparse
    args = argparse.Namespace(start="2024-01-01", end="2024-03-31", universe="stocks_nifty500",
                                classifier_version="v1.0-test")
    rc = _states_classify_cmd(args)
    assert rc == 0
    with db_engine.connect() as c:
        rows = c.execute(text(
            "SELECT COUNT(*) FROM atlas.atlas_stock_state_daily "
            "WHERE classifier_version = 'v1.0-test'"
        )).scalar()
    assert rows > 0
```

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Add CLI subcommand**

```python
# atlas/trading/cli.py — add a new subcommand _states_classify_cmd

def _states_classify_cmd(args: argparse.Namespace) -> int:
    """Compute V1 state classification for the date range; persist to DB."""
    from atlas.intelligence.states.classifier import classify_state_panel
    from atlas.intelligence.states.dwell import derive_urgency
    from atlas.intelligence.states.persistence import persist_state_panel
    from atlas.intelligence.states.thresholds import load_active_thresholds
    from atlas.intelligence.states.features import (
        sma, slope, atr_14, distribution_days_25d,
        up_down_volume_ratio_50d, rs_rank_12m, base_depth,
    )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    db_url = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)
    thresholds = load_active_thresholds(eng)

    log.info("states_classify_start", start=str(start), end=str(end),
             n_thresholds=len(thresholds))
    # Load OHLCV — extend the start back 252 trading days so we can compute SMA-200
    fetch_start = start - pd.Timedelta(days=400)
    metrics, _ = _load_data(fetch_start, end, args.universe)
    log.info("states_classify_loaded_data", rows=len(metrics))

    # Compute features per stock
    features_rows = []
    for iid, group in metrics.groupby("instrument_id"):
        g = group.sort_values("date").reset_index(drop=True)
        features_rows.append(_compute_features_for_stock(g))
    features_df = pd.concat(features_rows, ignore_index=True)
    features_df = features_df[features_df["date"].between(start, end)]

    panel = classify_state_panel(features_df, thresholds, args.classifier_version)
    # Add urgency + within_state_rank columns (Tasks 1.10 builds the full version;
    # MVP here uses a simple percentile rank within state)
    panel["dwell_percentile"] = None  # populated by Task 1.10
    panel["urgency_score"] = "n/a"     # populated by Task 1.10
    panel["within_state_rank"] = None
    n = persist_state_panel(eng, panel)
    log.info("states_classify_persisted", n_rows=n)
    return 0
```

- [ ] **Step 4-5: Pass + commit.**

### Task 1.10: dwell percentile + urgency wiring + within-state rank

Compute dwell_percentile + urgency_score + within_state_rank after the initial classify pass.

**Files:**
- Modify: `atlas/trading/cli.py`
- Modify: `atlas/intelligence/states/dwell.py` (helper to compute percentile)
- Modify: `tests/intelligence/states/test_dwell.py`

- [ ] **Step 1: Test for dwell_percentile assignment**

- [ ] **Step 2: Run + fail.**

- [ ] **Step 3: Modify _states_classify_cmd to compute baselines, then update panel rows with percentile + urgency + within_state_rank before persisting**

(Logic: after building `panel`, query atlas_state_dwell_statistics for active baselines per cohort/state, then for each row compute dwell_percentile + urgency + within_state_rank using cohort baselines + RS rank + freshness + volume.)

- [ ] **Step 4-5: Pass + commit.**

### Task 1.11: Smoke test on known historical Stage 2 stocks

End-to-end smoke. Confirms the classifier puts known Stage 2 stocks (e.g., Adani Green Jul 2020, Tata Power Apr 2023, TDPOWERSYS in 2025-2026) into Stage 2 on the right dates.

**Files:**
- Create: `tests/intelligence/states/test_smoke_known_stage2.py`

- [ ] **Step 1: Write smoke test**

```python
def test_known_stage_2a_breakouts(db_engine):
    """Hand-picked historical breakouts should classify as stage_2a within ±5 trading days."""
    # Pull instrument_ids for these tickers
    known = [
        ("TDPOWERSYS", "2024-09-01", "2024-12-31"),  # confirmed breakout window
        ("ATHERENERG", "2025-04-01", "2025-07-31"),
    ]
    with db_engine.connect() as c:
        for symbol, start, end in known:
            rows = c.execute(text("""
                SELECT s.state, s.date
                FROM atlas.atlas_stock_state_daily s
                JOIN atlas.atlas_universe_stocks u USING (instrument_id)
                WHERE u.symbol = :sym
                  AND s.date BETWEEN :start AND :end
                  AND s.state IN ('stage_2a','stage_2b')
                LIMIT 5
            """), {"sym": symbol, "start": start, "end": end}).fetchall()
            assert rows, f"{symbol} should be in stage_2x somewhere in {start}..{end}"
```

- [ ] **Step 2: Run + fail (no data yet).**

- [ ] **Step 3: Backfill 2014-2026 via `atlas-lab states classify --start 2014-01-01 --end 2026-12-31` on EC2.**

- [ ] **Step 4: Run smoke test pass.**

- [ ] **Step 5: Commit smoke test.**

---

# PHASE 2 — IC validation closes the loop (1 week)

### Task 2.1: threshold_optimizer.py — grid sweep harness

**Files:**
- Create: `atlas/intelligence/states/threshold_optimizer.py`
- Create: `tests/intelligence/states/test_threshold_optimizer.py`

For each θ:
1. Build state-membership boolean series under candidate values
2. Compute IC of membership vs forward returns at the state's natural horizon
3. Pick θ that maximizes Q5–Q1 spread while passing IR_of_IC > 0.4
4. Persist optimal θ to `atlas_state_thresholds` (deactivate old, activate new)

Key signature:
```python
def tune_threshold(
    engine: Engine, threshold_name: str, state: str,
    candidate_values: list[float], as_of: date, horizon_days: int,
) -> ThresholdTuningResult
```

The harness reuses `atlas/intelligence/validation/ic_engine.compute_ic_over_window` and `forward_returns.load_price_matrix + compute_forward_returns`.

- [ ] **Step 1: Test** (synthetic case: candidate θ where one value clearly maximizes IC; verify harness picks it).
- [ ] **Step 2-5: Run/fail, implement, pass, commit.** ~250 LOC.

### Task 2.2: CLI `atlas-lab states tune`

- [ ] Add subcommand to `cli.py` taking `--as-of` and looping over all thresholds in catalog with reasonable grids.
- [ ] Tests + commit per pattern above.

### Task 2.3: Re-backfill with tuned thresholds

- [ ] Operational: after `tune` writes new active thresholds, re-run `atlas-lab states classify --start 2014-01-01 --end 2026-12-31` to repopulate `atlas_stock_state_daily` under the new θ.
- [ ] Compare IC of new states vs old states. Document in `docs/audits/state-engine-phase2-ic-report.md`.

---

# PHASE 2.5 — Component IC Validation (1 week)

Independently IC-validate each component indicator (RS / momentum / volatility / volume)
at the tier level. Each badge shown to a fund manager must be a true signal at the
horizon its implied action assumes — not just a conjunct of a working composite.

### Task 2.5.1: Migration 077 — atlas_component_validation

Standard alembic migration following the 072–076 pattern.
- Columns: component_name, badge, threshold_range, implied_action, horizon_days,
  as_of_date, mean_ic, ic_std, ic_t_stat, ic_ir, q5_q1_spread, n_observations, status.
- PK (component_name, badge, horizon_days, as_of_date).
- CHECK on status IN (validated, validated_inverse, weak, decorative).
- Test: existence + status CHECK rejection. Same pattern as test_072–076.

### Task 2.5.2: component_validator.py

**Files:**
- Create: `atlas/intelligence/states/component_validator.py` (~250 LOC)
- Create: `tests/intelligence/states/test_component_validator.py`

Public API:
```python
def validate_all_components(
    engine: Engine, start: date, end: date
) -> list[ComponentValidationResult]:
    """For each (component, tier) pair, compute IC + classify + persist."""
```

Components catalog (matches the 4 indicators displayed in the UI):
```python
COMPONENTS = [
    {
        "name": "rs_rank_12m",
        "horizon_days": 63,
        "implied_action": "favours_long",
        "tiers": [
            ("Leader", "rs_rank_12m >= 0.90"),
            ("Strong", "rs_rank_12m >= 0.70 AND rs_rank_12m < 0.90"),
            ("Average", "rs_rank_12m >= 0.30 AND rs_rank_12m < 0.70"),
            ("Weak", "rs_rank_12m >= 0.10 AND rs_rank_12m < 0.30"),
            ("Laggard", "rs_rank_12m < 0.10"),
        ],
    },
    {
        "name": "momentum_slope_21d",
        "horizon_days": 21,
        "implied_action": "favours_long",
        "tiers": [
            ("Accelerating", "slope_21d >= θ_mom_hi"),
            ("Stable", "between"),
            ("Decelerating", "slope_21d <= θ_mom_lo"),
        ],
    },
    {
        "name": "natr_14",
        "horizon_days": 63,
        "implied_action": "warns_long",  # high NATR → expected to underperform on a risk-adjusted basis
        "tiers": [...quartiles...],
    },
    {
        "name": "up_down_volume_ratio_50d",
        "horizon_days": 21,
        "implied_action": "favours_long",
        "tiers": [("Accumulation", ">θ_hi"), ("Neutral", "between"), ("Distribution", "<θ_lo")],
    },
]
```

For each (component, tier):
1. Build factor series — boolean 1/0 of "stock is in this tier on this date."
2. Load forward returns at horizon_days via `compute_forward_returns`.
3. Compute IC via `compute_ic_over_window`.
4. Classify per status rule:
   - `validated` if IR > 0.4 AND sign matches implied_action
   - `validated_inverse` if IR > 0.4 AND sign opposite
   - `weak` if 0.2 < IR ≤ 0.4
   - `decorative` otherwise.
5. Persist row to `atlas_component_validation`.

Tests (5+ per component, 20+ total):
- Synthetic data where one tier clearly has positive IC; validator detects it.
- Synthetic data where one tier has IC ~ 0; classified decorative.
- Sign-inverse detection: synthetic data where high tier → negative returns.
- Empty/insufficient data handling.

### Task 2.5.3: CLI `atlas-lab states validate-components`

Add to `atlas/trading/cli_states.py` (state-related CLI ops). Takes `--start` / `--end`,
loops the component catalog, persists results.

### Task 2.5.4: Frontend rendering rule (Phase 5 follow-on)

Tracked separately; not in this phase's code. Phase 5 frontend reads
`atlas_component_validation.status` for each badge and applies treatment:
- `validated` — green badge with implied action.
- `validated_inverse` — orange badge with "historically anti-predictive" hover.
- `weak` — grey badge with asterisk.
- `decorative` — plain label, no implied action.

### Task 2.5.5: Audit existing components against initial run

Operational, not coding. After running `atlas-lab states validate-components`, write
`docs/audits/component-validation-2026-05.md` summarizing which tiers are validated /
weak / decorative / validated_inverse, with the implication on which badges to revise
or drop in the UI.

---

# PHASE 3 — Aggregation (1 week)

### Task 3.1: aggregation.py — sector breadth

**Files:**
- Create: `atlas/intelligence/states/aggregation.py`
- Create: `tests/intelligence/states/test_aggregation.py`

```python
def compute_sector_breadth(engine: Engine, as_of: date) -> pd.DataFrame:
    """For each sector, count constituents in each state. Return wide format:
    sector, date, breadth_pct_stage_1, ..._stage_2a, ..._stage_2b, ..., breadth_summary"""
```

- [ ] TDD: test, fail, implement, pass, commit per pattern.

### Task 3.2: aggregation.py — country breadth

```python
def compute_country_breadth(engine: Engine, as_of: date, country: str = "IN") -> pd.Series:
    """Country = aggregate of all stocks. Same shape as sector_breadth."""
```

- [ ] TDD pattern.

### Task 3.3: aggregation.py — ETF + MF direct + breadth

```python
def classify_etf_direct(engine: Engine, as_of: date) -> pd.DataFrame:
    """Apply stock classifier to ETF OHLCV (from public.de_etf_ohlcv)."""

def classify_mf_direct(engine: Engine, as_of: date) -> pd.DataFrame:
    """Apply stock classifier to MF NAV (from public.de_mf_nav_daily)."""

def compute_etf_breadth_from_holdings(engine: Engine, as_of: date,
                                        freshness_threshold_days: int = 30) -> pd.DataFrame:
    """ETF breadth from de_etf_holdings where holdings fresh."""
```

- [ ] TDD pattern; 3 new table populations.

### Task 3.4: CLI `atlas-lab states aggregate`

- [ ] Subcommand triggering sector + country + ETF + MF aggregation.
- [ ] TDD pattern.

---

# PHASE 4 — Action engine + recommendations (1 week)

### Task 4.1: actions.py — transition detection + action mapping

**Files:**
- Create: `atlas/intelligence/states/actions.py`
- Create: `tests/intelligence/states/test_actions.py`

```python
@dataclass(frozen=True)
class Action:
    instrument_id: str
    date: date
    transition: str          # e.g. "stage_1->stage_2a"
    action: str              # BUY/HOLD/TRIM/EXIT/WATCH/FORCE_EXIT
    suppressed_by: str | None
    position_size: float | None
    within_state_rank: float | None
    urgency_score: str | None

def detect_transitions(state_panel: pd.DataFrame) -> pd.DataFrame:
    """Find state changes; return rows for changed (instrument, date) only."""

def map_transitions_to_actions(transitions: pd.DataFrame, risk_ctx: RiskContext,
                                  thresholds: dict) -> list[Action]:
    """Compose action mapping table + risk gate suppression."""
```

- [ ] TDD pattern; ~200 LOC.

### Task 4.2: STATE-ENGINE-V1 strategy entry + recommendations

```python
def generate_state_engine_recommendations(engine: Engine, as_of: date,
                                            top_n: int = 20) -> pd.DataFrame:
    """For (as_of) date, generate the STATE-ENGINE-V1 recommendations:
       - All BUY actions from today's transitions (Stage 1→2A)
       - Plus held positions (yesterday's Stage 2 stocks that didn't transition out)
       - Ranked by within_state_rank × urgency (urgent first, late last)
       - Take top_n; persist to atlas_strategy_recommendations_daily under
         genome_id for STATE-ENGINE-V1-WEINSTEIN."""
```

- [ ] Insert leaderboard row for STATE-ENGINE-V1-WEINSTEIN once with profile='aggressive', alpha_oos=0 initially (will be filled by backtest in Phase 6).
- [ ] TDD pattern.

### Task 4.3: CLI `atlas-lab states recommend`

- [ ] Subcommand `--date` triggers transition detection + action map + recommendations persist.
- [ ] Schedule in nightly cron after `states classify`.

---

# PHASE 5 — Frontend rewiring (1-2 weeks)

**Status:** Deferred to dedicated frontend session with `frontend-design` skill. Plan-shaped tasks:

- **5.1** — Stock detail page: render state + dwell + urgency badge. Files: `frontend/src/components/stocks/StateBadge.tsx`, `frontend/src/app/stocks/[id]/page.tsx`.
- **5.2** — Sector page: dual view (direct + breadth columns). Files: `frontend/src/components/sectors/SectorStateView.tsx`.
- **5.3** — ETF/MF/Country pages: dual view rendering. Files in `frontend/src/components/etfs/`, `mfs/`, `country/`.
- **5.4** — `/admin/state-thresholds` page: shows active θ + IC + last-tuned date.

Each task: write failing test (Playwright E2E), implement component, run pass, commit.

---

# PHASE 6 — Burn-in + V5 deprecation decision (30 days)

**Operational, not coding-heavy.** Run STATE-ENGINE-V1 alongside V5-RP-TREND for 30 days. Daily:

- `atlas-lab goal-post --rank 1` continues monitoring.
- `atlas-lab states recommend --date <today>` produces STATE-ENGINE-V1 recommendations.
- Compute realized IC of recommendations after 21d / 63d.
- Compare V5 vs STATE-ENGINE: alpha_realized, DD-compliance, hit rate.

After 30 days, write `docs/audits/state-engine-burnin-report.md` with the comparison and the decision rationale. If state engine wins, swap rank-1 via admin proposal (existing UI). If V5 wins, state engine stays informational.

---

## Self-review notes

**Spec coverage:** every locked premise (P1 state-as-filter+rank, P2 7 states, P3 Rung 2 inputs, P4 direct+breadth aggregation, P5 dwell+urgency, P6 coexistence+burn-in) has at least one Phase 0–4 task implementing it.

**Placeholder scan:** Phase 5 frontend tasks are described as "plan-shaped" — each names files and acceptance criteria; the TDD-step expansion happens in the dedicated frontend session per the design spec's sequencing.

**Type consistency:** state value names (`stage_2a` etc.) and table/column names (`atlas_stock_state_daily.state`) match across migrations, classifier, persistence, and tests. `within_state_rank` is `Numeric(5,4)` everywhere.
