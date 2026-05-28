# TradingView Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TradingView market data caching, portfolio risk analytics, and MCP tool wiring to Atlas as a new `atlas/tv/` bounded context.

**Architecture:** Approach B (Cached + MCP). A nightly pg_cron job fetches TV screener metrics for all ~750 Atlas universe symbols via the `tradingview-screener` PyPI library, upserts into `atlas.tv_metrics`, and the API serves stale-if-old data with a staleness guard. Portfolio analytics (Sharpe, Sortino, Calmar, Alpha, Beta, MaxDD, TWR) are computed on-demand from `atlas_paper_portfolio`, `atlas_user_lots`, and `de_equity_ohlcv`. TV-07 wires `mikeh-22/tradingview-mcp` into the MCP server list for Hermes queries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (sync engine), `tradingview-screener` PyPI, Alembic, pg_cron, NumPy/Pandas (vectorised), pytest + pytest-asyncio

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `migrations/versions/117_tv_metrics_tables.py` | Create | tv_metrics + tv_portfolio_exports schema |
| `pyproject.toml` | Modify | Add `tradingview-screener` dependency |
| `atlas/tv/__init__.py` | Create | Package marker + public exports |
| `atlas/tv/screener.py` | Create | Fetch TV data for all ~750 symbols, upsert, instrument_id soft-link |
| `atlas/tv/portfolio_analytics.py` | Create | Compute Sharpe/Sortino/Calmar/Alpha/Beta/MaxDD/TWR |
| `atlas/tv/routes.py` | Create | GET /v1/tv/metrics/{symbol}, GET /v1/portfolios/{id}/analytics |
| `atlas/api/__init__.py` | Modify | Register tv_router |
| `tests/tv/test_screener.py` | Create | Unit tests for screener upsert logic |
| `tests/tv/test_portfolio_analytics.py` | Create | Unit tests for each analytics metric |
| `tests/tv/test_routes.py` | Create | API smoke tests for TV routes |

**BLOCKED** (pending design approval or user input):
- `atlas/tv/csv_export.py` — TV-04: CSV export (format confirmed — see Task 10)
- Frontend: TV-05 (TVChartPanel, TVMetricsBadge) — needs `.design-approved.json`
- Frontend: TV-06 (Portfolio Analytics page) — needs `.design-approved.json`

---

## Task 1: Migration 117 — tv_metrics + tv_portfolio_exports tables

**Files:**
- Create: `migrations/versions/117_tv_metrics_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""tv_metrics and tv_portfolio_exports tables

Revision ID: 117
Revises: 116
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa

revision = "117"
down_revision = "116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.tv_metrics (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol          TEXT NOT NULL,
            instrument_id   UUID,
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            tv_recommend_label  TEXT,
            recommend_all   NUMERIC(10,6),
            recommend_ma    NUMERIC(10,6),
            recommend_other NUMERIC(10,6),
            rsi_14          NUMERIC(10,4),
            macd_macd       NUMERIC(10,4),
            ema_20          NUMERIC(16,4),
            ema_50          NUMERIC(16,4),
            ema_200         NUMERIC(16,4),
            atr_14          NUMERIC(16,4),
            volume          BIGINT,
            volume_10d_avg  BIGINT,
            price           NUMERIC(16,4),
            high_52w        NUMERIC(16,4),
            low_52w         NUMERIC(16,4),
            raw_payload     JSONB,
            CONSTRAINT tv_metrics_symbol_unique UNIQUE (symbol)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tv_metrics_instrument_id
            ON atlas.tv_metrics (instrument_id)
            WHERE instrument_id IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.tv_portfolio_exports (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id    UUID NOT NULL,
            exported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            row_count       INT NOT NULL,
            file_bytes      BYTEA
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tv_portfolio_exports_portfolio_id
            ON atlas.tv_portfolio_exports (portfolio_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.tv_portfolio_exports")
    op.execute("DROP TABLE IF EXISTS atlas.tv_metrics")
```

- [ ] **Step 2: Run migration locally**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os
alembic upgrade head
```

Expected: `Running upgrade 116 -> 117, tv_metrics and tv_portfolio_exports tables`

- [ ] **Step 3: Verify tables exist**

```bash
psql $DATABASE_URL -c "\dt atlas.tv_metrics" -c "\dt atlas.tv_portfolio_exports"
```

Expected: Both tables listed.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/117_tv_metrics_tables.py
git commit -m "feat(tv): migration 117 — tv_metrics + tv_portfolio_exports"
```

---

## Task 2: Add tradingview-screener dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

In `pyproject.toml`, find the `[project.dependencies]` or `dependencies = [` section and add:

```toml
"tradingview-screener>=0.14.0",
```

Place it alphabetically near `"structlog"` or at end of block.

- [ ] **Step 2: Verify install**

```bash
pip install tradingview-screener
python -c "from tradingview_screener import Scanner; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(tv): add tradingview-screener dependency"
```

---

## Task 3: atlas/tv package skeleton

**Files:**
- Create: `atlas/tv/__init__.py`

- [ ] **Step 1: Create package**

```python
"""atlas.tv — TradingView integration bounded context.

Public surface:
  fetch_and_upsert_all()   — called by pg_cron nightly
  compute_portfolio_analytics(portfolio_id, engine) — on-demand
"""

from atlas.tv.screener import fetch_and_upsert_all
from atlas.tv.portfolio_analytics import compute_portfolio_analytics

__all__ = ["fetch_and_upsert_all", "compute_portfolio_analytics"]
```

- [ ] **Step 2: Create tests/tv directory**

```bash
mkdir -p tests/tv
touch tests/tv/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add atlas/tv/__init__.py tests/tv/__init__.py
git commit -m "feat(tv): atlas/tv package skeleton"
```

---

