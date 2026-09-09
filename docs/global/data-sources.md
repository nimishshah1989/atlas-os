# Global Atlas — data sources

Every number the global board shows traces to one of the sources below (rule #0). This file
is the register: what feeds what, at what cadence, what the fallback is, and which gate proves
the feed is real. The SIP gate — Phase 0's first gate, and the decision that picks the price
spine — logs its result at the bottom.

**Verified 2026-09-04.** Plan availability, rate limits, endpoint shapes and package names
were checked on this date (`docs/global/plan.md`, "Data sources"). Anything marked
*unverified* is a claim we still have to test against a real account; nothing here counts
as a source until its gate has passed on real rows.

## Decision 2026-09-07 — the price spine is Alpaca; the SIP gate PASSED on real bars

**This supersedes the 2026-09-04 decision recorded below, and no feed is bought.** On 2026-09-06 the FM opened an Alpaca paper account, which removed the only reason Alpaca had been struck — a process reason ("too cumbersome to start"), never a data one. The free-first rule then applied again: no feed is bought until a free one has failed a gate on real bars. On 2026-09-07 `validate_global.py --check SIP` ran on that account and **passed every check** (the log below carries the numbers). So the spine is **Alpaca**, `GLOBAL_PRICE_PROVIDER=alpaca`, and the $30/month Tiingo subscription is not spent.

**The entitlement question is settled by measurement, not by documentation.** It had been open since Phase 0: a paper-only account might be served the consolidated (SIP) tape or only IEX, and IEX alone prints a small fraction of true volume — which would have silently poisoned the $1,000,000 liquidity floor and every ADV$ band built on it. Two independent readings answer it:

- The gate's own check (2): median Alpaca ÷ Stooq SPY volume = **1.0017** over 39 sessions (min 0.9982, max 1.0163). Consolidated. An IEX-only entitlement reads ~0.02–0.03 there.
- The account as its own control: the SAME four sessions pulled with `feed=iex` return **2.79 %** of the `feed=sip` volume (SPY 2026-08-25: 766,153 against 27,475,227). The two feeds are genuinely different, and the one we are served is the consolidated one.

**Both price bases are available, so `close_adj` and `close_tr` come from the vendor, not from us.** Measured on SPY 2016-01-04: `adjustment=split` closes 201.0192 (the price actually traded) and `adjustment=all` closes 171.10 (dividends back-adjusted). Two pulls, merged, exactly as the plan specified — and no derived-from-adjustment estimator is needed, so rule #0 is never strained. As a bonus this independently corroborates `--check BASIS`: the Stooq archive's 171.85 for that day sits 0.44 % from Alpaca's total-return close and nowhere near the traded price, which is what a total-return series re-based to a different date looks like.

**The one real limit: history stops at 2016-01-04.** A request starting in 1990 returns 2,684 bars beginning 2016-01-04 for SPY, and *exactly the same count and start* for AAPL, which listed in 1980. That is a plan-wide floor, not a listing date. It happens to be precisely the history the plan asks for, with zero margin, so: **Alpaca is the spine for 2016→ and every nightly increment; the Stooq archive is the permanent source of anything older** (it reaches 1970 for names like JPM and KO) and stays the cross-source-agreement check. I am not certain whether the floor is fixed at 2016 or a rolling ~10-year window — worth re-checking against the vendor's own documentation before anyone depends on pre-2016 coverage arriving later.

**What survives from 2026-09-04.** Everything except the vendor line. Stooq still cannot be the spine (no nightly refresh, undocumented and moving adjustment basis, no events) — since proven by `--check BASIS`, which measured the archive as total-return and re-based to the download date. And the vendor comparison in `phase1.md` §1 is not withdrawn: it is now the contingency if Alpaca lapses or its terms change, with **Tiingo Power** the named fallback.

**Still unverified, and not assumed anywhere:** the corporate-actions endpoint's plan tier, and Alpaca's terms on displaying derived data in a commercial adviser product. Both are confirmed against the account before Phase 3, not before.

### Superseded — decision 2026-09-04 (kept for the record)

> The FM ruled Alpaca out ("too cumbersome to start"). Stooq cannot be the spine (no nightly refresh, undocumented and moving adjustment basis, no events). The spine is **Tiingo** — raw + adjusted bars with `divCash`/`splitFactor` per row, 99.9% coverage of today's listed ETFs (measured), delisted names kept — behind the same `PriceProvider` Protocol; Stooq stays the cross-check and emergency fallback. Licence tiers, the vendor comparison and the FEED gate that replaces the SIP gate: `docs/global/phase1.md` §1. The OHLCV and corporate-actions rows below are superseded accordingly; `--check SIP` is replaced by `--check FEED` (same checks, vendor-agnostic).

## Sources, cadence, fallbacks, gates

| Need | Primary (free, official) | Cadence | Fallback | Gate |
|---|---|---|---|---|
| OHLCV 2016→ | **Alpaca** (SIP gate PASS 2026-09-07): free plan, `feed=sip`, `adjustment=split` → `close_adj` and `adjustment=all` → `close_tr`, 200 req/min, multi-symbol bars ≤ 10,000 points per page. **History floor 2016-01-04, plan-wide** | nightly incremental once `ingest_prices.py` lands (P1-B) | **Stooq importer** for pre-2016 history (permanent, not emergency) and as the cross-source check; Tiingo Power if Alpaca lapses (`phase1.md` §1); yfinance only as a third cross-check | **SIP gate PASSED** (log below), then gate A (P1-B) |
| Corporate actions | Alpaca corporate-actions endpoint (16 event types incl. splits and cash/stock dividends) — **plan-tier access unverified**, confirmed against the account, not assumed | daily | derive from `all` vs `split` bar ratios, flagged `source='derived_from_adjustment'` (needs FM approval — rule #0) | every `\|ret_1d\| > 0.5` on `close_adj` has a matching action |
| Index / macro | FRED (`SP500`, `VIXCLS`, `DGS10`, `DTB3`, `DTWEXBGS`) — key already in India `.env` | daily | — | through EOD-1 |
| ETF universe | Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt` (ETF = Y, exchange, test-issue flag) | weekly | Alpaca `/v2/assets` | ≥ 5,000 ETF rows, every one with an exchange (measured 2026-09-04: 5,655 = 1,257 Nasdaq-listed + 4,398 other exchanges — the plan's "3,300–4,000" was an estimate) |
| S&P 500 | **SSGA SPY daily holdings workbook** (`.xlsx` via `openpyxl`: constituents, weights, CUSIP; verified 2026-09-04 — the `Sector` column is present but `-` on all 505 rows) + **the eleven Select Sector SPDR workbooks** (XLB…XLY, same layout) for `sector_gics` by membership — `providers/ssga.py`; history `fja05680/sp500` (MIT; `providers/sp500_history.py`). SSGA's notice forbids reproducing the workbooks: never committed, fetched live by tests and the weekly step | weekly / one-time | Wikipedia list | 500–505 names, weights ≈ 100% (505 rows, Σ 0.99936 on 2026-09-03); ≥ 98% of ticker rows in exactly one sector file (504/504 on 2026-09-03) |
| Identity | Nasdaq directory (`nasdaqlisted.txt` + `otherlisted.txt`: ETF flag, exchange legend, ACT/CQS/NASDAQ spellings); SEC `company_tickers.json` + `company_tickers_exchange.json` (registrants → CIK) and `company_tickers_mf.json` (1940-Act funds → CIK/series/class; field names verified 2026-09-04); Tiingo `supported_tickers.zip` (listing dates, spelling proof); the Stooq archive's members (delisted names, `is_active=false`) — `build_identity.py`, `providers/directories.py` (P1-A) | weekly | `symbol_alias` manual rows | measured 2026-09-04: 13,154 listings, exchange on 100%; CIK on 99.6% of stock-flagged rows (the rest: rights, which the SEC does not list, and bank holding companies filing with their regulator) and on 82.5% of ETFs (79.3% with a series/class id — trusts, commodity pools and ETNs are registrants, not 1940-Act funds); alias round-trip on all 543 punctuation tickers; `import_stooq --dry-run` maps 13,334 of the archive's 13,352 members (99.9%; the 18 unmapped are empty files of names absent from the directory) |
| ETF holdings + exposures | **EDGAR Form N-PORT-P**, fetched directly — one `browse-edgar` index request per SERIES (`CIK=S000004310&type=NPORT-P&output=atom`) then that filing's `Archives/.../primary_doc.xml`; `providers/nport.py` parses it and `ingest_nport.py` writes `etf_holdings` + `etf_meta`. Built 2026-09-09 (P2-A); the measured shape of the feed is below | weekly, incremental on each fund's stored accession | — | Σ\|weight_frac\| ∈ [0.9, 1.1]; holdings on ≥90% of ETFs by count, ≥98% by AUM |
| Fresh holdings (big four) | Issuer CSVs via `etf-scraper` (iShares daily incl. history since 2010; SSGA, Vanguard, Invesco current); `query_listings()` for issuer product lists (AUM, expense) | daily | N-PORT | Σ\|weight_frac\| ∈ [0.9, 1.1] for ≥97% of non-leveraged ETFs |
| Stock fundamentals | **EDGAR XBRL company facts via `edgartools`** — `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`, ONE request per filer for the entire history, `filed` per fact = PIT. Built 2026-09-09 (`ingest_financials.py` → `stock_financials_pit`); the measured shape of the feed is below | nightly, incremental on each filer's stored `max(filed)` | — | ≥95% of S&P 500 with ≥8 quarters (`fund_min_quarters`); continuity checks |
| Catalysts / flow | EDGAR 8-K (item codes), Form 4, 13F via `edgartools`; **FINRA Equity Short Interest** (free files + `api.finra.org`, twice monthly, archives to 2014) | daily / per publication | — | filing-rich names score catalyst > 0 |
| Taxonomy seed | `FinanceDatabase` (MIT) sector/industry approximations + ETF category/family — seed and cross-check only | one-time | — | — |

**Rejected as spine:** Polygon free (2-year cap), Tiingo free (500 symbols/month), yfinance
(unofficial, rate-limited), Stooq API (daily-hit limits; bulk download CAPTCHA-gated →
manual). **Rejected as a library:** OpenBB Platform (AGPLv3 — unacceptable ambiguity for a
licensed commercial product; 30 providers where we need four).

Packages: `pyproject.toml` extra `global` holds `alpaca-py`, `openpyxl`, `TA-Lib` and — since P3-A — `edgartools` (floor `>=5.56`; resolved and run against **5.57.0** on 2026-09-09). A package is added in the
PR that first imports it, never ahead of its importer: `edgartools` landed with
`ingest_financials.py`, and `financedatabase` arrives with the taxonomy seed (`financetoolkit`
comes transitively via it, so the Phase 3 "add or not" decision costs nothing either way),
`exchange_calendars` with Phase 1's gate A (floors verified on PyPI 2026-09-04). Every other library the global tree
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

### EDGAR Form N-PORT-P — what the feed actually looks like (measured 2026-09-09, P2-A)

Measured on four real filings, kept verbatim under `tests/fixtures/global/nport/` (that
directory's `SOURCE.md` carries each accession and hash) and on three more fetched live.
Five things differ from what the plan assumed, and each one is a way to be wrong:

1. **`pctVal` is a PERCENT.** IVV's CBRE line is `0.061079735228` and `valUSD / netAssets` for
   the same row is `0.00061079…`. Stored as a fraction it would put every S&P 500 constituent
   at a hundred times its weight. `weight_frac` is divided by a hundred exactly once, in
   `providers/nport.py`.
2. **The period is the filer's FISCAL quarter, not the calendar's.** iShares reports 30 June,
   ProShares 31 May, and `repPdEnd` is the fiscal YEAR end (2027-03-31 on a filing whose
   holdings are as of 2026-06-30) — nine months adrift if read as the snapshot date. The lag
   from period to filing is real and close to the plan's estimate: 56 days (IVV), 58 (TQQQ),
   57 (EWJ).
3. **`netAssets` is the SERIES', and a series can have several share classes.** VOO is one of
   FOUR classes of the Vanguard 500 Index Fund, whose filed net assets are $1.671tn; that is
   not VOO's AUM, and N-PORT carries no class-level assets at all. `ingest_nport.py` fills
   `etf_meta.aum_usd` only where `series_class_count = 1` and keeps the series figure under
   `series_net_assets_usd` — a missing sub-score rather than a wrong number (rule #0).
4. **Leverage is invisible in the weights.** A swap's `pctVal` is its MARK. TQQQ — a
   three-times fund — sums to 101.26% of net assets against IVV's 100.12%. The only structural
   evidence is `derivativeInfo/*/notionalAmt`: TQQQ's ten swaps total $107.5bn against $39.8bn
   of net assets (`derivative_notional_share` **2.70**), where IVV reads **0.0016**. Both the
   mark (`derivatives_share`) and the notional share are stored, because they answer different
   questions.
5. **"N/A" is a value the filers write** — as a `cusip`, an `lei`, an `isin`, an `invCountry`
   and a `payoffProfile`. `country_iso2` is `char(2)`: unhandled, VOO's twelve futures lines
   would store the country `N/`. And the *categories* move to an attribute when they are off
   enum (`<assetConditional assetCat="OTHER" desc="Right"/>`), so reading only the elements
   loses a CVR, an ETF position and every futures line's issuer.

**Identity.** CUSIP is missing on 176 of EWJ's 182 holdings (Japanese equities have none) and
ISIN on 16 of VOO's 520, so neither alone is a key: `holding_key` takes the first that exists,
with an occurrence suffix because IVV really does hold one money-market CUSIP on two lines.
Look-through resolves by CUSIP then ISIN through `symbol_alias(source='cusip')`, which
`ingest_index_membership.py` writes from the SSGA workbook — the only place in the repo that
holds a real (symbol, CUSIP) pair.

**Size, and why the writer batches.** A filing is 157 KB (TQQQ, 127 holdings) to **15.9 MB**
(AGG, **13,269 holdings**), against IVV's 512 KB / 508. A full first pass over several
thousand funds is therefore millions of records, which is why `ingest_nport.py` commits every
50,000 rows rather than at the end: bounded memory on a 2-vCPU box, and a long first run that
resumes from its watermarks instead of restarting. Retention of old snapshots is an open
question for the FM — nothing prunes `etf_holdings` today.

**Not in this feed, whatever the plan hoped:** expense ratio, shares outstanding, inception
date. The cost lens's expense sub-score and `etf_shares_daily` still need an issuer feed;
`etf_shares_daily` is deliberately left empty rather than filled with quarterly points, since
its documented job is a 21-session Δ-shares proxy.

**SPY is absent and that is correct.** It is a unit investment trust, and UITs do not file
N-PORT; it is not in `company_tickers_mf.json` either. QQQ is present (S000101292).

**Bulk alternative, not taken.** SEC publishes quarterly N-PORT data sets as flat files
(`https://www.sec.gov/files/dera/data/form-n-port-data-sets/<yyyy>q<n>_nport.zip`; verified
2026-09-09: 2026q1 463 MB, 2026q2 441 MB, 2025q4 418 MB). One download covers every fund, but
it is organised by the quarter the filings were MADE, so it trails the per-fund fetch by up to
a quarter and costs gigabytes of disk on the box. It is the backfill route if we ever want
history, not the nightly one.

### EDGAR XBRL company facts — what the feed actually looks like (measured 2026-09-09, P3-A)

Verified against real payloads for AAPL, JPM, VZ (committed under
`tests/fixtures/global/edgar/`, provenance in its `SOURCE.md`) plus KO and PG, and against the
SEC `frames` API for CY2025Q1. Everything here changed a design decision, so it is recorded
rather than left to the next reader to rediscover.

* **One request per filer, whole history.** `companyfacts` returns every fact the company ever
  tagged — 3.8 MB for Apple, 7.9 MB for JPMorgan, 20 years deep. There is no windowed request,
  so an incremental run costs the same fetch as a backfill; what is incremental is the write.
  Requests are spaced by `SEC_MIN_INTERVAL_S` (0.11 s ≈ 9/s, under SEC's stated 10/s), and the
  contact `User-Agent` comes from `EDGAR_IDENTITY` — never a literal, this repo is public.
* **No filer tags a discrete fourth quarter after 2020.** The SEC dropped the
  selected-quarterly-data requirement, so a 10-K carries only the twelve-month duration.
  Apple's last real Q4 is FY2020 and Verizon's FY2019. Q4 is therefore the identity
  FY − Q1 − Q2 − Q3 (`ratios.implied_q4`, tested against Apple's real FY2020 Q4, which it
  reproduces to the dollar). **Without it there is no TTM for three quarters in four.**
* **A 10-Q's cash-flow statement is cumulative.** Only the first fiscal quarter's operating
  cash flow, capex and dividends are three-month durations; Q2 and Q3 publish six- and
  nine-month figures, which are dropped rather than stored in a column read as a quarter. So
  **FCF is present on Q1 rows and annual rows only** — the fundamental lens must renormalise,
  or read TTM FCF off the last 10-K. The fix, if it becomes a constraint, is a `period_months`
  column in the primary key (see the hand-over notes).
* **Duration ambiguity is resolved by form.** Several durations end on the same date (a 10-Q
  carries the quarter and the YTD; a pre-2021 10-K carries a Q4 beside the year). The primary
  key admits one row per `(period_end, form, filed)`, so the row takes the filing's own class —
  a year for 10-K/20-F/40-F, a quarter for 10-Q.
* **`fy`/`fp` on a fact describe the FILING, not the fact.** The prior-year quarter shown as a
  comparative in a 2026 Q1 10-Q is stamped `fy=2026 fp=Q1`. Copied verbatim it mislabels the
  period by a year, so the stamp is taken only for the filing's own period and a comparative
  keeps `FY` (which its duration proves) or nothing.
* **Forms beyond the periodic reports appear.** Verizon, Coca-Cola and JPMorgan tag `8-K`
  earnings releases and `DEF 14A` proxy tables in the same payload;
  `chk_stock_financials_pit_form` admits neither, so they are filtered before the insert.
* **Restatements are real and material.** Apple's FY2019 diluted share count is 4,648,913
  thousand as filed in 2019 and 18,595,651 thousand as re-filed in 2020, restated for the
  four-for-one split — the same `(period_end, form)` under two `filed` dates. Keying the table
  on `(instrument, period_end)` would have destroyed the first, and every pre-split backtest.
* **Banks are a different chart of accounts, not a gap to fill.** JPMorgan files no
  `OperatingIncomeLoss`, no `GrossProfit`, no `AssetsCurrent`/`LiabilitiesCurrent` and no
  capital expenditure at all, and its only quarterly top line is `RevenuesNetOfInterestExpense`.
  EBIT, EBITDA, ROCE, operating margin, interest cover and FCF are therefore genuinely absent
  for financials — `None`, never a zero — on top of the D/E and current-ratio suppression the
  `is_financial` flag applies.
* **Verizon files no `PaymentsToAcquirePropertyPlantAndEquipment`** since 2019 (it splits capex
  across `PaymentsToAcquireIntangibleAssets` and `PaymentsToAcquireOtherProductiveAssets`), so
  its capex and free cash flow are null. Summing the two would be a derived number; it is left
  absent and said out loud.
* **The element a filer uses is not the element you expect, and one tag per concept scores
  half the index null.** Measured on 15 real members: Caterpillar tags **no** `NetIncomeLoss`
  on any quarterly duration (only `ProfitLoss`); Exxon and Berkshire tag no `OperatingIncomeLoss`
  in the current period; Berkshire files no diluted EPS, no diluted share count and no debt
  element at all. Each of those is the filer's own practice, not a bug — the ordered fallbacks
  cover what can honestly be covered and the rest is `None`.
* **`GrossProfit` is not universal.** JPMorgan, Verizon and P&G tag none. Cost of revenue is
  mapped (`atlas.global_market.fundamentals.xbrl_map`) but `stock_financials_pit` has no column
  for it, so gross margin is unavailable for those filers until one is added.

The tag map itself, with the ordered fallbacks and the corrections made to the plan's starting
list, is `atlas/global_market/fundamentals/xbrl_map.py` — every tag verified against a real
payload, with the SEC `frames` filer count for the ones absent from all five samples.


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

## SIP gate log

One row per run, appended by hand from the gate's printed output — never edited in place.

| Run date (ET) | Account | Window (sessions) | SPY ret corr vs FRED | SPY volume ratio vs Stooq (median) | Session gaps | Result | Decision |
|---|---|---|---|---|---|---|---|
| 2026-09-07 | paper, free plan | 2026-06-29 → 2026-09-04 (40) | 0.99921 on 39 returns (worst residual 0.0650 % on 2026-08-27, an ex-dividend day) | 1.0017 (min 0.9982, max 1.0163, 39 sessions); median \|close diff\| 0.0000 % | none — 40 FRED and 39 Stooq sessions all present | **PASS** (8/8) | Alpaca is the spine; `GLOBAL_PRICE_PROVIDER=alpaca`; no paid feed bought |

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
NASDAQ Symbol column; `eti_` a preferred with no series; 391 members) and is left untouched by the
normaliser: `build_identity.py` writes the `symbol_alias(source='stooq')` row for every listing from the
CQS spelling (`AGMpD → AGM_D.US`, `ACHR.WS → ACHR-WS.US` — the ACT column says `ACHR.W`, so warrants also
need the alias), and archive members absent from the directory get an inactive row of their own, so the
whole archive maps (13,352 of 13,352 members on the 2026-09-04 files; `--dry-run` prints the count). A
kind mismatch between the folder and `instrument_master.asset_class` is noted in the report, not resolved
silently (2,035 members on 2026-09-04 — the archive's `etfs`/`stocks` folders do not follow the
directory's ETF flag); with an empty `instrument_master` every member is reported unmapped and the
importer exits 2.

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
