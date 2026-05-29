# Stock Detail Page — Backlog & Strategic Questions

**Status:** Working build shipped on `feat/tv-integration` (commits `c5cd570e` → `930d82b3`).

## What ships in v2 (2026-05-29)

The stock detail page at `/stocks/{symbol}` now renders **14 sections** in a single scroll:

1. **TraderViewHeader** — verdict pill (BUY/ACCUMULATE/WATCH/HOLD/AVOID/SELL/WAIT), tier, verdict source, since-call return, conviction breakdown
2. **EventHeader** — symbol, sector, index badges, stage label, dwell days, peer rank, 4 metric cells (price/3M return/RS percentile/conviction)
3. **GatesPanel** — 5 investability gates (strength, direction, risk, sector, market) with PASS/FAIL/N/A dots, the value that triggers each, derived CLEAR vs WAIT verdict
4. **MultiTimeframeReturnsTable** — 1W/1M/3M/6M/12M absolute returns + alpha vs Nifty
5. **SectorContextStrip** — sector state, breadth, sector rank in market, stock rank in sector
6. **Sector + stock 12M sparklines** — TradingView mini overview widgets side by side
7. **StockChartPanel** — TradingView Advanced Chart (light theme, weekly, EMA20/50/200 overlays, volume), Atlas Chart Reading (server-generated commentary), 5 fundamental pills (P/E, P/S, P/B, Debt/Eq, ROE)
8. **RSConfirmationPanel** — stock-vs-sector + stock-vs-Nifty ratio charts with resistance lines (Recharts) and breakout-status badges
9. **ConvictionDecompositionPanel** — horizontal bars of `contributing_signals` JSONB from `atlas_stock_conviction_daily`
10. **SparklineTrajectoryGrid** — 12 Atlas-derived metric sparklines: RS pctile, 3M return, EMA20/EMA10 ratios, extension, drawdown ratio, max drawdown, volume ratio, average volume, ATR, alpha vs Nifty, volume expansion
11. **LifecyclePanel** — days in stage, volume trend, EMA20 position, extension from 200D EMA, lifecycle reading
12. **TVTechnicalAnalysis** — TradingView composite Buy/Sell gauge with multi-timeframe consensus
13. **PeerMatrix** — top-4 sector peers vs parent stock across 8 metrics
14. **TVFinancials** — TradingView financials widget (revenue, EBITDA, EPS over quarters)
15. **TVNews** — TradingView curated news feed for the symbol
16. **Supporting Detail drawers** — TV Company Profile, Weinstein stage history (DwellTimeline), Component Scorecard, signal_call audit ledger
17. **Act** — position sizing widget

## Backend extensions committed (NOT yet deployed to EC2)

- **Migration 118** — 5 fundamental columns on `atlas.tv_metrics` (pe_ttm, ps_current, pb_fbs, debt_to_equity, roe)
- **Migration 119** — 57 additional columns on `atlas.tv_metrics` (oscillators, MAs, perf, volatility, fundamentals, EV ratios)
- **screener.py** fetches all 76 columns in nightly TV screener pull
- `GET /v1/stocks/{symbol}/rs-ratios` — stock vs sector + stock vs Nifty ratio time series
- `GET /v1/stocks/{symbol}/peer-matrix` — parent + top-4 sector peers
- `GET /v1/tv/metrics/{symbol}` — returns all 76 TV columns

**Deploy steps for EC2:**
```
ssh jsl-wealth-server
cd ~/atlas-os && git pull
alembic upgrade head        # applies 118 + 119
python -m atlas.tv.screener # one-off fetch of all 76 cols
systemctl restart atlas-internal-recompute  # rebuild routes
```

## Open question: yFinance / Claude finance plugins

**User raised:** "Claude has launched plugins, yFinance, which has plugins of portfolio management, research, of everything, and we are using those capabilities, or at least that framework, for the Indian context."

**Status:** Acknowledged as a parallel strategic thread. Not yet researched in depth. The current build uses TradingView's `tradingview-screener` Python package as the data backbone (76 metrics across price/technical/fundamental). Switching backbones from TV to yFinance/Claude finance plugins is a separate architecture decision that requires:

1. Confirming yFinance NSE coverage parity vs TradingView (TV has confirmed NSE coverage; yFinance NSE coverage historically had gaps and used `.NS` suffix)
2. Latency/refresh-cadence comparison (TV screener is realtime-ish; yFinance is delayed and rate-limited heavily)
3. Coverage of the 57 columns we just added in migration 119 — many are TV-proprietary composite signals (`Recommend.All`, `Recommend.MA`, technical rating sub-signals)
4. Cost: TV widget embed is free; Claude finance plugins require API spend

**My recommendation:** Keep TV as the data backbone for v2. Treat Claude finance plugins as a **research/agent surface** (Hermes asks the Claude finance plugin for analyst takes, alongside our own scorecard) rather than a data replacement. This avoids re-architecting the screener pipeline that just shipped.

**Action:** Decide in next planning session whether to:
- (a) Keep TV-only (current state) and add Claude finance plugins to Hermes agents
- (b) Run a 2-week parallel A/B between TV screener and yFinance to compare coverage/cost/freshness
- (c) Migrate fully to yFinance + Claude finance plugins (substantial refactor)

## Known issues to address next session

1. **TV widget "symbol only available on TradingView" modal** — appears on all NSE stock iframes for users without TradingView Pro. This is a TV licensing constraint, not a code bug. Workarounds:
   - Embed the iframe in a way that bypasses the modal (some TV docs mention `client_id` registration)
   - Replace the main chart with our own Recharts candlestick using `de_equity_ohlcv` data (loses TV's drawing tools but eliminates the modal)
   - Accept the modal as a "click through" friction for free TV users

2. **DB connection pool exhaustion** — bumped pool from 10 → 14 with shorter idle_timeout. Stock detail page now does 11 concurrent queries in batch 1 + 7 in batch 2; risk of pool exhaustion under load remains. Long-term fix is to move to Supabase transaction-mode pooler (port 6543) and refactor `sql.begin() + SET LOCAL` to use explicit `SET` statements that survive the connection drop.

3. **Apple chart bug** — caused by `allow_symbol_change=1` letting TV drift the symbol when an embed is loaded from a cached cookie. Fixed in commit `930d82b3` by switching to `URLSearchParams` and `allow_symbol_change=false`.

4. **Conviction decomposition** — `contributing_signals` JSONB is parsed but the data is sparse (~3% of stocks have populated signals). For most stocks the panel will be hidden. Backend work needed to populate `contributing_signals` consistently in `atlas/intelligence/conviction/persistence.py`.

5. **Multi-timeframe returns table** — many of the fields (`ret_1w`, `ret_1m`, `ret_6m`, `ret_12m`, `alpha_3m`, `alpha_6m`) are not in the `MetricHistoryRow` returned by `getStockMetricHistory`. The table will show `—` for those columns until the SQL is extended to project them.

## Template for ETF / Fund / Sector pages

This stock detail page is the **template**. The shape transfers as:

| Section | Stock | ETF | Fund | Sector |
|---|---|---|---|---|
| Verdict | TraderViewHeader | ETFTraderHeader | FundTraderHeader | SectorTraderHeader |
| Identity | EventHeader | ETFHero | FundHero | SectorHero |
| Gates | 5 investability gates | tracking error gate, AUM gate | expense ratio, age, AUM | sector breadth gate |
| Returns | 1W/1M/3M/6M/12M abs + alpha | same vs benchmark | same vs category | sector-relative |
| Context | sector context strip | category context | category context | macro regime |
| Chart | TV chart NSE:SYM | TV chart NSE:ETF | NAV chart (Atlas-built) | sector index chart |
| Substantiation | gates + conviction decomp | premium/discount + tracking | rolling alpha + risk | breadth + leadership |
| Trajectory | 12 Atlas sparklines | 12 ETF metrics | 12 fund metrics | sector sparklines |
| Peers | top-4 sector peers | top-4 category ETFs | top-4 category funds | sector ranking |
| TV widgets | financials, news, profile, technical | same | same | macro events |
| Detail drawers | stage history, scorecard, signal calls | tracking history, holdings | rolling history, holdings | sector rotation history |
| Act | position sizing | portfolio add | switch proposal | sector tilt |

Sector page becomes the **abridged** version (same shape but fewer panels, more breadth-focused).