## Task 4: screener.py — fetch, upsert, instrument_id soft-link

**Files:**
- Create: `atlas/tv/screener.py`
- Create: `tests/tv/test_screener.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tv/test_screener.py
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from atlas.tv.screener import fetch_and_upsert_all, _resolve_instrument_ids


def _mock_engine(rows: list[dict]):
    """Return a fake engine whose execute returns rows."""
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.all.return_value = rows
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


def test_resolve_instrument_ids_maps_symbol_to_uuid():
    engine = _mock_engine([
        {"symbol": "RELIANCE", "instrument_id": "uuid-1"},
        {"symbol": "TCS", "instrument_id": "uuid-2"},
    ])
    result = _resolve_instrument_ids(["RELIANCE", "TCS"], engine)
    assert result["RELIANCE"] == "uuid-1"
    assert result["TCS"] == "uuid-2"


def test_fetch_and_upsert_all_calls_upsert(monkeypatch):
    fake_df = pd.DataFrame([
        {"ticker": "RELIANCE", "Recommend.All": 0.5, "RSI": 55.0, "close": 2800.0,
         "MACD.macd": 10.0, "EMA20": 2750.0, "EMA50": 2700.0, "EMA200": 2600.0,
         "ATR": 40.0, "volume": 1_000_000, "average_volume_10d_calc": 900_000,
         "High.All": 3000.0, "Low.All": 2400.0, "Recommend.MA": 0.6,
         "Recommend.Other": 0.4}
    ])
    monkeypatch.setattr("atlas.tv.screener._fetch_tv_batch", lambda symbols: fake_df)
    engine = _mock_engine([{"symbol": "RELIANCE", "instrument_id": "uuid-1"}])
    upsert_calls = []
    with patch("atlas.tv.screener._upsert_rows") as mock_upsert:
        fetch_and_upsert_all(engine=engine)
    mock_upsert.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/tv/test_screener.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.tv.screener'`

- [ ] **Step 3: Implement screener.py**

```python
# atlas/tv/screener.py
"""Nightly fetch from tradingview-screener → upsert into atlas.tv_metrics."""

from __future__ import annotations

import math
import structlog
import pandas as pd
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

_BATCH_SIZE = 100  # TV screener API limit per call

_COLUMNS = [
    "close",
    "volume",
    "Recommend.All",
    "Recommend.MA",
    "Recommend.Other",
    "RSI",
    "MACD.macd",
    "EMA20",
    "EMA50",
    "EMA200",
    "ATR",
    "average_volume_10d_calc",
    "High.All",
    "Low.All",
]


def _load_universe_symbols(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            "SELECT symbol FROM atlas.atlas_universe_stocks ORDER BY symbol"
        ).mappings().all()
    return [r["symbol"] for r in rows]


def _fetch_tv_batch(symbols: list[str]) -> pd.DataFrame:
    from tradingview_screener import Scanner

    # TV screener expects NSE:SYMBOL format for Indian equities
    qualified = [f"NSE:{s}" for s in symbols]
    _, df = Scanner.get_scanner_data(
        symbols=qualified,
        columns=_COLUMNS,
    )
    if df.empty:
        return df
    # Strip "NSE:" prefix from ticker column
    df["ticker"] = df["ticker"].str.replace("NSE:", "", regex=False)
    return df


def _resolve_instrument_ids(symbols: list[str], engine: Engine) -> dict[str, str]:
    """Return {symbol: instrument_id_str} for symbols that exist in atlas_universe_stocks."""
    with engine.connect() as conn:
        rows = conn.execute(
            "SELECT symbol, instrument_id::text FROM atlas.atlas_universe_stocks "
            "WHERE symbol = ANY(:syms)",
            {"syms": symbols},
        ).mappings().all()
    return {r["symbol"]: r["instrument_id"] for r in rows}


def _upsert_rows(rows: list[dict], engine: Engine) -> None:
    if not rows:
        return
    upsert_sql = """
        INSERT INTO atlas.tv_metrics (
            symbol, instrument_id, fetched_at,
            tv_recommend_label, recommend_all, recommend_ma, recommend_other,
            rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
            volume, volume_10d_avg, price, high_52w, low_52w, raw_payload
        ) VALUES (
            :symbol, :instrument_id, NOW(),
            :tv_recommend_label, :recommend_all, :recommend_ma, :recommend_other,
            :rsi_14, :macd_macd, :ema_20, :ema_50, :ema_200, :atr_14,
            :volume, :volume_10d_avg, :price, :high_52w, :low_52w, :raw_payload::jsonb
        )
        ON CONFLICT (symbol) DO UPDATE SET
            instrument_id    = EXCLUDED.instrument_id,
            fetched_at       = EXCLUDED.fetched_at,
            tv_recommend_label = EXCLUDED.tv_recommend_label,
            recommend_all    = EXCLUDED.recommend_all,
            recommend_ma     = EXCLUDED.recommend_ma,
            recommend_other  = EXCLUDED.recommend_other,
            rsi_14           = EXCLUDED.rsi_14,
            macd_macd        = EXCLUDED.macd_macd,
            ema_20           = EXCLUDED.ema_20,
            ema_50           = EXCLUDED.ema_50,
            ema_200          = EXCLUDED.ema_200,
            atr_14           = EXCLUDED.atr_14,
            volume           = EXCLUDED.volume,
            volume_10d_avg   = EXCLUDED.volume_10d_avg,
            price            = EXCLUDED.price,
            high_52w         = EXCLUDED.high_52w,
            low_52w          = EXCLUDED.low_52w,
            raw_payload      = EXCLUDED.raw_payload
    """
    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)


def _label(score: float | None) -> str | None:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return None
    if score >= 0.5:
        return "STRONG_BUY"
    if score >= 0.1:
        return "BUY"
    if score > -0.1:
        return "NEUTRAL"
    if score > -0.5:
        return "SELL"
    return "STRONG_SELL"


def fetch_and_upsert_all(engine: Engine | None = None) -> None:
    """Entry point for pg_cron: fetch TV metrics for all ~750 universe symbols."""
    engine = engine or get_engine()
    symbols = _load_universe_symbols(engine)
    log.info("tv_screener.start", total_symbols=len(symbols))

    inst_map = _resolve_instrument_ids(symbols, engine)

    total_upserted = 0
    for i in range(0, len(symbols), _BATCH_SIZE):
        batch = symbols[i : i + _BATCH_SIZE]
        try:
            df = _fetch_tv_batch(batch)
        except Exception:
            log.exception("tv_screener.batch_failed", batch_start=i, batch_size=len(batch))
            continue

        if df.empty:
            log.warning("tv_screener.empty_batch", batch_start=i)
            continue

        rows = []
        for _, row in df.iterrows():
            sym = row.get("ticker", "")
            recommend_all = row.get("Recommend.All")
            rows.append({
                "symbol": sym,
                "instrument_id": inst_map.get(sym),
                "tv_recommend_label": _label(recommend_all),
                "recommend_all": recommend_all,
                "recommend_ma": row.get("Recommend.MA"),
                "recommend_other": row.get("Recommend.Other"),
                "rsi_14": row.get("RSI"),
                "macd_macd": row.get("MACD.macd"),
                "ema_20": row.get("EMA20"),
                "ema_50": row.get("EMA50"),
                "ema_200": row.get("EMA200"),
                "atr_14": row.get("ATR"),
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                "volume_10d_avg": int(row["average_volume_10d_calc"]) if pd.notna(row.get("average_volume_10d_calc")) else None,
                "price": row.get("close"),
                "high_52w": row.get("High.All"),
                "low_52w": row.get("Low.All"),
                "raw_payload": row.to_json(),
            })

        _upsert_rows(rows, engine)
        total_upserted += len(rows)
        log.info("tv_screener.batch_done", batch_start=i, rows=len(rows))

    log.info("tv_screener.complete", total_upserted=total_upserted)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tv/test_screener.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add atlas/tv/screener.py tests/tv/test_screener.py
git commit -m "feat(tv): screener.py — nightly TV metrics fetch + upsert"
```

