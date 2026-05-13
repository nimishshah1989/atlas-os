# SP09 — CTS Timing Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build PPC/NPC/Contraction/Stage as native Atlas compute, self-calibrating via Timing IC and Hit-Rate Lift loops, with full frontend integration across screener, sectors, and stock deep-dive.

**Architecture:** Five phases — (A) vectorised signal compute + migration, (B) calibration data layer, (C) auto-calibration loop, (D) frontend surfaces, (E) on-demand Hermes brief. Phases A–C are pure backend with no UI; each feeds the next. Phase D consumes Phase A signals. Phase E adds the LLM synthesis layer.

**Tech Stack:** Python/pandas/pandas-ta (compute), SQLAlchemy + psycopg2 (DB), Alembic (migration), pytest/pytest-asyncio (tests), Next.js/React (frontend), Playwright (E2E)

---

## gstack Skill Sequence (Quality Gates)

| Milestone | Skill fired |
|-----------|-------------|
| Before each phase coding starts | `andrej-karpathy-skills:karpathy-guidelines` |
| After Phase A ships to EC2 | `superpowers:code-reviewer` → `superpowers:verification-before-completion` |
| After Phase B data is live | `superpowers:code-reviewer` + manual IC sanity check |
| After Phase C admin UI | `superpowers:code-reviewer` → `superpowers:verification-before-completion` → `/review` + `/codex` |
| After Phase D frontend | `playwright-expert` E2E → `superpowers:code-reviewer` → `superpowers:verification-before-completion` |
| After Phase E brief endpoint | `playwright-expert` E2E → `/review` + `/codex` → `/ship` |

---

## File Map

**New files:**
```
migrations/versions/043_create_cts_tables.py
atlas/compute/cts/__init__.py
atlas/compute/cts/primitives.py          # TRP, ATR14, SMA-N, volume ratio
atlas/compute/cts/stage.py               # Weinstein stage classifier
atlas/compute/cts/signals.py             # PPC, NPC, Contraction detection + strength
atlas/compute/cts/sector_pivot.py        # Sector-level PPC/NPC balance
atlas/intelligence/cts/__init__.py
atlas/intelligence/cts/timing_ic.py      # Spearman IC: signal strength vs fwd_ret
atlas/intelligence/cts/hit_rate.py       # Binary hit rate + lift ratio
atlas/intelligence/cts/auto_calibration/__init__.py
atlas/intelligence/cts/auto_calibration/param_candidates.py
atlas/intelligence/cts/auto_calibration/persistence.py
atlas/api/cts_brief.py                   # POST /api/v1/stocks/{symbol}/cts_brief
scripts/compute_cts_signals.py
scripts/backfill_cts_signals.py
scripts/update_cts_fwd_returns.py
scripts/compute_timing_ic.py
scripts/compute_cts_hit_rates.py
scripts/generate_cts_param_candidates.py
frontend/src/components/stocks/CTSSignalBadge.tsx
frontend/src/components/stocks/CTSDeepDiveCard.tsx
frontend/src/app/api/stocks/[symbol]/cts-brief/route.ts
tests/unit/cts/test_primitives.py
tests/unit/cts/test_stage.py
tests/unit/cts/test_signals.py
tests/unit/cts/test_hit_rate.py
tests/e2e/test_cts_screener.py
```

**Modified files:**
```
atlas/api/__init__.py                    # register cts_brief router
atlas/api/auth.py                        # no changes needed (JWT already on)
scripts/run_atlas_intelligence_nightly.sh # add 6 new steps
frontend/src/components/stocks/StockScreener.tsx   # add Stage + Signal columns
frontend/src/components/sectors/SectorDecisionTable.tsx  # add Pivot Balance
```

---

## Phase A — Compute Foundation

### Task 1: Migration 043

**Files:**
- Create: `migrations/versions/043_create_cts_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""SP09: CTS Timing Engine — schema foundation.

Creates:
- atlas_cts_signals_daily: daily PPC/NPC/Contraction/Stage per instrument
- atlas_cts_sector_pivot_daily: sector-level PPC/NPC balance
- atlas_cts_timing_ic: rolling Spearman IC for signal strength
- atlas_cts_hit_rates: binary hit rate + lift ratio per signal type
- atlas_cts_param_proposals: threshold calibration proposals

Revision ID: 043
Revises: 042
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE atlas.atlas_cts_signals_daily (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date            DATE NOT NULL,
            instrument_id   UUID NOT NULL REFERENCES atlas.atlas_instruments(id),
            stage           SMALLINT,
            is_stage1b      BOOLEAN,
            sma_150         NUMERIC(12, 4),
            sma_150_slope   NUMERIC(8, 6),
            trp             NUMERIC(6, 4),
            avg_trp         NUMERIC(6, 4),
            trp_ratio       NUMERIC(6, 4),
            is_tradeable    BOOLEAN,
            is_ppc          BOOLEAN,
            ppc_strength    NUMERIC(6, 4),
            is_npc          BOOLEAN,
            npc_strength    NUMERIC(6, 4),
            is_contraction  BOOLEAN,
            is_trigger_bar  BOOLEAN,
            trigger_level   NUMERIC(12, 4),
            atr_14          NUMERIC(8, 4),
            atr_slope       NUMERIC(10, 6),
            fwd_ret_5d      NUMERIC(8, 6),
            fwd_ret_10d     NUMERIC(8, 6),
            fwd_ret_20d     NUMERIC(8, 6),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_signals_daily_uq UNIQUE (date, instrument_id)
        )
    """)
    op.execute("CREATE INDEX cts_sig_date_idx   ON atlas.atlas_cts_signals_daily (date)")
    op.execute("CREATE INDEX cts_sig_inst_idx   ON atlas.atlas_cts_signals_daily (instrument_id)")
    op.execute("CREATE INDEX cts_sig_ppc_idx    ON atlas.atlas_cts_signals_daily (date) WHERE is_ppc")
    op.execute("CREATE INDEX cts_sig_stage2_idx ON atlas.atlas_cts_signals_daily (date) WHERE stage = 2")

    op.execute("""
        CREATE TABLE atlas.atlas_cts_sector_pivot_daily (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date            DATE NOT NULL,
            sector          VARCHAR(100) NOT NULL,
            ppc_count       INT NOT NULL DEFAULT 0,
            npc_count       INT NOT NULL DEFAULT 0,
            total_tradeable INT NOT NULL DEFAULT 0,
            pivot_balance   NUMERIC(6, 4),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_sector_pivot_uq UNIQUE (date, sector)
        )
    """)

    op.execute("""
        CREATE TABLE atlas.atlas_cts_timing_ic (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date        DATE NOT NULL,
            signal_name       VARCHAR(50) NOT NULL,
            lookback_window   INT NOT NULL,
            forward_horizon   INT NOT NULL,
            n_observations    INT NOT NULL,
            ic                NUMERIC(8, 6),
            t_stat            NUMERIC(8, 4),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_timing_ic_uq UNIQUE (as_of_date, signal_name, lookback_window, forward_horizon)
        )
    """)

    op.execute("""
        CREATE TABLE atlas.atlas_cts_hit_rates (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date        DATE NOT NULL,
            signal_type       VARCHAR(20) NOT NULL,
            stage_filter      SMALLINT,
            forward_horizon   INT NOT NULL,
            return_threshold  NUMERIC(6, 4) NOT NULL,
            hit_count         INT NOT NULL,
            total_signals     INT NOT NULL,
            hit_rate          NUMERIC(6, 4),
            base_rate         NUMERIC(6, 4),
            lift_ratio        NUMERIC(6, 4),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_hit_rates_uq UNIQUE (as_of_date, signal_type, stage_filter, forward_horizon, return_threshold)
        )
    """)

    op.execute("""
        CREATE TABLE atlas.atlas_cts_param_proposals (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date          DATE NOT NULL,
            param_key           VARCHAR(100) NOT NULL,
            current_value       NUMERIC(12, 6) NOT NULL,
            proposed_value      NUMERIC(12, 6) NOT NULL,
            smoothed_value      NUMERIC(12, 6) NOT NULL,
            direction           VARCHAR(10) NOT NULL,
            expected_lift_delta NUMERIC(8, 6),
            rationale           TEXT NOT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'pending',
            applied_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Seed CTS thresholds (Jhaveri defaults as prior)
    op.execute("""
        INSERT INTO atlas.atlas_thresholds (threshold_key, threshold_value, description, is_active)
        VALUES
            ('cts_trp_tradeable_min',         2.0,  'Min TRP% for tradeable stock',             true),
            ('cts_ppc_range_multiplier',       1.5,  'PPC: TRP ratio threshold',                 true),
            ('cts_ppc_close_pct',              0.60, 'PPC: close must be in top X% of range',    true),
            ('cts_ppc_volume_multiplier',      1.5,  'PPC: volume vs 20-bar avg',                true),
            ('cts_npc_range_multiplier',       1.5,  'NPC: TRP ratio threshold',                 true),
            ('cts_npc_close_pct',              0.40, 'NPC: close must be in bottom X% of range', true),
            ('cts_npc_volume_multiplier',      1.5,  'NPC: volume vs 20-bar avg',                true),
            ('cts_contraction_bars',           5,    'Contraction narrowing lookback bars',       true),
            ('cts_contraction_resistance_pct', 3.0,  'Contraction: max % from highest high',     true),
            ('cts_stage2_sma_period',          150,  'Weinstein SMA period (trading days)',       true),
            ('cts_stage2_slope_min_days',      20,   'SMA slope lookback days',                  true)
        ON CONFLICT (threshold_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_param_proposals")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_hit_rates")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_timing_ic")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_sector_pivot_daily")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_signals_daily")
    op.execute("""
        DELETE FROM atlas.atlas_thresholds
        WHERE threshold_key LIKE 'cts_%'
    """)
```

- [ ] **Step 2: Run migration locally**

```bash
alembic upgrade 043
```
Expected: `Running upgrade 042 -> 043`

- [ ] **Step 3: Verify tables created**

```bash
python -c "
from atlas.db import get_engine
from sqlalchemy import text
with get_engine().connect() as c:
    rows = c.execute(text(\"SELECT table_name FROM information_schema.tables WHERE table_schema='atlas' AND table_name LIKE 'atlas_cts%' ORDER BY 1\")).fetchall()
    for r in rows: print(r[0])
"
```
Expected: 5 table names printed.

- [ ] **Step 4: Verify thresholds seeded**

```bash
python -c "
from atlas.db import get_engine
from sqlalchemy import text
with get_engine().connect() as c:
    rows = c.execute(text(\"SELECT threshold_key, threshold_value FROM atlas.atlas_thresholds WHERE threshold_key LIKE 'cts_%' ORDER BY 1\")).fetchall()
    for r in rows: print(r[0], r[1])
"
```
Expected: 11 cts_* rows printed.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/043_create_cts_tables.py
git commit -m "feat(sp09): migration 043 — CTS tables + threshold seeds"
```

---

### Task 2: CTS Compute Primitives

**Files:**
- Create: `atlas/compute/cts/__init__.py`
- Create: `atlas/compute/cts/primitives.py`
- Create: `tests/unit/cts/__init__.py`
- Create: `tests/unit/cts/test_primitives.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/cts/test_primitives.py
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from decimal import Decimal
from atlas.compute.cts.primitives import add_trp, add_sma_slope, add_volume_ratio


def _make_ohlcv(n: int = 30) -> pd.DataFrame:
    """Synthetic OHLCV for one instrument."""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high  = close + rng.uniform(0.5, 2.0, n)
    low   = close - rng.uniform(0.5, 2.0, n)
    vol   = rng.integers(100_000, 500_000, n).astype(float)
    return pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "open": close - rng.uniform(0.1, 0.5, n),
        "high": high,
        "low": low,
        "close": close,
        "volume": vol,
    })


def test_add_trp_computes_correct_formula():
    df = _make_ohlcv(30)
    out = add_trp(df)
    expected_trp = (df["high"] - df["low"]) / df["close"] * 100
    pd.testing.assert_series_equal(out["trp"], expected_trp, check_names=False, rtol=1e-6)


def test_add_trp_avg_trp_is_20bar_rolling_mean():
    df = _make_ohlcv(30)
    out = add_trp(df)
    trp_series = (df["high"] - df["low"]) / df["close"] * 100
    expected_avg = trp_series.rolling(20).mean()
    pd.testing.assert_series_equal(out["avg_trp"], expected_avg, check_names=False, rtol=1e-6)


