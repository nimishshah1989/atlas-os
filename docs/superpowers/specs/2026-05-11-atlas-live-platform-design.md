# Atlas Live Platform — Design Spec
**Date:** 2026-05-11
**Status:** Premises confirmed | Spec review pass 2 | Ready for CEO review
**Branch:** main
**Author:** Nimish Shah

---

## Problem Statement

Atlas OS is a powerful wealth analytics engine — regime classification, RS/momentum states, multi-asset screeners, RRG charts, decision engine — but it feels like a report. Advisors open it, read it, then manually check each client's holdings against the signals they just saw. There is no way to know "which of my 50 clients has a holding that just degraded?" without doing it by hand.

The gap is not analytics depth (Atlas beats every Indian competitor). The gap is operational liveness: client portfolio awareness, signal monitoring per holding, and freshness of data through the trading day.

**What already exists in India:** WealthLab does RS/Stage 2 analysis with no portfolio tracking. SmallCase does portfolio tracking with no deep analytics. No product combines both. Atlas's JOIN between client holdings and Atlas signals is genuinely novel.

---

## Success Criteria

1. An advisor can see, in one view, every client holding currently flagged by a degraded Atlas signal
2. The system automatically detects state changes overnight and surfaces them before market open
3. During market hours, prices update every 15 minutes and price-sensitive metrics refresh after each poll
4. Advisors can build model portfolios (strategy constructs) and link them to real client portfolios to track drift
5. All existing Atlas screeners, deep dives, and RRG charts continue working unchanged

---

## Premises

- **P1:** Internal JSL advisors only — no public access, no billing, no multi-tenancy in this build
- **P2:** Portfolio + alert system ships on day-end data first (Phase 1). Intraday polling is Phase 2
- **P3:** Intraday = 15-min polling via vendor-agnostic `IMarketDataProvider` abstraction; Kite Connect as default vendor
- **P4:** Both model portfolios (strategy constructs, already exist as M15 rule-based/custom) and client portfolios (actual holdings with cost basis) — linked for drift tracking
- **P5:** Recommendations = signal alerts only. Advisor decides. Atlas is the data layer, not SEBI-regulated advice

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        PHASE 1 (Day-End)                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  Client Mgmt     │  Holdings Track  │  Alert Engine             │
│  atlas.clients   │  atlas.client_   │  Nightly diff job         │
│  (advisor-owned) │  holdings        │  atlas.signal_alerts      │
│  advisor_id FK   │  cost_basis,qty  │  in-app inbox             │
│  → auth.users    │  instrument_id   │  email digest (deferred)  │
└──────────────────┴──────────────────┴───────────────────────────┘
         │                  │                      │
         └──────────────────┴──────────────────────┘
                            │
                  JOIN: client_holdings
                  × atlas_stock_states_daily  (stocks only Phase 1)
                  × atlas.decisions
                  = Portfolio Health CTE

┌─────────────────────────────────────────────────────────────────┐
│                       PHASE 2 (Intraday)                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  IMarketData     │  15-min Compute  │  SSE Push                 │
│  Provider        │  atlas.intraday_ │  /api/stream/prices       │
│  abstraction     │  prices (shadow) │  fires after each poll    │
│  KiteConnect     │  atlas.compute.  │  EventSource in frontend  │
│  TrueData/GDFL   │  rs/states funcs │  timestamp field included │
└──────────────────┴──────────────────┴───────────────────────────┘
```

---

## Phase 1: Client Portfolio Tracking + Alert Engine

### New Data Model

**`atlas.clients`**
```
id            UUID PK
advisor_id    UUID NOT NULL  (FK → auth.users, owner scoping — index)
name          TEXT NOT NULL
email         TEXT
phone         TEXT
risk_profile  ENUM (conservative/moderate/aggressive)  -- optional, can be null
advisor_note  TEXT
is_deleted    BOOLEAN DEFAULT FALSE
deleted_at    TIMESTAMPTZ
created_at    TIMESTAMPTZ NOT NULL
updated_at    TIMESTAMPTZ NOT NULL
```

**`atlas.client_holdings`**
```
id                   UUID PK
client_id            UUID NOT NULL FK → atlas.clients (index)
instrument_id        TEXT NOT NULL
  -- canonical format: plain NSE symbol e.g. "HDFCBANK"
  -- must match atlas_stock_states_daily.symbol exactly
  -- validated on insert against atlas.universe_stocks/etfs/funds
