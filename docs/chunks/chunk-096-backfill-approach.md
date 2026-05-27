# Chunk 096 approach — backfill atlas_signal_calls + mf_recommendation_daily + etf_signal_calls

## Actual data scale (verified 2026-05-26)

- `atlas_conviction_daily` latest date: 2026-05-22, 2988 rows (747 iids × 4 tenures)
  - POSITIVE: 75, NEGATIVE: 288, NEUTRAL: 2625
- `atlas_scorecard_daily` latest: 747 rows on 2026-05-22
- `atlas_cell_definitions`: 21 active cells
- Join (conviction + scorecard + cell_definitions) for POSITIVE/NEGATIVE: **363 rows** — exactly matches expected
- `atlas_fund_scorecard` latest: 587 rows on 2026-05-22 (sub_metrics has NO nav key)
- `atlas_etf_scorecard` latest: 34 rows on 2026-05-22, 9 is_atlas_leader=TRUE
- `atlas_market_regime_daily` on 2026-05-22: `regime_state = 'Cautious'` (not in atlas_regime_state enum)

## Chosen approach

Single Alembic migration (096) with `op.execute(sql)` raw SQL. Three INSERT...SELECT blocks.

### Backfill #1: atlas_signal_calls (363 rows expected)
- JOIN: conviction_daily + scorecard_daily (scorecard_id FK) + cell_definitions
- `cell_definition_id` is the column in conviction_daily (not `cell_id`)
- Regime fallback: CASE WHEN value IN enum_values THEN cast ELSE 'Elevated' END
  - 'Cautious' and 'Constructive' are pre-v6 regime labels not in the atlas_regime_state enum;
    'Elevated' is the closest semantic match (mid-risk, non-extreme state)
- `confidence_unconditional` sourced from conviction_daily.ic (COALESCE to 0 if NULL)
- No ON CONFLICT clause needed (table is empty); add NOT EXISTS guard for idempotency

### Backfill #2: atlas_mf_recommendation_daily — SKIP
- `nav` column is NOT NULL in atlas_mf_recommendation_daily
- `atlas_fund_scorecard.sub_metrics` keys: alpha, aum_cr, calmar, max_dd, sharpe, sortino,
  ter_pct, up_capture, down_capture, fund_age_years, n_observations, manager_tenure_years
- NO nav key in sub_metrics. Zero rows can be inserted without fabricating data.
- Decision: skip this backfill per rule (a) from task spec. Document in migration docstring.
- atlas_mf_recommendation_daily stays empty. Frontend must handle empty state.

### Backfill #3: atlas_etf_signal_calls (9 rows expected — leaders only)
- Source: atlas_etf_scorecard WHERE is_atlas_leader = TRUE on max snapshot_date
- etf_category → atlas_etf_sub_category: 'broad_index' → 'broad_market'; all others → 'sectoral'
- atlas_etf_scorecard has no is_avoid column; only leaders (POSITIVE action) inserted
- cell_id: hardcoded subquery for Large/POSITIVE/6m (heuristic; documented as stopgap)
- Regime same fallback as #1
- STOPGAP: marked in docstring; v6.1 should replace with rule_dsl evaluation against ETF state

## Wiki patterns checked
- Existing signal_calls migration (080): uses same enum types
- Conviction daily migration (092): column names verified
- Fund/ETF scorecard migration (093): no NAV column gap identified

## Edge cases handled
- NULL ic in conviction_daily: COALESCE(c.ic, 0) for NOT NULL confidence_unconditional
- Regime mismatch (Cautious/Constructive): fallback to 'Elevated'
- Idempotency: NOT EXISTS guards in WHERE clause prevent re-insertion
- NAV gap: skip entire backfill #2, document clearly

## Expected runtime on t3.large
- All three INSERTs operate on < 600 rows total. Sub-second.