---

## Task 5: GET /v1/tv/metrics/{symbol} route

**Files:**
- Create: `atlas/tv/routes.py` (initial — metrics endpoint only)
- Modify: `atlas/api/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tv/test_routes.py
import os
os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

# Import app after env var is set
from atlas.main import app  # adjust if main.py location differs

client = TestClient(app)


def test_tv_metrics_returns_200(monkeypatch):
    fake_row = {
        "symbol": "RELIANCE",
        "instrument_id": "uuid-1",
        "fetched_at": "2026-05-28T21:00:00+05:30",
        "tv_recommend_label": "BUY",
        "recommend_all": 0.35,
        "rsi_14": 58.0,
        "price": 2820.0,
        "high_52w": 3000.0,
        "low_52w": 2400.0,
        "raw_payload": "{}",
    }
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.first.return_value = fake_row
    mock_engine = MagicMock()
    mock_engine.connect.return_value = conn

    with patch("atlas.tv.routes.get_engine", return_value=mock_engine):
        resp = client.get("/v1/tv/metrics/RELIANCE")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["symbol"] == "RELIANCE"
    assert data["tv_recommend_label"] == "BUY"


def test_tv_metrics_returns_404_for_unknown_symbol(monkeypatch):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.first.return_value = None
    mock_engine = MagicMock()
    mock_engine.connect.return_value = conn

    with patch("atlas.tv.routes.get_engine", return_value=mock_engine):
        resp = client.get("/v1/tv/metrics/DOESNOTEXIST")

    assert resp.status_code == 404


def test_tv_metrics_stale_flag(monkeypatch):
    import datetime
    fake_row = {
        "symbol": "TCS",
        "instrument_id": "uuid-2",
        # 4 days ago — stale
        "fetched_at": (datetime.datetime.utcnow() - datetime.timedelta(days=4)).isoformat(),
        "tv_recommend_label": "NEUTRAL",
        "recommend_all": 0.0,
        "rsi_14": 50.0,
        "price": 3500.0,
        "high_52w": 3800.0,
        "low_52w": 3000.0,
        "raw_payload": "{}",
    }
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.first.return_value = fake_row
    mock_engine = MagicMock()
    mock_engine.connect.return_value = conn

    with patch("atlas.tv.routes.get_engine", return_value=mock_engine):
        resp = client.get("/v1/tv/metrics/TCS")

    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["is_stale"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tv/test_routes.py -v
```

Expected: FAIL — no routes registered yet.

- [ ] **Step 3: Implement routes.py (metrics endpoint)**

```python
# atlas/tv/routes.py
"""TradingView integration API routes."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException

from atlas.db import get_engine

router = APIRouter(prefix="/v1/tv", tags=["tv"])

_STALE_DAYS = 2  # flag stale if fetched_at older than this


@router.get("/metrics/{symbol}")
def get_tv_metrics(symbol: str):
    """Return cached TV screener metrics for a symbol.

    Meta includes is_stale=True if data is >2 trading days old.
    """
    sql = """
        SELECT symbol, instrument_id::text, fetched_at,
               tv_recommend_label, recommend_all, recommend_ma, recommend_other,
               rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
               volume, volume_10d_avg, price, high_52w, low_52w
        FROM atlas.tv_metrics
        WHERE symbol = :symbol
    """
    with get_engine().connect() as conn:
        row = conn.execute(sql, {"symbol": symbol.upper()}).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No TV metrics for symbol: {symbol}")

    fetched_at = row["fetched_at"]
    if isinstance(fetched_at, str):
        fetched_at = datetime.datetime.fromisoformat(fetched_at)
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=datetime.timezone.utc)
    is_stale = (now - fetched_at).days >= _STALE_DAYS

    return {
        "data": dict(row),
        "meta": {
            "data_as_of": fetched_at.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "is_stale": is_stale,
            "source": "tradingview-screener",
        },
    }
```

