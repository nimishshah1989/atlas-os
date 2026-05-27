# v6 backend MVs — Funds · ETFs · Calls Performance (locked plan)

**Date:** 2026-05-26
**Branch base:** `main`
**Driving mockups:** `06-funds.html`, `06a-fund-ppfas.html`, `07-etfs.html`,
`07a-etf-goldbees.html`, `08-calls-performance.html` (see
`~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/`).
**Glossary:** `CONTEXT.md` + `docs/v6/glossary-additions-2026-05-26.md`.

## Scope

Seven materialized views land as separate PRs. Each is a thin read surface
over existing tables, except where flagged "needs upstream data work."

| # | MV | Driver | Upstream | Independent? |
|---|---|---|---|---|
| 1 | `mv_fund_list_v6` | 06 Funds list | `atlas_mf_recommendation_daily`, `atlas_fund_scorecard`, `de_mf_master` | ✓ |
| 2 | `mv_fund_amc_ladder` | 06 AMC leaderboard | `atlas_mf_recommendation_daily` | ✓ |
| 3 | `mv_fund_deepdive` | 06a per-fund | `mv_fund_quartile_monthly` (NEW), `atlas_fund_scorecard.sub_metrics` | needs 60-mo backfill |
| 4 | `mv_etf_list_v6` | 07 ETFs list | `atlas_etf_signal_calls`, `atlas_etf_scorecard` | ✓ |
| 5 | `mv_etf_premium_track` | 07a premium history | **NEW** `atlas_etf_daily_metrics` | needs new daily ETL + 1y backfill |
| 6 | `mv_etf_deepdive` | 07a per-ETF | PR 5 + `atlas_etf_signal_calls` | depends on PR 5 |
| 7 | `mv_calls_performance` | 08 Calls Performance | `atlas_signal_calls`, `atlas_ledger`, `de_index_prices` | ✓ |

## Build order (by dependency, not calendar)

1. **Independent batch first:** PRs 1, 2, 4, 7 in any order — no new ETLs.
2. **PR 5 next:** ships `atlas_etf_daily_metrics` table + nightly compute +
   1y backfill of `premium_bps`, `te_60d`, `adv_20d_inr`.
3. **PR 6 after PR 5:** consumes the new ETF daily metrics.
4. **PR 3 last:** depends on whether `atlas_mf_recommendation_daily` has ≥ 60
   month-end snapshots. If not, ship `mv_fund_quartile_monthly` upstream MV
   that recomputes per-fund per-month-end peer quartile from raw NAV +
   `de_mf_master.category`.

## Cross-cutting decisions (locked)

- **Refresh strategy:** all MVs are `CREATE MATERIALIZED VIEW … WITH NO DATA`
  + populated in the migration's data step, with explicit indexes for the
  page hot-path. Nightly refresh joins SP02's `pg_cron` job at 20:00 IST
  via `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
- **Schema:** `atlas.mv_*`. No new schemas.
- **Sub-metrics:** JSONB for editorial deep-dive fields; structured columns
  for filterable list-page columns.
- **Decimal everywhere for money/percent.** Floats are hook-blocked.
- **MV staleness contract:** every MV carries `as_of date` + `computed_at`
  TIMESTAMPTZ columns. Frontend API surfaces `data_as_of` per envelope spec
  in `CLAUDE.md`.
- **One MV per migration.** Helps the rollback story; one file = one
  reviewable unit.

## Per-PR exit criteria

Each PR exits when:

1. Alembic migration applies cleanly on a fresh DB (test fixture).
2. `REFRESH MATERIALIZED VIEW <name>` runs without errors.
3. Output row count for a known snapshot date matches the row count of the
   driving join (deterministic).
4. At least one schema test asserts the column list + types.
5. At least one data test asserts a known invariant (e.g. row count > 0
   when source has > 0 rows; canonical filter narrows to expected slice).
6. `/codex review` returns ACCEPT.
7. `coderabbit:code-review` returns no P0/P1 findings.
8. `/review` returns ACCEPT.

## ADR-worthy decisions

- **ADR 2026-05-26-etf-daily-metrics-table.md** — PR 5 introduces a new
  store-vs-compute trade-off. Write this ADR before migration 097.
- **ADR 2026-05-26-mv-refresh-strategy.md** — first MV (PR 1) locks the
  CONCURRENTLY-refresh + pg_cron pattern. Write this ADR with PR 1.

## Live verification gap (2026-05-26 session)

The CLI environment for this session cannot reach Supabase
(`db.nanvgbhootvvthjujkvs.supabase.co:5432` blocked). All MVs are designed
against migration files + existing compute paths. **EC2 deploy step** for
each PR must verify:

- Source table row counts match expectations (≥0, recent dates).
- MV refresh runs in < 60 s.
- Page-hot-path query plans hit the new indexes (`EXPLAIN ANALYZE`).

This is in-scope for the per-PR EC2 deploy step (not the PR review gate).

## Open follow-ups (NOT in scope for these 7 PRs)

- pg_cron registration of nightly `REFRESH MATERIALIZED VIEW`. Currently
  done by hand on EC2; the modern path is a migration that
  `INSERT INTO cron.job (…)`. Out of scope here — ticket separately.
- Drift between `atlas_signal_calls.action` (POSITIVE/NEUTRAL/NEGATIVE)
  and the user-facing display vocab (BUY/HOLD/AVOID/SELL). The display
  rendering lives in the frontend API layer per CONTEXT.md
  §"Cell display name". MVs store internal vocab; do NOT pre-render
  display labels.
- AMC backfill for `atlas_mf_recommendation_daily.amc` if column missing.
  PR 2 confirms; if missing, joins to `de_mf_master.amc`.