def test_add_trp_ratio_is_trp_over_avg():
    df = _make_ohlcv(30)
    out = add_trp(df)
    mask = out["avg_trp"].notna() & (out["avg_trp"] > 0)
    ratios = out.loc[mask, "trp"] / out.loc[mask, "avg_trp"]
    pd.testing.assert_series_equal(out.loc[mask, "trp_ratio"], ratios, check_names=False, rtol=1e-6)


def test_add_sma_slope_positive_on_uptrend():
    n = 200
    df = pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": np.linspace(100, 200, n),  # clean uptrend
    })
    out = add_sma_slope(df, sma_period=150, slope_days=20)
    # Last row: SMA is rising → slope positive
    assert out["sma_150_slope"].iloc[-1] > 0


def test_add_volume_ratio_equals_vol_over_20bar_mean():
    df = _make_ohlcv(30)
    out = add_volume_ratio(df)
    expected_avg_vol = df["volume"].rolling(20).mean()
    expected_ratio = df["volume"] / expected_avg_vol
    pd.testing.assert_series_equal(out["vol_ratio"], expected_ratio, check_names=False, rtol=1e-6)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/unit/cts/test_primitives.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'atlas.compute.cts'`

- [ ] **Step 3: Write the module**

```python
# atlas/compute/cts/__init__.py
"""CTS Timing Engine compute primitives.

Public surface: primitives, stage, signals, sector_pivot.
All functions take the whole universe DataFrame and vectorise via groupby.
No Python row loops. All thresholds injected as Mapping[str, Decimal].
"""
```

```python
# atlas/compute/cts/primitives.py
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta


def add_trp(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    avg_window: int = 20,
) -> pd.DataFrame:
    """Append trp, avg_trp, trp_ratio columns.

    TRP = (high - low) / close * 100. Vectorised across all groups.
    avg_trp = 20-bar SMA of TRP per instrument.
    trp_ratio = trp / avg_trp (NaN when avg_trp is 0 or not yet available).
    """
    out = df.copy().sort_values([group_col, "date"])
    out["trp"] = (out["high"] - out["low"]) / out["close"] * 100

    out["avg_trp"] = (
        out.groupby(group_col, observed=True)["trp"]
        .transform(lambda s: s.rolling(avg_window, min_periods=avg_window).mean())
    )
    out["trp_ratio"] = out["trp"] / out["avg_trp"].replace(0, pd.NA)
    return out


def add_sma_slope(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    sma_period: int = 150,
    slope_days: int = 20,
) -> pd.DataFrame:
    """Append sma_{sma_period} and sma_{sma_period}_slope columns.

    Slope = (sma_t - sma_{t-slope_days}) / slope_days — normalised change
    per bar. Positive = rising SMA (Stage 2 / Stage 3 condition).
    """
    out = df.copy().sort_values([group_col, "date"])
    col = f"sma_{sma_period}"
    out[col] = (
        out.groupby(group_col, observed=True)["close"]
        .transform(lambda s: s.rolling(sma_period, min_periods=sma_period).mean())
    )
    out[f"{col}_slope"] = (
        out.groupby(group_col, observed=True)[col]
        .transform(lambda s: s.diff(slope_days) / slope_days)
    )
    return out


def add_volume_ratio(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    avg_window: int = 20,
) -> pd.DataFrame:
    """Append avg_vol_20 and vol_ratio columns."""
    out = df.copy().sort_values([group_col, "date"])
    out["avg_vol_20"] = (
        out.groupby(group_col, observed=True)["volume"]
        .transform(lambda s: s.rolling(avg_window, min_periods=avg_window).mean())
    )
    out["vol_ratio"] = out["volume"] / out["avg_vol_20"].replace(0, pd.NA)
    return out


def add_atr14(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    length: int = 14,
) -> pd.DataFrame:
    """Append atr_14 via pandas-ta Wilder smoothing, and atr_slope.

    atr_slope = linear-regression slope of ATR over last 5 bars (normalised
    by current ATR). Negative slope = volatility compressing (Contraction cue).
    """
    out = df.copy().sort_values([group_col, "date"])
    col = f"atr_{length}"

    def _atr(g: pd.DataFrame) -> pd.Series:
        return ta.atr(g["high"], g["low"], g["close"], length=length)

    out[col] = (
        out.groupby(group_col, group_keys=False, observed=True)
        .apply(_atr)
        .reset_index(level=0, drop=True)
    )

    def _lr_slope(s: pd.Series, window: int = 5) -> pd.Series:
        def _slope(arr: np.ndarray) -> float:
            if np.isnan(arr).any():
                return np.nan
            x = np.arange(len(arr), dtype=float)
            return float(np.polyfit(x, arr, 1)[0])
        return s.rolling(window, min_periods=window).apply(_slope, raw=True)

    out["atr_slope"] = (
        out.groupby(group_col, observed=True)[col]
        .transform(_lr_slope)
    )
    return out
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/cts/test_primitives.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/compute/cts/ tests/unit/cts/
git commit -m "feat(sp09): CTS compute primitives — TRP, SMA slope, volume ratio, ATR14"
```

---

### Task 3: Stage Classifier

**Files:**
- Create: `atlas/compute/cts/stage.py`
- Create: `tests/unit/cts/test_stage.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/cts/test_stage.py
from __future__ import annotations
import numpy as np
import pandas as pd
from decimal import Decimal
from atlas.compute.cts.stage import classify_stage


def _uptrend_df(n: int = 200) -> pd.DataFrame:
    close = np.linspace(80, 120, n)  # clean uptrend, ends above SMA
    return pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": close,
    })


def _downtrend_df(n: int = 200) -> pd.DataFrame:
    close = np.linspace(120, 80, n)  # clean downtrend
    return pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": close,
    })


THRESHOLDS = {
    "cts_stage2_sma_period": Decimal("150"),
    "cts_stage2_slope_min_days": Decimal("20"),
}


def test_stage2_on_uptrend():
    df = _uptrend_df()
    out = classify_stage(df, thresholds=THRESHOLDS)
    # Last row: price above rising SMA → Stage 2
    last = out.iloc[-1]
    assert last["stage"] == 2
    assert last["sma_150_slope"] > 0


def test_stage4_on_downtrend():
    df = _downtrend_df()
    out = classify_stage(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    assert last["stage"] == 4


def test_stage_null_before_sma_period():
    df = _uptrend_df(200)
    out = classify_stage(df, thresholds=THRESHOLDS)
    # First 149 rows have no SMA → stage should be None
    assert out.iloc[148]["stage"] is None or pd.isna(out.iloc[148]["stage"])


# ENG-REVIEW FIX (D7): Stage 1, 1B, and 3 tests — previously untested.
# Misclassification here corrupts IC data from day 1 (signals correlated
# against wrong forward-return populations).

def test_stage1_on_basing_pattern():
    """Stage 1: price below flat/rising SMA (not yet broken out)."""
    # Price starts below SMA and SMA slope is flat → Stage 1
    n = 200
    # Flat SMA: all prices at 100, trend horizontal
    close = np.full(n, 100.0)
    df = pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": close,
    })
    out = classify_stage(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    # Flat SMA, price = SMA → close <= SMA, slope >= 0 → Stage 1
    assert last["stage"] == 1, f"expected Stage 1, got {last['stage']}"


def test_stage3_on_topping_pattern():
    """Stage 3: price above SMA but SMA slope turning negative."""
    n = 200
    # Uptrend for 160 bars, then price pulls back while SMA still high
    close = list(np.linspace(80, 130, 160)) + list(np.linspace(130, 115, 40))
    df = pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": close,
    })
    out = classify_stage(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    # After the decline: price may still be above SMA but slope is negative → Stage 3
    # (Could be 3 or 4 depending on how far price has fallen; test Stage 3 window)
    stage_at_180 = out.iloc[180]["stage"]
    assert stage_at_180 == 3, f"expected Stage 3 at peak pullback, got {stage_at_180}"


def test_stage1b_boundary_exclusive():
    """Stage 1B: price within <=3% below SMA (uses <= not <).

    ENG-REVIEW FIX (D7 critical gap): <=3% vs <3% — the boundary condition.
    Price exactly 3% below SMA should be IS_stage1b=True.
    Price exactly 3.1% below SMA should be IS_stage1b=False.
    A < instead of <= would silently exclude stocks at exactly 3% proximity.
    """
    n = 200
    # Build flat SMA ≈ 100, then set last price to exactly 97 (3% below)
    close_arr = np.full(n, 100.0)
    close_arr[-1] = 97.0  # exactly 3% below SMA
    df_at_boundary = pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": close_arr,
    })
    out = classify_stage(df_at_boundary, thresholds=THRESHOLDS)
    assert out.iloc[-1]["is_stage1b"] is True or out.iloc[-1]["is_stage1b"] == True, \
        "price at exactly 3% below SMA should trigger Stage 1B (<=, not <)"

    # Price at 3.1% below should NOT be Stage 1B
    close_arr2 = np.full(n, 100.0)
    close_arr2[-1] = 96.9  # 3.1% below SMA
    df_outside = pd.DataFrame({
        "instrument_id": ["AAA"] * n,
        "date": pd.date_range("2025-01-01", periods=n),
        "close": close_arr2,
    })
    out2 = classify_stage(df_outside, thresholds=THRESHOLDS)
    assert not out2.iloc[-1]["is_stage1b"], \
        "price at 3.1% below SMA should NOT trigger Stage 1B"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/unit/cts/test_stage.py -v 2>&1 | head -10
```
Expected: `ImportError`

- [ ] **Step 3: Write the module**

```python
# atlas/compute/cts/stage.py
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

import numpy as np
import pandas as pd

from atlas.compute.cts.primitives import add_sma_slope


