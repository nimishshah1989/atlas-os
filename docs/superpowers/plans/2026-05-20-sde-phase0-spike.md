# SDE Phase 0 — Factor IC Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Modulith hook note:** edits under `atlas/**` are gated — the implementing
> session MUST invoke a planning skill first (e.g. `andrej-karpathy-skills:karpathy-guidelines`).
> Files under `scripts/**` and `tests/**` are not gated.

**Goal:** Determine, in one focused build, whether any pandas-ta factor has tradeable out-of-sample Information Coefficient on the liquid Indian-equity universe — a hard go/no-go gate before any further Signal Discovery Engine work.

**Architecture:** A small set of pure modules under `atlas/research/sde/` (factor catalog, data loaders, IC ranking) plus two runnable scripts under `scripts/`. Pure functions are TDD'd on Mac with synthetic fixtures; the data-touching scripts run on the EC2 host `jsl-wealth-server` (Mac psycopg2 is broken). The spike reuses the existing, tested `atlas/intelligence/validation/ic_engine.py` for IC computation — injected as a parameter so the SDE modules carry no cross-context import.

**Tech Stack:** Python 3, pandas, pandas-ta (already a core dependency), scipy, SQLAlchemy (sync, via `atlas.db.get_engine`), pytest. No new dependencies — vectorbt/alphalens/quantstats are not needed for Phase 0.

**Scope:** This plan covers the pre-flight data-integrity checks and the Phase 0 spike only. Phase 1 (the thin bot) gets its own plan, written only if the Phase 0 gate says PROCEED.

---

## File Structure

| File | Responsibility |
|---|---|
| `atlas/research/__init__.py` | New bounded context package marker |
| `atlas/research/sde/__init__.py` | SDE package marker (docstring only in Phase 0) |
| `atlas/research/sde/data.py` | Universe + OHLCV loaders; corporate-action rescaling of open/high/low |
| `atlas/research/sde/factors.py` | Factor catalog (~20 pandas-ta factors), factor generation, PIT liquidity mask |
| `atlas/research/sde/ic_ranking.py` | Train/test split, forward returns, IC-based factor ranking, decision gate |
| `scripts/sde_preflight_checks.py` | Two data-integrity checks; runs on EC2 |
| `scripts/sde_phase0_spike.py` | Spike orchestrator; runs on EC2, writes the results report |
| `tests/research/sde/conftest.py` | Shared synthetic OHLCV fixture |
| `tests/research/sde/test_preflight.py` | Tests for the pre-flight report formatter |
| `tests/research/sde/test_data.py` | Tests for OHLCV corporate-action rescaling |
| `tests/research/sde/test_factors.py` | Tests for factor generation + liquidity mask |
| `tests/research/sde/test_ic_ranking.py` | Tests for split, forward returns, ranking, gate |

`atlas.research.sde` modules import only `pandas`, `pandas_ta`, and `atlas.db`
(shared kernel) — no other bounded context. Cross-context wiring (pulling in
`ic_engine`) happens only in the `scripts/` orchestrator, which is outside the
import-boundary hook's scope.

---

## Task 1: Package scaffold + shared test fixture

**Files:**
- Create: `atlas/research/__init__.py`
- Create: `atlas/research/sde/__init__.py`
- Create: `tests/research/sde/conftest.py`

- [ ] **Step 1: Create the bounded-context package markers**

`atlas/research/__init__.py`:

```python
"""atlas.research — research and discovery bounded context.

Houses the Signal Discovery Engine (SDE). Imports only the shared kernel
(atlas.db, atlas.config, atlas.primitives) — never another bounded context.
"""
```

`atlas/research/sde/__init__.py`:

```python
"""Signal Discovery Engine — Phase 0 (factor IC spike).

Pure modules: data loaders, factor catalog, IC ranking. The runnable
spike lives in scripts/sde_phase0_spike.py.
"""
```

- [ ] **Step 2: Create the shared synthetic OHLCV fixture**

`tests/research/sde/conftest.py`:

```python
"""Shared fixtures for Signal Discovery Engine tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlcv_panel() -> pd.DataFrame:
    """Deterministic 3-instrument, 400-trading-day OHLCV long DataFrame.

    Columns: date, instrument_id, open, high, low, close, volume.
    """
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2022-01-03", periods=400)
    frames: list[pd.DataFrame] = []
    for i, iid in enumerate(["aaa", "bbb", "ccc"]):
        steps = rng.normal(0.0005, 0.015, size=len(dates))
        close = 100 * (1 + i * 0.1) * np.exp(np.cumsum(steps))
        high = close * (1 + rng.uniform(0, 0.02, len(dates)))
        low = close * (1 - rng.uniform(0, 0.02, len(dates)))
        open_ = close * (1 + rng.normal(0, 0.005, len(dates)))
        volume = rng.integers(50_000, 500_000, len(dates)).astype(float)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "instrument_id": iid,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
```

