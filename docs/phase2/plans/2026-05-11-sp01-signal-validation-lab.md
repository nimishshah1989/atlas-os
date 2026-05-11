# SP01 — Signal Validation Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED PRE-FLIGHT:** Before starting any task in this plan, read `docs/phase2/00-master-plan.html` section "Sub-project 01" and `docs/phase2/01-data-validator-agent.html`. The Phase 2 contract requires it. Project rules in `CLAUDE.md` enforce a planning-skill hook on writes to `atlas/**` — this plan satisfies that gate.

**Goal:** Measure Information Coefficient (IC) on the full Atlas `decision_state` composite (RS + Momentum + Risk + Volume + Sector + Regime states) against 5/21/63-day forward returns over rolling 6-month windows. Establish the predictive-power baseline that every downstream Phase 2 sub-project depends on.

**Architecture:** Three-layer pipeline. (1) **Factor loader** joins existing state tables (`atlas_stock_states_daily`, `atlas_sector_states_daily`, `atlas_market_regime_daily`) per (instrument_id, date) and encodes categorical states to a numeric composite quality score. (2) **IC engine** computes alphalens-style IC, t-statistics, quantile spreads, decay curves, and turnover on rolling windows. (3) **Persistence + reporting** writes results to `atlas_signal_ic` table and emits a markdown tearsheet under `output/validation/`.

**Tech Stack:** Python 3.12, alphalens-reloaded (cloudQuant fork; the original Quantopian package is abandoned on Py 3.11+), statsmodels (for t-stats), pandas, SQLAlchemy 2.0 (existing). New migration 032. New module `atlas/intelligence/validation/`. New CLI `scripts/run_signal_validation.py`.

**Decision-state composite encoding (v1):** Each categorical state maps to a [0,1] quality score; dimensions weighted; sentinels (`INSUFFICIENT_HISTORY`, `ILLIQUID`, `DISLOCATION_SUSPENDED`) drop the row. SP04 (Signal Intelligence layer) replaces these hand-set weights with IC-derived weights from this very table. The v1 weights below are a measurable starting point, not a permanent choice:

