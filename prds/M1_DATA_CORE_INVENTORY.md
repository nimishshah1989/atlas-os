# M1 — Data Core Inventory & Gap Map

**Milestone:** M1  
**Category:** FOUNDATION (diagnostic)  
**Estimated complexity:** S (small, but consequential)  
**Depends on:** None  
**Blocks:** M2, M3 (and transitively all downstream)

---

## 1. Objective

Produce a verified inventory of what raw historical data JIP Data Core currently holds, and map it against the data this platform requires. The output is a delta document that tells M2 exactly what to ingest (and what not to bother ingesting because it already exists).

This milestone does not write any computed data. It does not modify any existing tables. It does not change the schema. It is purely diagnostic. Its deliverable is three structured documents that together describe the current state, the required state, and the gap between them.

---

## 2. Scope

### 2.1 In Scope

- Schema discovery across the existing JIP Data Core PostgreSQL database
- Per-table row counts, date ranges, distinct identifier counts
- Per-instrument coverage analysis (where the data permits)
- Generation of canonical universe lists (750 stocks, 100 ETFs, 75 indices, ~400 MF schemes) by ranking against current data
- Gap mapping per required instrument with READY / PARTIAL / MISSING status

### 2.2 Out of Scope

- Ingestion of any new data
- Computation of any derived metrics
- Schema modifications, additions, or deletions
- Migration of any data
- Validation against external sources (Tier 1 validation begins in M2)

### 2.3 Read-Only Constraint

This milestone executes only `SELECT` and `information_schema` queries. The single permitted DDL is the optional creation of an `intelligence_inventory_cache` table to persist inventory results for downstream milestones to consume. No `UPDATE`, `DELETE`, `DROP`, or `ALTER` on any existing table.

---

## 3. Tables

### 3.1 Tables Created in This Milestone

**Optional cache table** (for performance and for downstream consumption):

```sql
CREATE TABLE IF NOT EXISTS intelligence.inventory_cache (
  table_name        TEXT NOT NULL,
  identifier_column TEXT NOT NULL,    -- the column used as instrument key in this table
  identifier_value  TEXT NOT NULL,    -- the value in that column
  date_column       TEXT NOT NULL,    -- the column holding the date
  earliest_date     DATE,
  latest_date       DATE,
  observation_count INTEGER,
  null_close_count  INTEGER,          -- nulls in the primary value column
  scanned_at        TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (table_name, identifier_column, identifier_value)
);
```

This table is the canonical source for downstream milestones querying "what do we have for instrument X." It is rebuilt at the start of each M1 run (truncated and repopulated) so it always reflects current state. Schema name `intelligence` is the proposed schema for new platform tables; final schema name confirmed during M1 execution (see Open Questions).

### 3.2 Tables Read in This Milestone

All tables prefixed `de_` in the existing JIP Data Core. Schema names are not assumed — they are discovered in Phase A.

---

## 4. Formulae and Mechanisms

The milestone executes in four sequential phases. Each phase produces an artifact consumed by the next.

### 4.1 Phase A — Schema Discovery

**Purpose:** Discover what tables exist, what columns they contain, and which columns serve as identifier and date keys for each table. This is necessary because identifier columns differ across tables (`instrument_id` for equity, `mstar_id` for funds, `index_code` for indices, etc.).

**Mechanism:**

```sql
-- Step A.1: Enumerate all tables in candidate schemas
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('public', 'data_engine', 'fie_v3', 'jip')
  AND table_name LIKE 'de\\_%' ESCAPE '\\'
  AND table_type = 'BASE TABLE'
ORDER BY table_schema, table_name;
```

```sql
-- Step A.2: For each table found, enumerate columns and types
SELECT 
  table_schema,
  table_name,
  column_name,
  data_type,
  is_nullable,
  ordinal_position
FROM information_schema.columns
WHERE (table_schema, table_name) IN ( /* tables from A.1 */ )
ORDER BY table_schema, table_name, ordinal_position;
```