- [ ] **Step 3: Verify the fixture loads**

Run: `pytest tests/research/sde/ -v`
Expected: `no tests ran` (collection succeeds, no errors importing conftest).

- [ ] **Step 4: Commit**

```bash
git add atlas/research/__init__.py atlas/research/sde/__init__.py tests/research/sde/conftest.py
git commit -m "feat(sde): scaffold research.sde package + test fixture"
```

---

## Task 2: OHLCV data loaders

**Files:**
- Create: `atlas/research/sde/data.py`
- Test: `tests/research/sde/test_data.py`

- [ ] **Step 1: Write the failing test**

`tests/research/sde/test_data.py`:

```python
"""Tests for SDE Phase 0 data loaders."""

from __future__ import annotations

import pandas as pd

from atlas.research.sde.data import adjust_ohlc


def test_adjust_ohlc_rescales_ohlc_by_adjustment_ratio() -> None:
    long_df = pd.DataFrame(
        {
            "date": ["2024-01-01"],
            "instrument_id": ["aaa"],
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [100.0],
            "close_adj": [50.0],
            "volume": [1000.0],
        }
    )
    out = adjust_ohlc(long_df)
    # ratio = close_adj / close = 0.5 — open/high/low halved, close = close_adj
    assert out.loc[0, "open"] == 50.0
    assert out.loc[0, "high"] == 55.0
    assert out.loc[0, "low"] == 45.0
    assert out.loc[0, "close"] == 50.0


def test_adjust_ohlc_falls_back_when_close_adj_null() -> None:
    long_df = pd.DataFrame(
        {
            "date": ["2024-01-01"],
            "instrument_id": ["aaa"],
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [100.0],
            "close_adj": [None],
            "volume": [1000.0],
        }
    )
    out = adjust_ohlc(long_df)
    # close_adj null -> ratio 1.0, OHLC unchanged, close = raw close
    assert out.loc[0, "open"] == 100.0
    assert out.loc[0, "close"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/sde/test_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.research.sde.data'`

- [ ] **Step 3: Write the implementation**

`atlas/research/sde/data.py`:

```python
"""SDE Phase 0 data loaders.

Pulls the liquidity-defined universe and an OHLCV panel from
public.de_equity_ohlcv. open/high/low are rescaled by close_adj/close so
all four price columns are corporate-action consistent; close itself
becomes close_adj. Rows with a null/zero close_adj fall back to raw prices.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

# Liquid universe over the window: instruments whose median daily traded
# value (close * volume) clears the floor. Self-PIT — no index membership.
_UNIVERSE_SQL = """
    SELECT instrument_id::text AS instrument_id
      FROM public.de_equity_ohlcv
     WHERE date BETWEEN :start AND :end
       AND data_status IN ('raw', 'validated')
       AND close > 0 AND volume > 0
     GROUP BY instrument_id
    HAVING PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close * volume) >= :floor_inr
"""

_OHLCV_SQL = """
    SELECT date,
           instrument_id::text AS instrument_id,
           open, high, low, close, close_adj, volume
      FROM public.de_equity_ohlcv
     WHERE date BETWEEN :start AND :end
       AND instrument_id = ANY(CAST(:ids AS uuid[]))
       AND data_status IN ('raw', 'validated')
     ORDER BY instrument_id, date
"""


def load_liquid_universe(
    engine: Engine, *, start: date, end: date, floor_inr: float = 5e7
) -> list[str]:
    """Return instrument_id strings whose median traded value clears the floor.

    floor_inr default 5e7 = Rs 5 crore.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(_UNIVERSE_SQL),
            {"start": start, "end": end, "floor_inr": floor_inr},
        ).all()
    ids = [r.instrument_id for r in rows]
    log.info("sde_universe", n_instruments=len(ids))
    return ids


def adjust_ohlc(long_df: pd.DataFrame) -> pd.DataFrame:
    """Rescale open/high/low by the close_adj/close ratio and set close=close_adj.

    Where close_adj is null or close is non-positive, ratio falls back to 1.0
    and close falls back to the raw close.
    """
    df = long_df.copy()
    close_raw = pd.to_numeric(df["close"], errors="coerce")
    close_adj = pd.to_numeric(df["close_adj"], errors="coerce")
    ratio = (close_adj / close_raw).where(
        close_adj.notna() & (close_raw > 0), 1.0
    )
    for col in ("open", "high", "low"):
        df[col] = pd.to_numeric(df[col], errors="coerce") * ratio
    df["close"] = close_adj.where(close_adj.notna(), close_raw)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "instrument_id", "open", "high", "low", "close", "volume"]]


def load_ohlcv_panel(
    engine: Engine, *, instrument_ids: Sequence[str], start: date, end: date
) -> pd.DataFrame:
    """Load a corporate-action-adjusted OHLCV long DataFrame for the given ids.

    Returns columns: date, instrument_id, open, high, low, close, volume.
    """
    with engine.connect() as conn:
        long_df = pd.read_sql(
            text(_OHLCV_SQL),
            conn,
            params={"start": start, "end": end, "ids": list(instrument_ids)},
        )
    if long_df.empty:
        return long_df
    panel = adjust_ohlc(long_df)
    log.info("sde_ohlcv_panel", rows=len(panel), instruments=panel["instrument_id"].nunique())
    return panel
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/research/sde/test_data.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/research/sde/data.py tests/research/sde/test_data.py
git commit -m "feat(sde): universe + OHLCV loaders with corporate-action rescaling"
```

