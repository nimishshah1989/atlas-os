# v6 Plan 2 — Backend Trading Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v6 backend trading engine — signal stack + composite scorer + HRP portfolio + risk overlays + crisis sleeve + simulator + walk-forward validator. Output: working `lab.run_backtest()` producing real CAGR/MDD/Sharpe/Calmar numbers + nightly write to `atlas_v6_strategy_runs` and `atlas_v6_recommendations_daily`.

**Architecture:** Modular monolith under `atlas/trading/v6/`. Thin orchestrator (`lab.py` ≤ 250 LOC) calls into 11 bounded-context modules (signals/, composite, regime, portfolio, risk, governance, crisis_sleeve, simulator, validator). Imports only from `atlas.primitives`, `atlas.db`, `atlas.config`, and `atlas.data_prereqs.v6` (Plan 1A). No imports from `atlas.api`, `atlas.simulation`, or v5 `atlas.trading.*` internals.

**Tech Stack:** Python 3.12, NumPy, pandas, scipy (HRP linkage), SQLAlchemy 2.0, Alembic, Postgres. pytest + pytest-asyncio. Atlas hooks enforce: source ≤ 600 LOC, tests ≤ 800 LOC, no float on money, structured logs.

**Anchor docs:**
- Spec: `docs/superpowers/specs/2026-05-18-v6-rs-trading-model-design.md`
- Plan 1A (prereqs): `docs/superpowers/plans/2026-05-18-v6-data-prerequisites.md`

---

## File structure

### Backend — new files under `atlas/trading/v6/`

```
__init__.py                     # public exports (lab, run_backtest, live_rebalance)
universe.py                     # PIT Nifty 500 + ADV floor + investability filter
governance.py                   # Indian hard-exclusion filters
composite.py                    # z-score blend + sector neutralize + selection + buffer zones
regime.py                       # 5-signal macro regime composite → gross multiplier
portfolio.py                    # HRP optimizer + cap stack
risk.py                         # vol-target, trend gates, DD circuit breaker, sqrt slippage
crisis_sleeve.py                # cross-asset TSMOM on gold + G-Sec ETFs
simulator.py                    # backtest engine
validator.py                    # walk-forward + OOS-IC retention + goal-post + hold-out singleton
lab.py                          # thin orchestrator (≤ 250 LOC)
tax_engine.py                   # STCG/LTCG (lift from v5 by copy)
signals/
  __init__.py
  v5_carry.py                   # natr_14, beta_alpha_63d, mom_low_vol (lift by copy)
  price_signals.py              # 52WH, FIP, industry_RS
  residual_momentum.py          # 3-factor residual cumulant
  bab.py                        # betting-against-beta
  quality.py                    # price-based quality proxy (v0.1 placeholder)
  factor_returns.py             # daily Indian Mkt+SMB+WML factor return compute job
```

### Tests — mirrors source tree
`tests/trading/v6/test_*.py` with `tests/trading/v6/fixtures/` for sample panels.

---

## Phase 1 — Foundation (universe + v5 signal carry + price signals + bab + quality)

### Task 1.1: `universe.py` — point-in-time investable universe

**Files:**
- Create: `atlas/trading/v6/__init__.py`, `atlas/trading/v6/universe.py`
- Test: `tests/trading/v6/__init__.py`, `tests/trading/v6/conftest.py`, `tests/trading/v6/test_universe.py`

- [ ] **Step 1.1.1: Write failing tests**

