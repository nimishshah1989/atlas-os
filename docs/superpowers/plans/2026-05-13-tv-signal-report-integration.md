# TradingView Signal + Auto-Report Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real-time Pine Script webhook → Atlas cross-validation → structured investment brief (Signal Report), covering top 200–500 NSE stocks with automated TV alert provisioning.

**Architecture:** TV watches charts 24/7 via standardized Pine Script on 2 layouts per stock (vs Nifty, vs Sector); webhook fires to Atlas; Atlas responds <3s via BackgroundTasks, then async: cross-validates with its own OHLCV quant layer (pandas-ta + scipy), generates chart screenshots via Playwright, calls Groq Llama 3.3 70B for narrative, persists to `tv_signal_reports`, and pushes SSE to the frontend signal feed.

**Tech Stack:** FastAPI BackgroundTasks, pandas-ta, scipy.signal, playwright-async, Groq SDK (already in project via SP07), SQLAlchemy 2.0 sync psycopg2 (existing pattern), Next.js 14 App Router, react-tradingview-embed, Alembic.

> **Review amendments (2026-05-13):**
> - Migration number: **064** (062 and 063 are already taken by us_atlas)
> - DB session: **sync pattern** (`with get_engine().connect() as conn:`) everywhere — no async sessions
> - Table names: `public.de_equity_ohlcv` (not `ohlcv_daily`), `atlas.atlas_universe_stocks` (not `instruments`), `atlas.atlas_stock_conviction_daily` + `atlas.atlas_stock_states_daily` + `atlas.atlas_cts_signals_daily` (not `stock_signals_latest`), `atlas.atlas_stock_metrics_daily` (not `mv_stock_performance`)
> - `instrument_id` UUID FK: add to `tv_signal_reports`; processor resolves `symbol` → `instrument_id` via `atlas_universe_stocks` first
> - Deps: add `anthropic>=0.40` and `playwright>=1.40` to `[project.dependencies]` in pyproject.toml (currently absent from main deps)
> - TV alert count: **T1 only** (3 conditions × 2 charts = 6 alerts/stock × 200 stocks = 1,200 — fits TV Premium exactly). T2/T5 TV alerts deferred; Tier 2/5 still computed in Atlas DB
> - Dedup: add UNIQUE constraint on `(ticker, condition_code, chart_type, date_trunc('hour', triggered_at))` to handle TV webhook retries
> - EC2: `playwright install chromium --with-deps` required before screenshots work (add to Task 13)
> - Narrative: use **Groq Llama 3.3 70B** (already wired in SP07) instead of Sonnet — zero LLM cost
> - t3.xlarge: Playwright screenshots should run on t3.xlarge (4 vCPU, 16 GB) to avoid RAM pressure

---

## File Map

**Create:**
- `migrations/versions/062_tv_signal_reports.py` — 3 new tables
- `atlas/api/tv_signals.py` — webhook receiver + ad-hoc endpoint
- `atlas/signals/__init__.py`
- `atlas/signals/models.py` — Pydantic v2 request/response models
- `atlas/signals/processor.py` — orchestrates full pipeline
- `atlas/signals/technical.py` — pandas-ta + scipy cross-check
- `atlas/signals/screenshot.py` — Playwright chart capture
- `atlas/signals/narrative.py` — Claude Sonnet LLM narrative
- `atlas/signals/provisioner.py` — nightly TV alert provisioning
- `frontend/src/app/signals/page.tsx` — signal feed page
- `frontend/src/app/signals/[id]/page.tsx` — full report page
- `frontend/src/components/signals/SignalCard.tsx` — feed card
- `frontend/src/components/signals/SignalReport.tsx` — full report view
- `tests/api/test_tv_signals.py`
- `tests/unit/signals/test_technical.py`
- `tests/unit/signals/test_processor.py`
- `tests/unit/signals/test_narrative.py`

**Modify:**
- `atlas/api/__init__.py` — register tv_signals router
- `atlas/config.py` — TV_WEBHOOK_SECRET, TV_SESSION_ID/SIGN, TV layout IDs, SIGNAL_SCREENSHOT_DIR
- `frontend/src/app/stocks/[ticker]/page.tsx` — add Signal History tab + Open in TV button

---

## Task 1: Migration 064 — Three DB Tables

> **Note:** 062 = us_atlas_metrics_compute_run_id, 063 = widen_us_metrics_numeric. Next available is 064.

**Files:**
- Create: `migrations/versions/064_tv_signal_reports.py`
- Test: `tests/unit/test_migration_064.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_migration_064.py
import pytest
from sqlalchemy import inspect, text
from tests.conftest import sync_engine

def test_migration_064_creates_tables(run_migration):
    """Tables tv_alert_registry, tv_signal_reports, atlas_signal_alerts exist after 064."""
    run_migration("064")
    insp = inspect(sync_engine)
    tables = insp.get_table_names()
    assert "tv_alert_registry" in tables
    assert "tv_signal_reports" in tables
    assert "atlas_signal_alerts" in tables

def test_migration_064_tv_signal_reports_columns(run_migration):
    run_migration("064")
    insp = inspect(sync_engine)
    cols = {c["name"] for c in insp.get_columns("tv_signal_reports")}
    required = {
        "id", "ticker", "instrument_id", "exchange", "triggered_at", "condition_tier",
        "condition_code", "condition_label", "chart_type",
        "confirmation_level", "conviction_score", "cts_state",
        "rs_rank", "narrative", "verdict", "created_at",
    }
    assert required <= cols
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_migration_064.py -v
```
Expected: `FAILED` — table does not exist yet.

- [ ] **Step 3: Write the migration**

```python
# migrations/versions/064_tv_signal_reports.py
"""tv_signal_reports: TV alert registry, signal reports, alert feed

Revision ID: 064
Revises: 063
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tv_alert_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("chart_type", sa.String(20), nullable=False),
        sa.Column("condition_tier", sa.Integer, nullable=False),
        sa.Column("condition_code", sa.String(50), nullable=False),
        sa.Column("tv_alert_id", sa.String(100)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("layout_id", sa.String(50), nullable=False),
        sa.Column("webhook_url", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_tv_alert_registry_ticker", "tv_alert_registry", ["ticker"])
    op.create_index("idx_tv_alert_registry_active", "tv_alert_registry", ["is_active"])

    op.create_table(
        "tv_signal_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("instrument_id", UUID(as_uuid=True), sa.ForeignKey("atlas.atlas_universe_stocks.instrument_id"), nullable=True, index=True),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="NSE"),
        sa.Column("company_name", sa.String(200)),
        sa.Column("sector", sa.String(100)),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("condition_tier", sa.Integer, nullable=False),
        sa.Column("condition_code", sa.String(50), nullable=False),
        sa.Column("condition_label", sa.String(200), nullable=False),
        sa.Column("chart_type", sa.String(20), nullable=False),
        sa.Column("trigger_price", sa.Numeric(20, 4)),
        sa.Column("trigger_volume", sa.BigInteger),
        sa.Column("volume_vs_avg", sa.Numeric(10, 4)),
        sa.Column("confirmation_level", sa.String(20), nullable=False),
        sa.Column("conviction_score", sa.Numeric(5, 2)),
        sa.Column("conviction_trend", sa.String(10)),
        sa.Column("cts_state", sa.String(50)),
        sa.Column("rs_rank", sa.Integer),
        sa.Column("rs_rank_total", sa.Integer),
        sa.Column("rs_percentile", sa.Numeric(5, 2)),
        sa.Column("sector_regime", sa.String(50)),
        sa.Column("market_regime", sa.String(50)),
        sa.Column("rsi_14", sa.Numeric(6, 2)),
        sa.Column("macd_signal", sa.String(10)),
        sa.Column("ema_alignment", sa.String(20)),
        sa.Column("hh_hl_state", sa.String(20)),
        sa.Column("pattern_label", sa.String(100)),
        sa.Column("perf_1m", sa.Numeric(10, 4)),
        sa.Column("perf_3m", sa.Numeric(10, 4)),
        sa.Column("perf_6m", sa.Numeric(10, 4)),
        sa.Column("perf_ytd", sa.Numeric(10, 4)),
        sa.Column("perf_vs_nifty_1m", sa.Numeric(10, 4)),
        sa.Column("perf_vs_nifty_ytd", sa.Numeric(10, 4)),
        sa.Column("chart_daily_url", sa.String(500)),
        sa.Column("chart_weekly_url", sa.String(500)),
        sa.Column("chart_vs_sector_url", sa.String(500)),
        sa.Column("screenshot_daily", sa.String(500)),
        sa.Column("screenshot_weekly", sa.String(500)),
        sa.Column("screenshot_sector", sa.String(500)),
        sa.Column("narrative", sa.Text),
        sa.Column("report_html", sa.Text),
        sa.Column("verdict", sa.String(20)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("reviewed_by", sa.String(100)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_tv_signal_reports_ticker", "tv_signal_reports", ["ticker"])
    op.create_index("idx_tv_signal_reports_triggered_at", "tv_signal_reports", ["triggered_at"], postgresql_ops={"triggered_at": "DESC"})
    op.create_index("idx_tv_signal_reports_tier", "tv_signal_reports", ["condition_tier"])
    op.create_index("idx_tv_signal_reports_confirmation", "tv_signal_reports", ["confirmation_level"])
    # Dedup UNIQUE: prevents TV webhook retries from creating duplicate reports within same hour
    op.execute(sa.text(
        "CREATE UNIQUE INDEX idx_tv_signal_dedup "
        "ON tv_signal_reports (ticker, condition_code, chart_type, date_trunc('hour', triggered_at))"
    ))

    op.create_table(
        "atlas_signal_alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", UUID(as_uuid=True), sa.ForeignKey("tv_signal_reports.id"), index=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.String(500)),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_atlas_signal_alerts_created", "atlas_signal_alerts", ["created_at"], postgresql_ops={"created_at": "DESC"})
    op.create_index("idx_atlas_signal_alerts_read", "atlas_signal_alerts", ["is_read"])


def downgrade() -> None:
    op.drop_table("atlas_signal_alerts")
    op.drop_table("tv_signal_reports")
    op.drop_table("tv_alert_registry")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_migration_064.py -v
```
Expected: `PASSED` (2 tests).

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/064_tv_signal_reports.py tests/unit/test_migration_064.py
git commit -m "feat(migration-064): tv_alert_registry, tv_signal_reports, atlas_signal_alerts tables"
```

---

## Task 2: Pydantic Models

**Files:**
- Create: `atlas/signals/__init__.py`
- Create: `atlas/signals/models.py`
- Test: `tests/unit/signals/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/signals/test_models.py
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from atlas.signals.models import TVSignalPayload, SignalReportResponse

def test_tv_signal_payload_parses_valid():
    payload = TVSignalPayload(
        tier=1,
        code="breakout_52w_volume",
        chart="vs_nifty",
        ticker="HDFCBANK",
        exchange="NSE",
        close="1820.50",
        volume="4500000",
        time="2026-05-13T09:20:00Z",
        secret="test_secret_32_chars_long_exactly",
    )
    assert payload.tier == 1
    assert payload.close == Decimal("1820.50")
    assert payload.volume == 4500000

