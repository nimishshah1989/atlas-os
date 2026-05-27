# TradingView Signal + Auto-Report Integration
**Design Spec — Atlas OS**
Date: 2026-05-13
Status: Draft — pending engineering review

---

## 1. Problem Statement

Atlas identifies high-conviction stocks and sectors quantitatively (conviction score, CTS timing, RS rank, regime state). But a buy/sell decision requires a second, independent confirmation: does the *chart* agree? Currently an analyst must manually open TradingView, apply indicators, and visually confirm — a bottleneck that breaks at scale.

This feature closes that gap. TradingView watches all charts 24/7 via Pine Script. When a technical condition fires, Atlas receives the signal in real-time, cross-validates against its own quantitative layer, generates a structured investment brief (the "Signal Report"), and creates an alert in the Atlas UI. The report format is inspired by 13D Research & Strategy's "What Are The Markets Telling Us?" — each idea represented with dual-timeframe charts, annotated patterns, relative strength context, momentum state, and a narrative that bridges the technical trigger to Atlas's quantitative case.

---

## 2. Design Goals

1. **Real-time** — report generates within 5 seconds of Pine condition firing during market hours
2. **Scale** — covers top 500 NSE stocks + relevant ETFs (~500 instruments)
3. **Dual confirmation** — signal is stronger when both TV Pine and Atlas DB agree; report clearly flags which layer(s) confirmed
4. **13D-quality output** — each report has: dual-timeframe TV chart screenshots, pattern label, RS context, momentum state, Atlas intelligence layer, LLM narrative, performance vs benchmark
5. **Zero manual setup per stock** — alert provisioning is automated; universe changes propagate nightly
6. **Both flows** — batch nightly report for high-conviction picks AND ad-hoc on-demand from any stock page

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ALERT PROVISIONING (nightly)                  │
│  Atlas DB universe  →  Python diff script  →  CSV config        │
│                                ↓                                 │
│              alleyway/add-tradingview-alerts-tool                │
│              (Playwright + TV Premium account)                   │
│              Creates/updates/deletes TV alerts for 500 stocks    │
│              2 charts per stock × 2 conditions = ~2000 alerts    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ (one-time setup, nightly sync)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   TRADINGVIEW (runs 24/7)                        │
│  Pine Script v5 — standardized across all charts                 │
│  Chart 1: Instrument / Nifty 50 (RS + price breakouts)          │
│  Chart 2: Instrument / Sector Index (RS + sector context)        │
│  Conditions: Tier 1-5 (see §6)                                   │
│  Fires webhook POST → Atlas on condition trigger                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │ real-time webhook
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│            ATLAS WEBHOOK RECEIVER  /api/v1/tv/signal            │
│  FastAPI async endpoint — must respond < 3s (TV hard timeout)   │
│  1. Validate payload + secret token                              │
│  2. Enqueue to background task (returns 200 immediately)         │
│  3. Background: cross-validate against Atlas DB signals          │
│  4. Determine confirmation level (TV-only / Atlas-only / Both)   │
│  5. Trigger report generation pipeline                           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                  ┌────────────┴────────────┐
                  ▼                         ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│  ATLAS DB CROSS-CHECK   │   │    TV CHART SCREENSHOT          │
│  pandas-ta: RSI/MACD/   │   │    Playwright headless browser  │
│  EMA computed daily     │   │    Opens TV chart URL           │
│  scipy: HH/HL pivots    │   │    Daily + Weekly timeframe     │
│  Returns: confirmed /   │   │    Chart 1 + Chart 2            │
│  partial / unconfirmed  │   │    Saves PNG to S3/local        │
└─────────────┬───────────┘   └────────────────┬────────────────┘
              │                                 │
              └─────────────┬───────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  REPORT GENERATION ENGINE                        │