- [ ] **Step 4: Register tv_router in atlas/api/__init__.py**

Open `atlas/api/__init__.py` and add after the last `include_router` call:

```python
from atlas.tv.routes import router as tv_router
app.include_router(tv_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/tv/test_routes.py::test_tv_metrics_returns_200 tests/tv/test_routes.py::test_tv_metrics_returns_404_for_unknown_symbol tests/tv/test_routes.py::test_tv_metrics_stale_flag -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add atlas/tv/routes.py atlas/api/__init__.py tests/tv/test_routes.py
git commit -m "feat(tv): GET /v1/tv/metrics/{symbol} with staleness guard"
```

---

## Task 6: pg_cron job for nightly TV metrics fetch

**Files:**
- Modify: `migrations/versions/117_tv_metrics_tables.py`

Note: Add the pg_cron job to the existing migration 117 upgrade() function, not a new migration. The migration already exists from Task 1 — re-run after amending, or create a thin 118 migration if 117 is already applied.

If migration 117 **not yet applied**, amend it. If already applied, create `migrations/versions/118_tv_screener_cron.py` with `down_revision = "117"`.

- [ ] **Step 1: Add pg_cron schedule to migration**

Add to `upgrade()` function (in 117 or new 118):

```python
op.execute("""
    SELECT cron.schedule(
        'tv_screener_nightly',
        '30 15 * * 1-5',
        $$ SELECT atlas.tv_screener_run() $$
    )
""")
# 30 15 UTC = 21:00 IST, weekdays only
```

Add wrapper function so pg_cron can call Python via a pg stored proc:

```python
op.execute("""
    CREATE OR REPLACE FUNCTION atlas.tv_screener_run()
    RETURNS void LANGUAGE plpgsql AS $$
    BEGIN
        PERFORM http_post(
            'http://localhost:8000/v1/tv/internal/run-screener',
            '',
            'application/json'
        );
    END;
    $$
""")
```

**Note:** The pg_cron → HTTP approach mirrors the pattern from migration 099. The internal endpoint below must be added to routes.py.

- [ ] **Step 2: Add internal trigger endpoint to routes.py**

Append to `atlas/tv/routes.py`:

```python
from atlas.tv.screener import fetch_and_upsert_all
import structlog as _log

_internal_log = _log.get_logger(__name__)

_internal_router = APIRouter(prefix="/v1/tv/internal", tags=["tv-internal"])


@_internal_router.post("/run-screener")
def trigger_screener():
    """Called by pg_cron at 21:00 IST on weekdays."""
    try:
        fetch_and_upsert_all()
        return {"status": "ok"}
    except Exception as exc:
        _internal_log.exception("tv_screener.trigger_failed")
        raise HTTPException(status_code=500, detail=str(exc))
```

Also register `_internal_router` in `atlas/api/__init__.py`:

```python
from atlas.tv.routes import router as tv_router, _internal_router as tv_internal_router
app.include_router(tv_router)
app.include_router(tv_internal_router)
```

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade 117 -> 118` (or amending 117 in place)

- [ ] **Step 4: Verify cron is registered**

```bash
psql $DATABASE_URL -c "SELECT jobname, schedule FROM cron.job WHERE jobname = 'tv_screener_nightly'"
```

Expected: 1 row returned with `30 15 * * 1-5`

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/117_tv_metrics_tables.py  # or 118
git commit -m "feat(tv): pg_cron nightly screener job at 21:00 IST"
```

---

## Task 7: portfolio_analytics.py — risk metrics computation

**Files:**
- Create: `atlas/tv/portfolio_analytics.py`
- Create: `tests/tv/test_portfolio_analytics.py`

**Formulas (from spec + methodology lock):**
- Daily return series: TWR from portfolio lots using `de_equity_ohlcv.COALESCE(close_adj, close)`
- Sharpe = (mean_daily_return - Rf/252) / std_daily_return * sqrt(252)
- Sortino = (mean_daily_return - Rf/252) / downside_std * sqrt(252) where downside_std uses only negative returns
- Calmar = annualized_return / max_drawdown (NULL if max_drawdown == 0)
- Beta = cov(Rp, Rm) / var(Rm) where Rm = Nifty 50 daily returns; NULL if < 30 observations
- Alpha = Rp_annualised - [Rf + Beta * (Rm_annualised - Rf)]; Jensen's Alpha
- Max Drawdown = min(cumulative / rolling_max - 1); absolute value
- TWR = product(1 + daily_return) - 1 over full period
- Rf from `load_thresholds()["risk_free_91d"]` (annualised); use Rf/252 for daily
- Benchmark (Rm): `de_index_prices` WHERE `index_code = 'NIFTY 50'`

- [ ] **Step 1: Write the failing tests**