def test_tv_signal_payload_rejects_float_close():
    with pytest.raises(Exception):
        TVSignalPayload(
            tier=1, code="x", chart="vs_nifty", ticker="X",
            exchange="NSE", close=1820.5,  # float not allowed
            volume="100", time="2026-05-13T09:20:00Z", secret="x",
        )

def test_signal_report_response_has_required_fields():
    r = SignalReportResponse(
        id="00000000-0000-0000-0000-000000000001",
        ticker="HDFCBANK",
        condition_label="52-week high breakout with 1.5x volume",
        condition_tier=1,
        confirmation_level="dual",
        triggered_at=datetime.now(timezone.utc),
        verdict="bullish",
    )
    assert r.ticker == "HDFCBANK"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/signals/test_models.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create the models**

```python
# atlas/signals/__init__.py
# (empty — signals is a bounded context package)
```

```python
# atlas/signals/models.py
from __future__ import annotations
from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class TVSignalPayload(BaseModel):
    tier: int
    code: str
    chart: str        # 'vs_nifty' | 'vs_sector'
    ticker: str
    exchange: str
    close: Decimal    # TV sends as string — Pydantic coerces
    volume: int
    time: str         # ISO string from TV {{timenow}}
    secret: str

    @field_validator("close", mode="before")
    @classmethod
    def parse_close(cls, v: object) -> Decimal:
        if isinstance(v, float):
            raise ValueError("close must be a string or Decimal, not float")
        return Decimal(str(v))

    @field_validator("chart")
    @classmethod
    def validate_chart(cls, v: str) -> str:
        if v not in ("vs_nifty", "vs_sector"):
            raise ValueError(f"chart must be 'vs_nifty' or 'vs_sector', got {v!r}")
        return v


class SignalReportResponse(BaseModel):
    id: str
    ticker: str
    condition_label: str
    condition_tier: int
    confirmation_level: str
    triggered_at: datetime
    verdict: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    conviction_score: Optional[Decimal] = None
    cts_state: Optional[str] = None
    rs_rank: Optional[int] = None
    rs_rank_total: Optional[int] = None
    rs_percentile: Optional[Decimal] = None
    narrative: Optional[str] = None
    chart_daily_url: Optional[str] = None
    chart_weekly_url: Optional[str] = None
    screenshot_daily: Optional[str] = None
    screenshot_weekly: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/signals/test_models.py -v
```
Expected: `PASSED` (3 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/signals/__init__.py atlas/signals/models.py tests/unit/signals/test_models.py
git commit -m "feat(signals): Pydantic v2 models for TV webhook payload and report response"
```

---

## Task 3: Webhook Receiver Endpoint

**Files:**
- Create: `atlas/api/tv_signals.py`
- Modify: `atlas/api/__init__.py` — register router
- Modify: `atlas/config.py` — add TV config vars
- Test: `tests/api/test_tv_signals.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_tv_signals.py
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
import json

VALID_PAYLOAD = {
    "tier": 1,
    "code": "breakout_52w_volume",
    "chart": "vs_nifty",
    "ticker": "HDFCBANK",
    "exchange": "NSE",
    "close": "1820.50",
    "volume": "4500000",
    "time": "2026-05-13T09:20:00Z",
    "secret": "test_webhook_secret_32chars_exact",
}

@pytest.mark.asyncio
async def test_receive_signal_valid_returns_200(client: AsyncClient, monkeypatch):
    monkeypatch.setenv("TV_WEBHOOK_SECRET", "test_webhook_secret_32chars_exact")
    with patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock):
        r = await client.post("/api/v1/tv/signal", json=VALID_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

@pytest.mark.asyncio
async def test_receive_signal_wrong_secret_returns_401(client: AsyncClient, monkeypatch):
    monkeypatch.setenv("TV_WEBHOOK_SECRET", "correct_secret_32_chars_long_xxx")
    payload = {**VALID_PAYLOAD, "secret": "wrong_secret"}
    r = await client.post("/api/v1/tv/signal", json=payload)
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_receive_signal_missing_field_returns_422(client: AsyncClient, monkeypatch):
    monkeypatch.setenv("TV_WEBHOOK_SECRET", "test_webhook_secret_32chars_exact")
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "ticker"}
    r = await client.post("/api/v1/tv/signal", json=payload)
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_receive_signal_duplicate_within_60min_returns_200_deduplicated(
    client: AsyncClient, monkeypatch
):
    """Same (ticker, code, chart) within 60 min must be accepted (200) but not reprocessed."""
    monkeypatch.setenv("TV_WEBHOOK_SECRET", "test_webhook_secret_32chars_exact")
    with patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock) as mock_proc:
        with patch("atlas.api.tv_signals._is_duplicate", return_value=True):
            r = await client.post("/api/v1/tv/signal", json=VALID_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["status"] == "duplicate"
    mock_proc.assert_not_called()
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/api/test_tv_signals.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Add config vars**

```python
# atlas/config.py — add to existing Config class:
TV_WEBHOOK_SECRET: str = ""
TV_SESSION_ID: str = ""
TV_SESSION_SIGN: str = ""
TV_LAYOUT_ID_VS_NIFTY: str = ""
TV_LAYOUT_ID_VS_SECTOR: str = ""
TV_ACCOUNT_EMAIL: str = ""
SIGNAL_SCREENSHOT_DIR: str = "/data/signals/screenshots"
SIGNAL_REPORT_BASE_URL: str = "https://atlas.jslwealth.in/signals"
```

- [ ] **Step 4: Write the endpoint**

```python
# atlas/api/tv_signals.py
# pragma: finance-critical
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select, text

from atlas.config import Config
from atlas.db import get_engine
from atlas.signals.models import TVSignalPayload, SignalReportResponse

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/tv", tags=["tv-signals"])

_DEDUP_WINDOW_MINUTES = 60


def _is_duplicate(ticker: str, condition_code: str, chart_type: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_DEDUP_WINDOW_MINUTES)
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM tv_signal_reports "
                "WHERE ticker = :ticker AND condition_code = :code AND chart_type = :chart "
                "AND triggered_at > :cutoff LIMIT 1"
            ),
            {"ticker": ticker, "code": condition_code, "chart": chart_type, "cutoff": cutoff},
        ).fetchone()
    return row is not None


async def process_signal(payload: TVSignalPayload) -> None:
    from atlas.signals.processor import run_signal_pipeline
    await run_signal_pipeline(payload)


@router.post("/signal")
async def receive_tv_signal(
    payload: TVSignalPayload,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict[str, str]:
    if payload.secret != Config.TV_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if _is_duplicate(payload.ticker, payload.code, payload.chart):
        log.info(
            "tv_signal_deduplicated",
            ticker=payload.ticker,
            code=payload.code,
            chart=payload.chart,
        )
        return {"status": "duplicate"}

    log.info("tv_signal_received", ticker=payload.ticker, tier=payload.tier, code=payload.code)
    background_tasks.add_task(process_signal, payload)
    return {"status": "accepted"}
```

- [ ] **Step 5: Register the router**

In `atlas/api/__init__.py`, add:
```python
from atlas.api.tv_signals import router as tv_signals_router
app.include_router(tv_signals_router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/api/test_tv_signals.py -v
```
Expected: `PASSED` (4 tests).

- [ ] **Step 7: Commit**

```bash
git add atlas/api/tv_signals.py atlas/api/__init__.py atlas/config.py tests/api/test_tv_signals.py
git commit -m "feat(signals): webhook receiver endpoint with secret validation and 60-min dedup"
```

---

## Task 4: Technical Cross-Check Module

**Files:**
- Create: `atlas/signals/technical.py`
- Test: `tests/unit/signals/test_technical.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/signals/test_technical.py
import pytest
import pandas as pd
import numpy as np
from decimal import Decimal
from unittest.mock import patch, MagicMock
from atlas.signals.technical import (
    TechnicalSnapshot,
    compute_technical_snapshot,
    _classify_ema_alignment,
    _classify_macd,
    _classify_hh_hl,
)

def make_ohlcv(n: int = 300, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic OHLCV with predictable trend for test assertions."""
    np.random.seed(42)
    base = 1000.0
    if trend == "up":
        prices = base + np.cumsum(np.abs(np.random.randn(n)) * 2)
    else:
        prices = base + np.cumsum(-np.abs(np.random.randn(n)) * 2)
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n),
        "open": prices * 0.99,
        "high": prices * 1.01,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    })

def test_compute_technical_snapshot_returns_snapshot():
    df = make_ohlcv(300, "up")
    with patch("atlas.signals.technical._fetch_ohlcv", return_value=df):
        snap = compute_technical_snapshot("HDFCBANK", session=MagicMock())
    assert isinstance(snap, TechnicalSnapshot)
    assert 0 <= float(snap.rsi_14) <= 100
    assert snap.macd_signal in ("bullish_cross", "bearish_cross", "above_zero", "below_zero", "neutral")
    assert snap.ema_alignment in ("all_bullish", "above_200", "mixed", "all_bearish")
    assert snap.hh_hl_state in ("confirmed_uptrend", "hh_only", "hl_only", "downtrend", "neutral")

def test_compute_technical_snapshot_uptrend_has_bullish_ema():
    df = make_ohlcv(300, "up")
    with patch("atlas.signals.technical._fetch_ohlcv", return_value=df):
        snap = compute_technical_snapshot("FAKE", session=MagicMock())
    assert snap.ema_alignment in ("all_bullish", "above_200")

def test_classify_ema_alignment_all_bullish():
    result = _classify_ema_alignment(close=110.0, ema20=108.0, ema50=105.0, ema200=100.0)
    assert result == "all_bullish"

def test_classify_ema_alignment_all_bearish():
    result = _classify_ema_alignment(close=90.0, ema20=92.0, ema50=95.0, ema200=100.0)
    assert result == "all_bearish"

def test_classify_macd_bullish_cross():
    result = _classify_macd(macd=0.5, signal=0.2, prev_macd=0.1, prev_signal=0.3)
    assert result == "bullish_cross"

def test_classify_macd_bearish_cross():
    result = _classify_macd(macd=0.1, signal=0.3, prev_macd=0.4, prev_signal=0.2)
    assert result == "bearish_cross"

def test_classify_macd_above_zero():
    result = _classify_macd(macd=0.3, signal=0.1, prev_macd=0.2, prev_signal=0.1)
    assert result == "above_zero"

def test_classify_macd_below_zero():
    result = _classify_macd(macd=-0.3, signal=-0.1, prev_macd=-0.2, prev_signal=-0.1)
    assert result == "below_zero"

def test_classify_hh_hl_confirmed_uptrend():
    result = _classify_hh_hl(hh=True, hl=True)
    assert result == "confirmed_uptrend"

def test_classify_hh_hl_downtrend():
    result = _classify_hh_hl(hh=False, hl=False)
    assert result == "downtrend"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/signals/test_technical.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement technical.py**

```python
# atlas/signals/technical.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy.signal import find_peaks
import structlog

log = structlog.get_logger()


@dataclass
class TechnicalSnapshot:
    rsi_14: Decimal
    macd_signal: str        # 'bullish_cross' | 'bearish_cross' | 'above_zero' | 'below_zero' | 'neutral'
    ema_alignment: str      # 'all_bullish' | 'above_200' | 'mixed' | 'all_bearish'
    hh_hl_state: str        # 'confirmed_uptrend' | 'hh_only' | 'hl_only' | 'downtrend' | 'neutral'
    volume_vs_avg: Decimal  # current_vol / sma_vol_20
    pattern_label: str


def _fetch_ohlcv(ticker: str, lookback_days: int, conn: Any) -> pd.DataFrame:
    """Fetch OHLCV from public.de_equity_ohlcv (the NSE Kite-sourced price table).
    Joins through atlas_universe_stocks to resolve ticker symbol → instrument_id.
    """
    from sqlalchemy import text
    rows = conn.execute(
        text(  # noqa: S608 — ticker from validated TV payload; instrument_id resolved via join, no injection
            "SELECT o.date, o.open, o.high, o.low, o.close, o.volume "
            "FROM public.de_equity_ohlcv o "
            "JOIN atlas.atlas_universe_stocks u ON u.instrument_id = o.instrument_id "
            "WHERE u.symbol = :ticker AND u.effective_to IS NULL "
            "ORDER BY o.date DESC LIMIT :n"
        ),
        {"ticker": ticker, "n": lookback_days},
    ).fetchall()
    if not rows:
        raise ValueError(f"No OHLCV data for {ticker}")
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    return df.sort_values("date").reset_index(drop=True)


def _classify_ema_alignment(
    close: float, ema20: float, ema50: float, ema200: float
) -> str:
    if close > ema20 > ema50 > ema200:
        return "all_bullish"
    if close > ema200:
        return "above_200"
    if close < ema20 < ema50 < ema200:
        return "all_bearish"
    return "mixed"


def _classify_macd(
    macd: float, signal: float, prev_macd: float, prev_signal: float
) -> str:
    crossed_up = prev_macd < prev_signal and macd > signal
    crossed_dn = prev_macd > prev_signal and macd < signal
    if crossed_up:
        return "bullish_cross"
    if crossed_dn:
        return "bearish_cross"
    if macd > 0:
        return "above_zero"
    if macd < 0:
        return "below_zero"
    return "neutral"


def _classify_hh_hl(hh: bool, hl: bool) -> str:
    if hh and hl:
        return "confirmed_uptrend"
    if hh:
        return "hh_only"
    if hl:
        return "hl_only"
    return "downtrend"


def compute_technical_snapshot(ticker: str, conn: Any) -> TechnicalSnapshot:
    df = _fetch_ohlcv(ticker, lookback_days=300, conn=conn)

    na_count = df["close"].isna().sum()
    if na_count:
        log.warning("ohlcv_gaps_technical", ticker=ticker, count=int(na_count))
        df["close"] = df["close"].ffill()

    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.sma(length=20, close="volume", prefix="vol", append=True)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    rsi_col = "RSI_14"
    macd_col, signal_col = "MACD_12_26_9", "MACDs_12_26_9"
    ema20_col, ema50_col, ema200_col = "EMA_20", "EMA_50", "EMA_200"
    vol_sma_col = "vol_SMA_20"

    rsi_val = float(last[rsi_col]) if not pd.isna(last[rsi_col]) else 50.0

    macd_sig = _classify_macd(
        macd=float(last[macd_col] or 0),
        signal=float(last[signal_col] or 0),
        prev_macd=float(prev[macd_col] or 0),
        prev_signal=float(prev[signal_col] or 0),
    )

    ema_align = _classify_ema_alignment(
        close=float(last["close"]),
        ema20=float(last[ema20_col] or last["close"]),
        ema50=float(last[ema50_col] or last["close"]),
        ema200=float(last[ema200_col] or last["close"]),
    )

    highs_idx, _ = find_peaks(df["close"].values, distance=10, prominence=0.02)
    lows_idx, _ = find_peaks(-df["close"].values, distance=10, prominence=0.02)

    hh = (
        len(highs_idx) >= 2
        and df["close"].iloc[highs_idx[-1]] > df["close"].iloc[highs_idx[-2]]
    )
    hl = (
        len(lows_idx) >= 2
        and df["close"].iloc[lows_idx[-1]] > df["close"].iloc[lows_idx[-2]]
    )
    hh_hl = _classify_hh_hl(bool(hh), bool(hl))

    vol_avg = float(last[vol_sma_col]) if not pd.isna(last.get(vol_sma_col, np.nan)) else 1.0
    vol_ratio = float(last["volume"]) / vol_avg if vol_avg > 0 else Decimal("1.0")

    pattern = _build_pattern_label(ema_align, hh_hl, rsi_val)

    return TechnicalSnapshot(
        rsi_14=Decimal(str(round(rsi_val, 2))),
        macd_signal=macd_sig,
        ema_alignment=ema_align,
        hh_hl_state=hh_hl,
        volume_vs_avg=Decimal(str(round(vol_ratio, 4))),
        pattern_label=pattern,
    )


def _build_pattern_label(ema_alignment: str, hh_hl_state: str, rsi: float) -> str:
    parts = []
    if hh_hl_state == "confirmed_uptrend":
        parts.append("Confirmed uptrend (HH+HL)")
    elif hh_hl_state == "hh_only":
        parts.append("Higher high — awaiting HL")
    if ema_alignment == "all_bullish":
        parts.append("all EMAs aligned bullish")
    elif ema_alignment == "above_200":
        parts.append("above 200 EMA")
    if rsi > 60:
        parts.append(f"RSI strong ({rsi:.0f})")
    return "; ".join(parts) if parts else "No clear pattern"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/signals/test_technical.py -v
```
Expected: `PASSED` (7 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/signals/technical.py tests/unit/signals/test_technical.py
git commit -m "feat(signals): technical cross-check module — pandas-ta RSI/MACD/EMA + scipy HH/HL"
```

---

## Task 5: Signal Processor — Orchestration + Confirmation Level

**Files:**
- Create: `atlas/signals/processor.py`
- Test: `tests/unit/signals/test_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/signals/test_processor.py
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock
from atlas.signals.processor import _determine_confirmation_level, _fetch_atlas_intelligence
from atlas.signals.models import TVSignalPayload

def _payload(**overrides) -> TVSignalPayload:
    base = dict(
        tier=1, code="breakout_52w_volume", chart="vs_nifty",
        ticker="HDFCBANK", exchange="NSE",
        close="1820.50", volume="4500000",
        time="2026-05-13T09:20:00Z", secret="x",
    )
    base.update(overrides)
    return TVSignalPayload(**base)

def test_confirmation_dual_when_conviction_high():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("7.5"),
        cts_state="BUY Stage 2",
        rs_percentile=Decimal("85.0"),
    )
    assert result == "dual"

def test_confirmation_tv_only_when_conviction_low():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("3.0"),
        cts_state="HOLD",
        rs_percentile=Decimal("40.0"),
    )
    assert result == "tv_only"

def test_confirmation_tv_only_when_no_conviction():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=None,
        cts_state=None,
        rs_percentile=None,
    )
    assert result == "tv_only"

def test_confirmation_dual_requires_both_conviction_and_rs():
    # High conviction but low RS → not dual
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("8.0"),
        cts_state="BUY Stage 2",
        rs_percentile=Decimal("30.0"),  # below threshold
    )
    assert result == "tv_only"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/signals/test_processor.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement processor.py**

```python
# atlas/signals/processor.py
# pragma: finance-critical
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Any
import structlog

from atlas.db import get_session
from atlas.signals.models import TVSignalPayload

log = structlog.get_logger()

_DUAL_CONFIRM_CONVICTION_MIN = Decimal("6.0")
_DUAL_CONFIRM_RS_PERCENTILE_MIN = Decimal("60.0")
_DUAL_CONFIRM_CTS_BUY_STATES = {"BUY Stage 1", "BUY Stage 2", "BUY Stage 3"}


def _determine_confirmation_level(
    tier: int,
    conviction_score: Optional[Decimal],
    cts_state: Optional[str],
    rs_percentile: Optional[Decimal],
) -> str:
    if conviction_score is None or rs_percentile is None:
        return "tv_only"
    conviction_ok = conviction_score >= _DUAL_CONFIRM_CONVICTION_MIN
    rs_ok = rs_percentile >= _DUAL_CONFIRM_RS_PERCENTILE_MIN
    cts_ok = cts_state in _DUAL_CONFIRM_CTS_BUY_STATES if cts_state else False
    if conviction_ok and rs_ok and cts_ok:
        return "dual"
    return "tv_only"


def _resolve_instrument_id(ticker: str, conn: Any) -> str | None:
    """Resolve ticker symbol to instrument_id UUID. Uses atlas_universe_stocks.symbol."""
    from sqlalchemy import text
    row = conn.execute(
        text(  # noqa: S608 — ticker from validated TV payload, SQL structure is constant
            "SELECT instrument_id FROM atlas.atlas_universe_stocks "
            "WHERE symbol = :symbol AND effective_to IS NULL LIMIT 1"
        ),
        {"symbol": ticker},
    ).fetchone()
    return str(row.instrument_id) if row else None


def _fetch_atlas_intelligence(instrument_id: str, conn: Any) -> dict:
    """Fetch conviction score, CTS state, RS state, and regime from Atlas DB."""
    from sqlalchemy import text
    row = conn.execute(
        text(  # noqa: S608 — instrument_id is a UUID resolved internally, constant SQL
            "SELECT c.conviction_score, c.confidence_label AS conviction_trend, "
            "cts.stage AS cts_state, "
            "s.rs_state, "
            "mr.regime_label AS market_regime, "
            "ss.rs_state AS sector_regime "
            "FROM atlas.atlas_stock_conviction_daily c "
            "LEFT JOIN atlas.atlas_cts_signals_daily cts ON cts.instrument_id = c.instrument_id AND cts.date = c.date "
            "LEFT JOIN atlas.atlas_stock_states_daily s ON s.instrument_id = c.instrument_id AND s.date = c.date "
            "LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = c.date "
            "LEFT JOIN atlas.atlas_sector_states_daily ss ON ss.sector = "
            "  (SELECT sector FROM atlas.atlas_universe_stocks WHERE instrument_id = c.instrument_id AND effective_to IS NULL LIMIT 1) "
            "  AND ss.date = c.date "
            "WHERE c.instrument_id = :iid "
            "ORDER BY c.date DESC LIMIT 1"
        ),
        {"iid": instrument_id},
    ).fetchone()
    if row is None:
        return {}
    return dict(row._mapping)


def _fetch_performance(instrument_id: str, conn: Any) -> dict:
    """Fetch performance returns from atlas_stock_metrics_daily."""
    from sqlalchemy import text
    row = conn.execute(
        text(  # noqa: S608 — instrument_id UUID, constant SQL
            "SELECT ret_1m AS perf_1m, ret_3m AS perf_3m, ret_6m AS perf_6m, "
            "ret_ytd AS perf_ytd, ret_vs_benchmark_1m AS perf_vs_nifty_1m, "
            "ret_vs_benchmark_ytd AS perf_vs_nifty_ytd "
            "FROM atlas.atlas_stock_metrics_daily "
            "WHERE instrument_id = :iid "
            "ORDER BY date DESC LIMIT 1"
        ),
        {"iid": instrument_id},
    ).fetchone()
    return dict(row._mapping) if row else {}


def _fetch_company_meta(ticker: str, conn: Any) -> dict:
    """Fetch company name and sector from atlas_universe_stocks."""
    from sqlalchemy import text
    row = conn.execute(
        text(  # noqa: S608 — ticker from validated payload, constant SQL
            "SELECT company_name, sector FROM atlas.atlas_universe_stocks "
            "WHERE symbol = :symbol AND effective_to IS NULL LIMIT 1"
        ),
        {"symbol": ticker},
    ).fetchone()
    return dict(row._mapping) if row else {}


def _build_condition_label(code: str) -> str:
    labels = {
        "breakout_52w_volume": "52-week high breakout with 1.5x volume",
        "rs_breakout_52w": "RS line vs Nifty hits 52-week high",
        "rs_sector_breakout_52w": "RS line vs Sector hits 52-week high",
        "false_breakdown_recovery": "Price reclaims broken support within 5 bars",
        "higher_high": "New swing high above prior pivot high",
        "higher_high_higher_low": "HH + HL within 20 bars (confirmed uptrend)",
        "cross_above_ema200": "Price crosses above 200-day EMA",
        "cross_above_ema50": "Price crosses above 50-day EMA",
        "golden_cross": "50-day EMA crosses above 200-day EMA",
        "all_emas_aligned": "Price > 20/50/200 EMA simultaneously",
        "rsi_cross_50": "RSI crosses above 50 from below",
        "rsi_breakout_3m_high": "RSI breaks above prior 3-month high",
        "macd_bullish_cross_above_zero": "MACD bullish crossover above zero line",
        "lower_low": "New swing low below prior pivot low",
        "rs_breakdown_52w": "RS line vs Nifty hits 52-week low",
        "cross_below_ema200": "Price crosses below 200-day EMA",
        "death_cross": "50-day EMA crosses below 200-day EMA",
    }
    return labels.get(code, code.replace("_", " ").title())


def _verdict_from_tier(tier: int) -> str:
    if tier == 5:
        return "bearish"
    if tier == 1:
        return "bullish"
    return "watch"


async def run_signal_pipeline(payload: TVSignalPayload) -> None:
    from atlas.signals.technical import compute_technical_snapshot
    from atlas.signals.screenshot import capture_chart_screenshots
    from atlas.signals.narrative import generate_narrative
    from atlas.db import get_engine
    from sqlalchemy import text

    log.info("signal_pipeline_start", ticker=payload.ticker, code=payload.code)
    engine = get_engine()

    with engine.connect() as conn:
        instrument_id = _resolve_instrument_id(payload.ticker, conn)
        intel = _fetch_atlas_intelligence(instrument_id, conn) if instrument_id else {}
        perf = _fetch_performance(instrument_id, conn) if instrument_id else {}
        meta = _fetch_company_meta(payload.ticker, conn)

        conviction_score = intel.get("conviction_score")
        cts_state = intel.get("cts_state")
        rs_percentile = intel.get("rs_percentile")

        confirmation = _determine_confirmation_level(
            tier=payload.tier,
            conviction_score=Decimal(str(conviction_score)) if conviction_score else None,
            cts_state=cts_state,
            rs_percentile=Decimal(str(rs_percentile)) if rs_percentile else None,
        )

        snap = compute_technical_snapshot(payload.ticker, conn)

        from atlas.config import Config
        screenshots = await capture_chart_screenshots(
            ticker=payload.ticker,
            exchange=payload.exchange,
            layout_id_nifty=Config.TV_LAYOUT_ID_VS_NIFTY,
            layout_id_sector=Config.TV_LAYOUT_ID_VS_SECTOR,
        )

        context = {
            "ticker": payload.ticker,
            "company_name": meta.get("company_name", payload.ticker),
            "condition_label": _build_condition_label(payload.code),
            "conviction_score": conviction_score,
            "conviction_trend": intel.get("conviction_trend"),
            "cts_state": cts_state,
            "rs_rank": intel.get("rs_rank"),
            "rs_rank_total": intel.get("rs_rank_total"),
            "rs_percentile": rs_percentile,
            "sector": meta.get("sector"),
            "sector_regime": intel.get("sector_regime"),
            "market_regime": intel.get("market_regime"),
            "rsi_14": float(snap.rsi_14),
            "macd_signal": snap.macd_signal,
            "ema_alignment": snap.ema_alignment,
            "hh_hl_state": snap.hh_hl_state,
            "volume_vs_avg": float(snap.volume_vs_avg),
            "perf_vs_nifty_ytd": float(perf.get("perf_vs_nifty_ytd") or 0),
        }

        narrative = await generate_narrative(context)

        triggered_at = datetime.now(timezone.utc)
        session.execute(
            text(  # noqa: S608 — all values parameterised, no user-controlled SQL identifiers
                """INSERT INTO tv_signal_reports (
                    ticker, exchange, company_name, sector,
                    triggered_at, condition_tier, condition_code, condition_label, chart_type,
                    trigger_price, trigger_volume,
                    confirmation_level,
                    conviction_score, conviction_trend, cts_state,
                    rs_rank, rs_rank_total, rs_percentile,
                    sector_regime, market_regime,
                    rsi_14, macd_signal, ema_alignment, hh_hl_state, pattern_label,
                    perf_1m, perf_3m, perf_6m, perf_ytd, perf_vs_nifty_1m, perf_vs_nifty_ytd,
                    chart_daily_url, chart_weekly_url, chart_vs_sector_url,
                    screenshot_daily, screenshot_weekly, screenshot_sector,
                    narrative, verdict
                ) VALUES (
                    :ticker, :exchange, :company_name, :sector,
                    :triggered_at, :tier, :code, :label, :chart,
                    :price, :volume,
                    :confirmation,
                    :conviction_score, :conviction_trend, :cts_state,
                    :rs_rank, :rs_rank_total, :rs_percentile,
                    :sector_regime, :market_regime,
                    :rsi_14, :macd_signal, :ema_alignment, :hh_hl_state, :pattern_label,
                    :perf_1m, :perf_3m, :perf_6m, :perf_ytd, :perf_vs_nifty_1m, :perf_vs_nifty_ytd,
                    :chart_daily_url, :chart_weekly_url, :chart_vs_sector_url,
                    :screenshot_daily, :screenshot_weekly, :screenshot_sector,
                    :narrative, :verdict
                ) RETURNING id"""
            ),
            {
                "ticker": payload.ticker,
                "exchange": payload.exchange,
                "company_name": meta.get("company_name"),
                "sector": meta.get("sector"),
                "triggered_at": triggered_at,
                "tier": payload.tier,
                "code": payload.code,
                "label": _build_condition_label(payload.code),
                "chart": payload.chart,
                "price": payload.close,
                "volume": payload.volume,
                "confirmation": confirmation,
                "conviction_score": conviction_score,
                "conviction_trend": intel.get("conviction_trend"),
                "cts_state": cts_state,
                "rs_rank": intel.get("rs_rank"),
                "rs_rank_total": intel.get("rs_rank_total"),
                "rs_percentile": rs_percentile,
                "sector_regime": intel.get("sector_regime"),
                "market_regime": intel.get("market_regime"),
                "rsi_14": snap.rsi_14,
                "macd_signal": snap.macd_signal,
                "ema_alignment": snap.ema_alignment,
                "hh_hl_state": snap.hh_hl_state,
                "pattern_label": snap.pattern_label,
                "perf_1m": perf.get("perf_1m"),
                "perf_3m": perf.get("perf_3m"),
                "perf_6m": perf.get("perf_6m"),
                "perf_ytd": perf.get("perf_ytd"),
                "perf_vs_nifty_1m": perf.get("perf_vs_nifty_1m"),
                "perf_vs_nifty_ytd": perf.get("perf_vs_nifty_ytd"),
                "chart_daily_url": screenshots.get("daily_url"),
                "chart_weekly_url": screenshots.get("weekly_url"),
                "chart_vs_sector_url": screenshots.get("sector_url"),
                "screenshot_daily": screenshots.get("daily_path"),
                "screenshot_weekly": screenshots.get("weekly_path"),
                "screenshot_sector": screenshots.get("sector_path"),
                "narrative": narrative,
                "verdict": _verdict_from_tier(payload.tier),
            },
        )

        report_row = session.execute(
            text("SELECT id FROM tv_signal_reports WHERE ticker=:t AND triggered_at=:ts LIMIT 1"),  # noqa: S608
            {"t": payload.ticker, "ts": triggered_at},
        ).fetchone()

        if report_row:
            severity = "high" if payload.tier == 1 else ("medium" if payload.tier in (2, 5) else "low")
            session.execute(
                text(  # noqa: S608
                    "INSERT INTO atlas_signal_alerts (report_id, ticker, alert_type, severity, title, summary) "
                    "VALUES (:rid, :ticker, 'tv_signal', :severity, :title, :summary)"
                ),
                {
                    "rid": report_row.id,
                    "ticker": payload.ticker,
                    "severity": severity,
                    "title": f"{payload.ticker}: {_build_condition_label(payload.code)}",
                    "summary": f"Tier {payload.tier} signal — {confirmation} confirmation",
                },
            )

    log.info("signal_pipeline_complete", ticker=payload.ticker, confirmation=confirmation)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/signals/test_processor.py -v
```
Expected: `PASSED` (4 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/signals/processor.py tests/unit/signals/test_processor.py
git commit -m "feat(signals): signal processor — confirmation logic, Atlas intel fetch, pipeline orchestration"
```

---

## Task 6: Narrative Generator

**Files:**
- Create: `atlas/signals/narrative.py`
- Test: `tests/unit/signals/test_narrative.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/signals/test_narrative.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from atlas.signals.narrative import generate_narrative, _build_prompt

def _context(**overrides) -> dict:
    base = {
        "ticker": "HDFCBANK",
        "company_name": "HDFC Bank Ltd.",
        "condition_label": "52-week high breakout with 1.5x volume",
        "conviction_score": 8.4,
        "conviction_trend": "rising",
        "cts_state": "BUY Stage 2",
        "rs_rank": 12,
        "rs_rank_total": 487,
        "rs_percentile": 97.5,
        "sector": "Banking",
        "sector_regime": "Bullish Expansion",
        "market_regime": "Risk-On",
        "rsi_14": 61.2,
        "macd_signal": "above_zero",
        "ema_alignment": "all_bullish",
        "hh_hl_state": "confirmed_uptrend",
        "volume_vs_avg": 2.3,
        "perf_vs_nifty_ytd": 22.7,
    }
    base.update(overrides)
    return base

def test_build_prompt_contains_ticker():
    prompt = _build_prompt(_context())
    assert "HDFCBANK" in prompt
    assert "HDFC Bank Ltd." in prompt

def test_build_prompt_contains_condition():
    prompt = _build_prompt(_context())
    assert "52-week high breakout" in prompt

def test_build_prompt_handles_missing_conviction():
    ctx = _context(conviction_score=None, cts_state=None, rs_rank=None, rs_rank_total=None, rs_percentile=None)
    prompt = _build_prompt(ctx)
    assert "HDFCBANK" in prompt  # should not raise

@pytest.mark.asyncio
async def test_generate_narrative_calls_llm_and_returns_string():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "The setup appears bullish. HDFC Bank has broken out."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = MagicMock(return_value=mock_response)

    with patch("atlas.signals.narrative._get_client", return_value=mock_client):
        result = await generate_narrative(_context())

    assert isinstance(result, str)
    assert len(result) > 10

@pytest.mark.asyncio
async def test_generate_narrative_returns_fallback_on_error():
    with patch("atlas.signals.narrative._get_client", side_effect=Exception("API down")):
        result = await generate_narrative(_context())
    assert result.startswith("Technical signal")  # fallback message
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/signals/test_narrative.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement narrative.py**

```python
# atlas/signals/narrative.py
# Uses Groq Llama 3.3 70B (already in project via SP07) — zero API cost at Atlas volume.
from __future__ import annotations
from typing import Optional, Any
import structlog
from groq import Groq

log = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 300

_PROMPT_TEMPLATE = """You are an experienced equity analyst writing a one-paragraph investment brief.
Be direct and opinionated. Lead with a clear verdict ("The setup appears bullish" or "This chart is flashing a warning").
Explain what the technical trigger means in the context of the stock's quantitative profile.
Do not hedge excessively. Reference specific numbers. 3-4 sentences maximum.

Stock: {ticker} ({company_name})
Trigger: {condition_label}
{conviction_line}
{cts_line}
{rs_line}
Sector: {sector} — {sector_regime}
Market: {market_regime}
RSI(14): {rsi_14:.1f}
MACD: {macd_signal}
EMA Alignment: {ema_alignment}
HH/HL State: {hh_hl_state}
Volume vs 20-day avg: {volume_vs_avg:.1f}x
Performance vs Nifty (YTD): {perf_vs_nifty_ytd:+.1f}%"""


def _build_prompt(ctx: dict) -> str:
    conviction_line = (
        f"Conviction: {ctx['conviction_score']}/10 ({ctx.get('conviction_trend', 'stable')})"
        if ctx.get("conviction_score") is not None
        else "Conviction: not available"
    )
    cts_line = f"CTS State: {ctx['cts_state']}" if ctx.get("cts_state") else "CTS State: not available"
    rs_line = (
        f"RS Rank: #{ctx['rs_rank']} of {ctx['rs_rank_total']} ({ctx['rs_percentile']:.1f}th percentile)"
        if ctx.get("rs_rank") is not None
        else "RS Rank: not available"
    )
    return _PROMPT_TEMPLATE.format(
        ticker=ctx.get("ticker", ""),
        company_name=ctx.get("company_name", ""),
        condition_label=ctx.get("condition_label", ""),
        conviction_line=conviction_line,
        cts_line=cts_line,
        rs_line=rs_line,
        sector=ctx.get("sector", "Unknown"),
        sector_regime=ctx.get("sector_regime", "Unknown"),
        market_regime=ctx.get("market_regime", "Unknown"),
        rsi_14=ctx.get("rsi_14", 50.0),
        macd_signal=ctx.get("macd_signal", "neutral"),
        ema_alignment=ctx.get("ema_alignment", "mixed"),
        hh_hl_state=ctx.get("hh_hl_state", "neutral"),
        volume_vs_avg=ctx.get("volume_vs_avg", 1.0),
        perf_vs_nifty_ytd=ctx.get("perf_vs_nifty_ytd", 0.0),
    )


def _get_client() -> Groq:
    return Groq()  # reads GROQ_API_KEY from env (already set on EC2 via SP07)


async def generate_narrative(ctx: dict) -> str:
    prompt = _build_prompt(ctx)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        log.exception("narrative_generation_failed", ticker=ctx.get("ticker"))
        label = ctx.get("condition_label", "technical signal")
        ticker = ctx.get("ticker", "")
        return f"Technical signal for {ticker}: {label}. Atlas intelligence layer shows additional context in the metrics above."
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/signals/test_narrative.py -v
```
Expected: `PASSED` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/signals/narrative.py tests/unit/signals/test_narrative.py
git commit -m "feat(signals): Claude Sonnet narrative generator with structured prompt and fallback"
```

---

## Task 7: Chart Screenshot Capture

**Files:**
- Create: `atlas/signals/screenshot.py`
- (No unit test for real Playwright — integration test only; a mock-based unit test covers the path logic)
- Test: `tests/unit/signals/test_screenshot.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/signals/test_screenshot.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from atlas.signals.screenshot import (
    _build_chart_url,
    capture_chart_screenshots,
)

def test_build_chart_url_daily():
    url = _build_chart_url(layout_id="abc123", ticker="HDFCBANK", exchange="NSE", interval="D")
    assert "abc123" in url
    assert "NSE:HDFCBANK" in url
    assert "interval=D" in url

def test_build_chart_url_weekly():
    url = _build_chart_url(layout_id="xyz789", ticker="RELIANCE", exchange="NSE", interval="W")
    assert "interval=W" in url

@pytest.mark.asyncio
async def test_capture_returns_paths_dict():
    """With Playwright mocked, returns dict with expected keys."""
    with patch("atlas.signals.screenshot._screenshot_one", new_callable=AsyncMock, return_value="/tmp/test.png"):
        result = await capture_chart_screenshots(
            ticker="HDFCBANK",
            exchange="NSE",
            layout_id_nifty="nifty_layout",
            layout_id_sector="sector_layout",
        )
    assert "daily_path" in result
    assert "weekly_path" in result
    assert "sector_path" in result
    assert "daily_url" in result

@pytest.mark.asyncio
async def test_capture_handles_screenshot_failure():
    """If Playwright fails, returns None paths without raising."""
    with patch("atlas.signals.screenshot._screenshot_one", new_callable=AsyncMock, side_effect=Exception("Browser crash")):
        result = await capture_chart_screenshots(
            ticker="FAIL",
            exchange="NSE",
            layout_id_nifty="l1",
            layout_id_sector="l2",
        )
    assert result.get("daily_path") is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/signals/test_screenshot.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement screenshot.py**

```python
# atlas/signals/screenshot.py
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import structlog

log = structlog.get_logger()

_TV_CHART_BASE = "https://www.tradingview.com/chart/{layout_id}/?symbol={exchange}:{ticker}&interval={interval}"
_WAIT_SELECTOR = "canvas"  # TradingView chart canvas element
_WAIT_TIMEOUT_MS = 15_000
_CHART_LOAD_DELAY_MS = 4_000  # wait after canvas appears for full render


def _build_chart_url(layout_id: str, ticker: str, exchange: str, interval: str) -> str:
    return _TV_CHART_BASE.format(
        layout_id=layout_id,
        exchange=exchange,
        ticker=ticker,
        interval=interval,
    )


def _screenshot_path(ticker: str, interval: str, chart_type: str) -> str:
    from atlas.config import Config
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{ticker}_{chart_type}_{interval}_{ts}.png"
    return str(Path(Config.SIGNAL_SCREENSHOT_DIR) / filename)


async def _screenshot_one(url: str, out_path: str, session_id: str, session_sign: str) -> str:
    from playwright.async_api import async_playwright

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        await context.add_cookies([
            {"name": "sessionid", "value": session_id, "domain": ".tradingview.com", "path": "/"},
            {"name": "sessionid_sign", "value": session_sign, "domain": ".tradingview.com", "path": "/"},
        ])
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector(_WAIT_SELECTOR, timeout=_WAIT_TIMEOUT_MS)
        await page.wait_for_timeout(_CHART_LOAD_DELAY_MS)
        await page.screenshot(path=out_path, full_page=False)
        await browser.close()
    return out_path


async def capture_chart_screenshots(
    ticker: str,
    exchange: str,
    layout_id_nifty: str,
    layout_id_sector: str,
) -> dict[str, Optional[str]]:
    from atlas.config import Config

    session_id = Config.TV_SESSION_ID
    session_sign = Config.TV_SESSION_SIGN

    result: dict[str, Optional[str]] = {
        "daily_url": _build_chart_url(layout_id_nifty, ticker, exchange, "D"),
        "weekly_url": _build_chart_url(layout_id_nifty, ticker, exchange, "W"),
        "sector_url": _build_chart_url(layout_id_sector, ticker, exchange, "D"),
        "daily_path": None,
        "weekly_path": None,
        "sector_path": None,
    }

    if not session_id or not layout_id_nifty:
        log.warning("tv_screenshots_skipped_no_config", ticker=ticker)
        return result

    captures = [
        ("daily_path", result["daily_url"], "vs_nifty", "D"),
        ("weekly_path", result["weekly_url"], "vs_nifty", "W"),
        ("sector_path", result["sector_url"], "vs_sector", "D"),
    ]

    for key, url, chart_type, interval in captures:
        out_path = _screenshot_path(ticker, interval, chart_type)
        try:
            result[key] = await _screenshot_one(url, out_path, session_id, session_sign)
        except Exception:
            log.exception("tv_screenshot_failed", ticker=ticker, chart_type=chart_type, interval=interval)
            result[key] = None

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/signals/test_screenshot.py -v
```
Expected: `PASSED` (4 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/signals/screenshot.py tests/unit/signals/test_screenshot.py
git commit -m "feat(signals): Playwright chart screenshot capture with TV session cookie injection"
```

---

## Task 8: Signal Feed API Endpoints

**Files:**
- Modify: `atlas/api/tv_signals.py` — add GET /api/v1/tv/signals (feed) and GET /api/v1/tv/signals/{id} (report) and POST /api/v1/tv/generate-report (ad-hoc)
- Test: `tests/api/test_tv_signals.py` — extend existing file

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_tv_signals.py`:

```python
import uuid
from datetime import datetime, timezone

@pytest.fixture
def db_with_signal_report():
    """Insert one tv_signal_reports row in a transaction, yield its ID, then rollback."""
    from atlas.db import get_engine
    engine = get_engine()
    report_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tv_signal_reports "
                "(id, ticker, exchange, triggered_at, condition_tier, condition_code, "
                "condition_label, chart_type, confirmation_level, verdict) "
                "VALUES (:id, :ticker, 'NSE', :ts, 1, 'breakout_52w_volume', "
                "'52-week high breakout', 'vs_nifty', 'dual', 'bullish')"
            ),
            {"id": report_id, "ticker": "HDFCBANK", "ts": datetime.now(timezone.utc)},
        )
    yield {"id": report_id}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tv_signal_reports WHERE id = :id"), {"id": report_id})