│  1. Assemble structured context:                                 │
│     - TV trigger: condition type, tier, timeframe, price        │
│     - Atlas layer: conviction score, CTS state, RS rank,        │
│       sector regime, market regime, performance data            │
│     - Technical computed: RSI, MACD, EMA alignment,             │
│       volume vs avg, HH/HL state                                │
│     - Chart screenshots: daily + weekly for both charts         │
│  2. LLM call (Claude Sonnet) → generate narrative paragraph     │
│  3. Render report HTML                                           │
│  4. Persist to tv_signal_reports table                           │
│  5. Create alert record in atlas_alerts                          │
│  6. Push notification to Atlas frontend (SSE/WebSocket)         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
              ┌────────────────┴───────────────────┐
              ▼                                     ▼
┌─────────────────────────┐           ┌─────────────────────────┐
│   ATLAS SIGNAL FEED     │           │    PDF EXPORT           │
│   /signals page         │           │    On-demand from       │
│   Alert card per signal │           │    report page          │
│   Click → full report   │           │    Playwright PDF       │
│   "Open in TV" button   │           │    print-to-PDF         │
│   Embedded TV iframe    │           └─────────────────────────┘
└─────────────────────────┘
```

---

## 4. New Database Tables

### 4.1 `tv_alert_registry`
Tracks which TV alerts have been provisioned, to enable nightly diff.

```sql
CREATE TABLE tv_alert_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          VARCHAR(20) NOT NULL,          -- NSE:RELIANCE
    chart_type      VARCHAR(20) NOT NULL,          -- 'vs_nifty' | 'vs_sector'
    condition_tier  INTEGER NOT NULL,              -- 1-5
    condition_code  VARCHAR(50) NOT NULL,          -- 'breakout_52w_volume'
    tv_alert_id     VARCHAR(100),                  -- TV internal ID if known
    is_active       BOOLEAN DEFAULT TRUE,
    layout_id       VARCHAR(50) NOT NULL,          -- TV saved layout ID
    webhook_url     VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tv_alert_registry_ticker ON tv_alert_registry(ticker);
CREATE INDEX idx_tv_alert_registry_active ON tv_alert_registry(is_active);
```

### 4.2 `tv_signal_reports`
One row per signal event. The full report lives here.

```sql
CREATE TABLE tv_signal_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker              VARCHAR(20) NOT NULL,
    exchange            VARCHAR(10) NOT NULL DEFAULT 'NSE',
    company_name        VARCHAR(200),
    sector              VARCHAR(100),

    -- Trigger metadata
    triggered_at        TIMESTAMPTZ NOT NULL,
    condition_tier      INTEGER NOT NULL,
    condition_code      VARCHAR(50) NOT NULL,
    condition_label     VARCHAR(200) NOT NULL,      -- "RS breakout vs Nifty 50"
    chart_type          VARCHAR(20) NOT NULL,       -- 'vs_nifty' | 'vs_sector'
    trigger_price       NUMERIC(20, 4),
    trigger_volume      BIGINT,
    volume_vs_avg       NUMERIC(10, 4),             -- e.g. 2.3 = 2.3x avg

    -- Confirmation level
    confirmation_level  VARCHAR(20) NOT NULL,       -- 'dual' | 'tv_only' | 'atlas_only'

    -- Atlas intelligence layer (snapshot at signal time)
    conviction_score    NUMERIC(5, 2),
    conviction_trend    VARCHAR(10),                -- 'rising' | 'falling' | 'stable'
    cts_state           VARCHAR(50),
    rs_rank             INTEGER,
    rs_rank_total       INTEGER,
    rs_percentile       NUMERIC(5, 2),
    sector_regime       VARCHAR(50),
    market_regime       VARCHAR(50),

    -- Technical computed layer
    rsi_14              NUMERIC(6, 2),
    macd_signal         VARCHAR(10),                -- 'bullish_cross' | 'above_zero' | etc.
    ema_alignment       VARCHAR(20),                -- 'all_bullish' | 'above_200' | etc.
    hh_hl_state         VARCHAR(20),                -- 'confirmed_uptrend' | 'hh_only' | etc.
    pattern_label       VARCHAR(100),               -- "Breakout above 18-month resistance"

    -- Performance (snapshot)
    perf_1m             NUMERIC(10, 4),
    perf_3m             NUMERIC(10, 4),
    perf_6m             NUMERIC(10, 4),
    perf_ytd            NUMERIC(10, 4),
    perf_vs_nifty_1m    NUMERIC(10, 4),
    perf_vs_nifty_ytd   NUMERIC(10, 4),

    -- Chart assets
    chart_daily_url     VARCHAR(500),               -- TV deep link daily
    chart_weekly_url    VARCHAR(500),               -- TV deep link weekly
    chart_vs_sector_url VARCHAR(500),               -- TV deep link vs sector
    screenshot_daily    VARCHAR(500),               -- S3 path or local path
    screenshot_weekly   VARCHAR(500),
    screenshot_sector   VARCHAR(500),

    -- Report content
    narrative           TEXT,                       -- LLM-generated paragraph
    report_html         TEXT,                       -- rendered HTML
    verdict             VARCHAR(20),                -- 'bullish' | 'bearish' | 'watch'

    -- Lifecycle
    is_active           BOOLEAN DEFAULT TRUE,
    reviewed_by         VARCHAR(100),
    reviewed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tv_signal_reports_ticker ON tv_signal_reports(ticker);