**Phase A output:** A structured map of `(table → columns → types)`. Stored as `phase_a_schema.json`.

**Heuristics for identifying key columns:**

| Likely identifier column patterns | Likely date column patterns |
|---|---|
| `instrument_id`, `mstar_id`, `index_code`, `isin`, `symbol`, `scheme_code`, `ticker` | `date`, `nav_date`, `trade_date`, `as_of_date`, `effective_from` |

Claude Code applies these heuristics to classify each column, and where multiple candidates exist (e.g., a table has both `symbol` and `instrument_id`), prefers the more specific identifier in this priority order: `instrument_id` > `mstar_id` > `index_code` > `isin` > `scheme_code` > `symbol` > `ticker`.

### 4.2 Phase B — Per-Table Inventory

**Purpose:** For each raw and reference table, compute aggregate statistics and per-instrument coverage.

**Mechanism:** For each table identified in Phase A, generate a dynamic query using the discovered identifier and date columns.

**Aggregate-level template:**

```sql
SELECT 
  COUNT(*) AS total_rows,
  COUNT(DISTINCT {{identifier_col}}) AS distinct_instruments,
  MIN({{date_col}}) AS earliest_date,
  MAX({{date_col}}) AS latest_date,
  COUNT(*) FILTER (WHERE {{date_col}} >= '2010-04-01') AS rows_post_2010,
  COUNT(*) FILTER (WHERE {{date_col}} >= CURRENT_DATE - INTERVAL '30 days') AS rows_last_30d
FROM {{schema}}.{{table}};
```

**Per-instrument template (writes to inventory cache):**

```sql
INSERT INTO intelligence.inventory_cache 
  (table_name, identifier_column, identifier_value, date_column,
   earliest_date, latest_date, observation_count, null_close_count)
SELECT 
  '{{schema}}.{{table}}'                AS table_name,
  '{{identifier_col}}'                  AS identifier_column,
  {{identifier_col}}::TEXT              AS identifier_value,
  '{{date_col}}'                        AS date_column,
  MIN({{date_col}})                     AS earliest_date,
  MAX({{date_col}})                     AS latest_date,
  COUNT(*)                              AS observation_count,
  COUNT(*) FILTER (WHERE {{value_col}} IS NULL) AS null_close_count
FROM {{schema}}.{{table}}
GROUP BY {{identifier_col}};
```

`{{value_col}}` is the table's primary value column — `close` for OHLCV tables, `nav` for NAV tables, `close` for index prices.

**Phase B output:** Populated `intelligence.inventory_cache` table + a summary `phase_b_inventory.md` document with per-table aggregates.

### 4.3 Phase C — Universe List Generation

**Purpose:** Generate the canonical lists of instruments the platform will operate on.

#### 4.3.1 Stock Universe — 750 Names

**Method:** Query the existing `de_index_constituents` table (or equivalent) for the most recent constituent list of Nifty 500 and Nifty Microcap 250. Take the union and deduplicate.

```sql
-- Conceptual; adapt to actual table structure discovered in Phase A
WITH latest_nifty500 AS (
  SELECT DISTINCT instrument_id 
  FROM de_index_constituents 
  WHERE index_code = 'NIFTY500' 
    AND as_of_date = (SELECT MAX(as_of_date) FROM de_index_constituents WHERE index_code = 'NIFTY500')
),
latest_microcap250 AS (
  SELECT DISTINCT instrument_id 
  FROM de_index_constituents 
  WHERE index_code = 'NIFTYMICROCAP250'
    AND as_of_date = (SELECT MAX(as_of_date) FROM de_index_constituents WHERE index_code = 'NIFTYMICROCAP250')
)
SELECT instrument_id FROM latest_nifty500
UNION
SELECT instrument_id FROM latest_microcap250;
```