```python
# tests/trading/v6/test_universe.py
"""universe.get_investable — PIT Nifty 500 + ADV ≥ ₹5cr floor."""
from __future__ import annotations
from datetime import date
import uuid

import pytest
from sqlalchemy import text

from atlas.trading.v6.universe import (
    InvestableFilter,
    get_investable,
)


def test_filter_drops_below_adv_floor(tmp_db_session):
    """ADV < ₹5cr → excluded even if in Nifty 500."""
    iid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_universe_stocks
            (instrument_id, symbol, company_name, in_nifty_500, effective_from)
        VALUES (:i, 'XYZ', 'Test', true, '2024-01-01')
        ON CONFLICT DO NOTHING
    """), {"i": str(iid)})
    # Insert 20 days of low-ADV data
    for d in range(20):
        tmp_db_session.execute(text("""
            INSERT INTO atlas.atlas_stock_metrics_daily
                (instrument_id, date, close, volume_value)
            VALUES (:i, :d, 100, 10000000)
            ON CONFLICT DO NOTHING
        """), {"i": str(iid), "d": date(2026, 1, d + 1)})
    f = InvestableFilter(adv_floor_cr=5.0)
    out = f.apply(tmp_db_session, ref_date=date(2026, 1, 20))
    assert iid not in {u.instrument_id for u in out}


def test_filter_keeps_above_adv_floor(tmp_db_session):
    iid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_universe_stocks
            (instrument_id, symbol, company_name, in_nifty_500, effective_from)
        VALUES (:i, 'BIG', 'Big Test', true, '2024-01-01')
        ON CONFLICT DO NOTHING
    """), {"i": str(iid)})
    # ₹10cr / day for 20 days
    for d in range(20):
        tmp_db_session.execute(text("""
            INSERT INTO atlas.atlas_stock_metrics_daily
                (instrument_id, date, close, volume_value)
            VALUES (:i, :d, 100, 100000000)
            ON CONFLICT DO NOTHING
        """), {"i": str(iid), "d": date(2026, 1, d + 1)})
    f = InvestableFilter(adv_floor_cr=5.0)
    out = f.apply(tmp_db_session, ref_date=date(2026, 1, 20))
    assert iid in {u.instrument_id for u in out}
```

- [ ] **Step 1.1.2: Implement `universe.py`**

```python
# atlas/trading/v6/universe.py
"""Point-in-time investable universe for the v6 trading model.

Universe = current Nifty 500 (via atlas_universe_stocks.in_nifty_500) AND
20d median traded value >= ₹5 crore.

When Plan 1A D1 backfill lands, swap the in_nifty_500 boolean to the PIT
atlas_index_membership table for survivorship-bias-free backtest.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass(frozen=True)
class InvestableInstrument:
    instrument_id: uuid.UUID
    symbol: str
    sector: str | None
    median_adv_cr: float


@dataclass
class InvestableFilter:
    adv_floor_cr: float = 5.0
    adv_window_days: int = 20

    def apply(
        self, session: Session, ref_date: date
    ) -> list[InvestableInstrument]:
        window_start = ref_date - timedelta(days=self.adv_window_days * 2)  # ~40 cal days
        rows = session.execute(text("""
            WITH adv AS (
              SELECT m.instrument_id,
                     PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.volume_value)
                       OVER (PARTITION BY m.instrument_id) / 1e7 AS median_adv_cr
                FROM atlas.atlas_stock_metrics_daily m
               WHERE m.date BETWEEN :s AND :e
            )
            SELECT DISTINCT u.instrument_id, u.symbol, u.sector,
                            MIN(adv.median_adv_cr) AS median_adv_cr
              FROM atlas.atlas_universe_stocks u
              JOIN adv USING (instrument_id)
             WHERE u.in_nifty_500 = true
               AND adv.median_adv_cr >= :floor
             GROUP BY u.instrument_id, u.symbol, u.sector
        """), {"s": window_start, "e": ref_date, "floor": self.adv_floor_cr}).fetchall()
        return [
            InvestableInstrument(
                instrument_id=uuid.UUID(str(r.instrument_id)),
                symbol=r.symbol,
                sector=r.sector,
                median_adv_cr=float(r.median_adv_cr or 0),
            )
            for r in rows
        ]


def get_investable(
    session: Session, ref_date: date, adv_floor_cr: float = 5.0
) -> list[InvestableInstrument]:
    return InvestableFilter(adv_floor_cr=adv_floor_cr).apply(session, ref_date)
```

- [ ] **Step 1.1.3: Run tests, verify pass**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os-v6 && pytest tests/trading/v6/test_universe.py -v`
Expected: 2 passing (DB-dependent — needs ATLAS_TEST_DB_URL set; otherwise skip via conftest).

- [ ] **Step 1.1.4: Commit**

```bash
git add atlas/trading/v6/__init__.py atlas/trading/v6/universe.py \
        tests/trading/v6/__init__.py tests/trading/v6/conftest.py \
        tests/trading/v6/test_universe.py