CREATE INDEX idx_tv_signal_reports_triggered_at ON tv_signal_reports(triggered_at DESC);
CREATE INDEX idx_tv_signal_reports_tier ON tv_signal_reports(condition_tier);
CREATE INDEX idx_tv_signal_reports_confirmation ON tv_signal_reports(confirmation_level);
```

### 4.3 `atlas_signal_alerts`
Lightweight alert feed table (separate from full report for performance).

```sql
CREATE TABLE atlas_signal_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id       UUID REFERENCES tv_signal_reports(id),
    ticker          VARCHAR(20) NOT NULL,
    alert_type      VARCHAR(20) NOT NULL,           -- 'tv_signal' | 'atlas_flag'
    severity        VARCHAR(10) NOT NULL,           -- 'high' | 'medium' | 'low'
    title           VARCHAR(300) NOT NULL,
    summary         VARCHAR(500),
    is_read         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_atlas_signal_alerts_created ON atlas_signal_alerts(created_at DESC);
CREATE INDEX idx_atlas_signal_alerts_read ON atlas_signal_alerts(is_read);
```

---

## 5. Pine Script Conditions (Standardized)

Two chart templates, one Pine Script each. Same script applies to all 500 stocks.

### Chart 1: Instrument / Benchmark (Nifty 50)
**Layout ID:** `tv_layout_vs_nifty` (saved once, URL-parameterized with symbol)

Pine Script plots:
- Price chart with 20/50/200 EMA overlaid
- RS line: `close / request.security("NSE:NIFTY", timeframe.period, close)`
- RSI(14) in pane 2
- MACD(12,26,9) in pane 3
- Volume with 20-day avg line in pane 4

Alert conditions (using `alert()` — one alert covers all, condition encoded in message):
```pine
// T1: 52-week high breakout + volume
t1_breakout = close > ta.highest(high, 252)[1] and volume > ta.sma(volume, 20) * 1.5
if t1_breakout
    alert('{"tier":1,"code":"breakout_52w_volume","chart":"vs_nifty","ticker":"{{ticker}}","exchange":"{{exchange}}","close":{{close}},"volume":{{volume}},"time":"{{timenow}}"}', alert.freq_once_per_bar_close)

// T1b: RS line 52-week high
rs_line = close / request.security("NSE:NIFTY", timeframe.period, close)
t1_rs = rs_line > ta.highest(rs_line, 252)[1]
if t1_rs
    alert('{"tier":1,"code":"rs_breakout_52w","chart":"vs_nifty","ticker":"{{ticker}}","exchange":"{{exchange}}","close":{{close}},"volume":{{volume}},"time":"{{timenow}}"}', alert.freq_once_per_bar_close)