---

## Task 3: Factor catalog, factor generation, liquidity mask

**Files:**
- Create: `atlas/research/sde/factors.py`
- Test: `tests/research/sde/test_factors.py`

- [ ] **Step 1: Write the failing test**

`tests/research/sde/test_factors.py`:

```python
"""Tests for SDE Phase 0 factor generation and liquidity mask."""

from __future__ import annotations

import pandas as pd

from atlas.research.sde.factors import (
    FACTOR_CATALOG,
    generate_factors,
    liquidity_mask,
)


def test_generate_factors_returns_every_catalog_key(ohlcv_panel: pd.DataFrame) -> None:
    factors = generate_factors(ohlcv_panel)
    assert set(factors.keys()) == set(FACTOR_CATALOG.keys())


def test_factor_frame_has_multiindex_and_factor_column(
    ohlcv_panel: pd.DataFrame,
) -> None:
    factors = generate_factors(ohlcv_panel)
    frame = factors["roc_63"]
    assert list(frame.index.names) == ["date", "instrument_id"]
    assert list(frame.columns) == ["factor"]
    assert len(frame) > 0


def test_liquidity_mask_flags_low_traded_value(ohlcv_panel: pd.DataFrame) -> None:
    # Force instrument "ccc" to near-zero volume -> illiquid.
    panel = ohlcv_panel.copy()
    panel.loc[panel["instrument_id"] == "ccc", "volume"] = 1.0
    mask = liquidity_mask(panel, floor_inr=5e7, window=60)
    ccc = mask.xs("ccc", level="instrument_id")
    aaa = mask.xs("aaa", level="instrument_id")
    assert not ccc.any()       # ccc never clears the floor
    assert aaa.tail(100).any()  # aaa does, once the rolling window fills
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/sde/test_factors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.research.sde.factors'`

- [ ] **Step 3: Write the implementation**

`atlas/research/sde/factors.py`:

```python
"""SDE Phase 0 factor catalog and generation.

Each catalog entry maps a single instrument's OHLCV frame (date-indexed,
columns open/high/low/close/volume) to a Series of factor values.
generate_factors runs the whole catalog across an OHLCV panel and returns,
per factor, a (date, instrument_id) MultiIndex frame with one 'factor'
column — the shape ic_engine.compute_ic_over_window expects.

The catalog is a curated, countable seed library across the standard
families: momentum, mean-reversion, volatility, volume, range, and
return-distribution. ~20 factors keeps the search space small enough to
honestly account for in the IC interpretation.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pandas_ta as ta
import structlog

log = structlog.get_logger()


def _ret(df: pd.DataFrame) -> pd.Series:
    return df["close"].pct_change()


# name -> function(single-instrument OHLCV frame) -> Series
FACTOR_CATALOG: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    # momentum
    "roc_63": lambda df: ta.roc(df["close"], length=63),
    "roc_126": lambda df: ta.roc(df["close"], length=126),
    "roc_252": lambda df: ta.roc(df["close"], length=252),
    "rsi_14": lambda df: ta.rsi(df["close"], length=14),
    "ema_ratio_50": lambda df: df["close"] / ta.ema(df["close"], length=50) - 1.0,
    # mean-reversion
    "rsi_3": lambda df: ta.rsi(df["close"], length=3),
    "dist_sma_20": lambda df: df["close"] / ta.sma(df["close"], length=20) - 1.0,
    "dist_sma_200": lambda df: df["close"] / ta.sma(df["close"], length=200) - 1.0,
    # volatility
    "atr_pct_14": lambda df: ta.atr(df["high"], df["low"], df["close"], length=14)
    / df["close"],
    "natr_14": lambda df: ta.natr(df["high"], df["low"], df["close"], length=14),
    "vol_21": lambda df: _ret(df).rolling(21).std(),
    "vol_63": lambda df: _ret(df).rolling(63).std(),
    # volume
    "vol_ratio_20": lambda df: df["volume"] / df["volume"].rolling(20).mean(),
    "obv_chg_21": lambda df: ta.obv(df["close"], df["volume"]).pct_change(21),
    "mfi_14": lambda df: ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=14),
    "cmf_20": lambda df: ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=20),
    # range / price location
    "prox_52w_high": lambda df: df["close"] / df["close"].rolling(252).max(),
    "prox_52w_low": lambda df: df["close"] / df["close"].rolling(252).min(),
    # return distribution
    "skew_63": lambda df: _ret(df).rolling(63).skew(),
    "kurt_63": lambda df: _ret(df).rolling(63).kurt(),
}


def generate_factors(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run the factor catalog across an OHLCV panel.

    panel: long DataFrame with date, instrument_id, open/high/low/close/volume.
    Returns dict[factor_name -> DataFrame], each indexed by a
    (date, instrument_id) MultiIndex with a single 'factor' column.
    """
    collected: dict[str, list[pd.DataFrame]] = {name: [] for name in FACTOR_CATALOG}
    for iid, group in panel.groupby("instrument_id", sort=False):
        idf = group.sort_values("date").set_index("date")
        for name, fn in FACTOR_CATALOG.items():
            series = fn(idf)
            if series is None:
                continue
            frame = pd.DataFrame({"factor": pd.Series(series.to_numpy(), index=idf.index)})
            frame["instrument_id"] = iid
            collected[name].append(frame)

    result: dict[str, pd.DataFrame] = {}
    for name, frames in collected.items():
        if not frames:
            result[name] = pd.DataFrame(
                {"factor": pd.Series(dtype="float64")},
                index=pd.MultiIndex.from_arrays([[], []], names=["date", "instrument_id"]),
            )
            continue
        df = pd.concat(frames)
        df = df.set_index("instrument_id", append=True)
        df.index = df.index.set_names(["date", "instrument_id"])
        result[name] = df[["factor"]].dropna()

    log.info("sde_factors_generated", n_factors=len(result))
    return result


def liquidity_mask(
    panel: pd.DataFrame, *, floor_inr: float = 5e7, window: int = 60
) -> pd.Series:
    """Per-(date, instrument) boolean: trailing-`window`-day median traded
    value (close * volume) is at or above the floor.

    Returned as a boolean Series on a (date, instrument_id) MultiIndex.
    This is the point-in-time liquidity gate — it drops days where a kept
    instrument was temporarily illiquid (e.g. early in its listed history).
    """
    df = panel.sort_values(["instrument_id", "date"]).copy()
    df["traded_value"] = df["close"] * df["volume"]
    df["median_tv"] = df.groupby("instrument_id")["traded_value"].transform(
        lambda s: s.rolling(window, min_periods=window // 2).median()
    )
    indexed = df.set_index(["date", "instrument_id"])
    return (indexed["median_tv"] >= floor_inr).fillna(False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/research/sde/test_factors.py -v`