```python
# tests/tv/test_portfolio_analytics.py
import numpy as np
import pandas as pd
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from atlas.tv.portfolio_analytics import (
    _compute_sharpe,
    _compute_sortino,
    _compute_beta,
    _compute_alpha,
    _compute_max_drawdown,
    _compute_calmar,
    _compute_twr,
)

RNG = np.random.default_rng(42)
N = 252
PORTFOLIO_RETURNS = pd.Series(RNG.normal(0.0005, 0.012, N))
NIFTY_RETURNS = pd.Series(RNG.normal(0.0003, 0.010, N))
RF = Decimal("0.065")  # 6.5% annualised


def test_sharpe_positive_for_positive_drift():
    sharpe = _compute_sharpe(PORTFOLIO_RETURNS, RF)
    assert isinstance(sharpe, float)
    assert -5.0 < sharpe < 5.0


def test_sortino_gte_sharpe_for_positive_returns():
    # Sortino ignores upside volatility so must be >= Sharpe when drift > 0
    sharpe = _compute_sharpe(PORTFOLIO_RETURNS, RF)
    sortino = _compute_sortino(PORTFOLIO_RETURNS, RF)
    assert sortino >= sharpe


def test_beta_is_near_one_for_identical_series():
    beta = _compute_beta(NIFTY_RETURNS, NIFTY_RETURNS)
    assert abs(beta - 1.0) < 0.01


def test_beta_null_for_short_series():
    short = pd.Series(NIFTY_RETURNS[:25])
    assert _compute_beta(short, short[:25]) is None


def test_max_drawdown_between_zero_and_one():
    dd = _compute_max_drawdown(PORTFOLIO_RETURNS)
    assert 0.0 <= dd <= 1.0


def test_twr_compound_product():
    simple = pd.Series([0.1, -0.1])  # 0.1 * 0.9 - 1 = -0.01
    twr = _compute_twr(simple)
    assert abs(twr - (1.1 * 0.9 - 1)) < 1e-9


def test_calmar_null_when_zero_drawdown():
    flat = pd.Series([0.001] * 100)
    # No drawdown on a monotonically rising series → calmar should not raise
    calmar = _compute_calmar(flat)
    # Drawdown can be very small but not exactly 0, so calmar may be very large
    assert calmar is None or calmar > 0


def test_alpha_positive_for_alpha_generating_portfolio():
    outperforming = NIFTY_RETURNS + 0.001  # 25 bps daily alpha
    alpha = _compute_alpha(outperforming, NIFTY_RETURNS, RF)
    assert alpha > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tv/test_portfolio_analytics.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.tv.portfolio_analytics'`

- [ ] **Step 3: Implement portfolio_analytics.py**

```python
# atlas/tv/portfolio_analytics.py
"""Compute risk/return analytics for Atlas paper portfolios and user lots."""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
import structlog
from decimal import Decimal
from typing import Any

from atlas.db import get_engine, load_thresholds
from sqlalchemy.engine import Engine

log = structlog.get_logger(__name__)

_MIN_BETA_OBS = 30
_ANNUALISE = 252


def _compute_sharpe(returns: pd.Series, rf_annual: Decimal) -> float:
    rf_daily = float(rf_annual) / _ANNUALISE
    excess = returns - rf_daily
    std = returns.std(ddof=1)
    if std == 0:
        return 0.0
    return float((excess.mean() / std) * math.sqrt(_ANNUALISE))


def _compute_sortino(returns: pd.Series, rf_annual: Decimal) -> float:
    rf_daily = float(rf_annual) / _ANNUALISE
    excess = returns - rf_daily
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std(ddof=1) == 0:
        return float("inf")
    return float((excess.mean() / downside.std(ddof=1)) * math.sqrt(_ANNUALISE))


def _compute_beta(port_returns: pd.Series, mkt_returns: pd.Series) -> float | None:
    aligned = pd.concat([port_returns, mkt_returns], axis=1).dropna()
    if len(aligned) < _MIN_BETA_OBS:
        return None
    cov = np.cov(aligned.iloc[:, 0].values, aligned.iloc[:, 1].values)
    var_mkt = cov[1, 1]
    if var_mkt == 0:
        return None
    return float(cov[0, 1] / var_mkt)


def _compute_alpha(
    port_returns: pd.Series,
    mkt_returns: pd.Series,
    rf_annual: Decimal,
) -> float | None:
    beta = _compute_beta(port_returns, mkt_returns)
    if beta is None:
        return None
    rf = float(rf_annual)
    rp = float((1 + port_returns).prod() ** (_ANNUALISE / max(len(port_returns), 1)) - 1)
    rm = float((1 + mkt_returns).prod() ** (_ANNUALISE / max(len(mkt_returns), 1)) - 1)
    return rp - (rf + beta * (rm - rf))


def _compute_max_drawdown(returns: pd.Series) -> float:
    cumulative = (1 + returns.fillna(0)).cumprod()
    rolling_peak = cumulative.cummax()
    drawdown = cumulative / rolling_peak - 1
    return float(abs(drawdown.min()))


def _compute_calmar(returns: pd.Series) -> float | None:
    dd = _compute_max_drawdown(returns)
    if dd == 0:
        return None
    ann_return = float((1 + returns).prod() ** (_ANNUALISE / max(len(returns), 1)) - 1)
    return ann_return / dd


def _compute_twr(returns: pd.Series) -> float:
    return float((1 + returns).prod() - 1)


def _fetch_portfolio_returns(portfolio_id: str, engine: Engine) -> pd.Series:
    """Build daily return series for a paper portfolio from lot-level prices.

    Returns: pd.Series indexed by date, values = daily portfolio return.
    """
    lots_sql = """
        SELECT
            au.symbol,
            p.entry_date,
            p.exit_date,
            p.entry_price,
            p.exit_price
        FROM atlas.atlas_paper_portfolio p
        JOIN atlas.atlas_universe_stocks au ON au.instrument_id = p.instrument_id
        WHERE p.portfolio_id = :pid
          AND p.exit_date IS NOT NULL
    """
    with engine.connect() as conn:
        rows = conn.execute(lots_sql, {"pid": portfolio_id}).mappings().all()

    if not rows:
        return pd.Series(dtype=float)

    symbols = list({r["symbol"] for r in rows})
    prices_sql = """
        SELECT date, symbol, COALESCE(close_adj, close) AS close
        FROM public.de_equity_ohlcv
        WHERE symbol = ANY(:syms)
        ORDER BY symbol, date
    """
    with engine.connect() as conn:
        price_rows = conn.execute(prices_sql, {"syms": symbols}).mappings().all()

    if not price_rows:
        return pd.Series(dtype=float)

    prices = pd.DataFrame(list(price_rows))
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.pivot(index="date", columns="symbol", values="close")

    # Equal-weight lots → average daily return across active positions each day
    daily_rets = prices.pct_change()
    portfolio_series = daily_rets.mean(axis=1).dropna()
    return portfolio_series


def _fetch_nifty_returns(engine: Engine, start_date: str, end_date: str) -> pd.Series:
    sql = """
        SELECT date, close
        FROM public.de_index_prices
        WHERE index_code = 'NIFTY 50'
          AND date BETWEEN :start AND :end
        ORDER BY date
    """
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start_date, "end": end_date}).mappings().all()
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["close"].pct_change().dropna()


def compute_portfolio_analytics(
    portfolio_id: str,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Compute and return risk/return analytics dict for a portfolio."""
    engine = engine or get_engine()
    thresholds = load_thresholds()
    rf = thresholds.get("risk_free_91d", Decimal("0.065"))

    port_returns = _fetch_portfolio_returns(portfolio_id, engine)
    if port_returns.empty:
        return {"error": "no_data", "portfolio_id": portfolio_id}

    start = str(port_returns.index.min().date())
    end = str(port_returns.index.max().date())
    nifty_returns = _fetch_nifty_returns(engine, start, end)

    sharpe = _compute_sharpe(port_returns, rf)
    sortino = _compute_sortino(port_returns, rf)
    calmar = _compute_calmar(port_returns)
    beta = _compute_beta(port_returns, nifty_returns)
    alpha = _compute_alpha(port_returns, nifty_returns, rf)
    max_dd = _compute_max_drawdown(port_returns)
    twr = _compute_twr(port_returns)
    ann_return = float((1 + port_returns).prod() ** (_ANNUALISE / max(len(port_returns), 1)) - 1)

    # Build dual-benchmark daily returns series for response
    aligned = pd.concat(
        {"portfolio_return": port_returns, "nifty50_return": nifty_returns},
        axis=1,
    ).dropna()

    daily_returns = [
        {
            "date": str(idx.date()),
            "portfolio_return": round(float(row["portfolio_return"]), 6),
            "nifty50_return": round(float(row["nifty50_return"]), 6),
        }
        for idx, row in aligned.iterrows()
    ]

    return {
        "portfolio_id": portfolio_id,
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4) if not math.isinf(sortino) else None,
        "calmar": round(calmar, 4) if calmar is not None else None,
        "beta": round(beta, 4) if beta is not None else None,
        "alpha": round(alpha, 4) if alpha is not None else None,
        "max_drawdown": round(max_dd, 4),
        "twr": round(twr, 4),
        "annualised_return": round(ann_return, 4),
        "observation_days": len(port_returns),
        "risk_free_rate_used": float(rf),
        "daily_returns": daily_returns,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tv/test_portfolio_analytics.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add atlas/tv/portfolio_analytics.py tests/tv/test_portfolio_analytics.py
git commit -m "feat(tv): portfolio analytics — Sharpe/Sortino/Calmar/Alpha/Beta/MaxDD/TWR"
```

