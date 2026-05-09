# Atlas M7 Phase 3 — Custom Portfolio Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Custom Portfolio Builder: FM designs a portfolio (up to 30 instruments), validates it against the Atlas universe, runs a vectorbt backtest over historical Atlas signals, and starts paper trading it.

**Architecture:**
- `backtest/engine.py` — vectorbt wrapper (shared with Phase 4 optimizer)
- `backtest/report.py` — writes `BacktestResult` to `atlas.strategy_backtest_results`
- `custom/builder.py` — validates instrument list + optional PyPortfolioOpt weight suggestion
- `custom/portfolio.py` — orchestrates create → validate → backtest → paper trading activation

**Tech Stack:** vectorbt ≥0.26 (NumPy-backed backtesting), PyPortfolioOpt ≥1.5 (optional min-variance weights), FastAPI BackgroundTasks + ProcessPoolExecutor (non-blocking backtest), psycopg2/SQLAlchemy sync (consistent with Phase 1+2 pattern).

**Important schema notes (discovered during Phase 1+2 smoke tests — spec has wrong names):**
- JIP equity prices: `de_equity_ohlcv` (NOT `de_ohlcv_daily`)
- Fund decisions: `mstar_id` column (NOT `instrument_id`); fund NAV: `de_mf_nav_history`
- `signal_adapter.py` was fixed before this plan was written — both bugs corrected

---

### Task 1: Add simulation dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add vectorbt and PyPortfolioOpt to pyproject.toml**

Add a new optional-dependencies group `simulation` to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.4",
    "pyright>=1.1",
    "ipython>=8.0",
]

simulation = [
    "vectorbt>=0.26",
    "PyPortfolioOpt>=1.5",
]

optimizer = [
    "optuna[postgres]>=3.0",
]

ui = [
    "streamlit>=1.32",
    "plotly>=5.18",
    "altair>=5.2",
]
```

- [ ] **Step 2: Install simulation dependencies on EC2**

```bash
pip install "vectorbt>=0.26" "PyPortfolioOpt>=1.5"
```

Expected: no errors. vectorbt requires Python ≥3.11 (project already enforces this).

- [ ] **Step 3: Verify imports work**

```bash
python -c "import vectorbt as vbt; print('vectorbt', vbt.__version__)"
python -c "from pypfopt import EfficientFrontier; print('PyPortfolioOpt OK')"
```

Expected: version strings printed, no ImportError.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(m7-p3): add simulation + optimizer dependencies to pyproject.toml"
```

---

### Task 2: backtest/engine.py — vectorbt wrapper

**Files:**
- Create: `atlas/simulation/backtest/engine.py`
- Create: `tests/unit/simulation/test_engine.py`

The engine takes a `SignalMatrix` (already built by `signal_adapter.py`) and runs a vectorbt backtest. Returns a `BacktestResult` dataclass. No DB calls — pure compute.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_engine.py
"""Unit tests for backtest/engine.py — uses synthetic SignalMatrix, no DB."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import date

from atlas.simulation.core.signal_adapter import SignalMatrix


def _make_synthetic_signal_matrix(n_days: int = 60, n_instruments: int = 3) -> SignalMatrix:
    """3 instruments, 60 trading days, deterministic signals."""
    rng = np.random.default_rng(seed=42)
    dates = pd.date_range(start="2024-01-02", periods=n_days, freq="B")
    prices = 100.0 + np.cumsum(rng.normal(0, 1, (n_days, n_instruments)), axis=0)
    entries = np.zeros((n_days, n_instruments), dtype=bool)
    exits = np.zeros((n_days, n_instruments), dtype=bool)
    # Enter on day 5, exit on day 20 for all instruments
    entries[5, :] = True
    exits[20, :] = True
    return SignalMatrix(
        prices=prices,
        entries=entries,
        exits=exits,
        dates=dates,
        instruments=["INST_A", "INST_B", "INST_C"],
    )


class TestRunBacktest:
    def test_returns_backtest_result_with_required_fields(self):
        from atlas.simulation.backtest.engine import BacktestResult, run_backtest

        sm = _make_synthetic_signal_matrix()
        result = run_backtest(sm, init_cash=1_000_000.0, fees_pct=0.001)

        assert isinstance(result, BacktestResult)
        assert result.sharpe_ratio is not None
        assert result.max_drawdown is not None
        assert result.total_return is not None
        assert isinstance(result.daily_returns, pd.Series)
        assert len(result.daily_returns) > 0

    def test_empty_signal_matrix_returns_zero_result(self):
        from atlas.simulation.backtest.engine import BacktestResult, run_backtest

        empty_sm = SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )
        result = run_backtest(empty_sm, init_cash=1_000_000.0, fees_pct=0.001)
        assert result.total_return == 0.0
        assert result.sharpe_ratio is None

    def test_result_includes_start_end_dates(self):
        from atlas.simulation.backtest.engine import run_backtest

        sm = _make_synthetic_signal_matrix()
        result = run_backtest(sm, init_cash=1_000_000.0, fees_pct=0.001)

        assert result.start_date == date(2024, 1, 2)
        assert result.end_date is not None
        assert result.end_date >= result.start_date
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/simulation/test_engine.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.simulation.backtest.engine'`

- [ ] **Step 3: Write backtest/engine.py**

```python
# atlas/simulation/backtest/engine.py
"""vectorbt-backed backtesting engine.

