# Global Atlas — Phase 1 plan: identity, prices, technicals, universe, first surfaces

Status: DRAFT (2026-09-04), **amended 2026-09-07**. Supersedes the Phase 1 paragraph of `plan.md`
where they differ. The 2026-09-04 line "Alpaca is out" is **reversed**: the FM opened an Alpaca
account on 2026-09-06 and the SIP gate passed on real bars on 2026-09-07, so Alpaca is the spine and
no feed is bought. §1's vendor comparison is kept as the contingency; P1-B carries the amendment.

## 1. The price-spine decision

**Question the FM asked:** is Stooq the final solution for historic data, or something else?

**Answer: Stooq is the cross-check and the fallback, not the spine.** It fails three tests a spine must pass:

1. **It cannot refresh nightly.** The bulk archive is CAPTCHA-gated and hand-downloaded; the per-ticker
   CSV endpoint is rate-limited per IP (a few hundred hits a day, not 6,000) and unreachable from the
   cloud sandbox. A board whose prices advance only when the FM downloads 541 MB is not a nightly board.
2. **Its adjustment basis is undocumented and moving.** The FM's archive shows SPY re-based to the
   download date on a total-return basis (2010-01-04 close 87.44 vs the ~113.3 actual close; 2016-01-04
   171.85 vs ~201.0; 2020-01-02 300.27 vs ~324.9; 2025-01-02 582.89 vs ~584.6 — the ratio walks from
   0.77 to ~1.00 exactly as dividend back-adjustment does; the "actual" closes are from memory and the
   FRED cross-check in P1-B makes the claim rigorous). Every dividend re-bases the whole history, so an
   incremental append against a stale base is silently wrong by the dividend amount.
3. **It carries no events.** No split or dividend rows → we cannot build `close_adj` (splits only, for
   charts/technicals) separately from `close_tr` (splits + dividends, for returns), and cannot label
   what a file carries without an independent series.

