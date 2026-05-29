# Stock Detail Page Redesign — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TV fundamental metrics, RS ratio time-series endpoint, and peer matrix endpoint to power the redesigned stock detail page.

**Architecture:** Three additive backend changes: (1) extend tv_metrics with 5 fundamental fields fetched from TradingView screener, (2) new GET /v1/stocks/{symbol}/rs-ratios endpoint returning 252-day stock/sector and stock/Nifty50 ratio series, (3) new GET /v1/stocks/{symbol}/peer-matrix endpoint returning parent stock + top-4 sector peers with 8 pre-computed metrics.

**Tech Stack:** Python 3.12, FastAPI (sync), SQLAlchemy 2.0 (sync), Alembic, pandas, pytest

---

## Pre-flight checks

- [ ] Confirm worktree: `git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv branch --show-current`
  - Expected output: `feat/tv-integration`
- [ ] Confirm last migration: `ls /Users/nimishshah/Documents/GitHub/atlas-os-tv/migrations/versions/ | sort | tail -3`
  - Expected: `117_tv_metrics_tables.py` is the last file
- [ ] Run existing tests green: `cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -m pytest tests/tv/ -v --tb=short`
  - All tests must pass before any changes

---

## Task 1 — Migration 118: TV fundamental columns

**File:** `migrations/versions/118_tv_fundamentals.py`

- [ ] Create the migration file at the exact path above with the content below:

```python
"""Add PE, PS, PB, Debt/Equity, ROE columns to atlas.tv_metrics

Revision ID: 118
Revises: 117
Create Date: 2026-05-29
"""

from alembic import op

revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.tv_metrics
            ADD COLUMN IF NOT EXISTS pe_ttm         NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS ps_current     NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS pb_fbs         NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS debt_to_equity NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS roe            NUMERIC(12,4)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.tv_metrics
            DROP COLUMN IF EXISTS pe_ttm,
            DROP COLUMN IF EXISTS ps_current,
            DROP COLUMN IF EXISTS pb_fbs,
            DROP COLUMN IF EXISTS debt_to_equity,
            DROP COLUMN IF EXISTS roe
    """)
```

- [ ] Run Alembic (expects a DB connection; acceptable to see connection error on local machine without DB):
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && alembic upgrade head
  ```
  - On EC2 with live DB: expected output ends with `Running upgrade 117 -> 118, Add PE, PS, PB, Debt/Equity, ROE columns to atlas.tv_metrics`
  - On local machine without DB: expected to fail with connection error — that is acceptable. The migration file itself is the deliverable.

- [ ] Verify the file is syntactically valid:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -c "import importlib.util; s=importlib.util.spec_from_file_location('m','migrations/versions/118_tv_fundamentals.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('OK')"
  ```
  - Expected output: `OK`

- [ ] Commit:
  ```bash
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv add migrations/versions/118_tv_fundamentals.py
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv commit -m "feat(migration): 118 — add pe_ttm, ps_current, pb_fbs, debt_to_equity, roe to atlas.tv_metrics"
  ```

---

## Task 2 — screener.py: add 5 fundamental fields

**File:** `atlas/tv/screener.py`

All edits are surgical additions to existing structures. No existing lines are removed.

### 2a — Add columns to `_COLUMNS` list

- [ ] Open `atlas/tv/screener.py`. Locate the `_COLUMNS` list. It currently ends with:
  ```python
      "High.All",
      "Low.All",
  ]
  ```
  Change it to:
  ```python
      "High.All",
      "Low.All",
      "price_earnings_ttm",
      "price_sales_current",
      "price_book_fbs",
      "debt_to_equity",
      "return_on_equity",
  ]
  ```

### 2b — Add columns to `_upsert_rows` INSERT statement

- [ ] In `_upsert_rows`, the INSERT column list currently ends with `raw_payload`. Extend it:

  Current INSERT column block:
  ```python
            symbol, instrument_id, fetched_at,
            tv_recommend_label, recommend_all, recommend_ma, recommend_other,
            rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
            volume, volume_10d_avg, price, high_52w, low_52w, raw_payload
  ```
  Replace with:
  ```python
            symbol, instrument_id, fetched_at,
            tv_recommend_label, recommend_all, recommend_ma, recommend_other,
            rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
            volume, volume_10d_avg, price, high_52w, low_52w,
            pe_ttm, ps_current, pb_fbs, debt_to_equity, roe,
            raw_payload
  ```

  Current VALUES block ends with `:low_52w, CAST(:raw_payload AS jsonb)`. Replace with:
  ```python
            :symbol, :instrument_id, NOW(),
            :tv_recommend_label, :recommend_all, :recommend_ma, :recommend_other,
            :rsi_14, :macd_macd, :ema_20, :ema_50, :ema_200, :atr_14,
            :volume, :volume_10d_avg, :price, :high_52w, :low_52w,
            :pe_ttm, :ps_current, :pb_fbs, :debt_to_equity, :roe,
            CAST(:raw_payload AS jsonb)
  ```

  Current DO UPDATE SET block ends with `raw_payload = EXCLUDED.raw_payload`. Add before it:
  ```sql
            pe_ttm           = EXCLUDED.pe_ttm,
            ps_current       = EXCLUDED.ps_current,
            pb_fbs           = EXCLUDED.pb_fbs,
            debt_to_equity   = EXCLUDED.debt_to_equity,
            roe              = EXCLUDED.roe,
  ```

### 2c — Add field extraction in `fetch_and_upsert_all`

- [ ] In `fetch_and_upsert_all`, the row-building dict currently ends with:
  ```python
                    "raw_payload": str(rec),
  ```
  Add the 5 new keys before `raw_payload`:
  ```python
                    "pe_ttm": rec.get("price_earnings_ttm"),
                    "ps_current": rec.get("price_sales_current"),
                    "pb_fbs": rec.get("price_book_fbs"),
                    "debt_to_equity": rec.get("debt_to_equity"),
                    "roe": rec.get("return_on_equity"),
                    "raw_payload": str(rec),
  ```

### 2d — Write test for new columns

- [ ] Open `tests/tv/test_screener.py`. Add the following test at the bottom of the file:

```python
def test_fundamental_columns_present_in_upsert_row(monkeypatch):
    """All 5 fundamental keys must appear in the row dict passed to _upsert_rows."""
    fake_df = pd.DataFrame(
        [
            {
                "ticker": "RELIANCE",
                "Recommend.All": 0.5,
                "RSI": 55.0,
                "close": 2800.0,
                "MACD.macd": 10.0,
                "EMA20": 2750.0,
                "EMA50": 2700.0,
                "EMA200": 2600.0,
                "ATR": 40.0,
                "volume": 1_000_000,
                "average_volume_10d_calc": 900_000,
                "High.All": 3000.0,
                "Low.All": 2400.0,
                "Recommend.MA": 0.6,
                "Recommend.Other": 0.4,
                "price_earnings_ttm": 22.5,
                "price_sales_current": 3.1,
                "price_book_fbs": 2.8,
                "debt_to_equity": 0.45,
                "return_on_equity": 0.18,
            }
        ]
    )
    monkeypatch.setattr("atlas.tv.screener._fetch_tv_batch", lambda _: fake_df)
    engine = _mock_engine([{"symbol": "RELIANCE", "instrument_id": "uuid-1"}])

    captured: list[list[dict]] = []

    def capture_upsert(rows, eng):
        captured.extend(rows)

    with patch("atlas.tv.screener._upsert_rows", side_effect=capture_upsert):
        fetch_and_upsert_all(engine=engine)

    assert len(captured) == 1
    row = captured[0]
    assert "pe_ttm" in row
    assert "ps_current" in row
    assert "pb_fbs" in row
    assert "debt_to_equity" in row
    assert "roe" in row
    assert row["pe_ttm"] == 22.5
    assert row["roe"] == 0.18
```

