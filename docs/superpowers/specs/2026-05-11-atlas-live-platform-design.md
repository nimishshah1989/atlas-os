# Atlas Live Platform — Design Spec
**Date:** 2026-05-11
**Status:** Premises confirmed | Ready for CEO review
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
3. During market hours, prices update every 15 minutes and signal-sensitive metrics (RS pctile, trend state) refresh
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
│  atlas.client_   │  holdings        │  atlas.signal_alerts      │
│  advisors        │  cost_basis,qty  │  in-app inbox             │
│                  │  instrument_id   │  email digest (optional)  │
└──────────────────┴──────────────────┴───────────────────────────┘
         │                  │                      │
         └──────────────────┴──────────────────────┘
                            │
                  JOIN: client_holdings
                  × atlas_stock_states_daily
                  × atlas.decisions
                  = Portfolio Health View

┌─────────────────────────────────────────────────────────────────┐
│                       PHASE 2 (Intraday)                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  IMarketData     │  15-min Compute  │  SSE Push                 │
│  Provider        │  fast_metrics    │  /api/stream/prices       │
│  abstraction     │  (price-sens     │  EventSource in           │
│  KiteConnect     │  metrics only)   │  frontend                 │
│  TrueData/GDFL   │  APScheduler     │  live price tiles         │
└──────────────────┴──────────────────┴───────────────────────────┘
```

---

## Phase 1: Client Portfolio Tracking + Alert Engine

### New Data Model

**`atlas.clients`**
```
id          UUID PK
name        TEXT NOT NULL
email       TEXT
phone       TEXT
risk_profile ENUM (conservative/moderate/aggressive)
advisor_note TEXT
created_at  TIMESTAMPTZ NOT NULL
updated_at  TIMESTAMPTZ NOT NULL
```

**`atlas.client_holdings`**
```
id              UUID PK
client_id       UUID FK → atlas.clients (index)
instrument_id   TEXT NOT NULL  (e.g. NSE:HDFCBANK)
instrument_type ENUM (stock/mf/etf)
quantity        NUMERIC(20,4) NOT NULL
avg_cost_price  NUMERIC(20,4) NOT NULL  (₹, never float)
purchase_date   DATE
model_portfolio_id UUID FK → atlas.strategy_fm_custom_portfolios (nullable)
is_active       BOOLEAN DEFAULT TRUE
created_at      TIMESTAMPTZ NOT NULL
updated_at      TIMESTAMPTZ NOT NULL
```

**`atlas.signal_alerts`**
```
id              UUID PK
client_id       UUID FK → atlas.clients (index)
holding_id      UUID FK → atlas.client_holdings (index)
instrument_id   TEXT NOT NULL
alert_type      ENUM (state_degraded/regime_change/rs_drop/exit_signal)
prev_value      JSONB  (what was the state/RS before)
curr_value      JSONB  (what is it now)
triggered_at    TIMESTAMPTZ NOT NULL
acknowledged_at TIMESTAMPTZ (NULL = unread)
created_at      TIMESTAMPTZ NOT NULL
```

### API Endpoints

```
GET  /api/clients                   list all clients
POST /api/clients                   create client
GET  /api/clients/{id}              client detail
PUT  /api/clients/{id}              update client
GET  /api/clients/{id}/holdings     client's holdings with current Atlas signals
POST /api/clients/{id}/holdings     add holding
DELETE /api/clients/{id}/holdings/{holding_id}  remove holding

GET  /api/portfolio-watch           all holdings across all clients, current signals
GET  /api/alerts                    all unacknowledged signal alerts
POST /api/alerts/{id}/acknowledge   mark alert as read
```

### Portfolio Watch View (the core screen)

A single table showing every holding across all clients, enriched with current Atlas signals:

```
Client    | Instrument   | Qty  | Avg Cost | CMP  | P&L    | RS State  | Signal  | Alert?
----------|--------------|------|----------|------|--------|-----------|---------|-------
Sharma    | HDFCBANK     | 500  | ₹1,450   | 1,620| +11.7% | Leader    | HOLD    |  —
Sharma    | BAJFINANCE   | 200  | ₹6,800   | 5,900| -13.2% | Weakening | WATCH   | ⚠️ RS drop
Mehta     | INFY         | 300  | ₹1,200   | 1,310| +9.2%  | Leader    | BUY     |  —
```

- Sortable by: client, P&L, RS state, signal, alert status
- Filterable by: alert type, signal, instrument type
- Click instrument → deep dive page (existing)
- Click client → client holdings view
- Alert badge → acknowledgeable inline

### Nightly Alert Engine

Background job runs at 5:30 PM IST (after nightly compute):

1. Fetch today's `atlas_stock_states_daily` + `atlas.decisions`
2. Compare against yesterday's snapshot per holding
3. Detect: state downgrades (Leader→Weakening, Weakening→Laggard), new exit signals, regime changes affecting sector
4. Write `atlas.signal_alerts` rows for any detected changes
5. On next page load, unacknowledged alerts surface in notification inbox

### Model Portfolio Linking

When `holding.model_portfolio_id` is set:
- Show drift: "Client holds 500 HDFC Bank. Model says 15% weight. Current allocation: 18%."
- Flag when model says exit an instrument the client still holds
- No auto-rebalancing. Advisory only. Advisor acts on the drift.

---

## Phase 2: Intraday Data Layer

### IMarketDataProvider Abstraction

```python
# atlas/market_data/provider.py
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime

class MarketDataSnapshot:
    symbol: str
    ltp: Decimal          # last traded price
    open: Decimal
    high: Decimal
    low: Decimal
    volume: int
    timestamp: datetime

class IMarketDataProvider(ABC):
    @abstractmethod
    def get_snapshot(self, symbols: list[str]) -> list[MarketDataSnapshot]: ...

    @abstractmethod
    def is_market_open(self) -> bool: ...
```

**Default implementation:** `KiteConnectProvider` using Kite Connect WebSocket API (₹500/month, internal use OK).

**Swap path:** Implement `TrueDataProvider` or `GDFLProvider` with same interface. Change `MARKET_DATA_VENDOR=kite` env var. Zero application code changes.

### 15-Minute Polling Engine

APScheduler job, runs 9:15 AM – 3:30 PM IST on market days:

1. `provider.get_snapshot(all_active_symbols)` — ~2000 NSE symbols
2. Store in `atlas.intraday_prices` (rolling 1-day window, pruned at EOD)
3. Recompute price-sensitive metrics: RS pctile (price-relative), EMA ratio, trend direction
4. Publish update event to SSE channel

### SSE Push to Frontend

```python
# FastAPI SSE endpoint
@router.get("/api/stream/prices")
async def price_stream():
    async def event_generator():
        while True:
            snapshot = await get_latest_intraday_snapshot()
            yield f"data: {snapshot.json()}\n\n"
            await asyncio.sleep(15)
    return EventSourceResponse(event_generator())
```

Frontend `useMarketData()` hook subscribes via `EventSource`. Price tiles show live LTP + "Updated 2 min ago" freshness badge.

---

## UI Changes (Phase 1)

### New Pages
- `/clients` — client list with quick stats (# holdings, # active alerts)
- `/clients/[id]` — client holdings table + alert history
- `/portfolio-watch` — all holdings across all clients, sortable/filterable
- `/alerts` — notification inbox for signal degradation events

### Existing Pages (minimal changes)
- Nav: add "Clients" and "Portfolio Watch" links
- Stock deep dive: add "Clients holding this" badge (count + click to see which clients)
- Regime page: add "Portfolio Impact" panel — how many client holdings are in sectors affected by current regime

### Live Feel (Phase 2 additions to existing pages)
- Every price display: LTP tile with "Updated Xm ago" badge
- Screener rows: price column updates in-place via SSE
- Deep dive header: live price + intraday RS change

---

## What is NOT in Scope

- Multi-tenancy / multiple advisory firms
- Client-facing portal (clients cannot log in; advisors use Atlas)
- Automated trade execution or order routing
- SMS/WhatsApp alert delivery (in-app + optional email only)
- Real-time tick data (15-min polling is the minimum viable freshness)
- Historical P&L / XIRR calculation (day-end mark-to-market only in Phase 1)

---

## What Already Exists (Reuse Map)

| Sub-problem | Existing code | Reuse how |
|---|---|---|
| Portfolio construct (model) | `atlas.strategy_fm_custom_portfolios` | `model_portfolio_id` FK in holdings |
| Instrument picker | `frontend/src/components/portfolio/InstrumentPicker.tsx` | Reuse in holdings entry form |
| Signal states (stocks) | `atlas_stock_states_daily` | JOIN with client_holdings for watch view |
| Decisions (buy/hold/sell) | `atlas.decisions` table | Populate Signal column in watch table |
| Deep dive pages | All existing `/stocks/[symbol]`, `/funds/[id]`, `/etfs/[ticker]` pages | Link from watch table rows |
| Health freshness | `atlas.health_freshness` | Drive "data as of" staleness indicators |
| Backtest engine | `atlas/simulation/backtest/engine.py` | Future: simulate what client portfolio would have returned |

---

## Build Order (Phase 1)

1. DB migrations: `atlas.clients`, `atlas.client_holdings`, `atlas.signal_alerts`
2. Backend API: client CRUD + holdings management (FastAPI, ~4 endpoints)
3. Portfolio Watch query: JOIN holdings × states × decisions (single SQL CTE)
4. Alert engine: nightly diff script (new `scripts/nightly_alerts.py`)
5. Frontend: `/clients`, `/clients/[id]`, `/portfolio-watch` pages
6. Frontend: `/alerts` notification inbox
7. Nav updates + "Clients holding this" badge on deep dives

## Build Order (Phase 2, after Phase 1 ships)

1. `IMarketDataProvider` abstraction + `KiteConnectProvider`
2. APScheduler integration in FastAPI app startup
3. `atlas.intraday_prices` table + fast metric recompute
4. SSE endpoint + `useMarketData()` React hook
5. Live price tiles across existing pages

---

## Open Questions (for CEO review)

1. Should `atlas.clients` track a formal "risk profile" or just free-text advisor notes?
2. Average cost price — do advisors enter manually, or should we support CSV import from Zerodha/Groww statements?
3. Alert delivery: in-app inbox only first, or wire email digest in Phase 1?
4. Should the nightly alert engine also handle fund/ETF holdings, or stocks-only in Phase 1?