| Dimension | Weight | Encoding |
|---|---|---|
| `rs_state` | 0.35 | Leader=1.0, Strong=0.85, Consolidating=0.6, Emerging=0.55, Average=0.4, Weak=0.15, Laggard=0.0 |
| `momentum_state` | 0.25 | Accelerating=1.0, Improving=0.75, Flat=0.5, Deteriorating=0.25, Collapsing=0.0 |
| `risk_state` | 0.15 | Low=1.0, Normal=0.75, Below Trend=0.5, Elevated=0.25, High=0.0 |
| `volume_state` | 0.10 | Accumulation=1.0, Steady-Buying=0.75, Neutral=0.5, Distribution=0.25, Heavy Distribution=0.0 |
| `sector_state` (stock's sector) | 0.10 | Overweight=1.0, Neutral=0.5, Underweight=0.25, Avoid=0.0 |
| `regime_state` (regime multiplier) | 0.05 | Risk-On=1.0, Constructive=0.7, Cautious=0.4, Risk-Off=0.0 |

`decision_state_score = Σ (weight_i × encoded_state_i)` per row. Range [0,1]. Higher = more attractive per current methodology.

**Success criteria (from master plan SP01):**
1. `decision_state` mean IC > 0.05 with IC t-stat > 2.0 on 21-day forward returns over 3-year rolling window
2. Quantile spread (Q5 − Q1) > 8% annualized on 21-day forward returns
3. Turnover < 30% per month (else transaction costs eat alpha)
4. Pipeline runs end-to-end in &lt; 180 seconds for 10-year history

If criteria are not met: the answer is informative, not a failure. It drives SP04 redesign.

**File structure to create:**
```
atlas/intelligence/__init__.py                          # package marker
atlas/intelligence/validation/__init__.py               # exports public API
atlas/intelligence/validation/encoding.py               # state→numeric encoder
atlas/intelligence/validation/factor_loader.py          # SQL + composite assembly
atlas/intelligence/validation/forward_returns.py        # forward return matrix
atlas/intelligence/validation/ic_engine.py              # alphalens wrapper + rolling IC
atlas/intelligence/validation/persistence.py            # writes to atlas_signal_ic
atlas/intelligence/validation/report.py                 # markdown tearsheet generator
scripts/run_signal_validation.py                        # CLI orchestrator
migrations/versions/032_create_signal_ic_table.py
tests/intelligence/__init__.py
tests/intelligence/validation/__init__.py
tests/intelligence/validation/test_encoding.py
tests/intelligence/validation/test_factor_loader.py
tests/intelligence/validation/test_forward_returns.py
tests/intelligence/validation/test_ic_engine.py
tests/intelligence/validation/test_persistence.py
tests/intelligence/validation/test_sanity.py            # the three validation-strategy checks
```

**File responsibility split:**
- `encoding.py` — pure functions, no I/O. Maps state strings to numeric scores. Easy to unit-test.
- `factor_loader.py` — SQL only. Reads the four state tables + universe filter, joins, applies encoding, returns DataFrame keyed by (date, instrument_id).
- `forward_returns.py` — SQL only. Reads `atlas_stock_metrics_daily.close_approx`, computes log returns over the three forward windows.
- `ic_engine.py` — pandas/alphalens. No SQL. Takes factor and returns DataFrames, computes IC stats. Pure compute layer.
- `persistence.py` — SQL only. UPSERTs IC results to `atlas_signal_ic`.
- `report.py` — string-template output. Reads from `atlas_signal_ic` and a few in-memory artifacts to render markdown.
- `scripts/run_signal_validation.py` — orchestration only. Wires the above four with CLI args.

**Pre-existing Atlas patterns this plan follows:**
- `atlas.db.get_engine()` for DB connection (no new connection management)
- `Decimal` for any money/return values stored; `float` only inside compute
- `# noqa: S608` per-line on any SQL f-string with justification
- New context lives under `atlas/intelligence/` — module-boundaries hook (scripts/hooks/check_module_boundaries.py) will need this added to ALLOWED_EDGES if it imports from `atlas.db` (it will); update the hook as part of Task 0.
- Pyright/ruff/file-size hooks must pass; tests required for substantive edits.

---

## Task 0: Pre-flight + dependencies + module-boundary registration

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/hooks/check_module_boundaries.py`
- Modify: `CLAUDE.md` (only if you add a new convention; otherwise no change)

- [ ] **Step 1: Read the master plan SP01 section**

Open `docs/phase2/00-master-plan.html` in a browser and read sub-project 01 in full. Confirm the deliverables and success criteria match this plan's stated goal. If they diverge, STOP and reconcile before continuing.

- [ ] **Step 2: Read the Phase 2 contract rules in CLAUDE.md**

```bash
grep -A 30 "Phase 2" CLAUDE.md
```

Expected: the section pointing at `docs/phase2/00-master-plan.html` and `01-data-validator-agent.html`.

- [ ] **Step 3: Add alphalens-reloaded + statsmodels to pyproject.toml**

Modify `pyproject.toml` — under the existing `simulation` optional-dependencies group, add the new dep block:

```toml
intelligence = [
    "alphalens-reloaded>=0.4.5",
    "statsmodels>=0.14",
]
```

Place it after the existing `simulation = [...]` block, before `optimizer = [...]`.

- [ ] **Step 4: Install the new extras into the venv**

```bash
pip install -e ".[intelligence]"
```

Expected: alphalens-reloaded and statsmodels install without conflicts. Run `python -c "import alphalens; print(alphalens.__version__)"` and confirm version >= 0.4.5.

- [ ] **Step 5: Register the new bounded context in the module-boundaries hook**

The new `atlas.intelligence.*` context will read from `atlas.db` (shared kernel — always allowed) and call SQL against existing atlas tables. It will NOT import from any other bounded context. Open `scripts/hooks/check_module_boundaries.py` and confirm that ALLOWED_EDGES does not need any new entries because `atlas.db` is the shared kernel (not a context). However, you may need to update the hook's "known contexts" list to include `atlas.intelligence`.

Read the file:
```bash
grep -n "known_contexts\|CONTEXTS\|atlas.compute\|atlas.api" scripts/hooks/check_module_boundaries.py | head -20
```

If a hardcoded context list exists, add `atlas.intelligence` to it. If contexts are derived from directory structure, no change needed.

- [ ] **Step 6: Commit dependency + hook changes**

```bash
git add pyproject.toml scripts/hooks/check_module_boundaries.py
git commit -m "feat(sp01): add intelligence extras (alphalens-reloaded, statsmodels)"
```

---

## Task 1: Migration 032 — `atlas_signal_ic` table

**Files:**
- Create: `migrations/versions/032_create_signal_ic_table.py`

- [ ] **Step 1: Write the migration**

Create `migrations/versions/032_create_signal_ic_table.py`:

```python
"""SP01: create atlas_signal_ic for storing rolling IC measurements.

One row per (signal_name, timeframe, forward_period_days, rolling_window,
as_of_date). Rolling-window-end-date is the natural key — every window has
its own row, so the time series of IC over time is reconstructible.

Revision ID: 032
Revises: 031
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_signal_ic (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            signal_name             VARCHAR(64) NOT NULL,
            timeframe               VARCHAR(16) NOT NULL,
            forward_period_days     INTEGER     NOT NULL,
            rolling_window          VARCHAR(8)  NOT NULL,
            as_of_date              DATE        NOT NULL,

            n_observations          INTEGER     NOT NULL,
            mean_ic                 NUMERIC(10, 6),
            ic_std                  NUMERIC(10, 6),
            ic_t_stat               NUMERIC(10, 4),
            ic_ir                   NUMERIC(10, 4),
            quantile_spread_ann     NUMERIC(10, 4),
            turnover_monthly        NUMERIC(10, 4),

            computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_signal_ic_run UNIQUE (
                signal_name, timeframe, forward_period_days,
                rolling_window, as_of_date
            ),
            CONSTRAINT chk_signal_ic_period CHECK (forward_period_days > 0),
            CONSTRAINT chk_signal_ic_n_obs CHECK (n_observations >= 0)
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_signal_ic_signal_date
        ON atlas.atlas_signal_ic (signal_name, as_of_date DESC)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_signal_ic_signal_date"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_signal_ic"))
```

- [ ] **Step 2: Run migration locally against Supabase**

```bash
alembic upgrade head 2>&1 | tail -5
```

Expected: `Running upgrade 031 -> 032, SP01: create atlas_signal_ic for storing rolling IC measurements.`

- [ ] **Step 3: Verify table created**

```bash
python -c "
from atlas.db import get_engine
from sqlalchemy import text
eng = get_engine()
with eng.connect() as c:
    rows = c.execute(text(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='atlas' AND table_name='atlas_signal_ic' ORDER BY ordinal_position\")).fetchall()
    for r in rows: print(r)
"
```

Expected: 13 columns listed in the order defined above.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/032_create_signal_ic_table.py
git commit -m "feat(sp01): migration 032 — atlas_signal_ic table"
```

---

## Task 2: State encoding module (pure functions)

**Files:**
- Create: `atlas/intelligence/__init__.py`
- Create: `atlas/intelligence/validation/__init__.py`
- Create: `atlas/intelligence/validation/encoding.py`
- Create: `tests/intelligence/__init__.py`
- Create: `tests/intelligence/validation/__init__.py`
- Create: `tests/intelligence/validation/test_encoding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/validation/test_encoding.py`:

```python
"""Unit tests for state-to-numeric encoding."""

from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.validation.encoding import (
    DIMENSION_WEIGHTS,
    SENTINEL_STATES,
    STATE_ENCODINGS,
    compute_decision_state_score,
    encode_state,
)


class TestEncodeState:
    def test_rs_leader_is_one(self):
        assert encode_state("rs_state", "Leader") == 1.0

    def test_rs_laggard_is_zero(self):
        assert encode_state("rs_state", "Laggard") == 0.0

    def test_momentum_accelerating_is_one(self):
        assert encode_state("momentum_state", "Accelerating") == 1.0

    def test_regime_risk_on_is_one(self):
        assert encode_state("regime_state", "Risk-On") == 1.0

    def test_regime_risk_off_is_zero(self):
        assert encode_state("regime_state", "Risk-Off") == 0.0

    def test_sentinel_returns_none(self):
        assert encode_state("rs_state", "INSUFFICIENT_HISTORY") is None
        assert encode_state("rs_state", "ILLIQUID") is None
        assert encode_state("rs_state", "DISLOCATION_SUSPENDED") is None

    def test_unknown_state_raises(self):
        with pytest.raises(ValueError, match="unknown rs_state"):
            encode_state("rs_state", "Bogus")

    def test_unknown_dimension_raises(self):
        with pytest.raises(KeyError):
            encode_state("nonsense_state", "Leader")


class TestComputeDecisionStateScore:
    def test_all_top_states_give_one(self):
        row = pd.Series({
            "rs_state": "Leader",
            "momentum_state": "Accelerating",
            "risk_state": "Low",
            "volume_state": "Accumulation",
            "sector_state": "Overweight",
            "regime_state": "Risk-On",
        })
        score = compute_decision_state_score(row)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_all_bottom_states_give_zero(self):
        row = pd.Series({
            "rs_state": "Laggard",
            "momentum_state": "Collapsing",
            "risk_state": "High",
            "volume_state": "Heavy Distribution",
            "sector_state": "Avoid",
            "regime_state": "Risk-Off",
        })
        score = compute_decision_state_score(row)
        assert score == pytest.approx(0.0, abs=1e-9)

    def test_any_sentinel_returns_none(self):
        row = pd.Series({
            "rs_state": "INSUFFICIENT_HISTORY",  # one sentinel
            "momentum_state": "Accelerating",
            "risk_state": "Low",
            "volume_state": "Accumulation",
            "sector_state": "Overweight",
            "regime_state": "Risk-On",
        })
        assert compute_decision_state_score(row) is None

    def test_weights_sum_to_one(self):
        assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)

    def test_intermediate_blend(self):
        row = pd.Series({
            "rs_state": "Strong",          # 0.85 × 0.35 = 0.2975
            "momentum_state": "Flat",       # 0.5  × 0.25 = 0.125
            "risk_state": "Normal",         # 0.75 × 0.15 = 0.1125
            "volume_state": "Neutral",      # 0.5  × 0.10 = 0.05
            "sector_state": "Neutral",      # 0.5  × 0.10 = 0.05
            "regime_state": "Constructive", # 0.7  × 0.05 = 0.035
        })
        # Total = 0.67
        score = compute_decision_state_score(row)
        assert score == pytest.approx(0.67, abs=1e-3)

    def test_sentinel_constants_defined(self):
        assert "INSUFFICIENT_HISTORY" in SENTINEL_STATES
        assert "ILLIQUID" in SENTINEL_STATES
        assert "DISLOCATION_SUSPENDED" in SENTINEL_STATES

    def test_all_six_dimensions_have_encodings(self):
        for dim in DIMENSION_WEIGHTS.keys():
            assert dim in STATE_ENCODINGS, f"{dim} missing from STATE_ENCODINGS"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/intelligence/validation/test_encoding.py -v
```

Expected: ImportError or ModuleNotFoundError — `atlas.intelligence.validation.encoding` doesn't exist yet.

- [ ] **Step 3: Create package markers**

Create `atlas/intelligence/__init__.py`:

```python
"""Atlas intelligence layer — graded signals, IC measurement, composites.

This bounded context produces measured, validated outputs from the
deterministic compute layer. It MUST NOT import from atlas.api or atlas.compute
internals — only from the shared kernel (atlas.db, atlas.config).

See docs/phase2/00-master-plan.html for the full Phase 2 design.
"""
```

Create `atlas/intelligence/validation/__init__.py`:

```python
"""Signal validation — Information Coefficient measurement and reporting.

Per Phase 2 sub-project SP01. Public surface:

- encoding: pure state→numeric encoder
- factor_loader: SQL → composite factor DataFrame
- forward_returns: SQL → forward return matrix
- ic_engine: alphalens-driven IC computation
- persistence: writes results to atlas_signal_ic
- report: markdown tearsheet generator
"""

from atlas.intelligence.validation.encoding import (
    DIMENSION_WEIGHTS,
    SENTINEL_STATES,
    STATE_ENCODINGS,
    compute_decision_state_score,
    encode_state,
)

__all__ = [
    "DIMENSION_WEIGHTS",
    "SENTINEL_STATES",
    "STATE_ENCODINGS",
    "compute_decision_state_score",
    "encode_state",
]
```

Create `tests/intelligence/__init__.py` and `tests/intelligence/validation/__init__.py` as empty files:

```bash
touch tests/intelligence/__init__.py tests/intelligence/validation/__init__.py
```

- [ ] **Step 4: Implement `encoding.py`**

Create `atlas/intelligence/validation/encoding.py`:

```python
"""State-to-numeric encoding for the Atlas decision_state composite.

Pure functions. No I/O. No external deps beyond pandas.

The encoding is the V1 hand-set quality scoring. SP04 (Signal Intelligence)
will replace these weights with IC-derived weights from the atlas_signal_ic
table that THIS module populates. Treat these weights as a measurable
starting point, not a permanent choice.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

# Sentinel state values — rows containing any of these are dropped from
# IC measurement. They represent "we couldn't classify this row" not
# "the row should score zero."
SENTINEL_STATES: Final[frozenset[str]] = frozenset({
    "INSUFFICIENT_HISTORY",
    "ILLIQUID",
    "DISLOCATION_SUSPENDED",
})

# Per-dimension state → quality score in [0, 1].
STATE_ENCODINGS: Final[dict[str, dict[str, float]]] = {
    "rs_state": {
        "Leader": 1.0,
        "Strong": 0.85,
        "Consolidating": 0.6,
        "Emerging": 0.55,
        "Average": 0.4,
        "Weak": 0.15,
        "Laggard": 0.0,
    },
    "momentum_state": {
        "Accelerating": 1.0,
        "Improving": 0.75,
        "Flat": 0.5,
        "Deteriorating": 0.25,
        "Collapsing": 0.0,
    },
    "risk_state": {
        "Low": 1.0,
        "Normal": 0.75,
        "Below Trend": 0.5,
        "Elevated": 0.25,
        "High": 0.0,
    },
    "volume_state": {
        "Accumulation": 1.0,
        "Steady-Buying": 0.75,
        "Neutral": 0.5,
        "Distribution": 0.25,
        "Heavy Distribution": 0.0,
    },
    "sector_state": {
        "Overweight": 1.0,
        "Neutral": 0.5,
        "Underweight": 0.25,
        "Avoid": 0.0,
    },
    "regime_state": {
        "Risk-On": 1.0,
        "Constructive": 0.7,
        "Cautious": 0.4,
        "Risk-Off": 0.0,
    },
}

# Dimension weights in the composite. Sum to 1.0.
DIMENSION_WEIGHTS: Final[dict[str, float]] = {
    "rs_state": 0.35,
    "momentum_state": 0.25,
    "risk_state": 0.15,
    "volume_state": 0.10,
    "sector_state": 0.10,
    "regime_state": 0.05,
}


def encode_state(dimension: str, value: str) -> float | None:
    """Encode a categorical state value to its [0,1] quality score.

    Returns None for sentinel states (the row should be dropped).
    Raises KeyError for unknown dimensions.
    Raises ValueError for unknown state values within a known dimension.
    """
    if value in SENTINEL_STATES:
        return None
    encoding = STATE_ENCODINGS[dimension]  # KeyError on unknown dimension
    if value not in encoding:
        raise ValueError(f"unknown {dimension} value: {value!r}")
    return encoding[value]


def compute_decision_state_score(row: pd.Series) -> float | None:
    """Compute the composite decision_state score for one (instrument, date) row.

    Returns None if any required dimension is a sentinel state.
    Returns float in [0, 1] otherwise.
    """
    total = 0.0
    for dimension, weight in DIMENSION_WEIGHTS.items():
        value = row[dimension]
        encoded = encode_state(dimension, value)
        if encoded is None:
            return None
        total += weight * encoded
    return total
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/intelligence/validation/test_encoding.py -v
```

Expected: 13 passed.

- [ ] **Step 6: Commit**

```bash
git add atlas/intelligence/ tests/intelligence/
git commit -m "feat(sp01): state encoding + decision_state_score composite"
```

---

## Task 3: Factor loader — SQL → composite factor DataFrame

**Files:**
- Create: `atlas/intelligence/validation/factor_loader.py`
- Create: `tests/intelligence/validation/test_factor_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/validation/test_factor_loader.py`:

```python
"""Tests for factor_loader. Uses real DB connection — integration-tier."""

from datetime import date

import pandas as pd
import pytest

from atlas.db import get_engine
from atlas.intelligence.validation.factor_loader import load_decision_state_factor


@pytest.mark.integration
class TestLoadDecisionStateFactor:
    def test_returns_multiindex_dataframe(self):
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        # MultiIndex (date, instrument_id)
        assert isinstance(df.index, pd.MultiIndex)
        assert df.index.names == ["date", "instrument_id"]
        assert "factor" in df.columns

    def test_factor_in_unit_interval(self):
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert df["factor"].min() >= 0.0 - 1e-9
        assert df["factor"].max() <= 1.0 + 1e-9
        assert df["factor"].notna().all()  # sentinels already dropped

    def test_empty_range_returns_empty_df(self):
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(1990, 1, 1),
            end_date=date(1990, 1, 2),
        )
        assert len(df) == 0
        assert "factor" in df.columns

    def test_universe_filter_applies(self):
        """If a universe_filter is passed, only those instruments appear."""
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            universe_filter=["DUMMY_NON_EXISTENT_ID"],
        )
        assert len(df) == 0
