# v6 Data Source Map

**Generated:** 2026-05-26
**Status:** Living document — update when query modules are added or renamed.
**Machine-check:** `python scripts/v6_data_availability_audit.py`
**Seed verification:** Run `scripts/v6_data_availability_check.sql` via EC2 (see that file for instructions).

---

## Autonomous resolutions (patch header 2026-05-26)

These decisions were applied to the v6 query layer during ground-truth migration scan.
Future agents MUST understand this history before touching query modules.

| Deprecated reference | Replacement | Reason | Migration |
|---|---|---|---|
| `atlas_universe_snapshot` | `atlas_universe_stocks` | `atlas_universe_snapshot` never existed per migration 081z comment; "vaporware" | 002 |
| `atlas_sector_breadth_daily` | Derive from `atlas_scorecard_daily.features` JSONB (`ema_distance_20/50/200`) | Table never created; breadth signal embedded in scorecard JSONB per migration 080 | 080 |
| `atlas_fund_holdings_history` | `atlas_fund_scorecard.top_holdings` JSONB | `atlas_fund_holdings_history` not in any migration; holdings exist as JSONB column since migration 093 | 093 |
| `atlas_ledger_public` | `atlas_ledger` | Actual table name per migration 083; no `_public` suffix | 083 |

---

## Phase A — Existing query modules (7 modules)

### `frontend/src/lib/queries/v6/stocks.ts`

| Table | Migration | Columns depended on |
|---|---|---|
| `atlas_universe_stocks` | 002 (`CREATE TABLE IF NOT EXISTS`) | `instrument_id`, `symbol`, `company_name`, `sector`, `tier`, `effective_to` |
| `atlas_stock_signal_unified` | **VIEW** — see note below | `instrument_id`, `rs_state`, `engine_state`, `is_investable`, `date` |
| `atlas_stock_metrics_daily` | 004 (`CREATE TABLE IF NOT EXISTS`) | `instrument_id`, `date`, `ret_1m`, `ret_3m`, `ret_6m`, `ret_12m`, `rs_pctile_3m` |
| `atlas_conviction_daily` | 092 (`op.create_table`) | `instrument_id`, `snapshot_date`, `tenure`, `verdict`, `ic`, `best_rule_id` |

**Note on `atlas_stock_signal_unified`:** This is a SQL VIEW, not an Alembic-managed table.
It was defined in `docs/superpowers/specs/2026-05-18-atlas-signal-consolidation-design.md`
and applied directly to the Supabase `atlas` schema (outside of Alembic).
The `scripts/v6_data_availability_audit.py` treats it as a `KNOWN_VIEW` — it is valid
and must not be flagged as missing.

---

### `frontend/src/lib/queries/v6/etfs.ts`

| Table | Migration | Columns depended on |
|---|---|---|
| `atlas_etf_scorecard` | 093 (`op.create_table`) | `instrument_id`, `ticker`, `etf_name`, `etf_category`, `snapshot_date`, `composite_score`, `matrix_conviction_score`, `sector_strength_score`, `tracking_quality_score`, `aum_bracket_score`, `liquidity_score`, `expense_ratio_score`, `rank_in_category`, `category_size`, `is_atlas_leader`, `eli5` |
| `atlas_universe_etfs` | 002 (`CREATE TABLE IF NOT EXISTS`) | `ticker`, `etf_name`, `effective_to` |
| `atlas_etf_metrics_daily` | 004 (`CREATE TABLE IF NOT EXISTS`) | `ticker`, `date`, `ret_1m`, `ret_3m`, `ret_6m`, `ret_12m`, `rs_pctile_3m` |

---

### `frontend/src/lib/queries/v6/funds.ts`