instrument_type      ENUM (stock/mf/etf) NOT NULL
  -- Phase 1: CHECK (instrument_type = 'stock') — remove in Phase 2
quantity             NUMERIC(20,4) NOT NULL
avg_cost_price       NUMERIC(20,4) NOT NULL  (₹ — never float)
purchase_date        DATE
model_portfolio_id   UUID FK → atlas.strategy_fm_custom_portfolios (nullable)
  -- weight_pct for drift: read from strategy_fm_custom_portfolios.weights JSONB
  -- drift = (holding_mkt_value / total_client_mkt_value) vs model weight_pct
  -- when model_portfolio_id IS NULL, drift column shows NULL (no model assigned)
is_active            BOOLEAN DEFAULT TRUE
is_deleted           BOOLEAN DEFAULT FALSE
deleted_at           TIMESTAMPTZ
created_at           TIMESTAMPTZ NOT NULL
updated_at           TIMESTAMPTZ NOT NULL
```

**`atlas.signal_alerts`**
```
id              UUID PK
client_id       UUID NOT NULL FK → atlas.clients (index)
holding_id      UUID NOT NULL FK → atlas.client_holdings (index)
instrument_id   TEXT NOT NULL
alert_type      ENUM (state_degraded/regime_change/rs_drop/exit_signal)
prev_value      JSONB  (state/RS before — e.g. {"rs_state":"Leader","rs_pctile":82})
curr_value      JSONB  (state/RS now   — e.g. {"rs_state":"Weakening","rs_pctile":61})
triggered_at    TIMESTAMPTZ NOT NULL
acknowledged_at TIMESTAMPTZ  (NULL = unread)
created_at      TIMESTAMPTZ NOT NULL
updated_at      TIMESTAMPTZ NOT NULL
UNIQUE (holding_id, alert_type, (triggered_at AT TIME ZONE 'Asia/Kolkata')::date)
  -- idempotency: one alert per type per holding per calendar day (IST)
```

### Advisor Ownership Scoping

In Phase 1, each advisor only sees their own clients. All API endpoints filter by `advisor_id = current_user_id` extracted from the Supabase JWT. No full RBAC — just ownership. Structure supports multi-advisor without any schema change.

```python
# Every client query is scoped
WHERE advisor_id = :current_user_id AND is_deleted = FALSE
```

### API Endpoints

```
GET  /api/clients                     list advisor's clients
POST /api/clients                     create client (advisor_id from JWT)
GET  /api/clients/{id}                client detail
PUT  /api/clients/{id}                update client
PUT  /api/clients/{id}/deactivate     soft-delete client (sets is_deleted=true)

GET  /api/clients/{id}/holdings       client's active holdings with current Atlas signals
POST /api/clients/{id}/holdings       add holding (validates instrument_id against universe)
  -- 422 {"error_code": "invalid_instrument", "field": "instrument_id",
  --      "message": "symbol not found in atlas universe"}
  --     if instrument_id is not in atlas.universe_stocks (Phase 1)
PUT  /api/clients/{id}/holdings/{holding_id}   update holding
PUT  /api/clients/{id}/holdings/{holding_id}/deactivate  soft-delete holding