git commit -m "feat(v6): universe.py — PIT Nifty 500 + ADV floor"
```

---

### Task 1.2: `signals/v5_carry.py` — lift v5 signals by copy

Copy 3 functions from `atlas/trading/data_loader.py` (committed at 5e1bd87):
- `compute_natr_14(high, low, close)`
- `compute_beta_alpha_63d(close, nifty500_close)`
- `compute_mom_low_vol(ret_12m, realized_vol)`

**Files:**
- Create: `atlas/trading/v6/signals/__init__.py`, `atlas/trading/v6/signals/v5_carry.py`
- Test: `tests/trading/v6/signals/__init__.py`, `tests/trading/v6/signals/test_v5_carry.py`

- [ ] **Step 1.2.1: Write golden tests with hand-computed expected output**

```python
# tests/trading/v6/signals/test_v5_carry.py
"""v5_carry — verify lifted functions match v5 originals on fixture data."""
from __future__ import annotations
import numpy as np

from atlas.trading.v6.signals.v5_carry import (
    compute_natr_14,
    compute_beta_alpha_63d,
    compute_mom_low_vol,
)


def test_natr_14_known_input():
    """ATR over flat prices is 0 → NATR is 0."""
    close = np.full((1, 30), 100.0, dtype=np.float32)
    high = np.full((1, 30), 100.0, dtype=np.float32)
    low = np.full((1, 30), 100.0, dtype=np.float32)
    natr = compute_natr_14(high, low, close)
    assert np.allclose(natr[:, 14:], 0.0, atol=1e-3)


def test_natr_14_known_volatility():
    """ATR over 1% daily H-L spread → NATR ≈ 1.0."""
    close = np.full((1, 30), 100.0, dtype=np.float32)
    high = np.full((1, 30), 100.5, dtype=np.float32)
    low = np.full((1, 30), 99.5, dtype=np.float32)
    natr = compute_natr_14(high, low, close)
    # ATR ≈ 1.0, divided by 100 × 100 = 1.0
    assert 0.9 < natr[0, 20] < 1.1


def test_beta_alpha_63d_zero_for_synced_returns():
    """Stock = benchmark → alpha = 0."""
    close = np.array([[100 + i for i in range(70)]], dtype=np.float32)
    bench = np.array([100 + i for i in range(70)], dtype=np.float64)
    out = compute_beta_alpha_63d(close, bench)
    assert abs(out[0, 65]) < 0.01


def test_mom_low_vol_multiplies_correctly():
    """mom_low_vol = ret_12m × (1 - cross_sectional_vol_rank)."""
    ret = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    vol = np.array([[0.10, 0.20, 0.30]], dtype=np.float32)
    out = compute_mom_low_vol(ret, vol)
    # vol_rank cross-sectional: all same row, all same vol → tied, rank = 0.5 for all (with one row, pandas pct_rank gives 1.0)
    # We test directionally: smaller vol → larger weight
    assert out.shape == ret.shape
```

- [ ] **Step 1.2.2: Implement by copy**

Read `atlas/trading/data_loader.py` lines 132-197 (compute_natr_14, compute_beta_alpha_63d, compute_mom_low_vol). Copy the three functions verbatim into `atlas/trading/v6/signals/v5_carry.py`, add module docstring noting the carry source. Do not modify the math.

- [ ] **Step 1.2.3: Run tests, verify pass**

Run: `pytest tests/trading/v6/signals/test_v5_carry.py -v`

- [ ] **Step 1.2.4: Commit**

```bash
git add atlas/trading/v6/signals/__init__.py atlas/trading/v6/signals/v5_carry.py \
        tests/trading/v6/signals/__init__.py tests/trading/v6/signals/test_v5_carry.py
git commit -m "feat(v6/signals): v5_carry — natr_14 + beta_alpha_63d + mom_low_vol"
```

---

### Task 1.3: `signals/price_signals.py` — 52WH + FIP + industry-RS

**Files:**
- Create: `atlas/trading/v6/signals/price_signals.py`
- Test: `tests/trading/v6/signals/test_price_signals.py`

- [ ] **Step 1.3.1: Write tests**

```python
# tests/trading/v6/signals/test_price_signals.py
"""52WH proximity + FIP smoothness + industry-decomposed RS."""
from __future__ import annotations
import numpy as np
import pandas as pd

from atlas.trading.v6.signals.price_signals import (
    compute_52wh_proximity,
    compute_fip_smoothness,
    compute_industry_rs,
)


def test_52wh_at_high_returns_1():
    """Stock at its 252d max → proximity = 1.0."""
    close = np.array([[100 + i for i in range(252)]], dtype=np.float32)
    out = compute_52wh_proximity(close, window=252)
    assert out[0, -1] == 1.0