**Fallback method (if constituents not available):** Rank stocks by latest available daily market cap (`close * shares_outstanding`) and take top 750. This requires shares-outstanding data, which may not exist in JIP Data Core today — flagged as Open Question.

**Tier assignment:** Tag each of 750 with tier (Large / Mid / Small / Micro) based on Nifty 100 / Midcap 150 / Smallcap 250 / Microcap 250 membership.

#### 4.3.2 ETF Universe — 100 Names

**Method:** Rank ETFs (instrument_type = 'ETF' in the master, or identified by ISIN convention / symbol pattern) by 60-day median traded value over the most recent 60 trading days. Take top 100.

```sql
WITH recent_60d AS (
  SELECT 
    instrument_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close * volume) AS median_traded_value
  FROM de_equity_ohlcv
  WHERE date >= CURRENT_DATE - INTERVAL '90 days'  -- ~60 trading days
    AND instrument_id IN (SELECT instrument_id FROM de_instrument WHERE instrument_type = 'ETF')
  GROUP BY instrument_id
)
SELECT instrument_id 
FROM recent_60d 
ORDER BY median_traded_value DESC 
LIMIT 100;
```

#### 4.3.3 Index Universe — ~75 Names

**Method:** Reference the curated list defined in Master PRD Section 5.3. Cross-check against `de_index_master` for which indices have data available. Indices in the curated list but not in `de_index_master` go to MISSING.

#### 4.3.4 MF Universe — ~400 Names

**Method:** Filter `de_mf_master` (or equivalent) by the criteria in Master PRD Section 5.4: Equity category, Regular plan, Growth option only. Apply category sub-filters.

```sql
SELECT mstar_id, scheme_name, category, sub_category, plan, option
FROM de_mf_master
WHERE category = 'Equity'
  AND plan = 'Regular'
  AND option = 'Growth'
  AND sub_category IN (
    'Large Cap', 'Mid Cap', 'Small Cap',
    'Large & Mid Cap', 'Multi Cap', 'Flexi Cap',
    'ELSS', 'Sectoral', 'Thematic'
  )
  -- Excludes: Hybrid, Debt, Liquid, Solution-oriented, Index Funds, Global
ORDER BY mstar_id;
```

The exact `sub_category` values may differ from the above (depends on Morningstar taxonomy used); Claude Code adapts based on actual values discovered.

**Phase C output:** Four CSV files committed to the spec repo:
- `universe_stocks_750.csv` — instrument_id, symbol, name, tier
- `universe_etfs_100.csv` — instrument_id, symbol, name, theme
- `universe_indices_75.csv` — index_code, name, category, sub_category
- `universe_mf_schemes.csv` — mstar_id, scheme_name, sub_category

### 4.4 Phase D — Gap Mapping

**Purpose:** For each required instrument from Phase C, determine current data status against the 15-year (April 2011 – present) target.

**Status definitions:**

| Status | Meaning |
|---|---|
| `READY` | Required data is present, complete, and clean. No M2 action needed. |
| `PARTIAL` | Required data is present but with gaps or shorter history than target. M2 action: fetch the missing date range. |
| `MISSING` | Required data is not in JIP Data Core at all. M2 action: full historical fetch from external source. |
| `LATE_LISTED` | Instrument legitimately has shorter history (delisted, recent IPO, recent index addition). Marked READY with note. |

**Mechanism:** Join the universe lists (Phase C) against the inventory cache (Phase B) and classify each row.