// T2: Higher high formation
pivot_high = ta.pivothigh(high, 10, 10)
prev_pivot_high = ta.valuewhen(not na(pivot_high), pivot_high, 1)
t2_hh = not na(pivot_high) and pivot_high > prev_pivot_high
if t2_hh
    alert('{"tier":2,"code":"higher_high","chart":"vs_nifty","ticker":"{{ticker}}","exchange":"{{exchange}}","close":{{close}},"volume":{{volume}},"time":"{{timenow}}"}', alert.freq_once_per_bar_close)

// T3: Price crosses above 200 EMA
ema200 = ta.ema(close, 200)
t3_ema200 = ta.crossover(close, ema200)
if t3_ema200
    alert('{"tier":3,"code":"cross_above_ema200","chart":"vs_nifty","ticker":"{{ticker}}","exchange":"{{exchange}}","close":{{close}},"volume":{{volume}},"time":"{{timenow}}"}', alert.freq_once_per_bar_close)

// T4: RSI crosses above 50
rsi = ta.rsi(close, 14)
t4_rsi = ta.crossover(rsi, 50)
if t4_rsi
    alert('{"tier":4,"code":"rsi_cross_50","chart":"vs_nifty","ticker":"{{ticker}}","exchange":"{{exchange}}","close":{{close}},"volume":{{volume}},"time":"{{timenow}}"}', alert.freq_once_per_bar_close)

// T5 (Sell): Lower low formed
pivot_low = ta.pivotlow(low, 10, 10)
prev_pivot_low = ta.valuewhen(not na(pivot_low), pivot_low, 1)
t5_ll = not na(pivot_low) and pivot_low < prev_pivot_low
if t5_ll
    alert('{"tier":5,"code":"lower_low","chart":"vs_nifty","ticker":"{{ticker}}","exchange":"{{exchange}}","close":{{close}},"volume":{{volume}},"time":"{{timenow}}"}', alert.freq_once_per_bar_close)
```

### Chart 2: Instrument / Sector Index
Same structure. `request.security` target is sector ETF/index instead of Nifty.
Sector index mapping stored in Atlas DB (`sector_index_map` table, already exists in schema).

---

## 6. Trigger Condition Registry

| Tier | Code | Label | Verdict | Priority |
|---|---|---|---|---|
| 1 | `breakout_52w_volume` | 52-week high breakout with 1.5x volume | Bullish | Critical |
| 1 | `rs_breakout_52w` | RS line vs Nifty hits 52-week high | Bullish | Critical |
| 1 | `rs_sector_breakout_52w` | RS line vs Sector hits 52-week high | Bullish | Critical |
| 1 | `false_breakdown_recovery` | Price reclaims broken support within 5 bars | Bullish | Critical |
| 2 | `higher_high` | New swing high above prior pivot high | Bullish | High |
| 2 | `higher_high_higher_low` | HH + HL within 20 bars (uptrend confirmed) | Bullish | High |
| 3 | `cross_above_ema200` | Price crosses above 200-day EMA | Bullish | Medium |
| 3 | `cross_above_ema50` | Price crosses above 50-day EMA (RS improving) | Bullish | Medium |
| 3 | `golden_cross` | 50-day EMA crosses above 200-day EMA | Bullish | Medium |
| 3 | `all_emas_aligned` | Price > 20/50/200 EMA simultaneously | Bullish | Medium |
| 4 | `rsi_cross_50` | RSI crosses above 50 from below | Bullish | Low |
| 4 | `rsi_breakout_3m_high` | RSI breaks above prior 3-month high | Bullish | Low |
| 4 | `macd_bullish_cross_above_zero` | MACD bullish crossover above zero line | Bullish | Low |
| 5 | `lower_low` | New swing low below prior pivot low | Bearish | High |
| 5 | `rs_breakdown_52w` | RS line vs Nifty hits 52-week low | Bearish | High |
| 5 | `cross_below_ema200` | Price crosses below 200-day EMA | Bearish | Medium |
| 5 | `death_cross` | 50-day EMA crosses below 200-day EMA | Bearish | Medium |

---

## 7. Backend Components

### 7.1 Webhook Receiver — `atlas/api/tv_signals.py`

```python
# POST /api/v1/tv/signal
# Must respond < 3s. Enqueues background task immediately.