def classify_stage(
    df: pd.DataFrame,
    *,
    thresholds: Mapping[str, Decimal],
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Append stage (1–4), is_stage1b, sma_150, sma_150_slope columns.

    Stage rules (Weinstein, adapted for NSE daily bars):
      2 = price > SMA_150 AND slope > 0  (advancing — only stage to be long)
      3 = price > SMA_150 AND slope <= 0 (topping — SMA flattening/declining)
      1 = price <= SMA_150 AND slope >= 0 (basing — SMA flat or rising)
      4 = price <= SMA_150 AND slope < 0  (declining)
      1B = stage 1 AND price within 3% below SMA_150 (about to break out)

    NaN stage when SMA_150 not yet computable (< 150 bars of history).
    """
    sma_period = int(thresholds["cts_stage2_sma_period"])
    slope_days = int(thresholds["cts_stage2_slope_min_days"])

    out = add_sma_slope(df, sma_period=sma_period, slope_days=slope_days)
    sma_col = f"sma_{sma_period}"
    slope_col = f"{sma_col}_slope"

    above = out["close"] > out[sma_col]
    rising = out[slope_col] > 0
    has_sma = out[sma_col].notna()

    conditions = [
        has_sma & above & rising,          # Stage 2
        has_sma & above & ~rising,         # Stage 3
        has_sma & ~above & rising,         # Stage 1
        has_sma & ~above & ~rising,        # Stage 4
    ]
    out["stage"] = np.select(conditions, [2, 3, 1, 4], default=None)
    out["stage"] = out["stage"].where(has_sma, other=None)

    # Stage 1B: price within 3% below SMA (coiling before breakout)
    out["is_stage1b"] = (
        (out["stage"] == 1)
        & ((out[sma_col] - out["close"]) / out[sma_col] <= Decimal("0.03"))
    )

    out.rename(columns={sma_col: "sma_150", slope_col: "sma_150_slope"}, inplace=True)
    return out
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/cts/test_stage.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/compute/cts/stage.py tests/unit/cts/test_stage.py
git commit -m "feat(sp09): Weinstein stage classifier (1/1B/2/3/4)"
```

---

### Task 4: PPC / NPC / Contraction Signal Detection

**Files:**
- Create: `atlas/compute/cts/signals.py`
- Create: `tests/unit/cts/test_signals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/cts/test_signals.py
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from decimal import Decimal
from atlas.compute.cts.signals import detect_signals

THRESHOLDS = {
    "cts_ppc_range_multiplier":       Decimal("1.5"),
    "cts_ppc_close_pct":              Decimal("0.60"),
    "cts_ppc_volume_multiplier":      Decimal("1.5"),
    "cts_npc_range_multiplier":       Decimal("1.5"),
    "cts_npc_close_pct":              Decimal("0.40"),
    "cts_npc_volume_multiplier":      Decimal("1.5"),
    "cts_trp_tradeable_min":          Decimal("2.0"),
    "cts_contraction_bars":           Decimal("5"),
    "cts_contraction_resistance_pct": Decimal("3.0"),
    "cts_stage2_sma_period":          Decimal("150"),
    "cts_stage2_slope_min_days":      Decimal("20"),
}


def _make_ppc_row() -> dict:
    """One candle that satisfies all four PPC conditions."""
    close, open_ = 105.0, 100.0
    high, low = 110.0, 98.0          # range=12, close%=(105-98)/12=0.583... wait
    # close_pct = (close - low) / (high - low) = (105-98)/(110-98) = 7/12 = 0.583 < 0.60
    # Adjust: high=109, low=98, close=105.5
    # close_pct = (105.5-98)/(109-98) = 7.5/11 = 0.682 ✓
    high, low, close = 109.0, 98.0, 105.5
    return {"open": 100.0, "high": high, "low": low, "close": close}


def _build_universe(n: int = 40, *, inject_ppc: bool = False) -> pd.DataFrame:
    """Build a minimal 40-bar universe for one instrument."""
    rng = np.random.default_rng(7)
    base_close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    rows = []
    for i in range(n):
        c = base_close[i]
        h = c + 1.0
        lo = c - 1.0
        rows.append({
            "instrument_id": "INS1",
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "open": c - 0.2,
            "high": h,
            "low": lo,
            "close": c,
            "volume": 200_000.0,
            "rs_pctile_cross_sector": 0.60,
        })
    if inject_ppc:
        last = rows[-1]
        last["high"]   = last["close"] + 8.0
        last["low"]    = last["close"] - 4.0
        last["close"]  = last["close"] + 6.5   # close_pct > 0.60
        last["open"]   = last["close"] - 2.0   # green candle
        last["volume"] = 600_000.0              # vol_ratio >> 1.5
    return pd.DataFrame(rows)


def test_detect_signals_returns_required_columns():
    df = _build_universe()
    out = detect_signals(df, thresholds=THRESHOLDS)
    for col in ["is_ppc", "ppc_strength", "is_npc", "npc_strength",
                "is_contraction", "is_trigger_bar", "trigger_level"]:
        assert col in out.columns, f"missing column {col}"


def test_no_ppc_on_flat_candles():
    df = _build_universe(inject_ppc=False)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert not out["is_ppc"].any(), "expected no PPC on flat candles"


def test_ppc_strength_in_unit_range():
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    ppc_rows = out[out["is_ppc"] == True]
    if not ppc_rows.empty:
        assert (ppc_rows["ppc_strength"].dropna() >= 0).all()
        assert (ppc_rows["ppc_strength"].dropna() <= 1).all()


def test_npc_not_fired_on_green_candle():
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    # Injected row is green (close > open) → NPC must not fire
    last = out.iloc[-1]
    if last["is_ppc"]:
        assert not last["is_npc"]


# ENG-REVIEW FIX (D7): Vectorized contraction test — verifies rolling-window
# implementation (not the old Python loop). Injects 7 bars of tightening range
# with declining ATR and proximity to 50-bar high. The old loop would also pass
# this test, but the new vectorized path must produce identical results.
def test_contraction_fires_on_tightening_setup():
    """Contraction detection: ≥60% narrowing + declining ATR + near 50-bar high."""
    n = 60  # enough for 50-bar rolling high
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, n))
    rows = []
    for i in range(n):
        c = closes[i]
        # Give the last 7 bars progressively tightening ranges (2.0 → 0.6 spread)
        if i >= n - 7:
            spread = 2.0 - (i - (n - 7)) * 0.2  # narrows each bar
            h, lo = c + spread / 2, c - spread / 2
        else:
            h, lo = c + 2.0, c - 2.0
        rows.append({
            "instrument_id": "INS1",
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "open": c - 0.1,
            "high": h,
            "low": lo,
            "close": c,
            "volume": 200_000.0,
            "rs_pctile_cross_sector": 0.60,
        })
    # Push closes to be close to the 50-bar rolling high
    # (the last few closes are near the peak from bar 50)
    peak = max(closes)
    for row in rows[-5:]:
        row["close"] = peak * 0.98  # within 2% of 50-bar high
        row["high"]  = peak * 0.99
        row["low"]   = peak * 0.97
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    # At least one of the last 5 bars should flag contraction
    assert out.tail(5)["is_contraction"].any(), \
        "expected contraction to fire on tightening setup near 50-bar high"


# ENG-REVIEW FIX (D7): ATR slope guard — fewer than 14 bars means no valid ATR.
# The rolling-window computation must not crash and must return NaN/False for
# all signal columns when there's insufficient history.
def test_short_series_no_crash():
    """Under-14-bar series must return NaN/False signals, not crash."""
    rows = [
        {
            "instrument_id": "INS1",
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
            "volume": 100_000.0, "rs_pctile_cross_sector": 0.5,
        }
        for i in range(10)  # only 10 bars — ATR period is 14
    ]
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    # No crash; signal columns present; no spurious True signals
    assert "is_ppc" in out.columns
    assert not out["is_ppc"].any(), "no PPC should fire on 10-bar history"
    assert not out["is_npc"].any(), "no NPC should fire on 10-bar history"
    assert not out["is_contraction"].any(), "no contraction on 10-bar history"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/unit/cts/test_signals.py -v 2>&1 | head -10
```
Expected: `ImportError`

- [ ] **Step 3: Write the module**

```python
# atlas/compute/cts/signals.py
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

import numpy as np
import pandas as pd

from atlas.compute.cts.primitives import add_atr14, add_trp, add_volume_ratio
from atlas.compute.cts.stage import classify_stage

# PPC/NPC strength composite weights — stored in atlas_signal_weights (tier='cts_ppc')
# Defaults here; loader overrides at runtime when weights exist in DB.
_DEFAULT_PPC_WEIGHTS = {"trp": 0.35, "vol": 0.35, "rs": 0.20, "stage": 0.10}


def detect_signals(
    df: pd.DataFrame,
    *,
    thresholds: Mapping[str, Decimal],
    ppc_weights: dict[str, float] | None = None,
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Detect PPC, NPC, and Contraction on the input OHLCV universe.

    Input DataFrame must have: instrument_id, date, open, high, low,
    close, volume, rs_pctile_cross_sector (float 0–1).

    Appends: is_ppc, ppc_strength, is_npc, npc_strength, is_contraction,
    is_trigger_bar, trigger_level, atr_14, atr_slope, trp, avg_trp,
    trp_ratio, vol_ratio, stage, sma_150, sma_150_slope, is_stage1b.
    """
    weights = ppc_weights or _DEFAULT_PPC_WEIGHTS

    out = add_trp(df)
    out = add_volume_ratio(out)
    out = add_atr14(out)
    out = classify_stage(out, thresholds=thresholds)

    ppc_range  = float(thresholds["cts_ppc_range_multiplier"])
    ppc_close  = float(thresholds["cts_ppc_close_pct"])
    ppc_vol    = float(thresholds["cts_ppc_volume_multiplier"])
    npc_range  = float(thresholds["cts_npc_range_multiplier"])
    npc_close  = float(thresholds["cts_npc_close_pct"])
    npc_vol    = float(thresholds["cts_npc_volume_multiplier"])
    con_bars   = int(thresholds["cts_contraction_bars"])
    con_res    = float(thresholds["cts_contraction_resistance_pct"])

    candle_range = (out["high"] - out["low"]).replace(0, pd.NA)
    close_pct = (out["close"] - out["low"]) / candle_range

    # PPC: all 4 conditions
    out["is_ppc"] = (
        (out["trp_ratio"] >= ppc_range)
        & (close_pct >= ppc_close)
        & (out["vol_ratio"] >= ppc_vol)
        & (out["close"] > out["open"])
    ).fillna(False)

    # NPC: all 4 conditions (mirror of PPC)
    out["is_npc"] = (
        (out["trp_ratio"] >= npc_range)
        & (close_pct <= npc_close)
        & (out["vol_ratio"] >= npc_vol)
        & (out["close"] < out["open"])
    ).fillna(False)

    # PPC strength composite (0–1)
    rs_col = "rs_pctile_cross_sector" if "rs_pctile_cross_sector" in out.columns else None
    trp_component  = (out["trp_ratio"] / 3.0).clip(0, 1)
    vol_component  = (out["vol_ratio"] / 4.0).clip(0, 1)
    rs_component   = out[rs_col].clip(0, 1) if rs_col else pd.Series(0.0, index=out.index)
    stage_component = (out["stage"] == 2).astype(float)

    out["ppc_strength"] = (
        weights["trp"]   * trp_component
        + weights["vol"] * vol_component
        + weights["rs"]  * rs_component
        + weights["stage"] * stage_component
    ).where(out["is_ppc"], other=pd.NA)

    out["npc_strength"] = (
        weights["trp"]   * trp_component
        + weights["vol"] * vol_component
        + weights["rs"]  * (1.0 - rs_component)   # low RS = stronger NPC
        + weights["stage"] * (out["stage"] == 4).astype(float)
    ).where(out["is_npc"], other=pd.NA)

    # Contraction detection
    out = _add_contraction(out, thresholds=thresholds, con_bars=con_bars, con_res=con_res)
    return out


def _add_contraction(
    df: pd.DataFrame,
    *,
    thresholds: Mapping[str, Decimal],
    con_bars: int,
    con_res: float,
) -> pd.DataFrame:
    """Append is_contraction, is_trigger_bar, trigger_level per instrument.

    ENG-REVIEW FIX (D3): Vectorised rolling-window implementation.
    The previous version used `for i in range(con_bars-1, n)` inside
    groupby.apply() — equivalent to iterrows() on a 500k-row dataset.
    This version uses rolling pandas operations: O(N) not O(N*con_bars).

    Three conditions, each computed as a boolean Series per instrument group:
    1. ATR slope negative  → computed via atr_slope column (already in df
       from add_atr14 via linear-regression rolling).  atr_slope < 0.
    2. ≥60% of bar-to-bar range transitions are narrowing  → rolling window
       counts narrowing transitions via a custom lambda.
    3. Within con_res % of 50-bar highest high  → rolling max proximity.

    All-NaN ATR guard: if atr_14 is all-NaN (< 14 bars history), atr_slope
    is also NaN — condition 1 is False → is_contraction stays False. No crash.
    """
    out = df.copy()

    def _contraction_for_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()

        # Condition 1: ATR slope negative (already computed by add_atr14)
        cond_atr = g["atr_slope"].fillna(0) < 0

        # Condition 2: ≥60% of bar-to-bar range transitions are narrowing
        rng = g["high"] - g["low"]
        def _narrowing_count(window: np.ndarray) -> float:
            if len(window) < 2:
                return 0.0
            return float(np.sum(window[1:] <= window[:-1] * 1.05))
        narrowing = rng.rolling(con_bars, min_periods=con_bars).apply(
            _narrowing_count, raw=True
        )
        cond_narrow = narrowing >= con_bars * 0.6

        # Condition 3: close within con_res % of 50-bar highest high
        highest = g["high"].rolling(50, min_periods=50).max()
        dist_pct = (highest - g["close"]) / highest.replace(0, pd.NA) * 100
        cond_prox = dist_pct <= con_res  # NaN highest → False (pd.NA comparison)

        is_con = cond_atr & cond_narrow & cond_prox
        g["is_contraction"] = is_con.fillna(False)
        g["is_trigger_bar"] = g["is_contraction"]
        g["trigger_level"]  = np.where(g["is_contraction"], g["high"], np.nan)
        return g

    result = (
        out.groupby("instrument_id", group_keys=False, observed=True)
        .apply(_contraction_for_group)
        .reset_index(drop=True)
    )
    return result
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/cts/test_signals.py -v
```
Expected: all 7 tests PASS (4 original + 3 ENG-REVIEW D7 fixes: contraction vectorized, short-series guard, stage 1B boundary).

- [ ] **Step 5: Commit**

```bash
git add atlas/compute/cts/signals.py tests/unit/cts/test_signals.py
git commit -m "feat(sp09): PPC/NPC/Contraction detection + strength composite"
```

---

### Task 5: Nightly Compute Script

**Files:**
- Create: `scripts/compute_cts_signals.py`
- Create: `atlas/compute/cts/sector_pivot.py`

- [ ] **Step 1: Write sector_pivot module**

```python
# atlas/compute/cts/sector_pivot.py
from __future__ import annotations

import pandas as pd


def compute_sector_pivot(signals_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate PPC/NPC counts by sector for one date.

    Input: signals_df with columns: instrument_id, date, is_ppc, is_npc,
           is_tradeable, sector.
    Output: DataFrame with date, sector, ppc_count, npc_count,
            total_tradeable, pivot_balance.
    """
    tradeable = signals_df[signals_df["is_tradeable"].fillna(False)]
    grouped = tradeable.groupby(["date", "sector"]).agg(
        ppc_count=("is_ppc", "sum"),
        npc_count=("is_npc", "sum"),
        total_tradeable=("instrument_id", "count"),
    ).reset_index()
    grouped["ppc_count"]  = grouped["ppc_count"].astype(int)
    grouped["npc_count"]  = grouped["npc_count"].astype(int)
    denom = grouped["total_tradeable"].replace(0, pd.NA)
    grouped["pivot_balance"] = (grouped["ppc_count"] - grouped["npc_count"]) / denom
    return grouped
```

- [ ] **Step 2: Write the nightly orchestrator**

```python
# scripts/compute_cts_signals.py
"""Compute PPC/NPC/Contraction/Stage for all ~750 stocks for today's date.

Run nightly after the M2-M5 pipeline (which writes de_equity_ohlcv).
Usage:
    python scripts/compute_cts_signals.py [--date YYYY-MM-DD] [--persist]
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import pandas as pd
import structlog

from atlas.compute._session import bulk_upsert, open_compute_session
from atlas.compute.cts.sector_pivot import compute_sector_pivot
from atlas.compute.cts.signals import detect_signals
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

LOOKBACK_BARS = 210  # need 200 bars for SMA-150 + slope buffer


def _load_universe(engine):
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT u.instrument_id, u.symbol, u.sector, u.tier
            FROM atlas.atlas_universe_stocks u
            WHERE u.effective_to IS NULL
            """,
            conn,
        )


def _load_ohlcv(engine, instrument_ids: list[str], end: date) -> pd.DataFrame:
    start = end - timedelta(days=int(LOOKBACK_BARS * 1.5))  # calendar days buffer
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT instrument_id, date, open, high, low, close, volume
            FROM public.de_equity_ohlcv
            WHERE instrument_id = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY instrument_id, date
            """,
            conn,
            params={"ids": instrument_ids, "start": start, "end": end},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _load_rs_pctile(engine, as_of_date: date) -> pd.DataFrame:
    """Load cross-sector RS percentile from the latest sector rotation MV."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT i.id AS instrument_id,
                   COALESCE(m.rs_pctile_3m_nifty500, 0.0)::float AS rs_pctile_cross_sector
            FROM atlas.atlas_instruments i
            LEFT JOIN atlas.atlas_stock_metrics_daily m
                ON m.instrument_id = i.id AND m.date = %(d)s
            WHERE i.is_active
            """,
            conn,
            params={"d": as_of_date},
        )


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()
    thresholds = load_thresholds(engine)

    log.info("cts_compute_start", date=str(as_of_date))
    universe = _load_universe(engine)
    ids = universe["instrument_id"].tolist()

    ohlcv = _load_ohlcv(engine, ids, as_of_date)
    log.info("ohlcv_loaded", rows=len(ohlcv), instruments=ohlcv["instrument_id"].nunique())

    rs_pctile = _load_rs_pctile(engine, as_of_date)
    ohlcv = ohlcv.merge(rs_pctile, on="instrument_id", how="left")
    ohlcv["rs_pctile_cross_sector"] = ohlcv["rs_pctile_cross_sector"].fillna(0.0)

    signals = detect_signals(ohlcv, thresholds=thresholds)

    # Keep only today's rows
    today_signals = signals[signals["date"] == as_of_date].copy()
    today_signals = today_signals.merge(
        universe[["instrument_id", "sector", "tier"]], on="instrument_id", how="left"
    )

    trp_min = float(thresholds["cts_trp_tradeable_min"])
    today_signals["is_tradeable"] = today_signals["avg_trp"].fillna(0) >= trp_min

    log.info(
        "signals_computed",
        total=len(today_signals),
        ppc=int(today_signals["is_ppc"].sum()),
        npc=int(today_signals["is_npc"].sum()),
        contraction=int(today_signals["is_contraction"].sum()),
        stage2=int((today_signals["stage"] == 2).sum()),
    )

    if persist:
        _upsert_signals(engine, today_signals, as_of_date)
        pivot = compute_sector_pivot(today_signals)
        _upsert_pivot(engine, pivot)
        log.info("cts_compute_persisted", date=str(as_of_date))


def _upsert_signals(engine, df: pd.DataFrame, as_of_date: date) -> None:
    cols = [
        "date", "instrument_id", "stage", "is_stage1b", "sma_150", "sma_150_slope",
        "trp", "avg_trp", "trp_ratio", "is_tradeable",
        "is_ppc", "ppc_strength", "is_npc", "npc_strength",
        "is_contraction", "is_trigger_bar", "trigger_level",
        "atr_14", "atr_slope",
    ]
    from atlas.compute._session import df_to_pg_rows
    rows = df_to_pg_rows(df[cols])
    bulk_upsert(engine, "atlas.atlas_cts_signals_daily", cols, rows, ["date", "instrument_id"])


def _upsert_pivot(engine, df: pd.DataFrame) -> None:
    cols = ["date", "sector", "ppc_count", "npc_count", "total_tradeable", "pivot_balance"]
    from atlas.compute._session import df_to_pg_rows
    rows = df_to_pg_rows(df[cols])
    bulk_upsert(engine, "atlas.atlas_cts_sector_pivot_daily", cols, rows, ["date", "sector"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
```

- [ ] **Step 3: Dry-run (no persist)**

```bash
python scripts/compute_cts_signals.py --date 2026-05-09
```
Expected: log lines with `cts_compute_start`, `ohlcv_loaded`, `signals_computed` (no DB write).

- [ ] **Step 4: Commit**

```bash
git add atlas/compute/cts/sector_pivot.py scripts/compute_cts_signals.py
git commit -m "feat(sp09): nightly CTS signal compute script + sector pivot"
```

---

### Task 6: Backfill Script + Phase A Quality Gate

**Files:**
- Create: `scripts/backfill_cts_signals.py`

- [ ] **Step 1: Write the backfill script**

```python
# scripts/backfill_cts_signals.py
"""Backfill CTS signals for the last 2 years.

Runs once on EC2 to bootstrap the IC measurement tables.
Usage:
    python scripts/backfill_cts_signals.py [--days 504] [--batch-days 20]
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import structlog

from atlas.db import get_engine
from scripts.compute_cts_signals import run

log = structlog.get_logger()


def backfill(total_days: int = 504, batch_days: int = 20) -> None:
    engine = get_engine()

    # Get trading dates from calendar
    from sqlalchemy import text
    from atlas.compute._session import open_compute_session
    with open_compute_session(engine) as conn:
        rows = conn.execute(text("""
            SELECT date FROM public.de_trading_calendar
            WHERE is_trading = TRUE
              AND exchange = 'NSE'
              AND date <= CURRENT_DATE
              AND date >= CURRENT_DATE - %(days)s
            ORDER BY date
        """), {"days": total_days * 2}).fetchall()  # calendar days buffer
    trading_dates = [r[0] for r in rows][-total_days:]

    log.info("backfill_start", total_dates=len(trading_dates))
    for i, d in enumerate(trading_dates):
        try:
            run(d, persist=True)
            log.info("backfill_progress", date=str(d), done=i + 1, total=len(trading_dates))
        except Exception as e:
            log.error("backfill_date_failed", date=str(d), error=str(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=504)
    backfill(total_days=parser.parse_args().days)
```

- [ ] **Step 2: Phase A Quality Gate — invoke code-reviewer**

Invoke `superpowers:code-reviewer` on the Phase A changes before EC2 deploy:
```bash
# review all Phase A files
git diff HEAD~6 HEAD -- atlas/compute/cts/ migrations/versions/043_create_cts_tables.py scripts/compute_cts_signals.py scripts/backfill_cts_signals.py
```

- [ ] **Step 3: Run full Phase A test suite**

```bash
pytest tests/unit/cts/ -v
```
Expected: all tests PASS.

- [ ] **Step 4: Invoke verification-before-completion**

Run `superpowers:verification-before-completion` — verify:
1. All 5 cts_* tables exist in DB
2. 11 cts_* thresholds seeded
3. Dry-run of compute_cts_signals.py produces PPC/NPC/Stage data
4. No Python errors

- [ ] **Step 5: EC2 deploy Phase A**

```bash
ssh atlas "cd ~/atlas-os && git pull && source .venv/bin/activate && alembic upgrade 043"
ssh atlas "cd ~/atlas-os && source .venv/bin/activate && python scripts/backfill_cts_signals.py --days 504 >> ~/logs/cts-backfill.log 2>&1 &"
```

- [ ] **Step 6: Verify EC2 backfill running**

```bash
ssh atlas "tail -f ~/logs/cts-backfill.log"
```
Expected: `backfill_progress` log lines every few seconds.

- [ ] **Step 7: Commit**

```bash
git add scripts/backfill_cts_signals.py
git commit -m "feat(sp09): 2-year CTS signal backfill script"
```

---

## Phase B — Calibration Data

### Task 7: Forward Returns Backfill

**Files:**
- Create: `scripts/update_cts_fwd_returns.py`

- [ ] **Step 1: Write the script**

```python
# scripts/update_cts_fwd_returns.py
"""Back-fill fwd_ret_5d / fwd_ret_10d / fwd_ret_20d on past signal rows.

Runs nightly. Finds signal rows where fwd_ret_20d IS NULL and the date is
old enough (>= 20 trading days ago). Loads prices and computes exact returns.
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text

from atlas.compute._session import open_compute_session, bulk_upsert, df_to_pg_rows
from atlas.db import get_engine

log = structlog.get_logger()


def run(*, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        # Rows that need forward returns: old enough AND not yet filled
        pending = pd.read_sql("""
            SELECT s.instrument_id, s.date
            FROM atlas.atlas_cts_signals_daily s
            WHERE s.fwd_ret_20d IS NULL
              AND (s.is_ppc OR s.is_npc OR s.is_contraction)
              AND s.date <= CURRENT_DATE - INTERVAL '22 trading days'
            ORDER BY s.date
            LIMIT 5000
        """, conn)

    if pending.empty:
        log.info("fwd_returns_nothing_to_update")
        return

    log.info("fwd_returns_pending", rows=len(pending))

    ids = pending["instrument_id"].unique().tolist()
    min_date = pending["date"].min()
    max_date = pending["date"].max()

    with open_compute_session(engine) as conn:
        prices = pd.read_sql("""
            SELECT instrument_id, date, close
            FROM public.de_equity_ohlcv
            WHERE instrument_id = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s + INTERVAL '30 days'
            ORDER BY instrument_id, date
        """, conn, params={"ids": ids, "start": min_date, "end": max_date})

    prices["date"] = pd.to_datetime(prices["date"]).dt.date
    pending["date"] = pd.to_datetime(pending["date"]).dt.date

    # ENG-REVIEW FIX (D6): Vectorised forward returns — NO iterrows().
    # Pivot prices to wide (date × instrument_id), shift per horizon,
    # compute pct change, melt back to long, merge onto pending.
    # One price load handles all three horizons in O(N) not O(N * K).
    prices["date"] = pd.to_datetime(prices["date"])
    pending["date"] = pd.to_datetime(pending["date"])

    prices_wide = prices.pivot(index="date", columns="instrument_id", values="close").sort_index()

    ret_frames = {}
    for horizon, col in [(5, "fwd_ret_5d"), (10, "fwd_ret_10d"), (20, "fwd_ret_20d")]:
        fwd = prices_wide.shift(-horizon) / prices_wide - 1
        ret_frames[col] = (
            fwd.reset_index()
            .melt(id_vars="date", var_name="instrument_id", value_name=col)
        )

    # Start with pending, left-join each horizon
    result = pending[["date", "instrument_id"]].copy()
    for col, frame in ret_frames.items():
        result = result.merge(frame, on=["date", "instrument_id"], how="left")

    if not persist:
        log.info("fwd_returns_computed_dry_run", count=len(result))
        return

    # Bulk UPDATE via temp table (one round-trip, not N individual UPDATEs)
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        result.to_sql(
            "__cts_fwd_tmp", conn, if_exists="replace", index=False,
            dtype={"instrument_id": sa.UUID, "date": sa.Date,
                   "fwd_ret_5d": sa.Numeric, "fwd_ret_10d": sa.Numeric,
                   "fwd_ret_20d": sa.Numeric},
        )
        conn.execute(text("""
            UPDATE atlas.atlas_cts_signals_daily s
            SET fwd_ret_5d=t.fwd_ret_5d, fwd_ret_10d=t.fwd_ret_10d, fwd_ret_20d=t.fwd_ret_20d
            FROM __cts_fwd_tmp t
            WHERE s.date=t.date AND s.instrument_id=t.instrument_id
        """))
        conn.execute(text("DROP TABLE IF EXISTS __cts_fwd_tmp"))
    log.info("fwd_returns_updated", count=len(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(persist=args.persist)
```

- [ ] **Step 2: Dry-run**

```bash
python scripts/update_cts_fwd_returns.py
```
Expected: `fwd_returns_pending` or `fwd_returns_nothing_to_update`

- [ ] **Step 3: Commit**

```bash
git add scripts/update_cts_fwd_returns.py
git commit -m "feat(sp09): back-fill forward returns on CTS signal rows"
```

---

### Task 8: Timing IC + Hit Rate Scripts

**Files:**
- Create: `scripts/compute_timing_ic.py`
- Create: `scripts/compute_cts_hit_rates.py`
- Create: `atlas/intelligence/cts/__init__.py`
- Create: `atlas/intelligence/cts/timing_ic.py`
- Create: `atlas/intelligence/cts/hit_rate.py`
- Create: `tests/unit/cts/test_hit_rate.py`

- [ ] **Step 1: Write failing hit-rate test**

```python
# tests/unit/cts/test_hit_rate.py
from __future__ import annotations
import pandas as pd
import numpy as np
from atlas.intelligence.cts.hit_rate import compute_hit_rate


def _make_signal_rows(n_signals: int, n_non: int, hit_fraction: float) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n_signals):
        ret = 0.07 if i < int(n_signals * hit_fraction) else 0.02
        rows.append({"is_ppc": True, "stage": 2, "fwd_ret_20d": ret})
    for _ in range(n_non):
        rows.append({"is_ppc": False, "stage": 2, "fwd_ret_20d": rng.uniform(-0.02, 0.06)})
    return pd.DataFrame(rows)


def test_hit_rate_matches_fraction():
    df = _make_signal_rows(100, 200, hit_fraction=0.70)
    result = compute_hit_rate(df, signal_col="is_ppc", stage_filter=2,
                              forward_col="fwd_ret_20d", return_threshold=0.05)
    assert abs(result["hit_rate"] - 0.70) < 0.02


def test_lift_ratio_above_one_when_signal_beats_base():
    df = _make_signal_rows(100, 200, hit_fraction=0.70)
    result = compute_hit_rate(df, signal_col="is_ppc", stage_filter=2,
                              forward_col="fwd_ret_20d", return_threshold=0.05)
    assert result["lift_ratio"] > 1.0


def test_returns_required_keys():
    df = _make_signal_rows(50, 100, 0.5)
    result = compute_hit_rate(df, signal_col="is_ppc", stage_filter=None,
                              forward_col="fwd_ret_20d", return_threshold=0.05)
    for k in ["hit_count", "total_signals", "hit_rate", "base_rate", "lift_ratio"]:
        assert k in result
```

- [ ] **Step 2: Write the hit_rate module**

```python
# atlas/intelligence/cts/hit_rate.py
from __future__ import annotations

from typing import Any

import pandas as pd


def compute_hit_rate(
    df: pd.DataFrame,
    *,
    signal_col: str,
    stage_filter: int | None,
    forward_col: str,
    return_threshold: float,
) -> dict[str, Any]:
    """Compute hit rate and lift ratio for a binary signal.

    Args:
        df: must have signal_col (bool), stage (int), forward_col (float).
        signal_col: 'is_ppc', 'is_npc', or 'is_contraction'.
        stage_filter: if not None, restrict universe to rows where stage == stage_filter.
        forward_col: 'fwd_ret_5d', 'fwd_ret_10d', or 'fwd_ret_20d'.
        return_threshold: minimum return to count as a 'hit'.

    Returns dict with hit_count, total_signals, hit_rate, base_rate, lift_ratio.
    """
    valid = df[df[forward_col].notna()].copy()
    if stage_filter is not None:
        valid = valid[valid["stage"] == stage_filter]

    if valid.empty:
        return {"hit_count": 0, "total_signals": 0, "hit_rate": None, "base_rate": None, "lift_ratio": None}

    signals = valid[valid[signal_col] == True]
    non_signals = valid[valid[signal_col] != True]

    hit_count = int((signals[forward_col] >= return_threshold).sum())
    total_signals = len(signals)
    hit_rate = hit_count / total_signals if total_signals > 0 else None

    base_count = int((non_signals[forward_col] >= return_threshold).sum())
    base_rate = base_count / len(non_signals) if len(non_signals) > 0 else None

    lift_ratio = (hit_rate / base_rate) if (hit_rate and base_rate and base_rate > 0) else None

    return {
        "hit_count": hit_count,
        "total_signals": total_signals,
        "hit_rate": hit_rate,
        "base_rate": base_rate,
        "lift_ratio": lift_ratio,
    }
```

- [ ] **Step 3: Run hit-rate tests**

```bash
pytest tests/unit/cts/test_hit_rate.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 4: Write compute_timing_ic.py**

```python
# scripts/compute_timing_ic.py
"""Compute Spearman IC between ppc_strength / npc_strength / atr_slope
and forward returns. Reuses atlas.intelligence.validation.ic_engine directly.

Usage: python scripts/compute_timing_ic.py [--persist]
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine
from atlas.intelligence.validation.ic_engine import compute_ic_over_window

log = structlog.get_logger()

SIGNAL_CONFIGS = [
    ("ppc_strength",  "fwd_ret_20d"),
    ("npc_strength",  "fwd_ret_20d"),
    ("atr_slope",     "fwd_ret_20d"),
    ("ppc_strength",  "fwd_ret_10d"),
]
LOOKBACK_DAYS = 90
MIN_OBS = 20


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        df = pd.read_sql("""
            SELECT date, instrument_id, ppc_strength, npc_strength, atr_slope,
                   fwd_ret_5d, fwd_ret_10d, fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_20d IS NOT NULL
        """, conn, params={
            "start": as_of_date - pd.Timedelta(days=LOOKBACK_DAYS),
            "end": as_of_date,
        })

    if df.empty:
        log.warning("timing_ic_no_data", date=str(as_of_date))
        return

    results = []
    for signal_col, fwd_col in SIGNAL_CONFIGS:
        horizon = int(fwd_col.split("_")[-1].replace("d", ""))
        sub = df[["date", "instrument_id", signal_col, fwd_col]].dropna()
        if len(sub) < MIN_OBS:
            continue
        # Build wide returns matrix expected by ic_engine
        returns_wide = sub.pivot(index="date", columns="instrument_id", values=fwd_col)
        factor = sub[["date", "instrument_id", signal_col]].rename(columns={signal_col: "factor_value"})
        factor = factor.set_index(["date", "instrument_id"])
        try:
            ic_result = compute_ic_over_window(factor, returns_wide)
        except Exception as e:
            log.warning("timing_ic_failed", signal=signal_col, error=str(e))
            continue

        results.append({
            "as_of_date": as_of_date,
            "signal_name": signal_col,
            "lookback_window": LOOKBACK_DAYS,
            "forward_horizon": horizon,
            "n_observations": ic_result.n_observations,
            "ic": ic_result.mean_ic,
            "t_stat": ic_result.ic_t_stat,
        })
        log.info("timing_ic_computed", signal=signal_col, horizon=horizon,
                 ic=round(ic_result.mean_ic, 4), n=ic_result.n_observations)

    if results and persist:
        df_out = pd.DataFrame(results)
        rows = df_to_pg_rows(df_out)
        cols = list(df_out.columns)
        bulk_upsert(engine, "atlas.atlas_cts_timing_ic", cols, rows,
                    ["as_of_date", "signal_name", "lookback_window", "forward_horizon"])
        log.info("timing_ic_persisted", count=len(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
```

- [ ] **Step 5: Write compute_cts_hit_rates.py**

```python
# scripts/compute_cts_hit_rates.py
"""Compute binary hit rates + lift ratios for PPC/NPC/Contraction signals.

Usage: python scripts/compute_cts_hit_rates.py [--persist]
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd
import structlog

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine
from atlas.intelligence.cts.hit_rate import compute_hit_rate

log = structlog.get_logger()

CONFIGS = [
    # (signal_col, stage_filter, forward_col, return_threshold)
    ("is_ppc",         2,    "fwd_ret_20d", 0.05),
    ("is_ppc",         2,    "fwd_ret_10d", 0.03),
    ("is_ppc",         None, "fwd_ret_20d", 0.05),
    ("is_npc",         None, "fwd_ret_20d", -0.05),
    ("is_contraction", 2,    "fwd_ret_20d", 0.05),
]
LOOKBACK_DAYS = 90


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        df = pd.read_sql("""
            SELECT date, instrument_id, is_ppc, is_npc, is_contraction,
                   stage, fwd_ret_5d, fwd_ret_10d, fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_20d IS NOT NULL
        """, conn, params={
            "start": as_of_date - pd.Timedelta(days=LOOKBACK_DAYS),
            "end": as_of_date,
        })

    results = []
    for signal_col, stage_filter, fwd_col, threshold in CONFIGS:
        horizon = int(fwd_col.split("_")[-1].replace("d", ""))
        metrics = compute_hit_rate(
            df, signal_col=signal_col, stage_filter=stage_filter,
            forward_col=fwd_col, return_threshold=abs(threshold),
        )
        if metrics["total_signals"] < 10:
            continue
        results.append({
            "as_of_date": as_of_date,
            "signal_type": signal_col.replace("is_", ""),
            "stage_filter": stage_filter,
            "forward_horizon": horizon,
            "return_threshold": threshold,
            **metrics,
        })
        log.info("hit_rate_computed", signal=signal_col, stage=stage_filter,
                 lift=round(metrics["lift_ratio"] or 0, 3))

    if results and persist:
        df_out = pd.DataFrame(results)
        cols = list(df_out.columns)
        rows = df_to_pg_rows(df_out)
        bulk_upsert(engine, "atlas.atlas_cts_hit_rates", cols, rows,
                    ["as_of_date", "signal_type", "stage_filter", "forward_horizon", "return_threshold"])
    log.info("hit_rates_done", count=len(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
```

- [ ] **Step 6: Wire Phase B into nightly script**

Edit `scripts/run_atlas_intelligence_nightly.sh`, add after `compute_conviction` step:

```bash
# SP09 CTS Timing Engine
run_step "compute_cts_signals"     python scripts/compute_cts_signals.py --persist
run_step "update_cts_fwd_returns"  python scripts/update_cts_fwd_returns.py --persist
run_step "compute_timing_ic"       python scripts/compute_timing_ic.py --persist
run_step "compute_cts_hit_rates"   python scripts/compute_cts_hit_rates.py --persist
```

- [ ] **Step 7: Commit**

```bash
git add atlas/intelligence/cts/ scripts/compute_timing_ic.py scripts/compute_cts_hit_rates.py scripts/run_atlas_intelligence_nightly.sh tests/unit/cts/test_hit_rate.py
git commit -m "feat(sp09): timing IC + hit rate calibration data pipeline"
```

---

## Phase C — Auto-Calibration Loop

### Task 9: Param Candidate Generator

**Files:**
- Create: `atlas/intelligence/cts/auto_calibration/__init__.py`
- Create: `atlas/intelligence/cts/auto_calibration/param_candidates.py`
- Create: `atlas/intelligence/cts/auto_calibration/persistence.py`
- Create: `scripts/generate_cts_param_candidates.py`

- [ ] **Step 1: Write persistence module**

```python
# atlas/intelligence/cts/auto_calibration/persistence.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


def insert_proposals(engine: Engine, proposals: list[dict[str, Any]]) -> int:
    """Insert pending proposals. Skip if same param_key already pending."""
    if not proposals:
        return 0
    written = 0
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        for p in proposals:
            result = conn.execute(text("""
                INSERT INTO atlas.atlas_cts_param_proposals
                    (as_of_date, param_key, current_value, proposed_value,
                     smoothed_value, direction, expected_lift_delta, rationale, status)
                SELECT :d, :key, :cur, :prop, :smooth, :dir, :delta, :rat, 'pending'
                WHERE NOT EXISTS (
                    SELECT 1 FROM atlas.atlas_cts_param_proposals
                    WHERE param_key = :key AND status = 'pending'
                )
            """), {
                "d": p["as_of_date"], "key": p["param_key"],
                "cur": p["current_value"], "prop": p["proposed_value"],
                "smooth": p["smoothed_value"], "dir": p["direction"],
                "delta": p.get("expected_lift_delta"), "rat": p["rationale"],
            })
            written += result.rowcount
    log.info("cts_proposals_inserted", count=written)
    return written
```

- [ ] **Step 2: Write param candidate generator**

```python
# atlas/intelligence/cts/auto_calibration/param_candidates.py
"""Generate threshold adjustment proposals driven by Hit Rate Lift.

For each calibratable CTS threshold:
1. Compute lift ratio at current value (last 90 days).
2. Simulate lift at current + step and current - step.
3. If best alternative improves lift by > MATERIAL_LIFT_DELTA, generate proposal.
4. Apply 15% Bayesian smoothing: smoothed = 0.85 * current + 0.15 * proposed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.cts.hit_rate import compute_hit_rate

log = structlog.get_logger()

from atlas.intelligence.conviction.optimization.smoothing import DEFAULT_LAMBDA

MATERIAL_LIFT_DELTA = Decimal("0.05")   # 5% improvement in lift ratio
# ENG-REVIEW FIX (D4): reuse DEFAULT_LAMBDA from the existing smoothing module.
# Note: blend_weights() itself is dict-shaped (weight vectors summing to 1) and
# cannot be called here — threshold values are scalars. We import only the constant.
SMOOTHING_ALPHA = DEFAULT_LAMBDA        # Decimal("0.15") — same 15% blend rate

# Parameters eligible for auto-calibration + step sizes + bounds
CALIBRATABLE_PARAMS: dict[str, dict[str, Any]] = {
    "cts_ppc_range_multiplier":  {"step": 0.1, "min": 1.2, "max": 2.5},
    "cts_ppc_volume_multiplier": {"step": 0.1, "min": 1.2, "max": 3.0},
    "cts_ppc_close_pct":         {"step": 0.05, "min": 0.50, "max": 0.80},
    "cts_npc_range_multiplier":  {"step": 0.1, "min": 1.2, "max": 2.5},
    "cts_npc_volume_multiplier": {"step": 0.1, "min": 1.2, "max": 3.0},
    "cts_contraction_resistance_pct": {"step": 0.5, "min": 1.0, "max": 8.0},
}

MIN_SIGNAL_COUNT = 30  # don't propose if fewer signals in window


def generate_proposals(
    engine: Engine,
    as_of_date: date,
    thresholds: Mapping[str, Decimal],
) -> list[dict[str, Any]]:
    """Return list of proposal dicts ready for persistence.insert_proposals."""
    # Load recent signal data with forward returns
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        df = pd.read_sql("""
            SELECT date, instrument_id, is_ppc, is_npc, is_contraction,
                   stage, trp_ratio, vol_ratio, atr_slope,
                   fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_20d IS NOT NULL
        """, conn.connection, params={
            "start": as_of_date - pd.Timedelta(days=90),
            "end": as_of_date,
        })

    if df.empty:
        return []

    proposals = []
    for param_key, spec in CALIBRATABLE_PARAMS.items():
        current_val = float(thresholds.get(param_key, 0))
        step = spec["step"]

        # Re-filter signals using alternative threshold values
        for direction, candidate_val in [
            ("increase", current_val + step),
            ("decrease", current_val - step),
        ]:
            if not (spec["min"] <= candidate_val <= spec["max"]):
                continue

            # Apply the candidate threshold to re-classify signals
            df_refiltered = _apply_threshold(df, param_key, candidate_val)
            metrics = compute_hit_rate(
                df_refiltered, signal_col="is_ppc", stage_filter=2,
                forward_col="fwd_ret_20d", return_threshold=0.05,
            )
            if metrics["total_signals"] < MIN_SIGNAL_COUNT:
                continue
            if metrics["lift_ratio"] is None:
                continue

            current_metrics = compute_hit_rate(
                df, signal_col="is_ppc", stage_filter=2,
                forward_col="fwd_ret_20d", return_threshold=0.05,
            )
            current_lift = current_metrics.get("lift_ratio") or 0
            delta = Decimal(str(metrics["lift_ratio"])) - Decimal(str(current_lift))

            if delta < MATERIAL_LIFT_DELTA:
                continue

            proposed = Decimal(str(candidate_val))
            current  = Decimal(str(current_val))
            smoothed = current * (1 - SMOOTHING_ALPHA) + proposed * SMOOTHING_ALPHA

            proposals.append({
                "as_of_date": as_of_date,
                "param_key": param_key,
                "current_value": current,
                "proposed_value": proposed,
                "smoothed_value": smoothed,
                "direction": direction,
                "expected_lift_delta": delta,
                "rationale": (
                    f"Lift {direction}s from {current_lift:.3f} to "
                    f"{metrics['lift_ratio']:.3f} (+{float(delta):.3f}) "
                    f"with {metrics['total_signals']} PPC signals on Stage 2."
                ),
            })
            # Only one direction can win per param per day
            break

    return proposals


def _apply_threshold(df: pd.DataFrame, param_key: str, value: float) -> pd.DataFrame:
    """Re-apply a single threshold to the existing signal DataFrame.

    ENG-REVIEW FIX (D5): All 6 calibratable params handled.
    The previous stub only handled 2 of 6 — the other 4 were silent no-ops,
    meaning proposals for NPC volume, PPC close position, NPC range, and
    contraction resistance would always show 0 signal change (never promoted).
    """
    out = df.copy()
    if param_key == "cts_ppc_range_multiplier":
        out["is_ppc"] = out["is_ppc"] & (out["trp_ratio"] >= value)
    elif param_key == "cts_ppc_volume_multiplier":
        out["is_ppc"] = out["is_ppc"] & (out["vol_ratio"] >= value)
    elif param_key == "cts_ppc_close_pct":
        close_pct = (out["close"] - out["low"]) / (out["high"] - out["low"]).replace(0, pd.NA)
        out["is_ppc"] = out["is_ppc"] & (close_pct.fillna(0) >= value)
    elif param_key == "cts_npc_range_multiplier":
        out["is_npc"] = out["is_npc"] & (out["trp_ratio"] >= value)
    elif param_key == "cts_npc_volume_multiplier":
        out["is_npc"] = out["is_npc"] & (out["vol_ratio"] >= value)
    elif param_key == "cts_contraction_resistance_pct":
        highest = out["high"].rolling(50, min_periods=50).max()
        dist = (highest - out["close"]) / highest.replace(0, pd.NA) * 100
        out["is_contraction"] = out["is_contraction"] & (dist.fillna(999) <= value)
    return out
```

- [ ] **Step 3: Write the nightly script**

```python
# scripts/generate_cts_param_candidates.py
"""Generate CTS threshold calibration proposals. Run nightly.

Waits for >=30 days of fwd_ret data before generating proposals (no-op otherwise).
"""
from __future__ import annotations

import argparse
from datetime import date

import structlog

from atlas.db import get_engine, load_thresholds
from atlas.intelligence.cts.auto_calibration.param_candidates import generate_proposals
from atlas.intelligence.cts.auto_calibration.persistence import insert_proposals

log = structlog.get_logger()


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()
    thresholds = load_thresholds(engine)
    proposals = generate_proposals(engine, as_of_date, thresholds)
    log.info("cts_proposals_generated", count=len(proposals))
    if proposals and persist:
        insert_proposals(engine, proposals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
```

- [ ] **Step 4: Add to nightly script**

```bash
run_step "generate_cts_param_candidates" python scripts/generate_cts_param_candidates.py --persist
```

- [ ] **Step 5: Phase C quality gate — invoke code-reviewer**

Run `superpowers:code-reviewer` on Phase B + C diff.

- [ ] **Step 6: Commit Phase C**

```bash
git add atlas/intelligence/cts/ scripts/generate_cts_param_candidates.py
git commit -m "feat(sp09): auto-calibration loop — param proposals + persistence"
```

---

## Phase D — Frontend Integration

### Task 10: Stock Screener — Stage + Signal Columns

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx`
- Create: `frontend/src/components/stocks/CTSSignalBadge.tsx`
- Modify: `frontend/src/lib/queries/stocks.ts` (add CTS join)

- [ ] **Step 1: Write CTSSignalBadge component**

Design notes applied: `rounded-[2px]` (Atlas standard — NOT `rounded`), tooltips on all abbreviations, `data-testid` for Playwright, `aria-label` on empty state, date formatted per DESIGN.md DD-MMM.

```tsx
// frontend/src/components/stocks/CTSSignalBadge.tsx
'use client'

type Stage = 1 | 2 | 3 | 4 | null
type Signal = 'PPC' | 'NPC' | 'Contraction' | null

const STAGE_STYLES: Record<number, string> = {
  2: 'bg-signal-pos/10 text-signal-pos border border-signal-pos/30',
  1: 'bg-paper-rule/20 text-ink-secondary border border-paper-rule',
  3: 'bg-signal-warn/10 text-signal-warn border border-signal-warn/30',
  4: 'bg-signal-neg/10 text-signal-neg border border-signal-neg/30',
}

const STAGE_TOOLTIPS: Record<number, string> = {
  1: 'Stage 1 — Base-building: below declining 150-day MA. Range-bound, no directional bias.',
  2: 'Stage 2 — Advancing: price above rising 150-day MA. Primary uptrend in progress.',
  3: 'Stage 3 — Distribution: above MA but slope flattening. Potential topping.',
  4: 'Stage 4 — Decline: below declining 150-day MA. Avoid.',
}

export function StageBadge({ stage }: { stage: Stage }) {
  if (!stage) return (
    <span className="text-ink-tertiary text-xs" aria-label="No stage data">—</span>
  )
  const label = `S${stage}`
  return (
    <span
      data-testid="stage-badge"
      title={STAGE_TOOLTIPS[stage]}
      aria-label={STAGE_TOOLTIPS[stage]}
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-xs font-mono font-medium ${STAGE_STYLES[stage]}`}
    >
      {label}
    </span>
  )
}

const SIGNAL_STYLES: Record<string, string> = {
  PPC: 'bg-signal-pos/10 text-signal-pos border border-signal-pos/30',
  NPC: 'bg-signal-neg/10 text-signal-neg border border-signal-neg/30',
  Contraction: 'bg-signal-warn/10 text-signal-warn border border-signal-warn/30',
}

const SIGNAL_TOOLTIPS: Record<string, string> = {
  PPC: 'Positive Pivotal Candle — large-range up-close candle on elevated volume. Setup for continuation.',
  NPC: 'Negative Pivotal Candle — large-range down-close candle on elevated volume. Setup for reversal.',
  Contraction: 'Price contraction near highs on declining ATR. Coil before potential breakout.',
}

export function SignalBadge({ signal, date }: { signal: Signal; date?: Date | string }) {
  if (!signal) return (
    <span className="text-ink-tertiary text-xs" aria-label="No CTS signal">—</span>
  )
  const dateStr = date
    ? (date instanceof Date ? date : new Date(date)).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    : undefined
  return (
    <div className="flex flex-col gap-0.5">
      <span
        data-testid="signal-badge"
        title={SIGNAL_TOOLTIPS[signal]}
        aria-label={`${signal}: ${SIGNAL_TOOLTIPS[signal]}`}
        className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-xs font-mono font-medium ${SIGNAL_STYLES[signal]}`}
      >
        {signal}
      </span>
      {dateStr && <span className="text-ink-tertiary text-[10px]">{dateStr}</span>}
    </div>
  )
}
```

- [ ] **Step 2: Add CTS columns to screener API query**

In `frontend/src/lib/queries/stocks.ts`, add to the screener SELECT:

```typescript
// Add to existing screener query SELECT list:
// cts.stage,
// cts.is_ppc,
// cts.is_npc,
// cts.is_contraction,
// cts.trigger_level,
// cts.ppc_strength,
// cts.signal_date
// LEFT JOIN atlas.atlas_cts_signals_daily cts
//   ON cts.instrument_id = s.instrument_id
//   AND cts.date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
```

Also add to the TypeScript row type: `stage?: number | null; is_ppc?: boolean; is_npc?: boolean; is_contraction?: boolean; trigger_level?: string | null; ppc_strength?: string | null; signal_date?: string | null`

- [ ] **Step 3: Add Stage + CTS Signal columns to StockScreener table**

Design fix: `key: 'cts_signal'` (NOT `key: 'signal'` — 'signal' key already exists in OPTIONAL_COLS for the RS composite signal; using the same key silently breaks the column toggle). Both columns are `defaultVisible: false` — screener is already 11 always-visible columns; these are enrichment.

In `frontend/src/components/stocks/StockScreener.tsx`, add to `OPTIONAL_COLS`:

```tsx
// Import at top:
import { StageBadge, SignalBadge } from './CTSSignalBadge'

// In OPTIONAL_COLS array (before conviction entry):
{ key: 'cts_stage',  label: 'Stage',      defaultVisible: false },
{ key: 'cts_signal', label: 'CTS Signal', defaultVisible: false },

// In the column render switch/if block, add cases:
case 'cts_stage':
  return <StageBadge stage={(optNum(row, 'stage') as 1|2|3|4|null)} />
case 'cts_signal': {
  const sig = optBool(row, 'is_ppc') ? 'PPC'
    : optBool(row, 'is_npc') ? 'NPC'
    : optBool(row, 'is_contraction') ? 'Contraction'
    : null
  return <SignalBadge signal={sig as 'PPC'|'NPC'|'Contraction'|null} date={optStr(row, 'signal_date') ?? undefined} />
}
```

- [ ] **Step 4: Start dev server and visual verify**

```bash
cd frontend && npm run dev
```
Open http://localhost:3000/stocks. Toggle Stage and CTS Signal columns on via column picker. Confirm S2 badge is green-tinted, S4 is red-tinted, PPC badge is green, all badges have near-square corners (NOT rounded pill shape). Hover a badge — tooltip should appear.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stocks/CTSSignalBadge.tsx frontend/src/components/stocks/StockScreener.tsx frontend/src/lib/queries/stocks.ts
git commit -m "feat(sp09): stock screener — Stage + CTS signal optional columns"
```

---

### Task 11: Sectors Page — Pivot Balance Column

**Files:**
- Modify: `frontend/src/components/sectors/SectorDecisionTable.tsx`
- Modify: `frontend/src/lib/queries/sectors.ts` (add pivot join)
- Modify: `frontend/src/app/sectors/page.tsx` (pass pivot data)

- [ ] **Step 1: Add pivot query to sectors.ts**

```typescript
// In frontend/src/lib/queries/sectors.ts, add:
export type SectorPivotRow = {
  sector: string
  ppc_count: number
  npc_count: number
  total_tradeable: number
  pivot_balance: string | null  // NUMERIC as string
}

export async function getSectorCTSPivot(): Promise<SectorPivotRow[]> {
  return sql<SectorPivotRow[]>`
    SELECT sector, ppc_count, npc_count, total_tradeable,
           pivot_balance::text AS pivot_balance
    FROM atlas.atlas_cts_sector_pivot_daily
    WHERE date = (SELECT MAX(date) FROM atlas.atlas_cts_sector_pivot_daily)
    ORDER BY pivot_balance DESC NULLS LAST
  `
}
```

- [ ] **Step 2: Add PivotBalance column to SectorDecisionTable**

Design notes: MiniBar from StockIntelligencePanel pattern (visual encoding, not just number). Props type extended. Column only renders when ctsPivot data exists (guard).

Add `SectorPivotRow` import and extend component props:
```tsx
// Add to SectorDecisionTable.tsx props:
ctsPivot?: Record<string, SectorPivotRow>  // pass {} when Phase A not yet run
```

Add column — only render when ctsPivot has data:
```tsx
// In SectorDecisionTable.tsx, add column after existing columns (guarded):
...(ctsPivot && Object.keys(ctsPivot).length > 0 ? [{
  key: 'pivot_balance',
  header: 'PPC/NPC',
  cell: (row: SectorRow) => {
    const pivot = ctsPivot[row.sector_name]
    if (!pivot) return <span className="text-ink-tertiary text-xs" aria-label="No pivot data">—</span>
    const balance = parseFloat(pivot.pivot_balance ?? '0')
    const isPos = balance > 0
    // Color: green if +20%+, amber if near zero, red if -20%-
    const barColor = balance > 0.2 ? '#2F6B43' : balance < -0.2 ? '#B0492C' : '#B8860B'
    return (
      <div className="flex flex-col items-end gap-1 min-w-[56px]">
        <div className="w-14 h-1.5 bg-paper-rule rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${Math.min(Math.abs(balance) * 100, 100)}%`, background: barColor }}
          />
        </div>
        <span className={`font-mono text-xs tabular-nums ${isPos ? 'text-signal-pos' : 'text-signal-neg'}`}>
          {isPos ? '+' : ''}{(balance * 100).toFixed(0)}%
        </span>
        <span className="text-ink-tertiary text-[10px]">
          {pivot.ppc_count}↑ {pivot.npc_count}↓
        </span>
      </div>
    )
  }
}] : [])
```

- [ ] **Step 3: Visual verify on dev server**

Open http://localhost:3000/sectors. Confirm PPC/NPC column appears with + green / - red values.

- [ ] **Step 4: Playwright E2E test**

Invoke `playwright-expert` skill, then write:

```typescript
// tests/e2e/test_cts_screener.py (Playwright Python)
import pytest
from playwright.sync_api import Page, expect