```sql
-- Conceptual structure for stock gap mapping
WITH required AS (
  SELECT instrument_id, 'stock' AS instrument_type
  FROM universe_stocks_750
),
have AS (
  SELECT 
    identifier_value AS instrument_id,
    earliest_date,
    latest_date,
    observation_count
  FROM intelligence.inventory_cache
  WHERE table_name LIKE '%de_equity_ohlcv%'
    AND identifier_column = 'instrument_id'
),
gap AS (
  SELECT 
    r.instrument_id,
    h.earliest_date,
    h.latest_date,
    h.observation_count,
    CASE
      WHEN h.instrument_id IS NULL THEN 'MISSING'
      WHEN h.earliest_date > '2011-04-01' AND <stock listed before 2011-04-01> THEN 'PARTIAL'
      WHEN h.latest_date < CURRENT_DATE - INTERVAL '5 days' THEN 'PARTIAL'
      WHEN h.observation_count < <expected obs given listing date> * 0.95 THEN 'PARTIAL'
      ELSE 'READY'
    END AS status,
    CASE
      WHEN h.instrument_id IS NULL THEN '2011-04-01'
      WHEN h.earliest_date > '2011-04-01' THEN '2011-04-01'
      ELSE h.latest_date + 1
    END AS fetch_from,
    CURRENT_DATE - 1 AS fetch_to
  FROM required r
  LEFT JOIN have h ON h.instrument_id = r.instrument_id
)
SELECT * FROM gap;
```

The exact logic for "expected observations given listing date" requires knowing each stock's listing date — typically available from `de_instrument` or NSE master. If not available, fall back to "expected ≈ trading_days_between(earliest_target, today) × 0.99".

**Phase D output:** A consolidated gap map document `GAP_MAP.md` with one section per instrument type (stocks, ETFs, indices, MFs, gold, international benchmarks). Each section: a table of instrument_id, status, current_earliest_date, current_latest_date, fetch_from, fetch_to, source_to_use.

---

## 5. Validations and Quality Checks

### 5.1 Validation V1 — Universe Completeness

Every required instrument in Phase C must appear in the gap map (Phase D) with one of the four statuses. Zero instruments lost.

```python
assert len(gap_map_stocks) == 750
assert len(gap_map_etfs) == 100
assert len(gap_map_indices) <= 75  # may be smaller if some not available
assert len(gap_map_mfs) >= 350     # may be smaller depending on filters
assert all(row['status'] in {'READY', 'PARTIAL', 'MISSING', 'LATE_LISTED'} for row in gap_map)
```

### 5.2 Validation V2 — READY Sample Verification

For each instrument type, randomly sample 10 instruments marked READY. Run a direct query against the source table for 5 random dates within their stated date range. Confirm rows exist and primary value column is non-null.

```python
for instrument_type in ['stock', 'etf', 'index', 'mf']:
    ready_instruments = [r for r in gap_map[instrument_type] if r['status'] == 'READY']
    sample = random.sample(ready_instruments, min(10, len(ready_instruments)))
    for instrument in sample:
        sample_dates = random_dates_within(instrument.earliest_date, instrument.latest_date, n=5)
        for date in sample_dates:
            row = query_source_table(instrument.id, date)
            assert row is not None, f"READY instrument {instrument.id} missing data on {date}"
            assert row[primary_value_col] is not None
```

### 5.3 Validation V3 — Action Specification Completeness

Every PARTIAL and MISSING entry must have `fetch_from`, `fetch_to`, and `source_to_use` populated. Sources must be from the master's locked source list (NSE BHAV, AMFI, Morningstar API, yfinance, MCX/Nippon Gold ETF).

### 5.4 Quality Check Q1 — Schema Discovery Sanity

The schema discovery (Phase A) must find at minimum: one OHLCV table, one NAV table, one index table, one instrument master table. If any of these is missing, escalate to Open Questions and halt — the platform cannot proceed without these foundational tables.

### 5.5 Quality Check Q2 — Inventory Cache Population

After Phase B, the inventory cache must have ≥ 1,000 rows (covers 750 stocks + 100 ETFs + 75 indices + 400 funds at minimum). If significantly less, the per-instrument inventory queries failed silently — diagnose and rerun.

### 5.6 Quality Check Q3 — Date Range Sanity