async def receive_tv_signal(payload: TVSignalPayload, background_tasks: BackgroundTasks):
    # 1. Validate ATLAS_TV_WEBHOOK_SECRET in payload
    # 2. Deduplicate: same (ticker, condition_code, chart_type) tuple within 60 min = skip.
    #    Timeframe-crossing duplicates (daily vs weekly firing same condition same hour) are
    #    intentionally collapsed — the first one wins, second is discarded.
    # 3. background_tasks.add_task(process_signal, payload)
    # 4. return 200 immediately
```

Allowlist TV source IPs in EC2 security group:
`52.89.214.238`, `34.212.75.30`, `54.218.53.128`, `52.32.178.7`

### 7.2 Signal Processor — `atlas/signals/processor.py`

```python
async def process_signal(payload: TVSignalPayload):
    # 1. Fetch Atlas intelligence snapshot for ticker
    #    - conviction_score, cts_state, rs_rank, sector_regime, market_regime
    # 2. Compute technical layer from Atlas DB OHLCV
    #    - pandas-ta: RSI(14), MACD(12,26,9), EMA(20,50,200)
    #    - scipy.find_peaks: HH/HL state
    #    - volume_ratio = current_volume / sma_volume_20
    # 3. Determine confirmation_level
    #    - 'dual' if Atlas quant also flags this ticker as actionable
    #    - 'tv_only' if Atlas is neutral/no signal
    #    - 'atlas_only' not applicable here (Atlas DB pre-screening is separate flow)
    # 4. Generate chart screenshots (async Playwright)
    # 5. Build structured context dict
    # 6. Call LLM for narrative
    # 7. Render report HTML
    # 8. Persist to tv_signal_reports
    # 9. Create atlas_signal_alerts record
    # 10. Push SSE notification to frontend
```

### 7.3 Technical Cross-Check — `atlas/signals/technical.py`

Uses `pandas-ta` and `scipy.signal`. Reads from existing `ohlcv_daily` table.
No new data sources — Atlas already has Kite-sourced OHLCV for all NSE stocks.

```python
import pandas_ta as ta
from scipy.signal import find_peaks

def compute_technical_snapshot(ticker: str, session) -> TechnicalSnapshot:
    df = fetch_ohlcv(ticker, lookback_days=300, session=session)
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)

    # HH/HL via pivot detection
    highs_idx, _ = find_peaks(df['close'].values, distance=10, prominence=0.02)
    lows_idx, _ = find_peaks(-df['close'].values, distance=10, prominence=0.02)

    hh = len(highs_idx) >= 2 and df['close'].iloc[highs_idx[-1]] > df['close'].iloc[highs_idx[-2]]
    hl = len(lows_idx) >= 2 and df['close'].iloc[lows_idx[-1]] > df['close'].iloc[lows_idx[-2]]

    return TechnicalSnapshot(rsi=..., macd_signal=..., ema_alignment=..., hh=hh, hl=hl, ...)
```

### 7.4 Chart Screenshot — `atlas/signals/screenshot.py`

Playwright async context. Opens TV chart URL with correct symbol + timeframe.
Two screenshots: daily + weekly (same layout, `?interval=D` and `?interval=W`).

```python
TV_CHART_BASE = "https://www.tradingview.com/chart/{layout_id}/?symbol={exchange}:{ticker}&interval={interval}"

async def capture_chart_screenshots(ticker, exchange, layout_id_nifty, layout_id_sector):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Load session cookies for TV Premium account
        # Navigate to chart URL
        # Wait for chart to render (waitForSelector on canvas element)
        # Screenshot → save to /tmp/ → upload to storage