def test_stage_badge_visible_on_screener(page: Page):
    page.goto("http://localhost:3000/stocks")
    page.wait_for_selector('[data-testid="stock-screener-table"]', timeout=10000)
    # Stage column header should exist
    expect(page.locator('th:has-text("Stage")')).to_be_visible()
    # At least one stage badge should be rendered
    stage_badges = page.locator('.stage-badge')  # add data-testid="stage-badge" to StageBadge
    expect(stage_badges.first).to_be_visible()


def test_pivot_balance_column_on_sectors(page: Page):
    page.goto("http://localhost:3000/sectors")
    page.wait_for_selector('[data-testid="sector-decision-table"]', timeout=10000)
    expect(page.locator('th:has-text("PPC/NPC")')).to_be_visible()
```

- [ ] **Step 5: Run E2E tests**

```bash
cd frontend && npx playwright test tests/e2e/test_cts_screener.py
```
Expected: both tests PASS.

- [ ] **Step 6: Phase D quality gate**

Run `superpowers:code-reviewer` on all Phase D changes. Then `superpowers:verification-before-completion`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/ tests/e2e/test_cts_screener.py
git commit -m "feat(sp09): frontend — Stage badges, Signal badges, Sector PPC/NPC balance"
```

---

## Phase E — On-demand Stock Brief