GET  /api/portfolio-watch             all active holdings across advisor's clients + signals
GET  /api/alerts                      all unacknowledged alerts for advisor's clients
POST /api/alerts/{id}/acknowledge     mark alert as read
```

No hard deletes anywhere. All removals set `is_deleted=true`, `deleted_at=now()`.

**Error contract (all endpoints):** `404` if resource not found or belongs to a different advisor; `403` if advisor tries to access another advisor's resource; `422` with `{error_code, field, message}` on validation failure. These follow the global API error envelope convention in CLAUDE.md.

### Portfolio Watch Query (CTE skeleton)

```sql
WITH active_holdings AS (
  SELECT
    h.id AS holding_id,
    c.id AS client_id,
    c.name AS client_name,
    h.instrument_id,
    h.quantity,
    h.avg_cost_price
  FROM atlas.client_holdings h
  JOIN atlas.clients c ON c.id = h.client_id
  WHERE c.advisor_id = :advisor_id
    AND c.is_deleted = FALSE
    AND h.is_active = TRUE
    AND h.is_deleted = FALSE
    AND h.instrument_type = 'stock'  -- Phase 1: stocks only
),
latest_signals AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    rs_state,
    rs_pctile_3m,
    momentum_state,
    computed_date
  FROM atlas.atlas_stock_states_daily
  ORDER BY symbol, computed_date DESC
),
latest_decisions AS (
  SELECT DISTINCT ON (instrument_id)
    instrument_id,
    decision,
    decision_date
  FROM atlas.decisions
  WHERE instrument_type = 'stock'
  ORDER BY instrument_id, decision_date DESC
),
latest_alerts AS (
  SELECT DISTINCT ON (holding_id)
    holding_id,
    alert_type,
    triggered_at
  FROM atlas.signal_alerts
  WHERE acknowledged_at IS NULL
  ORDER BY holding_id, triggered_at DESC
)
SELECT
  ah.*,
  ls.rs_state,
  ls.rs_pctile_3m,
  ls.momentum_state,
  ls.close_price AS current_price,       -- Phase 1: day-end close; Phase 2: replaced by intraday LTP
  ls.computed_date AS signal_as_of,
  ld.decision,
  la.alert_type AS active_alert
  -- pnl_pct, drift_pct: computed in Python after fetch, not in SQL
  --   pnl_pct  = (current_price - avg_cost_price) / avg_cost_price
  --   drift_pct = computed via model_portfolio_id → weights JSONB lookup (null if no model assigned)
FROM active_holdings ah
LEFT JOIN latest_signals   ls ON ls.symbol = ah.instrument_id
LEFT JOIN latest_decisions ld ON ld.instrument_id = ah.instrument_id
LEFT JOIN latest_alerts    la ON la.holding_id = ah.holding_id;
```

Index required: `atlas_stock_states_daily(symbol, computed_date DESC)` — already exists from M2/M3 compute.

**`PortfolioWatchRow` Pydantic schema (response contract)**
```python
class PortfolioWatchRow(BaseModel):
    holding_id: UUID
    client_id: UUID
    client_name: str
    instrument_id: str
    quantity: Decimal
    avg_cost_price: Decimal
    current_price: Decimal | None        # close_price Phase 1; LTP Phase 2
    pnl_pct: Decimal | None              # (current_price - avg_cost_price) / avg_cost_price
    rs_state: str | None
    rs_pctile_3m: Decimal | None
    momentum_state: str | None
    signal_as_of: date | None
    decision: str | None
    active_alert: str | None             # alert_type of most recent unread alert, or null
    drift_pct: Decimal | None            # null when no model_portfolio_id assigned