---

## Task 8: GET /v1/portfolios/{id}/analytics route

**Files:**
- Modify: `atlas/tv/routes.py`

- [ ] **Step 1: Add analytics route to routes.py**

Append to `atlas/tv/routes.py`:

```python
from atlas.tv.portfolio_analytics import compute_portfolio_analytics

_portfolios_router = APIRouter(prefix="/v1/portfolios", tags=["portfolios-analytics"])


@_portfolios_router.get("/{portfolio_id}/analytics")
def get_portfolio_analytics(portfolio_id: str):
    """Return Sharpe, Sortino, Calmar, Beta, Alpha, MaxDD, TWR for a portfolio."""
    result = compute_portfolio_analytics(portfolio_id)
    if "error" in result and result["error"] == "no_data":
        raise HTTPException(
            status_code=404,
            detail=f"No closed positions found for portfolio: {portfolio_id}",
        )
    return {
        "data": result,
        "meta": {
            "data_as_of": result.get("daily_returns", [{}])[-1].get("date") if result.get("daily_returns") else None,
            "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "source": "atlas-portfolio-analytics",
        },
    }
```

Register `_portfolios_router` in `atlas/api/__init__.py`:

```python
from atlas.tv.routes import router as tv_router, _internal_router as tv_internal_router, _portfolios_router as tv_portfolios_router
app.include_router(tv_portfolios_router)
```

- [ ] **Step 2: Add test for analytics route**

Append to `tests/tv/test_routes.py`:

```python
def test_portfolio_analytics_returns_200(monkeypatch):
    fake_analytics = {
        "portfolio_id": "pid-1",
        "sharpe": 1.2,
        "sortino": 1.8,
        "calmar": 2.1,
        "beta": 0.85,
        "alpha": 0.12,
        "max_drawdown": 0.08,
        "twr": 0.35,
        "annualised_return": 0.22,
        "observation_days": 252,
        "risk_free_rate_used": 0.065,
        "daily_returns": [{"date": "2026-01-02", "portfolio_return": 0.005, "nifty50_return": 0.003}],
    }
    with patch("atlas.tv.routes.compute_portfolio_analytics", return_value=fake_analytics):
        resp = client.get("/v1/portfolios/pid-1/analytics")

    assert resp.status_code == 200
    assert resp.json()["data"]["sharpe"] == 1.2


def test_portfolio_analytics_returns_404_for_no_data(monkeypatch):
    with patch("atlas.tv.routes.compute_portfolio_analytics", return_value={"error": "no_data", "portfolio_id": "pid-x"}):
        resp = client.get("/v1/portfolios/pid-x/analytics")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/tv/test_routes.py -v
```