For tables that should have ~15 years of data, the spread between `earliest_date` and `latest_date` should be ≥ 12 years for at least 50% of instruments. If less, flag in the inventory document — likely indicates the historical backfill from `de_pipeline_log` was never completed.

### 5.7 Validation Report

Output: `validation_M1_<YYYY-MM-DD>.md`. Committed to repo. Contains:
- Phase A summary: tables found, columns, key column inferences
- Phase B summary: aggregate row counts, date ranges per table
- Phase C summary: counts per universe list with first 10 entries
- Phase D summary: status counts (% READY / PARTIAL / MISSING per type)
- All validations V1–V3 results with pass/fail
- All quality checks Q1–Q3 results
- Total rows scanned, total queries executed, wall time

---

## 6. Principles (Milestone-Specific)

These supplement the master's Four Laws.

### 6.1 Read-Only

Phase A through D execute only SELECTs against existing tables. The single permitted write is to the new `intelligence.inventory_cache` table. No existing table is modified.

### 6.2 Verified Facts Only

Every status in the gap map is derived from a SELECT result on the actual database. No status is inferred from the JIP Data Core spec, from memory of past builds, or from the master PRD. If a table named in the spec doesn't exist in the database, the gap map reflects that, regardless of what was promised earlier.

### 6.3 Per-Instrument Granularity

Aggregate row counts hide the bias where some instruments have 15 years of clean data and others have 6 months. The inventory operates at per-instrument granularity from Phase B onward.

### 6.4 Idempotent

Running M1 twice in a row produces identical artifacts. The inventory cache is truncated and repopulated; gap map and universe lists are regenerated from scratch each run.

### 6.5 Diagnostic, Not Prescriptive

M1 reports current state. It does not decide what to do about gaps — that's M2. M1 surfaces the gap; the human or the next milestone decides how to fill it.

---

## 7. Boundary Conditions

### 7.1 Delisted Stocks

A stock that delisted before today legitimately has a truncated `latest_date`. If `latest_date` < CURRENT_DATE but the stock is recorded as delisted in the instrument master, status = `LATE_LISTED` with note `delisted on YYYY-MM-DD`. Not flagged as PARTIAL.

### 7.2 Recent IPOs

A stock that listed after April 2011 cannot have 15 years of data. If `earliest_date` aligns with the listing date in the instrument master, status = `LATE_LISTED` with note `listed on YYYY-MM-DD`. The fetch_from for any incremental ingest is the listing date, not 2011-04-01.

### 7.3 Holidays and Trading Calendar

Coverage gaps that align with NSE trading holidays are not gaps. The expected observation count for a date range is `actual_trading_days(start, end)` — typically ~250/year, not 365. Use a trading calendar table or an empirical count from Nifty 50 itself as the reference.

### 7.4 Mutual Funds with Less History

An MF that was launched in 2018 cannot have 15 years of NAV. Same handling as recent IPOs — `LATE_LISTED` with launch date. fetch_from is launch date.

### 7.5 Indices Launched Mid-Period

Some Nifty indices were launched after 2011 (e.g., Nifty Microcap 250 in 2021). For these, expected history starts at index inception, not 2011. Same `LATE_LISTED` handling.

### 7.6 Holdings Data

Holdings data via Morningstar is a known new build per Master PRD Section 10. M1 marks all required fund holdings as MISSING with source = "Morningstar API (M2 build)". No further analysis needed in M1 for holdings.

### 7.7 International Benchmarks

MSCI World and S&P 500 may not exist in JIP Data Core's `de_global_prices` table at all, or may have partial coverage. Both possibilities are valid; gap map reflects whatever is found.

### 7.8 Gold Price

Gold price comes via Nippon India Gold ETF NAV. M1 checks whether this scheme's NAV exists in `de_mf_nav_daily`. If yes, status = READY (since the AMFI ingest already covers it). If no, status = PARTIAL or MISSING — confirms the gold pipeline needs explicit handling in M2.

