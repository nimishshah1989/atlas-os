---
chunk: D.10
project: atlas-os
date: 2026-05-26
task: /v6/cells/[cell_id] cell detail page
---

## Data scale (observed)

- atlas_cell_walkforward_runs: table exists (migration 081z), row count unknown without DB access (likely <100 rows — only completed sweeps)
- atlas_ledger: table exists (migration 083 / 094), expected 0 rows at v6.0 launch
- atlas_signal_calls: has rows (conviction_tape backfilled 2026-05-25)
- atlas_cell_definitions: 24 cells

## Chosen approach

RSC page shell (≤250 LOC) fetches all data server-side via existing query modules:
- getCellById (C.1) — cell definition + IC + fric-adj + bh_fdr_q (null) + drift_status
- getSignalCallsByCell (C.6 recent_signal_calls) — firing history + today's stocks
- getHeldIidSet (B.1 portfolio_holdings) — for PortfolioBadge column

No new query module needed. D.10 composes existing C.1 + C.6 + B.1.

## Table sources used

- atlas_cell_definitions (via getCellById)
- atlas_signal_calls (via getCellById for predicted_excess, getSignalCallsByCell for history)
- atlas_cell_walkforward_runs (raw SQL query in page.tsx for backtest windows)
- atlas_ledger (raw SQL for realized outcomes — empty at v6.0)
- atlas_paper_portfolio (via getHeldIidSet)

## Components created

1. page.tsx — thin RSC wrapper, ≤250 LOC
2. CellDetailClient.tsx — main client component, ≤500 LOC
3. CellHero.tsx — hero strip, ≤300 LOC
4. CellRulePlainEnglish.tsx — rule_dsl → plain English, ≤200 LOC

## Edge cases

- bh_fdr_q is always null from DB → render "—"
- predicted_excess null → render "—"
- drift_warn chip only when drift_status === 'drift_warn'
- No stocks firing today → "No stocks firing this cell today"
- atlas_ledger empty → "No realized outcomes yet"
- atlas_cell_walkforward_runs empty → "Insufficient backtest data"
- rule_dsl may be empty {} → render empty list gracefully

## ConvictionTape import note

ConvictionTape requires a `Tape` object from `@/lib/api/v1`. For cell firing table
we show PortfolioBadge + signal calls data but do NOT need ConvictionTape per stock
(we don't have per-stock tape from cell query). Show simplified state badge instead.

## Expected runtime

Page load: 3 SQL queries → <50ms on t3.large; well within Next.js RSC budget.