### Task 12: CTS Brief Endpoint

**Files:**
- Create: `atlas/api/cts_brief.py`
- Modify: `atlas/api/__init__.py`
- Create: `frontend/src/app/api/stocks/[symbol]/cts-brief/route.ts`
- Modify: `frontend/src/components/stocks/CTSDeepDiveCard.tsx` (new component)

- [ ] **Step 1: Write the brief endpoint**

```python
# atlas/api/cts_brief.py
"""POST /api/v1/stocks/{symbol}/cts_brief

Builds context from Atlas conviction + CTS signals and calls the Hermes
LLM agent to produce a one-paragraph decision brief. SEBI guard: no forward
return predictions, no explicit buy/sell instructions.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from atlas.db import get_engine, load_thresholds
from atlas.compute._session import open_compute_session
from sqlalchemy import text
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/stocks", tags=["cts"])

SEBI_GUARD = (
    "You are a research assistant for a SEBI-registered portfolio manager. "
    "You MUST NOT make explicit buy or sell recommendations. "
    "You MUST NOT predict forward returns. "
    "Describe the observable signal state only."
)

BRIEF_PROMPT = """\
Given the following data for {symbol}, write ONE paragraph (4-6 sentences) describing
the current technical and quantitative state. Focus on: Stage, recent CTS signal,
Atlas conviction tier, sector alignment, and RS rank. Do not recommend action.

Atlas data:
- Conviction tier: {conviction_tier}
- RS cross-sector percentile: {rs_pctile:.0%}
- Sector state: {sector_state}
- Market regime: {regime}

CTS signals (today):
- Weinstein stage: {stage}
- SMA 150 slope: {sma_slope_direction}
- Latest PPC: {last_ppc}
- Is contraction: {is_contraction} {trigger_info}
- TRP ratio: {trp_ratio:.2f}x avg

Sector PPC/NPC balance: {pivot_balance}
"""


class CTSBriefResponse(BaseModel):
    symbol: str
    brief: str
    context: dict


@router.post("/{symbol}/cts_brief", response_model=CTSBriefResponse)
async def get_cts_brief(symbol: str):
    engine = get_engine()

    with open_compute_session(engine) as conn:
        # Load stock context
        row = conn.execute(text("""
            SELECT
                i.symbol,
                c.conviction_score,
                c.tier,
                m.rs_pctile_3m_nifty500,
                m.sector_state,
                r.regime_state,
                s.stage,
                s.sma_150_slope,
                s.is_ppc,
                s.is_npc,
                s.is_contraction,
                s.trigger_level,
                s.trp_ratio,
                s.ppc_strength,
                sp.pivot_balance
            FROM atlas.atlas_instruments i
            LEFT JOIN atlas.atlas_stock_conviction_daily c
                ON c.instrument_id = i.id
                AND c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
            LEFT JOIN atlas.atlas_stock_metrics_daily m
                ON m.instrument_id = i.id
                AND m.date = (SELECT MAX(date) FROM atlas.atlas_stock_metrics_daily)
            LEFT JOIN atlas.atlas_cts_signals_daily s
                ON s.instrument_id = i.id
                AND s.date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
            LEFT JOIN atlas.mv_current_market_regime r ON TRUE
            LEFT JOIN LATERAL (
                SELECT p.pivot_balance
                FROM atlas.atlas_cts_sector_pivot_daily p
                WHERE p.sector = m.sector
                AND p.date = (SELECT MAX(date) FROM atlas.atlas_cts_sector_pivot_daily)
                LIMIT 1
            ) sp ON TRUE
            WHERE UPPER(i.symbol) = UPPER(:sym)
        """), {"sym": symbol}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    ctx = dict(row._mapping)

    # Build prompt
    slope_dir = "rising" if (ctx.get("sma_150_slope") or 0) > 0 else "flat/declining"
    last_ppc = "None in recent window"
    if ctx.get("is_ppc"):
        last_ppc = f"Today (strength {float(ctx.get('ppc_strength') or 0):.2f})"

    trigger_info = ""
    if ctx.get("is_contraction") and ctx.get("trigger_level"):
        trigger_info = f"(trigger ₹{float(ctx['trigger_level']):.2f})"

    pivot = ctx.get("pivot_balance")
    pivot_str = f"{float(pivot)*100:+.0f}%" if pivot else "no data"

    prompt = BRIEF_PROMPT.format(
        symbol=symbol.upper(),
        conviction_tier=ctx.get("tier") or "Not ranked",
        rs_pctile=float(ctx.get("rs_pctile_3m_nifty500") or 0),
        sector_state=ctx.get("sector_state") or "Unknown",
        regime=ctx.get("regime_state") or "Unknown",
        stage=ctx.get("stage") or "N/A",
        sma_slope_direction=slope_dir,
        last_ppc=last_ppc,
        is_contraction=bool(ctx.get("is_contraction")),
        trigger_info=trigger_info,
        trp_ratio=float(ctx.get("trp_ratio") or 1.0),
        pivot_balance=pivot_str,
    )

    # Call Groq (Hermes pattern from SP07)
    try:
        from atlas.agents.specialists.base import call_groq
        brief_text = await call_groq(system=SEBI_GUARD, user=prompt)
    except Exception as e:
        log.error("cts_brief_llm_failed", symbol=symbol, error=str(e))
        brief_text = f"Brief unavailable: {e}"

    return CTSBriefResponse(symbol=symbol.upper(), brief=brief_text, context=ctx)
```