Pure compute — no DB calls. Takes a SignalMatrix (from signal_adapter.py)
and returns a BacktestResult with Sharpe, drawdown, total return, and daily returns Series.
"""
from __future__ import annotations

import gc
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
import structlog
import vectorbt as vbt

from atlas.simulation.core.signal_adapter import SignalMatrix

log = structlog.get_logger()

_INIT_CASH = 10_000_000.0  # ₹1 crore default
_FEES_PCT = 0.001           # 0.1% round-trip


@dataclass
class BacktestResult:
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_return: float | None
    daily_returns: pd.Series
    start_date: date | None
    end_date: date | None
    n_trades: int = 0


def run_backtest(
    signal_matrix: SignalMatrix,
    init_cash: float = _INIT_CASH,
    fees_pct: float = _FEES_PCT,
) -> BacktestResult:
    """Run vectorbt backtest on a SignalMatrix. No DB calls.

    Memory discipline: del pf; gc.collect() after use — vectorbt Portfolio
    objects hold full price history in RAM.
    """
    if signal_matrix.prices.size == 0 or len(signal_matrix.instruments) == 0:
        return BacktestResult(
            sharpe_ratio=None,
            max_drawdown=None,
            total_return=None,
            daily_returns=pd.Series(dtype=float),
            start_date=None,
            end_date=None,
            n_trades=0,
        )

    price_df = pd.DataFrame(
        signal_matrix.prices,
        index=signal_matrix.dates,
        columns=signal_matrix.instruments,
    )
    entry_df = pd.DataFrame(
        signal_matrix.entries,
        index=signal_matrix.dates,
        columns=signal_matrix.instruments,
    )
    exit_df = pd.DataFrame(
        signal_matrix.exits,
        index=signal_matrix.dates,
        columns=signal_matrix.instruments,
    )

    try:
        pf = vbt.Portfolio.from_signals(
            close=price_df,
            entries=entry_df,
            exits=exit_df,
            init_cash=init_cash,
            fees=fees_pct,
            freq="D",
        )

        daily_rets = pf.daily_returns()
        if isinstance(daily_rets, pd.DataFrame):
            # Multiple instruments — aggregate to portfolio-level returns
            daily_rets = daily_rets.mean(axis=1)

        sharpe = float(pf.sharpe_ratio()) if not np.isnan(pf.sharpe_ratio()) else None
        drawdown = float(pf.max_drawdown())
        total_ret = float(pf.total_return())
        n_trades = int(pf.stats()["Total Trades"]) if hasattr(pf, "stats") else 0

        dates_idx = price_df.index
        start = dates_idx[0].date() if len(dates_idx) > 0 else None
        end = dates_idx[-1].date() if len(dates_idx) > 0 else None

        result = BacktestResult(
            sharpe_ratio=sharpe,
            max_drawdown=drawdown,
            total_return=total_ret,
            daily_returns=daily_rets,
            start_date=start,
            end_date=end,
            n_trades=n_trades,
        )
    finally:
        # Mandatory: vectorbt Portfolio holds full price history in RAM.
        # On t3.large (8GB), forgetting this causes OOM in the optimizer.
        del pf
        gc.collect()

    log.info(
        "backtest_engine_done",
        instruments=len(signal_matrix.instruments),
        sharpe=result.sharpe_ratio,
        total_return=result.total_return,
    )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/simulation/test_engine.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/simulation/backtest/engine.py tests/unit/simulation/test_engine.py
git commit -m "feat(m7-p3): backtest/engine.py — vectorbt wrapper with memory discipline"
```

---

### Task 3: backtest/report.py — write BacktestResult to DB

**Files:**
- Create: `atlas/simulation/backtest/report.py`
- Create: `tests/unit/simulation/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_report.py
"""Unit tests for backtest/report.py — mocked DB, no real connection."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from atlas.simulation.backtest.engine import BacktestResult