```

- [ ] **Step 2: Run test — expect failure (module missing)**

```bash
pytest tests/intelligence/validation/test_factor_loader.py -v -m integration
```

Expected: ImportError.

- [ ] **Step 3: Implement `factor_loader.py`**

Create `atlas/intelligence/validation/factor_loader.py`:

```python
"""Factor loader — joins state tables and computes the decision_state composite.

Reads:
  atlas.atlas_stock_states_daily   (rs/momentum/risk/volume per stock per date)
  atlas.atlas_sector_states_daily  (sector_state per sector per date)
  atlas.atlas_market_regime_daily  (regime_state per date)
  atlas.atlas_universe_stocks      (instrument_id → sector_name mapping)

Output: DataFrame indexed by (date, instrument_id) with single column 'factor'.
Sentinel rows are dropped.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.encoding import compute_decision_state_score

log = structlog.get_logger()

# Limit to one query — joins handle the assembly. Universe filter is optional.
_LOAD_SQL = """
    SELECT
        s.date,
        s.instrument_id,
        s.rs_state,
        s.momentum_state,
        s.risk_state,
        s.volume_state,
        COALESCE(sec.sector_state, 'Neutral') AS sector_state,
        COALESCE(reg.regime_state, 'Constructive') AS regime_state
    FROM atlas.atlas_stock_states_daily s
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = s.instrument_id
    LEFT JOIN atlas.atlas_sector_states_daily sec
           ON sec.sector_name = u.sector_name
          AND sec.date = s.date
    LEFT JOIN atlas.atlas_market_regime_daily reg
           ON reg.date = s.date
    WHERE s.date >= :start_date
      AND s.date <= :end_date
"""

_LOAD_SQL_WITH_UNIVERSE = _LOAD_SQL + "\n      AND s.instrument_id = ANY(:universe)"


def load_decision_state_factor(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    universe_filter: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Load (date, instrument_id) → decision_state_score factor DataFrame.

    Drops rows where any dimension is a sentinel state. Returns empty
    DataFrame if no rows match the date range or universe filter.
    """
    if universe_filter is not None:
        sql = _LOAD_SQL_WITH_UNIVERSE
        params: dict = {
            "start_date": start_date,
            "end_date": end_date,
            "universe": list(universe_filter),
        }
    else:
        sql = _LOAD_SQL
        params = {"start_date": start_date, "end_date": end_date}

    with engine.connect() as conn:
        raw = pd.read_sql(text(sql), conn, params=params)

    if raw.empty:
        return pd.DataFrame(columns=["factor"]).set_index(
            pd.MultiIndex.from_arrays([[], []], names=["date", "instrument_id"])
        )

    # Compute the composite. Sentinels → None → dropped.
    raw["factor"] = raw.apply(compute_decision_state_score, axis=1)
    n_before = len(raw)
    cleaned = raw.dropna(subset=["factor"]).copy()
    n_after = len(cleaned)
    log.info(
        "decision_state_factor_loaded",
        n_raw=n_before,
        n_after_sentinel_drop=n_after,
        date_range=f"{start_date}..{end_date}",
        universe_filter_applied=universe_filter is not None,
    )

    cleaned = cleaned[["date", "instrument_id", "factor"]]
    cleaned["date"] = pd.to_datetime(cleaned["date"])
    return cleaned.set_index(["date", "instrument_id"])
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/intelligence/validation/test_factor_loader.py -v -m integration
```

Expected: 4 passed. (The test relies on real data in `atlas_stock_states_daily` for Jan 2025 — if EC2 hasn't backfilled that period, adjust the test date range to a known-populated month from `M3 PRD memory file project_m3_state.md`.)

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/validation/factor_loader.py tests/intelligence/validation/test_factor_loader.py
git commit -m "feat(sp01): factor loader — composite decision_state factor from state tables"
```

---

## Task 4: Forward returns loader

**Files:**
- Create: `atlas/intelligence/validation/forward_returns.py`
- Create: `tests/intelligence/validation/test_forward_returns.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/validation/test_forward_returns.py`:

```python
"""Tests for forward returns matrix."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from atlas.db import get_engine
from atlas.intelligence.validation.forward_returns import load_price_matrix, compute_forward_returns


@pytest.mark.integration
class TestLoadPriceMatrix:
    def test_returns_wide_matrix(self):
        eng = get_engine()
        df = load_price_matrix(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )
        # Wide format: dates as index, instruments as columns
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.shape[1] > 0  # at least one instrument
        assert df.shape[0] > 30  # at least 30 trading days in 3 months

    def test_prices_are_positive(self):
        eng = get_engine()
        df = load_price_matrix(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        # Allow NaN (instruments not trading) but no zero/negative
        non_null = df.stack()
        assert (non_null > 0).all()


class TestComputeForwardReturns:
    def test_simple_5_day_return(self):
        """If price doubles in 5 days, forward return is 1.0."""
        dates = pd.date_range("2025-01-01", periods=10, freq="B")
        prices = pd.Series([100, 100, 100, 100, 100, 200, 200, 200, 200, 200], index=dates)
        df = pd.DataFrame({"A": prices})
        fwd = compute_forward_returns(df, periods=[5])
        # On day 0, price[0]=100 and price[5]=200 → return = 1.0
        assert fwd.loc[dates[0], ("return_5d", "A")] == pytest.approx(1.0, abs=1e-9)

    def test_nan_for_insufficient_lookahead(self):
        """Last N rows have NaN because the lookahead window extends past data."""
        dates = pd.date_range("2025-01-01", periods=10, freq="B")
        prices = pd.Series(range(100, 110), index=dates)
        df = pd.DataFrame({"A": prices})
        fwd = compute_forward_returns(df, periods=[5])
        # Last 5 rows should be NaN for return_5d
        assert fwd.loc[dates[-5:], ("return_5d", "A")].isna().all()

    def test_multi_period_columns(self):
        dates = pd.date_range("2025-01-01", periods=70, freq="B")
        df = pd.DataFrame({"A": np.linspace(100, 200, 70)}, index=dates)
        fwd = compute_forward_returns(df, periods=[5, 21, 63])
        # MultiIndex columns: (period, instrument)
        assert ("return_5d", "A") in fwd.columns
        assert ("return_21d", "A") in fwd.columns
        assert ("return_63d", "A") in fwd.columns
```

- [ ] **Step 2: Run test — expect import failure**

```bash
pytest tests/intelligence/validation/test_forward_returns.py -v
```

- [ ] **Step 3: Implement `forward_returns.py`**

Create `atlas/intelligence/validation/forward_returns.py`:

```python
"""Forward-returns matrix builder.

Reads atlas.atlas_stock_metrics_daily.close_approx into a wide
(date × instrument) DataFrame, then computes simple percentage forward
returns over the requested horizons.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

_PRICE_SQL = """
    SELECT date, instrument_id, close_approx
    FROM atlas.atlas_stock_metrics_daily
    WHERE date >= :start_date
      AND date <= :end_date
    ORDER BY date
"""


def load_price_matrix(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load close_approx into a wide DataFrame: rows=dates, columns=instruments."""
    with engine.connect() as conn:
        long_df = pd.read_sql(text(_PRICE_SQL), conn, params={
            "start_date": start_date,
            "end_date": end_date,
        })
    if long_df.empty:
        return pd.DataFrame()
    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df["close_approx"] = pd.to_numeric(long_df["close_approx"])
    wide = long_df.pivot(index="date", columns="instrument_id", values="close_approx")
    log.info(
        "price_matrix_loaded",
        n_dates=wide.shape[0],
        n_instruments=wide.shape[1],
        date_range=f"{start_date}..{end_date}",
    )
    return wide


def compute_forward_returns(
    prices: pd.DataFrame,
    *,
    periods: Sequence[int],
) -> pd.DataFrame:
    """Compute forward returns for each (date, instrument) over each period.

    Returns a DataFrame with a MultiIndex column:
      level 0 = "return_{N}d"
      level 1 = instrument_id

    Last N rows of each instrument are NaN where lookahead extends past data.
    """
    frames: list[pd.DataFrame] = []
    for n in periods:
        fwd = prices.shift(-n) / prices - 1.0
        fwd.columns = pd.MultiIndex.from_product([[f"return_{n}d"], fwd.columns])
        frames.append(fwd)
    return pd.concat(frames, axis=1)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/intelligence/validation/test_forward_returns.py -v
```

Expected: 5 passed (2 integration if marked, 3 unit).

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/validation/forward_returns.py tests/intelligence/validation/test_forward_returns.py
git commit -m "feat(sp01): forward returns matrix + price-matrix loader"
```

---

## Task 5: IC engine — alphalens-driven IC + rolling windows

**Files:**
- Create: `atlas/intelligence/validation/ic_engine.py`
- Create: `tests/intelligence/validation/test_ic_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/validation/test_ic_engine.py`:

```python
"""Tests for the IC engine — pure pandas, no DB."""

import numpy as np
import pandas as pd
import pytest

from atlas.intelligence.validation.ic_engine import (
    ICResult,
    compute_ic_over_window,
    compute_rolling_ic,
    compute_quantile_spread,
    compute_turnover,
)


@pytest.fixture
def perfect_signal():
    """Factor exactly equal to forward return — IC should be 1.0."""
    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    instruments = [f"INST{i:03d}" for i in range(50)]
    np.random.seed(42)
    factor_data = []
    return_data = []
    for d in dates:
        for inst in instruments:
            x = np.random.randn()
            factor_data.append((d, inst, x))
            return_data.append((d, inst, x))
    factor_df = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"])
    factor_df = factor_df.set_index(["date", "instrument_id"])
    returns_df = pd.DataFrame(return_data, columns=["date", "instrument_id", "ret"])
    returns_wide = returns_df.pivot(index="date", columns="instrument_id", values="ret")
    return factor_df, returns_wide


@pytest.fixture
def noise_signal():
    """Factor uncorrelated with returns — IC should be ≈ 0."""
    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    instruments = [f"INST{i:03d}" for i in range(50)]
    np.random.seed(42)
    factor_data = []
    return_data = []
    for d in dates:
        for inst in instruments:
            factor_data.append((d, inst, np.random.randn()))
            return_data.append((d, inst, np.random.randn()))
    factor_df = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"])
    factor_df = factor_df.set_index(["date", "instrument_id"])
    returns_df = pd.DataFrame(return_data, columns=["date", "instrument_id", "ret"])
    returns_wide = returns_df.pivot(index="date", columns="instrument_id", values="ret")
    return factor_df, returns_wide


class TestComputeICOverWindow:
    def test_perfect_signal_gives_ic_one(self, perfect_signal):
        factor, returns = perfect_signal
        result = compute_ic_over_window(factor, returns)
        assert result.mean_ic == pytest.approx(1.0, abs=1e-6)

    def test_noise_signal_gives_ic_near_zero(self, noise_signal):
        factor, returns = noise_signal
        result = compute_ic_over_window(factor, returns)
        assert abs(result.mean_ic) < 0.1  # noise — should be near zero

    def test_returns_icresult_dataclass(self, noise_signal):
        factor, returns = noise_signal
        result = compute_ic_over_window(factor, returns)
        assert isinstance(result, ICResult)
        assert hasattr(result, "mean_ic")
        assert hasattr(result, "ic_std")
        assert hasattr(result, "ic_t_stat")
        assert hasattr(result, "n_observations")


class TestComputeRollingIC:
    def test_returns_one_row_per_window(self, noise_signal):
        factor, returns = noise_signal
        results = compute_rolling_ic(factor, returns, window_days=20, step_days=5)
        # 60 days, window 20, step 5 → roughly (60-20)/5+1 = 9 windows
        assert len(results) >= 7


class TestComputeQuantileSpread:
    def test_perfect_signal_has_positive_spread(self, perfect_signal):
        factor, returns = perfect_signal
        spread = compute_quantile_spread(factor, returns, n_quantiles=5)
        assert spread > 0.0