```

### Portfolio Watch View (the core screen)

```
Client    | Instrument   | Qty  | Avg Cost | CMP  | P&L    | RS State  | Decision | Alert?
----------|--------------|------|----------|------|--------|-----------|----------|-------
Sharma    | HDFCBANK     | 500  | ₹1,450   | 1,620| +11.7% | Leader    | HOLD     |  —
Sharma    | BAJFINANCE   | 200  | ₹6,800   | 5,900| -13.2% | Weakening | WATCH    | ⚠️ RS drop
Mehta     | INFY         | 300  | ₹1,200   | 1,310| +9.2%  | Leader    | BUY      |  —
```

- CMP column: day-end price in Phase 1, live LTP in Phase 2
- Sortable by: client, P&L%, RS state, decision, alert status
- Filterable by: alert type, RS state, decision, instrument type
- Click instrument → existing deep dive page
- Click client → client holdings page
- Alert badge → acknowledgeable inline

### Nightly Alert Engine (`scripts/nightly_alerts.py`)

Runs at 5:30 PM IST (after nightly compute completes):

0. **Dependency check:** `SELECT MAX(computed_date) FROM atlas.atlas_stock_states_daily` must equal `CURRENT_DATE` (IST). If not, abort with exit code 1 and log `"nightly compute not yet complete — alerts deferred"`. Cron will retry at 5:45 PM.
1. Fetch today's `atlas_stock_states_daily` for all symbols with active holdings
2. Compare against yesterday's state per holding (previous day's `computed_date` row)
3. Detect changes:
   - RS state downgrade: Leader→Weakening, Weakening→Laggard, any→Exiting
   - New EXIT decision (decision changed to EXIT today)
   - Regime change affecting holding's sector (join via `atlas.universe_stocks.sector_id`)
   - RS pctile drop > 15 points in 1 day
4. Insert `atlas.signal_alerts` rows (idempotent on `holding_id + triggered_at date`)
5. Alerts surface in `/alerts` inbox on next page load
6. **Re-run safety:** idempotent via UNIQUE constraint — re-running after partial failure inserts only the missing rows; no duplicates, no data loss

**Regime change definition:** a regime-change alert fires when `atlas.sector_regime_signals.regime_signal` (column: `regime_signal TEXT`, values: `bullish/neutral/bearish`) changes sign for a sector that contains one of the advisor's client holdings. Join path: `client_holdings.instrument_id → atlas.universe_stocks.sector_id → atlas.sector_regime_signals.sector_id`.

**Phase 1 scope: stocks only.** MF/ETF alerts deferred to Phase 2 (requires joining different state tables: `atlas_fund_states_daily`, `atlas_etf_states_daily`).

### Model Portfolio Drift

When `holding.model_portfolio_id` is set, drift is calculated as:

```
client_weight_pct = (holding_quantity × current_price) / sum(all_holdings_market_value)
model_weight_pct  = strategy_fm_custom_portfolios.weights->>instrument_id  (from JSONB column)
drift_pct         = client_weight_pct - model_weight_pct

-- Phase 1: current_price = atlas_stock_states_daily.close_price (latest computed_date row)
-- Phase 2: current_price = atlas.intraday_prices.ltp (latest intraday snapshot)
-- Denominator: sum of market value of ALL active holdings for the client (not just model-linked ones)
-- If strategy_fm_custom_portfolios.weights JSONB does not contain the instrument_id key,
--   drift_pct = NULL and the UI shows "Not in model" (not an error — instrument may have been added outside the model)
```

Display: green if within ±3%, amber if ±3–8%, red if >8% drift. NULL if no model assigned.
Flag: if model decision = EXIT and client still holds, show "Model says exit" warning.

---

## Phase 2: Intraday Data Layer

### IMarketDataProvider Abstraction

```python
# atlas/market_data/provider.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

@dataclass
class MarketDataSnapshot:
    symbol: str
    ltp: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    volume: int
    timestamp: datetime

class IMarketDataProvider(ABC):
    @abstractmethod
    async def get_snapshot(self, symbols: list[str]) -> list[MarketDataSnapshot]:
        """Fetch current snapshot for given symbols.
        Must be async — KiteConnect makes 4 sequential HTTP calls for 2000 symbols (~4s);
        blocking the event loop is not acceptable. Implementations use httpx.AsyncClient.
        Handles pagination internally (KiteConnect Quote API: max 500 symbols per call).
        """
        ...

    @abstractmethod
    def is_market_open(self) -> bool: ...
```

**Default: `KiteConnectProvider`** — uses Kite Connect Quote API (REST), not WebSocket.
- Quote API: max 500 instruments per call, rate limit 1 req/sec
- For 2000 symbols: 4 sequential calls, ~4 seconds total — acceptable for 15-min cadence
- ₹500/month, internal use OK (no redistribution restriction for own tools)

**Swap path:** `TrueDataProvider` or `GDFLProvider` implements same interface.
Change `MARKET_DATA_VENDOR=kite|truedata|gdfl` env var. Zero application code changes.

### 15-Minute Polling Engine

APScheduler job runs 9:15 AM – 3:30 PM IST on exchange trading days only:

```python
# atlas/market_data/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('interval', minutes=15, start_date='...',
                          timezone='Asia/Kolkata')
async def intraday_poll():
    if not provider.is_market_open():
        return
    symbols = get_all_active_symbols()  # full atlas.universe_stocks — NOT filtered to client holdings
    # polling full universe (not just client holdings) keeps RS pctile rankings accurate;
    # RS is a relative metric — dropping to client-only symbols would distort pctile calculations
    snapshots = provider.get_snapshot(symbols)  # handles 500-symbol batching internally
    await store_intraday_prices(snapshots)       # write to atlas.intraday_prices
    await recompute_intraday_metrics(snapshots)  # atlas.compute.rs, atlas.compute.states
    await notify_sse_clients()                   # push to SSE channel