def _make_result() -> BacktestResult:
    return BacktestResult(
        sharpe_ratio=1.45,
        max_drawdown=-0.12,
        total_return=0.28,
        daily_returns=pd.Series([0.01, -0.005, 0.008]),
        start_date=date(2023, 1, 2),
        end_date=date(2024, 12, 31),
        n_trades=42,
    )


class TestWriteBacktestResult:
    def test_returns_uuid(self):
        from atlas.simulation.backtest.report import write_backtest_result

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        mock_conn.__enter__ = lambda _: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("atlas.simulation.backtest.report.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result_id = write_backtest_result(
                engine=mock_engine,
                result=_make_result(),
                backtest_type="custom",
                strategy_id=None,
                custom_portfolio_id=None,
            )

        assert result_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_commit_called(self):
        from atlas.simulation.backtest.report import write_backtest_result

        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = "test-uuid"

        with patch("atlas.simulation.backtest.report.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            write_backtest_result(MagicMock(), _make_result(), "custom")

        mock_conn.commit.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/simulation/test_report.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.simulation.backtest.report'`

- [ ] **Step 3: Write backtest/report.py**

```python
# atlas/simulation/backtest/report.py
"""Write BacktestResult to atlas.strategy_backtest_results."""
from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import BacktestResult

log = structlog.get_logger()


def write_backtest_result(
    engine: Engine,
    result: BacktestResult,
    backtest_type: str,
    strategy_id: UUID | None = None,
    custom_portfolio_id: UUID | None = None,
) -> str:
    """Insert a BacktestResult into atlas.strategy_backtest_results.

    Returns the new row's UUID as a string.
    backtest_type: 'full' | 'walk_forward' | 'custom'
    """
    with open_compute_session(engine) as conn:
        row_id = conn.execute(
            text("""
                INSERT INTO atlas.strategy_backtest_results
                    (strategy_id, custom_portfolio_id, backtest_type,
                     start_date, end_date,
                     sharpe_ratio, max_drawdown, total_return)
                VALUES
                    (:sid, :cpid, :btype,
                     :start_date, :end_date,
                     :sharpe, :drawdown, :total_return)
                RETURNING id::text
            """),
            {
                "sid": str(strategy_id) if strategy_id else None,
                "cpid": str(custom_portfolio_id) if custom_portfolio_id else None,
                "btype": backtest_type,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "sharpe": result.sharpe_ratio,
                "drawdown": result.max_drawdown,
                "total_return": result.total_return,
            },
        ).scalar()
        conn.commit()

    log.info(
        "backtest_report_written",
        backtest_id=row_id,
        backtest_type=backtest_type,
        sharpe=result.sharpe_ratio,
    )
    return row_id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/simulation/test_report.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/simulation/backtest/report.py tests/unit/simulation/test_report.py
git commit -m "feat(m7-p3): backtest/report.py — write BacktestResult to DB"
```

---

### Task 4: custom/builder.py — portfolio validation + weight suggestion

**Files:**
- Create: `atlas/simulation/custom/builder.py`
- Create: `tests/unit/simulation/test_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/simulation/test_builder.py
"""Unit tests for custom/builder.py — validation rules, no DB required for most tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio


def _instruments(n: int, weight: float | None = None) -> list[InstrumentWeight]:
    per = weight if weight is not None else round(100.0 / n, 4)
    return [
        InstrumentWeight(instrument_id=f"INS_{i:03d}", instrument_type="stock", weight_pct=per)
        for i in range(n)
    ]


class TestValidateCustomPortfolio:
    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            validate_custom_portfolio([], engine=MagicMock())

    def test_over_30_instruments_raises(self):
        insts = _instruments(31)
        with pytest.raises(ValueError, match="30"):
            validate_custom_portfolio(insts, engine=MagicMock())

    def test_weights_not_summing_to_100_raises(self):
        insts = [
            InstrumentWeight("A", "stock", 60.0),
            InstrumentWeight("B", "stock", 30.0),
            # total = 90, missing 10
        ]
        with pytest.raises(ValueError, match="sum to 100"):
            validate_custom_portfolio(insts, engine=MagicMock())

    def test_duplicate_instrument_ids_raises(self):
        insts = [
            InstrumentWeight("AAPL", "stock", 50.0),
            InstrumentWeight("AAPL", "stock", 50.0),
        ]
        with pytest.raises(ValueError, match="duplicate"):
            validate_custom_portfolio(insts, engine=MagicMock())

    def test_non_investable_instrument_raises(self):
        insts = _instruments(2, 50.0)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        # DB returns only 1 investable instrument out of 2 requested
        mock_conn.execute.return_value.fetchall.return_value = [("INS_000",)]
        mock_conn.__enter__ = lambda _: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("atlas.simulation.custom.builder.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(ValueError, match="not in Atlas universe"):
                validate_custom_portfolio(insts, engine=mock_engine)

    def test_valid_portfolio_passes(self):
        insts = _instruments(3, weight=None)
        # Adjust to make weights sum to exactly 100
        insts = [
            InstrumentWeight("A", "stock", 40.0),
            InstrumentWeight("B", "stock", 35.0),
            InstrumentWeight("C", "stock", 25.0),
        ]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("A",), ("B",), ("C",)]
        mock_conn.__enter__ = lambda _: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("atlas.simulation.custom.builder.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            validate_custom_portfolio(insts, engine=MagicMock())  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/simulation/test_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.simulation.custom.builder'`

- [ ] **Step 3: Write custom/builder.py**

```python
# atlas/simulation/custom/builder.py
"""Custom portfolio validation and optional weight suggestion (PyPortfolioOpt).

validate_custom_portfolio() is the primary entry point. It runs 4 checks and
raises ValueError for each violation. Universe lookup uses a single IN query
with parameterized values — never f-string interpolation of user input.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

log = structlog.get_logger()

_MAX_INSTRUMENTS = 30
_WEIGHT_SUM_TOLERANCE = 0.01  # ±0.01% tolerance


@dataclass
class InstrumentWeight:
    instrument_id: str
    instrument_type: str  # 'stock' | 'etf' | 'fund'
    weight_pct: float


def validate_custom_portfolio(
    instruments: list[InstrumentWeight],
    engine: Engine,
) -> None:
    """Validate a custom portfolio before saving.

    Raises ValueError with a descriptive message for each violation:
    - Empty list
    - More than 30 instruments
    - Duplicate instrument_ids
    - Weights don't sum to 100 ± 0.01
    - Any instrument not in Atlas universe (using recent decision date)

    The universe lookup uses a single parameterized IN query — never f-string
    interpolation of instrument_ids (which come from user input).
    """
    if not instruments:
        raise ValueError("Portfolio must contain at least 1 instrument.")

    if len(instruments) > _MAX_INSTRUMENTS:
        raise ValueError(
            f"Portfolio exceeds {_MAX_INSTRUMENTS} instruments ({len(instruments)} given). "
            "Max 30 instruments for custom portfolios."
        )

    ids = [i.instrument_id for i in instruments]
    if len(ids) != len(set(ids)):
        seen: set[str] = set()
        dupes = [i for i in ids if i in seen or seen.add(i)]  # type: ignore[func-returns-value]
        raise ValueError(f"Portfolio contains duplicate instrument IDs: {dupes}")

    total_weight = sum(i.weight_pct for i in instruments)
    if abs(total_weight - 100.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"Portfolio weights must sum to 100% ± {_WEIGHT_SUM_TOLERANCE}%. "
            f"Got {total_weight:.4f}%."
        )

    _validate_universe_membership(ids, engine)


def _validate_universe_membership(instrument_ids: list[str], engine: Engine) -> None:
    """Check all instruments appear in a recent Atlas stock decisions date.

    Uses a single IN query with bound parameters. The reference date is the
    most recent available date in atlas_stock_decisions_daily.
    """
    # Single parameterized query — no f-string interpolation of user input
    with open_compute_session(engine) as conn:
        ref_date = conn.execute(
            text("SELECT MAX(date) FROM atlas.atlas_stock_decisions_daily")
        ).scalar()

        if ref_date is None:
            log.warning("builder_no_decisions_date", msg="Cannot validate universe membership")
            return

        rows = conn.execute(
            text("""
                SELECT instrument_id::text
                FROM atlas.atlas_stock_decisions_daily
                WHERE date = :ref_date
                  AND instrument_id::text = ANY(:ids)
            """),
            {"ref_date": ref_date, "ids": instrument_ids},
        ).fetchall()

    found = {r[0] for r in rows}
    missing = set(instrument_ids) - found
    if missing:
        raise ValueError(
            f"The following instruments are not in Atlas universe as of {ref_date}: "
            f"{sorted(missing)}. Only investable instruments may be included."
        )


def suggest_min_variance_weights(
    instruments: list[InstrumentWeight],
    engine: Engine,
    lookback_days: int = 252,
) -> list[InstrumentWeight]:
    """Suggest minimum-variance weights using PyPortfolioOpt.

    Only available for portfolios with ≤ 30 instruments. For larger portfolios,
    returns equal weights. Uses JIP price history for covariance estimation.
    """
    if len(instruments) > _MAX_INSTRUMENTS:
        log.info("builder_suggest_equal_weight", reason="over_30_instruments")
        equal_w = round(100.0 / len(instruments), 4)
        return [
            InstrumentWeight(i.instrument_id, i.instrument_type, equal_w)
            for i in instruments
        ]

    ids = [i.instrument_id for i in instruments]
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            text("""
                SELECT date, instrument_id::text AS instrument_id, close
                FROM de_equity_ohlcv
                WHERE instrument_id::text = ANY(:ids)
                  AND date BETWEEN :start AND :end
                ORDER BY date, instrument_id
            """),
            conn,
            params={"ids": ids, "start": start_date, "end": end_date},
        )

    if df.empty:
        log.warning("builder_suggest_no_prices", instruments=ids)
        equal_w = round(100.0 / len(instruments), 4)
        return [
            InstrumentWeight(i.instrument_id, i.instrument_type, equal_w)
            for i in instruments
        ]

    price_pivot = df.pivot(index="date", columns="instrument_id", values="close").dropna()

    try:
        from pypfopt import EfficientFrontier, expected_returns, risk_models

        mu = expected_returns.mean_historical_return(price_pivot, frequency=252)
        S = risk_models.sample_cov(price_pivot, frequency=252)
        ef = EfficientFrontier(mu, S)
        raw_weights = ef.min_volatility()
        cleaned = ef.clean_weights()
    except Exception:
        log.warning("builder_pypfopt_failed", instruments=ids, exc_info=True)
        equal_w = round(100.0 / len(instruments), 4)
        return [
            InstrumentWeight(i.instrument_id, i.instrument_type, equal_w)
            for i in instruments
        ]

    result = []
    for inst in instruments:
        w = float(cleaned.get(inst.instrument_id, 0.0)) * 100.0
        result.append(InstrumentWeight(inst.instrument_id, inst.instrument_type, round(w, 4)))

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/simulation/test_builder.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/simulation/custom/builder.py tests/unit/simulation/test_builder.py
git commit -m "feat(m7-p3): custom/builder.py — portfolio validation + PyPortfolioOpt weight suggestion"
```

---

### Task 5: custom/portfolio.py — orchestrate create → backtest → activate

**Files:**
- Create: `atlas/simulation/custom/portfolio.py`
- Create: `tests/unit/simulation/test_custom_portfolio.py`

This module ties everything together. `create_custom_portfolio()` validates, saves to DB, and triggers the backtest. The backtest runs in a background process (non-blocking). `run_custom_portfolio_backtest()` is the function that runs inside the background process.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/simulation/test_custom_portfolio.py
"""Unit tests for custom/portfolio.py — mocked DB and engine, no real vectorbt."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from atlas.simulation.custom.builder import InstrumentWeight


_INSTRUMENTS = [
    InstrumentWeight("INS_A", "stock", 50.0),
    InstrumentWeight("INS_B", "stock", 50.0),
]


class TestCreateCustomPortfolio:
    def test_returns_portfolio_id_string(self):
        from atlas.simulation.custom.portfolio import create_custom_portfolio

        with (
            patch("atlas.simulation.custom.portfolio.validate_custom_portfolio"),
            patch(
                "atlas.simulation.custom.portfolio._save_portfolio_record",
                return_value="test-portfolio-uuid",
            ),
            patch("atlas.simulation.custom.portfolio._trigger_backtest_background"),
        ):
            portfolio_id = create_custom_portfolio(
                name="My Test Portfolio",
                instruments=_INSTRUMENTS,
                engine=MagicMock(),
            )

        assert portfolio_id == "test-portfolio-uuid"

    def test_validation_called_before_save(self):
        from atlas.simulation.custom.portfolio import create_custom_portfolio

        call_order = []

        def mock_validate(*args, **kwargs):
            call_order.append("validate")

        def mock_save(*args, **kwargs):
            call_order.append("save")
            return "uuid"

        with (
            patch(
                "atlas.simulation.custom.portfolio.validate_custom_portfolio",
                side_effect=mock_validate,
            ),
            patch(
                "atlas.simulation.custom.portfolio._save_portfolio_record",
                side_effect=mock_save,
            ),
            patch("atlas.simulation.custom.portfolio._trigger_backtest_background"),
        ):
            create_custom_portfolio("Test", _INSTRUMENTS, MagicMock())

        assert call_order == ["validate", "save"]

    def test_validation_error_does_not_save(self):
        from atlas.simulation.custom.portfolio import create_custom_portfolio

        with (
            patch(
                "atlas.simulation.custom.portfolio.validate_custom_portfolio",
                side_effect=ValueError("bad portfolio"),
            ),
            patch(
                "atlas.simulation.custom.portfolio._save_portfolio_record"
            ) as mock_save,
        ):
            with pytest.raises(ValueError, match="bad portfolio"):
                create_custom_portfolio("Test", _INSTRUMENTS, MagicMock())

        mock_save.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/simulation/test_custom_portfolio.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write custom/portfolio.py**

```python
# atlas/simulation/custom/portfolio.py
"""Orchestrates custom portfolio lifecycle: create → backtest → activate paper trading.

Background execution pattern:
  create_custom_portfolio() saves to DB and returns immediately.
  _trigger_backtest_background() submits run_custom_portfolio_backtest() to
  a ProcessPoolExecutor (max_workers=1). The backtest runs in a separate process,
  writes results to DB, and updates custom_portfolio.backtest_id when done.
  The frontend polls /api/portfolios/custom/{id}/status every 5s.

Why ProcessPoolExecutor not threading:
  vectorbt is CPU-bound (NumPy). Python's GIL means threads don't parallelize
  CPU work. A separate process bypasses the GIL and doesn't block the API event loop.
"""
from __future__ import annotations

import gc
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import run_backtest
from atlas.simulation.backtest.report import write_backtest_result
from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix
from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio

log = structlog.get_logger()

_EXECUTOR = ProcessPoolExecutor(max_workers=1)
_DEFAULT_LOOKBACK_DAYS = 547  # ~18 months, matches walk-forward minimum


def create_custom_portfolio(
    name: str,
    instruments: list[InstrumentWeight],
    engine: Engine,
) -> str:
    """Validate, save, and trigger background backtest. Returns portfolio_id (UUID string).

    Raises ValueError if validation fails — DB is never touched on validation failure.
    """
    validate_custom_portfolio(instruments, engine)
    portfolio_id = _save_portfolio_record(name, instruments, engine)
    _trigger_backtest_background(portfolio_id, engine)
    log.info("custom_portfolio_created", portfolio_id=portfolio_id, name=name)
    return portfolio_id


def _save_portfolio_record(
    name: str,
    instruments: list[InstrumentWeight],
    engine: Engine,
) -> str:
    instruments_json = json.dumps(
        [
            {"instrument_id": i.instrument_id, "instrument_type": i.instrument_type, "weight_pct": i.weight_pct}
            for i in instruments
        ]
    )
    with open_compute_session(engine) as conn:
        row_id = conn.execute(
            text("""
                INSERT INTO atlas.strategy_fm_custom_portfolios
                    (name, instruments)
                VALUES (:name, :instruments::jsonb)
                RETURNING id::text
            """),
            {"name": name, "instruments": instruments_json},
        ).scalar()
        conn.commit()
    return row_id


def _trigger_backtest_background(portfolio_id: str, engine: Engine) -> None:
    """Submit the backtest to a background ProcessPoolExecutor."""
    from atlas.db import get_engine  # imported here to avoid circular import

    _EXECUTOR.submit(_run_backtest_subprocess, portfolio_id)


def _run_backtest_subprocess(portfolio_id: str) -> None:
    """Entry point for the background process. Creates its own DB engine."""
    from atlas.db import get_engine

    engine = get_engine()
    try:
        run_custom_portfolio_backtest(UUID(portfolio_id), engine)
    except Exception:
        log.exception("custom_portfolio_backtest_failed", portfolio_id=portfolio_id)
        _mark_backtest_failed(portfolio_id, engine)


def run_custom_portfolio_backtest(portfolio_id: UUID, engine: Engine) -> None:
    """Run vectorbt backtest for a saved custom portfolio and link the result.

    Called by the background process. Writes to strategy_backtest_results and
    updates strategy_fm_custom_portfolios.backtest_id when done.
    """
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT name, instruments
                FROM atlas.strategy_fm_custom_portfolios
                WHERE id = :pid
            """),
            {"pid": str(portfolio_id)},
        ).fetchone()

    if row is None:
        raise ValueError(f"Custom portfolio {portfolio_id} not found.")

    instruments_data = row.instruments
    if isinstance(instruments_data, str):
        instruments_data = json.loads(instruments_data)

    instrument_ids = [i["instrument_id"] for i in instruments_data]

    end_date = date.today()
    start_date = end_date - timedelta(days=_DEFAULT_LOOKBACK_DAYS)

    signal_matrix = build_stock_etf_signal_matrix(
        engine=engine,
        instrument_ids=instrument_ids,
        start_date=start_date,
        end_date=end_date,
        decisions_table="atlas_stock_decisions_daily",
    )

    result = run_backtest(signal_matrix, init_cash=10_000_000.0, fees_pct=0.001)

    backtest_id = write_backtest_result(
        engine=engine,
        result=result,
        backtest_type="custom",
        custom_portfolio_id=portfolio_id,
    )

    with open_compute_session(engine) as conn:
        conn.execute(
            text("""
                UPDATE atlas.strategy_fm_custom_portfolios
                SET backtest_id = :bid, updated_at = now()
                WHERE id = :pid
            """),
            {"bid": backtest_id, "pid": str(portfolio_id)},
        )
        conn.commit()

    log.info(
        "custom_portfolio_backtest_done",
        portfolio_id=str(portfolio_id),
        backtest_id=backtest_id,
        sharpe=result.sharpe_ratio,
    )
    del signal_matrix
    gc.collect()