| Table | Migration | Columns depended on |
|---|---|---|
| `atlas_fund_scorecard` | 093 (`op.create_table`) | `scheme_code`, `snapshot_date`, `fund_name`, `fund_category`, `amc`, `fund_style`, `composite_score`, `risk_adjusted_return_score`, `holdings_conviction_score`, `style_sector_score`, `cost_manager_score`, `rank_in_category`, `category_size`, `is_atlas_leader`, `is_avoid`, `confidence_low`, `eli5`, `top_holdings` (JSONB) |
| `atlas_universe_funds` | 002 (`CREATE TABLE IF NOT EXISTS`) | `mstar_id`, `scheme_name`, `aum_cr`, `effective_to` |
| `atlas_fund_metrics_daily` | 004 (`CREATE TABLE IF NOT EXISTS`) | `mstar_id`, `nav_date`, `ret_1m`, `ret_3m`, `ret_6m`, `ret_12m`, `rs_pctile_3m` |

**JSONB dependency:** `atlas_fund_scorecard.top_holdings` is consumed via
`jsonb_to_recordset()` in Phase B.3 (PortfolioAwareness layer). This is a
JSONB column unpack, NOT a separate table reference.

---

### `frontend/src/lib/queries/v6/sectors.ts`

| Table | Migration | Columns depended on |
|---|---|---|
| `atlas_sector_states_daily` | 005 (`CREATE TABLE IF NOT EXISTS`) | `sector_name`, `date`, `sector_state`, `bottomup_state`, `topdown_state`, `bottomup_rs_state`, `bottomup_momentum_state`, `participation_rs_pct` |
| `atlas_sector_metrics_daily` | 004 (`CREATE TABLE IF NOT EXISTS`) | `sector_name`, `date`, `bottomup_ret_1m`, `bottomup_ret_3m`, `bottomup_rs_3m_nifty500`, `participation_50`, `constituent_count` |

**Sector breadth (autonomous resolution):** `atlas_sector_breadth_daily` DOES NOT EXIST.
Breadth data is embedded in `atlas_scorecard_daily.features` JSONB (columns
`ema_distance_20`, `ema_distance_50`, `ema_distance_200`). Any Phase B/C query
needing sector breadth must derive it via subquery on `atlas_scorecard_daily`.

---

### `frontend/src/lib/queries/v6/regime.ts`

| Table | Migration | Columns depended on |
|---|---|---|
| `atlas_market_regime_daily` | 004 (`CREATE TABLE IF NOT EXISTS`) | `date`, `regime_state`, `deployment_multiplier`, `pct_above_ema_50`, `pct_in_strong_states`, `pct_weinstein_pass` |

---

### `frontend/src/lib/queries/v6/instrument.ts`

No direct table queries. Delegates entirely to `stocks.ts` (`getStocksForDate`)
and `snapshot.ts` (`getLatestSnapshotDate`). Table dependencies inherited from
those two modules.

---

### `frontend/src/lib/queries/v6/snapshot.ts`

| Table | Migration | Columns depended on |
|---|---|---|
| `atlas_conviction_daily` | 092 (`op.create_table`) | `snapshot_date` (MAX) |
| `atlas_etf_scorecard` | 093 (`op.create_table`) | `snapshot_date` (MAX) |
| `atlas_fund_scorecard` | 093 (`op.create_table`) | `snapshot_date` (MAX) |
| `atlas_scorecard_daily` | 080 (`op.create_table`) | `date` (MAX) |
| `atlas_market_regime_daily` | 004 (`CREATE TABLE IF NOT EXISTS`) | `date` (MAX) |
| `atlas_sector_states_daily` | 005 (`CREATE TABLE IF NOT EXISTS`) | `date` (MAX) |

---

## Phase B — Future query modules (not yet in code)

These modules are planned for Phase B (portfolio-awareness layer) and Phase C
(page composites). They are listed here so future agents understand the planned
data layer.

### `frontend/src/lib/queries/v6/portfolio.ts` (Phase B)

| Table | Migration | Purpose |
|---|---|---|
| `atlas_user_lots` | 084 (`op.create_table`) | User portfolio positions |
| `atlas_paper_portfolio` | 084 (`op.create_table`) | Paper portfolio |
| `atlas_signal_calls` | 080 (`op.create_table`) | Active cell signals per instrument |
| `atlas_cell_definitions` | 080 (`op.create_table`) | Cell metadata (cell_id, archetype, tenure) |
| `de_index_constituents` | **JIP public schema** | Benchmark sector weights (B.2 BenchmarkToggle overlay) |

