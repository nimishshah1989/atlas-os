# Global Atlas — data sources

Every number the global board shows traces to one of the sources below (rule #0). This file
is the register: what feeds what, at what cadence, what the fallback is, and which gate proves
the feed is real. The SIP gate — Phase 0's first gate, and the decision that picks the price
spine — logs its result at the bottom.

**Verified 2026-09-04.** Plan availability, rate limits, endpoint shapes and package names
were checked on this date (`docs/global/plan.md`, "Data sources"). Anything marked
*unverified* is a claim we still have to test against a real account; nothing here counts
as a source until its gate has passed on real rows.

## Decision 2026-09-04 — the price spine is Tiingo, not Alpaca and not Stooq

The FM ruled Alpaca out ("too cumbersome to start"). Stooq cannot be the spine (no nightly refresh, undocumented and moving adjustment basis, no events). The spine is **Tiingo** — raw + adjusted bars with `divCash`/`splitFactor` per row, 99.9% coverage of today's listed ETFs (measured), delisted names kept — behind the same `PriceProvider` Protocol; Stooq stays the cross-check and emergency fallback. Licence tiers, the vendor comparison and the FEED gate that replaces the SIP gate: `docs/global/phase1.md` §1. The OHLCV and corporate-actions rows below are superseded accordingly; `--check SIP` is replaced by `--check FEED` (same checks, vendor-agnostic).

## Sources, cadence, fallbacks, gates

| Need | Primary (free, official) | Cadence | Fallback | Gate |
|---|---|---|---|---|
| OHLCV 2016→ | **Tiingo** (decided 2026-09-04; Alpaca out — see the decision note above and `phase1.md` §1): per-ticker daily bars with raw + adjusted OHLCV and `divCash`/`splitFactor` per row, 60+ yrs, 5,649 of today's 5,655 listed ETFs, delisted kept | nightly per-ticker (~6,200 calls); backfill in one call per ticker | **Stooq importer** (FM-downloaded `d_us_txt.zip`) as cross-check and emergency spine; yfinance only as a third cross-check | **FEED gate** (`validate_global --check FEED`), then gate A |
| Corporate actions | Tiingo per-row `splitFactor` / `divCash` (amended 2026-09-04; Alpaca out) | daily | derive from `all` vs `split` bar ratios, flagged `source='derived_from_adjustment'` (needs FM approval — rule #0) | every `\|ret_1d\| > 0.5` on `close_adj` has a matching action |
| Index / macro | FRED (`SP500`, `VIXCLS`, `DGS10`, `DTB3`, `DTWEXBGS`) — key already in India `.env` | daily | — | through EOD-1 |
| ETF universe | Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt` (ETF = Y, exchange, test-issue flag) | weekly | Alpaca `/v2/assets` | ≥ 5,000 ETF rows, every one with an exchange (measured 2026-09-04: 5,655 = 1,257 Nasdaq-listed + 4,398 other exchanges — the plan's "3,300–4,000" was an estimate) |
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

Packages: `pyproject.toml` extra `global` holds `alpaca-py` today. A package is added in the
PR that first imports it, never ahead of its importer: `edgartools` and `financedatabase`
arrive with Phase 2 (`financetoolkit` comes transitively via `financedatabase`, so the Phase 3
"add or not" decision costs nothing either way), `exchange_calendars` with Phase 1's gate A
(names and version floors verified on PyPI 2026-09-04). Every other library the global tree
uses is already a core or extra dependency.

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

The gate compares the last 40 sessions of real Alpaca bars against two independent real
sources and asserts on the produced numbers. It is run once before any other Phase 0 work
depends on the spine, and its result is recorded in the log below, pass or fail. The steps
below are what `validate_global.py --check SIP` executes — the log records a protocol that
ran, not one that was planned.

1. **Pull** daily bars for `SPY`, `AAPL`, `QQQ` over the last 70 calendar days with
   `feed=sip` and `adjustment=raw` — one pull, raw on purpose: FRED's `SP500` is a price
   index and Stooq's volume is unadjusted, so both comparisons need like-for-like bars.
   `end` is clamped to now − 16 minutes (the free plan's 15-minute SIP delay plus margin).
   SPY must have **≥ 40 sessions** in the window, and AAPL / QQQ a bar on every SPY session.
2. **Returns agree with FRED.** Pearson correlation of SPY daily returns with FRED `SP500`
   daily returns over the overlapping sessions (≥ 10 of them) must be **≥ 0.999**; the worst
   residual is printed (an SPY ex-dividend day shows there, as expected for raw bars).
3. **Volume is consolidated, not IEX-only.** Median over overlapping sessions of Alpaca SPY
   volume ÷ the Stooq `SPY.US` file's volume must lie in **[0.9, 1.1]** (needs
   `--stooq-file`; without it this check is reported FAIL "not run", never PASS). An IEX-only
   feed fails it by a factor of ~40 — that is the check the entitlement question hangs on.
   The median |close difference| between the two files is printed alongside.
4. **No session gaps.** Every session FRED reports inside SPY's window, and every session the
   Stooq file reports there, is present in Alpaca's SPY bars. (`exchange_calendars` is not
   used here; it arrives with Phase 1's gate A as the expected-session cross-check.)
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
adjustment)` (implemented by `alpaca` and `stooq_bulk`), `AssetProvider.assets()`; a
`HoldingsProvider` Protocol is added with its first adapter in Phase 2. The nightly spine is
selected by `GLOBAL_PRICE_PROVIDER=alpaca|stooq_bulk` — required, no default, so a forgotten
setting can never ingest an untested feed; `ingest_prices.py` writes `source` per row and
never mixes sources within one instrument-day without `--override`.

**Stooq importer** (`import_stooq.py --zip d_us_txt.zip`): walks
`data/daily/us/{nasdaq,nyse,nysemkt} {etfs,stocks}/…/<ticker>.us.txt`
(`<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>`);
`AAPL.US → AAPL`, `BRK-B.US → BRK.B` via `symbology.stooq_symbol()` + `symbol_alias(source='stooq')`;
unmapped tickers are logged, never dropped silently. Adjustment is auto-detected per file
against overlapping Alpaca `close_adj` / `close_tr` (min |diff| wins, written to
`adjustment_source`); a file whose best match exceeds 0.5% median error is refused and
logged — no guessing. That cross-check is a Phase 1 step after the SIP gate; until it runs,
every imported row carries `adjustment_source='stooq:unknown'` (see "Stooq importer" below).

**Free-tier budget is a monitored metric**: every provider call lands in
`atlas_global.provider_calls`, and `/health` shows the day's count against the plan limit.

## Feed gate log (was: SIP gate log)

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

## Stooq importer (`scripts/global_market/import_stooq.py`)

**What it does.** `atlas/global_market/providers/stooq_bulk.py` (`StooqBulkProvider`, `name="stooq_bulk"`)
reads the FM's `d_us_txt.zip` in place: `list_symbols()` derives `(symbol, kind, exchange)` from the six
`data/daily/us/{nasdaq,nyse,nysemkt} {etfs,stocks}` folders (names carry spaces and numbered sub-folders,
so it walks the zip's central directory, never a glob), and `bars()` opens only the requested members and
returns the `PriceProvider` frame — `Decimal` prices built from the file's own digits, volume rounded to
whole shares, `trade_count`/`vwap` None. The importer upserts `open/high/low/close/volume` into
`atlas_global.ohlcv_daily` with `source='stooq_csv'` and `close_adj`/`close_tr` NULL;
`ON CONFLICT … DO UPDATE … WHERE ohlcv_daily.source <> 'alpaca'` means a row Alpaca wrote is never
overwritten (protected rows are counted). Progress lands in `ingest_state(source='stooq_csv',
key=<symbol>)` as the member's zip CRC + size + `--since`, so a rerun resumes and a newer archive
re-imports only the files that changed. Every member's outcome (`imported` / `empty` / `unmapped` /
`skipped_resumed` / `refused_bar`) goes to a CSV report — nothing is dropped silently.

**Adjustment labelling rule.** Stooq does not document what adjustment its files carry, and the archive
shows both kinds at once: dividend adjustment (SPY's 2005-02-25 close is 93.6948 against a ~120 raw
close) and split adjustment (48.1 % of rows have fractional volumes, e.g.
`AADR.US,D,20100721,…,45503.680330826`). So the provider accepts only `adjustment="unknown"` —
`"raw"`, `"split"` and `"all"` raise `ValueError` — and every imported row carries
`adjustment_source='stooq:unknown'` with `close_adj`/`close_tr` NULL; nothing scores on these rows.
The Phase 1 cross-check (after the SIP gate; the `TODO` at the top of the importer) compares each
instrument's overlapping closes with Alpaca `adjustment=split` and `adjustment=all`, labels the closer
match (`stooq:split` / `stooq:all`) and leaves any file whose best match exceeds 0.5 % median error at
`stooq:unknown`, listed. Bars that are not valid (a price ≤ 0, high < low, open/close outside
[low, high]) are refused into the report by symbol and date, never imported.

**Identity-bridge rule.** Each member maps to exactly one `instrument_master` row and the importer never
mints one (`build_identity.py` is the only writer). Lookup order: `symbol_alias(source='stooq',
source_symbol='<TICKER>.US', valid_to IS NULL)` — Stooq's own spelling — then
`instrument_master.symbol = symbology.stooq_symbol(<ticker>)` (`SPY.US → SPY`, `BRK-B.US → BRK.B`,
`AAC-U.US → AAC.U`: Stooq's `-` is the class/unit/warrant separator that Nasdaq's ACT and CQS columns
spell `.`). Stooq's `_` marks a preferred series (`agm_d` is `AGM$D` in the ACT column and `AGM-D` in the
NASDAQ Symbol column; `eti_` a preferred with no series; 391 members) and is left untouched: those map
only through an alias and are reported unmapped until build_identity fixes the canonical spelling. A kind
mismatch between the folder and `instrument_master.asset_class` is noted in the report, not resolved
silently; with an empty `instrument_master` every member is reported unmapped and the importer exits 2.

**How to run — on the laptop** (stooq.com is unreachable from the cloud sandbox; the FM downloads the
archive by hand and it travels by Google Drive):

```
uv run python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip --dry-run             # parse + report, no DB (~4 min)
uv run python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip --symbols SPY,AAPL,BRK.B
uv run python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip --since 2016-01-01    # a rerun resumes
```

`ATLAS_DB_URL` selects the database; `--report PATH` names the CSV (a live run writes one next to the
zip by default). Proof against the real archive:
`STOOQ_ARCHIVE=~/Downloads/d_us_txt.zip uv run --extra dev pytest tests/integration/global_market/test_stooq_archive.py -m integration`
(without the zip it skips — it never passes vacuously). The directory parsers in `providers/symbology.py`
run in `make test` against the dated verbatim snapshot of the real Nasdaq Trader / SEC files in
`tests/fixtures/global/symbology/` (provenance and hashes in its `SOURCE.md`); point them at fresher
downloads with `SYMBOLOGY_DIR=<dir with nasdaqlisted.txt, otherlisted.txt, company_tickers.json>`.

**The archive, as measured** (`--dry-run` 2026-09-04 on the FM's file): 541 MB; 13,352 price files —
ETFs 948 NASDAQ + 2,801 NYSE, stocks 4,728 NASDAQ + 4,547 NYSE + 328 NYSEMKT (`nysemkt etfs/` is empty),
39 of them zero-byte; 27,972,711 valid daily bars from 1962-01-02 (IBM, GE) to 2026-09-03; 106 refused
bars in 49 files (35 with a price ≤ 0, 35 with high < low, 36 with open/close outside the high–low range);
13,468,390 fractional volumes (48.1 %); header, `PER=D`, ticker and date order verified on every row;
parsed in 248 s. `spy.us.txt` runs 2005-02-25 → 2026-09-03 (5,414 bars).