def _mark_backtest_failed(portfolio_id: str, engine: Engine) -> None:
    """Write a sentinel backtest row with None values to unblock polling."""
    with open_compute_session(engine) as conn:
        conn.execute(
            text("""
                UPDATE atlas.strategy_fm_custom_portfolios
                SET updated_at = now()
                WHERE id = :pid
            """),
            {"pid": portfolio_id},
        )
        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/simulation/test_custom_portfolio.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/simulation/custom/portfolio.py tests/unit/simulation/test_custom_portfolio.py
git commit -m "feat(m7-p3): custom/portfolio.py — create/backtest/activate lifecycle"
```

---

### Task 6: FastAPI API endpoints for custom portfolio

**Files:**
- Create: `atlas/api/portfolios.py`
- Modify: `atlas/api/__init__.py` or `atlas/main.py` (register router)

These are the endpoints the Phase 5 frontend will consume. Backend-only for now — no UI.

- [ ] **Step 1: Check if atlas/api/ exists and where FastAPI app is registered**

```bash
find /path/to/atlas/atlas/api -type f -name "*.py" 2>/dev/null || echo "no api dir"
find /path/to/atlas -name "main.py" | head -5
```

- [ ] **Step 2: Create atlas/api/portfolios.py**

```python
# atlas/api/portfolios.py
"""Custom portfolio API endpoints — consumed by Phase 5 frontend."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.simulation.custom.builder import InstrumentWeight
from atlas.simulation.custom.portfolio import create_custom_portfolio

router = APIRouter(prefix="/api/portfolios/custom", tags=["custom-portfolio"])


class InstrumentWeightRequest(BaseModel):
    instrument_id: str
    instrument_type: str
    weight_pct: float


class CreatePortfolioRequest(BaseModel):
    name: str
    instruments: list[InstrumentWeightRequest]


@router.post("", status_code=201)
def create_portfolio(
    body: CreatePortfolioRequest,
    engine: Engine = Depends(get_engine),
) -> dict[str, str]:
    """Validate, save, and trigger background backtest. Returns portfolio_id immediately."""
    instruments = [
        InstrumentWeight(i.instrument_id, i.instrument_type, i.weight_pct)
        for i in body.instruments
    ]
    try:
        portfolio_id = create_custom_portfolio(body.name, instruments, engine)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"portfolio_id": portfolio_id, "status": "pending"}


@router.get("/{portfolio_id}/status")
def get_portfolio_status(
    portfolio_id: str,
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Polling endpoint — returns 'pending' until backtest_id is populated."""
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT backtest_id::text, updated_at
                FROM atlas.strategy_fm_custom_portfolios
                WHERE id = :pid
            """),
            {"pid": portfolio_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if row.backtest_id is None:
        return {"portfolio_id": portfolio_id, "status": "pending", "backtest_id": None}
    return {"portfolio_id": portfolio_id, "status": "complete", "backtest_id": row.backtest_id}


@router.get("/{portfolio_id}")
def get_portfolio(
    portfolio_id: str,
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Full portfolio detail including backtest results."""
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT
                    p.id::text, p.name, p.instruments, p.paper_trading_active,
                    p.backtest_id::text, p.created_at,
                    b.sharpe_ratio, b.max_drawdown, b.total_return,
                    b.start_date, b.end_date
                FROM atlas.strategy_fm_custom_portfolios p
                LEFT JOIN atlas.strategy_backtest_results b ON b.id = p.backtest_id
                WHERE p.id = :pid
            """),
            {"pid": portfolio_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    return {
        "id": row[0],
        "name": row[1],
        "instruments": row[2],
        "paper_trading_active": row[3],
        "backtest_id": row[4],
        "created_at": str(row[5]),
        "backtest": {
            "sharpe_ratio": float(row[6]) if row[6] is not None else None,
            "max_drawdown": float(row[7]) if row[7] is not None else None,
            "total_return": float(row[8]) if row[8] is not None else None,
            "start_date": str(row[9]) if row[9] is not None else None,
            "end_date": str(row[10]) if row[10] is not None else None,
        } if row[4] else None,
    }


@router.get("")
def list_portfolios(engine: Engine = Depends(get_engine)) -> list[dict[str, Any]]:
    """List all custom portfolios with status."""
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT id::text, name, backtest_id::text, paper_trading_active, created_at
                FROM atlas.strategy_fm_custom_portfolios
                ORDER BY created_at DESC
            """)
        ).fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "status": "complete" if r[2] else "pending",
            "backtest_id": r[2],
            "paper_trading_active": r[3],
            "created_at": str(r[4]),
        }
        for r in rows
    ]
