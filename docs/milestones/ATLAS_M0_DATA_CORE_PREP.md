# Atlas-M0 — Data Core Fill and Prep

**Document:** ATLAS_M0_DATA_CORE_PREP
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Builder:** Claude Code (executing in JIP Data Core codebase)

**References:**
- `GAP_MAP.md` (gap analysis — already complete)
- `validation_M1_2026-05-03.md` (gap validation — already passed V3)
- `01_BACKEND_ARCHITECTURE.md` Section 4.3 (de_etf_holdings spec)

---

## 1. Goal

The gap analysis is **already done**. `GAP_MAP.md` enumerates every gap with fetch_from / fetch_to / source_to_use specified. Validation V3 passed.

This milestone has three jobs and only three jobs:

1. **Execute the existing gap-fill list** (258 items already identified)
2. **Build `de_etf_holdings`** — the only genuinely-new data dependency Atlas added beyond the original audit
3. **Clean up** — drop unused derived tables (with confirmation)

No re-audit. No re-verification. The work specified below assumes the gap analysis output is the authoritative input.

---

## 2. Job 1 — Execute the Gap-Fill List

Per `GAP_MAP.md` Validation V3 Action Specification:

| Status | Count | fetch_from | fetch_to | Source |
|---|---|---|---|---|
| PARTIAL stocks | 156 | 2011-04-01 | instrument's earliest_date - 1 | NSE BHAV copy |
| PARTIAL MFs | 100 | scheme's latest_date + 1 | 2026-05-03 (or current T-1) | AMFI daily NAV |
| MISSING international | 2 | 2011-04-01 | 2026-05-03 | yfinance |

Each row in this table has full fetch parameters already specified. JIP Data Core has existing ingestion playbooks for all three sources (BHAV, AMFI, yfinance). Run them.

### 2.1 Stocks (156 PARTIAL)

Use the per-instrument list in the gap analysis output. Run NSE BHAV copy ingestion for each instrument's specified date range. Insert into `public.de_equity_ohlcv`.

### 2.2 MFs (100 PARTIAL)

Use the per-scheme list in the gap analysis output. Run AMFI daily NAV ingestion for each scheme's specified date range. Insert into `public.de_mf_nav_daily`.

### 2.3 International (2 MISSING)

Per `GAP_MAP.md`:

| Index | yfinance ticker | Notes |
|---|---|---|
| S&P 500 | `^GSPC` | Direct index data |
| MSCI World | `URTH` (iShares MSCI World ETF) or `^990100-USD-STRD` | URTH is tradable proxy; index ticker may not return data |

**Naming convention:** Insert into `public.de_global_prices` with ticker prefixes to distinguish from Indian ETFs already in the table:
- `INTL_SPX` for S&P 500
- `INTL_MSCIWORLD` for MSCI World (note in readiness report whether sourced from URTH proxy or direct index)

**Stooq alternative:** Nimish has a Stooq bulk dump locally. If S&P 500 is in the Stooq file, ingest from there in preference to yfinance (more complete history, no rate limits). Inspect the dump for `SPX` / `^GSPC` patterns first; fall back to yfinance only if not present.

### 2.4 Definition of Done for Job 1

- [ ] All 156 PARTIAL stocks have ≥252 trading days before 2014-04-01 in `de_equity_ohlcv`
- [ ] All 100 PARTIAL MFs have NAV data current to T-1 (no stale dates)
- [ ] `INTL_SPX` and `INTL_MSCIWORLD` exist in `de_global_prices` with daily coverage 2014-04-01 to T-1
- [ ] No data in any existing rows was modified — only new rows inserted

---

## 3. Job 2 — Build `de_etf_holdings`

This is genuinely new. Wasn't in the original gap analysis because the original analysis was scoped to JIP Intelligence's data needs; Atlas-M5 added the requirement for thematic ETF dominant-sector classification, which needs ETF holdings data.

### 3.1 Create the Table