class TestComputeTurnover:
    def test_stable_signal_has_low_turnover(self):
        """If quintile membership doesn't change, turnover is 0."""
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        factor_data = []
        for d in dates:
            for i in range(10):
                # Same scores every day → same quintiles
                factor_data.append((d, f"INST{i:02d}", float(i)))
        factor = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"]).set_index(["date", "instrument_id"])
        turnover = compute_turnover(factor, n_quantiles=5)
        assert turnover < 0.05  # essentially zero
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/intelligence/validation/test_ic_engine.py -v
```

- [ ] **Step 3: Implement `ic_engine.py`**

Create `atlas/intelligence/validation/ic_engine.py`:

```python
"""IC computation engine.

Pure pandas — no I/O. Wraps alphalens for the heavy lifting (quantile bucketing,
IC calculation) and adds Atlas-specific rolling-window aggregation and turnover.

Reference: alphalens.utils.get_clean_factor_and_forward_returns,
alphalens.performance.factor_information_coefficient,
alphalens.performance.factor_returns
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog
from scipy import stats

log = structlog.get_logger()


@dataclass(frozen=True)
class ICResult:
    """One IC observation across a window."""
    mean_ic: float
    ic_std: float
    ic_t_stat: float
    n_observations: int
    window_start: pd.Timestamp | None = None
    window_end: pd.Timestamp | None = None


def _align_factor_to_returns(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
) -> pd.DataFrame:
    """Align (date, instrument_id) MultiIndex factor to wide returns DataFrame.

    Returns long DataFrame with columns: factor, fwd_return, indexed by (date, instrument_id).
    Drops rows where either is NaN.
    """
    long_returns = returns_wide.stack()
    long_returns.name = "fwd_return"
    long_returns.index = long_returns.index.set_names(["date", "instrument_id"])

    aligned = factor.join(long_returns, how="inner")
    return aligned.dropna(subset=["factor", "fwd_return"])


def compute_ic_over_window(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
) -> ICResult:
    """Compute IC (Spearman rank correlation) per date across instruments,
    then return the mean and t-stat across dates.

    factor: MultiIndex (date, instrument_id), column 'factor'
    returns_wide: DataFrame indexed by date, instruments as columns
    """
    aligned = _align_factor_to_returns(factor, returns_wide)

    if aligned.empty:
        return ICResult(mean_ic=float("nan"), ic_std=float("nan"),
                        ic_t_stat=float("nan"), n_observations=0)

    # Per-date Spearman rank correlation between factor and forward return
    ic_per_date = aligned.groupby(level="date").apply(
        lambda g: stats.spearmanr(g["factor"], g["fwd_return"]).statistic
        if len(g) >= 5 else float("nan")
    )
    ic_per_date = ic_per_date.dropna()

    if len(ic_per_date) < 2:
        return ICResult(mean_ic=float("nan"), ic_std=float("nan"),
                        ic_t_stat=float("nan"), n_observations=len(ic_per_date))

    mean_ic = float(ic_per_date.mean())
    ic_std = float(ic_per_date.std(ddof=1))
    t_stat = mean_ic / (ic_std / np.sqrt(len(ic_per_date))) if ic_std > 0 else float("nan")

    return ICResult(
        mean_ic=mean_ic,
        ic_std=ic_std,
        ic_t_stat=t_stat,
        n_observations=int(len(ic_per_date)),
        window_start=ic_per_date.index.min(),
        window_end=ic_per_date.index.max(),
    )


def compute_rolling_ic(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
    *,
    window_days: int,
    step_days: int = 21,
) -> list[ICResult]:
    """Compute IC over rolling windows. Returns one ICResult per window."""
    all_dates = factor.index.get_level_values("date").unique().sort_values()
    if len(all_dates) < window_days:
        return []

    results: list[ICResult] = []
    start_i = 0
    while start_i + window_days <= len(all_dates):
        window_dates = all_dates[start_i : start_i + window_days]
        window_factor = factor.loc[window_dates]
        window_returns = returns_wide.loc[returns_wide.index.intersection(window_dates)]
        results.append(compute_ic_over_window(window_factor, window_returns))
        start_i += step_days

    return results


def compute_quantile_spread(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
    *,
    n_quantiles: int = 5,
) -> float:
    """Compute Q_top − Q_bottom mean forward return, annualized to 252 days.

    Quantiles are computed per date (cross-sectional bucketing).
    """
    aligned = _align_factor_to_returns(factor, returns_wide)
    if aligned.empty:
        return float("nan")

    def _bucket(group: pd.DataFrame) -> pd.DataFrame:
        try:
            group = group.copy()
            group["quantile"] = pd.qcut(
                group["factor"], q=n_quantiles, labels=False, duplicates="drop"
            )
            return group
        except ValueError:
            group = group.copy()
            group["quantile"] = np.nan
            return group

    bucketed = aligned.groupby(level="date", group_keys=False).apply(_bucket).dropna(subset=["quantile"])
    if bucketed.empty:
        return float("nan")

    top = bucketed[bucketed["quantile"] == n_quantiles - 1]["fwd_return"].mean()
    bot = bucketed[bucketed["quantile"] == 0]["fwd_return"].mean()

    # Spread per period. Caller knows the period; annualization assumes
    # 21-trading-day returns by convention here (caller can rescale).
    return float(top - bot)


def compute_turnover(
    factor: pd.DataFrame,
    *,
    n_quantiles: int = 5,
) -> float:
    """Average fraction of instruments that change top-quintile membership day-over-day.

    Returns monthly turnover (multiplied by 21 trading days).
    """
    quantiles: list[pd.Series] = []
    dates_sorted = factor.index.get_level_values("date").unique().sort_values()
    for d in dates_sorted:
        snapshot = factor.loc[d]
        if len(snapshot) < n_quantiles:
            continue
        try:
            q = pd.qcut(snapshot["factor"], q=n_quantiles, labels=False, duplicates="drop")
            top = set(q[q == n_quantiles - 1].index.tolist())
            quantiles.append(pd.Series({"date": d, "top": top}))
        except ValueError:
            continue

    if len(quantiles) < 2:
        return float("nan")

    deltas: list[float] = []
    for prev, curr in zip(quantiles[:-1], quantiles[1:], strict=False):
        prev_set, curr_set = prev["top"], curr["top"]
        if not prev_set:
            continue
        added = len(curr_set - prev_set)
        deltas.append(added / max(1, len(prev_set)))

    if not deltas:
        return float("nan")

    daily_turnover = float(np.mean(deltas))
    return daily_turnover * 21.0
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/intelligence/validation/test_ic_engine.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/validation/ic_engine.py tests/intelligence/validation/test_ic_engine.py
git commit -m "feat(sp01): IC engine — rolling Spearman IC + quantile spread + turnover"
```

---

## Task 6: Persistence layer — write to `atlas_signal_ic`

**Files:**
- Create: `atlas/intelligence/validation/persistence.py`
- Create: `tests/intelligence/validation/test_persistence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/validation/test_persistence.py`:

```python
"""Tests for atlas_signal_ic persistence."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.validation.ic_engine import ICResult
from atlas.intelligence.validation.persistence import (
    persist_ic_result,
    delete_run,
)


@pytest.mark.integration
class TestPersistICResult:
    @pytest.fixture(autouse=True)
    def clean_test_rows(self):
        """Clean up any prior test rows before and after each test."""
        eng = get_engine()
        with eng.connect() as c:
            c.execute(text("DELETE FROM atlas.atlas_signal_ic WHERE signal_name = 'test_signal'"))
            c.commit()
        yield
        with eng.connect() as c:
            c.execute(text("DELETE FROM atlas.atlas_signal_ic WHERE signal_name = 'test_signal'"))
            c.commit()

    def test_inserts_one_row(self):
        eng = get_engine()
        result = ICResult(
            mean_ic=0.067,
            ic_std=0.12,
            ic_t_stat=2.3,
            n_observations=126,
        )
        persist_ic_result(
            engine=eng,
            signal_name="test_signal",
            timeframe="daily",
            forward_period_days=21,
            rolling_window="6M",
            as_of=date(2025, 6, 30),
            result=result,
            quantile_spread_ann=0.085,
            turnover_monthly=0.28,
        )
        with eng.connect() as c:
            row = c.execute(text("""
                SELECT signal_name, forward_period_days, mean_ic, ic_t_stat
                FROM atlas.atlas_signal_ic
                WHERE signal_name = 'test_signal'
            """)).fetchone()
        assert row is not None
        assert row[0] == "test_signal"
        assert row[1] == 21
        assert float(row[2]) == pytest.approx(0.067, abs=1e-6)
        assert float(row[3]) == pytest.approx(2.3, abs=1e-4)

    def test_upsert_on_duplicate_key(self):
        """Inserting the same (signal, period, window, as_of) twice updates instead of failing."""
        eng = get_engine()
        result1 = ICResult(mean_ic=0.05, ic_std=0.1, ic_t_stat=2.0, n_observations=100)
        result2 = ICResult(mean_ic=0.08, ic_std=0.12, ic_t_stat=2.5, n_observations=120)

        persist_ic_result(
            engine=eng, signal_name="test_signal", timeframe="daily",
            forward_period_days=21, rolling_window="6M",
            as_of=date(2025, 6, 30), result=result1,
            quantile_spread_ann=0.05, turnover_monthly=0.30,
        )
        persist_ic_result(
            engine=eng, signal_name="test_signal", timeframe="daily",
            forward_period_days=21, rolling_window="6M",
            as_of=date(2025, 6, 30), result=result2,
            quantile_spread_ann=0.09, turnover_monthly=0.25,
        )

        with eng.connect() as c:
            row = c.execute(text("""
                SELECT mean_ic, n_observations FROM atlas.atlas_signal_ic
                WHERE signal_name='test_signal'
            """)).fetchone()
        # Second call should have overwritten
        assert float(row[0]) == pytest.approx(0.08, abs=1e-6)
        assert row[1] == 120
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/intelligence/validation/test_persistence.py -v -m integration
```

- [ ] **Step 3: Implement `persistence.py`**

Create `atlas/intelligence/validation/persistence.py`:

```python
"""Persist IC results to atlas.atlas_signal_ic.

UPSERT semantics on the natural key
(signal_name, timeframe, forward_period_days, rolling_window, as_of_date)
— re-running a window overwrites the prior row.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.ic_engine import ICResult

log = structlog.get_logger()

_UPSERT_SQL = """
    INSERT INTO atlas.atlas_signal_ic (
        signal_name, timeframe, forward_period_days, rolling_window,
        as_of_date, n_observations, mean_ic, ic_std, ic_t_stat, ic_ir,
        quantile_spread_ann, turnover_monthly
    ) VALUES (
        :signal_name, :timeframe, :forward_period_days, :rolling_window,
        :as_of_date, :n_observations, :mean_ic, :ic_std, :ic_t_stat, :ic_ir,
        :quantile_spread_ann, :turnover_monthly
    )
    ON CONFLICT (signal_name, timeframe, forward_period_days,
                 rolling_window, as_of_date)
    DO UPDATE SET
        n_observations       = EXCLUDED.n_observations,
        mean_ic              = EXCLUDED.mean_ic,
        ic_std               = EXCLUDED.ic_std,
        ic_t_stat            = EXCLUDED.ic_t_stat,
        ic_ir                = EXCLUDED.ic_ir,
        quantile_spread_ann  = EXCLUDED.quantile_spread_ann,
        turnover_monthly     = EXCLUDED.turnover_monthly,
        updated_at           = NOW()