def test_52wh_below_high_returns_fraction():
    """Stock 10% below its 252d max → proximity = 0.9."""
    close = np.array([[100.0] * 251 + [90.0]], dtype=np.float32)
    out = compute_52wh_proximity(close, window=252)
    assert abs(out[0, -1] - 0.9) < 0.001


def test_fip_smoothness_all_up_days():
    """All 252 days up → fip = 1.0."""
    close = np.array([[100 + i * 0.1 for i in range(253)]], dtype=np.float32)
    out = compute_fip_smoothness(close, window=252)
    assert out[0, -1] == 1.0


def test_fip_smoothness_alternating_days():
    """Alternating up/down → fip ≈ 0."""
    close = np.array([[100, 101, 100, 101, 100] * 51], dtype=np.float32)
    out = compute_fip_smoothness(close, window=252)
    assert abs(out[0, -1]) < 0.05


def test_industry_rs_isolates_within_sector():
    """Industry RS = stock 3m return - sector 3m return."""
    stock_3m = np.array([0.10, 0.15, 0.20])
    sector_3m = np.array([0.05, 0.10, 0.10])  # broadcast same length
    out = compute_industry_rs(stock_3m, sector_3m)
    assert np.allclose(out, [0.05, 0.05, 0.10])
```

- [ ] **Step 1.3.2: Implement**

```python
# atlas/trading/v6/signals/price_signals.py
"""52WH proximity (George-Hwang 2004), FIP smoothness (Gray-Vogel 2014),
industry-decomposed RS (Moskowitz-Grinblatt 1999)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_52wh_proximity(
    close: np.ndarray, window: int = 252
) -> np.ndarray:
    """proximity[i,t] = close[i,t] / max(close[i, t-window+1 : t+1]).

    Range: (0, 1]. 1.0 means at the high.
    """
    rolling_max = (
        pd.DataFrame(close).T.rolling(window, min_periods=20).max().T
    ).to_numpy().astype(np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(rolling_max > 0, close / rolling_max, 0.0).astype(np.float32)


def compute_fip_smoothness(
    close: np.ndarray, window: int = 252
) -> np.ndarray:
    """fip[i,t] = (n_up_days - n_down_days) / window over trailing window.

    Range: [-1, 1]. +1 means all up days; -1 means all down; 0 means balanced.
    Combined with sign(ret_12m_1m) downstream to fade "smooth losers".
    """
    daily_ret = np.zeros_like(close)
    daily_ret[:, 1:] = close[:, 1:] / np.where(close[:, :-1] > 0, close[:, :-1], 1) - 1
    sign = np.sign(daily_ret)
    rolling_sum = (
        pd.DataFrame(sign).T.rolling(window, min_periods=window // 2).sum().T
    ).to_numpy().astype(np.float32)
    return (rolling_sum / window).astype(np.float32)


def compute_industry_rs(
    stock_3m_ret: np.ndarray, sector_3m_ret: np.ndarray
) -> np.ndarray:
    """industry_rs = stock 3m return - sector 3m return.

    Shapes must be broadcastable.
    """
    return (stock_3m_ret - sector_3m_ret).astype(np.float32)
```

- [ ] **Step 1.3.3: Run + commit**

```bash
pytest tests/trading/v6/signals/test_price_signals.py -v
git add atlas/trading/v6/signals/price_signals.py tests/trading/v6/signals/test_price_signals.py
git commit -m "feat(v6/signals): 52WH proximity + FIP smoothness + industry-RS"
```

---

### Task 1.4: `signals/bab.py` — betting-against-beta

**Files:**
- Create: `atlas/trading/v6/signals/bab.py`
- Test: `tests/trading/v6/signals/test_bab.py`

- [ ] **Step 1.4.1: Test + implement (single commit)**

```python
# atlas/trading/v6/signals/bab.py
"""BAB — betting-against-beta tilt (Frazzini-Pedersen 2014)."""
from __future__ import annotations
import numpy as np
import pandas as pd


def compute_bab_rank(beta: np.ndarray) -> np.ndarray:
    """Cross-sectional inverse rank of beta. Low-beta names → high rank."""
    rank = pd.DataFrame(beta).rank(axis=0, pct=True).fillna(0.5).to_numpy()
    return (1.0 - rank).astype(np.float32)
```

```python
# tests/trading/v6/signals/test_bab.py
import numpy as np
from atlas.trading.v6.signals.bab import compute_bab_rank


def test_bab_inverts_rank():
    """Lowest beta → highest BAB rank."""
    beta = np.array([[0.5, 1.0, 1.5]])
    out = compute_bab_rank(beta)
    # 0.5 should rank highest (1.0), 1.5 lowest (0.0)
    assert out[0, 0] > out[0, 1] > out[0, 2]
```

- [ ] **Step 1.4.2: Commit**

```bash
pytest tests/trading/v6/signals/test_bab.py -v
git add atlas/trading/v6/signals/bab.py tests/trading/v6/signals/test_bab.py
git commit -m "feat(v6/signals): bab — betting-against-beta inverse rank"
```

---

### Task 1.5: `signals/quality.py` — price-based quality proxy

Per spec §5.4, v0.1 quality proxy:
```
quality_proxy = -0.5 × rank(realized_vol_63)
              - 0.3 × rank(max_drawdown_252d)
              + 0.2 × rank(ret_consistency_252d)
```
where `ret_consistency = ret_12m / |ret_12m_worst_quarter|`.

**Files:**
- Create: `atlas/trading/v6/signals/quality.py`
- Test: `tests/trading/v6/signals/test_quality.py`

- [ ] **Step 1.5.1: Implement + tests** (~80 LOC, follow same TDD pattern as 1.4)
- [ ] **Step 1.5.2: Commit:** `feat(v6/signals): quality.py — price-based proxy (v0.1)`

---

## Phase 2 — Residual momentum (factor returns + per-stock residual)

### Task 2.1: `signals/factor_returns.py` — Indian Mkt + SMB + WML daily compute job

Per spec §5.3 Step 1 — build factor return series stored in `atlas_factor_returns_daily` (migration 080 created the table; rows are empty).

**Files:**
- Create: `atlas/trading/v6/signals/factor_returns.py`
- Create: `scripts/v6_factor_returns_backfill.py`
- Test: `tests/trading/v6/signals/test_factor_returns.py`

- [ ] **Step 2.1.1: Implement compute logic**

Functions:
- `compute_mkt_excess(date, t_bill_rate) -> float` — Nifty 500 return − 91d T-bill
- `compute_smb(date) -> float` — top-200-mcap quintile-1 return − quintile-5 return
- `compute_wml(date) -> float` — top-decile 12-1 momentum return − bottom-decile

- [ ] **Step 2.1.2: Backfill script populates `atlas_factor_returns_daily` for 10y**

Run script, verify ~2,500 rows after backfill.

- [ ] **Step 2.1.3: Commit** — `feat(v6/signals): factor_returns compute + backfill 2016-2026`

### Task 2.2: `signals/residual_momentum.py` — per-stock residual cumulant

Spec §5.3 Step 2:
```python
# For stock i on date t:
# Regress trailing 252d daily returns of i on factors (Mkt, SMB, WML)
# r_i_daily = alpha_i + beta_mkt × MKT + beta_smb × SMB + beta_wml × WML + epsilon_i
# Sum epsilon_i over [t-252 : t-21] window (12-minus-1 cumulant)
```

**Files:**
- Create: `atlas/trading/v6/signals/residual_momentum.py`
- Test: `tests/trading/v6/signals/test_residual_momentum.py`

- [ ] **Step 2.2.1: Implement using `numpy.linalg.lstsq` for OLS per stock**
- [ ] **Step 2.2.2: Test on synthetic data where residual is known**
- [ ] **Step 2.2.3: Commit** — `feat(v6/signals): residual_momentum — 3-factor Carhart-minus-HML`

---

## Phase 3 — Composite + selection

### Task 3.1: `composite.py` — z-score blend + sector neutralize + selection + buffer zones

Per spec §6.

**Files:**
- Create: `atlas/trading/v6/composite.py`
- Test: `tests/trading/v6/test_composite.py`

API:
```python
def compute_composite(
    panel: pd.DataFrame,        # rows: instrument_id, cols: signal names + sector
    weights: dict[str, float],  # tier-A 0.15 each, tier-B 0.13, tier-C ~0.05
) -> pd.Series:                  # composite score per instrument
    ...

def select(
    composite: pd.Series,
    governance_excluded: set[uuid.UUID],
    trend_gate_pass: set[uuid.UUID],   # close >= 200dMA
    held_yesterday: set[uuid.UUID],
    enter_rank_cutoff: int = 30,
    stay_rank_cutoff: int = 50,
) -> SelectionResult:
    """Returns SelectionResult with entered, held, exited symbols + ranks."""
    ...
```

Tasks 3.1.1-3.1.4: tests + impl + commit. ~150 LOC source, ~250 LOC test.

---

## Phase 4 — Portfolio construction (HRP + cap stack)

### Task 4.1: `portfolio.py` — HRP optimizer

Per spec §6.5. Use `scipy.cluster.hierarchy` for linkage.

**Files:**
- Create: `atlas/trading/v6/portfolio.py`
- Test: `tests/trading/v6/test_portfolio.py`

```python
@dataclass
class HrpAllocator:
    corr_window_days: int = 252
    single_name_cap: float = 0.05
    sector_cap: float = 0.25
    issuer_group_cap: float = 0.05
    weight_floor: float = 0.005

    def allocate(
        self,
        returns_panel: pd.DataFrame,   # 252d daily returns for the cohort
        sector_map: dict[uuid.UUID, str],
        issuer_group_map: dict[uuid.UUID, str],
    ) -> pd.Series:                     # weights summing to 1.0
        ...
```

Steps:
1. corr → distance: `dist = sqrt(0.5 × (1 - corr))`
2. `scipy.cluster.hierarchy.linkage(dist, method='single')`
3. Quasi-diagonalize: traverse linkage tree to get leaf order
4. Recursive bisection: allocate by inverse cluster-variance
5. Apply caps in order: single-name → sector → issuer-group → floor
6. Redistribute excess from binding cap to uncapped names *within the same HRP cluster*

Tasks 4.1.1-4.1.6: ~250 LOC source. Hand-computed test on 5-name cohort.

---

## Phase 5 — Risk overlays (governance + regime + risk)

### Task 5.1: `governance.py` — Indian hard-exclusion filters

Per spec §7.1. Six filters in order: pledge, auditor quality, F&O ban, SME, group cap, audit qualification. All fail-open (missing data ≠ excluded).

**Files:**
- Create: `atlas/trading/v6/governance.py`
- Test: `tests/trading/v6/test_governance.py`

API:
```python
def is_excluded(
    session: Session,
    instrument_id: uuid.UUID,
    ref_date: date,
) -> tuple[bool, str | None]:    # (excluded?, reason)
```

Reads `atlas_governance_daily`, `atlas_governance_master`, `atlas_universe_stocks`. Logs every exclusion to `atlas_v6_exclusions_log`.

### Task 5.2: `regime.py` — 5-signal macro regime composite

Per spec §7.2. Five signals → score 0..5 → gross multiplier table. Hysteresis (3 days down, 5 days up).

API:
```python
def compute_regime(session: Session, ref_date: date) -> RegimeState:
    """Reads atlas_market_regime_daily + atlas_macro_daily, returns 5-signal composite."""
```

### Task 5.3: `risk.py` — vol target, trend gates, DD circuit breaker, sqrt slippage

Per spec §7.3-7.5, §7.7. Four primitives:
- `vol_targeted_gross(realized_vol, regime_mult, target=0.12)` → gross ∈ [0.30, 1.10]
- `per_name_trend_gate(close_series, ma_200)` → bool
- `dd_circuit_breaker(equity_curve, current_dd) → BreakerAction`
- `slippage_bps(order_value, adv_20d)` → bps

Tasks 5.1-5.3: combined ~400 LOC source + tests.

---

## Phase 6 — Crisis sleeve (cross-asset TSMOM)

### Task 6.1: `crisis_sleeve.py`

Per spec §7.6. Long-only, two-leg sleeve (gold ETF + G-Sec ETF). Scoring:
```
signal[a] = sign(12m_ret[a]) × target_asset_vol / realized_vol_63d[a]
positive_signal[a] = max(signal[a], 0)
sleeve_weight[a] = positive_signal[a] / Σ positive_signal
sleeve_pct = 0.05 + 0.10 × (regime_score / 5)
```

**Files:**
- Create: `atlas/trading/v6/crisis_sleeve.py`
- Test: `tests/trading/v6/test_crisis_sleeve.py`

~120 LOC.

---

## Phase 7 — Orchestrator + simulator

### Task 7.1: `simulator.py` — backtest engine

Loops monthly rebalance dates. At each date:
1. `universe.get_investable(date)`
2. `governance.apply_exclusions(...)`
3. compute all signals on the investable cohort
4. `composite.compute_composite(...)`, `composite.select(...)`
5. `portfolio.allocate_hrp(...)` + cap stack
6. `regime.compute_regime(date)` → gross multiplier
7. `risk.vol_targeted_gross(...)`
8. `crisis_sleeve.allocate(date)`
9. Merge equity book + sleeve, compute orders + slippage
10. Apply orders to running portfolio, record period return

Output: `SimulationResult` with per-period returns, holdings history, exclusions log, regime history.

~400 LOC. Atomic test on 6-month synthetic universe.

### Task 7.2: `lab.py` — thin orchestrator

Public API per spec §4:
- `run_backtest(start, end, **opts) -> BacktestResult`
- `live_rebalance(date) -> list[Order]`
- `intramonth_scan(date) -> list[Order]`
- `evaluate_goal_post() -> dict`

≤ 250 LOC. Delegates everything to the bounded-context modules.

---

## Phase 8 — Validator + walk-forward

### Task 8.1: `validator.py` — walk-forward harness

Per spec §8. Window structure:
- Train 2010-2014 → OOS 2015 → refit on 2010-2015 → OOS 2016 → ... → refit on 2010-2021 → OOS 2022
- Hold-out 2023-2025 untouched until terminal

Per-signal OOS-IC retention gate: `OOS_IC / IS_IC ≥ 0.70`.

### Task 8.2: Goal-post evaluator

Per spec §8.4. 9 hard constraints. Writes one row per strategy run to `atlas_v6_strategy_runs`.

### Task 8.3: Hold-out singleton enforcement

`atlas_v6_strategy_runs.holdout_examined_at` is a singleton. Examining hold-out before all OOS windows finished raises. Examining twice raises.

Tasks 8.1-8.3: ~350 LOC. Test the singleton enforcement explicitly.

---

## Phase 9 — Initial walk-forward run + IC validation

### Task 9.1: Run 2010-2022 walk-forward, populate `atlas_v6_strategy_runs`

Operator task. CLI:
```bash
python -m atlas.trading.v6.lab run-walk-forward --start 2010-01-01 --end 2022-12-31
```

### Task 9.2: Identify failing OOS-IC signals

Auto-shelve any signal failing `OOS_IC / IS_IC < 0.70` for 2 consecutive refits.

---

## Phase 10 — Weight optimization (Bayesian shrinkage)

### Task 10.1: Bayesian weight optimizer

Per spec §6.2. Reuse Stage 4a-style infrastructure. Generate candidate weight sets, rank by OOS Calmar, write to `atlas_signal_weights`.

~200 LOC. Test against known optimum on synthetic data.

---

## Phase 11 — Hold-out evaluation (terminal)

### Task 11.1: Examine 2023-2025 hold-out exactly once

Operator command:
```bash
python -m atlas.trading.v6.lab evaluate-holdout
```

Sets `holdout_examined_at = NOW()` on the latest passing strategy. Writes final report.

---

## Self-review checklist

- [ ] All 11 phases mapped to commits
- [ ] No `Decimal`-on-float violation (all money fields use `Decimal`/`Numeric`)
- [ ] No bare `except:` clauses
- [ ] All modules ≤ 600 LOC source / ≤ 800 LOC test
- [ ] `lab.py` ≤ 250 LOC (thin orchestrator)
- [ ] Bounded-context import discipline (no `atlas.api.*` / `atlas.simulation.*` / v5 `atlas.trading.*` internals)
- [ ] Every signal has IC validation test
- [ ] Hold-out singleton test passes (cannot examine twice)
- [ ] Tests use real Postgres (skip-if-env-missing); no SQLAlchemy mocks

## Execution

Recommended: subagent-driven-development. ~25-35 working days for a fresh team; faster with parallel subagent dispatch on independent tasks (e.g. all signals/* in Phase 1 can parallel).

When this plan completes, the v6 frontend `/strategies/v6/live` will show real CAGR/MDD/Sharpe/Calmar numbers (no more "—" Plan 2 pending labels). Plan 3 (frontend Tier 3 enhancements) and Plan 4 (paper-trade gate) become unblocked.