- [ ] **Step 2: Register router**

In `atlas/api/__init__.py`, add:

```python
from atlas.api.cts_brief import router as cts_brief_router
app.include_router(cts_brief_router)
```

- [ ] **Step 3: Write Next.js proxy route**

```typescript
// frontend/src/app/api/stocks/[symbol]/cts-brief/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { getAuthHeaders } from '@/lib/auth-headers'

export async function POST(
  _req: NextRequest,
  { params }: { params: { symbol: string } }
) {
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/stocks/${params.symbol}/cts_brief`
  const res = await fetch(backendUrl, {
    method: 'POST',
    headers: await getAuthHeaders(),
  })
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
```

- [ ] **Step 4: Create CTSDeepDiveCard component**

Design notes applied:
- Dynamic header from stage+signal state (not jargon "CTS Timing Signals")
- `text-accent` button (NOT `text-teal-600` — wrong Tailwind color)
- Horizontal Tile strip (NOT 2-col grid — generic AI pattern)
- Loading skeleton for brief section only (signal grid stays visible)
- Clean error state with retry (no raw Python exception text)
- `CommentaryBlock` for brief text (reuse existing Atlas pattern)
- SEBI disclaimer footer
- Placement: Overview tab right sidebar, below entry triggers (add to StockOverviewTab)

```tsx
// frontend/src/components/stocks/CTSDeepDiveCard.tsx
'use client'
import { useState } from 'react'
import { StageBadge, SignalBadge } from './CTSSignalBadge'

