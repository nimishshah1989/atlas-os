# Chunk: Decision Engine Task 3.5 — Portfolio Current-vs-Target + Compliance Display

## Approach

### Gap Analysis from Exploration

**`getStaticPortfolioById`** currently returns instruments as `Array<{instrument_id, instrument_type, weight_pct}>`. Missing fields:
- `target_weight_pct` — present in JSONB after migration 093 backfill, but not in the SELECT type or cast
- `sector` — must be JOINed from `atlas_universe_stocks`  
- `is_small_cap` — derived from `in_nifty_100 = false AND in_nifty_500 = false`

**`atlas_portfolio_proposed_change`** — no TS query exists. Will create `frontend/src/lib/queries/proposed-changes.ts`.

**Compliance** — Python `check_compliance` has 6 rules. Will mirror as `frontend/src/lib/policy-compliance.ts`, pure function, no DB.

**Page LOC** — currently 173 LOC. Adding one `<CurrentVsTarget>` import + one `<section>` ~6 LOC = ~179. Well under 250.

### Files

1. **`frontend/src/lib/policy-compliance.ts`** — pure TS `checkCompliance` mirroring Python 6 rules exactly
2. **`frontend/src/lib/queries/proposed-changes.ts`** — server-only query for `atlas_portfolio_proposed_change` pending rows  
3. **Extend `frontend/src/lib/queries/portfolios.ts`** — update `StaticPortfolioDetail.instruments` type to include `target_weight_pct: number | null`, `sector: string`, `is_small_cap: boolean`; update SQL to LEFT JOIN `atlas_universe_stocks` and JSONB-cast `target_weight_pct`
4. **`frontend/src/components/portfolio/CurrentVsTarget.tsx`** — table component
5. **Modify `frontend/src/app/portfolios/[id]/page.tsx`** — import + render + pass data

### Data Scale

`atlas_universe_stocks` has ~1600 rows. A portfolio has at most ~50 instruments. JOIN is trivially fast. No pagination needed.

### SQL for extending `getStaticPortfolioById`

The instruments JSONB stores per-element `{instrument_id, instrument_type, weight_pct, target_weight_pct}`. To enrich with sector + is_small_cap:

```sql
SELECT
  p.id,
  p.name,
  (
    SELECT jsonb_agg(
      elem || jsonb_build_object(
        'sector',      COALESCE(u.sector, 'Unknown'),
        'is_small_cap', (u.in_nifty_100 IS NOT TRUE AND u.in_nifty_500 IS NOT TRUE)
      )
    )
    FROM jsonb_array_elements(p.instruments) AS elem
    LEFT JOIN LATERAL (
      SELECT sector, in_nifty_100, in_nifty_500
      FROM atlas.atlas_universe_stocks
      WHERE instrument_id = (elem->>'instrument_id')::uuid
      ORDER BY effective_from DESC LIMIT 1
    ) u ON TRUE
  ) AS instruments,
  ...
FROM atlas.strategy_fm_custom_portfolios p
WHERE p.id = $1
```

This is a correlated subquery per row (1 portfolio row, up to 50 instruments). Well within t3.large.

### TS `checkCompliance` — 6 rules mirrored exactly

```
Policy input shape: {
  max_per_stock_pct: string | null
  max_per_sector_pct: string | null
  max_small_cap_pct: string | null
  min_holdings: string | null
  max_positions: string | null
  cash_floor_pct: string | null
}

Holding input shape: {
  instrument_id: string
  weight_pct: number        // display number (whole-percent, e.g. 5.0 = 5%)
  sector: string
  is_small_cap: boolean
}
```

All comparisons are strict `>` and `<`. A value exactly at a limit is NOT a breach (matches Python).

### `null target_weight_pct` handling (C5)

`target_weight_pct: null` → render "—" in Target column, omit Gap column for that row. Gap shown only when target is non-null.

### Weights sum (C7)

`investedPct = sum(instruments.map(i => i.weight_pct))`, `cashPct = 100 - investedPct`. Both shown in the footer.

### Expected Runtime

- Query: <10ms (single-row + correlated lateral ~50 iterations)
- Component render: synchronous

### Edge Cases

- Empty instruments array → 0 holdings, no table rows, sum = 0%, cash 100%
- `target_weight_pct = null` for a holding → show "—" gap, omit from gap computation
- NULL sector in universe → default "Unknown" at DB level
- Holdings with `instrument_type != 'stock'` (ETF, fund) → `sector = 'ETF'` / `'Fund'`, `is_small_cap = false`
- Policy `null` fields → skip that rule (treat limit as unlimited/unchecked)