**Note on `de_index_constituents`:** This table lives in the `public` schema (JIP data engine),
not the `atlas` schema. It is referenced as `public.de_index_constituents`. The audit script
treats all `de_*` tables as known JIP external tables and does not flag them.

### `frontend/src/lib/queries/v6/switch.ts` (Phase D)

| Table | Migration | Purpose |
|---|---|---|
| `atlas_mf_switch_rules` | 085 (`op.create_table`) | SWITCH selection rules (Q3→Q1, ≥6mo, expense tie-break) |
| `atlas_fund_scorecard` | 093 (`op.create_table`) | Fund ranking + category |

### `frontend/src/lib/queries/v6/ledger.ts` (Phase D.10)

| Table | Migration | Purpose |
|---|---|---|
| `atlas_ledger` | 083 (`op.create_table`) | Realized outcomes per signal_call |
| `atlas_signal_calls` | 080 (`op.create_table`) | Signal call context |

### `frontend/src/lib/queries/v6/gold_availability.ts` (Task A.2)

| Table | Migration | Purpose |
|---|---|---|
| `de_index_prices` | **JIP public schema** | Gold series existence check (`benchmark_code = 'GOLD'`) |

---

## Blockers (seed data gate)

Run `scripts/v6_data_availability_check.sql` via EC2 to verify row counts.
Results are stored at `/tmp/v6_check_results.txt`.

| Check | Expected | If zero |
|---|---|---|
| `atlas_mf_switch_rules` | ≥ 1 | **v6.0 BLOCKER** — SWITCH page has no rules. Write migration 094 with sensible seed data: Q3→Q1 same-category, ≥6mo consistency, expense-ratio tie-break. |
| `atlas_ledger` | any | Non-blocker — D.10 "realized outcomes" shows empty state gracefully. |
| `de_index_constituents` WHERE `index_code = 'NIFTY500'` | ≥ 400 | Blocker for B.2 benchmark-weight overlay; BenchmarkToggle degrades to show counts only. |
| `atlas_universe_stocks` (effective_to IS NULL) | ~727 | Universe integrity — investigate if count < 700. |
| `atlas_fund_scorecard.top_holdings` IS NOT NULL | ≥ 100 | B.3 fund holdings carousel empty — run scorecard backfill. |
| `atlas_scorecard_daily.features` IS NOT NULL (latest date) | ≥ 500 | conviction_tape all-NEUTRAL — run `atlas/features/scorecard_writer.py` backfill. |

---

## Known external tables (JIP public schema — not in Alembic)

These tables are owned by the JIP data engine and live in the `public` schema.
The Atlas frontend references them via `public.de_*` prefix. They are valid dependencies
and must NOT be flagged as missing by the audit script.

| Table | Schema | Description |
|---|---|---|
| `de_index_prices` | `public` | Daily index close prices (used for Gold availability check + benchmark returns) |
| `de_index_constituents` | `public` | Index constituent membership (used for benchmark sector weights in B.2) |
| `de_index_master` | `public` | Index metadata (75 curated indices) |

---

## Known views (applied directly to Supabase — not in Alembic)

These are SQL VIEWs defined in `docs/superpowers/specs/2026-05-18-atlas-signal-consolidation-design.md`
and applied directly to the Supabase `atlas` schema (outside Alembic migrations).

| View | Description |
|---|---|
| `atlas_stock_signal_unified` | Re-derives legacy column names from `atlas_stock_state_daily` per-row |
| `atlas_sector_signal_unified` | Bottom-up sector aggregator (constituent stock states) |
| `atlas_fund_signal_unified` | Bottom-up fund aggregator (constituent stock states) |
| `atlas_etf_signal_unified` | Bottom-up ETF aggregator (constituent stock states) |