Expected: All 5 route tests PASS

- [ ] **Step 4: Commit**

```bash
git add atlas/tv/routes.py atlas/api/__init__.py tests/tv/test_routes.py
git commit -m "feat(tv): GET /v1/portfolios/{id}/analytics route"
```

---

## Task 9: MCP wiring — tradingview-mcp (TV-07)

**Goal:** Register `mikeh-22/tradingview-mcp` as an MCP server so Hermes agents can query TV data directly.

- [ ] **Step 1: Locate MCP config**

```bash
find /Users/nimishshah/Documents/GitHub/atlas-os -name "mcp*.json" -o -name ".mcp.json" -o -name "claude.json" 2>/dev/null | head -10
# Also check:
cat ~/.claude.json | python3 -m json.tool | grep -A5 "mcpServers" | head -20
```

- [ ] **Step 2: Add tradingview-mcp server entry**

In the MCP config (whichever file is active), add under `mcpServers`:

```json
"tradingview": {
  "command": "npx",
  "args": ["-y", "tradingview-mcp"],
  "env": {
    "TV_SESSION_ID": "${TV_SESSION_ID}",
    "TV_SESSION_SIGN": "${TV_SESSION_SIGN}"
  }
}
```

- [ ] **Step 3: Smoke test**

```bash
# Start atlas server and verify MCP lists tradingview as a server
curl -s http://localhost:8000/v1/agents.json | python3 -m json.tool | grep -i tradingview
```

Expected: tradingview appears as an available tool source.

- [ ] **Step 4: Update Hermes system prompt**

Find the Hermes prompt file:

```bash
grep -rn "system_prompt\|hermes\|HERMES_PROMPT" /Users/nimishshah/Documents/GitHub/atlas-os/atlas/inference/ --include="*.py" | head -10
```

Add to the Hermes `stock_analyst` specialist's tool list:

```
- tradingview.get_analysis(symbol) — returns TV technical recommendation for a symbol
- tradingview.get_quote(symbol) — returns real-time quote from TradingView
```

- [ ] **Step 5: Commit**

```bash
git add .mcp.json  # or whichever config file was modified
git commit -m "feat(tv): wire tradingview-mcp into MCP server config (TV-07)"
```

---

## Task 10: csv_export.py — TradingView portfolio CSV export (TV-04)

**Files:**
- Create: `atlas/tv/csv_export.py`
- Modify: `atlas/tv/routes.py`
- Create: `tests/tv/test_csv_export.py`

**CSV format (confirmed from user-provided example):**

```
Symbol,Side,Qty,Fill Price,Commission,Closing Time
NASDAQ:AAPL,Buy,10,217,0,2024-09-17 0:00:00
NASDAQ:AAPL,Sell,10,240.01,,2024-09-18 0:00:00
```

Atlas mapping:
- `Symbol` → `NSE:{symbol}` (e.g. `NSE:RELIANCE`)
- `Side` → `Buy` for entry rows, `Sell` for exit rows
- `Qty` → `quantity` from `atlas_paper_portfolio`
- `Fill Price` → `entry_price` (Buy) or `exit_price` (Sell)
- `Commission` → empty (not tracked in Atlas)
- `Closing Time` → `entry_date` (Buy) or `exit_date` (Sell) as `YYYY-MM-DD 0:00:00`

Each lot generates two rows (Buy + Sell) when the position is closed. Open positions (null exit_date) generate only a Buy row.

- [ ] **Step 1: Write the failing test**

```python
# tests/tv/test_csv_export.py
import io
import csv
from unittest.mock import MagicMock
from decimal import Decimal

from atlas.tv.csv_export import export_portfolio_csv


def _mock_engine(lots: list[dict]):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.all.return_value = lots
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


_LOTS = [
    {
        "symbol": "RELIANCE",
        "quantity": Decimal("10"),
        "entry_price": Decimal("2800.00"),
        "entry_date": "2024-09-17",
        "exit_price": Decimal("3000.00"),
        "exit_date": "2024-09-18",
    },
    {
        "symbol": "TCS",
        "quantity": Decimal("5"),
        "entry_price": Decimal("3500.00"),
        "entry_date": "2024-10-01",
        "exit_price": None,
        "exit_date": None,
    },
]


def test_export_returns_bytes():
    engine = _mock_engine(_LOTS)
    result = export_portfolio_csv("pid-1", engine)
    assert isinstance(result, bytes)


def test_export_has_correct_header():
    engine = _mock_engine(_LOTS)
    csv_text = export_portfolio_csv("pid-1", engine).decode("utf-8")
    reader = csv.DictReader(io.StringIO(csv_text))
    assert reader.fieldnames == ["Symbol", "Side", "Qty", "Fill Price", "Commission", "Closing Time"]


def test_export_closed_lot_generates_buy_and_sell():
    engine = _mock_engine([_LOTS[0]])
    csv_text = export_portfolio_csv("pid-1", engine).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 2
    buy = next(r for r in rows if r["Side"] == "Buy")
    sell = next(r for r in rows if r["Side"] == "Sell")
    assert buy["Symbol"] == "NSE:RELIANCE"
    assert buy["Fill Price"] == "2800.00"
    assert sell["Fill Price"] == "3000.00"


def test_export_open_lot_generates_only_buy():
    engine = _mock_engine([_LOTS[1]])
    csv_text = export_portfolio_csv("pid-1", engine).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert rows[0]["Side"] == "Buy"
    assert rows[0]["Symbol"] == "NSE:TCS"
    assert rows[0]["Closing Time"] == "2024-10-01 0:00:00"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/tv/test_csv_export.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.tv.csv_export'`