"""


def persist_ic_result(
    engine: Engine,
    *,
    signal_name: str,
    timeframe: str,
    forward_period_days: int,
    rolling_window: str,
    as_of: date,
    result: ICResult,
    quantile_spread_ann: float,
    turnover_monthly: float,
) -> None:
    """UPSERT one IC result row."""
    ic_ir = (
        result.mean_ic / result.ic_std
        if result.ic_std and result.ic_std > 0 else None
    )
    params = {
        "signal_name": signal_name,
        "timeframe": timeframe,
        "forward_period_days": forward_period_days,
        "rolling_window": rolling_window,
        "as_of_date": as_of,
        "n_observations": result.n_observations,
        "mean_ic": _nan_to_none(result.mean_ic),
        "ic_std": _nan_to_none(result.ic_std),
        "ic_t_stat": _nan_to_none(result.ic_t_stat),
        "ic_ir": _nan_to_none(ic_ir),
        "quantile_spread_ann": _nan_to_none(quantile_spread_ann),
        "turnover_monthly": _nan_to_none(turnover_monthly),
    }
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), params)
    log.info(
        "signal_ic_persisted",
        signal=signal_name,
        period_days=forward_period_days,
        as_of=as_of.isoformat(),
        mean_ic=result.mean_ic,
    )


def delete_run(engine: Engine, *, signal_name: str) -> int:
    """Delete all rows for a signal_name. Returns row count deleted."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM atlas.atlas_signal_ic WHERE signal_name = :s"),
            {"s": signal_name},
        )
        return int(result.rowcount or 0)