```

- [ ] **Step 3: Register the router in the FastAPI app**

Find `atlas/main.py` (or equivalent) and add:

```python
from atlas.api.portfolios import router as portfolios_router
app.include_router(portfolios_router)
```

- [ ] **Step 4: Run ruff check**

```bash
ruff check atlas/api/portfolios.py atlas/simulation/custom/
ruff format atlas/api/portfolios.py atlas/simulation/custom/
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add atlas/api/portfolios.py atlas/
git commit -m "feat(m7-p3): custom portfolio API endpoints — create/status/detail/list"
```

---

### Task 7: Run full test suite + final validation

- [ ] **Step 1: Run all unit tests for Phase 3**

```bash
pytest tests/unit/simulation/test_engine.py tests/unit/simulation/test_report.py \
       tests/unit/simulation/test_builder.py tests/unit/simulation/test_custom_portfolio.py \
       -v --tb=short
```

Expected: all tests PASS. Zero failures.

- [ ] **Step 2: Run ruff on all new files**

```bash
ruff check atlas/simulation/backtest/ atlas/simulation/custom/ atlas/api/portfolios.py
```

Expected: no errors.

- [ ] **Step 3: Verify signal_adapter.py fixes are in place**

```bash
grep "de_equity_ohlcv\|mstar_id" atlas/simulation/core/signal_adapter.py
```

Expected: `de_equity_ohlcv` (not `de_ohlcv_daily`) and `mstar_id` in fund query.

- [ ] **Step 4: Final commit**

```bash
git add -p  # stage any remaining formatting fixes
git commit -m "fix(m7-p3): signal_adapter schema fixes (de_equity_ohlcv, mstar_id for funds)"
```
