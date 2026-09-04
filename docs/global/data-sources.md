# Global Atlas — data sources

Every number the global board shows traces to one of the sources below (rule #0). This file
is the register: what feeds what, at what cadence, what the fallback is, and which gate proves
the feed is real. The SIP gate — Phase 0's first gate, and the decision that picks the price
spine — logs its result at the bottom.

**Verified 2026-09-04.** Plan availability, rate limits, endpoint shapes and package names
were checked on this date (`docs/global/plan.md`, "Data sources"). Anything marked
*unverified* is a claim we still have to test against a real account; nothing here counts
as a source until its gate has passed on real rows.

## Sources, cadence, fallbacks, gates

| Need | Primary (free, official) | Cadence | Fallback | Gate |
|---|---|---|---|---|
| OHLCV 2016→ | **Alpaca Market Data, free plan**: 7+ yrs daily bars, 200 req/min, multi-symbol bars (≤10,000 points/page, `page_token`), `adjustment=split` and `all` (two pulls, merged), `feed=sip` for history older than 15 min; paper-only account = email signup, no KYC, international | nightly incremental; backfill ≈ 4,000 symbols × 7 yrs in minutes | **Stooq importer** (FM-downloaded `d_us_txt.zip`); yfinance only as a cross-check | **Phase 0 SIP gate** (protocol below). Fail → Stooq spine + paid slot (Polygon Starter / Tiingo) |
| Corporate actions | Alpaca corporate-actions endpoint (16 event types incl. splits, cash/stock dividends, spin-offs, mergers) — **plan-tier access unverified** | daily | derive from `all` vs `split` bar ratios, flagged `source='derived_from_adjustment'` (needs FM approval — rule #0) | every `\|ret_1d\| > 0.5` on `close_adj` has a matching action |
| Index / macro | FRED (`SP500`, `VIXCLS`, `DGS10`, `DTB3`, `DTWEXBGS`) — key already in India `.env` | daily | — | through EOD-1 |
| ETF universe | Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt` (ETF = Y, exchange, test-issue flag) | weekly | Alpaca `/v2/assets` | 3,300–4,000 rows, every one with an exchange |
| S&P 500 | **SSGA SPY daily holdings CSV** (constituents, weights, GICS sector column — verify columns on first fetch) via `etf-scraper`; history `fja05680/sp500` | daily / one-time | Wikipedia list | 500–505 names, weights ≈ 100% |
| Identity | Nasdaq directory; SEC `company_tickers.json` (stocks → CIK) and `company_tickers_mf.json` (funds → CIK/series/class; verify field names); SEC `submissions` API (SIC code); Alpaca assets (tradable, fractionable) | weekly | `symbol_alias` manual rows | CIK on 100% of stocks; series_id on ≥95% of ETFs; alias round-trip for 20 punctuation tickers |
| ETF holdings + exposures | **EDGAR N-PORT via `edgartools`** for the whole universe — per holding `name, cusip, ticker, balance, value_usd, pct_value, asset_category, investment_country`; per fund `net_assets, total_assets, series_id` (`Fund(ticker).get_portfolio()`); public only for the quarter-end month, ~60-day lag | weekly | — | holdings on ≥90% of ETFs by count, ≥98% by AUM |
| Fresh holdings (big four) | Issuer CSVs via `etf-scraper` (iShares daily incl. history since 2010; SSGA, Vanguard, Invesco current); `query_listings()` for issuer product lists (AUM, expense) | daily | N-PORT | Σ\|weight_frac\| ∈ [0.9, 1.1] for ≥97% of non-leveraged ETFs |
| Stock fundamentals | **EDGAR XBRL company facts via `edgartools`** (`filed` per fact = PIT) | weekly (changed filers) | — | ≥95% of S&P 500 with ≥8 quarters; continuity checks |
| Catalysts / flow | EDGAR 8-K (item codes), Form 4, 13F via `edgartools`; **FINRA Equity Short Interest** (free files + `api.finra.org`, twice monthly, archives to 2014) | daily / per publication | — | filing-rich names score catalyst > 0 |
| Taxonomy seed | `FinanceDatabase` (MIT) sector/industry approximations + ETF category/family — seed and cross-check only | one-time | — | — |

**Rejected as spine:** Polygon free (2-year cap), Tiingo free (500 symbols/month), yfinance
(unofficial, rate-limited), Stooq API (daily-hit limits; bulk download CAPTCHA-gated →
manual). **Rejected as a library:** OpenBB Platform (AGPLv3 — unacceptable ambiguity for a
licensed commercial product; 30 providers where we need four).

Packages: `pyproject.toml` extra `global` — `alpaca-py`, `edgartools`, `financedatabase`,
`exchange_calendars` (names and version floors verified on PyPI 2026-09-04; `financetoolkit`
arrives transitively via `financedatabase`, so the Phase 3 "add or not" decision costs
nothing either way). Every other library the global tree uses is already a core or extra
dependency.

**`etf-scraper` is not installable in this project.** Its only release (0.1.2) and its
`main` branch both pin `numpy<2.0`, while Atlas's core `pandas-ta==0.4.71b0` needs NumPy 2
(locked 2.2.6) — `uv lock` refuses the combination outright, so it is left out of the
extra. The rows above that name it (S&P 500 holdings, fresh big-four holdings) still stand
as *sources*; only the client library changes. Options for the Phase 1–2 owner, in order
of preference: (1) write `providers/issuer_holdings.py` directly — the iShares / SSGA /
Vanguard / Invesco holdings endpoints are plain CSV/XLSX downloads and the package is a thin
`requests` + `pandas` wrapper over them; (2) vendor its parsers with attribution (MIT);
(3) a project-wide `[tool.uv] override-dependencies` on numpy, which needs FM approval
because it silences every package's numpy pin, not just this one. Not decided here.

## The Alpaca paper-only caveat

The price spine is designed around an Alpaca **paper-only** account — email signup, no KYC,
open to international residents — because that is what the FM can create today. Two things
about that account are **unverified** until the SIP gate runs:

1. **SIP entitlement.** The free plan documents `feed=sip` for bars older than 15 minutes,
   but whether a paper-only account is entitled to the consolidated (SIP) feed or only to
   IEX is not something documentation settles. IEX alone shows roughly 2–3% of consolidated
   volume, so an IEX-only entitlement is unusable for the liquidity floor and for the ADV$
   bands — and it is exactly what the volume-ratio check below detects.
2. **Corporate-actions endpoint tier**, and Alpaca's terms on displaying derived data in a
   commercial adviser product. Both are confirmed against the account, not assumed.

Keys live in `.env` on the box/laptop and in Vercel env only — the repo is public and
gitleaks stays on.

## SIP gate protocol — `validate_global.py --check SIP` (Phase 0, first gate)

The gate compares 40 sessions of real Alpaca bars against two independent real sources and
asserts on the produced numbers. It is run once before any other Phase 0 work depends on
the spine, and its result is recorded in the log below, pass or fail.

1. **Pull** 40 sessions of daily bars for `SPY`, `AAPL`, `QQQ` with `feed=sip`, both
   `adjustment=split` and `adjustment=all`, `end` clamped to `eod_cutoff() − 1 min`.
2. **Returns agree with FRED.** Correlation of SPY daily returns (from the `all`-adjusted
   close) with FRED `SP500` daily returns over the same sessions must be **≥ 0.999**.
3. **Volume is consolidated, not IEX-only.** Per-session ratio of Alpaca SPY volume to the
   Stooq `SPY.US` file's volume must lie in **[0.9, 1.1]**. An IEX-only feed fails this by a
   factor of ~40 — that is the check the entitlement question hangs on.
4. **No session gaps.** The set of Alpaca dates for each of the three symbols equals the
   set of sessions FRED and Stooq report in the window (and `exchange_calendars` NYSE
   sessions, used only as the expected-session cross-check).
5. **Decide.**
   - **PASS** → Alpaca is the spine (`GLOBAL_PRICE_PROVIDER=alpaca`); `ingest_prices.py`
     writes `source='alpaca'` per row; Stooq becomes the cross-source-agreement check.
   - **FAIL** → record the numbers below; the FM's Stooq bulk download becomes the spine
     (`GLOBAL_PRICE_PROVIDER=stooq_bulk`, `import_stooq.py --zip d_us_txt.zip`), and the one
     paid feed slot opens (Polygon Starter / Tiingo). The decision is also appended to
     `decisions.jsonl`.

Whatever the outcome, no score is computed on the spine until Phase 1's `--check A`
(completeness ≥ 99%, `|ret_1d| ≤ 1`, `max_abs_log_jump < 0.4` on ≥ 99% of `close_adj`, SPY
vs FRED correlation ≥ 0.999 over the full history, Alpaca-vs-Stooq closes within 0.1% on a
50-ticker sample) passes on the real rows.

## Fallback mechanics

**Provider abstraction** (`atlas/global_market/providers/base.py`, Protocols; adapters do
the I/O and are the only off-box boundary): `PriceProvider.bars(symbols, start, end,
adjustment)`, `AssetProvider.assets()`, `HoldingsProvider.holdings(instrument, as_of)`.
Selected by `GLOBAL_PRICE_PROVIDER=alpaca|stooq_bulk`; `ingest_prices.py` writes `source`
per row and never mixes sources within one instrument-day without `--override`.

**Stooq importer** (`import_stooq.py --zip d_us_txt.zip`): walks
`data/daily/us/{nasdaq,nyse,nysemkt} {etfs,stocks}/…/<ticker>.us.txt`
(`<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>`);
`AAPL.US → AAPL`, `BRK-B.US → BRK.B` via `symbology.normalise()` + `symbol_alias(source='stooq')`;
unmapped tickers are logged, never dropped silently. Adjustment is auto-detected per file
against overlapping Alpaca `close_adj` / `close_tr` (min |diff| wins, written to
`adjustment_source`); a file whose best match exceeds 0.5% median error is refused and
logged — no guessing.

**Free-tier budget is a monitored metric**: every provider call lands in
`atlas_global.provider_calls`, and `/health` shows the day's count against the plan limit.

## SIP gate log

One row per run, appended by hand from the gate's printed output — never edited in place.

| Run date (ET) | Account | Window (sessions) | SPY ret corr vs FRED | SPY volume ratio vs Stooq (median) | Session gaps | Result | Decision |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | **not yet run** | spine undecided until this row is real |

## Open questions carried from the plan

- Alpaca 1Day bar finalisation time — the 01:00 UTC run assumes bars are final after
  extended hours; verify on the first nights and move the cron if not.
- Issuer site terms for automated holdings downloads — gentle cadence, caching; N-PORT is
  the licence-clean source and already carries the whole universe (lagged).
- `company_tickers_mf.json` field names and issuer product-list columns — verified on the
  first real fetch; `*_source` columns make any unofficial fill visible on the card.
- Index licensing (naming "S&P 500", showing membership in a commercial adviser product) —
  legal to confirm before launch.

## Stooq archive — what the FM's `d_us_txt.zip` actually contains (inspected 2026-09-04)

- 541 MB, 13,366 files, layout `data/daily/us/{nasdaq etfs, nasdaq stocks/<n>, nyse etfs/<n>, nyse stocks/<n>, nysemkt …}/<ticker>.us.txt`
  — folder names contain spaces and numbered sub-folders, so the importer must walk the zip, not glob a flat directory.
- Row format `<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>`; `spy.us.txt` runs 2005-02-25 → 2026-09-03 (5,415 rows).
- The SPY series looks **dividend-adjusted** (a 2005 close near 93.7 against a ~120 unadjusted close), so the importer's
  adjustment auto-detect must compare against Alpaca `adjustment=all`, not raw closes — exactly the case the plan anticipates.
- `stooq.com` is not reachable from the Claude Code cloud sandbox (egress reset); the archive came via Google Drive with
  link sharing on. The full import runs on the laptop or the box.