**The spine is one licensed daily EOD feed with raw bars plus official split and dividend events**, from
which `close_adj` and `close_tr` are computed by us (deterministic back-adjustment factors, parity-tested
against the vendor's own adjusted close) — the plan's "one paid slot", opened now: the plan's own rule
opens it when the free source fails, and Alpaca has failed for a process reason. Cost is one
subscription in the $20–30/month range. **Vendor: Tiingo** (`api.tiingo.com`), chosen over six alternatives on 2026-09-04 (§1a):

- **Fit.** One call per ticker returns the whole history with raw AND adjusted OHLCV plus the
  corporate-action factors on every row (`open high low close volume adjOpen adjHigh adjLow adjClose
  adjVolume divCash splitFactor`) — so our own back-adjustment can be parity-tested row by row against
  the vendor's, and no separate splits/dividends feed is needed. Measured on Tiingo's public ticker
  list (`supported_tickers.zip`, 108,553 rows, 2026-09-04): **5,649 of the 5,655 ETFs in today's Nasdaq
  directories are present (99.9%; the 6 misses are listed in §1a)**, 9,582 ETF rows of which 2,397 are
  delisted (history kept — survivorship honesty), SPY from 1993-01-29, AAPL from 1980-12-12, `BRK-B`
  hyphen spelling. History "60+ years"; provenance "at least 3 data sources" with a composite cross-check.
- **Price and licence (read on the vendor's pages 2026-09-04; the FM confirms before paying).** Free:
  500 unique symbols/month, 50 req/hour, 1,000 req/day — enough for the FEED gate and adapter
  development. **Power $30/month**: 10k req/hour, 100k req/day, ~110k symbols/month — "Internal Use
  Only … for your own personal use, may not display or share the data with another person or
  organization". **Commercial $50/month**: business use, still internal. Display / redistribution to
  clients: **$250–500/month** tier (M2's problem, priced in now). Recommendation: **Power while the FM
  is the only user (Phases 1–2), Commercial the day an analyst logs in (Phase 3), the display tier or
  an EODHD/Massive business quote before any client sees a number (M2).** Legal reviews the wording
  with the index-licence question (plan risk #2).
- **What it lacks.** No whole-market-per-day endpoint (the nightly is ~6,200 per-ticker calls, well
  inside 10k/hour), no ETF flag/CIK/ISIN in its list (identity comes from Nasdaq + SEC anyway — P1-A),
  no ETF fundamentals (Phase 2 uses N-PORT + issuer files as planned). Auth scheme (header vs `token=`
  query parameter) to be verified in the docs on day one — they render client-side and could not be
  read here.

### 1a. The alternatives, in one table (vendor pages read 2026-09-04)

| Vendor | Cheapest usable plan | History | Licence at that price | Why not |
|---|---|---|---|---|
| EODHD | $19.99/mo | 30+ yrs, bulk whole-US-per-day, raw + `adjusted_close`, delisted list | **personal use only**; commercial by sales quote (price unpublished) | licence; ask for a quote as the M2 display candidate |
| Massive (ex-Polygon) | Starter $29 / Developer $79 | 5 / 10 yrs | individual use only; redistribution = business plan | history too short; licence |
| FMP | Starter (price not readable) | 5 yrs (Premium 30) | display needs a separate agreement | history; unverifiable pricing |
| Sharadar Direct | $39/mo full history (1998→, delisted incl.) | 28 yrs | personal licence; professional via Nasdaq Data Link (login-gated price) | licence path unclear; strongest survivorship guarantee — M2 backtest candidate |
| Twelve Data | Grow $29/mo | to 1980 | "internal display" | credits/minute too low for 6k tickers; delisted coverage unstated |
| Marketstack | Basic $9.99 / Pro $49.99 | 10 / 15 yrs | commercial allowed | 10k requests/**month** on Basic; docs unreadable |
| yfinance | free | — | personal, non-commercial; no redistribution | never a displayed number; cross-check only |

The six directory ETFs absent from Tiingo's list: BZZ, FFF, GASZ, OPPG, PJIN, USSX — new or tiny; they
stay identity-only until the vendor lists them (the importer reports them, nothing invents a bar).

**What Stooq does from now on:** (a) the cross-source-agreement gate every night (a 50-ticker sample of
closes within 0.1% after the archive's adjustment is labelled by the FEED cross-check); (b) the
survivorship fallback for pre-2016 history and for tickers the vendor lacks; (c) the emergency spine
if the vendor lapses (weekly manual re-baseline, board marked stale). The importer already exists.

**What is NOT the spine:** yfinance (unofficial, ToS forbids commercial redistribution, breaks
unannounced) — allowed only as a third cross-check inside the gate, never a displayed number.

## 2. Ground rules (verbatim from Phase 0)
Rule #0; no hardcoded methodology numbers; Decimal for money; one EOD anchor (`_gdb.eod_cutoff`);
producer registry; point-in-time; glass box; repo is public. Every chunk carries a GOAL + DoD and
loops until every check passes on REAL produced rows; `make gate` + `schema_gate --market global`
before every PR; `review` + `ponytail-review` on every diff.


## 3. Chunk map and order

| Chunk | Depends on | Parallel with | Owner shape |
|---|---|---|---|
| P1-B0 FEED gate + adapter + `adjust.py` | vendor key | P1-A | one agent |
| P1-A identity | — | P1-B0 | one agent |
| P1-B ingest + actions + labelling + gate A | P1-A rows, P1-B0 | P1-C | one agent |
| P1-C macro, index, benchmarks | P1-A | P1-B | one agent |
| P1-D technicals | P1-B rows, P1-C benchmarks | P1-F | one agent |
| P1-E universe + ADV$ report | P1-D | P1-F | same agent as P1-D |
| P1-F ops, health, runbook | all producers exist | P1-G | one agent |
| P1-G first surfaces | P1-D/P1-E rows on a DB | P1-F | one agent (frontend) |

Every chunk: `test-driven-development` on real records → implement → `make gate` +
`schema_gate --market global` → `review` + `ponytail-review` → PR. Chunks land as separate PRs in the
order above; the integrator (this session) runs the DoD checks on a real DB before each merge request.

## 4. Chunks (GOAL + DoD)

### P1-A — Identity (`build_identity.py`, `providers/directories.py`)

GOAL: `instrument_master` holds one row per US-listed stock and ETF from the real directories — every
active row with an exchange, ≥ 99% of stocks with a CIK, an SEC identity (CIK via either file) on
≥ 80% of ETFs (series/class ids on the 1940-Act funds among them; trusts, commodity pools and ETNs
are registrants, not funds) — minted
under the confirmed identity rule (uuid5 of `us:{class}:{cik}:{symbol}`, else
`us:{class}:{symbol}:{listing_date}`), with `symbol_alias` bridging Stooq's and the vendor's
spellings, and the Stooq importer mapping ≥ 99% of the archive's members that are still listed.
- Sources (all free, official): Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt` (listing, ETF flag,
  exchange, test-issue filter) — parsers exist (`providers/symbology.py`); SEC `company_tickers.json`
  (stocks → CIK; parser exists) and `company_tickers_mf.json` (funds → CIK/series/class;
  real shape verified 2026-09-04: `{"fields": ["cik","seriesId","classId","symbol"], "data": [[2110, "S000009184", "C000024954", "LACAX"], …]}`, 28,500 rows; SPY, DIA, MDY, GLD, IAU, SLV, USO, UVXY, IBIT, GBTC have NO row there (unit investment trusts, grantor trusts, commodity pools and ETNs are not 1940-Act funds) but DO have a CIK in `company_tickers.json`); the vendor's symbol list for listing dates / delistings / ISIN where it
  has them (P1-B's adapter exposes `assets()`); the Stooq archive's member list as the
  survivorship source for delisted tickers (rows with `is_active=false`, `delisted_at` = last bar).
- New `providers/directories.py`: the fetch layer (SEC fair-access `User-Agent` = `EDGAR_IDENTITY`,
  10 req/s ceiling; Nasdaq files plain GET) writing the raw files under `scratchpad`/box tmp and
  recording `provider_calls`. Downloads are the ONLY network in this chunk.
- Canonical spelling = the Nasdaq **ACT symbol** (`BRK.B`, `AAC.U`, `AGM$D`); aliases: `stooq`
  (`BRK-B.US`, `AGM_D.US`), `tiingo` (`BRK-B`, verified in its ticker list), `nasdaq_symbol` (`AGM-D`), `cqs` (`AGMpD`).
  Renames: a symbol that leaves the directory while another appears under the SAME registrant (stocks:
  the CIK, with exactly one active listing before and after; funds: CIK + series + class) is paired —
  same uuid, new symbol, the old spellings closed (`valid_to` = run date), the new ones opened; a CIK
  with several listings (share classes, a trust's funds) is never paired, the new row carries a
  `possible rename` note. Recycles: a symbol whose CIK changes between runs — another registrant, none
  → one, one → none — is a new instrument (old row deactivated); with no CIK on either side a Tiingo
  listing start that jumps forward > 30 days is the recycle signal, a backward move a plain update. A
  deactivated no-CIK row that reappears with an agreeing name is reactivated (same uuid). The planner
  refuses to deactivate more than min(2% of active rows, 200) unless `--allow-mass-deactivation`; a
  Nasdaq file without its `File Creation Time` trailer does not parse; `source='manual'` rows are never
  auto-deactivated; cross-file CIK conflicts (4 on 2026-09-04: IA, SPCX, AEMC, ISRL) and directory-name
  vs SEC-title disagreements (117 of 7,650) are recorded per row in the report.
- Weekly step; re-runs are idempotent. Active rows are matched by symbol and updated in place; the
  writer never relies on `ON CONFLICT (symbol) WHERE is_active` — the previous holder of a recycled
  symbol is deactivated FIRST in the same transaction, new rows are inserted by primary key and renames
  / reactivations upserted with `ON CONFLICT (instrument_id)`; the partial unique index is an assertion
  (proven by unit tests on the real 2026-09-04 snapshot and the DB round trip in CI).
- DoD (thresholds measured on the 2026-09-04 files, not assumed): ≥ 5,000 ETF rows + every S&P 500
  name (from P1-C) with an exchange; CIK on 100% of S&P 500 stocks and ≥ 99% of directory stocks (measured
  99.6% = 7,467 of 7,499 once SEC's own spellings `AAC-UN`/`ACHR-WT`/`AGM-PD` are matched; the misses are
  rights, one warrant tranche and bank holding companies that file with their banking regulator); an SEC
  identity (CIK via either file) on ≥ 80% of active ETFs — today's files give 82.5% (4,666 of 5,655;
  series/class ids alone cover 79.3%), the rest are new launches, ETNs and trusts that fall to the
  `symbol + listing_date` key, each listed with its reason; alias round-trip for the 20
  punctuation tickers in `tests/fixtures/global/symbology`; `import_stooq --dry-run` maps ≥ 99% of
  members whose ticker is in the directory (the `_` preferred forms via aliases); `python -m atlas.db`
  + `freshness_guard` register `instrument_master` (weekly, lag 8) with `build_identity.py`.

### P1-B — The price spine (`ingest_prices.py`, `ingest_corporate_actions.py`, `label_stooq.py`, `validate_global --check A`)

**Amended 2026-09-07: the vendor is Alpaca, and the SIP gate has PASSED.** The 2026-09-04 draft of
this chunk named Tiingo, a $30/month feed, and a `--check FEED` gate to replace `--check SIP`. None
of that was ever built — no `providers/tiingo.py` exists, `PRICE_PROVIDERS` has always been
`{alpaca, stooq_bulk}`, and `--check` has always accepted only `SIP` and `BASIS`. The FM opened an
Alpaca account on 2026-09-06, the free-first rule reapplied, and the SIP gate passed 8/8 on real
bars on 2026-09-07 (`data-sources.md` carries the numbers and the decision). **Nothing is bought.**
The vendor comparison in §1 stands as the contingency if Alpaca lapses; Tiingo Power is the named
fallback. The adapter already exists: `atlas/global_market/providers/alpaca.py`.

GOAL: `ohlcv_daily` holds bars 2016-01-04 → EOD for every active instrument on all three bases the
vendor serves, `corporate_actions` holds its split and cash-dividend events, the Stooq archive's rows
are labelled by the cross-check, and gate A passes on the real rows.

**What the gate measured, and what it therefore removes from this chunk.** Three questions were open
since Phase 0; all three are now answered against the account rather than the documentation:

- **The feed is consolidated, not IEX.** Median Alpaca ÷ Stooq SPY volume = 1.0017 over 39 sessions.
  The account is its own control here: the same sessions pulled with `feed=iex` return 2.79 % of the
  `feed=sip` volume. Had it been IEX-only, the $1,000,000 liquidity floor and every ADV$ band would
  have been built on roughly a fortieth of real volume.
- **Both adjusted bases come from the vendor**, so `adjust.py` is NOT built. `adjustment=split` is
  `close_adj` and `adjustment=all` is `close_tr`, measured on SPY 2016-01-04 as 201.0192 and 171.10.
  The 2026-09-04 draft made a CRSP-style back-adjustment "the ONE bespoke formula" of the platform;
  three pulls per instrument delete it, along with its parity test and its whole class of bug. Rule
  #0 is satisfied more cleanly, not less: these are the vendor's prints, not our arithmetic.
- **History stops at 2016-01-04, plan-wide.** A request from 1990 returns 2,684 bars starting
  2016-01-04 for SPY and *the identical count and start* for AAPL, listed in 1980. So this is a floor
  on the plan, not a listing date, and it is exactly the history the plan wants with zero margin.
  **Stooq is therefore the permanent source of pre-2016 history** (it reaches 1970 for names like JPM
  and KO), not the emergency fallback it was called before. Worth verifying against the vendor's own
  documentation whether that floor is fixed at 2016 or a rolling ~10-year window — I could not settle
  it from the API alone, and the answer decides whether pre-2016 coverage ever arrives on its own.

**The re-basing rule survives the vendor change, and still binds.** Alpaca's `adjustment=all` is
anchored to the present, not to the request window — the same historical date returns the same value
whatever `end` is asked for (verified on SPY 2016-01-04 against `end` of 2016-01-07 and 2026-09-05:
identical to the printed digit). That is a strictly better property than the Stooq archive's, which
re-bases to its download date. But "anchored to the present" still means every cash dividend rescales
the entire history, so **`close_tr` is recomputed over the instrument's full window on every pull,
never appended.** A history half-written on an old base and half on a new one yields a wrong return
across the seam — the exact failure the 2026-09-04 draft identified for Stooq, and it does not go
away by changing vendor. Returns are invariant to the base; absolute levels are not.

- Adapter `providers/alpaca.py` (exists; extended here): `bars(symbols, start, end, adjustment)` over
  `GET https://data.alpaca.markets/v2/stocks/bars?symbols=…` — multi-symbol, `feed=sip`,
  `limit=10000` with the `page_token` loop, 200 req/min limiter (`ingest_kite._rate_limit` pattern),
  `Decimal(str(x))` at the boundary, `calls` Counter, plain `requests` — no vendor SDK. Three pulls
  per window (`raw`, `split`, `all`) merged on `(symbol, date)`; a date present in one basis and
  absent in another is reported, never filled. Plus `actions(symbols, start, end)` over the
  corporate-actions endpoint — **whose plan tier is unverified**; if the free plan does not serve it,
  splits are detected from the `raw` ÷ `split` ratio and the row is flagged
  `source='derived_from_adjustment'`, which needs the FM's prior approval under rule #0 and is not
  taken silently. Tests key on `ALPACA_API_KEY` and hit the real endpoint (skip without keys — never
  vacuous).
- `ingest_prices.py --eod / --backfill --since 2016-01-04 [--symbols]`: targets = active
  `instrument_master` rows; floor = per-instrument `max(date)` − 5 sessions (India's buffer), cap =
  EOD; writes `open/high/low/close/volume/trade_count/vwap` + `close_adj` + `close_tr` +
  `source='alpaca'` + `adjustment_source='alpaca:sip'`. On any new dividend for an instrument, its
  `close_tr` column is rewritten for the whole window (the rule above). Aborts loudly if SPY has no
  bar for the EOD — no anchor session, nothing to score.
- `label_stooq.py` (the importer's TODO, executed): per instrument, median |Stooq close ÷ x − 1| over
  the overlap for x ∈ {close (raw), close_adj, close_tr}; best match < 0.5% → `adjustment_source` =
  `stooq:raw|split|all`; else stays `stooq:unknown` and is listed. Expected from `--check BASIS`, and
  now corroborated by the vendor: SPY → `stooq:all` (the archive's 171.85 for 2016-01-04 sits 0.44 %
  from Alpaca's total-return 171.10 and nowhere near the 201.0192 that actually traded). Stooq rows
  never overwrite vendor rows (the importer's existing guard).
- DoD = **gate A** (`validate_global --check A`, in `gate_a.py`; each row a real assertion on
  produced output). Built and run 2026-09-07, and three rows of the 2026-09-04 draft were wrong
  against real data — each corrected from a measurement, not by loosening until it passed:
  - **Everything runs over the SCORED universe**, not every listing with bars. Of 203 real
    instruments, 19 carried a 0.4 log jump, and all 19 were already excluded by the FM: ten were
    geared products doing their job (2x single-stock funds, ProShares Ultra Silver), and seven
    were sub-floor shells with genuinely broken prints (ACTS 2.14 → 24.79 with no action reported,
    AMEM 24.52 → 53.00 → 24.82 across two days). A gate over everything fails nightly for reasons
    nobody acts on. What is excluded is still counted and printed, so nothing hides there.
  - **A gap is not a move.** `lag()` walks rows, not sessions, so an instrument that halts and
    resumes gets a multi-year difference reported as a daily one: ACII read +149.9 % "in a
    session" whose previous bar was 1,029 days earlier. Moves now require consecutive sessions
    (≤ 5 calendar days), and listing gaps are reported in their own right, because a period
    return spanning one is a fiction.
  - **The FRED correlation floor is 0.99, not 0.999.** The draft carried 0.999 over from the SIP
    gate, which measures 40 calm sessions. Over the full history it reads 0.99316 on 2,513
    returns, and the tail is 2020-03-12 → 03-25 and 2025-04-09/10 — SPY returned 5.86 % on
    2020-03-13 against the index's 9.29 %. An ETF is not its index in a dislocation.
  - **The seam detector compares `close_tr` to `close_adj`, not to `close`.** Both are
    split-adjusted, so a split cancels and only dividend re-basing moves the ratio. Against the
    raw close it fires on every reverse split and says nothing true (AMZA 2020-03-31 "fell" 4.87
    against a 0.032 rounding budget; AMLP 2020-05-18, 2.37 — both reverse splits, neither a seam).
  - **There is no reliable automatic test separating a missed split from a real crash**, and the
    gate says so rather than pretending. AMZA fell 42 % on 2020-03-09, the Saudi-Russia price war,
    on four times its usual volume, and was the ONLY scored name to move that hard — so breadth
    calls a real crash an outlier exactly as it would a missed split. Large jumps are therefore
    surfaced with what a human needs to judge them; the gate hard-fails only on the impossible.
  - **A share is asserted only where a share means something.** Over 38 scored instruments one
    name is 2.6 points, so "≥ 99 %" and "≥ 97 %" are the same claim; under 200 the check reports
    and says why.
  Hard rows, at any size: SPY has an anchor bar at or before the EOD (the EOD is a CALENDAR date —
  2026-09-06 was a Sunday — and callers anchor to the latest session on or before it, so demanding
  a bar ON it fails every weekend); completeness ≥ 99 % of the previous session; no move over 100 %
  between consecutive sessions on `close_tr`; no `close_tr`/`close_adj` seam beyond cent rounding;
  SPY vs FRED ≥ 0.99. Both the seam and impossible-move rows were verified to BITE by injection —
  a stale base in the older half of SPY's history is caught at the exact seam date (0.0050 against
  a 0.000052 budget), and a tripled AMLP close is caught at +195.8 %. Staleness in SESSIONS is
  deliberately left to `freshness_guard.py`, which already owns `ohlcv_daily` at lag 0; two owners
  would drift. Still to land with `label_stooq.py`: Stooq labelled on ≥ 95 % of overlapping
  instruments and a 50-ticker sample of labelled closes within 0.1 %.

**The archive's basis can no longer be measured against FRED, and `--check BASIS` was changed
to match (2026-09-07).** Once `ingest_prices` owns the recent window, `import_stooq`'s guard
refuses to overwrite it, so the archive's rows END where the vendor's begin — and FRED's
keyless export reaches back only ten years, which is exactly the window the vendor now owns.
Archive rows and the witness stop overlapping, so the gate measured the MIXED column instead,
correctly read the vendor half as `split_only`, and FAILED — withholding every nightly publish
for a question it was never asking. It now measures `source='stooq_csv'` rows only, and passes
when no archive row is in USE: an unlabelled row carries NULL adjusted columns,
`price_basis.basis_of` resolves nothing for `stooq:unknown`, and `compute_technicals` skips it,
so nothing on the board descends from it. Label one and the measurement is required again —
verified by labelling rows and watching the gate go back to measuring, and fail for want of an
overlap. That is fail-closed, not a loosening.

The consequence to keep in view: **one instrument's `close` column now holds two different
series** — the vendor's raw traded price from 2016-01-04 and the archive's total-return
re-based close before it. SPY reads 174.297 on 2015-12-31 and 201.019 on 2016-01-04, a 15 %
"move" that is purely the basis changing. Nothing splices them today, because the archive's
adjusted columns are NULL and every consumer resolves basis before reading. What is NOT yet
built is the thing that would let the pre-2016 history be USED: a per-instrument cross-check
against the vendor's three bases over their overlap in the archive FILE (the DB has no overlap
by construction), plus a rescale onto the vendor's base. Until then the archive is inert
history, not a source the board reads.
### P1-C — Macro, index membership, benchmarks (`ingest_macro.py`, `ingest_index_membership.py`, `seed_benchmarks.py`)

GOAL: `macro_daily` carries FRED `SP500, VIXCLS, DGS10, DTB3, DTWEXBGS` through EOD−1; `index_membership`
holds the S&P 500 as SSGA's SPY holdings file reports it (current) plus the `fja05680/sp500` history as
effective-dated ranges; `benchmark_master` resolves SPY/QQQ/IWM/VXUS/AGG/GLD/BIL to instrument ids; every
S&P member carries `sector_gics` from the holdings file.
- Reuse: `atlas/global_market/providers/fred.py:fred_series` (Decimal, drops "."), NOT India's
  `ingest_macro._fred` (float, INR carry columns). Calendar = SPY sessions (`gcal.sessions`), forward-fill
  onto sessions exactly as India's `_ffill_onto` does (`scripts/foundation/ingest_macro.py:63`).
- Index history: `fja05680/sp500`'s `sp500_ticker_start_end.csv` (`ticker,start_date,end_date`; start
  INCLUSIVE, end EXCLUSIVE — verified row by row against the repository's components file, which only
  the tests fetch) → `(index_code='SP500', instrument_id, effective_from, effective_to)` with
  `source='fja05680'`; the non-`ssga` rows are RE-DERIVED from the file on every `--history` run (a
  row no longer in the spell set is deleted; nothing is lost, the file reproduces it), `ssga` rows are
  never touched, and the writing transaction asserts two invariants — no instrument with two open
  intervals, no overlapping intervals — rolling back on violation. Departure dates on `ssga` rows are
  the weekly OBSERVATION date (up to 7 sessions late). Current weights from the SSGA file
  (`weight_frac` = percent/100).
- Gates before any write (exit 2): the file's as-of is not after the EOD and not OLDER than the as-of
  recorded in `ingest_state(ssga/spy_holdings)` (`--allow-older-as-of` for a documented rollback);
  500–505 equity rows (ticker AND SEDOL) and Σ `weight_frac` ∈ [0.99, 1.01]; ≤ 2% unresolved; ≥ 98%
  in exactly one sector file. `provider_calls` is banked in its own transaction before the gates.
  `ingest_macro` exits 2 without a SPY session calendar (`--allow-raw-dates`, development only).
  `sector_gics` is written without bumping `instrument_master.updated_at`.
- Tests: the SSGA workbooks (not redistributable) and the 5.5 MB components file are fetched at test
  time under the `live` pytest marker (never `unit`); CI runs them with `ATLAS_LIVE_FIXTURES=required`
  (`make test-live`), where an unreachable source is a failure, not a skip.
- DoD: 5 series present through EOD−1 (`--check A` row); 500–505 members with Σ weight ≈ 1.00;
  `sector_gics` non-null on 100% of current members (a member without one is listed in the weekly
  `--report` CSV and counted in the log); benchmarks 7/7 resolved; producers registered
  (`macro_daily` daily lag 3; `index_membership` weekly).

### P1-D — Technicals (`compute_technicals.py`)

GOAL: `technical_daily` holds, for every instrument with bars, the plan's §A metrics computed by the
existing TA-Lib functions on `close_adj` and the return/RS/risk metrics on `close_tr`, incrementally
(floor = per-instrument `max(date)` − 5 sessions, cap = EOD), and a recompute-and-diff on 50 random
instruments differs by < 1e-6.
- Reuse verbatim: `scripts/foundation/technicals.py` (`compute_price_technicals`, `above_ema_flags`,
  `compute_volatility_volume`, `max_abs_log_jump`; EMA 10/13/21/34/50/200, RSI 14, ATR 14, BB width,
  `vol_ratio_30d/60d`, `pos_52w`). Writer pattern copied from `scripts/foundation/compute_all.py`
  (`tech_max_dates`, `_source_max_dates` capped at cutoff, `targets --shard k/N`, write only rows > floor,
  `_gdb.upsert_df(..., ["instrument_id","date"])`); India's `BENCHMARKS`/`_SRC` hardcodes become
  `benchmark_master` rows + the single `ohlcv_daily` source.
- New, small: `rs_{w}_spy` in the RELATIVE form `(1+r_i)/(1+r_b) − 1` (ADR-0002) on `close_tr` — a
  `compute_relative_strength_ratio` variant beside India's difference form, never editing it; risk block
  via `empyrical-reloaded` (`annual_volatility`, `max_drawdown`, `downside_risk`, `alpha_beta` vs SPY on
  252 sessions) — no hand-written vol/drawdown; `adv_usd_60d_median` = median(close_raw × volume) over
  the last 60 sessions (same definition as India's `adv_frame`, in USD).
- Returns use `technicals.windowed_return` (calendar-anchored 1m/3m/6m/12m); 24m/36m added the same way.
- DoD: rows for 100% of instruments that have ≥ 20 bars at EOD; recompute-and-diff < 1e-6 on 50 random
  instruments (gate A); `rs_3m_spy` re-derived from `close_tr` in the gate within 1e-6 on 20 ETFs;
  `max_abs_log_jump(close_adj) < 0.4` on ≥ 99% (the unit-bug detector); freshness registered
  (`technical_daily`, lag 0) with `compute_technicals.py` in the daily orchestrator.

### P1-E — Universe snapshot + the ADV$ table for the FM (`build_universe_snapshot.py`)

GOAL: `universe_snapshot` has one row per active instrument at EOD with `adv_usd_60d_median`,
`in_sp500`, `aum_usd` (NULL until Phase 2), `basket_eligible` (NULL until the execution provider supplies
`fractionable`), `in_universe` computed by the reused `universe_core.members`, and `exclusion_reason`
— the ONE reason an excluded row is out, NULL when it is in — and the step fails
loudly while `liquidity_min_traded_value_usd` is unset, after printing and saving the ADV$ percentile
table the FM needs to set it.
- Reuse verbatim: `scripts/foundation/universe_core.py:members(adv, floor, held_ids)` (a Decimal floor
  is currency-agnostic) and the 60-distinct-sessions-in-150-days window of
  `build_universe_snapshot.adv_frame`; `held_ids` = ∅ until M2 (`basket_constituents`).
- The FM report: percentiles P10…P99 of ADV$ across ETFs and stocks separately, count of ETFs above
  $0.5M / $1M / $2M / $5M / $10M, written to `docs/global/reports/adv_usd_<eod>.md` (real numbers, dated)
  and printed. The floor is then set from `/admin/thresholds` (or `seed_thresholds`-style insert) —
  never in code.
- DoD: 100% of active instruments have a row at EOD; `in_sp500` matches `index_membership` for the
  date; the report file exists with the real distribution; with the floor unset the step exits 2 and the
  gate fails; with it set, `in_universe` count printed and `universe_snapshot` registered (weekly lag);
  every excluded row carries exactly one `exclusion_reason` and every in-universe row carries none —
  asserted on the frame before the upsert (`assert_partition`) and by two CHECKs on the table, so the
  board can name the rule that took each instrument out instead of showing a bare "excluded".

**FM decisions, 2026-09-06** — taken from `docs/global/reports/adv_usd_2026-09-03.md`, the real
distribution this step printed, and now implemented. Universe on 2026-09-03: **2,254** of 13,155
active instruments (**1,751 ETFs + 503 stocks**), down from 6,006 on liquidity alone.

1. **Stocks: S&P 500 only.** `in_universe` for a stock = `in_sp500` on the date AND ADV$ >= floor.
   3,389 liquid non-members left the universe; all 503 members clear $1M, so stocks in = 503.
   `in_sp500` is computed per date from `index_membership`, so trailing members keep their
   membership on the dates they held it — no special case for history, and every active
   instrument still gets a snapshot ROW.
2. **`liquidity_min_traded_value_usd` = $1,000,000, SEEDED** (`seed_thresholds.py`, now 61 rows,
   with the decision and the report cited in the row's `description`). One floor for both asset
   classes: 2,114 of 5,656 ETFs clear it, and so does every S&P 500 member. The exit-2 refusal
   is unchanged and stays — it is the guard for a database where the row is missing or inactive,
   not a placeholder, and the message now distinguishes the two.
3. **Leveraged and inverse ETFs are out**, via `atlas/global_market/classify/rules.py`
   (`leverage_flags(name) -> leveraged, inverse, multiple, rule`; the plan's L2 `rules.py`, name
   half only, started early). Measured over all 5,656 active ETF names: **749 leveraged, 166
   inverse, 125 both, 790 distinct**; 363 of those clear the floor, which is the whole
   difference between 2,114 and 1,751. Rule counts: `explicit_multiple` 665, `proshares_ultra`
   60, `proshares_ultrashort` 41, `proshares_short` 17, `leverage_word` 6,
   `inverse_leveraged_words` 2, `inverse_word` 1, `leveraged_loan_asset_class` 1 (an exclusion —
   LVLN's "Leveraged Loan" is an asset class), `no_leverage_pattern` 4,863.
   - Why the ordered table looks the way it does: **ProShares is the only issuer in this market
     whose leverage words carry no number** — every Direxion / Tradr / T-REX / Corgi /
     GraniteShares / Defiance / Leverage Shares / MicroSectors geared product states its
     multiple. So three anchored patterns (`^ProShares Ultra…`, `^ProShares Short`, plus the
     issuer-stripped `UltraPro` rows the directory carries) do all the issuer work, and "Ultra
     Short" / "Short-Term" / "Ultra-Small" / "Ultra Buffer" from anyone else stay clean without
     a second rule. `multiple` is filled only from a number the NAME states: ProShares "Ultra"
     is 2x for most funds but 1.5x for UVXY, and "Short" is -1x except -0.5x for SVXY.
   - **Known recall gap for Phase 2** (name-only cannot see it): return-stacked and
     "100% A & 100% B" funds carry ~200% notional with no multiple in the name — 8 Return
     Stacked funds, `BTGD`, `ISBG`, `ISSB`, and `UPAR` (a 1.4x risk-parity fund). Two of them,
     **RSST and RSSB**, clear the floor and ARE in the universe today. So are **FIAT** and
     **WNTR**, YieldMax "Short <ticker> Option Income" funds that carry inverse exposure inside
     an option wrapper. `derivatives_share` + holdings settle all six in Phase 2.
4. **Every excluded instrument says WHY, in the table** — `exclusion_reason`, one of `no_bars`,
   `too_few_observations`, `stale`, `not_sp500`, `leveraged`, `inverse`, `below_floor`, and NULL
   exactly when the row is in. On 2026-09-03 the FIRST rule to take each row out was `not_sp500`
   6,016, `below_floor` 2,323, `too_few_observations` 1,809, `leveraged` 595, `no_bars` 117,
   `inverse` 38, `stale` 3 — 10,901, the whole excluded set, each row counted once. Smaller than
   the rule counts in 3, which count every instrument a rule TOUCHES: 980 of the 6,996
   non-members never had an ADV$ at all, 154 of the 749 geared ETFs were already out on the
   ladder, and of the 166 inverse ETFs 21 had no ADV$ and 107 are geared too (an UltraShort
   reports as `leveraged`). The reason is the board's Universe column, in English.

### P1-F — Ops: orchestration, health, runbook

GOAL: `atlas_global_daily.sh` runs end to end on a real EOD (ingest_prices → ingest_macro →
compute_technicals → build_universe_snapshot → gates → health snapshot → revalidate), writes
`atlas_pipeline_runs` / `atlas_validator_results` / `atlas_health_daily`, and the producer registry
covers every table it fills.
- `write_health_snapshot.py` = India's `scripts/ops/write_health_snapshot.py` with `M` swapped,
  `TRACKED` = the global tables, `_GATE_VALIDATORS` = `{validate_global_A: gate_A, freshness_guard}`,
  tz America/New_York; the health tables here HAVE primary keys, so `upsert_df` replaces the plain
  insert (idempotent re-runs).
- `freshness_guard.py`: KEY = `ohlcv_daily 0`, `technical_daily 0`, `macro_daily 3`; BOARD =
  `instrument_master 8`, `index_membership 8`, `universe_snapshot 8`; COMPLETENESS = {ohlcv_daily,
  technical_daily}; PRODUCERS filled; registry test goes real.
- `provider_calls`: every script upserts its adapter's `calls` Counter at exit (`(run_date, provider,
  endpoint)`), `/health` shows the day's count vs the vendor's daily limit.
- Publish: `frontend-global/src/app/api/revalidate/route.ts` (POST, bearer `GLOBAL_REVALIDATE_SECRET`,
  `revalidateTag('eod')`), env in Vercel + box `.env`; the orchestrator's curl block uncommented.
- Runbook `docs/global/runbook.md`: box cron lines (01:00 UTC Tue–Sat daily, Sat 01:30 UTC weekly),
  the prod schema apply + seed approval, the `atlas_global_app` role grants (psql, not DDL files),
  env var list, Vercel/Supabase Auth setup, the first-night checklist, and "what to do when a gate
  fails".
- DoD: a full nightly run on a real EOD against a DB with the schema applied (box or laptop) — all
  steps success, gates PASS, health rows present, `/health` renders them; `test_producer_registry`
  green with non-empty registries; runbook reviewed by the FM.

### P1-G — First board surfaces (`/etfs`, `/etfs/[symbol]`, `/stocks`, `/stocks/[symbol]`, `/health`)

GOAL: the board shows real facts and price-derived numbers for every instrument — no scores, no
classification yet — in the Chart-room language, from `atlas_global` via the transaction pooler,
deployed on Vercel with ISR + the `eod` tag, and the FM can compute any-period returns on a real ETF.
- `/etfs`, `/stocks`: virtualised `DataTable` (design §5) of `instrument_master ⋈ technical_daily@EOD ⋈
  universe_snapshot@EOD`: symbol, name, exchange, price, `ret_1m/3m/6m/12m`, `rs_3m_spy`, `pos_52w`,
  `adv_usd_60d_median`, listing date; facets: exchange, S&P member, in-universe, ADV$ bands; sort;
  ⌘K search over symbol/name (client-side over the loaded list).
- `/etfs/[symbol]`, `/stocks/[symbol]`: `EntityHeader` (facts with source + as-of), price chart
  (`close_adj`, `close_tr`, SPY overlay; **lightweight-charts**, the library India's board already uses
  — port `frontend/src/components/charts/AtlasLightweightChart.tsx`), the RS strip
  (`rs_{1w,1m,3m,6m,12m}_spy`), the any-period return calculator (two dates → return on `close_tr`, on
  `close_adj`, and SPY's, with "as of" and the source), the data-provenance block (`source`,
  `adjustment_source`, first/last bar, sessions count). Empty states say what is missing and why.
- `/health`: already reads the three ops tables — wire freshness of `ohlcv_daily`/`technical_daily`
  from `atlas_health_daily` and the vendor call budget from `provider_calls`.
- Cache tag: every board query that feeds an ISR page wraps in `unstable_cache(..., { tags: ['eod'] })`
  — the `'eod'` literal `/api/revalidate` flushes (`src/lib/revalidate.ts`); until a page's queries carry
  it, the nightly publish is a no-op for that page.
- Design decisions taken now (FM may override): density default **calm**; no client-facing pages
  until M2 (all pages `fm|analyst`); `/etfs/[symbol]` written for an analyst, plain-English
  translation deferred to M2.
- DoD: `tsc`/vitest/lint/build green; queries live in `src/lib/queries/*` (schema gate scans them);
  Playwright smoke on the Vercel preview: `/etfs` renders ≥ 5,000 rows' worth of data through
  virtualisation, `/etfs/SPY` shows a chart with ≥ 2,400 sessions and the calculator returns the same
  number `technical_daily.ret_12m` holds for the matching window; no "NaN", no "Unmapped", no raw stat
  on user pages; `revalidateTag('eod')` verified by a manual POST.

## 5. FM actions (blocking, in order)
1. ~~Alpaca account~~ **DONE 2026-09-06/07.** `ALPACA_API_KEY` + `ALPACA_API_SECRET` (paper, free) and
   `GLOBAL_PRICE_PROVIDER=alpaca` in `.env`; the SIP gate PASSED 8/8 on real bars. Nothing is bought.
2. `EDGAR_IDENTITY="Nimish Shah <email>"` in `.env` (the SEC fair-access User-Agent) — never in-repo.
3. `FRED_API_KEY` (India's key) in the global `.env` — OPTIONAL; unset, `ingest_macro` uses FRED's
   keyless CSV export. Supply it for the JSON API's revision vintages, not to unblock anything.
4. Prod: `python scripts/global_market/apply_ddl.py` (41 tables) → `seed_thresholds.py --dry-run` →
   approve → `seed_thresholds.py`; create the `atlas_global_app` role per the runbook.
5. Vercel project (root `frontend-global/`, region bom1) + Supabase Auth (magic link, redirect
   allowlist `<origin>/login/callback`) + the FM's row in `atlas_global.app_user`.
6. After P1-E prints the ADV$ percentile table: set `liquidity_min_traded_value_usd`.

## 6. What this amends in `plan.md`

- Data-source table, row "OHLCV 2016→": primary = the licensed feed (§1), fallback = Stooq archive,
  gate = FEED then A. Alpaca rows (OHLCV, corporate actions, assets) are struck; `fractionable` and
  `tradable` come from the execution provider chosen in M4, so `basket_eligible` is NULL until then.
- Phase 1 DoD: "≥ 3,300 ETFs" → "≥ 5,000 ETFs" (5,655 listed on 2026-09-04); "series_id ≥ 95%" →
  "SEC identity ≥ 80%" (measured 82.5%; series/class ids exist only for 1940-Act funds).
- `ohlcv_daily.source` / `corporate_actions.source` CHECK constraints gain the vendor value.
- ~~`--check SIP` is replaced by `--check FEED`~~ — **withdrawn 2026-09-07.** `--check SIP` was never
  replaced, it was RUN, and it passed. `--check` accepts `SIP` and `BASIS`; gate A arrives with P1-B. The
  "SIP gate log" becomes the "feed gate log".

## 7. Verification, end to end

1. FEED gate PASS logged with real numbers (`data-sources.md`).
2. Backfill on a real DB: `ingest_prices --backfill` → `adjust` → `label_stooq` → `compute_technicals`
   → `build_universe_snapshot` (fails on the unset floor, prints the ADV$ table) → FM sets the floor →
   re-run → gate A PASS; `make gate`, both schema gates 0, `check_file_size` 0.
3. One real nightly (`atlas_global_daily.sh`) on the box or laptop: every step success, gates PASS,
   `atlas_health_daily` rows, `/health` renders them, revalidate fired.
4. Spot checks on real instruments: SPY (`stooq:all`, returns vs FRED), AAPL (2020 4:1 split visible
   in `corporate_actions` and invisible in `close_adj`), BRK.B (alias round-trip), a 2026 launch
   (fallback identity key), a delisted Stooq member (`is_active=false`, history kept), TQQQ/UVXY
   (present, unclassified, `basket_eligible` NULL).
5. FM review: the ADV$ percentile table → liquidity floor; the `/etfs` density; the feed-gate log.

## 8. Risks

1. Vendor terms for commercial display — legal confirms before any client sees a number (M2);
   Phases 1–3 are internal.
2. Adjustment parity failures on a few instruments (vendor's own errors, odd distributions, return of
   capital): those rows keep NULL adjusted columns and are listed — nothing scores on them.
3. Backfill volume: ~6,200 instruments × ~2,700 sessions ≈ 17M rows ≈ 2–3 GB with indexes on
   Supabase — confirm the project's storage headroom before the backfill (FM action).
4. Nasdaq directory "stock" rows include preferreds, warrants, units and notes (7,499 rows) — only
   S&P 500 members are stock targets in Phase 1; everything else is identity-only until Phase 3.
5. The MF JSON lags new launches: ~1,000 ETFs use the fallback key; a later SEC id never re-mints.