### 7.9 Schema Discovery Yields Zero Tables

If Phase A finds no `de_*` tables in any candidate schema, M1 halts immediately and surfaces this as a critical Open Question. Likely indicates wrong database connection or wrong schema search.

---

## 8. Points of Self-Direction (Claude Code Decides)

These are explicit decisions delegated to the implementing agent during M1 execution.

### 8.1 Database Connection Discovery

The master declares the RDS host and database (`fie_v3`). If Phase A finds the relevant `de_*` tables in a different schema or database, Claude Code follows the data — does not abort. Records the actual discovered location in the validation report.

### 8.2 Identifier Column Inference

Where multiple candidate identifier columns exist for a table (e.g., a table has both `instrument_id` and `symbol`), Claude Code picks per the priority ordering in Section 4.1. If none of the priority candidates exist, Claude Code picks the most specific available column and notes the choice in the validation report.

### 8.3 Schema Naming for New Tables

The master proposes `intelligence` as the schema for new platform tables. If this schema doesn't exist, Claude Code creates it. If a different schema is conventional in the existing JIP Data Core codebase (e.g., everything currently lives in `public`), Claude Code may use `public` for the inventory cache table and notes the divergence. Final convention confirmed in the validation report.

### 8.4 Query Optimization Strategy

Per-instrument inventory across ~5M rows can run as a single big GROUP BY or as parallel per-table queries. Claude Code picks based on observed performance — if the single big query takes >10 minutes, decompose. Records timing in the validation report.

### 8.5 Output Format Beyond Required Fields

The required columns in `GAP_MAP.md` are: instrument_id, status, current_earliest_date, current_latest_date, fetch_from, fetch_to, source_to_use. Claude Code may add useful diagnostic columns (observation_count, expected_count, completeness_ratio, days_stale) at its discretion to make the gap map more readable.

### 8.6 Universe Generation Fallbacks

If `de_index_constituents` is absent or stale, Claude Code falls back to ranking by daily market cap as described in 4.3.1. If shares-outstanding is also unavailable, Claude Code falls back to ranking by 60-day median traded value as a liquidity proxy and records the fallback in the validation report.

### 8.7 Sample Sizes

The validations specify minimums (10 instruments per type, 5 dates per instrument). Claude Code may sample more if it improves confidence and remains within the wall-time budget.

---

## 9. Open Questions

These items cannot be resolved from the chat interface and must be resolved during M1 execution by querying the actual database state. They are not blockers; they are flagged uncertainties that M1 will resolve.

### 9.1 Schema Location

What schema(s) do the `de_*` tables actually live in? Master proposes `public`, `data_engine`, `fie_v3`, or `jip` as candidates. Resolved by Phase A.

### 9.2 Actual Table List

The Master PRD Section 4.5 estimates 18 tables across three layers. The actual current state of JIP Data Core may differ — some spec'd tables may not exist, some unspec'd tables may exist (e.g., `de_market_cap_history`, `de_data_anomalies`). Resolved by Phase A.

### 9.3 Migration State

Were the previously-spec'd migrations actually completed? Specifically:
- 25.8M MF NAV rows from `fie2-db-1.nav_daily` → `de_mf_nav_daily` — done?
- 1.4M equity rows from `fie_v3.compass_stock_prices` → `de_equity_ohlcv` — done?
- 4,638 index constituent rows from `fie_v3.index_constituents` → `de_index_constituents` — done?
- 535 fund master records from `mf_engine.fund_master` → `de_mf_master` — done?

Resolved by Phase B (row counts).

### 9.4 Historical Backfill State

The earlier JIP Data Engine spec referenced a "BHAV Copy Full Backfill" job slated to run for 5–7 days post-sprint. Was this ever completed? If yes, equity OHLCV should go back to ~2000 for many stocks. If no, equity history is limited to what was migrated. Resolved by Phase B (date ranges per stock).