```

TV session cookies stored in EC2 `.env` as `TV_SESSION_ID` + `TV_SESSION_SIGN` (not in code).
Chart screenshots saved to EC2 local path `SIGNAL_SCREENSHOT_DIR` (default `/data/signals/screenshots/`).
`screenshot_daily` / `screenshot_weekly` columns in DB store the EC2 absolute path.
S3 upload is a Phase 3+ enhancement — local storage is sufficient for MVP given single-server architecture.

### 7.5 Report Narrative — `atlas/signals/narrative.py`

Claude Sonnet API call with structured context. Prompt is opinionated and verdict-first.

```python
NARRATIVE_PROMPT = """
You are an experienced equity analyst writing a one-paragraph investment brief.
Be direct and opinionated. Lead with a clear verdict ("The setup appears bullish" / "This chart is flashing a warning").
Explain what the technical trigger means in the context of the stock's quantitative profile.
Do not hedge excessively. Reference specific numbers. 3-4 sentences maximum.

Stock: {ticker} ({company_name})
Trigger: {condition_label}
Conviction: {conviction_score}/10 ({conviction_trend})
CTS State: {cts_state}
RS Rank: #{rs_rank} of {rs_rank_total} ({rs_percentile:.1f}th percentile)
Sector: {sector} — {sector_regime}
Market: {market_regime}
RSI(14): {rsi_14:.1f}
MACD: {macd_signal}
EMA Alignment: {ema_alignment}
HH/HL State: {hh_hl_state}
Volume vs 20-day avg: {volume_vs_avg:.1f}x
Performance vs Nifty (YTD): {perf_vs_nifty_ytd:+.1f}%
"""
```

### 7.6 Alert Provisioning — `atlas/signals/provisioner.py`

Nightly job (pg_cron or systemd timer at 19:00 IST, before market open next day).

```python
def provision_tv_alerts():
    # 1. Fetch current universe from Atlas screener (top 500 by market cap + in-scope)
    # 2. Fetch current tv_alert_registry (active alerts)
    # 3. Diff: new tickers to add, removed tickers to deactivate
    # 4. Generate alleyway tool CSV config for new alerts
    # 5. Run: subprocess.run(["node", "add-alerts-tool/index.js", "--config", csv_path])
    #    — idempotent: existing alerts are left untouched, only net-new are created
    # 6. On completion, mark provisioned alerts active in tv_alert_registry
    # 7. On failure mid-run: log failed tickers, leave registry unchanged for those tickers
    #    — next nightly run re-attempts (idempotent by design)
    # 8. Reconciliation: weekly full-scan of tv_alert_registry vs actual TV alerts
    #    (manual step — Playwright reads TV alert list, diffs against registry)
    # 9. Log: tickers added, removed, failed, total active