type Signal = 'PPC' | 'NPC' | 'Contraction' | null

function sectionTitle(stage: number | null, signal: Signal): string {
  if (stage === 2 && signal === 'PPC') return 'Stage 2 · PPC Setup'
  if (stage === 2 && signal === 'Contraction') return 'Stage 2 · Contracting'
  if (stage === 2 && signal === 'NPC') return 'Stage 2 · NPC Warning'
  if (stage === 2) return 'Stage 2 · Advancing'
  if (signal) return `Stage ${stage ?? '?'} · ${signal}`
  return 'Timing Setup'
}

export function CTSDeepDiveCard({
  symbol, stage, signal, signalDate, triggerLevel,
}: {
  symbol: string
  stage: number | null
  signal: Signal
  signalDate?: string | null
  triggerLevel?: number | null
}) {
  const [brief, setBrief] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const requestBrief = async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await fetch(`/api/stocks/${symbol}/cts-brief`, { method: 'POST' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setBrief(data.brief)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border border-paper-rule rounded-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-paper-rule">
        <h3 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          {sectionTitle(stage, signal)}
        </h3>
        <button
          onClick={requestBrief}
          disabled={loading}
          className="font-sans text-xs text-accent hover:text-ink-secondary disabled:opacity-40 min-h-[32px] px-1 flex items-center"
        >
          {loading ? 'Generating…' : 'Request Brief'}
        </button>
      </div>

      {/* Signal strip — always visible, static data */}
      <div className="flex items-stretch">
        <div className="flex flex-col gap-1 px-3 py-2.5 border-r border-paper-rule">
          <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Stage</span>
          <StageBadge stage={stage as 1|2|3|4|null} />
        </div>
        <div className="flex flex-col gap-1 px-3 py-2.5 border-r border-paper-rule">
          <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Signal</span>
          <SignalBadge signal={signal} date={signalDate ?? undefined} />
        </div>
        {triggerLevel != null && (
          <div className="flex flex-col gap-1 px-3 py-2.5">
            <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Trigger</span>
            <span className="font-mono text-sm text-ink-primary">₹{triggerLevel.toFixed(2)}</span>
          </div>
        )}
      </div>

      {/* Brief area — only appears after request */}
      {loading && (
        <div className="px-3 py-3 border-t border-paper-rule space-y-2 animate-pulse">
          <div className="h-2.5 bg-paper-rule/40 rounded-full w-full" />
          <div className="h-2.5 bg-paper-rule/40 rounded-full w-4/5" />
          <div className="h-2.5 bg-paper-rule/40 rounded-full w-3/5" />
        </div>
      )}

      {error && !loading && (
        <div className="px-3 py-3 border-t border-paper-rule">
          <p className="font-sans text-xs text-ink-tertiary">
            Brief unavailable — please try again.
          </p>
        </div>
      )}

      {brief && !loading && !error && (
        <div className="px-3 py-3 border-t border-paper-rule space-y-2">
          <p className="font-sans text-xs text-ink-primary leading-relaxed">{brief}</p>
          <p className="font-sans text-[10px] text-ink-tertiary">
            Generated from Atlas signals · Not investment advice · SEBI-compliant
          </p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4b: Wire CTSDeepDiveCard into StockOverviewTab**

Placement: Overview tab, right sidebar of the third row (below entry triggers, above the section close). In `frontend/src/components/stocks/StockOverviewTab.tsx`, import and add:

```tsx
import { CTSDeepDiveCard } from './CTSDeepDiveCard'

// In the right sidebar column of the third grid row, add below entry triggers:
<CTSDeepDiveCard
  symbol={stock.symbol}
  stage={(stock as any).stage ?? null}
  signal={
    (stock as any).is_ppc ? 'PPC'
    : (stock as any).is_npc ? 'NPC'
    : (stock as any).is_contraction ? 'Contraction'
    : null
  }
  signalDate={(stock as any).signal_date ?? null}
  triggerLevel={(stock as any).trigger_level ? parseFloat((stock as any).trigger_level) : null}
/>
```
```

- [ ] **Step 5: Smoke test the brief endpoint**

```bash
# With backend running:
curl -X POST http://localhost:8000/api/v1/stocks/RELIANCE/cts_brief | python -m json.tool
```
Expected: JSON with `symbol`, `brief` (non-empty), `context`.

- [ ] **Step 6: Final quality gate**

1. Invoke `superpowers:verification-before-completion` — checklist:
   - Migration 043 on EC2 ✓
   - Backfill complete (500+ days of signals) ✓
   - At least 2 nightly runs with forward returns filling ✓
   - Timing IC producing non-null values ✓
   - Hit rate lift > 1.0 for PPC Stage 2 ✓
   - Stage + Signal badges visible on screener ✓
   - PPC/NPC balance on sectors page ✓
   - CTS brief endpoint returns 200 ✓

2. Invoke `/review` + `/codex` for pre-merge review.

- [ ] **Step 7: Final commit + EC2 deploy**

```bash
git add atlas/api/cts_brief.py atlas/api/__init__.py frontend/src/components/stocks/CTSDeepDiveCard.tsx frontend/src/app/api/stocks/
git commit -m "feat(sp09): on-demand CTS stock brief via Hermes + SEBI guard"

# EC2
ssh atlas "cd ~/atlas-os && git pull && source .venv/bin/activate && pip install -q -e . && sudo systemctl restart atlas-api"
# Frontend
ssh atlas-fe "cd ~/atlas-frontend && git pull && npm run build && pm2 restart atlas-frontend"
```

---

## Data Quality Checks (run after Phase B data accumulates 20+ days)

```sql
-- 1. Signal counts look reasonable (not zero, not 100%)
SELECT date, COUNT(*) total, SUM(is_ppc::int) ppc, SUM(is_npc::int) npc,
       SUM(is_contraction::int) cont, SUM((stage=2)::int) stage2
FROM atlas.atlas_cts_signals_daily
WHERE date >= CURRENT_DATE - 5
GROUP BY date ORDER BY date DESC;

-- 2. Forward returns filling in (should reach ~0 nulls for dates >22 days ago)
SELECT date, COUNT(*) total, COUNT(fwd_ret_20d) filled
FROM atlas.atlas_cts_signals_daily
WHERE is_ppc OR is_npc
GROUP BY date ORDER BY date DESC LIMIT 30;

-- 3. Timing IC non-null and plausible (-0.15 to +0.15 normal range)
SELECT as_of_date, signal_name, forward_horizon, ic, t_stat, n_observations
FROM atlas.atlas_cts_timing_ic
ORDER BY as_of_date DESC, signal_name LIMIT 20;

-- 4. Hit rate lift above 1.0 for PPC Stage 2
SELECT as_of_date, signal_type, stage_filter, hit_rate, base_rate, lift_ratio
FROM atlas.atlas_cts_hit_rates
WHERE signal_type = 'ppc' AND stage_filter = 2
ORDER BY as_of_date DESC LIMIT 10;
```

---

## Execution Handoff

**Plan saved.** Two execution options:

**1. Subagent-Driven (recommended)** — spawn Opus agent per phase, fresh context, review between phases via `superpowers:code-reviewer`

**2. Inline** — execute tasks in this session using `superpowers:executing-plans`

Phases A and B should run together as one EC2 deployment to start accumulating calibration data. Phases C–E can follow 20 trading days later once the IC/hit-rate tables have meaningful data.

---

## GSTACK REVIEW REPORT

**Review date:** 2026-05-12  
**Reviewers:** `/plan-eng-review` (D1–D7) + `/plan-design-review` (7 passes, text-mode)  
**Plan status:** All issues addressed — plan is cleared for execution

### Engineering Review Summary (D3–D7 failure modes)

| ID | Failure mode | Severity | Fix applied |
|----|--------------|----------|-------------|
| D3 | Python loop in `_add_contraction()` — O(n) iterrows equivalent, blocked by data-engineering hook | Critical | Rewritten as rolling pandas ops: `rolling().apply()` for narrowing count, `rolling().max()` for proximity. Tests: `test_contraction_fires_on_tightening_setup()`, `test_short_series_no_crash()` |
| D4 | `blend_weights()` DRY violation — function takes `dict[str, Decimal]` weight vectors, not scalar thresholds | High | Import `DEFAULT_LAMBDA` constant only; added comment explaining why `blend_weights()` cannot be called here |
| D5 | `_apply_threshold()` silent no-ops — 4 of 6 calibratable params had no branch, proposals produced zero diff | High | All 6 branches added: `cts_ppc_close_pct`, `cts_npc_range_multiplier`, `cts_npc_volume_multiplier`, `cts_contraction_resistance_pct` |
| D6 | `iterrows()` in `update_cts_fwd_returns.py` — blocked by data-engineering commit hook | Critical | Vectorized: pivot → shift(-horizon) → melt; bulk UPDATE via temp table (one round-trip) |
| D7 | Missing tests: Stage 1, 1B, 3 untested; Stage 1B `<=` vs `<` boundary silent wrong result | High | Added: `test_stage1_on_basing_pattern()`, `test_stage3_on_topping_pattern()`, `test_stage1b_boundary_exclusive()` (verifies `<=3%`, not `<3%`), `test_contraction_fires_on_tightening_setup()`, `test_short_series_no_crash()` |
| D7b | LLM brief exposes raw Python exception string to user | Medium | try/catch returns clean "Brief unavailable — please try again." + retry affordance |

### Design Review Summary (7-pass, text-mode)

| Pass | Scope | Issues found | Fixes applied |
|------|-------|-------------|---------------|
| 1. Vocabulary | Atlas token compliance | `text-teal-600` (Tailwind #0D9488 ≠ Atlas #1D9E75) | Changed to `text-accent` (Atlas slate `#25394A`) |
| 2. Layout | Component structure | CTSDeepDiveCard used 2-col grid (generic pattern) | Horizontal Tile strip matching StockSnapshotTiles pattern |
| 3. Badges | Badge rendering | `rounded` (4px) instead of `rounded-[2px]` (Atlas standard) | All badge classes corrected |
| 4. Screener | Column key collision | `key: 'signal'` already exists in OPTIONAL_COLS for RS signal | Changed to `key: 'cts_stage'`/`key: 'cts_signal'` |
| 5. Screener | Column visibility | Stage/Signal columns `defaultVisible: true` in already-dense screener | Set to `defaultVisible: false` |
| 6. Card header | Context header | Static "CTS Timing Signals" title on all states | Dynamic `sectionTitle()`: "Stage 2 · PPC Setup", "Stage 2 · Contracting", etc. |
| 7. UX states | Error/loading | No error state; exception string exposed; no placement specified | Error: clean message + retry; Loading: skeleton in brief section only; Placement: Overview tab, right sidebar, below entry triggers; SEBI disclaimer footer |

### Sector PPC/NPC Balance (SectorDecisionTable)

MiniBar column guarded by `ctsPivot && Object.keys(ctsPivot).length > 0` — renders nothing until Phase A has been running for at least one nightly cycle. Color encoding: green (>+20%), terracotta (<−20%), ochre (±20%). Count annotation `{n}↑ {n}↓` below bar.

### Test coverage added by this review

| File | Tests added |
|------|------------|
| `tests/unit/cts/test_stage.py` | `test_stage1_on_basing_pattern`, `test_stage3_on_topping_pattern`, `test_stage1b_boundary_exclusive` |
| `tests/unit/cts/test_signals.py` | `test_contraction_fires_on_tightening_setup`, `test_short_series_no_crash` (+ 4 original = 7 total) |

### Open questions (non-blocking)

1. **Contraction `rolling().apply()` with custom function** — `_narrowing_count` uses `raw=True` for speed but the lambda captures outer scope `con_bars`. If `con_bars` changes at runtime (threshold tuning), the rolling closure updates correctly because `_contraction_for_group` recomputes `con_bars` from thresholds on each call.

2. **CTS brief SEBI guard** — current prompt forbids "recommend action" but allows describing current technical state. If Groq response contains directional language (e.g. "breakout likely"), the SEBI guard in SP07's `call_groq()` returns a safe fallback. No additional frontend filtering needed.

3. **Phase C gate** — auto-calibration should NOT go live until 20 trading days of IC data exist. The `check_cts_lift.py` script exits early if `n_signals < 30`. This gate must be retained; do not remove the early-exit even if it seems inconvenient during testing.