def _nan_to_none(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        if x != x:  # NaN check
            return None
    except TypeError:
        return None
    return x
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/intelligence/validation/test_persistence.py -v -m integration
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/validation/persistence.py tests/intelligence/validation/test_persistence.py
git commit -m "feat(sp01): persistence — UPSERT IC results to atlas_signal_ic"
```

---

## Task 7: Markdown report generator

**Files:**
- Create: `atlas/intelligence/validation/report.py`
- Create: `tests/intelligence/validation/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/validation/test_report.py`:

```python
"""Tests for markdown report generation."""

from datetime import date

from atlas.intelligence.validation.ic_engine import ICResult
from atlas.intelligence.validation.report import build_tearsheet_markdown


def test_tearsheet_includes_signal_name():
    results_by_period = {
        5:  (ICResult(mean_ic=0.03, ic_std=0.10, ic_t_stat=1.5, n_observations=126), 0.04, 0.32),
        21: (ICResult(mean_ic=0.07, ic_std=0.12, ic_t_stat=2.4, n_observations=126), 0.09, 0.28),
        63: (ICResult(mean_ic=0.05, ic_std=0.11, ic_t_stat=1.9, n_observations=126), 0.06, 0.22),
    }
    md = build_tearsheet_markdown(
        signal_name="decision_state",
        rolling_window="6M",
        as_of=date(2026, 5, 11),
        results_by_period=results_by_period,
    )
    assert "decision_state" in md
    assert "6M" in md
    assert "2026-05-11" in md


def test_tearsheet_flags_success_criteria():
    results_by_period = {
        21: (ICResult(mean_ic=0.07, ic_std=0.12, ic_t_stat=2.4, n_observations=126), 0.09, 0.28),
    }
    md = build_tearsheet_markdown(
        signal_name="decision_state",
        rolling_window="6M",
        as_of=date(2026, 5, 11),
        results_by_period=results_by_period,
    )
    # Should flag pass on the 21d row (IC > 0.05, t > 2.0, spread > 8%, turnover < 30%)
    assert "PASS" in md or "✓" in md


def test_tearsheet_flags_failures():
    results_by_period = {
        21: (ICResult(mean_ic=0.01, ic_std=0.20, ic_t_stat=0.5, n_observations=50), 0.02, 0.45),
    }
    md = build_tearsheet_markdown(
        signal_name="decision_state",
        rolling_window="6M",
        as_of=date(2026, 5, 11),
        results_by_period=results_by_period,
    )
    assert "FAIL" in md or "✗" in md
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/intelligence/validation/test_report.py -v
```

- [ ] **Step 3: Implement `report.py`**

Create `atlas/intelligence/validation/report.py`:

```python
"""Markdown tearsheet generator for signal validation runs.

One section per forward period. Each section reports mean IC, IC t-stat,
quantile spread, turnover, and PASS/FAIL against SP01 success criteria.
"""

from __future__ import annotations

from datetime import date

from atlas.intelligence.validation.ic_engine import ICResult

# SP01 success criteria — see docs/phase2/00-master-plan.html
_CRITERIA = {
    "mean_ic_min": 0.05,
    "ic_t_stat_min": 2.0,
    "quantile_spread_ann_min": 0.08,
    "turnover_monthly_max": 0.30,
}


def build_tearsheet_markdown(
    *,
    signal_name: str,
    rolling_window: str,
    as_of: date,
    results_by_period: dict[int, tuple[ICResult, float, float]],
) -> str:
    """Render a markdown tearsheet.

    results_by_period: {period_days: (ICResult, quantile_spread, turnover_monthly)}
    """
    lines: list[str] = []
    lines.append(f"# Signal Validation — {signal_name}")
    lines.append("")
    lines.append(f"**As of:** {as_of.isoformat()}")
    lines.append(f"**Rolling window:** {rolling_window}")
    lines.append("")
    lines.append("## Summary by forward period")
    lines.append("")
    lines.append("| Period | Mean IC | IC t-stat | Q-spread (ann) | Turnover/mo | N obs | Verdict |")
    lines.append("|---|---|---|---|---|---|---|")

    for period_days in sorted(results_by_period.keys()):
        ic_result, spread, turnover = results_by_period[period_days]
        verdict = _verdict(ic_result, spread, turnover)
        lines.append(
            f"| {period_days}d | {_fmt(ic_result.mean_ic)} | {_fmt(ic_result.ic_t_stat)} | "
            f"{_fmt(spread)} | {_fmt(turnover)} | {ic_result.n_observations} | {verdict} |"
        )

    lines.append("")
    lines.append("## SP01 success criteria")
    lines.append("")
    lines.append(f"- mean IC ≥ {_CRITERIA['mean_ic_min']:.2f}")
    lines.append(f"- IC t-stat ≥ {_CRITERIA['ic_t_stat_min']:.1f}")
    lines.append(f"- Quantile spread (Q_top − Q_bot) annualized ≥ {_CRITERIA['quantile_spread_ann_min']:.2%}")
    lines.append(f"- Turnover monthly ≤ {_CRITERIA['turnover_monthly_max']:.0%}")
    lines.append("")
    lines.append("> If criteria fail, the answer is informative, not a failure. It drives SP04 redesign.")
    lines.append("")

    return "\n".join(lines)


def _verdict(ic: ICResult, spread: float, turnover: float) -> str:
    passed = (
        ic.mean_ic >= _CRITERIA["mean_ic_min"]
        and ic.ic_t_stat >= _CRITERIA["ic_t_stat_min"]
        and spread >= _CRITERIA["quantile_spread_ann_min"]
        and turnover <= _CRITERIA["turnover_monthly_max"]
    )
    return "PASS ✓" if passed else "FAIL ✗"


def _fmt(x: float) -> str:
    try:
        if x != x:  # NaN
            return "—"
        return f"{x:.4f}"
    except (TypeError, ValueError):
        return "—"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/intelligence/validation/test_report.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/validation/report.py tests/intelligence/validation/test_report.py
git commit -m "feat(sp01): markdown tearsheet generator with PASS/FAIL verdict"
```

---

## Task 8: CLI orchestrator — `scripts/run_signal_validation.py`

**Files:**
- Create: `scripts/run_signal_validation.py`
- Create: `tests/intelligence/validation/test_cli_smoke.py`

- [ ] **Step 1: Write the CLI**

Create `scripts/run_signal_validation.py`:

```python
"""CLI: run signal validation for a given signal across forward periods.

Usage:
  python scripts/run_signal_validation.py \\
      --signal decision_state \\
      --periods 5,21,63 \\
      --rolling-window 6M \\
      --start 2020-01-01 \\
      --end 2026-05-01 \\
      --output output/validation/decision_state_2026-05-11.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import structlog

from atlas.db import get_engine
from atlas.intelligence.validation.factor_loader import load_decision_state_factor
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import (
    compute_ic_over_window,
    compute_quantile_spread,
    compute_turnover,
)
from atlas.intelligence.validation.persistence import persist_ic_result
from atlas.intelligence.validation.report import build_tearsheet_markdown

log = structlog.get_logger()

# Map rolling-window strings to trading-day counts.
_ROLLING_WINDOW_DAYS = {"3M": 63, "6M": 126, "12M": 252, "24M": 504}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--signal", required=True, help="signal name, e.g. decision_state")
    p.add_argument("--periods", required=True, help="comma-separated, e.g. 5,21,63")
    p.add_argument("--rolling-window", default="6M", choices=list(_ROLLING_WINDOW_DAYS))
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--output", required=True, help="markdown tearsheet path")
    p.add_argument("--persist", action="store_true",
                   help="write results to atlas_signal_ic (default: dry run)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    periods = [int(x) for x in args.periods.split(",")]
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    window_days = _ROLLING_WINDOW_DAYS[args.rolling_window]

    if args.signal != "decision_state":
        log.error("only_decision_state_supported_in_v1", signal=args.signal)
        return 2

    log.info("validation_run_started",
             signal=args.signal, periods=periods,
             rolling_window=args.rolling_window, start=str(start), end=str(end))

    engine = get_engine()

    # 1. Load factor
    factor = load_decision_state_factor(engine=engine, start_date=start, end_date=end)
    if factor.empty:
        log.error("no_factor_data_in_range")
        return 3

    # 2. Load prices and compute forward returns
    prices = load_price_matrix(engine=engine, start_date=start, end_date=end)
    if prices.empty:
        log.error("no_price_data_in_range")
        return 3
    fwd_returns_all = compute_forward_returns(prices, periods=periods)

    # 3. For each forward period, compute IC + spread + turnover on the latest window
    results_by_period: dict[int, tuple] = {}
    for period_days in periods:
        # Extract the single-period forward returns as a wide matrix
        period_returns = fwd_returns_all[f"return_{period_days}d"]

        # Use the most recent rolling window
        all_dates = sorted(factor.index.get_level_values("date").unique())
        if len(all_dates) < window_days:
            log.warning("insufficient_history_for_window",
                        n_dates=len(all_dates), window_days=window_days)
            continue
        window_dates = all_dates[-window_days:]
        window_factor = factor.loc[window_dates]
        window_returns = period_returns.loc[period_returns.index.intersection(window_dates)]

        ic_result = compute_ic_over_window(window_factor, window_returns)
        spread = compute_quantile_spread(window_factor, window_returns, n_quantiles=5)
        turnover = compute_turnover(window_factor, n_quantiles=5)

        # Annualize the spread roughly: assume the period IS the holding period
        spread_ann = spread * (252.0 / period_days) if spread == spread else float("nan")

        results_by_period[period_days] = (ic_result, spread_ann, turnover)

        if args.persist:
            persist_ic_result(
                engine=engine,
                signal_name=args.signal,
                timeframe="daily",
                forward_period_days=period_days,
                rolling_window=args.rolling_window,
                as_of=end,
                result=ic_result,
                quantile_spread_ann=spread_ann,
                turnover_monthly=turnover,
            )

    # 4. Write markdown tearsheet
    md = build_tearsheet_markdown(
        signal_name=args.signal,
        rolling_window=args.rolling_window,
        as_of=end,
        results_by_period=results_by_period,
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    log.info("validation_run_complete", output=str(out_path), n_periods=len(results_by_period))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write a smoke test for the CLI**

Create `tests/intelligence/validation/test_cli_smoke.py`:

```python
"""Smoke test: invoke the CLI end-to-end and verify the markdown file is written."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_cli_writes_markdown(tmp_path: Path):
    out = tmp_path / "out.md"
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/run_signal_validation.py",
            "--signal", "decision_state",
            "--periods", "5,21",
            "--rolling-window", "3M",
            "--start", "2024-10-01",
            "--end", "2025-01-31",
            "--output", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"CLI failed: stderr={result.stderr}"
    assert out.exists()
    content = out.read_text()
    assert "decision_state" in content
    assert "Mean IC" in content
```

- [ ] **Step 3: Run smoke test**

```bash
pytest tests/intelligence/validation/test_cli_smoke.py -v -m integration
```

Expected: 1 passed.

- [ ] **Step 4: Run the CLI manually with --persist on the last 3 years**

```bash
python scripts/run_signal_validation.py \
    --signal decision_state \
    --periods 5,21,63 \
    --rolling-window 6M \
    --start 2023-01-01 \
    --end 2026-05-01 \
    --output output/validation/decision_state_$(date +%Y-%m-%d).md \
    --persist
```

Expected: command exits 0 in &lt; 180 seconds. Inspect the output markdown.

- [ ] **Step 5: Verify persistence**

```bash
python -c "
from atlas.db import get_engine
from sqlalchemy import text
eng = get_engine()
with eng.connect() as c:
    rows = c.execute(text('SELECT forward_period_days, mean_ic, ic_t_stat, n_observations FROM atlas.atlas_signal_ic WHERE signal_name = \\'decision_state\\' ORDER BY forward_period_days')).fetchall()
    for r in rows: print(r)
"
```

Expected: 3 rows for forward_period_days ∈ {5, 21, 63}.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_signal_validation.py tests/intelligence/validation/test_cli_smoke.py
git commit -m "feat(sp01): CLI orchestrator + smoke test — wires factor → IC → persist → tearsheet"
```

---

## Task 9: Sanity validation tests (the three validation-strategy checks)

**Files:**
- Create: `tests/intelligence/validation/test_sanity.py`

- [ ] **Step 1: Write the three sanity tests**

Create `tests/intelligence/validation/test_sanity.py`:

```python
"""Three sanity checks from SP01 validation strategy.

(1) IC on a known-strong synthetic signal (12-month return) > 0.06
(2) IC on randomized signal labels ≈ 0
(3) Quantile spread on a strong synthetic signal > 0
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from atlas.intelligence.validation.ic_engine import (
    compute_ic_over_window,
    compute_quantile_spread,
)


@pytest.fixture
def synthetic_universe():
    """Build a synthetic 100-stock, 1-year universe where forward returns
    have a small but reliable correlation to a 12-month momentum factor.
    """
    np.random.seed(123)
    dates = pd.date_range("2025-01-01", periods=200, freq="B")
    instruments = [f"INST{i:03d}" for i in range(100)]

    # Generate true forward returns
    fwd_data: list[tuple] = []
    factor_data: list[tuple] = []
    # Stable per-instrument trend → produces stable RS ranking AND forward return correlation
    instrument_trends = {inst: np.random.randn() for inst in instruments}

    for d in dates:
        for inst in instruments:
            base = instrument_trends[inst]
            # Factor (12m momentum proxy) — same per instrument, with small noise
            factor_val = base + np.random.randn() * 0.1
            # Forward return correlated with the factor (signal=0.3, noise=0.7)
            ret = 0.3 * base + 0.7 * np.random.randn()
            factor_data.append((d, inst, factor_val))
            fwd_data.append((d, inst, ret))

    factor_df = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"])
    factor_df = factor_df.set_index(["date", "instrument_id"])
    fwd_df = pd.DataFrame(fwd_data, columns=["date", "instrument_id", "ret"])
    fwd_wide = fwd_df.pivot(index="date", columns="instrument_id", values="ret")
    return factor_df, fwd_wide


@pytest.fixture
def randomized_factor(synthetic_universe):
    """Take the synthetic universe but shuffle the factor values within each date.
    This destroys the signal-to-return relationship — IC should be near zero.
    """
    factor_df, fwd_wide = synthetic_universe
    rng = np.random.default_rng(456)
    shuffled = factor_df.copy()
    shuffled = (
        shuffled.groupby(level="date", group_keys=False)
        .apply(lambda g: g.assign(factor=rng.permutation(g["factor"].values)))
    )
    return shuffled, fwd_wide


class TestSP01ValidationStrategy:
    def test_known_strong_signal_ic_above_threshold(self, synthetic_universe):
        """Validation strategy step 1: known-strong synthetic signal IC > 0.06."""
        factor, returns = synthetic_universe
        result = compute_ic_over_window(factor, returns)
        assert result.mean_ic > 0.06, (
            f"Synthetic momentum signal should have IC > 0.06, got {result.mean_ic:.4f}. "
            "If this fails, the IC engine itself is broken (not the signal)."
        )

    def test_randomized_signal_ic_near_zero(self, randomized_factor):
        """Validation strategy step 2: randomized signal labels → IC ≈ 0."""
        factor, returns = randomized_factor
        result = compute_ic_over_window(factor, returns)
        assert abs(result.mean_ic) < 0.03, (
            f"Randomized signal should have |IC| < 0.03, got {result.mean_ic:.4f}. "
            "If this fails, there's a look-ahead bug or alignment error in the engine."
        )

    def test_quantile_spread_positive_on_strong_signal(self, synthetic_universe):
        """Validation strategy step 3: Q_top − Q_bot > 0 on a strong signal."""
        factor, returns = synthetic_universe
        spread = compute_quantile_spread(factor, returns, n_quantiles=5)
        assert spread > 0, (
            f"Synthetic momentum signal should have positive Q5−Q1 spread, got {spread:.4f}"
        )
```

- [ ] **Step 2: Run sanity tests**

```bash
pytest tests/intelligence/validation/test_sanity.py -v
```

Expected: 3 passed. **If any of these fail, STOP — the IC engine is broken, not the signal.** Investigate before continuing.

- [ ] **Step 3: Commit**

```bash
git add tests/intelligence/validation/test_sanity.py
git commit -m "test(sp01): three sanity checks — known signal, random signal, quantile spread"
```

---

## Task 10: Production run + interpretation

**Files:**
- Create: `output/validation/decision_state_<today>.md` (artifact, not committed)
- Modify: `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp01_state.md` (new memory file)

- [ ] **Step 1: Run the validator against full available history**

```bash
python scripts/run_signal_validation.py \
    --signal decision_state \
    --periods 5,21,63 \
    --rolling-window 6M \
    --start 2018-01-01 \
    --end $(date -d 'yesterday' +%Y-%m-%d) \
    --output output/validation/decision_state_$(date +%Y-%m-%d).md \
    --persist
```

Expected: completes in &lt; 180 seconds. Outputs the markdown tearsheet.

- [ ] **Step 2: Read the tearsheet**

```bash
cat output/validation/decision_state_$(date +%Y-%m-%d).md
```

Inspect the verdict per forward period (5d, 21d, 63d). The 21d row is the SP01 acceptance gate.

- [ ] **Step 3: Verify all 3 rows in atlas_signal_ic for today**

```bash
python -c "
from datetime import date
from atlas.db import get_engine
from sqlalchemy import text
eng = get_engine()
with eng.connect() as c:
    rows = c.execute(text('''
        SELECT forward_period_days, mean_ic, ic_t_stat, ic_ir, quantile_spread_ann, turnover_monthly, n_observations
        FROM atlas.atlas_signal_ic
        WHERE signal_name = 'decision_state'
          AND as_of_date >= CURRENT_DATE - 7
        ORDER BY forward_period_days
    ''')).fetchall()
    for r in rows: print(dict(r._mapping))
"
```

- [ ] **Step 4: Write a memory file documenting the SP01 result**

Create `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp01_state.md`:

```markdown
---
name: SP01 Signal Validation Lab — first run result
description: IC measurement on decision_state composite. First-run numbers + verdict against SP01 success criteria.
type: project
---

**Ran:** {today's date}
**Signal:** decision_state (v1 encoding — see atlas/intelligence/validation/encoding.py)
**History:** 2018-01-01 to {today-1}
**Rolling window:** 6M

## Results (first run)

| Period | Mean IC | t-stat | Q-spread (ann) | Turnover/mo | Verdict |
|---|---|---|---|---|---|
| 5d | {fill in} | {fill in} | {fill in} | {fill in} | PASS/FAIL |
| 21d | {fill in} | {fill in} | {fill in} | {fill in} | PASS/FAIL |  ← SP01 gate
| 63d | {fill in} | {fill in} | {fill in} | {fill in} | PASS/FAIL |

## Interpretation

{If 21d PASS:}
SP01 success criteria met. decision_state composite is predictive. Phase 2 downstream
sub-projects (SP04, SP05, SP06, SP07) can build on these signals with confidence.
Next: trigger SP04 (Signal Intelligence layer) to replace hand-set weights with
IC-derived weights from this table.

{If 21d FAIL:}
SP01 success criteria NOT met on the 21d horizon. Investigation candidates:
1. Composite weights need re-tuning (rs_state weight likely needs to increase)
2. Multi-timeframe confluence (SP04) may rescue the signal
3. The 6M rolling window may be too short for signal stability — try 12M
4. Sector regime conditioning (SP04) may be the missing factor

**How to apply:** Reference these numbers in SP04 design discussions. Don't
silently re-run with different weights to chase numbers — every weight change
is logged in atlas_signal_ic with the new as_of_date.
```

Fill in the actual numbers from Step 3 before saving.

- [ ] **Step 5: Update MEMORY.md index**

Add a pointer to the new memory file in `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/MEMORY.md`:

```
- [SP01 Signal Validation Lab — first run result](project_sp01_state.md) — IC measurement on decision_state composite; PASS/FAIL verdict per forward period
```

- [ ] **Step 6: Update the master plan's SP01 status**

In `docs/phase2/00-master-plan.html`, find the SP01 section's badge area and add a status badge: `<span class="badge">✓ Shipped</span>`. Commit the doc update.

- [ ] **Step 7: Commit the master plan update + push**

```bash
git add docs/phase2/00-master-plan.html
git commit -m "docs(sp01): mark Signal Validation Lab as shipped"
git push origin main
```

---

## Final verification checklist

Before declaring SP01 done, confirm:

- [ ] All pytest checks pass: `pytest tests/intelligence/ -v` shows green
- [ ] Pyright/mypy clean: `pyright atlas/intelligence/` shows zero errors
- [ ] Ruff clean: `ruff check atlas/intelligence/` shows zero issues
- [ ] Migration 032 applied to EC2 Supabase
- [ ] CLI runs end-to-end in &lt; 180 seconds for 10-year history
- [ ] `atlas_signal_ic` populated with 3 rows for current `as_of_date`
- [ ] Markdown tearsheet exists at `output/validation/decision_state_*.md`
- [ ] Memory file `project_sp01_state.md` filled in with actual numbers
- [ ] Master plan HTML reflects shipped status
- [ ] No leaked secrets in any committed file
- [ ] No `# noqa` suppressions without justification
- [ ] All commits use conventional-commit prefixes (`feat(sp01):`, `test(sp01):`, etc.)

---

## What SP01 hands off to SP04

SP04 (Signal Intelligence layer) starts the moment SP01 ships. It reads the
`atlas_signal_ic` table to derive **IC-weighted** composite weights, replacing
the v1 hand-set weights in `atlas/intelligence/validation/encoding.py`. The
contract:

- SP04 reads `atlas_signal_ic` filtered to the latest `as_of_date` per signal.
- For each dimension, SP04 may decide to: keep weight, raise weight (high
  individual IC), lower weight (low IC), or drop entirely (negative IC).
- SP04 writes a new composite to `atlas_stock_intelligence_daily` with full
  audit trail (which dimensions contributed; their IC at the time).
- The encoding in `encoding.py` becomes the v1 reference; SP04 supersedes it.

The framework is permanent; the weights evolve. That's the SP01 contract.