```sql
CREATE TABLE public.de_etf_holdings (
    ticker                 VARCHAR(32)     NOT NULL,    -- ETF ticker (matches de_etf_master.ticker)
    instrument_id          UUID            NOT NULL,    -- Underlying holding (matches de_instrument.id)
    weight                 NUMERIC(8,6)    NOT NULL,    -- Holding weight (decimal: 0.0512 = 5.12%)
    as_of_date             DATE            NOT NULL,    -- Portfolio disclosure date
    last_disclosed_date    DATE            NOT NULL,    -- When Morningstar received it
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, instrument_id, as_of_date),
    CONSTRAINT chk_etf_holdings_weight_range 
        CHECK (weight >= 0 AND weight <= 1)
);

CREATE INDEX idx_de_etf_holdings_ticker_date 
    ON public.de_etf_holdings (ticker, as_of_date DESC);
CREATE INDEX idx_de_etf_holdings_instrument 
    ON public.de_etf_holdings (instrument_id);
```

### 3.2 Build the Morningstar Ingestion

The Morningstar Direct API is already integrated for `de_mf_holdings`. This is an extension of the existing job, not new infrastructure.

**Endpoints (same service Morningstar provides for MF holdings):**

```
List universe:     GET /v2/service/mf/{service_id}/universeid/{universe_id}?accesscode={access_code}
Instrument detail: GET /v2/service/mf/{service_id}/{id_type}/{identifier}?accesscode={access_code}

Service ID:    fq9mxhk7xeb20f3b
Universe ID:   q3zv6b817mp4fz0f
Access code:   ftijxp6pf11ezmizn19otbz18ghq2iu4
```

These are routing/access identifiers (not login credentials). Store in environment variables as defaults; rotate via env vars if Morningstar changes them.

**Logic to extend:**

The existing Morningstar ingestion job iterates the universe and writes mutual fund holdings to `de_mf_holdings`. Extend it to:

1. Identify which instruments in the universe are ETFs (Morningstar response field — verify on first call; common values are `instrumentType = 'ETF'` or `categoryType = 'ETF'`)
2. For ETFs, parse the same holdings section
3. Write to `de_etf_holdings` keyed by ticker (instead of `de_mf_holdings` keyed by mstar_id)
4. Run on the same monthly cadence as MF holdings refresh

### 3.3 Caveats to Verify on First Call

- **Field names:** Morningstar response field names need verification. Don't bulk-process 100 ETFs until one ETF call has been inspected and the parser confirmed.
- **Top-N vs full holdings:** Some Morningstar responses return only top 10 or top 25 holdings for ETFs. For Broad ETFs holding 500 stocks this is fine; for Thematic ETFs it might miss long-tail exposures. Document what's returned.
- **Historical disclosures:** Determine whether the API returns only the latest disclosure or historical ones. If only latest, this run gets current snapshots; v1 adds historical backfill if useful.

### 3.4 Definition of Done for Job 2

- [ ] `de_etf_holdings` table created
- [ ] Morningstar ingestion extended to write ETF holdings to the new table
- [ ] At least one disclosure populated for every ETF in `universe_etfs_100.csv` (or documented exceptions where Morningstar has no data for an ETF)
- [ ] Monthly refresh cadence confirmed integrated with the existing Morningstar job schedule

---

## 4. Job 3 — Cleanup

JIP Data Core has derived tables built for the prior JIP Intelligence methodology. Atlas computes its own derivations, so these are not consumed by Atlas.

### 4.1 Tables Atlas Does NOT Consume

| Table | Row count | Built for |
|---|---|---|
| `de_rs_scores` | 34,281 | Prior RS methodology |
| `de_sector_breadth_daily` | 313,308 | Prior breadth measures |
| `de_equity_technical_daily` | 11,272 | Prior technical indicators |
| `de_mf_derived_daily` | (per inventory) | Prior MF metrics |
| `de_mf_sector_exposure` | 13,211 | Prior MF sector view |