### 9.5 Shares Outstanding Availability

Daily market cap calculation for universe ranking requires shares outstanding. Is this column present in `de_equity_ohlcv` (or a separate table)? If yes, where? If no, M1 falls back to ranking by traded value. Resolved by Phase A (column inspection) and noted as a v2 enhancement need.

### 9.6 Index Constituents Currency

Is the `de_index_constituents` table maintained current, or is it stale from the original migration? The Nifty 500 reconstitutes semi-annually; if last update was 2024, the constituent list is out of date. Resolved by checking `MAX(as_of_date)` per index.

### 9.7 Morningstar Holdings Pipeline

Has any Morningstar holdings data been ingested into JIP Data Core, or is this a fresh pipeline for M2? Resolved by Phase A — search for any table containing "holdings" in name.

### 9.8 Global Prices State

Does `de_global_prices` exist and is it populated? The earlier spec referenced ingestion via yfinance for major global indices. Resolved by Phase A and Phase B.

### 9.9 Gold ETF NAV Coverage

Is Nippon India Gold ETF (or HDFC Gold ETF) included in the existing AMFI NAV ingestion, or filtered out as non-equity? Resolved by querying `de_mf_nav_daily` for the relevant scheme codes.

---

## 10. Acceptance Criteria (Definition of Done)

M1 is complete when ALL of the following are true and verified:

### 10.1 Deliverables Produced

- [ ] `JIP_DATA_CORE_INVENTORY.md` — Phase A + Phase B output, committed to spec repo
- [ ] `universe_stocks_750.csv`, `universe_etfs_100.csv`, `universe_indices_75.csv`, `universe_mf_schemes.csv` — Phase C output, committed to spec repo
- [ ] `GAP_MAP.md` — Phase D output, committed to spec repo
- [ ] `validation_M1_<date>.md` — validation report, committed to spec repo
- [ ] `intelligence.inventory_cache` table created and populated in the database

### 10.2 Validations Passed

- [ ] V1: Every required instrument appears in gap map with valid status
- [ ] V2: Sample verification of READY instruments — 100% pass on 10 samples per type
- [ ] V3: Every PARTIAL and MISSING entry has fetch_from, fetch_to, source_to_use populated

### 10.3 Quality Checks Passed

- [ ] Q1: Schema discovery found minimum required tables (OHLCV, NAV, index, instrument master)
- [ ] Q2: Inventory cache populated with ≥ 1,000 rows
- [ ] Q3: Date range sanity check for 15-year-ish coverage (or documented gap)

### 10.4 Open Questions Resolved

Each item in Section 9 has a one-line answer in the validation report.

### 10.5 Wall Time

M1 completes in under 60 minutes total, including all phases. If exceeding, document why in the validation report.

### 10.6 No Side Effects

- [ ] No existing table modified (verified via row count comparison before/after on top 5 tables by row count)
- [ ] No data deleted
- [ ] No schema altered (other than creation of `intelligence` schema and `inventory_cache` table)

---

## 11. Handoff to M2

The output of M1 directly drives M2's scope.

**M2 inputs from M1:**
- `GAP_MAP.md` — defines exactly what to ingest
- `universe_*.csv` — defines the instrument lists to operate on
- `intelligence.inventory_cache` — programmatic source for "what do we already have"
- The validation report — confirms M1's findings are reliable

**Decision rules for M2 sizing:**

| If GAP_MAP shows... | M2 scope is... |
|---|---|
| ≥ 90% of required data is READY | Small (1–2 days, mostly fill recent gaps + new tables for holdings/sectors) |
| 50–90% READY | Medium (2–4 days, larger backfills + new tables) |
| < 50% READY | Large (4–7 days, significant external data fetching) |

This sizing is informational — M2 is scoped properly regardless. The point is that M1's output sets realistic expectations.

---

*End of M1 Spec.*