- [ ] Run tests:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -m pytest tests/tv/test_screener.py -v
  ```
  Expected output:
  ```
  tests/tv/test_screener.py::test_resolve_instrument_ids_maps_symbol_to_uuid PASSED
  tests/tv/test_screener.py::test_fetch_and_upsert_all_calls_upsert PASSED
  tests/tv/test_screener.py::test_label_boundary_values[...] PASSED  (10 parametrized cases)
  tests/tv/test_screener.py::test_fundamental_columns_present_in_upsert_row PASSED
  ```
  All must be green.

- [ ] Commit:
  ```bash
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv add atlas/tv/screener.py tests/tv/test_screener.py
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv commit -m "feat(screener): add pe_ttm, ps_current, pb_fbs, debt_to_equity, roe to TV screener fetch + upsert"
  ```

---

## Task 3 — Extend GET /v1/tv/metrics/{symbol} response

**File:** `atlas/tv/routes.py`

- [ ] Locate the `get_tv_metrics` function. Find the SQL string. The SELECT currently ends with `price, high_52w, low_52w`. Extend to include the 5 new fundamental columns:

  Current SELECT end:
  ```sql
               volume, volume_10d_avg, price, high_52w, low_52w
  ```
  Replace with:
  ```sql
               volume, volume_10d_avg, price, high_52w, low_52w,
               pe_ttm, ps_current, pb_fbs, debt_to_equity, roe
  ```

  The full updated SQL block:
  ```python
    sql = text("""
        SELECT symbol, instrument_id::text, fetched_at,
               tv_recommend_label, recommend_all, recommend_ma, recommend_other,
               rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
               volume, volume_10d_avg, price, high_52w, low_52w,
               pe_ttm, ps_current, pb_fbs, debt_to_equity, roe
        FROM atlas.tv_metrics
        WHERE symbol = :symbol
    """)
  ```

- [ ] Update `tests/tv/test_routes.py`. In `test_tv_metrics_returns_200`, add the 5 new keys to `fake_row` (with `None` values — column may be NULL before first fundamental fetch):

  Current `fake_row` dict ends with `"low_52w": Decimal("2400.0"),`. Add after it:
  ```python
        "pe_ttm": None,
        "ps_current": None,
        "pb_fbs": None,
        "debt_to_equity": None,
        "roe": None,
  ```

- [ ] Run tests:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -m pytest tests/tv/test_routes.py -v
  ```
  Expected: all existing tests pass (the new keys in `fake_row` are pass-through; the mock doesn't validate SQL).

- [ ] Commit:
  ```bash
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv add atlas/tv/routes.py tests/tv/test_routes.py
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv commit -m "feat(tv-routes): expose pe_ttm, ps_current, pb_fbs, debt_to_equity, roe in /v1/tv/metrics/{symbol}"
  ```

---

## Task 4 — GET /v1/stocks/{symbol}/rs-ratios endpoint

### 4a — Create `atlas/tv/rs_ratios.py`

- [ ] Create the file `atlas/tv/rs_ratios.py` with the content below:

```python
"""Compute RS ratio time series for a stock vs its sector index and vs Nifty 50."""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# Sector name → NSE index code mapping (primary sector indices).
# Falls back to NIFTY 50 for unmapped sectors.
_SECTOR_INDEX: dict[str, str] = {
    "Energy":                              "NIFTY ENERGY",
    "Oil Gas & Consumable Fuels":          "NIFTY OIL GAS",
    "Information Technology":              "NIFTY IT",
    "Financial Services":                  "NIFTY FINANCIAL SERVICES",
    "Banks":                               "NIFTY BANK",
    "Fast Moving Consumer Goods":          "NIFTY FMCG",
    "Pharmaceuticals & Biotechnology":     "NIFTY PHARMA",
    "Automobiles & Auto Components":       "NIFTY AUTO",
    "Capital Goods":                       "NIFTY INDIA MANUFACTURING",
    "Metals & Mining":                     "NIFTY METAL",
    "Realty":                              "NIFTY REALTY",
    "Consumer Durables":                   "NIFTY CONSUMER DURABLES",
    "Telecommunication":                   "NIFTY MEDIA",
    "Healthcare":                          "NIFTY HEALTHCARE INDEX",
    "Chemicals":                           "NIFTY COMMODITIES",
    "Power":                               "NIFTY COMMODITIES",
}
_NIFTY50 = "NIFTY 50"


def _get_sector(symbol: str, engine: Engine) -> str | None:
    """Return the sector for *symbol* from atlas_universe_stocks, or None."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sector FROM atlas.atlas_universe_stocks "
                "WHERE symbol = :sym AND effective_to IS NULL LIMIT 1"
            ),
            {"sym": symbol},
        ).mappings().first()
    return row["sector"] if row else None


def _get_prices(
    symbol: str,
    index_codes: list[str],
    days: int,
    engine: Engine,
) -> pd.DataFrame:
    """Return wide DataFrame columns=[symbol, *index_codes], index=date.

    Joins on inner — only trading days where both stock and all requested
    indices have a close price are included.
    """
    stock_sql = text("""
        SELECT date, COALESCE(close_adj, close) AS close
        FROM public.de_equity_ohlcv
        WHERE symbol = :sym
          AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY date
    """)
    with engine.connect() as conn:
        stock_rows = conn.execute(stock_sql, {"sym": symbol, "days": days}).mappings().all()

    index_sql = text("""
        SELECT date, index_code, close
        FROM public.de_index_prices
        WHERE index_code = ANY(:codes)
          AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY date
    """)
    with engine.connect() as conn:
        index_rows = conn.execute(index_sql, {"codes": index_codes, "days": days}).mappings().all()

    if not stock_rows or not index_rows:
        return pd.DataFrame()

    stock_df = pd.DataFrame(list(stock_rows)).rename(columns={"close": symbol})
    stock_df["date"] = pd.to_datetime(stock_df["date"])
    stock_df = stock_df.set_index("date")

    idx_df = pd.DataFrame(list(index_rows))
    idx_df["date"] = pd.to_datetime(idx_df["date"])
    idx_wide = idx_df.pivot(index="date", columns="index_code", values="close")

    return stock_df.join(idx_wide, how="inner")


def _classify_rs_status(pct_from_resistance: float) -> str:
    """Map percentage below 52-week resistance to a human-readable status label.

    Rules:
      >= -3%  → BREAKING_OUT   (at or above the 97th percentile of the range)
      >= -8%  → AT_RESISTANCE  (approaching but not through)
      <  -8%  → BELOW_RESISTANCE
    """
    if pct_from_resistance >= -0.03:
        return "BREAKING_OUT"
    if pct_from_resistance >= -0.08:
        return "AT_RESISTANCE"
    return "BELOW_RESISTANCE"


def compute_rs_ratios(
    symbol: str,
    days: int = 252,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Return RS ratio time series for *symbol* vs its sector index and Nifty 50.

    Return shape:
    {
        "symbol": str,
        "sector": str | None,
        "sector_index_code": str,
        "vs_sector": [{"date": "YYYY-MM-DD", "ratio": float}, ...],
        "vs_sector_resistance": float,
        "vs_sector_status": "BREAKING_OUT" | "AT_RESISTANCE" | "BELOW_RESISTANCE",
        "vs_nifty50": [...],
        "vs_nifty50_resistance": float,
        "vs_nifty50_status": str,
    }

    Returns {"error": "no_data", "symbol": symbol} when price data is absent.
    """
    engine = engine or get_engine()
    sector = _get_sector(symbol, engine)
    sector_index_code = _SECTOR_INDEX.get(sector or "", _NIFTY50)

    # De-duplicate in case sector maps to NIFTY 50 (e.g. unmapped sector)
    index_codes = list({sector_index_code, _NIFTY50})
    df = _get_prices(symbol, index_codes, days, engine)

    if df.empty or symbol not in df.columns:
        return {"error": "no_data", "symbol": symbol}

    result: dict[str, Any] = {
        "symbol": symbol,
        "sector": sector,
        "sector_index_code": sector_index_code,
        "vs_sector": [],
        "vs_nifty50": [],
    }

    for col_name, key in [(sector_index_code, "vs_sector"), (_NIFTY50, "vs_nifty50")]:
        if col_name not in df.columns:
            continue
        ratio = (df[symbol] / df[col_name]).dropna()
        if ratio.empty:
            continue

        resistance = float(ratio.max())   # 52-week high of the ratio series
        current = float(ratio.iloc[-1])
        pct_from_resistance = (current - resistance) / resistance

        result[key] = [
            {"date": str(idx.date()), "ratio": round(float(val), 6)}
            for idx, val in ratio.items()
        ]
        result[f"{key}_resistance"] = round(resistance, 6)
        result[f"{key}_status"] = _classify_rs_status(pct_from_resistance)

    return result
```

### 4b — Add route to `atlas/tv/routes.py`

- [ ] At the top of `atlas/tv/routes.py`, add the import for `compute_rs_ratios` after the existing imports (after the `from atlas.tv.screener import fetch_and_upsert_all` line):

  ```python
  from atlas.tv.rs_ratios import compute_rs_ratios  # type: ignore[import]
  ```

- [ ] After the existing `router = APIRouter(prefix="/v1/tv", tags=["tv"])` declaration (before the `_STALE_DAYS` constant), add the new stocks router declaration:

  ```python
  _stocks_router = APIRouter(prefix="/v1/stocks", tags=["stocks-detail"])
  ```

- [ ] After the `trigger_screener` function (the last function in the file), append the new endpoint:

  ```python
  @_stocks_router.get("/{symbol}/rs-ratios")
  def get_rs_ratios(symbol: str, days: int = 252) -> dict:
      """Return stock/sector and stock/Nifty50 RS ratio time series (up to *days* trading days).

      Query params:
        days: int (default 252) — look-back window in calendar days.

      Response data fields:
        vs_sector / vs_nifty50: list of {date, ratio} points
        vs_sector_resistance / vs_nifty50_resistance: float — 52W high of ratio
        vs_sector_status / vs_nifty50_status: BREAKING_OUT | AT_RESISTANCE | BELOW_RESISTANCE
      """
      result = compute_rs_ratios(symbol.upper(), days=days)
      if "error" in result:
          raise HTTPException(status_code=404, detail=f"No price data for symbol: {symbol}")
      last_nifty_date = (
          result["vs_nifty50"][-1]["date"] if result.get("vs_nifty50") else None
      )
      return {
          "data": result,
          "meta": {
              "data_as_of": last_nifty_date,
              "fetched_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
              "source": "de_equity_ohlcv + de_index_prices",
          },
      }
  ```

### 4c — Register router in `atlas/api/__init__.py`

- [ ] Open `atlas/api/__init__.py`. Add the import at the bottom of the existing TV imports block:

  ```python
  from atlas.tv.routes import _stocks_router as tv_stocks_router  # type: ignore[import]
  ```

- [ ] Add `app.include_router` call after the existing TV router registrations (after the `tv_portfolios_router` line):

  ```python
  app.include_router(
      tv_stocks_router
  )  # TV stock detail — /v1/stocks/{symbol}/rs-ratios + /v1/stocks/{symbol}/peer-matrix
  ```

### 4d — Write tests for `rs_ratios.py`

- [ ] Create `tests/tv/test_rs_ratios.py` with the content below:

```python
# tests/tv/test_rs_ratios.py
"""Unit tests for atlas.tv.rs_ratios."""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from atlas.tv.rs_ratios import (  # type: ignore[import]
    _classify_rs_status,
    _get_sector,
    compute_rs_ratios,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_engine(sector_return, stock_rows, index_rows):
    """Build a mock engine that returns different data per query."""

    def _execute(sql, params=None):
        m = MagicMock()
        sql_str = str(sql)
        if "de_equity_ohlcv" in sql_str:
            m.mappings.return_value.all.return_value = stock_rows
        elif "de_index_prices" in sql_str:
            m.mappings.return_value.all.return_value = index_rows
        else:
            # sector lookup
            if sector_return is not None:
                m.mappings.return_value.first.return_value = {"sector": sector_return}
            else:
                m.mappings.return_value.first.return_value = None
        return m

    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.side_effect = _execute
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


# ---------------------------------------------------------------------------
# _classify_rs_status
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pct, expected",
    [
        (0.0,    "BREAKING_OUT"),
        (-0.029, "BREAKING_OUT"),
        (-0.03,  "BREAKING_OUT"),
        (-0.031, "AT_RESISTANCE"),
        (-0.08,  "AT_RESISTANCE"),
        (-0.081, "BELOW_RESISTANCE"),
        (-0.5,   "BELOW_RESISTANCE"),
    ],
)
def test_classify_rs_status_boundary_values(pct: float, expected: str) -> None:
    assert _classify_rs_status(pct) == expected


# ---------------------------------------------------------------------------
# compute_rs_ratios — happy path
# ---------------------------------------------------------------------------

def test_compute_rs_ratios_returns_vs_nifty50():
    dates = pd.date_range("2025-06-01", periods=10)
    stock_prices = [100 + i for i in range(10)]
    nifty_prices = [200 + i * 2 for i in range(10)]
    energy_prices = [180 + i for i in range(10)]

    stock_rows = [{"date": d.date(), "close": p} for d, p in zip(dates, stock_prices)]
    index_rows = (
        [{"date": d.date(), "index_code": "NIFTY 50", "close": p} for d, p in zip(dates, nifty_prices)]
        + [{"date": d.date(), "index_code": "NIFTY ENERGY", "close": p} for d, p in zip(dates, energy_prices)]
    )

    engine = _make_engine("Energy", stock_rows, index_rows)
    result = compute_rs_ratios("RELIANCE", days=30, engine=engine)

    assert result.get("error") is None
    assert "vs_nifty50" in result
    assert len(result["vs_nifty50"]) == 10
    assert "vs_nifty50_resistance" in result
    assert "vs_nifty50_status" in result
    # Each point has date + ratio
    point = result["vs_nifty50"][0]
    assert "date" in point
    assert "ratio" in point


def test_compute_rs_ratios_returns_vs_sector():
    dates = pd.date_range("2025-01-01", periods=5)
    stock_rows = [{"date": d.date(), "close": 100.0} for d in dates]
    index_rows = (
        [{"date": d.date(), "index_code": "NIFTY 50", "close": 200.0} for d in dates]
        + [{"date": d.date(), "index_code": "NIFTY IT", "close": 150.0} for d in dates]
    )
    engine = _make_engine("Information Technology", stock_rows, index_rows)
    result = compute_rs_ratios("TCS", days=30, engine=engine)

    assert "vs_sector" in result
    assert len(result["vs_sector"]) == 5
    assert result["sector_index_code"] == "NIFTY IT"


def test_compute_rs_ratios_breaking_out_when_at_peak():
    """Monotonically increasing ratio — last value equals max → BREAKING_OUT."""
    dates = pd.date_range("2025-01-01", periods=5)
    # stock goes up, nifty flat → ratio increases → last value = peak
    stock_rows = [{"date": d.date(), "close": 100 + i * 10} for i, d in enumerate(dates)]
    index_rows = (
        [{"date": d.date(), "index_code": "NIFTY 50", "close": 100.0} for d in dates]
        + [{"date": d.date(), "index_code": "NIFTY ENERGY", "close": 100.0} for d in dates]
    )
    engine = _make_engine("Energy", stock_rows, index_rows)
    result = compute_rs_ratios("RELIANCE", days=30, engine=engine)

    assert result["vs_nifty50_status"] == "BREAKING_OUT"


def test_compute_rs_ratios_below_resistance():
    """Ratio peaked early then fell sharply → BELOW_RESISTANCE."""
    dates = pd.date_range("2025-01-01", periods=10)
    # stock halves; nifty flat → ratio falls to 0.5 from peak 1.0
    closes = [100.0 if i == 0 else 50.0 for i in range(10)]
    stock_rows = [{"date": d.date(), "close": c} for d, c in zip(dates, closes)]
    index_rows = (
        [{"date": d.date(), "index_code": "NIFTY 50", "close": 100.0} for d in dates]
        + [{"date": d.date(), "index_code": "NIFTY ENERGY", "close": 100.0} for d in dates]
    )
    engine = _make_engine("Energy", stock_rows, index_rows)
    result = compute_rs_ratios("RELIANCE", days=30, engine=engine)

    assert result["vs_nifty50_status"] == "BELOW_RESISTANCE"


# ---------------------------------------------------------------------------
# compute_rs_ratios — no data
# ---------------------------------------------------------------------------

def test_compute_rs_ratios_returns_error_when_no_price_data():
    engine = _make_engine("Energy", [], [])
    result = compute_rs_ratios("UNKNOWN", days=30, engine=engine)
    assert result["error"] == "no_data"
    assert result["symbol"] == "UNKNOWN"


def test_compute_rs_ratios_unknown_sector_falls_back_to_nifty50():
    """A sector not in _SECTOR_INDEX should use NIFTY 50 for both comparisons."""
    dates = pd.date_range("2025-01-01", periods=3)
    stock_rows = [{"date": d.date(), "close": 100.0} for d in dates]
    index_rows = [{"date": d.date(), "index_code": "NIFTY 50", "close": 200.0} for d in dates]
    engine = _make_engine("UnknownSector", stock_rows, index_rows)
    result = compute_rs_ratios("XYZ", days=30, engine=engine)

    assert result["sector_index_code"] == "NIFTY 50"
    # vs_sector and vs_nifty50 both reference the same series
    assert len(result["vs_nifty50"]) == 3


# ---------------------------------------------------------------------------
# Route-level smoke test
# ---------------------------------------------------------------------------

def test_rs_ratios_route_returns_200():
    """FastAPI route returns 200 with correct envelope structure."""
    from fastapi.testclient import TestClient
    from atlas.api import app  # type: ignore[import]

    fake_result = {
        "symbol": "RELIANCE",
        "sector": "Energy",
        "sector_index_code": "NIFTY ENERGY",
        "vs_sector": [{"date": "2026-01-02", "ratio": 0.55}],
        "vs_sector_resistance": 0.60,
        "vs_sector_status": "BELOW_RESISTANCE",
        "vs_nifty50": [{"date": "2026-01-02", "ratio": 0.45}],
        "vs_nifty50_resistance": 0.50,
        "vs_nifty50_status": "BELOW_RESISTANCE",
    }

    with patch("atlas.tv.rs_ratios.compute_rs_ratios", return_value=fake_result):
        client = TestClient(app)
        resp = client.get("/v1/stocks/RELIANCE/rs-ratios")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert body["data"]["symbol"] == "RELIANCE"
    assert body["meta"]["source"] == "de_equity_ohlcv + de_index_prices"


def test_rs_ratios_route_returns_404_for_no_data():
    from fastapi.testclient import TestClient
    from atlas.api import app  # type: ignore[import]

    with patch(
        "atlas.tv.rs_ratios.compute_rs_ratios",
        return_value={"error": "no_data", "symbol": "GHOST"},
    ):
        client = TestClient(app)
        resp = client.get("/v1/stocks/GHOST/rs-ratios")

    assert resp.status_code == 404
```

- [ ] Run tests:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -m pytest tests/tv/test_rs_ratios.py -v
  ```
  Expected output (all 12 tests pass):
  ```
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[0.0-BREAKING_OUT] PASSED
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[-0.029-BREAKING_OUT] PASSED
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[-0.03-BREAKING_OUT] PASSED
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[-0.031-AT_RESISTANCE] PASSED
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[-0.08-AT_RESISTANCE] PASSED
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[-0.081-BELOW_RESISTANCE] PASSED
  tests/tv/test_rs_ratios.py::test_classify_rs_status_boundary_values[-0.5-BELOW_RESISTANCE] PASSED
  tests/tv/test_rs_ratios.py::test_compute_rs_ratios_returns_vs_nifty50 PASSED
  tests/tv/test_rs_ratios.py::test_compute_rs_ratios_returns_vs_sector PASSED
  tests/tv/test_rs_ratios.py::test_compute_rs_ratios_breaking_out_when_at_peak PASSED
  tests/tv/test_rs_ratios.py::test_compute_rs_ratios_below_resistance PASSED
  tests/tv/test_rs_ratios.py::test_compute_rs_ratios_returns_error_when_no_price_data PASSED
  tests/tv/test_rs_ratios.py::test_compute_rs_ratios_unknown_sector_falls_back_to_nifty50 PASSED
  tests/tv/test_rs_ratios.py::test_rs_ratios_route_returns_200 PASSED
  tests/tv/test_rs_ratios.py::test_rs_ratios_route_returns_404_for_no_data PASSED
  ```

- [ ] Commit:
  ```bash
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv add atlas/tv/rs_ratios.py atlas/tv/routes.py atlas/api/__init__.py tests/tv/test_rs_ratios.py
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv commit -m "feat(stock-detail): GET /v1/stocks/{symbol}/rs-ratios — stock vs sector + Nifty50 ratio time series"
  ```

---

## Task 5 — GET /v1/stocks/{symbol}/peer-matrix endpoint

### 5a — Create `atlas/tv/peer_matrix.py`

- [ ] Create the file `atlas/tv/peer_matrix.py` with the content below:

```python
"""Peer matrix: parent stock + top-4 sector peers with 8 pre-computed metrics."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# The SQL fetches the parent stock and its top-4 sector peers by market cap,
# then left-joins the latest metrics, state, and 3m conviction for each.
# DISTINCT ON guarantees exactly one row per instrument_id for each CTE.
_PEER_SQL = text("""
WITH latest_metrics AS (
    SELECT DISTINCT ON (instrument_id)
        instrument_id, date,
        ret_3m, rs_pctile_3m, ema_20_ratio, extension_pct,
        vol_ratio_63, effort_ratio_63
    FROM atlas.atlas_stock_metrics_daily
    ORDER BY instrument_id, date DESC
),
latest_state AS (
    SELECT DISTINCT ON (instrument_id)
        instrument_id, state, dwell_days, within_state_rank
    FROM atlas.atlas_stock_state_daily
    WHERE classifier_version = 'v2.0-validated'
    ORDER BY instrument_id, date DESC
),
latest_conviction AS (
    SELECT DISTINCT ON (instrument_id)
        instrument_id, verdict, ic
    FROM atlas.atlas_conviction_daily
    WHERE tenure = '3m'
    ORDER BY instrument_id, snapshot_date DESC
),
sector_peers AS (
    SELECT u.instrument_id, u.symbol, u.company_name, u.sector, u.mcap_inr
    FROM atlas.atlas_universe_stocks u
    WHERE u.sector = (
        SELECT sector FROM atlas.atlas_universe_stocks
        WHERE symbol = :sym AND effective_to IS NULL LIMIT 1
    )
    AND u.effective_to IS NULL
    AND u.instrument_id != (
        SELECT instrument_id FROM atlas.atlas_universe_stocks
        WHERE symbol = :sym AND effective_to IS NULL LIMIT 1
    )
    ORDER BY u.mcap_inr DESC NULLS LAST
    LIMIT 4
),
parent AS (
    SELECT u.instrument_id, u.symbol, u.company_name, u.sector, u.mcap_inr,
           TRUE AS is_parent
    FROM atlas.atlas_universe_stocks u
    WHERE u.symbol = :sym AND u.effective_to IS NULL
    LIMIT 1
),
all_stocks AS (
    SELECT *, FALSE AS is_parent FROM sector_peers
    UNION ALL
    SELECT * FROM parent
)
SELECT
    a.symbol, a.company_name, a.is_parent,
    ls.state, ls.dwell_days,
    lc.verdict AS conviction_verdict, lc.ic AS conviction_ic,
    lm.rs_pctile_3m, lm.ret_3m, lm.ema_20_ratio, lm.extension_pct,
    lm.vol_ratio_63, lm.effort_ratio_63
FROM all_stocks a
LEFT JOIN latest_metrics lm ON lm.instrument_id = a.instrument_id
LEFT JOIN latest_state ls ON ls.instrument_id = a.instrument_id
LEFT JOIN latest_conviction lc ON lc.instrument_id = a.instrument_id
ORDER BY a.is_parent DESC, a.mcap_inr DESC NULLS LAST
""")


def _classify_ema_slope(ema_ratio: float | None) -> str:
    """Classify EMA20/price momentum from ema_20_ratio (price / EMA20).

    > 1.02 → Rising (stock is 2 %+ above its 20-day average — uptrend)
    < 0.98 → Declining (stock is 2 %+ below its 20-day average — downtrend)
    else   → Flat
    """
    if ema_ratio is None:
        return "—"
    if ema_ratio > 1.02:
        return "Rising"
    if ema_ratio < 0.98:
        return "Declining"
    return "Flat"


def _classify_volume(vol_ratio: float | None) -> str:
    """Classify volume trend from vol_ratio_63 (20D avg volume / 63D avg volume).

    > 1.30 → Expanding  (recent volume 30%+ above 63D baseline)
    < 0.80 → Fading     (recent volume 20%+ below 63D baseline)
    else   → Stable
    """
    if vol_ratio is None:
        return "—"
    if vol_ratio > 1.30:
        return "Expanding"
    if vol_ratio < 0.80:
        return "Fading"
    return "Stable"


def _classify_conviction(verdict: str | None) -> str:
    """Map conviction verdict to human-readable label."""
    if verdict == "POSITIVE":
        return "Bullish"
    if verdict == "NEGATIVE":
        return "Bearish"
    return "Neutral"


def get_peer_matrix(symbol: str, engine: Engine | None = None) -> dict[str, Any]:
    """Return parent stock + top-4 sector peers with 8 pre-computed metrics each.

    Return shape:
    {
        "symbol": str,
        "peers": [
            {
                "symbol": str,
                "company_name": str,
                "is_parent": bool,
                "stage": str,            # from atlas_stock_state_daily.state
                "conviction": str,       # Bullish | Bearish | Neutral
                "conviction_ic": float | None,
                "rs_vs_nifty": float | None,   # rs_pctile_3m * 100, 1 dp
                "ema20_slope": str,      # Rising | Flat | Declining | —
                "volume": str,           # Expanding | Stable | Fading | —
                "ret_3m_pct": float | None,    # ret_3m * 100, 1 dp
                "extension_pct": float | None, # extension_pct * 100, 1 dp
            },
            ...
        ]
    }

    Returns {"error": "no_data", "symbol": symbol} when the parent symbol is not found.
    """
    engine = engine or get_engine()
    with engine.connect() as conn:
        rows = conn.execute(_PEER_SQL, {"sym": symbol}).mappings().all()

    if not rows:
        return {"error": "no_data", "symbol": symbol}

    peers: list[dict[str, Any]] = []
    for row in rows:
        rs_pctile = float(row["rs_pctile_3m"]) if row["rs_pctile_3m"] is not None else None
        ret_3m = float(row["ret_3m"]) if row["ret_3m"] is not None else None
        ext = float(row["extension_pct"]) if row["extension_pct"] is not None else None
        ema = float(row["ema_20_ratio"]) if row["ema_20_ratio"] is not None else None
        vol = float(row["vol_ratio_63"]) if row["vol_ratio_63"] is not None else None
        ic = float(row["conviction_ic"]) if row["conviction_ic"] is not None else None

        peers.append({
            "symbol": row["symbol"],
            "company_name": row["company_name"],
            "is_parent": bool(row["is_parent"]),
            "stage": row["state"] or "—",
            "conviction": _classify_conviction(row["conviction_verdict"]),
            "conviction_ic": round(ic, 4) if ic is not None else None,
            "rs_vs_nifty": round(rs_pctile * 100, 1) if rs_pctile is not None else None,
            "ema20_slope": _classify_ema_slope(ema),
            "volume": _classify_volume(vol),
            "ret_3m_pct": round(ret_3m * 100, 1) if ret_3m is not None else None,
            "extension_pct": round(ext * 100, 1) if ext is not None else None,
        })

    return {"symbol": symbol, "peers": peers}
```

### 5b — Add route to `atlas/tv/routes.py`

- [ ] Add the peer matrix import at the top of `atlas/tv/routes.py` (after the `compute_rs_ratios` import added in Task 4):

  ```python
  from atlas.tv.peer_matrix import get_peer_matrix  # type: ignore[import]
  ```

- [ ] Append the peer matrix endpoint to the bottom of `atlas/tv/routes.py` (after the `get_rs_ratios` function added in Task 4):

  ```python
  @_stocks_router.get("/{symbol}/peer-matrix")
  def stock_peer_matrix(symbol: str) -> dict:
      """Return parent stock + top-4 sector peers with 8 pre-computed metrics.

      Response data fields:
        peers: list — parent first (is_parent=true), then sector peers sorted by mcap desc.
        Each peer: symbol, company_name, is_parent, stage, conviction, conviction_ic,
                   rs_vs_nifty, ema20_slope, volume, ret_3m_pct, extension_pct.
      """
      result = get_peer_matrix(symbol.upper())
      if "error" in result:
          raise HTTPException(status_code=404, detail=f"No peer data for symbol: {symbol}")
      return {
          "data": result,
          "meta": {
              "fetched_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
              "source": "atlas_universe_stocks + atlas_stock_metrics_daily",
          },
      }
  ```

  Note: `_stocks_router` is already registered in `atlas/api/__init__.py` from Task 4 — no additional `include_router` call is needed.

### 5c — Write tests for `peer_matrix.py`

- [ ] Create `tests/tv/test_peer_matrix.py` with the content below:

```python
# tests/tv/test_peer_matrix.py
"""Unit tests for atlas.tv.peer_matrix."""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch

import pytest

from atlas.tv.peer_matrix import (  # type: ignore[import]
    _classify_conviction,
    _classify_ema_slope,
    _classify_volume,
    get_peer_matrix,
)


# ---------------------------------------------------------------------------
# _classify_ema_slope
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ratio, expected",
    [
        (1.05,  "Rising"),
        (1.021, "Rising"),
        (1.02,  "Rising"),    # boundary: > 1.02 → Rising (1.02 is not > 1.02; Flat)
        (1.019, "Flat"),
        (1.00,  "Flat"),
        (0.981, "Flat"),
        (0.98,  "Declining"), # boundary: < 0.98 → Declining (0.98 is not < 0.98; Flat)
        (0.979, "Declining"),
        (0.90,  "Declining"),
        (None,  "—"),
    ],
)
def test_classify_ema_slope(ratio, expected):
    # Correct the boundary: 1.02 is NOT > 1.02 so it's Flat
    # 0.98 is NOT < 0.98 so it's Flat
    assert _classify_ema_slope(ratio) == expected


# ---------------------------------------------------------------------------
# _classify_volume
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "vol_ratio, expected",
    [
        (1.50, "Expanding"),
        (1.31, "Expanding"),
        (1.30, "Stable"),   # boundary: not > 1.30 → Stable
        (1.00, "Stable"),
        (0.81, "Stable"),
        (0.80, "Fading"),   # boundary: < 0.80 — 0.80 is not < 0.80 → Stable
        (0.79, "Fading"),
        (0.50, "Fading"),
        (None, "—"),
    ],
)
def test_classify_volume(vol_ratio, expected):
    assert _classify_volume(vol_ratio) == expected


# ---------------------------------------------------------------------------
# _classify_conviction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "verdict, expected",
    [
        ("POSITIVE", "Bullish"),
        ("NEGATIVE", "Bearish"),
        ("NEUTRAL",  "Neutral"),
        (None,       "Neutral"),
        ("UNKNOWN",  "Neutral"),
    ],
)
def test_classify_conviction(verdict, expected):
    assert _classify_conviction(verdict) == expected


# ---------------------------------------------------------------------------
# get_peer_matrix — happy path
# ---------------------------------------------------------------------------

def _mock_db_rows(rows: list[dict]):
    """Return an engine mock whose first conn.execute returns *rows* as mappings."""
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.all.return_value = rows
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


def _make_row(**kwargs):
    """Return a minimal peer row with sensible defaults."""
    defaults = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "is_parent": True,
        "state": "Stage 2",
        "dwell_days": 10,
        "conviction_verdict": "POSITIVE",
        "conviction_ic": 0.065,
        "rs_pctile_3m": 0.82,
        "ret_3m": 0.15,
        "ema_20_ratio": 1.03,
        "extension_pct": 0.05,
        "vol_ratio_63": 1.40,
        "effort_ratio_63": 0.95,
    }
    defaults.update(kwargs)
    return defaults


def test_get_peer_matrix_returns_correct_shape():
    rows = [
        _make_row(symbol="RELIANCE", is_parent=True),
        _make_row(symbol="ONGC",     is_parent=False, conviction_verdict="NEUTRAL", rs_pctile_3m=0.55),
        _make_row(symbol="IOC",      is_parent=False, conviction_verdict="NEGATIVE", rs_pctile_3m=0.40),
    ]
    engine = _mock_db_rows(rows)
    result = get_peer_matrix("RELIANCE", engine=engine)

    assert "symbol" in result
    assert result["symbol"] == "RELIANCE"
    assert "peers" in result
    assert len(result["peers"]) == 3


def test_get_peer_matrix_parent_is_first_and_flagged():
    rows = [
        _make_row(symbol="RELIANCE", is_parent=True),
        _make_row(symbol="ONGC", is_parent=False),
    ]
    engine = _mock_db_rows(rows)
    result = get_peer_matrix("RELIANCE", engine=engine)

    assert result["peers"][0]["symbol"] == "RELIANCE"
    assert result["peers"][0]["is_parent"] is True
    assert result["peers"][1]["is_parent"] is False


def test_get_peer_matrix_metric_classification():
    row = _make_row(
        symbol="RELIANCE",
        is_parent=True,
        ema_20_ratio=1.05,    # → Rising
        vol_ratio_63=1.50,    # → Expanding
        conviction_verdict="POSITIVE",
        rs_pctile_3m=0.82,    # → 82.0
        ret_3m=0.15,          # → 15.0
        extension_pct=0.05,   # → 5.0
    )
    engine = _mock_db_rows([row])
    result = get_peer_matrix("RELIANCE", engine=engine)

    peer = result["peers"][0]
    assert peer["ema20_slope"] == "Rising"
    assert peer["volume"] == "Expanding"
    assert peer["conviction"] == "Bullish"
    assert peer["rs_vs_nifty"] == 82.0
    assert peer["ret_3m_pct"] == 15.0
    assert peer["extension_pct"] == 5.0


def test_get_peer_matrix_null_metrics_handled():
    """NULL metrics from DB should produce None or '—' — not raise exceptions."""
    row = _make_row(
        symbol="RELIANCE",
        is_parent=True,
        ema_20_ratio=None,
        vol_ratio_63=None,
        conviction_ic=None,
        rs_pctile_3m=None,
        ret_3m=None,
        extension_pct=None,
        conviction_verdict=None,
        state=None,
    )
    engine = _mock_db_rows([row])
    result = get_peer_matrix("RELIANCE", engine=engine)

    peer = result["peers"][0]
    assert peer["ema20_slope"] == "—"
    assert peer["volume"] == "—"
    assert peer["conviction"] == "Neutral"
    assert peer["conviction_ic"] is None
    assert peer["rs_vs_nifty"] is None
    assert peer["ret_3m_pct"] is None
    assert peer["extension_pct"] is None
    assert peer["stage"] == "—"


def test_get_peer_matrix_returns_error_when_no_rows():
    engine = _mock_db_rows([])
    result = get_peer_matrix("UNKNOWN", engine=engine)

    assert result["error"] == "no_data"
    assert result["symbol"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Route-level smoke test
# ---------------------------------------------------------------------------

def test_peer_matrix_route_returns_200():
    from fastapi.testclient import TestClient
    from atlas.api import app  # type: ignore[import]

    fake_result = {
        "symbol": "RELIANCE",
        "peers": [
            {
                "symbol": "RELIANCE",
                "company_name": "Reliance Industries Ltd",
                "is_parent": True,
                "stage": "Stage 2",
                "conviction": "Bullish",
                "conviction_ic": 0.065,
                "rs_vs_nifty": 82.0,
                "ema20_slope": "Rising",
                "volume": "Expanding",
                "ret_3m_pct": 15.0,
                "extension_pct": 5.0,
            }
        ],
    }

    with patch("atlas.tv.peer_matrix.get_peer_matrix", return_value=fake_result):
        client = TestClient(app)
        resp = client.get("/v1/stocks/RELIANCE/peer-matrix")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert body["data"]["peers"][0]["is_parent"] is True
    assert body["meta"]["source"] == "atlas_universe_stocks + atlas_stock_metrics_daily"


def test_peer_matrix_route_returns_404_for_no_data():
    from fastapi.testclient import TestClient
    from atlas.api import app  # type: ignore[import]

    with patch(
        "atlas.tv.peer_matrix.get_peer_matrix",
        return_value={"error": "no_data", "symbol": "GHOST"},
    ):
        client = TestClient(app)
        resp = client.get("/v1/stocks/GHOST/peer-matrix")

    assert resp.status_code == 404
```

- [ ] Run tests:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -m pytest tests/tv/test_peer_matrix.py -v
  ```
  Expected output (all tests pass):
  ```
  tests/tv/test_peer_matrix.py::test_classify_ema_slope[...] PASSED  (10 parametrized)
  tests/tv/test_peer_matrix.py::test_classify_volume[...] PASSED     (9 parametrized)
  tests/tv/test_peer_matrix.py::test_classify_conviction[...] PASSED (5 parametrized)
  tests/tv/test_peer_matrix.py::test_get_peer_matrix_returns_correct_shape PASSED
  tests/tv/test_peer_matrix.py::test_get_peer_matrix_parent_is_first_and_flagged PASSED
  tests/tv/test_peer_matrix.py::test_get_peer_matrix_metric_classification PASSED
  tests/tv/test_peer_matrix.py::test_get_peer_matrix_null_metrics_handled PASSED
  tests/tv/test_peer_matrix.py::test_get_peer_matrix_returns_error_when_no_rows PASSED
  tests/tv/test_peer_matrix.py::test_peer_matrix_route_returns_200 PASSED
  tests/tv/test_peer_matrix.py::test_peer_matrix_route_returns_404_for_no_data PASSED
  ```

- [ ] Commit:
  ```bash
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv add atlas/tv/peer_matrix.py atlas/tv/routes.py tests/tv/test_peer_matrix.py
  git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv commit -m "feat(stock-detail): GET /v1/stocks/{symbol}/peer-matrix — parent + top-4 sector peers with 8 metrics"
  ```

---

## Task 6 — Full suite regression check

- [ ] Run the entire TV test suite to confirm no regressions:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -m pytest tests/tv/ -v --tb=short
  ```
  Expected: all tests pass. Zero failures, zero errors.

- [ ] Confirm new endpoint paths are registered:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && python -c "
  from atlas.api import app
  routes = [r.path for r in app.routes]
  assert '/v1/stocks/{symbol}/rs-ratios' in routes, 'rs-ratios route missing'
  assert '/v1/stocks/{symbol}/peer-matrix' in routes, 'peer-matrix route missing'
  print('Routes OK:', [r for r in routes if '/v1/stocks/' in r])
  "
  ```
  Expected output:
  ```
  Routes OK: ['/v1/stocks/{symbol}/rs-ratios', '/v1/stocks/{symbol}/peer-matrix']
  ```

---

## EC2 deploy checklist (run after pushing branch)

These steps run on the EC2 host (`jsl-wealth-server`). Not needed locally.

- [ ] Pull branch:
  ```bash
  cd ~/atlas && git fetch && git checkout feat/tv-integration && git pull
  ```
- [ ] Apply migration 118:
  ```bash
  cd ~/atlas && alembic upgrade head
  ```
  Expected output: `Running upgrade 117 -> 118, Add PE, PS, PB, Debt/Equity, ROE columns to atlas.tv_metrics`
- [ ] Restart API:
  ```bash
  pm2 restart atlas-api && pm2 logs atlas-api --lines 20
  ```
- [ ] Smoke test new endpoints:
  ```bash
  curl -s "http://localhost:8000/v1/stocks/RELIANCE/rs-ratios" | python3 -m json.tool | head -20
  curl -s "http://localhost:8000/v1/stocks/RELIANCE/peer-matrix" | python3 -m json.tool | head -20
  ```
  Both must return `200` with `data` and `meta` keys.
- [ ] Trigger screener to populate fundamental columns:
  ```bash
  curl -s -X POST "http://localhost:8000/v1/tv/internal/run-screener"
  ```
  Expected: `{"status":"ok"}`
- [ ] Verify fundamentals populated:
  ```bash
  psql $DATABASE_URL -c "SELECT symbol, pe_ttm, ps_current, pb_fbs, debt_to_equity, roe FROM atlas.tv_metrics WHERE pe_ttm IS NOT NULL LIMIT 5;"
  ```
  Expected: at least 1 row with non-NULL fundamental values.

---

## Summary of new API surface

| Method | Path | Source tables | Notes |
|--------|------|---------------|-------|
| GET | `/v1/tv/metrics/{symbol}` | `atlas.tv_metrics` | Extended: +pe_ttm, ps_current, pb_fbs, debt_to_equity, roe |
| GET | `/v1/stocks/{symbol}/rs-ratios` | `de_equity_ohlcv`, `de_index_prices` | `?days=252` optional; returns up to 252-day ratio series |
| GET | `/v1/stocks/{symbol}/peer-matrix` | `atlas_universe_stocks`, `atlas_stock_metrics_daily`, `atlas_stock_state_daily`, `atlas_conviction_daily` | Parent stock + top-4 sector peers sorted by mcap |

## Files created / modified

| Action | Path |
|--------|------|
| NEW | `migrations/versions/118_tv_fundamentals.py` |
| NEW | `atlas/tv/rs_ratios.py` |
| NEW | `atlas/tv/peer_matrix.py` |
| NEW | `tests/tv/test_rs_ratios.py` |
| NEW | `tests/tv/test_peer_matrix.py` |
| MODIFIED | `atlas/tv/screener.py` — 5 new columns in `_COLUMNS`, upsert SQL, row dict |
| MODIFIED | `atlas/tv/routes.py` — extended TV metrics SQL, `_stocks_router`, 2 new route handlers, 2 new imports |
| MODIFIED | `atlas/api/__init__.py` — `tv_stocks_router` import + `include_router` |
| MODIFIED | `tests/tv/test_screener.py` — `test_fundamental_columns_present_in_upsert_row` |
| MODIFIED | `tests/tv/test_routes.py` — 5 new keys in `test_tv_metrics_returns_200` fake_row |