```

---

## 8. Frontend Components

### 8.1 Signal Feed Page — `/signals`

New page. Shows chronological feed of all signal reports.

**Signal card** (compact):
- Ticker + company name
- Condition label ("RS breakout vs Nifty 50 — 52-week high")
- Tier badge (color-coded: T1=red, T2=orange, T3=yellow, T4=grey)
- Confirmation badge ("DUAL ✓" or "TV ONLY")
- Conviction score chip
- Triggered at timestamp
- Click → full report page

### 8.2 Signal Report Page — `/signals/[id]`

Full report. Structured like a 13D WATMU page:

```
┌─────────────────────────────────────────────────────────┐
│  NSE:HDFCBANK  HDFC Bank Ltd.         13-May-2026 14:32 │
│  RS Breakout vs Nifty 50 — 52-week high                 │
│  ██████████ DUAL CONFIRMED                              │
├─────────────────────────────────────────────────────────┤
│  ATLAS INTELLIGENCE                                      │
│  Conviction: 8.4/10 ▲  |  CTS: BUY Stage 2             │
│  RS Rank: #12 / 487 (97.5th pct)                       │
│  Sector: Banking — Bullish Expansion                    │
│  Market: Nifty Risk-On                                  │
├─────────────────────────────────────────────────────────┤
│  [Chart: HDFCBANK vs NIFTY - Daily]  [Open in TV ↗]    │
│  [Chart: HDFCBANK vs BANKEX - Daily] [Open in TV ↗]    │
├─────────────────────────────────────────────────────────┤
│  TECHNICAL SNAPSHOT                                      │
│  RSI(14): 61.2  |  MACD: Bullish crossover above zero  │
│  EMA: Price > 20/50/200 (all aligned)                   │
│  Pattern: Breakout above 18-month resistance, 2.3x vol  │
│  HH/HL: Confirmed uptrend                               │
├─────────────────────────────────────────────────────────┤
│  PERFORMANCE                                             │
│  1M: +8.4% vs Nifty +2.3%  |  YTD: +31.4% vs +8.7%   │
├─────────────────────────────────────────────────────────┤
│  NARRATIVE                                               │
│  "HDFC Bank's breakout above the ₹1,820 resistance..."  │
├─────────────────────────────────────────────────────────┤
│  [Download PDF]  [Mark Reviewed]  [Open in TV ↗]        │
└─────────────────────────────────────────────────────────┘
```

Charts shown as screenshots (PNG) with TV deep-link button next to each.
Embedded iframe (react-tradingview-embed) shown below for live view.

### 8.3 Stock Page Integration

On existing stock deep dive page, add:
- "Signal History" tab — shows last 5 signal reports for this ticker
- "Open in TV" button (deep link to saved layout)
- Alert badge if active signal (< 24h)

### 8.4 Ad-hoc Report Trigger

Button on stock page: "Generate Report Now"
→ POST `/api/v1/tv/generate-report` with ticker
→ Runs processor synchronously (no TV webhook needed)
→ Uses Atlas DB data + Playwright screenshot
→ Returns report in ~10-15 seconds

---

## 9. TV Account Setup (One-Time Manual Steps)

These are done once by the team, not automated:

1. **Create saved layouts** in TV Premium account:
   - Layout A: `atlas_vs_nifty` — Price + 20/50/200 EMA + RS vs Nifty + RSI + MACD + Volume
   - Layout B: `atlas_vs_sector` — same structure, RS vs sector index
   - Note the layout IDs from URL (e.g., `3jUkqZqY`)

2. **Publish Pine Script indicators** as private scripts to TV account:
   - One Pine script per chart type (2 scripts total)
   - Save layout with indicator applied

3. **Enable 2FA** on TV account (required for webhook alerts)

4. **Note session cookies** for Playwright: `sessionid` + `sessionid_sign`
   - Store in EC2 `.env` as `TV_SESSION_ID` + `TV_SESSION_SIGN`

5. **Upgrade to Ultimate** if universe > 400 stocks (Ultimate = 2000 concurrent alerts)

6. **Allowlist EC2 IP** in TV account settings for webhook

---

## 10. Configuration (.env additions)

```bash
# TradingView
TV_WEBHOOK_SECRET=<random_32_char_string>         # validated on every incoming webhook
TV_SESSION_ID=<from_browser_cookies>              # for Playwright alert provisioning
TV_SESSION_SIGN=<from_browser_cookies>            # paired with session_id
TV_LAYOUT_ID_VS_NIFTY=<layout_id>                # saved layout A
TV_LAYOUT_ID_VS_SECTOR=<layout_id>               # saved layout B
TV_ACCOUNT_EMAIL=<tv_login_email>