Expected: PASS (all three tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/research/sde/factors.py tests/research/sde/test_factors.py
git commit -m "feat(sde): factor catalog, generation, and PIT liquidity mask"
```

---

## Task 4: IC ranking and decision gate

**Files:**
- Create: `atlas/research/sde/ic_ranking.py`
- Test: `tests/research/sde/test_ic_ranking.py`

- [ ] **Step 1: Write the failing test**

`tests/research/sde/test_ic_ranking.py`:

```python
"""Tests for SDE Phase 0 IC ranking and decision gate."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from atlas.research.sde.ic_ranking import (
    FactorICRow,
    evaluate_gate,
    forward_returns_wide,
    rank_factors,
    time_split,
)


def test_time_split_70_30() -> None:
    dates = pd.bdate_range("2022-01-03", periods=100)
    train, test = time_split(dates, train_frac=0.7)
    assert len(train) == 70
    assert len(test) == 30
    assert train[-1] < test[0]


def test_forward_returns_wide_computes_simple_return() -> None:
    close_panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=4).tolist(),
            "instrument_id": ["aaa"] * 4,
            "close": [10.0, 11.0, 12.0, 13.0],
        }
    )
    fwd = forward_returns_wide(close_panel, horizon=1)
    # forward 1-day return at row 0 = 11/10 - 1 = 0.1
    assert abs(fwd.iloc[0]["aaa"] - 0.1) < 1e-9


def test_rank_factors_orders_by_abs_test_ic() -> None:
    # Two factors; fake ic_fn returns a fixed IC per factor via call order.
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2022-01-03", periods=10), ["aaa"]],
        names=["date", "instrument_id"],
    )
    factors = {
        "weak": pd.DataFrame({"factor": range(10)}, index=idx),
        "strong": pd.DataFrame({"factor": range(10)}, index=idx),
    }
    close_panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=10).tolist(),
            "instrument_id": ["aaa"] * 10,
            "close": [10.0 + i for i in range(10)],
        }
    )
    ic_by_factor = {"weak": 0.01, "strong": 0.20}
    calls: list[str] = []

    def fake_ic_fn(factor_frame: pd.DataFrame, returns_wide: pd.DataFrame):
        # factor_frame carries the factor name via attrs set in rank_factors.
        name = factor_frame.attrs["sde_name"]
        calls.append(name)
        return SimpleNamespace(
            mean_ic=ic_by_factor[name], ic_t_stat=3.0, n_observations=5
        )

    rows = rank_factors(
        factors, close_panel, horizons=[1], ic_fn=fake_ic_fn, train_frac=0.7
    )
    assert rows[0].factor == "strong"
    assert rows[1].factor == "weak"


def test_evaluate_gate_proceeds_on_strong_factor() -> None:
    rows = [
        FactorICRow("x", 63, train_ic=0.05, train_t=3.0, test_ic=0.04, test_t=2.5, n_test=20),
    ]
    result = evaluate_gate(rows, min_ic=0.03, min_t=2.0)
    assert result["proceed"] is True


def test_evaluate_gate_stops_on_weak_or_sign_flipped() -> None:
    rows = [
        FactorICRow("a", 63, train_ic=0.05, train_t=3.0, test_ic=0.01, test_t=0.5, n_test=20),
        FactorICRow("b", 63, train_ic=0.05, train_t=3.0, test_ic=-0.04, test_t=2.5, n_test=20),
    ]
    result = evaluate_gate(rows, min_ic=0.03, min_t=2.0)
    assert result["proceed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/sde/test_ic_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.research.sde.ic_ranking'`

- [ ] **Step 3: Write the implementation**

`atlas/research/sde/ic_ranking.py`:

```python
"""SDE Phase 0 IC ranking and decision gate.

Splits the date range into a train/test slice, computes forward returns,
and ranks each factor by out-of-sample IC. The IC function is injected
(ic_fn) so this module carries no cross-context import — the spike script
passes in atlas.intelligence.validation.ic_engine.compute_ic_over_window.

Honesty note: with overlapping forward-return windows the per-date IC
series is autocorrelated, so the injected t-stat is optimistic. Phase 0
treats it as a coarse screen; the autocorrelation correction is a Phase 1
concern.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd
import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class FactorICRow:
    """One factor's IC measured on the train and test splits at one horizon."""

    factor: str
    horizon: int
    train_ic: float
    train_t: float
    test_ic: float
    test_t: float
    n_test: int


def time_split(
    dates: Sequence[pd.Timestamp], *, train_frac: float = 0.7
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Split a set of dates chronologically into (train, test) DatetimeIndexes."""
    uniq = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dates).unique()))
    cut = int(len(uniq) * train_frac)
    return uniq[:cut], uniq[cut:]


def forward_returns_wide(close_panel: pd.DataFrame, *, horizon: int) -> pd.DataFrame:
    """Wide forward-return DataFrame: index=date, columns=instrument_id.

    close_panel: long DataFrame with date, instrument_id, close.
    Value at (t, i) = close[t+horizon] / close[t] - 1.
    """
    wide = close_panel.pivot(index="date", columns="instrument_id", values="close")
    wide.index = pd.DatetimeIndex(wide.index)
    return wide.shift(-horizon) / wide - 1.0


def rank_factors(
    factors: dict[str, pd.DataFrame],
    close_panel: pd.DataFrame,
    *,
    horizons: Sequence[int],
    ic_fn: Callable[[pd.DataFrame, pd.DataFrame], object],
    mask: pd.Series | None = None,
    train_frac: float = 0.7,
) -> list[FactorICRow]:
    """Rank factors by absolute out-of-sample IC across horizons.

    factors: dict[name -> (date, instrument_id) MultiIndex 'factor' frame].
    ic_fn: callable(factor_frame, returns_wide) -> object with attributes
           mean_ic, ic_t_stat, n_observations.
    mask: optional (date, instrument_id) boolean Series; factor rows where
          the mask is False are dropped before IC computation.
    """
    rows: list[FactorICRow] = []
    for horizon in horizons:
        fwd = forward_returns_wide(close_panel, horizon=horizon)
        train_d, test_d = time_split(fwd.index, train_frac=train_frac)
        for name, frame in factors.items():
            if mask is not None:
                aligned = mask.reindex(frame.index).fillna(False)
                frame = frame[aligned]
            if frame.empty:
                continue
            fdates = frame.index.get_level_values("date")
            train_frame = frame[fdates.isin(train_d)].copy()
            test_frame = frame[fdates.isin(test_d)].copy()
            train_frame.attrs["sde_name"] = name
            test_frame.attrs["sde_name"] = name
            train_ic = ic_fn(train_frame, fwd.loc[fwd.index.intersection(train_d)])
            test_ic = ic_fn(test_frame, fwd.loc[fwd.index.intersection(test_d)])
            rows.append(
                FactorICRow(
                    factor=name,
                    horizon=horizon,
                    train_ic=float(train_ic.mean_ic),  # type: ignore[attr-defined]
                    train_t=float(train_ic.ic_t_stat),  # type: ignore[attr-defined]
                    test_ic=float(test_ic.mean_ic),  # type: ignore[attr-defined]
                    test_t=float(test_ic.ic_t_stat),  # type: ignore[attr-defined]
                    n_test=int(test_ic.n_observations),  # type: ignore[attr-defined]
                )
            )

    rows.sort(
        key=lambda r: abs(r.test_ic) if pd.notna(r.test_ic) else 0.0, reverse=True
    )
    log.info("sde_factors_ranked", n_rows=len(rows))
    return rows


def evaluate_gate(
    rows: Sequence[FactorICRow], *, min_ic: float = 0.03, min_t: float = 2.0
) -> dict[str, object]:
    """Decision gate. PROCEED if at least one factor/horizon has out-of-sample
    IC of the same sign as its train IC, with |test_ic| >= min_ic and
    |test_t| >= min_t. Otherwise STOP.
    """
    survivors = [
        r
        for r in rows
        if pd.notna(r.test_ic)
        and pd.notna(r.train_ic)
        and (r.test_ic > 0) == (r.train_ic > 0)
        and abs(r.test_ic) >= min_ic
        and abs(r.test_t) >= min_t
    ]
    return {"proceed": bool(survivors), "survivors": survivors}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/research/sde/test_ic_ranking.py -v`
Expected: PASS (all five tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/research/sde/ic_ranking.py tests/research/sde/test_ic_ranking.py
git commit -m "feat(sde): IC ranking across horizons + decision gate"
```

---

## Task 5: Pre-flight checks script

**Files:**
- Create: `scripts/sde_preflight_checks.py`
- Test: `tests/research/sde/test_preflight.py`

- [ ] **Step 1: Write the failing test**

`tests/research/sde/test_preflight.py`:

```python
"""Tests for the SDE pre-flight report formatter."""

from __future__ import annotations

from scripts.sde_preflight_checks import PreflightResult, format_preflight


def test_format_preflight_pass_on_good_data() -> None:
    result = PreflightResult(
        adj_total=1000, adj_with=950, delisted=100, delisted_with_history=95
    )
    text = format_preflight(result)
    assert "Check 1 PASS" in text
    assert "Check 2 PASS" in text


def test_format_preflight_warn_on_low_coverage() -> None:
    result = PreflightResult(
        adj_total=1000, adj_with=200, delisted=100, delisted_with_history=10
    )
    text = format_preflight(result)
    assert "Check 1 WARN" in text
    assert "Check 2 WARN" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/sde/test_preflight.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.sde_preflight_checks'`

- [ ] **Step 3: Write the implementation**

`scripts/sde_preflight_checks.py`:

```python
"""SDE pre-flight data-integrity checks. Run on EC2 before the Phase 0 spike.

Check 1 - corporate-action adjustment coverage: fraction of recent OHLCV
rows with a non-null close_adj. Low coverage means factors computed on
COALESCE(close_adj, close) sit partly on unadjusted prices.

Check 2 - delisted-stock history retention: instruments last seen well in
the past should still carry full history. If dead stocks were purged,
survivorship bias re-enters the universe.

Usage (on EC2 host jsl-wealth-server):
    python -m scripts.sde_preflight_checks
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()

_ADJ_SQL = """
    SELECT count(*) AS total,
           count(close_adj) AS with_adj
      FROM public.de_equity_ohlcv
     WHERE date >= current_date - INTERVAL '2 years'
"""

_DELISTED_SQL = """
    WITH last_seen AS (
      SELECT instrument_id, max(date) AS last_date, count(*) AS n_rows
        FROM public.de_equity_ohlcv
       GROUP BY instrument_id
    )
    SELECT count(*) FILTER (
             WHERE last_date < current_date - INTERVAL '180 days'
           ) AS delisted,
           count(*) FILTER (
             WHERE last_date < current_date - INTERVAL '180 days'
               AND n_rows >= 250
           ) AS delisted_with_history
      FROM last_seen
"""


@dataclass(frozen=True)
class PreflightResult:
    """Raw counts from the two pre-flight queries."""

    adj_total: int
    adj_with: int
    delisted: int
    delisted_with_history: int


def run_preflight(engine: Engine) -> PreflightResult:
    """Execute both pre-flight queries and return the raw counts."""
    with engine.connect() as conn:
        adj = conn.execute(text(_ADJ_SQL)).one()
        dl = conn.execute(text(_DELISTED_SQL)).one()
    return PreflightResult(
        adj_total=int(adj.total),
        adj_with=int(adj.with_adj),
        delisted=int(dl.delisted),
        delisted_with_history=int(dl.delisted_with_history),
    )


def format_preflight(result: PreflightResult) -> str:
    """Render the pre-flight result as a human-readable report.

    Check 1 passes at >= 80% close_adj coverage. Check 2 passes when >= 80%
    of delisted instruments still carry >= 250 rows of history.
    """
    adj_pct = (result.adj_with / result.adj_total * 100) if result.adj_total else 0.0
    hist_pct = (
        (result.delisted_with_history / result.delisted * 100)
        if result.delisted
        else 0.0
    )
    check1 = "PASS" if adj_pct >= 80 else "WARN"
    check2 = "PASS" if hist_pct >= 80 else "WARN"
    return "\n".join(
        [
            "SDE pre-flight checks",
            f"  close_adj coverage  : {adj_pct:.1f}%  "
            f"({result.adj_with}/{result.adj_total} rows, last 2y)",
            f"  delisted instruments: {result.delisted}",
            f"  ...with >=250 rows  : {result.delisted_with_history} ({hist_pct:.1f}%)",
            "",
            f"  Check 1 {check1}: corporate-action adjustment coverage",
            f"  Check 2 {check2}: delisted-stock history retention",
        ]
    )


def main() -> None:
    report = format_preflight(run_preflight(get_engine()))
    log.info("sde_preflight_done")
    print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/research/sde/test_preflight.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/sde_preflight_checks.py tests/research/sde/test_preflight.py
git commit -m "feat(sde): pre-flight data-integrity checks"
```

---

## Task 6: Phase 0 spike orchestrator + EC2 run

**Files:**
- Create: `scripts/sde_phase0_spike.py`

- [ ] **Step 1: Write the spike orchestrator**

`scripts/sde_phase0_spike.py`:

```python
"""SDE Phase 0 spike - does any pandas-ta factor have tradeable
out-of-sample IC on the liquid Indian-equity universe?

Wires the SDE pure modules to the existing IC engine and writes a ranked
results report with a PROCEED / STOP verdict.

Run on EC2 (Mac psycopg2 is broken - see reference_ec2_access):
    ssh jsl-wealth-server
    cd <atlas-os repo checkout>
    git pull
    python -m scripts.sde_phase0_spike
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import structlog

from atlas.db import get_engine
from atlas.intelligence.validation.ic_engine import compute_ic_over_window
from atlas.research.sde.data import load_liquid_universe, load_ohlcv_panel
from atlas.research.sde.factors import generate_factors, liquidity_mask
from atlas.research.sde.ic_ranking import FactorICRow, evaluate_gate, rank_factors

log = structlog.get_logger()

# ~3m / 6m / 12m in trading days.
HORIZONS = [63, 126, 252]
OUT_PATH = Path("docs/sde/phase0-ic-results.md")


def _write_report(rows: list[FactorICRow], gate: dict[str, object]) -> None:
    verdict = "PROCEED to Phase 1" if gate["proceed"] else "STOP - no tradeable factor IC"
    lines = [
        "# SDE Phase 0 - Factor IC Results",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        f"## Decision: {verdict}",
        "",
        f"Survivors (out-of-sample IC, same sign as train, |IC|>=0.03, |t|>=2.0): "
        f"{len(gate['survivors'])}",  # type: ignore[arg-type]
        "",
        "| Factor | Horizon | Train IC | Train t | Test IC | Test t | N test |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| {r.factor} | {r.horizon} | {r.train_ic:.4f} | {r.train_t:.2f} "
            f"| {r.test_ic:.4f} | {r.test_t:.2f} | {r.n_test} |"
        )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    engine = get_engine()
    end = date.today()
    start = end - timedelta(days=365 * 6)  # ~5y usable after factor warm-up

    universe = load_liquid_universe(engine, start=start, end=end)
    panel = load_ohlcv_panel(engine, instrument_ids=universe, start=start, end=end)
    if panel.empty:
        raise SystemExit("sde_phase0: OHLCV panel is empty - check the date range/universe")

    factors = generate_factors(panel)
    mask = liquidity_mask(panel)
    close_panel = panel[["date", "instrument_id", "close"]]

    rows = rank_factors(
        factors, close_panel, horizons=HORIZONS, ic_fn=compute_ic_over_window, mask=mask
    )
    gate = evaluate_gate(rows)
    _write_report(rows, gate)

    log.info(
        "sde_phase0_done",
        proceed=gate["proceed"],
        n_survivors=len(gate["survivors"]),  # type: ignore[arg-type]
        report=str(OUT_PATH),
    )
    print(f"Phase 0 complete. Verdict: {'PROCEED' if gate['proceed'] else 'STOP'}")
    print(f"Report written to {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the orchestrator imports cleanly**

Run: `python -c "import scripts.sde_phase0_spike"`
Expected: no output, exit 0 (imports resolve; no DB connection attempted at import time).

- [ ] **Step 3: Commit**

```bash
git add scripts/sde_phase0_spike.py
git commit -m "feat(sde): Phase 0 spike orchestrator"
```

- [ ] **Step 4: Run the pre-flight checks on EC2**

```bash
ssh jsl-wealth-server
cd <atlas-os repo checkout>   # path per reference_ec2_access memory
git pull
python -m scripts.sde_preflight_checks
```

Expected: a printed report. Record the result. If Check 1 (close_adj
coverage) is WARN, note it — factor IC will sit partly on unadjusted
prices and the spike numbers carry that caveat. Do not silently proceed
past a WARN; surface it to the user.

- [ ] **Step 5: Run the Phase 0 spike on EC2**

```bash
python -m scripts.sde_phase0_spike
```

Expected: console prints `Verdict: PROCEED` or `Verdict: STOP`, and
`docs/sde/phase0-ic-results.md` is written with the ranked IC table.

- [ ] **Step 6: Commit the results report and report back to the user**

```bash
git add docs/sde/phase0-ic-results.md
git commit -m "chore(sde): Phase 0 factor IC results"
```

Then summarize for the user: the verdict, the top factors by out-of-sample
IC, and the pre-flight WARN status if any. This is the go/no-go gate —
Phase 1 is planned only if the verdict is PROCEED.

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-05-20-signal-discovery-engine-design.md`):

- Pre-flight checks (corporate-action adjustment, delisted history) → Task 5 + Task 6 Step 4.
- Liquidity-defined, self-PIT-correct universe → Task 2 (`load_liquid_universe`) + Task 3 (`liquidity_mask`).
- Label = cross-sectional relative return rank, 3m/6m/12m → Task 4 (`forward_returns_wide` + `compute_ic_over_window`, which is Spearman rank IC computed cross-sectionally per date; horizons 63/126/252).
- Curated seed library, ~20 factors → Task 3 (`FACTOR_CATALOG`).
- Phase 0 spike with go/no-go gate → Task 4 (`evaluate_gate`) + Task 6.
- Integration over invention → reuses `ic_engine.compute_ic_over_window`; zero new dependencies.
- Honest validation (search-count awareness, autocorrelation caveat) → documented in `ic_ranking.py` module docstring; ~20-factor catalog kept small deliberately.

**Refinements logged vs the spec:** the spec named `atlas_v6_clean_ohlcv` and `alphalens`; this branch has neither wired in (migration 091 is on the retired v6 branch; alphalens is an unused optional extra). The plan reads `public.de_equity_ohlcv` directly and reuses the in-repo `ic_engine`. Corrupt-row filtering (the v6 view's purpose) is deferred to Phase 1.

**Placeholder scan:** none — every step has complete code or an exact command. The one non-code unknown is the EC2 repo checkout path (Task 6), left as `<atlas-os repo checkout>` because it is an environment fact the operator confirms from the `reference_ec2_access` memory, not a code placeholder.

**Type consistency:** `FactorICRow` fields are consistent across `ic_ranking.py`, its tests, and the spike report. `ic_fn` is duck-typed on `.mean_ic` / `.ic_t_stat` / `.n_observations` — matching `ICResult` in `atlas/intelligence/validation/ic_engine.py` and the `SimpleNamespace` fake in the test.