```

Runs in a separate worker process (not the FastAPI request process) to avoid resource contention with the nightly EC2 compute job. Nightly compute: 5:30–6:30 PM IST. Polling: 9:15 AM–3:30 PM IST. Non-overlapping schedules — no conflict.

### Intraday Metrics (shadow tables — do NOT mutate day-end rows)

```
atlas.intraday_prices     — raw snapshots, rolling 1-day window, pruned at EOD
atlas.intraday_rs         — RS pctile recomputed from intraday prices
atlas.intraday_ema        — EMA ratio recomputed from intraday prices
```

Recomputed via existing functions:
- `atlas.compute.rs.compute_rs_pctile(prices, universe_prices)` — existing function
- `atlas.compute.states.classify_trend_state(ema_ratio)` — existing function

Day-end tables (`atlas_stock_states_daily`) are NEVER mutated by intraday jobs.

### SSE Push to Frontend

```python
# FastAPI SSE endpoint — fires after each 15-min poll, not on a bare timer
from sse_starlette.sse import EventSourceResponse

_latest_snapshot: dict = {}  # updated by polling job; {} until first poll fires

@router.get("/api/stream/prices")
async def price_stream(current_user = Depends(get_current_user)):
    # Requires Supabase JWT auth (same middleware as all other endpoints).
    # EventSource cannot set Authorization header; frontend passes JWT as
    # ?token= query param and middleware reads it from there for SSE only.
    async def event_generator():
        last_sent_ts = None
        while True:
            if _latest_snapshot and _latest_snapshot.get("timestamp") != last_sent_ts:
                # guard: skip yield if snapshot is still empty (before 9:15 AM first poll)
                last_sent_ts = _latest_snapshot["timestamp"]
                yield {
                    "data": json.dumps({
                        "prices": _latest_snapshot["prices"],
                        "timestamp": last_sent_ts,  # ISO8601 — client uses for staleness
                        "next_update_at": compute_next_poll_time(),
                    })
                }
            await asyncio.sleep(2)  # check for new snapshot every 2s
    return EventSourceResponse(event_generator())