Plus likely-unused (Atlas doesn't consume):
- `de_fo_bhavcopy` (367,666 rows) — F&O data
- `de_bse_announcements` (5,254 rows)
- `de_market_cap_history` (12,217 rows) — categorical only, Atlas uses traded value as proxy

### 4.2 Question for Architect Sign-Off

**Do any of these tables have consumers other than the deprecated JIP Intelligence engine?**

- **If no:** drop them all. Saves storage, removes ambiguity, prevents anyone accidentally using stale derived data.
- **If yes:** keep the consumed ones, drop the rest.

Default if unanswered: keep all (safer to leave clutter than break a forgotten consumer). Nimish provides answer before this job executes.

### 4.3 Definition of Done for Job 3

- [ ] Architect has provided list of confirmed unused tables (or "drop all")
- [ ] Drops executed via migration script
- [ ] Drop list documented in readiness report

---

## 5. Update Frequency Lock

Atlas runs daily compute. Confirm existing JIP nightly ingestion meets these SLAs:

| Source | Required by | Atlas reads at |
|---|---|---|
| Equity / ETF / Index daily prices | 22:00 IST T-1 | 22:00 IST nightly |
| AMFI daily NAVs | 23:00 IST T-1 | 23:00 IST nightly |
| Morningstar MF + ETF holdings | Within 5 business days of disclosure | Read on disclosure-day Atlas runs |
| International benchmarks (yfinance) | 23:00 IST T-1 | 23:00 IST nightly |

If existing nightly pipeline already meets these, no change. If anything is broken or slower than required, fix.

---

## 6. Readiness Report

Generate `data_core_readiness_M0.md` containing:

1. **Job 1 outcome:** number of stocks / MFs / international tickers filled, any items that couldn't be filled (with reason)
2. **Job 2 outcome:** ETF holdings ingestion summary — coverage rate, any ETFs without Morningstar data, top-N vs full disclosure status
3. **Job 3 outcome:** which tables were dropped vs kept, with rationale
4. **Update frequency confirmation:** all required ingestion jobs verified active
5. **Accepted limitations:** anything not fully resolved (e.g., MSCI World sourced via URTH ETF proxy, MF schemes Morningstar doesn't cover, etc.)
6. **Final call:** GO / REVIEW / NO-GO for Atlas-M1

### Pass criteria

- Job 1: ≥95% of identified gaps filled (allow small residual for delisted/data-unavailable instruments)
- Job 2: `de_etf_holdings` table exists and populated for ≥80 of 100 universe ETFs
- Job 3: cleanup decision made, drops executed if confirmed
- Update frequency: all required ingestion jobs verified running on schedule

If all pass → GO. Any partial → REVIEW (proceed with documented limitations). Any total failure → NO-GO.

---

## 7. Atlas-M0 Definition of Done

- [ ] Job 1 (gap fill) executed against the GAP_MAP.md V3 list
- [ ] Job 2 (`de_etf_holdings`) created and populated
- [ ] Job 3 (cleanup) executed per architect confirmation
- [ ] Update frequency confirmed for all required tables
- [ ] `data_core_readiness_M0.md` generated with explicit GO/REVIEW/NO-GO call
- [ ] Architect (Nimish) signs off
- [ ] If GO: Atlas-M1 unblocked

---

## 8. Operating Notes

**The gap analysis was already done.** `GAP_MAP.md` is the authoritative input list. Don't re-audit; execute against it.

**Don't reinvent ingestion.** JIP Data Core has working BHAV, AMFI, Morningstar, yfinance integrations. M0 directs which gaps to fill — JIP's existing playbooks do the actual ingestion.

**Smoke-test Morningstar for ETFs on one call before bulk processing.** Verify response shape, field names, top-N vs full holdings, then run bulk.

**Cleanup is irreversible.** Re-deriving dropped tables means re-running the prior JIP Intelligence compute. Confirm consumers before dropping.

---

## 9. What Comes Next

After M0 signs off as GO (or REVIEW with accepted limitations): start Atlas-M1 in the Atlas codebase.

---

**Document version:** 2.0
**Last updated:** 2026-05-04
