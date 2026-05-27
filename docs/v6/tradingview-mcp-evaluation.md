# TradingView MCP — Evaluation for Atlas v6

**Date:** 2026-05-26 (overnight)
**Context:** User suggested exploring TradingView MCP as a data source / metric provider for stocks
**Verdict:** Useful supplementary surface; NOT a primary backbone — NSE/RBI/MOSPI remain primary

---

## What "TradingView MCP" means today

TradingView itself doesn't publish an official MCP server. The community-built ones generally fall into these categories:

| MCP flavor | What it does | Reliability | Cost |
|---|---|---|---|
| **TradingView screener scrape MCP** | Pulls TradingView's stock screener results (technicals, fundamentals, ratings) | Medium (HTML structure changes occasionally) | Free; rate-limited |
| **TradingView Pine Script alert webhook MCP** | Receives webhook from a Pine Script on TradingView; surfaces as MCP tool | High (push model; one-way) | Pine Pro plan ($15-60/mo) |
| **TradingView chart screenshot MCP** | Generates chart images from a TradingView URL | High | Free |
| **TradingView "datafeed" MCP (light)** | Wraps tvDatafeed Python lib (unofficial) for historical OHLCV | Medium-low; tvDatafeed often broken (depends on TV auth state) | Free |
| **TradingView indicator-eval MCP** | Calls TradingView's `scanner.tradingview.com` API for one of ~70 built-in technicals (RSI, MACD, ADX, etc.) per ticker | Medium (unofficial endpoint) | Free; rate-limited |

The most useful for Atlas v6 is **#5 (indicator-eval)** — it gives 70+ technical indicators per ticker with one HTTP call. The least useful is #4 (datafeed) since we already have 19-year `de_equity_ohlcv`.

---

## Where TradingView fits in the Atlas v6 stack

### Already covered by current backend (no TradingView needed)

- OHLCV: `de_equity_ohlcv` (4.7M rows, 2007+)
- EMA / SMA / RSI / volume features: `atlas_stock_metrics_daily` (computed nightly)
- Sector classification: `atlas_universe_stocks.sector`
- Cell signals: `atlas_signal_calls` + `atlas_cell_definitions`
- RS calculations: native via `de_index_prices` joins

### Could be supplemented by TradingView

| Need | TradingView source | Atlas alternative |
|---|---|---|
| **Stock fundamentals snapshot** (P/E, ROE, debt/equity, etc.) | TradingView screener fields | NSE XBRL parser (Phase C5 — not built; this is the gap TradingView could close fastest) |
| **Long-tail technicals** (Stochastic, MFI, OBV, Williams %R, etc.) | TradingView indicator-eval API | Build our own (extends `atlas_stock_metrics_daily`) |
| **TradingView "Strong Buy/Buy/Neutral/Sell/Strong Sell" rating** | Screener rating column | Our own conviction tape (better — methodology-locked) |
| **Aggregated analyst price target** | Screener targets | Not currently — pure ask |
| **Pre-built screener queries** ("RSI < 30 and price > 200MA") | Screener URL params | Build native — keeps methodology consistent |

---

## Recommendation for v6.0

**Use TradingView MCP for ONE specific gap: stock fundamentals quick-fill.**

Phase C5 (NSE XBRL parser) is a substantial build — XBRL parsing, 40 quarters × 750 stocks backfill. TradingView's screener has P/E, P/B, EPS, ROE, dividend yield, market cap pre-aggregated. We could use TradingView MCP to populate `atlas_stock_fundamentals_quarterly` (table planned for migration 098 next session) for the LATEST quarter — gets v6 Page 05a deep-dive shipping faster — while NSE XBRL parser runs as a parallel proper-source workstream.

**Tradeoffs:**
- Pro: One HTTP call per stock instead of XBRL parsing per filing
- Pro: Already covers ratio derivations we'd otherwise compute
- Pro: Free
- Con: TradingView HTML/API can change without notice
- Con: Latest-quarter only; historical fundamentals need NSE XBRL
- Con: Single source = single point of failure
- **Mitigation:** treat TradingView as PROVISIONAL — proper NSE XBRL ingest is the authoritative path; TradingView fills the gap until then

**Decision:** approved for fundamentals fast-fill ONLY. NOT for OHLCV, NOT for technicals (we compute our own), NOT for RS, NOT for ratings. Single-purpose tool.

---

## Source priority per CLAUDE.md (unchanged)

1. NSE / BSE official (free, official)
2. RBI bulletins (free)
3. MOSPI (free)
4. NSDL CMOTS (free)
5. FRED API (free)
6. AMFI (free)
7. **TradingView MCP** — provisional for fundamentals fast-fill only (NEW)
8. ICE / Bloomberg (paid; only if no free)
9. yFinance — **last resort, breaks frequently**

---

## What to do next session (if TradingView path is approved)

1. Set up a community TradingView MCP server locally
2. Test pulling fundamentals for 5-10 sample stocks (Reliance, HDFC Bank, TCS, Infosys, Wipro)
3. Map TradingView field names → our `atlas_stock_fundamentals_quarterly` schema (migration 098)
4. Run a one-time batch fill for 750 stocks via TradingView MCP
5. In parallel, build the NSE XBRL parser as the authoritative source — TradingView gets a clear "provisional" flag in the table

---

## What I am NOT proposing

- Replacing any current data source with TradingView
- Using TradingView for OHLCV (we have 19yr clean data)
- Using TradingView for the closed-loop methodology engine (would corrupt the IP)
- Subscribing to TradingView paid tiers (Pine, Premium, Pro, etc.) — free tier MCPs only

TradingView remains a supplementary surface, not the backbone. The Atlas methodology and computations stay on Atlas-owned data and code.