# Report storage
SIGNAL_SCREENSHOT_DIR=/data/signals/screenshots   # EC2 local path
SIGNAL_REPORT_BASE_URL=https://atlas.jslwealth.in/signals
```

---

## 11. Migration

New migration: `migrations/versions/062_tv_signal_reports.py`

Creates:
- `tv_alert_registry`
- `tv_signal_reports`
- `atlas_signal_alerts`
- Indexes as defined in §4

---

## 12. Testing Strategy

### Unit tests
- `tests/unit/signals/test_technical.py` — `compute_technical_snapshot()` with fixture OHLCV data
- `tests/unit/signals/test_narrative.py` — narrative prompt assembly, mock LLM call
- `tests/unit/signals/test_processor.py` — confirmation level logic

### API tests
- `tests/api/test_tv_signals.py`
  - Valid webhook payload → 200, task enqueued
  - Invalid secret → 401
  - Duplicate within 60 min (same ticker+condition+chart_type) → 200, deduped (no new report)
  - Missing fields → 422

### Integration tests (EC2 only)
- Full signal → report pipeline with real Atlas DB data
- Playwright screenshot capture (mocked TV URL for CI, real in staging)

---

## 13. Rollout Plan

**Phase 1 — Infrastructure (Week 1)**
- Migration 062 — tables
- Webhook receiver endpoint (returns 200, logs payload, no processing yet)
- TV side: allowlist EC2 IP, create layouts, write Pine Script
- Manual test: fire one alert from TV → confirm Atlas receives it

**Phase 2 — Core Pipeline (Week 2)**
- Signal processor (no screenshots, no LLM yet)
- Technical cross-check (pandas-ta + scipy)
- Basic report record creation
- Alert feed API + minimal frontend card

**Phase 3 — Report Quality (Week 3)**
- Playwright screenshot integration
- LLM narrative (Claude Sonnet)
- Full report page frontend
- PDF export

**Phase 4 — Alert Provisioning (Week 4)**
- Alleyway tool integration
- Nightly provisioning job
- **Conditions provisioned per stock: Tier 1 + Tier 2 only (5 conditions × 2 charts = 10 alerts per stock)**
  - At 500 stocks: 5,000 alerts → requires TV Ultimate plan (2,000 technical + 2,000 price = 4,000 ceiling)
  - **MVP universe: top 200 stocks × 10 alerts = 2,000 alerts → fits TV Premium (800 tech + 400 price)**
  - Tier 3/4 conditions are computed in Atlas DB only (not provisioned as TV alerts) — they enrich report context but don't trigger independently
  - Tier 5 (sell) conditions: 2 conditions × 2 charts = 4 per stock, provisioned alongside buy conditions
- Start with top 50 stocks, validate, then scale to 200 (Premium) or 500 (Ultimate)

**Phase 5 — Polish + Ad-hoc (Week 5)**
- "Generate Report Now" button on stock pages
  - This flow uses EOD price data (most recent close), NOT intraday live price
  - Playwright screenshots a TV chart with most recent close loaded — charts always show last close when opened via URL without a live session broadcasting ticks. This is acceptable for EOD ad-hoc reports.
  - Intraday live reports are TV-webhook-driven only (real-time flow in Phase 1-2)
- Signal history tab on stock deep dive
- Performance tracking (did the signal play out? — 5/10/20 day forward return vs Nifty)

---

## 14. Open Questions (to resolve before implementation)

1. **TV account plan**: Premium (800 alerts, up to ~200 stocks MVP) vs Ultimate (4,000 alerts, up to ~400 stocks). Resolved at provisioning time — spec supports both via universe size config.
2. **Screenshot storage**: EC2 local `/data/signals/screenshots/` for MVP. S3 migration is a Phase 3+ enhancement, not blocking.
3. **Pine Script layout sharing**: Layouts live on one TV account. If multiple team members need to view the same layout, share via TV's "Make it mine" feature — or use a shared team TV account for Atlas alerts.
4. **Sector index mapping**: Needs confirmation per sector. Proposed symbols — Banking: `NSE:BANKNIFTY`, IT: `NSE:CNXIT`, FMCG: `NSE:CNXFMCG`, Auto: `NSE:CNXAUTO`, Pharma: `NSE:CNXPHARMA`, Metal: `NSE:CNXMETAL`, Realty: `NSE:CNXREALTY`, Energy: `NSE:CNXENERGY`, Infra: `NSE:CNXINFRA`, Media: `NSE:CNXMEDIA`. Verify all resolve on TV before provisioning.
5. **Promoter buying data**: BSE filings — future enhancement, out of scope for this spec.
6. **Alert dedup window**: Resolved — 60 minutes per (ticker, condition_code, chart_type) tuple. See §7.1.

---

## 15. What This Is Not

- Not a trading bot (no order execution)
- Not a full TV Charting Library integration (uses screenshots + deep links, not embedded Pine)
- Not a replacement for analyst judgment (reports go to a review queue, not auto-published to clients)
- Not real-time intraday charting inside Atlas (SP08/SP10 handles intraday separately)