- [ ] **Step 3: Implement csv_export.py**

```python
# atlas/tv/csv_export.py
"""Export Atlas paper portfolio as TradingView-compatible CSV.

TV import format:
  Symbol,Side,Qty,Fill Price,Commission,Closing Time
  NSE:RELIANCE,Buy,10,2800.00,,2024-09-17 0:00:00
  NSE:RELIANCE,Sell,10,3000.00,,2024-09-18 0:00:00
"""

from __future__ import annotations

import csv
import io
import structlog
from decimal import Decimal
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

_COLUMNS = ["Symbol", "Side", "Qty", "Fill Price", "Commission", "Closing Time"]


def _fmt_date(d) -> str:
    if d is None:
        return ""
    return f"{d} 0:00:00"


def _fmt_price(p) -> str:
    if p is None:
        return ""
    return f"{Decimal(str(p)):.2f}"


def export_portfolio_csv(portfolio_id: str, engine: Engine | None = None) -> bytes:
    """Return TV-format CSV bytes for all lots in a paper portfolio."""
    engine = engine or get_engine()

    sql = """
        SELECT
            au.symbol,
            p.quantity,
            p.entry_price,
            p.entry_date::text AS entry_date,
            p.exit_price,
            p.exit_date::text AS exit_date
        FROM atlas.atlas_paper_portfolio p
        JOIN atlas.atlas_universe_stocks au ON au.instrument_id = p.instrument_id
        WHERE p.portfolio_id = :pid
        ORDER BY p.entry_date, au.symbol
    """
    with engine.connect() as conn:
        rows = conn.execute(sql, {"pid": portfolio_id}).mappings().all()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_COLUMNS, lineterminator="\n")
    writer.writeheader()

    for row in rows:
        symbol = f"NSE:{row['symbol']}"
        qty = str(row["quantity"])

        writer.writerow({
            "Symbol": symbol,
            "Side": "Buy",
            "Qty": qty,
            "Fill Price": _fmt_price(row["entry_price"]),
            "Commission": "",
            "Closing Time": _fmt_date(row["entry_date"]),
        })

        if row["exit_date"] is not None:
            writer.writerow({
                "Symbol": symbol,
                "Side": "Sell",
                "Qty": qty,
                "Fill Price": _fmt_price(row["exit_price"]),
                "Commission": "",
                "Closing Time": _fmt_date(row["exit_date"]),
            })

    log.info("tv_csv_export.done", portfolio_id=portfolio_id, lots=len(rows))
    return buf.getvalue().encode("utf-8")
```

- [ ] **Step 4: Add route to routes.py**

Append to `atlas/tv/routes.py`:

```python
from atlas.tv.csv_export import export_portfolio_csv
from fastapi.responses import Response


@_portfolios_router.get("/{portfolio_id}/tv-export.csv")
def download_portfolio_csv(portfolio_id: str):
    """Download portfolio as TradingView-compatible CSV for manual import."""
    csv_bytes = export_portfolio_csv(portfolio_id)
    if not csv_bytes or csv_bytes.count(b"\n") <= 1:
        raise HTTPException(status_code=404, detail=f"No lots found for portfolio: {portfolio_id}")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=portfolio-{portfolio_id}.csv"},
    )
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/tv/test_csv_export.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add atlas/tv/csv_export.py atlas/tv/routes.py tests/tv/test_csv_export.py
git commit -m "feat(tv): portfolio CSV export in TradingView import format (TV-04)"
```

---

## BLOCKED Tasks (do not implement until unblocked)

### TV-05: TVChartPanel + TVMetricsBadge frontend — BLOCKED

**Blocked by:** Requires `.design-approved.json` before `atlas/tv/` frontend work can proceed (hook enforcement).

**To unblock:** Run `/plan-design-review` for the 36/64 stock detail split layout with TradingView chart iframe on the right and Atlas fundamentals on the left. Once `.design-approved.json` is present, implement:
- `frontend/src/components/v6/TVChartPanel.tsx` — iframe widget wrapper
- `frontend/src/components/v6/TVMetricsBadge.tsx` — RSI/MACD/Recommend badge
- Wire into existing `StockDetailPage` or equivalent

### TV-06: Portfolio Analytics Page — BLOCKED

**Blocked by:** Requires `.design-approved.json`.

**To unblock:** Run `/plan-design-review` for the portfolio analytics page layout. Once approved, implement the page consuming `GET /v1/portfolios/{id}/analytics`.

### TV-05: TVChartPanel + TVMetricsBadge frontend — BLOCKED

**Blocked by:** Requires `.design-approved.json` before `atlas/tv/` frontend work can proceed (hook enforcement).

**To unblock:** Run `/plan-design-review` for the 36/64 stock detail split layout with TradingView chart iframe on the right and Atlas fundamentals on the left. Once `.design-approved.json` is present, implement:
- `frontend/src/components/v6/TVChartPanel.tsx` — iframe widget wrapper
- `frontend/src/components/v6/TVMetricsBadge.tsx` — RSI/MACD/Recommend badge
- Wire into existing `StockDetailPage` or equivalent

### TV-06: Portfolio Analytics Page — BLOCKED

**Blocked by:** Requires `.design-approved.json`.

**To unblock:** Run `/plan-design-review` for the portfolio analytics page layout. Once approved, implement the page consuming `GET /v1/portfolios/{id}/analytics`.

---

## Execution Order Summary

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 (parallel) → Task 6 → Task 7 → Task 8 → Task 9
 117 migration   pkg       screener  metrics route   pg_cron   analytics   analytics route  MCP
```

Tasks 5 and 6 can begin in parallel after Task 4 passes tests.

TV-05, TV-06 are blocked — do not start until `.design-approved.json` exists.
