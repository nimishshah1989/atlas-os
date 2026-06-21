# Atlas Six-Lens — Data Inventory (tables & metrics)

> What each lens consumes, from where, into which table. Grounded in the **real**
> `atlas.tv_metrics` columns (already in prod) + Theta's actual schema (to inherit)
> + the clean Kite foundation we just built. Status: ✅ have · 🔧 build/inherit · ⚠️ gap.

## Output (the product of all lenses)
`atlas.atlas_lens_scores_daily` — one row per (instrument_id, date):
`technical, fundamental, valuation, catalyst, flow, policy` (each 0–100) +
`composite, conviction_tier, risk_flags(jsonb)` + the sub-component breakdown.
The same shape rolls up to **sector** and **ETF/fund** by cap/holdings weighting.

---

## Lens 1 · TECHNICAL ✅ (data built today)
**Source:** `foundation_staging.technical_daily` (from 25y Kite OHLCV).
**Have:** `ema_21/50/200, rsi_14, ret_1d…ret_12m, rs_{1d…12m}_{n50,n500}, above_ema_{21,50,200}`.
**Components → metrics:**
- Trend → EMA 21/50/200 alignment + slope; price vs EMA-200 ✅
- Relative Strength → `rs_*_n500` + `rs_*_sector` (sector RS to add) ✅
- Volatility Contraction → ATR(14) + Bollinger-width squeeze 🔧 *(derive from OHLCV — ~2 cols to add)*
- Volume / Participation → volume vs 30/60d avg + delivery% 🔧 *(derive; delivery% not in Kite — optional)*

## Lens 2 · FUNDAMENTAL *(quality + operating-leverage, merged)*
**Source A — levels, ✅ from `atlas.tv_metrics`:** `roe, roa, roic, operating_margin,
net_margin, gross_margin, debt_to_equity, current_ratio, quick_ratio,
revenue_growth_yoy, eps_growth_yoy, revenue_ttm, eps_diluted_ttm, book_value_per_share`.
**Source B — multi-year history, ⚠️ GAP:** ROCE *inflection*, margin *streak*,
deleveraging *trajectory* need 10y annual / 8q financials. TV scanner is **snapshot only**.
→ proper source = **NSE XBRL quarterly results** (official, robust) — build a fetcher,
or run Fundamental v1 on *levels only* and add trend signals once history exists.
**Components → metrics:** Profitability (ROCE/ROE level ✅ + trend ⚠️) · Margin
(level ✅ + streak ⚠️) · Growth (rev/eps YoY ✅) · Balance sheet (D/E, net-cash level ✅ + deleveraging ⚠️).
**Output:** `atlas.lens_fundamental_daily`.

## Lens 3 · VALUATION ✅ (neutral descriptor, from `atlas.tv_metrics`)
**Metrics:** `pe_ttm, pb_fbs, ps_current, ev_ebitda, ev_sales, price_fcf, peg_ratio,
dividend_yield, market_cap, enterprise_value` + **sector-median PE** (computed cross-universe).
Snapshot is correct for valuation — **no history needed.** TV ✅.
**Components:** Relative cheapness (vs sector median) · Absolute cheapness (PE/EV-EBITDA zones).
**Output:** `atlas.lens_valuation_daily`.

## Lens 4 · CATALYST 🔧 (inherit Theta's NSE fetcher)
**Raw table** `atlas.lens_filings` *(model: `india_corporate_filings`)*:
`instrument_id, filing_date, category, category_bucket(earnings|capital|governance),
subject_text, signal_priority, extracted_text, word_count, source_url`.
**Fetcher:** NSE `corporate-announcements` API + `pdfplumber` text extraction (official, moderate).
**Score:** Python rules per bucket (credit upgrade +, resignation −, buyback +, …) recency-weighted;
optional Claude deepen on top filings (budget-capped).
**Output:** `atlas.lens_catalyst_daily`.

## Lens 5 · FLOW 🔧 (inherit Theta's NSE/BSE fetchers)
**Raw tables:**
- `atlas.lens_insider` *(india_promoter_signals)*: `signal_type, value_cr, person_name,
  pledge_pct_after, transaction_date, price_per_share` — SEBI PIT via NSE `corporates-pit`.
- `atlas.lens_shareholding` *(india_shareholding_patterns)*: `quarter, promoter_pct, fii_pct,
  dii_pct, mf_pct, notable_holders(jsonb + superstar flag)` — NSE shareholding API.
- `atlas.lens_bulk_deals` *(india_bulk_deals)*: `deal_date, client_name, buy_sell, qty, price,
  is_institutional, is_superstar` — NSE large-deals snapshot.
**Score:** promoter buys/pledge (lens) + FII/DII/MF deltas + superstar/bulk (modifiers).
**Output:** `atlas.lens_flow_daily`.

## Lens 6 · POLICY ✅ (config-as-data)
**Source:** `atlas.policy_registry` (or JSON): `policy_name, impact, beneficiary_sectors, keywords`
(PLI, capex, China+1, …). Matched on instrument sector/industry.
**Output:** `atlas.lens_policy_daily`.

## Risk overlay (flags, not a lens)
Derived from existing feeds — auditor exit / CFO resignation / downgrade (Catalyst),
pledge spike (Flow), going-concern/solvency. Visible flag; dampens display; never hides.

---

## What we already have vs. need to source
| Lens | Data status |
|---|---|
| Technical | ✅ built (add ~2 derived vol/volume cols) |
| Valuation | ✅ `tv_metrics` — *widen 750→2000 + nightly refresh* |
| Fundamental (levels) | ✅ `tv_metrics` |
| Fundamental (trend) | ⚠️ needs financials history → **NSE XBRL** (or levels-only v1) |
| Catalyst | 🔧 inherit NSE filings fetcher → new tables |
| Flow | 🔧 inherit NSE/BSE insider/shareholding/bulk fetchers → new tables |
| Policy | ✅ registry |

**Two genuine data-sourcing TODOs:** (1) financials *history* for Fundamental trend
signals (NSE XBRL — or ship levels-only first); (2) the NSE/BSE Catalyst + Flow feeds.
Everything else is in hand. **`atlas.tv_metrics` already carries the full fundamentals/
valuation field set** — it just needs widening to the full 2,000 universe and a nightly refresh.