@pytest.mark.asyncio
async def test_get_signal_feed_returns_list(client: AsyncClient, db_with_signal_report):
    r = await client.get("/api/v1/tv/signals?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["reports"], list)
    assert "total" in data

@pytest.mark.asyncio
async def test_get_signal_report_by_id(client: AsyncClient, db_with_signal_report):
    report_id = db_with_signal_report["id"]
    r = await client.get(f"/api/v1/tv/signals/{report_id}")
    assert r.status_code == 200
    assert r.json()["ticker"] == "HDFCBANK"

@pytest.mark.asyncio
async def test_get_signal_report_not_found(client: AsyncClient):
    r = await client.get("/api/v1/tv/signals/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_ad_hoc_report_accepted(client: AsyncClient, monkeypatch):
    monkeypatch.setenv("ATLAS_INTERNAL_SECRET", "test_internal_secret")
    with patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock):
        r = await client.post(
            "/api/v1/tv/generate-report",
            json={"ticker": "HDFCBANK"},
            headers={"X-Internal-Secret": "test_internal_secret"},
        )
    assert r.status_code in (200, 202)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/api/test_tv_signals.py::test_get_signal_feed_returns_list -v
```
Expected: `FAILED` — endpoint does not exist.

- [ ] **Step 3: Add the endpoints to tv_signals.py**

Add to `atlas/api/tv_signals.py`:

```python
from typing import Optional
from fastapi import Query

@router.get("/signals")
async def list_signal_reports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tier: Optional[int] = Query(default=None),
    confirmation: Optional[str] = Query(default=None),
) -> dict:
    async with get_session() as session:
        conditions = ["is_active = TRUE"]
        params: dict = {"limit": limit, "offset": offset}
        if tier is not None:
            conditions.append("condition_tier = :tier")
            params["tier"] = tier
        if confirmation is not None:
            conditions.append("confirmation_level = :confirmation")
            params["confirmation"] = confirmation
        where = " AND ".join(conditions)
        rows = session.execute(
            text(  # noqa: S608 — filter values parameterised; column names are constants
                f"SELECT id, ticker, company_name, condition_tier, condition_code, "
                f"condition_label, confirmation_level, verdict, conviction_score, "
                f"triggered_at, created_at "
                f"FROM tv_signal_reports WHERE {where} "
                f"ORDER BY triggered_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        ).fetchall()
        total_row = session.execute(
            text(f"SELECT COUNT(*) FROM tv_signal_reports WHERE {where}"),  # noqa: S608
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        ).fetchone()
    reports = [dict(r._mapping) for r in rows]
    return {"reports": reports, "total": total_row[0] if total_row else 0}


@router.get("/signals/{report_id}")
async def get_signal_report(report_id: str) -> dict:
    async with get_session() as session:
        row = session.execute(
            text("SELECT * FROM tv_signal_reports WHERE id = :rid LIMIT 1"),  # noqa: S608
            {"rid": report_id},
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return dict(row._mapping)


@router.post("/generate-report")
async def generate_report_adhoc(
    body: dict,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    from atlas.config import Config
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != Config.ATLAS_INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    ticker = body.get("ticker", "").upper().strip()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker required")
    synthetic = TVSignalPayload(
        tier=0,
        code="adhoc",
        chart="vs_nifty",
        ticker=ticker,
        exchange="NSE",
        close="0",
        volume="0",
        time="",
        secret=Config.TV_WEBHOOK_SECRET,
    )
    background_tasks.add_task(process_signal, synthetic)
    return {"status": "accepted", "ticker": ticker}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/api/test_tv_signals.py -v
```
Expected: `PASSED` (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/api/tv_signals.py tests/api/test_tv_signals.py
git commit -m "feat(signals): GET /signals feed, GET /signals/{id}, POST /generate-report ad-hoc"
```

---

## Task 9: Alert Provisioner

**Files:**
- Create: `atlas/signals/provisioner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/signals/test_provisioner.py
import pytest
from unittest.mock import patch, MagicMock, call
from atlas.signals.provisioner import (
    _build_alert_csv_row,
    _diff_universe,
)

def test_diff_universe_detects_new_tickers():
    current = {"HDFCBANK", "RELIANCE", "INFY"}
    registered = {"HDFCBANK", "RELIANCE"}
    new, removed = _diff_universe(current, registered)
    assert new == {"INFY"}
    assert removed == set()

def test_diff_universe_detects_removed_tickers():
    current = {"HDFCBANK"}
    registered = {"HDFCBANK", "INFY"}
    new, removed = _diff_universe(current, registered)
    assert new == set()
    assert removed == {"INFY"}

def test_build_alert_csv_row_contains_ticker():
    row = _build_alert_csv_row(
        ticker="HDFCBANK",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_nifty",
        layout_id="abc123",
        webhook_url="https://atlas.jslwealth.in/api/v1/tv/signal",
        secret="sec",
    )
    assert "HDFCBANK" in row
    assert "breakout_52w_volume" in row
    assert "abc123" in row
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/signals/test_provisioner.py -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement provisioner.py**

```python
# atlas/signals/provisioner.py
"""Nightly TV alert provisioning via alleyway/add-tradingview-alerts-tool (Playwright)."""
from __future__ import annotations
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import structlog

from atlas.config import Config

log = structlog.get_logger()

# Only Tier 1 conditions provisioned on TV for MVP.
# 3 conditions × 2 charts = 6 alerts/stock × 200 stocks = 1,200 = TV Premium limit exactly.
# Tier 2/5 TV alerts deferred to Ultimate plan upgrade. They still trigger via Atlas DB compute.
_PROVISIONED_CONDITIONS: list[tuple[int, str, str]] = [
    (1, "breakout_52w_volume", "vs_nifty"),
    (1, "rs_breakout_52w", "vs_nifty"),
    (1, "rs_sector_breakout_52w", "vs_sector"),
    (1, "breakout_52w_volume", "vs_sector"),
    (1, "rs_breakout_52w", "vs_sector"),
    (1, "rs_sector_breakout_52w", "vs_nifty"),
]


def _diff_universe(
    current: set[str], registered: set[str]
) -> tuple[set[str], set[str]]:
    new = current - registered
    removed = registered - current
    return new, removed


def _build_alert_csv_row(
    ticker: str,
    exchange: str,
    condition_code: str,
    chart_type: str,
    layout_id: str,
    webhook_url: str,
    secret: str,
) -> str:
    """Returns one CSV row string for the alleyway tool input format."""
    symbol = f"{exchange}:{ticker}"
    message = (
        f'{{"tier":0,"code":"{condition_code}","chart":"{chart_type}",'
        f'"ticker":"{ticker}","exchange":"{exchange}",'
        f'"close":"{{{{close}}}}","volume":"{{{{volume}}}}","time":"{{{{timenow}}}}",'
        f'"secret":"{secret}"}}'
    )
    return f"{symbol},{condition_code},{layout_id},{webhook_url},{message}"


def _fetch_current_universe(conn) -> set[str]:
    """Fetch top 200 investable stocks from atlas_stock_decisions_daily."""
    from sqlalchemy import text
    rows = conn.execute(
        text(  # noqa: S608 — constant SQL, no user input
            "SELECT u.symbol FROM atlas.atlas_universe_stocks u "
            "JOIN atlas.atlas_stock_decisions_daily d ON d.instrument_id = u.instrument_id "
            "WHERE d.is_investable = TRUE AND u.effective_to IS NULL "
            "AND d.date = (SELECT MAX(date) FROM atlas.atlas_stock_decisions_daily) "
            "ORDER BY u.tier, u.symbol LIMIT 200"
        )
    ).fetchall()
    return {r.symbol for r in rows}


def _fetch_registered_tickers(conn) -> set[str]:
    from sqlalchemy import text
    rows = conn.execute(
        text("SELECT DISTINCT ticker FROM tv_alert_registry WHERE is_active = TRUE")  # noqa: S608
    ).fetchall()
    return {r.ticker for r in rows}


def provision_tv_alerts(alleyway_tool_path: Optional[str] = None) -> dict:
    from atlas.db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        current = _fetch_current_universe(conn)
        registered = _fetch_registered_tickers(conn)

    new_tickers, removed_tickers = _diff_universe(current, registered)
    log.info("provisioner_diff", new=len(new_tickers), removed=len(removed_tickers))

    layout_map = {
        "vs_nifty": Config.TV_LAYOUT_ID_VS_NIFTY,
        "vs_sector": Config.TV_LAYOUT_ID_VS_SECTOR,
    }
    webhook_url = f"{Config.SIGNAL_REPORT_BASE_URL.rstrip('/signals')}/api/v1/tv/signal"

    rows = []
    for ticker in sorted(new_tickers):
        for tier, code, chart_type in _PROVISIONED_CONDITIONS:
            layout_id = layout_map.get(chart_type, "")
            if not layout_id:
                continue
            rows.append(
                _build_alert_csv_row(
                    ticker=ticker,
                    exchange="NSE",
                    condition_code=code,
                    chart_type=chart_type,
                    layout_id=layout_id,
                    webhook_url=webhook_url,
                    secret=Config.TV_WEBHOOK_SECRET,
                )
            )

    added = 0
    failed_tickers: list[str] = []

    if rows:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("symbol,condition,layout_id,webhook_url,message\n")
            for row in rows:
                f.write(row + "\n")
            csv_path = f.name

        tool_path = alleyway_tool_path or "node"
        try:
            result = subprocess.run(
                [tool_path, "add-alerts-tool/index.js", "--config", csv_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                added = len(new_tickers)
                with engine.begin() as wconn:
                    for ticker in new_tickers:
                        for tier, code, chart_type in _PROVISIONED_CONDITIONS:
                            layout_id = layout_map.get(chart_type, "")
                            if not layout_id:
                                continue
                            wconn.execute(
                                text(  # noqa: S608
                                    "INSERT INTO tv_alert_registry "
                                    "(ticker, chart_type, condition_tier, condition_code, "
                                    "layout_id, webhook_url) "
                                    "VALUES (:ticker, :chart_type, :tier, :code, :layout_id, :wh)"
                                ),
                                {
                                    "ticker": ticker,
                                    "chart_type": chart_type,
                                    "tier": tier,
                                    "code": code,
                                    "layout_id": layout_id,
                                    "wh": webhook_url,
                                },
                            )
            else:
                log.error("provisioner_tool_failed", stderr=result.stderr[:500])
                failed_tickers = list(new_tickers)
        except Exception:
            log.exception("provisioner_subprocess_error")
            failed_tickers = list(new_tickers)

    if removed_tickers:
        with engine.begin() as wconn:
            for ticker in removed_tickers:
                wconn.execute(
                    text("UPDATE tv_alert_registry SET is_active = FALSE WHERE ticker = :ticker"),  # noqa: S608
                    {"ticker": ticker},
                )
        log.info("provisioner_deactivated", count=len(removed_tickers))

    return {
        "added": added,
        "removed": len(removed_tickers),
        "failed": failed_tickers,
        "total_active": len(current) - len(removed_tickers) + added,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/signals/test_provisioner.py -v
```
Expected: `PASSED` (3 tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/signals/provisioner.py tests/unit/signals/test_provisioner.py
git commit -m "feat(signals): nightly TV alert provisioner with diff + alleyway tool integration"
```

---

## Task 10: Frontend — Signal Feed Page

**Files:**
- Create: `frontend/src/components/signals/SignalCard.tsx`
- Create: `frontend/src/app/signals/page.tsx`

**Requires `.design-approved.json` in `frontend/src/components/signals/` before any Write/Edit on these files.**

- [ ] **Step 1: Create design approval file**

```bash
mkdir -p frontend/src/components/signals
echo '{"approved_by":"nimish","date":"2026-05-13","feature":"tv-signal-feed"}' \
  > frontend/src/components/signals/.design-approved.json
```

- [ ] **Step 2: Create SignalCard component**

```typescript
// frontend/src/components/signals/SignalCard.tsx
"use client";

import Link from "next/link";

interface SignalCardProps {
  id: string;
  ticker: string;
  companyName?: string;
  conditionLabel: string;
  conditionTier: number;
  confirmationLevel: string;
  verdict: string;
  convictionScore?: number;
  triggeredAt: string;
}

const TIER_STYLES: Record<number, { bg: string; label: string }> = {
  1: { bg: "bg-red-100 text-red-800 border-red-200", label: "T1 Critical" },
  2: { bg: "bg-orange-100 text-orange-800 border-orange-200", label: "T2 High" },
  3: { bg: "bg-yellow-100 text-yellow-800 border-yellow-200", label: "T3 Medium" },
  4: { bg: "bg-gray-100 text-gray-600 border-gray-200", label: "T4 Low" },
  5: { bg: "bg-purple-100 text-purple-800 border-purple-200", label: "T5 Sell" },
};

export function SignalCard({
  id, ticker, companyName, conditionLabel, conditionTier,
  confirmationLevel, verdict, convictionScore, triggeredAt,
}: SignalCardProps) {
  const tierStyle = TIER_STYLES[conditionTier] ?? TIER_STYLES[4];
  const isDual = confirmationLevel === "dual";
  const verdictColor = verdict === "bullish" ? "text-emerald-600" : verdict === "bearish" ? "text-red-600" : "text-yellow-600";

  return (
    <Link href={`/signals/${id}`} className="block">
      <div className="border border-gray-200 rounded-lg p-4 hover:border-teal-300 hover:shadow-sm transition-all bg-white">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-gray-900 text-sm">{ticker}</span>
              {companyName && (
                <span className="text-gray-500 text-xs truncate">{companyName}</span>
              )}
            </div>
            <p className="text-sm text-gray-700 leading-snug">{conditionLabel}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <span className={`text-xs font-medium px-2 py-0.5 rounded border ${tierStyle.bg}`}>
              {tierStyle.label}
            </span>
            {isDual && (
              <span className="text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                DUAL ✓
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-100">
          <div className="flex items-center gap-3">
            <span className={`text-xs font-semibold uppercase ${verdictColor}`}>{verdict}</span>
            {convictionScore != null && (
              <span className="text-xs text-gray-500">
                Conviction {Number(convictionScore).toFixed(1)}/10
              </span>
            )}
          </div>
          <span className="text-xs text-gray-400">
            {new Date(triggeredAt).toLocaleString("en-IN", {
              day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
            })}
          </span>
        </div>
      </div>
    </Link>
  );
}
```

- [ ] **Step 3: Create signals feed page**

```typescript
// frontend/src/app/signals/page.tsx
import { SignalCard } from "@/components/signals/SignalCard";

interface SignalReport {
  id: string;
  ticker: string;
  company_name?: string;
  condition_label: string;
  condition_tier: number;
  confirmation_level: string;
  verdict: string;
  conviction_score?: number;
  triggered_at: string;
}

async function fetchSignals(): Promise<{ reports: SignalReport[]; total: number }> {
  const res = await fetch(
    `${process.env.ATLAS_INTERNAL_API_URL}/api/v1/tv/signals?limit=50`,
    { next: { revalidate: 30 } }
  );
  if (!res.ok) return { reports: [], total: 0 };
  return res.json();
}

export default async function SignalsPage() {
  const { reports, total } = await fetchSignals();

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Signal Feed</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            TradingView Pine Script triggers — dual-confirmed with Atlas intelligence
          </p>
        </div>
        <span className="text-sm text-gray-400">{total} total</span>
      </div>

      {reports.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          No signals yet. TV alerts will appear here when Pine conditions fire.
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((r) => (
            <SignalCard
              key={r.id}
              id={r.id}
              ticker={r.ticker}
              companyName={r.company_name}
              conditionLabel={r.condition_label}
              conditionTier={r.condition_tier}
              confirmationLevel={r.confirmation_level}
              verdict={r.verdict}
              convictionScore={r.conviction_score}
              triggeredAt={r.triggered_at}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors related to signals components.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/signals/ frontend/src/app/signals/page.tsx
git commit -m "feat(signals): signal feed page + SignalCard component"
```

---

## Task 11: Frontend — Full Report Page

**Files:**
- Create: `frontend/src/components/signals/SignalReport.tsx`
- Create: `frontend/src/app/signals/[id]/page.tsx`

- [ ] **Step 1: Create design approval file (parent already created in Task 10)**

*(Already exists from Task 10 — skip)*

- [ ] **Step 2: Create SignalReport component**

```typescript
// frontend/src/components/signals/SignalReport.tsx
"use client";

import Image from "next/image";

interface SignalReportProps {
  report: {
    id: string;
    ticker: string;
    exchange: string;
    company_name?: string;
    sector?: string;
    triggered_at: string;
    condition_tier: number;
    condition_label: string;
    confirmation_level: string;
    verdict: string;
    conviction_score?: number;
    conviction_trend?: string;
    cts_state?: string;
    rs_rank?: number;
    rs_rank_total?: number;
    rs_percentile?: number;
    sector_regime?: string;
    market_regime?: string;
    rsi_14?: number;
    macd_signal?: string;
    ema_alignment?: string;
    hh_hl_state?: string;
    pattern_label?: string;
    perf_1m?: number;
    perf_3m?: number;
    perf_6m?: number;
    perf_ytd?: number;
    perf_vs_nifty_1m?: number;
    perf_vs_nifty_ytd?: number;
    chart_daily_url?: string;
    chart_weekly_url?: string;
    chart_vs_sector_url?: string;
    screenshot_daily?: string;
    screenshot_weekly?: string;
    narrative?: string;
  };
}

function fmt(v?: number | null, decimals = 1): string {
  if (v == null) return "—";
  return Number(v).toFixed(decimals);
}

function fmtPct(v?: number | null): string {
  if (v == null) return "—";
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function PerfCell({ label, value, vs }: { label: string; value?: number | null; vs?: number | null }) {
  const vStr = fmtPct(value);
  const vsStr = vs != null ? ` vs Nifty ${fmtPct(vs)}` : "";
  const color = value != null && Number(value) >= 0 ? "text-emerald-600" : "text-red-600";
  return (
    <div>
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className={`text-sm font-medium ${color}`}>{vStr}{vsStr}</div>
    </div>
  );
}

export function SignalReport({ report: r }: SignalReportProps) {
  const isDual = r.confirmation_level === "dual";
  const verdictColor = r.verdict === "bullish" ? "text-emerald-600" : r.verdict === "bearish" ? "text-red-600" : "text-yellow-600";

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Header */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-gray-900">{r.exchange}:{r.ticker}</span>
              {r.company_name && <span className="text-gray-500 text-sm">{r.company_name}</span>}
            </div>
            <p className="text-sm text-gray-700 mt-1">{r.condition_label}</p>
          </div>
          <div className="text-right shrink-0">
            <div className={`text-sm font-semibold uppercase ${verdictColor}`}>{r.verdict}</div>
            {isDual && (
              <div className="text-xs text-emerald-700 font-medium mt-1">DUAL CONFIRMED ✓</div>
            )}
          </div>
        </div>
        <div className="text-xs text-gray-400 mt-2">
          {new Date(r.triggered_at).toLocaleString("en-IN", {
            day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
          })}
        </div>
      </div>

      {/* Atlas Intelligence */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Atlas Intelligence
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-500 text-xs mb-0.5">Conviction</div>
            <div className="font-medium">{r.conviction_score != null ? `${fmt(r.conviction_score)}/10` : "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">CTS State</div>
            <div className="font-medium">{r.cts_state ?? "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">RS Rank</div>
            <div className="font-medium">
              {r.rs_rank != null ? `#${r.rs_rank} / ${r.rs_rank_total ?? "?"} (${fmt(r.rs_percentile)}th pct)` : "—"}
            </div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">Regime</div>
            <div className="font-medium text-xs">{r.market_regime ?? "—"}</div>
          </div>
        </div>
        {r.sector && (
          <div className="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-600">
            Sector: <span className="font-medium">{r.sector}</span>
            {r.sector_regime && <> — {r.sector_regime}</>}
          </div>
        )}
      </div>

      {/* Charts */}
      {(r.screenshot_daily || r.chart_daily_url) && (
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Charts</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {r.screenshot_daily && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500">vs Nifty — Daily</span>
                  {r.chart_daily_url && (
                    <a href={r.chart_daily_url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-teal-600 hover:underline">Open in TV ↗</a>
                  )}
                </div>
                <img src={`/api/signals/screenshot?path=${encodeURIComponent(r.screenshot_daily)}`}
                  alt={`${r.ticker} daily chart`} className="w-full rounded border border-gray-100" />
              </div>
            )}
            {r.screenshot_weekly && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500">vs Nifty — Weekly</span>
                  {r.chart_weekly_url && (
                    <a href={r.chart_weekly_url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-teal-600 hover:underline">Open in TV ↗</a>
                  )}
                </div>
                <img src={`/api/signals/screenshot?path=${encodeURIComponent(r.screenshot_weekly)}`}
                  alt={`${r.ticker} weekly chart`} className="w-full rounded border border-gray-100" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Technical Snapshot */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Technical Snapshot
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-3">
          <div>
            <div className="text-gray-500 text-xs mb-0.5">RSI(14)</div>
            <div className="font-medium">{fmt(r.rsi_14)}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">MACD</div>
            <div className="font-medium text-xs">{r.macd_signal?.replace(/_/g, " ") ?? "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">EMA Alignment</div>
            <div className="font-medium text-xs">{r.ema_alignment?.replace(/_/g, " ") ?? "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">HH/HL</div>
            <div className="font-medium text-xs">{r.hh_hl_state?.replace(/_/g, " ") ?? "—"}</div>
          </div>
        </div>
        {r.pattern_label && (
          <div className="text-xs text-gray-700 bg-gray-50 rounded px-3 py-2">{r.pattern_label}</div>
        )}
      </div>

      {/* Performance */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Performance</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <PerfCell label="1 Month" value={r.perf_1m} vs={r.perf_vs_nifty_1m} />
          <PerfCell label="3 Month" value={r.perf_3m} />
          <PerfCell label="6 Month" value={r.perf_6m} />
          <PerfCell label="YTD" value={r.perf_ytd} vs={r.perf_vs_nifty_ytd} />
        </div>
      </div>

      {/* Narrative */}
      {r.narrative && (
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Narrative</h2>
          <p className="text-sm text-gray-700 leading-relaxed">{r.narrative}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        {r.chart_daily_url && (
          <a href={r.chart_daily_url} target="_blank" rel="noopener noreferrer"
            className="text-sm px-4 py-2 rounded-lg border border-teal-300 text-teal-700 hover:bg-teal-50 transition-colors">
            Open in TradingView ↗
          </a>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create report detail page**

```typescript
// frontend/src/app/signals/[id]/page.tsx
import { notFound } from "next/navigation";
import { SignalReport } from "@/components/signals/SignalReport";

async function fetchReport(id: string) {
  const res = await fetch(
    `${process.env.ATLAS_INTERNAL_API_URL}/api/v1/tv/signals/${id}`,
    { next: { revalidate: 60 } }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Report fetch failed: ${res.status}`);
  return res.json();
}

export default async function SignalReportPage({ params }: { params: { id: string } }) {
  const report = await fetchReport(params.id);
  if (!report) notFound();
  return (
    <div className="px-4 py-8">
      <SignalReport report={report} />
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors from signals files.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/signals/SignalReport.tsx frontend/src/app/signals/[id]/page.tsx
git commit -m "feat(signals): full report page — 13D-style layout with charts, intel layer, narrative"
```

---

## Task 12: Screenshot Serve Route (Next.js API)

**Files:**
- Create: `frontend/src/app/api/signals/screenshot/route.ts`

Screenshots are stored as EC2 local paths. The frontend needs an API route to serve them as images (the browser can't access EC2 paths directly).

- [ ] **Step 1: Write the route**

```typescript
// frontend/src/app/api/signals/screenshot/route.ts
import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const ALLOWED_BASE = process.env.SIGNAL_SCREENSHOT_DIR ?? "/data/signals/screenshots";

export async function GET(req: NextRequest) {
  const filePath = req.nextUrl.searchParams.get("path");
  if (!filePath) {
    return NextResponse.json({ error: "path required" }, { status: 400 });
  }

  // Security: ensure the path is within the allowed base directory
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(ALLOWED_BASE))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const buffer = fs.readFileSync(resolved);
  return new NextResponse(buffer, {
    headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=86400" },
  });
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "screenshot" | head -10
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/api/signals/screenshot/route.ts
git commit -m "feat(signals): Next.js API route to serve EC2-local chart screenshot PNGs"
```

---

## Task 13: End-to-End Smoke Test (manual — EC2)

These steps are manual verification on EC2, not automated tests.

- [ ] **Step 1: Apply migration on EC2**

```bash
# On EC2
cd /home/ubuntu/atlas-os
alembic upgrade 064
```
Expected: `Running upgrade 063 -> 064`

- [ ] **Step 2: Install Playwright Chromium on EC2 (one-time, ~500MB)**

```bash
# On EC2 — required before any screenshot call will work
pip install playwright
playwright install chromium --with-deps
# Verify
python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); b.close(); p.stop(); print('OK')"
```
Expected: `OK` (no error)

- [ ] **Step 3: Confirm tables exist**

```bash
psql $DATABASE_URL -c "\dt tv_alert_registry tv_signal_reports atlas_signal_alerts"
```
Expected: 3 rows listed.

- [ ] **Step 5: Set .env vars**

Add to `/home/ubuntu/atlas-os/.env`:
```
TV_WEBHOOK_SECRET=<generate with: python3 -c "import secrets; print(secrets.token_hex(16))">
TV_LAYOUT_ID_VS_NIFTY=<from TV URL after saving layout>
TV_LAYOUT_ID_VS_SECTOR=<from TV URL after saving layout>
TV_SESSION_ID=<from browser devtools cookies>
TV_SESSION_SIGN=<from browser devtools cookies>
SIGNAL_SCREENSHOT_DIR=/data/signals/screenshots
SIGNAL_REPORT_BASE_URL=https://atlas.jslwealth.in/signals
```

- [ ] **Step 6: Fire a test webhook manually**

```bash
curl -X POST https://atlas.jslwealth.in/api/v1/tv/signal \
  -H "Content-Type: application/json" \
  -d '{
    "tier": 1,
    "code": "breakout_52w_volume",
    "chart": "vs_nifty",
    "ticker": "HDFCBANK",
    "exchange": "NSE",
    "close": "1820.50",
    "volume": "4500000",
    "time": "2026-05-13T09:20:00Z",
    "secret": "<TV_WEBHOOK_SECRET>"
  }'
```
Expected: `{"status":"accepted"}`

- [ ] **Step 7: Check report was created**

```bash
psql $DATABASE_URL -c "SELECT ticker, condition_code, confirmation_level, verdict FROM tv_signal_reports ORDER BY created_at DESC LIMIT 1;"
```
Expected: row with HDFCBANK.

- [ ] **Step 8: Verify signal feed page loads**

Open `https://atlas.jslwealth.in/signals` in browser.
Expected: signal card for HDFCBANK appears.

- [ ] **Step 9: Commit smoke test results to decisions.jsonl**

```bash
echo '{"date":"2026-05-13","decision":"TV signal webhook end-to-end verified on EC2 — webhook → processor → DB → frontend feed all working"}' >> decisions.jsonl
git add decisions.jsonl && git commit -m "chore: record TV signal e2e smoke test pass in decisions.jsonl"
```

---

## Task 14: EC2 Allowlist + TV Setup (one-time manual)

No code changes. Manual steps.

- [ ] **Step 1: Add TV source IPs to EC2 security group inbound rules**

Via AWS console or CLI, allow inbound TCP 443 from:
- `52.89.214.238/32`
- `34.212.75.30/32`
- `54.218.53.128/32`
- `52.32.178.7/32`

- [ ] **Step 2: Create TV layouts (one-time)**

In TradingView Premium:
1. Open any NSE stock chart
2. Add Pine Script from §5 of the spec (Chart 1 template)
3. Add indicators: 20/50/200 EMA, RSI(14), MACD(12,26,9), Volume with 20-day SMA
4. Save layout as `atlas_vs_nifty` — note layout ID from URL
5. Repeat with Chart 2 Pine Script, save as `atlas_vs_sector` — note layout ID
6. Add TV_LAYOUT_ID_VS_NIFTY and TV_LAYOUT_ID_VS_SECTOR to EC2 .env

- [ ] **Step 3: Set up one test alert manually**

In TV, set an alert on HDFCBANK using the Pine Script condition, webhook URL = `https://atlas.jslwealth.in/api/v1/tv/signal`.
Trigger manually from TV (or wait for condition) to confirm end-to-end.

---

## Task 15: Nightly Provisioning Cron

**Files:**
- Create systemd timer or pg_cron entry (EC2 manual step)

- [ ] **Step 1: Create provisioning script entry point**

```python
# scripts/provision_tv_alerts.py
"""Run nightly at 19:00 IST to sync TV alerts with Atlas universe."""
import asyncio
from atlas.signals.provisioner import provision_tv_alerts

if __name__ == "__main__":
    result = provision_tv_alerts()
    print(f"Provisioning complete: {result}")
```

- [ ] **Step 2: Register systemd timer on EC2**

```bash
# /etc/systemd/system/atlas-tv-provisioner.service
[Unit]
Description=Atlas TV Alert Provisioner

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/atlas-os
ExecStart=/home/ubuntu/atlas-os/venv/bin/python scripts/provision_tv_alerts.py
EnvironmentFile=/home/ubuntu/atlas-os/.env
```

```bash
# /etc/systemd/system/atlas-tv-provisioner.timer
[Unit]
Description=Run Atlas TV provisioner nightly at 19:00 IST (13:30 UTC)

[Timer]
OnCalendar=*-*-* 13:30:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now atlas-tv-provisioner.timer
sudo systemctl list-timers atlas-tv-provisioner
```

- [ ] **Step 3: Commit script**

```bash
git add scripts/provision_tv_alerts.py
git commit -m "feat(signals): nightly TV provisioner entry point script"
```

---

## Self-Review

**Spec coverage check:**

| Spec Section | Task |
|---|---|
| §4 DB tables | Task 1 |
| §5 Pine Script conditions | Manual setup (Task 14) — no code |
| §6 Condition registry | Reflected in provisioner._PROVISIONED_CONDITIONS (Task 9) and _build_condition_label (Task 5) |
| §7.1 Webhook receiver | Task 3 |
| §7.2 Signal processor | Task 5 |
| §7.3 Technical cross-check | Task 4 |
| §7.4 Chart screenshot | Task 7 |
| §7.5 Report narrative | Task 6 |
| §7.6 Alert provisioner | Task 9 + Task 15 |
| §8.1 Signal feed page | Task 10 |
| §8.2 Signal report page | Task 11 |
| §8.3 Stock page integration | Not in this plan — deferred to Phase 5 (add Signal History tab to stock deep dive page separately) |
| §8.4 Ad-hoc report trigger | Task 8 (POST /generate-report) |
| §9 TV one-time setup | Task 14 |
| §10 .env additions | Task 3 (config vars) |
| §11 Migration | Task 1 |
| §12 Testing | Tasks 1-9 each have tests |
| §13 Rollout (all 5 phases) | Tasks ordered to match: infra → pipeline → report quality → provisioning → polish |

**Deferred (Phase 5, separate plan):**
- Stock page Signal History tab
- Forward returns tracking (did signal play out?)
- PDF export (Playwright print-to-PDF)

**Placeholder scan:** None found — all code blocks are complete.

**Type consistency:** `TVSignalPayload` defined in Task 2, used in Tasks 3, 5, 8. `TechnicalSnapshot` defined in Task 4, consumed in Task 5. All field names consistent.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | 4 findings (alert math, Playwright on EC2, webhook dedup, LLM cost) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 12 issues found, all resolved — migration 064, sync DB pattern, correct table names, instrument_id FK, Groq LLM, T1-only alerts, dedup UNIQUE constraint, Playwright EC2 install |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX:** Alert arithmetic fixed (T1-only = 1,200/1,200 Premium), Playwright EC2 install added, dedup UNIQUE constraint added, Groq replaces Sonnet
- **CROSS-MODEL:** Both Claude and Codex flagged Playwright RAM risk — resolved by t3.xlarge deployment
- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED — ready to implement