def compute_next_poll_time() -> str:
    """Return next 15-min wall-clock boundary as ISO8601 string (IST).
    E.g. if now is 10:17 IST → returns 10:30 IST.
    Caps at 15:30 if market is closed (end-of-day).
    """
    now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    minutes = (now.minute // 15 + 1) * 15
    next_poll = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return min(next_poll, market_close).isoformat()
```

**Single-worker assumption:** `_latest_snapshot` is an in-process dict. Phase 2 assumes a single FastAPI worker process. If the deployment ever scales to multiple workers, replace with Redis pub/sub (`PUBLISH atlas:prices` from the APScheduler worker; `SUBSCRIBE` in SSE endpoint) — zero frontend change required.

Frontend `useMarketData()` hook:
- `EventSource` auto-reconnects on drop
- On reconnect, server sends latest snapshot immediately (no stale-on-reconnect)
- Frontend checks `timestamp` field to detect if data is stale (>20 min old = show warning)
- Price tiles show: LTP + "Updated 3m ago" freshness label from `timestamp`

---

## UI Changes (Phase 1)

### New Pages
- `/clients` — advisor's client list with quick stats (# holdings, # active alerts)
- `/clients/[id]` — client holdings table + model drift + alert history
- `/portfolio-watch` — all holdings across advisor's clients, sortable/filterable
- `/alerts` — notification inbox, acknowledgeable, grouped by client

### Existing Pages (minimal targeted changes)
- Nav: add "Clients" and "Watch" links
- Regime page: "Portfolio Impact" panel — how many of advisor's client holdings are in sectors with negative regime signal

### Phase 1.5 (backlog, not in Phase 1 scope)
- Stock/fund/ETF deep dive: "Clients holding this" badge — deferred; requires cross-cutting change to all deep dive pages

### Live Feel (Phase 2 additions to existing pages)
- Every price display: LTP tile with `timestamp`-driven "Updated Xm ago" badge
- Screener rows: price column updates in-place via SSE (no page reload)
- Deep dive header: live LTP + intraday RS change vs previous close

---

## What is NOT in Scope

- Multi-tenancy / multiple advisory firms
- Client-facing portal (clients cannot log in — advisors only)
- Automated trade execution or order routing
- SMS/WhatsApp alert delivery (in-app inbox only in Phase 1)
- Real-time tick data (15-min polling is the minimum viable freshness)
- Historical P&L / XIRR (day-end mark-to-market in Phase 1; XIRR is Phase 3+)
- MF/ETF holdings tracking (Phase 1: stocks only, enforced by CHECK constraint)
- Backtest engine integration with client portfolios (future, not Phase 1 or 2)

---

## What Already Exists (Reuse Map)

| Sub-problem | Existing code | Reuse how |
|---|---|---|
| Portfolio construct (model) | `atlas.strategy_fm_custom_portfolios` | `model_portfolio_id` FK; read `weights` JSONB for drift |
| Instrument picker | `frontend/src/components/portfolio/InstrumentPicker.tsx` | Reuse in holdings entry form |
| Signal states (stocks) | `atlas_stock_states_daily` | JOIN with client_holdings in portfolio watch CTE |
| Decisions (buy/hold/sell) | `atlas.decisions` table | Populate Decision column in watch table |
| Deep dive pages | All existing `/stocks/[symbol]`, `/funds/[id]`, `/etfs/[ticker]` | Link from watch table rows |
| Health freshness | `atlas.health_freshness` | Drive "data as of" staleness indicators |
| RS compute | `atlas.compute.rs.compute_rs_pctile()` | Call from intraday recompute job in Phase 2 |
| State classify | `atlas.compute.states.classify_trend_state()` | Call from intraday recompute job in Phase 2 |

---

## Build Order (Phase 1)

1. **DB migrations:** `atlas.clients`, `atlas.client_holdings` (with stock-only CHECK), `atlas.signal_alerts`
2. **Backend API:** client CRUD + holdings management + portfolio watch endpoint
   - `atlas/api/clients.py` — client CRUD
   - `atlas/api/holdings.py` — holdings management per client
   - `atlas/api/portfolio_watch.py` — `/portfolio-watch` aggregated view
   - `atlas/api/alerts.py` — alert list + acknowledge
   - `atlas/models/client.py` — SQLAlchemy models for `clients`, `client_holdings`, `signal_alerts`
3. **Alert engine:** `scripts/nightly_alerts.py` + wire into EC2 cron at 5:30 PM IST
4. **Frontend — `/clients` + `/clients/[id]`:** client list + holdings entry form (reuse `InstrumentPicker`)
5. **Frontend — `/portfolio-watch`:** watch table with current signals
6. **Frontend — `/alerts`:** notification inbox
7. **Frontend — Portfolio Impact panel on regime page:** "X of your clients hold stocks in regime-negative sectors" (minimal change to existing page, driven by joining `atlas.clients` + `atlas.universe_stocks.sector_id`)

## Build Order (Phase 2)

1. **`IMarketDataProvider`** abstraction + `KiteConnectProvider` (handles 500-symbol batching)
2. **`atlas.intraday_prices`** table + APScheduler worker process
3. **Intraday recompute** — call existing `atlas.compute.rs` + `atlas.compute.states` functions, write to shadow tables
4. **SSE endpoint** (`/api/stream/prices`) with timestamp field + stale detection
5. **`useMarketData()` React hook** + live price tiles across existing pages
6. **Email digest** — daily alert summary to advisor at 6 AM IST via SendGrid/SES; in-app inbox remains primary

---

## Resolved Questions

1. **Risk profile:** Track as ENUM (conservative/moderate/aggressive, nullable). Advisor can leave blank.
2. **Cost price entry:** Manual entry in Phase 1. CSV import from Zerodha/Groww is Phase 2.
3. **Alert delivery:** In-app inbox only in Phase 1. Email digest in Phase 2.
4. **Fund/ETF alerts:** Stocks-only in Phase 1 (`CHECK (instrument_type = 'stock')` constraint). MF/ETF in Phase 2 (requires joining `atlas_fund_states_daily`, `atlas_etf_states_daily`).
