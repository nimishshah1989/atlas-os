# Sprint 2: Stocks + ETF Page Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Stocks and ETF screener pages with 10 new columns each, intelligence panels (commentary + distribution bars + top picks), expandable state-history rows, column show/hide controls, and a new ETF commentary engine — matching the Atlas design system throughout.

**Architecture:** New aggregate queries (`stocks-aggregates.ts`, `etfs-aggregates.ts`) run server-side in RSC page components and feed Intelligence Panels. A `/api/states-compact` route serves the expandable row state mini-chart via client fetch with AbortController + 300ms debounce. `ColumnSettings` persists to localStorage. `DistributionBars` is a shared UI primitive used by both intelligence panels.

**Tech Stack:** Next.js 14 App Router (RSC + client components), TypeScript strict, postgres.js `sql` template tag, Vitest + @testing-library/react, Alembic migrations, Radix UI Popover, Recharts horizontal bar, Tailwind with Atlas design tokens (`#F8F4EC` paper, `#1D9E75` teal, `CHART_COLORS` from `lib/chart-colors.ts`).

---

## File Map

**New files:**
- `migrations/versions/028_add_etf_state_since_date.py`
- `frontend/src/lib/queries/stocks-aggregates.ts`
- `frontend/src/lib/queries/etfs-aggregates.ts`
- `frontend/src/lib/commentary/etfs.ts`
- `frontend/src/app/api/states-compact/route.ts`
- `frontend/src/components/ui/ColumnSettings.tsx`
- `frontend/src/components/ui/MetricTileRow.tsx`
- `frontend/src/components/ui/DistributionBars.tsx`
- `frontend/src/components/stocks/StocksIntelligencePanel.tsx`
- `frontend/src/components/stocks/ExpandableStateRow.tsx`
- `frontend/src/components/etfs/ETFIntelligencePanel.tsx`

**Modified files:**
- `frontend/src/lib/queries/stocks.ts` — add 10 columns to `getAllStocks()` + extend `StockRowWithSector`
- `frontend/src/lib/queries/etfs.ts` — add 4 columns to `getAllETFs()` + extend `ETFRow`
- `frontend/src/components/stocks/StockScreener.tsx` — new cols + ColumnSettings + sector filter + expandable rows
- `frontend/src/components/etfs/ETFScreener.tsx` — new cols + ColumnSettings + 6-gate badge
- `frontend/src/app/stocks/page.tsx` — wire aggregates + StocksIntelligencePanel, remove StockTopPicks
- `frontend/src/app/etfs/page.tsx` — wire aggregates + ETFIntelligencePanel

**Test files:**
- `frontend/src/lib/queries/__tests__/stocks-aggregates.test.ts`
- `frontend/src/lib/queries/__tests__/etfs-aggregates.test.ts`
- `frontend/src/lib/commentary/__tests__/etfs.test.ts`
- `frontend/src/app/api/states-compact/__tests__/route.test.ts`
- `frontend/src/components/ui/__tests__/ColumnSettings.test.tsx`

---

### Task 1: Migration 028 — ETF state_since_date

**Files:**
- Create: `migrations/versions/028_add_etf_state_since_date.py`

Context: Migration 026 added `state_since_date` to `atlas_stock_states_daily`. Migration 027 added sector indexes. This migration adds the same column to `atlas_etf_states_daily` using `ticker` as the partition key (not `instrument_id`). The existing ETF states PK is `(ticker, date)` — no extra index needed for the states-compact query.

- [ ] **Step 1: Write the migration**

```python
"""add state_since_date to atlas_etf_states_daily

Revision ID: 028
Revises: 027
Create Date: 2026-05-10

Mirrors migration 026 for stocks. Enables days_in_state in getAllETFs().
NULL means pre-backfill; frontend displays as '—'.
"""
from alembic import op

revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.atlas_etf_states_daily
        ADD COLUMN IF NOT EXISTS state_since_date DATE;
    """)

    op.execute("""
        WITH ranked AS (
            SELECT
                ticker,
                date,
                rs_state,
                LAG(rs_state) OVER (
                    PARTITION BY ticker ORDER BY date
                ) AS prev_rs_state
            FROM atlas.atlas_etf_states_daily
        ),
        state_starts AS (
            SELECT ticker, date AS start_date, rs_state
            FROM ranked
            WHERE prev_rs_state IS DISTINCT FROM rs_state
        ),
        latest_start AS (
            SELECT DISTINCT ON (s.ticker)
                s.ticker,
                ss.start_date
            FROM atlas.atlas_etf_states_daily s
            JOIN state_starts ss
                ON ss.ticker = s.ticker
                AND ss.rs_state = s.rs_state
                AND ss.start_date <= s.date
            ORDER BY s.ticker, ss.start_date DESC
        )
        UPDATE atlas.atlas_etf_states_daily dst
        SET state_since_date = ls.start_date
        FROM latest_start ls
        WHERE dst.ticker = ls.ticker
          AND dst.state_since_date IS NULL;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_etf_states_since_date
        ON atlas.atlas_etf_states_daily (ticker, state_since_date);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS atlas.idx_etf_states_since_date;")
    op.execute("""
        ALTER TABLE atlas.atlas_etf_states_daily
        DROP COLUMN IF EXISTS state_since_date;
    """)
```

- [ ] **Step 2: Run the migration**

```bash
alembic upgrade head
```

Expected output: `Running upgrade 027 -> 028, add state_since_date to atlas_etf_states_daily`

- [ ] **Step 3: Verify**

```bash
alembic current
```

Expected: `028 (head)`

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/028_add_etf_state_since_date.py
git commit -m "feat(migration): add state_since_date to atlas_etf_states_daily (028)"
```

---

### Task 2: Update getAllStocks() — 10 new columns

**Files:**
- Modify: `frontend/src/lib/queries/stocks.ts`

All 10 columns already exist in DB (migrations 004–006 + 026):
- `ret_1w`, `extension_pct`, `realized_vol_63`, `drawdown_ratio_252` → `atlas_stock_metrics_daily`
- `state_since_date` → `atlas_stock_states_daily` (migration 026)
- `history_gate_pass`, `liquidity_gate_pass`, `stage1_base_qualifies` → `atlas_stock_states_daily`
- `strength_gate`, `direction_gate` → `atlas_stock_decisions_daily`

- [ ] **Step 1: Extend `StockRowWithSector` type**

In `frontend/src/lib/queries/stocks.ts`, replace the existing `StockRowWithSector` type:

```typescript
export type StockRowWithSector = StockRow & {
  sector: string
  above_30w_ma: boolean | null
  ret_1w: string | null
  extension_pct: string | null
  vol_63: string | null
  drawdown: string | null
  days_in_state: number | null
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  stage1_base_qualifies: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
}
```

- [ ] **Step 2: Add 10 new columns to the SELECT in `getAllStocks()`**

After `m.above_30w_ma,` add:

```sql
      m.ret_1w::text                       AS ret_1w,
      m.extension_pct::text                AS extension_pct,
      m.realized_vol_63::text              AS vol_63,
      m.drawdown_ratio_252::text           AS drawdown,
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      s.stage1_base_qualifies,
      d.strength_gate,
      d.direction_gate
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queries/stocks.ts
git commit -m "feat(stocks): add 10 new columns to getAllStocks() and StockRowWithSector"
```

---

### Task 3: getAllStocksAggregates() + tests

**Files:**
- Create: `frontend/src/lib/queries/stocks-aggregates.ts`
- Create: `frontend/src/lib/queries/__tests__/stocks-aggregates.test.ts`

`StocksAggregates` is a structural superset of `StocksPageAggregates` (from `lib/commentary/stocks.ts`). TypeScript structural typing allows passing `StocksAggregates` directly to `buildStocksCommentary()` without casting. `pct_leader_strong` and `median_rs_pctile` are **fraction 0–1** to match the existing commentary tests.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/queries/__tests__/stocks-aggregates.test.ts
import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import type { StocksAggregates } from '@/lib/queries/stocks-aggregates'

describe('StocksAggregates type shape', () => {
  it('has all required fields', () => {
    const agg: StocksAggregates = {
      total: 500,
      investable_count: 40,
      leader_count: 30,
      strong_count: 60,
      pct_leader_strong: 0.18,
      median_rs_pctile: 0.55,
      accel_count: 20,
      regime_state: 'Constructive',
      deployment_multiplier: 0.7,
      rs_distribution: { Leader: 30, Strong: 60, Average: 200 },
      momentum_distribution: { Accelerating: 20, Improving: 80 },
      top_picks: [],
    }
    expect(agg.total).toBe(500)
    expect(agg.rs_distribution['Leader']).toBe(30)
    expect(Array.isArray(agg.top_picks)).toBe(true)
  })

  it('top_picks shape is valid', () => {
    const pick = {
      instrument_id: 'abc-123',
      symbol: 'RELIANCE',
      company_name: 'Reliance Industries',
      sector: 'Energy',
      rs_pctile_3m: '0.87',
      rs_state: 'Leader',
      position_size_pct: '0.05',
    }
    const agg: StocksAggregates = {
      total: 1, investable_count: 1, leader_count: 1, strong_count: 0,
      pct_leader_strong: 1, median_rs_pctile: 0.87, accel_count: 0,
      regime_state: 'Constructive', deployment_multiplier: 0.7,
      rs_distribution: {}, momentum_distribution: {}, top_picks: [pick],
    }
    expect(agg.top_picks[0].symbol).toBe('RELIANCE')
  })
})
```

- [ ] **Step 2: Run test — confirm FAIL**

```bash
cd frontend && bun run test src/lib/queries/__tests__/stocks-aggregates.test.ts
```

Expected: FAIL — `Cannot find module '@/lib/queries/stocks-aggregates'`

- [ ] **Step 3: Create `stocks-aggregates.ts`**

```typescript
// frontend/src/lib/queries/stocks-aggregates.ts
import 'server-only'
import sql from '@/lib/db'

export type TopPickRow = {
  instrument_id: string
  symbol: string
  company_name: string
  sector: string
  rs_pctile_3m: string | null
  rs_state: string | null
  position_size_pct: string | null
}

// Structural superset of StocksPageAggregates — passes directly to buildStocksCommentary().
// pct_leader_strong and median_rs_pctile are fraction 0-1 (matches commentary tests).
export type StocksAggregates = {
  total: number
  investable_count: number
  leader_count: number
  strong_count: number
  pct_leader_strong: number
  median_rs_pctile: number
  accel_count: number
  regime_state: string
  deployment_multiplier: number
  rs_distribution: Record<string, number>
  momentum_distribution: Record<string, number>
  top_picks: TopPickRow[]
}

type AggRow = {
  total: number
  investable_count: number
  leader_count: number
  strong_count: number
  accel_count: number
  median_rs_pctile: number | null
  regime_state: string
  deployment_multiplier: string
  rs_distribution: Record<string, number> | null
  momentum_distribution: Record<string, number> | null
  top_picks: TopPickRow[] | null
}

export async function getAllStocksAggregates(): Promise<StocksAggregates> {
  const rows = await sql<AggRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    regime AS (
      SELECT regime_state, deployment_multiplier
      FROM atlas.atlas_market_regime_daily
      ORDER BY date DESC LIMIT 1
    ),
    base AS (
      SELECT s.rs_state, s.momentum_state, m.rs_pctile_3m, d.is_investable
      FROM atlas.atlas_universe_stocks u
      JOIN latest l ON TRUE
      LEFT JOIN atlas.atlas_stock_metrics_daily m
        ON m.instrument_id = u.instrument_id AND m.date = l.d
      LEFT JOIN atlas.atlas_stock_states_daily s
        ON s.instrument_id = u.instrument_id AND s.date = l.d
      LEFT JOIN atlas.atlas_stock_decisions_daily d
        ON d.instrument_id = u.instrument_id AND d.date = l.d
      WHERE u.effective_to IS NULL
    ),
    rs_dist AS (
      SELECT jsonb_object_agg(rs_state, cnt) AS dist
      FROM (SELECT rs_state, COUNT(*)::int AS cnt FROM base
            WHERE rs_state IS NOT NULL GROUP BY rs_state) x
    ),
    mom_dist AS (
      SELECT jsonb_object_agg(momentum_state, cnt) AS dist
      FROM (SELECT momentum_state, COUNT(*)::int AS cnt FROM base
            WHERE momentum_state IS NOT NULL GROUP BY momentum_state) x
    ),
    picks AS (
      SELECT jsonb_agg(row_to_json(t)) AS picks
      FROM (
        SELECT u.instrument_id::text, u.symbol, u.company_name, u.sector,
               m.rs_pctile_3m::text, s.rs_state, d.position_size_pct::text
        FROM atlas.atlas_universe_stocks u
        JOIN latest l ON TRUE
        LEFT JOIN atlas.atlas_stock_metrics_daily m
          ON m.instrument_id = u.instrument_id AND m.date = l.d
        LEFT JOIN atlas.atlas_stock_states_daily s
          ON s.instrument_id = u.instrument_id AND s.date = l.d
        JOIN atlas.atlas_stock_decisions_daily d
          ON d.instrument_id = u.instrument_id AND d.date = l.d
        WHERE u.effective_to IS NULL
          AND d.is_investable = true
          AND s.rs_state IN ('Leader', 'Strong')
        ORDER BY m.rs_pctile_3m DESC NULLS LAST
        LIMIT 3
      ) t
    )
    SELECT
      (SELECT COUNT(*)::int FROM base)                                            AS total,
      (SELECT COUNT(*)::int FROM base WHERE is_investable)                        AS investable_count,
      (SELECT COUNT(*)::int FROM base WHERE rs_state = 'Leader')                 AS leader_count,
      (SELECT COUNT(*)::int FROM base WHERE rs_state = 'Strong')                 AS strong_count,
      (SELECT COUNT(*)::int FROM base
       WHERE momentum_state IN ('Accelerating', 'Improving'))                     AS accel_count,
      (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY rs_pctile_3m)::float8
       FROM base WHERE rs_pctile_3m IS NOT NULL)                                 AS median_rs_pctile,
      r.regime_state,
      r.deployment_multiplier,
      rd.dist AS rs_distribution,
      md.dist AS momentum_distribution,
      p.picks AS top_picks
    FROM regime r
    CROSS JOIN rs_dist rd
    CROSS JOIN mom_dist md
    CROSS JOIN picks p
  `

  const row = rows[0]
  const total = row.total ?? 0
  const leader = row.leader_count ?? 0
  const strong = row.strong_count ?? 0

  return {
    total,
    investable_count: row.investable_count ?? 0,
    leader_count: leader,
    strong_count: strong,
    pct_leader_strong: total > 0 ? (leader + strong) / total : 0,
    median_rs_pctile: row.median_rs_pctile ?? 0,
    accel_count: row.accel_count ?? 0,
    regime_state: row.regime_state ?? 'Unknown',
    deployment_multiplier: parseFloat(row.deployment_multiplier ?? '0'),
    rs_distribution: row.rs_distribution ?? {},
    momentum_distribution: row.momentum_distribution ?? {},
    top_picks: row.top_picks ?? [],
  }
}
```

- [ ] **Step 4: Run tests — confirm PASS**

```bash
cd frontend && bun run test src/lib/queries/__tests__/stocks-aggregates.test.ts
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/queries/stocks-aggregates.ts \
        frontend/src/lib/queries/__tests__/stocks-aggregates.test.ts
git commit -m "feat(stocks): add getAllStocksAggregates() with RS/momentum distribution and top picks"
```

---

### Task 4: Update getAllETFs() — 4 new columns

**Files:**
- Modify: `frontend/src/lib/queries/etfs.ts`

`extension_pct` already exists in `ETFRow`. Adding: `ret_1w`, `vol_63` (realized_vol_63), `drawdown` (drawdown_ratio_252) from `atlas_etf_metrics_daily` (migration 004). `days_in_state` requires `state_since_date` added in Task 1 (migration 028).

- [ ] **Step 1: Add 4 new fields to `ETFRow` type** — after `extension_pct`:

```typescript
  ret_1w: string | null
  vol_63: string | null
  drawdown: string | null
  days_in_state: number | null
```

- [ ] **Step 2: Add 4 columns to `getAllETFs()` SELECT** — after `m.extension_pct::text AS extension_pct,`:

```sql
      m.ret_1w::text              AS ret_1w,
      m.realized_vol_63::text     AS vol_63,
      m.drawdown_ratio_252::text  AS drawdown,
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queries/etfs.ts
git commit -m "feat(etfs): add ret_1w, vol_63, drawdown, days_in_state to getAllETFs()"
```

---

### Task 5: getAllETFsAggregates() + tests

**Files:**
- Create: `frontend/src/lib/queries/etfs-aggregates.ts`
- Create: `frontend/src/lib/queries/__tests__/etfs-aggregates.test.ts`

Note: `pct_leader_strong` and `median_rs_pctile` are **0–100 scale** for ETFs (not fraction) so commentary conditions read naturally: `a.pct_leader_strong > 40`. The SQL multiplies `rs_pctile_3m * 100` for `median_rs_pctile`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/queries/__tests__/etfs-aggregates.test.ts
import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import type { ETFsAggregates } from '@/lib/queries/etfs-aggregates'

describe('ETFsAggregates type shape', () => {
  it('has required fields with correct scale', () => {
    const agg: ETFsAggregates = {
      total: 80,
      investable_count: 12,
      broad_investable: 3,
      leader_count: 15,
      strong_count: 20,
      pct_leader_strong: 43.75,   // 0-100
      median_rs_pctile: 58,       // 0-100
      accel_count: 8,
      regime_state: 'Constructive',
      deployment_multiplier: 0.7,
      rs_distribution: { Leader: 15, Strong: 20 },
      momentum_distribution: { Accelerating: 8, Improving: 22 },
      top_picks: [],
    }
    expect(agg.broad_investable).toBe(3)
    expect(agg.pct_leader_strong).toBeCloseTo(43.75)
    expect(agg.median_rs_pctile).toBe(58)
  })

  it('top_picks shape is valid', () => {
    const pick = {
      ticker: 'NIFTYBEES',
      etf_name: 'Nippon India ETF Nifty BeES',
      theme: 'Broad',
      rs_pctile_3m: '0.80',
      rs_state: 'Leader',
      position_size_pct: '0.04',
    }
    const agg: ETFsAggregates = {
      total: 1, investable_count: 1, broad_investable: 1,
      leader_count: 1, strong_count: 0, pct_leader_strong: 100,
      median_rs_pctile: 80, accel_count: 0,
      regime_state: 'Constructive', deployment_multiplier: 0.7,
      rs_distribution: {}, momentum_distribution: {}, top_picks: [pick],
    }
    expect(agg.top_picks[0].ticker).toBe('NIFTYBEES')
  })
})
```

- [ ] **Step 2: Run test — confirm FAIL**

```bash
cd frontend && bun run test src/lib/queries/__tests__/etfs-aggregates.test.ts
```

Expected: FAIL — `Cannot find module '@/lib/queries/etfs-aggregates'`

- [ ] **Step 3: Create `etfs-aggregates.ts`**

```typescript
// frontend/src/lib/queries/etfs-aggregates.ts
import 'server-only'
import sql from '@/lib/db'

export type ETFTopPickRow = {
  ticker: string
  etf_name: string | null
  theme: string
  rs_pctile_3m: string | null
  rs_state: string | null
  position_size_pct: string | null
}

// pct_leader_strong and median_rs_pctile are 0-100 scale (not fraction).
// ETF commentary conditions use these directly: `a.pct_leader_strong > 40`.
export type ETFsAggregates = {
  total: number
  investable_count: number
  broad_investable: number
  leader_count: number
  strong_count: number
  pct_leader_strong: number
  median_rs_pctile: number
  accel_count: number
  regime_state: string
  deployment_multiplier: number
  rs_distribution: Record<string, number>
  momentum_distribution: Record<string, number>
  top_picks: ETFTopPickRow[]
}

type AggRow = {
  total: number
  investable_count: number
  broad_investable: number
  leader_count: number
  strong_count: number
  accel_count: number
  median_rs_pctile: number | null
  regime_state: string
  deployment_multiplier: string
  rs_distribution: Record<string, number> | null
  momentum_distribution: Record<string, number> | null
  top_picks: ETFTopPickRow[] | null
}

export async function getAllETFsAggregates(): Promise<ETFsAggregates> {
  const rows = await sql<AggRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
    ),
    regime AS (
      SELECT regime_state, deployment_multiplier
      FROM atlas.atlas_market_regime_daily
      ORDER BY date DESC LIMIT 1
    ),
    base AS (
      SELECT u.theme, s.rs_state, s.momentum_state, m.rs_pctile_3m, d.is_investable
      FROM atlas.atlas_universe_etfs u
      JOIN latest l ON TRUE
      LEFT JOIN atlas.atlas_etf_metrics_daily m
        ON m.ticker = u.ticker AND m.date = l.d
      LEFT JOIN atlas.atlas_etf_states_daily s
        ON s.ticker = u.ticker AND s.date = l.d
      LEFT JOIN atlas.atlas_etf_decisions_daily d
        ON d.ticker = u.ticker AND d.date = l.d
      WHERE u.effective_to IS NULL
    ),
    rs_dist AS (
      SELECT jsonb_object_agg(rs_state, cnt) AS dist
      FROM (SELECT rs_state, COUNT(*)::int AS cnt FROM base
            WHERE rs_state IS NOT NULL GROUP BY rs_state) x
    ),
    mom_dist AS (
      SELECT jsonb_object_agg(momentum_state, cnt) AS dist
      FROM (SELECT momentum_state, COUNT(*)::int AS cnt FROM base
            WHERE momentum_state IS NOT NULL GROUP BY momentum_state) x
    ),
    picks AS (
      SELECT jsonb_agg(row_to_json(t)) AS picks
      FROM (
        SELECT u.ticker, u.etf_name, u.theme,
               m.rs_pctile_3m::text, s.rs_state, d.position_size_pct::text
        FROM atlas.atlas_universe_etfs u
        JOIN latest l ON TRUE
        LEFT JOIN atlas.atlas_etf_metrics_daily m
          ON m.ticker = u.ticker AND m.date = l.d
        LEFT JOIN atlas.atlas_etf_states_daily s
          ON s.ticker = u.ticker AND s.date = l.d
        JOIN atlas.atlas_etf_decisions_daily d
          ON d.ticker = u.ticker AND d.date = l.d
        WHERE u.effective_to IS NULL
          AND d.is_investable = true
          AND s.rs_state IN ('Leader', 'Strong')
        ORDER BY m.rs_pctile_3m DESC NULLS LAST
        LIMIT 3
      ) t
    )
    SELECT
      (SELECT COUNT(*)::int FROM base)                                             AS total,
      (SELECT COUNT(*)::int FROM base WHERE is_investable)                         AS investable_count,
      (SELECT COUNT(*)::int FROM base WHERE theme = 'Broad' AND is_investable)    AS broad_investable,
      (SELECT COUNT(*)::int FROM base WHERE rs_state = 'Leader')                  AS leader_count,
      (SELECT COUNT(*)::int FROM base WHERE rs_state = 'Strong')                  AS strong_count,
      (SELECT COUNT(*)::int FROM base
       WHERE momentum_state IN ('Accelerating', 'Improving'))                      AS accel_count,
      (SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY rs_pctile_3m) * 100)::float8
       FROM base WHERE rs_pctile_3m IS NOT NULL)                                  AS median_rs_pctile,
      r.regime_state,
      r.deployment_multiplier,
      rd.dist AS rs_distribution,
      md.dist AS momentum_distribution,
      p.picks AS top_picks
    FROM regime r
    CROSS JOIN rs_dist rd
    CROSS JOIN mom_dist md
    CROSS JOIN picks p
  `

  const row = rows[0]
  const total = row.total ?? 0
  const leader = row.leader_count ?? 0
  const strong = row.strong_count ?? 0

  return {
    total,
    investable_count: row.investable_count ?? 0,
    broad_investable: row.broad_investable ?? 0,
    leader_count: leader,
    strong_count: strong,
    pct_leader_strong: total > 0 ? ((leader + strong) / total) * 100 : 0,
    median_rs_pctile: row.median_rs_pctile ?? 0,
    accel_count: row.accel_count ?? 0,
    regime_state: row.regime_state ?? 'Unknown',
    deployment_multiplier: parseFloat(row.deployment_multiplier ?? '0'),
    rs_distribution: row.rs_distribution ?? {},
    momentum_distribution: row.momentum_distribution ?? {},
    top_picks: row.top_picks ?? [],
  }
}
```

- [ ] **Step 4: Run tests — confirm PASS**

```bash
cd frontend && bun run test src/lib/queries/__tests__/etfs-aggregates.test.ts
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/queries/etfs-aggregates.ts \
        frontend/src/lib/queries/__tests__/etfs-aggregates.test.ts
git commit -m "feat(etfs): add getAllETFsAggregates() with RS/momentum distribution and top picks"
```

---

### Task 6: buildETFCommentary + tests

**Files:**
- Create: `frontend/src/lib/commentary/etfs.ts`
- Create: `frontend/src/lib/commentary/__tests__/etfs.test.ts`

Mirrors the CONDITIONS array pattern from `lib/commentary/stocks.ts`. Imports `CommentaryResult` from stocks (same shape). `pct_leader_strong` and `median_rs_pctile` are 0–100 scale here.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/commentary/__tests__/etfs.test.ts
import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))

import { buildETFCommentary, type ETFsPageAggregates } from '@/lib/commentary/etfs'

const base: ETFsPageAggregates = {
  total_count: 80,
  investable_count: 12,
  broad_investable: 3,
  leader_count: 15,
  strong_count: 20,
  pct_leader_strong: 43.75,
  median_rs_pctile: 58,
  regime_state: 'Constructive',
  deployment_multiplier: 0.7,
}

describe('buildETFCommentary', () => {
  it('returns a narrative string', () => {
    const result = buildETFCommentary(base)
    expect(typeof result.narrative).toBe('string')
    expect(result.narrative.length).toBeGreaterThan(30)
  })

  it('returns non-empty context cards', () => {
    const result = buildETFCommentary(base)
    expect(result.contextCards.length).toBeGreaterThan(0)
  })

  it('fires strong breadth condition when pct_leader_strong > 40', () => {
    const result = buildETFCommentary({ ...base, pct_leader_strong: 45 })
    expect(result.narrative.toLowerCase()).toMatch(/strong|leader|broad/)
  })

  it('fires narrow broad condition when broad_investable < 2', () => {
    const result = buildETFCommentary({ ...base, pct_leader_strong: 20, broad_investable: 1 })
    expect(result.narrative.toLowerCase()).toMatch(/broad|concentrat/)
  })

  it('fires high median RS condition when median_rs_pctile > 70', () => {
    const result = buildETFCommentary({ ...base, pct_leader_strong: 20, median_rs_pctile: 75 })
    expect(result.narrative.toLowerCase()).toMatch(/median|participat|broad/)
  })

  it('default condition fires for normal market', () => {
    const normal = { ...base, pct_leader_strong: 25, median_rs_pctile: 55, broad_investable: 4 }
    const result = buildETFCommentary(normal)
    expect(result.narrative).toContain('12')
  })

  it('context cards include investable_count', () => {
    const result = buildETFCommentary(base)
    const card = result.contextCards.find(c => c.label.toLowerCase().includes('investable'))
    expect(card?.value).toContain('12')
  })

  it('context cards include leader+strong count', () => {
    const result = buildETFCommentary(base)
    const card = result.contextCards.find(c => c.label.toLowerCase().includes('leader'))
    expect(card?.value).toContain('35')
  })
})
```

- [ ] **Step 2: Run test — confirm FAIL**

```bash
cd frontend && bun run test src/lib/commentary/__tests__/etfs.test.ts
```

Expected: FAIL — `Cannot find module '@/lib/commentary/etfs'`

- [ ] **Step 3: Create `etfs.ts` commentary**

```typescript
// frontend/src/lib/commentary/etfs.ts
import type { CommentaryResult } from '@/lib/commentary/stocks'

export type ETFsPageAggregates = {
  total_count: number
  investable_count: number
  broad_investable: number
  leader_count: number
  strong_count: number
  pct_leader_strong: number     // 0-100 scale
  median_rs_pctile: number      // 0-100 scale
  regime_state: string
  deployment_multiplier: number // fraction 0-1
}

type ETFCondition = {
  test: (a: ETFsPageAggregates) => boolean
  generate: (a: ETFsPageAggregates) => string
}

const CONDITIONS: ETFCondition[] = [
  {
    test: a => a.pct_leader_strong > 40,
    generate: a =>
      `ETF breadth is strong: ${a.pct_leader_strong.toFixed(0)}% of universe in Leader/Strong (${a.leader_count + a.strong_count} of ${a.total_count}). ${a.investable_count} ETFs meet all entry criteria under ${a.regime_state}.`,
  },
  {
    test: a => a.broad_investable < 2,
    generate: a =>
      `Only ${a.broad_investable} broad-market ETF${a.broad_investable === 1 ? ' is' : 's are'} investable — equity risk is concentrated in sectoral/thematic names. ${a.investable_count} total investable at ${a.median_rs_pctile.toFixed(0)}th median RS percentile.`,
  },
  {
    test: a => a.median_rs_pctile > 70,
    generate: a =>
      `Median RS percentile at ${a.median_rs_pctile.toFixed(0)} signals broad participation — most ETFs are outperforming. ${a.investable_count} investable under ${a.regime_state} (${Math.round(a.deployment_multiplier * 100)}% deployment).`,
  },
  {
    test: () => true,
    generate: a =>
      `${a.investable_count} of ${a.total_count} ETFs are investable at ${a.median_rs_pctile.toFixed(0)}th median RS percentile. ${a.leader_count + a.strong_count} are Leader/Strong (${a.pct_leader_strong.toFixed(0)}%) under ${a.regime_state} at ${Math.round(a.deployment_multiplier * 100)}% deployment.`,
  },
]

export function buildETFCommentary(aggregates: ETFsPageAggregates): CommentaryResult {
  const condition = CONDITIONS.find(c => c.test(aggregates))!
  const narrative = condition.generate(aggregates)

  const contextCards = [
    { label: 'Investable', value: `${aggregates.investable_count} ETFs` },
    { label: 'Leader/Strong', value: `${aggregates.leader_count + aggregates.strong_count}` },
    {
      label: 'Broad Investable',
      value: `${aggregates.broad_investable}`,
      deltaPositive: aggregates.broad_investable >= 2,
    },
    {
      label: 'Deployment',
      value: `${Math.round(aggregates.deployment_multiplier * 100)}%`,
      deltaPositive: aggregates.deployment_multiplier >= 0.7,
    },
  ]

  return { narrative, contextCards }
}
```

- [ ] **Step 4: Run tests — confirm PASS**

```bash
cd frontend && bun run test src/lib/commentary/__tests__/etfs.test.ts
```

Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/commentary/etfs.ts \
        frontend/src/lib/commentary/__tests__/etfs.test.ts
git commit -m "feat(etfs): add buildETFCommentary with CONDITIONS array pattern"
```

---

### Task 7: /api/states-compact route + tests

**Files:**
- Create: `frontend/src/app/api/states-compact/route.ts`
- Create: `frontend/src/app/api/states-compact/__tests__/route.test.ts`

Validation rules: exactly one of `instrument_id` or `ticker` required; `days` must be integer 1–365; defaults to 90. Routes to `getStockStateHistory` or `getETFStateHistory` accordingly.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/app/api/states-compact/__tests__/route.test.ts
import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/queries/stocks', () => ({
  getStockStateHistory: vi.fn().mockResolvedValue([
    { date: new Date('2026-04-01'), rs_state: 'Leader', momentum_state: 'Accelerating',
      risk_state: 'Low', volume_state: 'Accumulation' },
  ]),
}))
vi.mock('@/lib/queries/etfs', () => ({
  getETFStateHistory: vi.fn().mockResolvedValue([
    { date: new Date('2026-04-01'), rs_state: 'Strong', momentum_state: 'Improving',
      risk_state: 'Normal' },
  ]),
}))

import { GET } from '@/app/api/states-compact/route'

function makeRequest(params: Record<string, string>) {
  const url = new URL('http://localhost/api/states-compact')
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  return new Request(url.toString())
}

describe('GET /api/states-compact', () => {
  it('returns 400 when no param provided', async () => {
    const res = await GET(makeRequest({}))
    expect(res.status).toBe(400)
    expect((await res.json()).error).toBeTruthy()
  })

  it('returns 400 when both params provided', async () => {
    const res = await GET(makeRequest({ instrument_id: 'abc', ticker: 'XYZ' }))
    expect(res.status).toBe(400)
  })

  it('returns 400 for days > 365', async () => {
    const res = await GET(makeRequest({ instrument_id: 'abc-123', days: '400' }))
    expect(res.status).toBe(400)
  })

  it('returns 400 for days = 0', async () => {
    const res = await GET(makeRequest({ instrument_id: 'abc-123', days: '0' }))
    expect(res.status).toBe(400)
  })

  it('returns 200 with stock state history', async () => {
    const res = await GET(makeRequest({ instrument_id: 'abc-123' }))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body)).toBe(true)
    expect(body[0].rs_state).toBe('Leader')
  })

  it('returns 200 with ETF state history', async () => {
    const res = await GET(makeRequest({ ticker: 'NIFTYBEES' }))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body[0].rs_state).toBe('Strong')
  })

  it('defaults days to 90', async () => {
    const { getStockStateHistory } = await import('@/lib/queries/stocks')
    await GET(makeRequest({ instrument_id: 'abc-123' }))
    expect(getStockStateHistory).toHaveBeenCalledWith('abc-123', 90)
  })
})
```

- [ ] **Step 2: Run test — confirm FAIL**

```bash
cd frontend && bun run test src/app/api/states-compact/__tests__/route.test.ts
```

Expected: FAIL — `Cannot find module '@/app/api/states-compact/route'`

- [ ] **Step 3: Create the route**

```typescript
// frontend/src/app/api/states-compact/route.ts
import { NextResponse } from 'next/server'
import { getStockStateHistory } from '@/lib/queries/stocks'
import { getETFStateHistory } from '@/lib/queries/etfs'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const instrument_id = searchParams.get('instrument_id')
  const ticker = searchParams.get('ticker')

  if (!instrument_id && !ticker) {
    return NextResponse.json({ error: 'Provide instrument_id or ticker' }, { status: 400 })
  }
  if (instrument_id && ticker) {
    return NextResponse.json({ error: 'Provide one param, not both' }, { status: 400 })
  }

  const daysRaw = searchParams.get('days') ?? '90'
  const days = parseInt(daysRaw, 10)
  if (!Number.isInteger(days) || days < 1 || days > 365) {
    return NextResponse.json(
      { error: 'days must be an integer between 1 and 365' },
      { status: 400 },
    )
  }

  if (instrument_id) {
    const rows = await getStockStateHistory(instrument_id, days)
    return NextResponse.json(rows)
  }

  const rows = await getETFStateHistory(ticker!, days)
  return NextResponse.json(rows)
}
```

- [ ] **Step 4: Run tests — confirm PASS**

```bash
cd frontend && bun run test src/app/api/states-compact/__tests__/route.test.ts
```

Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/states-compact/route.ts \
        frontend/src/app/api/states-compact/__tests__/route.test.ts
git commit -m "feat(api): add /api/states-compact with instrument_id/ticker validation"
```

---

### Task 8: ColumnSettings.tsx + tests

**Files:**
- Create: `frontend/src/components/ui/ColumnSettings.tsx`
- Create: `frontend/src/components/ui/__tests__/ColumnSettings.test.tsx`

Radix UI Popover trigger opens a checklist of optional columns. State saved to `localStorage` under `storageKey`. On mount, reads localStorage; if missing, defaults to `defaultVisible: true` columns. `QuotaExceededError` on write is silently ignored (in-memory change persists for session).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/ui/__tests__/ColumnSettings.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('server-only', () => ({}))

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { store = {} },
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

import { ColumnSettings, type ColumnDef } from '@/components/ui/ColumnSettings'

const columns: ColumnDef[] = [
  { key: 'ret_1m',   label: '1M Ret',   defaultVisible: true },
  { key: 'vol_63',   label: 'Vol 63D',  defaultVisible: false },
  { key: 'drawdown', label: 'Drawdown', defaultVisible: false },
]

describe('ColumnSettings', () => {
  beforeEach(() => localStorageMock.clear())

  it('renders trigger button with accessible label', () => {
    render(<ColumnSettings columns={columns} storageKey="test" onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /columns/i })).toBeInTheDocument()
  })

  it('calls onChange with default visible set on mount', () => {
    const onChange = vi.fn()
    render(<ColumnSettings columns={columns} storageKey="test" onChange={onChange} />)
    expect(onChange).toHaveBeenCalledOnce()
    const visible = onChange.mock.calls[0][0] as Set<string>
    expect(visible.has('ret_1m')).toBe(true)
    expect(visible.has('vol_63')).toBe(false)
  })

  it('restores visible set from localStorage', () => {
    localStorageMock.setItem('test', JSON.stringify(['vol_63', 'drawdown']))
    const onChange = vi.fn()
    render(<ColumnSettings columns={columns} storageKey="test" onChange={onChange} />)
    const visible = onChange.mock.calls[0][0] as Set<string>
    expect(visible.has('vol_63')).toBe(true)
    expect(visible.has('ret_1m')).toBe(false)
  })
})
```

- [ ] **Step 2: Run test — confirm FAIL**

```bash
cd frontend && bun run test src/components/ui/__tests__/ColumnSettings.test.tsx
```

Expected: FAIL — `Cannot find module '@/components/ui/ColumnSettings'`

- [ ] **Step 3: Create `ColumnSettings.tsx`**

```tsx
// frontend/src/components/ui/ColumnSettings.tsx
'use client'
import { useEffect, useState } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { SlidersHorizontal } from 'lucide-react'

export type ColumnDef = {
  key: string
  label: string
  defaultVisible: boolean
}

type Props = {
  columns: ColumnDef[]
  storageKey: string
  onChange: (visible: Set<string>) => void
}

function loadFromStorage(key: string, columns: ColumnDef[]): Set<string> {
  try {
    const stored = localStorage.getItem(key)
    if (stored) return new Set(JSON.parse(stored) as string[])
  } catch {
    // corrupted — fall through to defaults
  }
  return new Set(columns.filter(c => c.defaultVisible).map(c => c.key))
}

export function ColumnSettings({ columns, storageKey, onChange }: Props) {
  const [visible, setVisible] = useState<Set<string>>(
    () => new Set(columns.filter(c => c.defaultVisible).map(c => c.key)),
  )

  useEffect(() => {
    const initial = loadFromStorage(storageKey, columns)
    setVisible(initial)
    onChange(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function toggle(key: string) {
    const next = new Set(visible)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setVisible(next)
    onChange(next)
    try {
      localStorage.setItem(storageKey, JSON.stringify(Array.from(next)))
    } catch {
      // QuotaExceededError — change persists in-memory for this session
    }
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label="Columns"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-sm border border-paper-rule font-sans text-xs text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/20 transition-colors"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          Columns
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="z-50 w-48 bg-paper border border-paper-rule rounded-sm shadow-md p-2"
          sideOffset={4}
          align="end"
        >
          <p className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary px-2 py-1 mb-1">
            Show / hide columns
          </p>
          {columns.map(col => (
            <label
              key={col.key}
              className="flex items-center gap-2 px-2 py-1.5 rounded-sm hover:bg-paper-rule/20 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={visible.has(col.key)}
                onChange={() => toggle(col.key)}
                className="accent-teal w-3.5 h-3.5"
              />
              <span className="font-sans text-xs text-ink-primary">{col.label}</span>
            </label>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
```

- [ ] **Step 4: Run tests — confirm PASS**

```bash
cd frontend && bun run test src/components/ui/__tests__/ColumnSettings.test.tsx
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/ColumnSettings.tsx \
        frontend/src/components/ui/__tests__/ColumnSettings.test.tsx
git commit -m "feat(ui): add ColumnSettings with Radix Popover and localStorage persistence"
```

---

### Task 9: MetricTileRow.tsx

**Files:**
- Create: `frontend/src/components/ui/MetricTileRow.tsx`

Pure presentational — no logic, no tests needed.

- [ ] **Step 1: Create `MetricTileRow.tsx`**

```tsx
// frontend/src/components/ui/MetricTileRow.tsx
type Tile = {
  label: string
  value: string
  subValue?: string
  positive?: boolean   // true = teal, false = red, undefined = ink-primary
}

export function MetricTileRow({ tiles }: { tiles: Tile[] }) {
  return (
    <div className="flex flex-wrap gap-3">
      {tiles.map(tile => (
        <div
          key={tile.label}
          className="flex flex-col gap-0.5 px-3 py-2 bg-paper border border-paper-rule rounded-sm min-w-[90px]"
        >
          <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
            {tile.label}
          </span>
          <span
            className={`font-mono text-sm font-semibold tabular-nums ${
              tile.positive === true
                ? 'text-signal-pos'
                : tile.positive === false
                  ? 'text-signal-neg'
                  : 'text-ink-primary'
            }`}
          >
            {tile.value}
          </span>
          {tile.subValue && (
            <span className="font-sans text-[10px] text-ink-tertiary">{tile.subValue}</span>
          )}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/MetricTileRow.tsx
git commit -m "feat(ui): add MetricTileRow presentational component"
```

---

### Task 10: DistributionBars.tsx

**Files:**
- Create: `frontend/src/components/ui/DistributionBars.tsx`

Shared between `StocksIntelligencePanel` and `ETFIntelligencePanel`. Uses `CHART_COLORS` from `lib/chart-colors.ts`. Renders a horizontal Recharts bar for a `Record<string, number>` distribution. Sorted by `RS_ORDER` or `MOM_ORDER`.

- [ ] **Step 1: Create `DistributionBars.tsx`**

```tsx
// frontend/src/components/ui/DistributionBars.tsx
'use client'
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { CHART_COLORS } from '@/lib/chart-colors'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']

const RS_COLORS: Record<string, string> = {
  Leader:        CHART_COLORS.teal,
  Strong:        CHART_COLORS.posLight,
  Consolidating: CHART_COLORS.ochre,
  Emerging:      CHART_COLORS.ochreLight,
  Average:       CHART_COLORS.neutral,
  Weak:          CHART_COLORS.negLight,
  Laggard:       CHART_COLORS.neg,
}

const MOM_COLORS: Record<string, string> = {
  Accelerating:  CHART_COLORS.teal,
  Improving:     CHART_COLORS.posLight,
  Flat:          CHART_COLORS.neutral,
  Deteriorating: CHART_COLORS.negLight,
  Collapsing:    CHART_COLORS.neg,
}

type Props = {
  distribution: Record<string, number>
  type: 'rs' | 'momentum'
  label: string
}

export function DistributionBars({ distribution, type, label }: Props) {
  const order = type === 'rs' ? RS_ORDER : MOM_ORDER
  const colors = type === 'rs' ? RS_COLORS : MOM_COLORS
  const data = order
    .map(state => ({ state, count: distribution[state] ?? 0 }))
    .filter(d => d.count > 0)

  return (
    <div className="flex flex-col gap-1">
      <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
        {label}
      </span>
      {data.length === 0 ? (
        <div className="h-10 flex items-center">
          <span className="font-sans text-xs text-ink-tertiary">No data</span>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={40}>
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <XAxis type="number" hide />
            <Tooltip
              cursor={{ fill: 'transparent' }}
              content={({ payload }) => {
                if (!payload?.[0]) return null
                const d = payload[0].payload as { state: string; count: number }
                return (
                  <div className="bg-paper border border-paper-rule rounded-sm px-2 py-1">
                    <span className="font-sans text-xs text-ink-primary">{d.state}: {d.count}</span>
                  </div>
                )
              }}
            />
            <Bar dataKey="count" radius={[0, 2, 2, 0]}>
              {data.map(d => (
                <Cell key={d.state} fill={colors[d.state] ?? CHART_COLORS.neutral} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/DistributionBars.tsx
git commit -m "feat(ui): add shared DistributionBars component using CHART_COLORS"
```

---

### Task 11: StocksIntelligencePanel + ExpandableStateRow

**Files:**
- Create: `frontend/src/components/stocks/StocksIntelligencePanel.tsx`
- Create: `frontend/src/components/stocks/ExpandableStateRow.tsx`

`StocksIntelligencePanel` is a server component (no `'use client'` needed — it only renders RSC-safe primitives and passes data to `CommentaryBlock`). `ExpandableStateRow` is client-only (fetch + AbortController).

- [ ] **Step 1: Create `ExpandableStateRow.tsx`**

```tsx
// frontend/src/components/stocks/ExpandableStateRow.tsx
'use client'
import { useEffect, useState, useRef } from 'react'
import { RSStateChip, MomentumChip } from '@/lib/stock-formatters'

type StateRow = {
  date: string
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
}

type Props = {
  instrumentId: string
  colSpan: number
}

export function ExpandableStateRow({ instrumentId, colSpan }: Props) {
  const [rows, setRows] = useState<StateRow[] | null>(null)
  const [loading, setLoading] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      fetch(
        `/api/states-compact?instrument_id=${encodeURIComponent(instrumentId)}&days=90`,
        { signal: ctrl.signal },
      )
        .then(r => r.json())
        .then((data: StateRow[]) => { setRows(data); setLoading(false) })
        .catch(err => { if (err.name !== 'AbortError') setLoading(false) })
    }, 300)

    return () => { clearTimeout(timer); abortRef.current?.abort() }
  }, [instrumentId])

  if (loading) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-6 py-3 bg-paper-rule/10">
          <div className="h-4 w-48 bg-paper-rule/30 rounded animate-pulse" />
        </td>
      </tr>
    )
  }

  if (!rows || rows.length === 0) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-6 py-3 bg-paper-rule/10 border-b border-paper-rule">
          <span className="font-sans text-xs text-ink-tertiary">No state history available</span>
        </td>
      </tr>
    )
  }

  const weekly = rows.filter((_, i) => i % 5 === 0).slice(-13)

  return (
    <tr>
      <td colSpan={colSpan} className="px-6 py-3 bg-paper-rule/10 border-b border-paper-rule">
        <div className="flex flex-col gap-2">
          <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
            State history — last ~13 weeks (RS · Momentum)
          </span>
          <div className="flex flex-wrap gap-1">
            {weekly.map(row => (
              <div key={row.date} className="flex flex-col items-center gap-0.5">
                <RSStateChip value={row.rs_state} />
                <span className="font-mono text-[8px] text-ink-tertiary">
                  {new Date(row.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
                </span>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {weekly.map(row => (
              <MomentumChip key={`m-${row.date}`} value={row.momentum_state} />
            ))}
          </div>
        </div>
      </td>
    </tr>
  )
}
```

- [ ] **Step 2: Create `StocksIntelligencePanel.tsx`**

```tsx
// frontend/src/components/stocks/StocksIntelligencePanel.tsx
import type { StocksAggregates } from '@/lib/queries/stocks-aggregates'
import { buildStocksCommentary } from '@/lib/commentary/stocks'
import { CommentaryBlock } from '@/components/ui/CommentaryBlock'
import { MetricTileRow } from '@/components/ui/MetricTileRow'
import { DistributionBars } from '@/components/ui/DistributionBars'
import Link from 'next/link'

export function StocksIntelligencePanel({ aggregates: agg }: { aggregates: StocksAggregates }) {
  const commentary = buildStocksCommentary(agg)

  const tiles = [
    { label: 'Investable', value: String(agg.investable_count), subValue: `of ${agg.total}`, positive: agg.investable_count > 30 },
    { label: 'Leader/Strong', value: String(agg.leader_count + agg.strong_count), positive: agg.pct_leader_strong > 0.20 },
    { label: 'Breadth', value: `${(agg.pct_leader_strong * 100).toFixed(0)}%`, positive: agg.pct_leader_strong > 0.25 },
    { label: 'Median RS', value: `${(agg.median_rs_pctile * 100).toFixed(0)}th`, positive: agg.median_rs_pctile > 0.5 },
    { label: 'Accel/Impr', value: String(agg.accel_count) },
    { label: 'Deployment', value: `${Math.round(agg.deployment_multiplier * 100)}%`, positive: agg.deployment_multiplier >= 0.7 },
  ]

  return (
    <div className="flex flex-col gap-4 p-4 bg-paper border border-paper-rule rounded-sm">
      <MetricTileRow tiles={tiles} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <DistributionBars distribution={agg.rs_distribution} type="rs" label="RS State Distribution" />
        <DistributionBars distribution={agg.momentum_distribution} type="momentum" label="Momentum Distribution" />
      </div>
      {agg.top_picks.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
            Top Picks
          </span>
          <div className="flex flex-wrap gap-2">
            {agg.top_picks.map(pick => (
              <Link
                key={pick.instrument_id}
                href={`/stocks/${encodeURIComponent(pick.symbol)}`}
                className="flex flex-col gap-0.5 px-3 py-2 border border-paper-rule rounded-sm hover:bg-paper-rule/20 transition-colors min-w-[120px]"
              >
                <span className="font-sans text-xs font-semibold text-ink-primary">{pick.symbol}</span>
                <span className="font-sans text-[10px] text-ink-tertiary truncate max-w-[150px]" title={pick.company_name}>
                  {pick.company_name}
                </span>
                <span className="font-mono text-[10px] text-teal tabular-nums">
                  RS {pick.rs_pctile_3m ? (parseFloat(pick.rs_pctile_3m) * 100).toFixed(0) : '—'}th
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
      <CommentaryBlock commentary={commentary} />
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stocks/StocksIntelligencePanel.tsx \
        frontend/src/components/stocks/ExpandableStateRow.tsx
git commit -m "feat(stocks): add StocksIntelligencePanel and ExpandableStateRow"
```

---

### Task 12: ETFIntelligencePanel.tsx

**Files:**
- Create: `frontend/src/components/etfs/ETFIntelligencePanel.tsx`

- [ ] **Step 1: Create `ETFIntelligencePanel.tsx`**

```tsx
// frontend/src/components/etfs/ETFIntelligencePanel.tsx
import type { ETFsAggregates } from '@/lib/queries/etfs-aggregates'
import { buildETFCommentary } from '@/lib/commentary/etfs'
import { CommentaryBlock } from '@/components/ui/CommentaryBlock'
import { MetricTileRow } from '@/components/ui/MetricTileRow'
import { DistributionBars } from '@/components/ui/DistributionBars'
import Link from 'next/link'

export function ETFIntelligencePanel({ aggregates: agg }: { aggregates: ETFsAggregates }) {
  const commentary = buildETFCommentary({
    total_count: agg.total,
    investable_count: agg.investable_count,
    broad_investable: agg.broad_investable,
    leader_count: agg.leader_count,
    strong_count: agg.strong_count,
    pct_leader_strong: agg.pct_leader_strong,
    median_rs_pctile: agg.median_rs_pctile,
    regime_state: agg.regime_state,
    deployment_multiplier: agg.deployment_multiplier,
  })

  const tiles = [
    { label: 'Investable', value: String(agg.investable_count), subValue: `of ${agg.total}`, positive: agg.investable_count > 5 },
    { label: 'Broad Inv.', value: String(agg.broad_investable), positive: agg.broad_investable >= 2 },
    { label: 'Leader/Strong', value: String(agg.leader_count + agg.strong_count), positive: agg.pct_leader_strong > 25 },
    { label: 'Breadth', value: `${agg.pct_leader_strong.toFixed(0)}%`, positive: agg.pct_leader_strong > 30 },
    { label: 'Median RS', value: `${agg.median_rs_pctile.toFixed(0)}th`, positive: agg.median_rs_pctile > 50 },
    { label: 'Deployment', value: `${Math.round(agg.deployment_multiplier * 100)}%`, positive: agg.deployment_multiplier >= 0.7 },
  ]

  return (
    <div className="flex flex-col gap-4 p-4 bg-paper border border-paper-rule rounded-sm">
      <MetricTileRow tiles={tiles} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <DistributionBars distribution={agg.rs_distribution} type="rs" label="RS State Distribution" />
        <DistributionBars distribution={agg.momentum_distribution} type="momentum" label="Momentum Distribution" />
      </div>
      {agg.top_picks.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
            Top Picks
          </span>
          <div className="flex flex-wrap gap-2">
            {agg.top_picks.map(pick => (
              <Link
                key={pick.ticker}
                href={`/etfs/${encodeURIComponent(pick.ticker)}`}
                className="flex flex-col gap-0.5 px-3 py-2 border border-paper-rule rounded-sm hover:bg-paper-rule/20 transition-colors min-w-[120px]"
              >
                <span className="font-sans text-xs font-semibold text-ink-primary">{pick.ticker}</span>
                <span className="font-sans text-[10px] text-ink-tertiary truncate max-w-[150px]" title={pick.etf_name ?? ''}>
                  {pick.etf_name ?? '—'}
                </span>
                <span className="font-mono text-[10px] text-teal tabular-nums">
                  RS {pick.rs_pctile_3m ? (parseFloat(pick.rs_pctile_3m) * 100).toFixed(0) : '—'}th
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
      <CommentaryBlock commentary={commentary} />
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/etfs/ETFIntelligencePanel.tsx
git commit -m "feat(etfs): add ETFIntelligencePanel"
```

---

### Task 13: StockScreener.tsx — upgrade

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx`

Adds: sector dropdown filter, 6 optional columns (`ret_1w`, `ret_6m`, `extension_pct`, `vol_63`, `drawdown`, `days_in_state`), 5-gate dot column, `ColumnSettings` trigger, expandable row on click. `// allow-large:` comment required since file will exceed 600 LOC with all these additions.

- [ ] **Step 1: Replace `StockScreener.tsx`**

```tsx
// frontend/src/components/stocks/StockScreener.tsx
// allow-large: screener with 18 columns, sector filter, column settings, and expandable rows
'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown, ChevronRight } from 'lucide-react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import {
  pct, pctColor, PosSizeBar, RSPctileBar,
  RSStateChip, MomentumChip, RiskChip, VolumeChip,
} from '@/lib/stock-formatters'
import { SectorBadge } from './SectorBadge'
import { ColumnSettings, type ColumnDef } from '@/components/ui/ColumnSettings'
import { ExpandableStateRow } from './ExpandableStateRow'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
const RISK_ORDER = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']
const VOL_ORDER = ['Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution']

type SortKey =
  | 'symbol' | 'sector' | 'rs_pctile_3m'
  | 'ret_1w' | 'ret_1m' | 'ret_3m' | 'ret_6m'
  | 'extension_pct' | 'vol_63' | 'drawdown' | 'days_in_state' | 'position_size_pct'
  | 'rs_state' | 'momentum_state' | 'risk_state' | 'volume_state'

type FilterChip = 'all' | 'n50' | 'n100' | 'n500' | 'investable' | 'leader' | 'accel'

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'n50',        label: 'Nifty 50' },
  { key: 'n100',       label: 'Nifty 100' },
  { key: 'n500',       label: 'Nifty 500' },
  { key: 'investable', label: 'Investable' },
  { key: 'leader',     label: 'Leader/Strong' },
  { key: 'accel',      label: 'Accelerating' },
]

const OPTIONAL_COLUMNS: ColumnDef[] = [
  { key: 'ret_1w',        label: '1W Ret',     defaultVisible: false },
  { key: 'ret_6m',        label: '6M Ret',     defaultVisible: false },
  { key: 'extension_pct', label: 'Extension',  defaultVisible: false },
  { key: 'vol_63',        label: 'Vol 63D',    defaultVisible: false },
  { key: 'drawdown',      label: 'Drawdown',   defaultVisible: false },
  { key: 'days_in_state', label: 'Days State', defaultVisible: false },
]

function stateRank(order: string[], val: string | null): number {
  const i = val ? order.indexOf(val) : -1
  return i === -1 ? order.length : i
}

function GateDot({ pass }: { pass: boolean | null | undefined }) {
  if (pass == null) return <span className="w-2 h-2 rounded-full bg-paper-rule inline-block" />
  return (
    <span
      className={`w-2 h-2 rounded-full inline-block ${pass ? 'bg-teal' : 'bg-signal-neg'}`}
    />
  )
}

export function StockScreener({ stocks }: { stocks: StockRowWithSector[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('rs_pctile_3m')
  const [asc, setAsc] = useState(false)
  const [chip, setChip] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')
  const [sectorFilter, setSectorFilter] = useState('all')
  const [visibleCols, setVisibleCols] = useState<Set<string>>(new Set())
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const sectors = useMemo(() => {
    const s = new Set(stocks.map(x => x.sector).filter(Boolean))
    return ['all', ...Array.from(s).sort()]
  }, [stocks])

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  function clearFilters() { setChip('all'); setSectorFilter('all'); setSearch('') }

  const filtered = useMemo(() => {
    let r = stocks
    if (chip === 'n50') r = r.filter(s => s.in_nifty_50)
    else if (chip === 'n100') r = r.filter(s => s.in_nifty_100)
    else if (chip === 'n500') r = r.filter(s => s.in_nifty_500)
    else if (chip === 'investable') r = r.filter(s => s.is_investable)
    else if (chip === 'leader') r = r.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong')
    else if (chip === 'accel') r = r.filter(s => s.momentum_state === 'Accelerating' || s.momentum_state === 'Improving')
    if (sectorFilter !== 'all') r = r.filter(s => s.sector === sectorFilter)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      r = r.filter(s => s.symbol.toLowerCase().includes(q) || s.company_name.toLowerCase().includes(q))
    }
    return [...r].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'symbol') cmp = a.symbol.localeCompare(b.symbol)
      else if (sortKey === 'sector') cmp = a.sector.localeCompare(b.sector)
      else if (sortKey === 'rs_state') cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
      else if (sortKey === 'momentum_state') cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
      else if (sortKey === 'risk_state') cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
      else if (sortKey === 'volume_state') cmp = stateRank(VOL_ORDER, a.volume_state) - stateRank(VOL_ORDER, b.volume_state)
      else {
        const av = a[sortKey as keyof typeof a] != null ? parseFloat(a[sortKey as keyof typeof a] as string) : null
        const bv = b[sortKey as keyof typeof b] != null ? parseFloat(b[sortKey as keyof typeof b] as string) : null
        cmp = av == null && bv == null ? 0 : av == null ? 1 : bv == null ? -1 : av - bv
      }
      return asc ? cmp : -cmp
    })
  }, [stocks, chip, sectorFilter, search, sortKey, asc])

  function SI({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, align = 'left', col }: { label: string; k: SortKey; align?: 'left' | 'right'; col?: string }) {
    if (col && !visibleCols.has(col)) return null
    const active = sortKey === k
    return (
      <th onClick={() => handleSort(k)} className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}`}>
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>{label}<SI k={k} /></span>
      </th>
    )
  }

  const optionalCount = OPTIONAL_COLUMNS.filter(c => visibleCols.has(c.key)).length
  const totalCols = 11 + optionalCount // chevron + symbol + sector + rs + mom + risk + vol + 1m + 3m + gates + rs_pctile + deploy

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input type="search" placeholder="Search symbol or company..." value={search} onChange={e => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56" />
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map(c => (
            <button key={c.key} type="button" aria-pressed={chip === c.key} onClick={() => setChip(c.key)}
              className={`px-2.5 py-1 rounded-sm font-sans text-xs font-medium transition-colors ${chip === c.key ? 'bg-teal text-paper' : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'}`}>
              {c.label}
            </button>
          ))}
        </div>
        <select value={sectorFilter} onChange={e => setSectorFilter(e.target.value)} aria-label="Filter by sector"
          className="px-2.5 py-1 border border-paper-rule rounded-sm font-sans text-xs text-ink-secondary bg-paper focus:outline-none focus:ring-1 focus:ring-teal/50">
          {sectors.map(s => <option key={s} value={s}>{s === 'all' ? 'All Sectors' : s}</option>)}
        </select>
        <ColumnSettings columns={OPTIONAL_COLUMNS} storageKey="atlas-stock-screener-cols" onChange={setVisibleCols} />
        <span className="ml-auto font-sans text-xs text-ink-tertiary whitespace-nowrap">
          {filtered.length} of {stocks.length} stocks
        </span>
      </div>

      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="w-8" />
              <Th label="Symbol" k="symbol" />
              <Th label="Sector" k="sector" />
              <Th label="RS State" k="rs_state" />
              <Th label="Mom" k="momentum_state" />
              <Th label="Risk" k="risk_state" />
              <Th label="Vol" k="volume_state" />
              <Th label="1W" k="ret_1w" align="right" col="ret_1w" />
              <Th label="1M" k="ret_1m" align="right" />
              <Th label="3M" k="ret_3m" align="right" />
              <Th label="6M" k="ret_6m" align="right" col="ret_6m" />
              <Th label="Ext%" k="extension_pct" align="right" col="extension_pct" />
              <Th label="Vol 63D" k="vol_63" align="right" col="vol_63" />
              <Th label="DD" k="drawdown" align="right" col="drawdown" />
              <Th label="Days" k="days_in_state" align="right" col="days_in_state" />
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap"
                title="History · Liquidity · Stage1 · Strength · Direction">Gates</th>
              <Th label="RS Pctile" k="rs_pctile_3m" align="right" />
              <Th label="Deploy %" k="position_size_pct" align="right" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary mb-2">No stocks match the current filter.</p>
                  <button onClick={clearFilters} className="font-sans text-xs text-teal hover:underline">Clear filters</button>
                </td>
              </tr>
            ) : (
              filtered.flatMap((row, i) => {
                const expanded = expandedId === row.instrument_id
                const tr = (
                  <tr key={row.instrument_id}
                    className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors cursor-pointer ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
                    onClick={() => setExpandedId(expanded ? null : row.instrument_id)}>
                    <td className="px-2 py-2.5 text-center">
                      <ChevronRight className={`w-3 h-3 text-ink-tertiary transition-transform ${expanded ? 'rotate-90' : ''}`} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <Link href={`/stocks/${encodeURIComponent(row.symbol)}`} onClick={e => e.stopPropagation()} className="hover:opacity-80">
                        <div className="font-sans text-xs font-semibold text-ink-primary">{row.symbol}</div>
                        <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[140px]" title={row.company_name}>{row.company_name}</div>
                      </Link>
                    </td>
                    <td className="px-3 py-2.5"><SectorBadge sector={row.sector} /></td>
                    <td className="px-3 py-2.5"><RSStateChip value={row.rs_state} /></td>
                    <td className="px-3 py-2.5"><MomentumChip value={row.momentum_state} /></td>
                    <td className="px-3 py-2.5"><RiskChip value={row.risk_state} /></td>
                    <td className="px-3 py-2.5"><VolumeChip value={row.volume_state} /></td>
                    {visibleCols.has('ret_1w') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1w)}`}>{pct(row.ret_1w)}</td>}
                    <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>{pct(row.ret_1m)}</td>
                    <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>{pct(row.ret_3m)}</td>
                    {visibleCols.has('ret_6m') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_6m)}`}>{pct(row.ret_6m)}</td>}
                    {visibleCols.has('extension_pct') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.extension_pct)}`}>{pct(row.extension_pct)}</td>}
                    {visibleCols.has('vol_63') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{row.vol_63 ? (parseFloat(row.vol_63) * 100).toFixed(1) : '—'}</td>}
                    {visibleCols.has('drawdown') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.drawdown)}`}>{pct(row.drawdown)}</td>}
                    {visibleCols.has('days_in_state') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{row.days_in_state ?? '—'}</td>}
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1">
                        <GateDot pass={row.history_gate_pass} />
                        <GateDot pass={row.liquidity_gate_pass} />
                        <GateDot pass={row.stage1_base_qualifies} />
                        <GateDot pass={row.strength_gate} />
                        <GateDot pass={row.direction_gate} />
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right"><RSPctileBar value={row.rs_pctile_3m} /></td>
                    <td className="px-3 py-2.5 text-right"><div className="flex justify-end"><PosSizeBar value={row.position_size_pct} /></div></td>
                  </tr>
                )
                return expanded
                  ? [tr, <ExpandableStateRow key={`${row.instrument_id}-exp`} instrumentId={row.instrument_id} colSpan={totalCols} />]
                  : [tr]
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stocks/StockScreener.tsx
git commit -m "feat(stocks): upgrade StockScreener — sector filter, optional cols, gate dots, expandable rows"
```

---

### Task 14: ETFScreener.tsx — upgrade

**Files:**
- Modify: `frontend/src/components/etfs/ETFScreener.tsx`

Adds: 4 optional columns (`ret_1w`, `vol_63`, `drawdown`, `days_in_state`), 6-gate badge, `ColumnSettings`.

- [ ] **Step 1: Replace `ETFScreener.tsx`**

```tsx
// frontend/src/components/etfs/ETFScreener.tsx
// allow-large: screener with 14 columns, column settings, 6-gate badge
'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'
import {
  pct, pctColor, PosSizeBar, RSPctileBar,
  RSStateChip, MomentumChip, RiskChip,
} from '@/lib/stock-formatters'
import { ColumnSettings, type ColumnDef } from '@/components/ui/ColumnSettings'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
const RISK_ORDER = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']

function stateRank(order: string[], val: string | null): number {
  const i = val ? order.indexOf(val) : -1
  return i === -1 ? order.length : i
}

type SortKey =
  | 'ticker' | 'theme' | 'rs_pctile_3m'
  | 'ret_1w' | 'ret_1m' | 'ret_3m' | 'vol_63' | 'drawdown' | 'days_in_state'
  | 'position_size_pct' | 'rs_state' | 'momentum_state' | 'risk_state'

type FilterChip = 'all' | 'broad' | 'sectoral' | 'thematic' | 'investable'

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'broad',      label: 'Broad' },
  { key: 'sectoral',   label: 'Sectoral' },
  { key: 'thematic',   label: 'Thematic' },
  { key: 'investable', label: 'Investable' },
]

const OPTIONAL_COLUMNS: ColumnDef[] = [
  { key: 'ret_1w',        label: '1W Ret',     defaultVisible: false },
  { key: 'vol_63',        label: 'Vol 63D',    defaultVisible: false },
  { key: 'drawdown',      label: 'Drawdown',   defaultVisible: false },
  { key: 'days_in_state', label: 'Days State', defaultVisible: false },
]

const THEME_STYLE: Record<string, string> = {
  Broad:    'bg-teal/10 text-teal',
  Sectoral: 'bg-signal-pos/10 text-signal-pos',
  Thematic: 'bg-signal-warn/10 text-signal-warn',
}

function ThemeBadge({ theme }: { theme: string }) {
  const style = THEME_STYLE[theme] ?? 'bg-ink-tertiary/10 text-ink-secondary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${style}`}>
      {theme}
    </span>
  )
}

function GateBadge({ row }: { row: ETFRow }) {
  const gates = [
    { label: 'H', pass: row.history_gate_pass,   title: 'History' },
    { label: 'L', pass: row.liquidity_gate_pass, title: 'Liquidity' },
    { label: 'W', pass: row.weinstein_gate_pass, title: 'Weinstein' },
    { label: 'S', pass: row.strength_gate,       title: 'Strength' },
    { label: 'D', pass: row.direction_gate,      title: 'Direction' },
    { label: 'Ri', pass: row.risk_gate,           title: 'Risk' },
  ]
  const passing = gates.filter(g => g.pass).length
  return (
    <div className="flex items-center gap-0.5" title={gates.map(g => `${g.title}: ${g.pass ? '✓' : '✗'}`).join('\n')}>
      {gates.map(g => (
        <span key={g.label}
          className={`inline-flex items-center justify-center w-4 h-4 rounded-[2px] font-mono text-[8px] font-bold ${
            g.pass == null ? 'bg-paper-rule/30 text-ink-tertiary' :
            g.pass ? 'bg-teal/20 text-teal' : 'bg-signal-neg/10 text-signal-neg'
          }`}>
          {g.label}
        </span>
      ))}
      <span className="ml-1 font-mono text-[10px] text-ink-tertiary">{passing}/6</span>
    </div>
  )
}

export function ETFScreener({ etfs }: { etfs: ETFRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('rs_pctile_3m')
  const [asc, setAsc] = useState(false)
  const [chip, setChip] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')
  const [visibleCols, setVisibleCols] = useState<Set<string>>(new Set())

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  const filtered = useMemo(() => {
    let r = etfs
    if (chip === 'broad') r = r.filter(e => e.theme === 'Broad')
    else if (chip === 'sectoral') r = r.filter(e => e.theme === 'Sectoral')
    else if (chip === 'thematic') r = r.filter(e => e.theme === 'Thematic')
    else if (chip === 'investable') r = r.filter(e => e.is_investable)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      r = r.filter(e => e.ticker.toLowerCase().includes(q) || (e.etf_name ?? '').toLowerCase().includes(q))
    }
    return [...r].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'ticker') cmp = a.ticker.localeCompare(b.ticker)
      else if (sortKey === 'theme') cmp = a.theme.localeCompare(b.theme)
      else if (sortKey === 'rs_state') cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
      else if (sortKey === 'momentum_state') cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
      else if (sortKey === 'risk_state') cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
      else {
        const av = a[sortKey as keyof ETFRow] != null ? parseFloat(a[sortKey as keyof ETFRow] as string) : null
        const bv = b[sortKey as keyof ETFRow] != null ? parseFloat(b[sortKey as keyof ETFRow] as string) : null
        cmp = av == null && bv == null ? 0 : av == null ? 1 : bv == null ? -1 : av - bv
      }
      return asc ? cmp : -cmp
    })
  }, [etfs, chip, search, sortKey, asc])

  function SI({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, align = 'left', col }: { label: string; k: SortKey; align?: 'left' | 'right'; col?: string }) {
    if (col && !visibleCols.has(col)) return null
    const active = sortKey === k
    return (
      <th onClick={() => handleSort(k)} className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}`}>
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>{label}<SI k={k} /></span>
      </th>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input type="search" placeholder="Search ticker or name..." value={search} onChange={e => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56" />
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map(c => (
            <button key={c.key} type="button" aria-pressed={chip === c.key} onClick={() => setChip(c.key)}
              className={`px-2.5 py-1 rounded-sm font-sans text-xs font-medium transition-colors ${chip === c.key ? 'bg-teal text-paper' : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'}`}>
              {c.label}
            </button>
          ))}
        </div>
        <ColumnSettings columns={OPTIONAL_COLUMNS} storageKey="atlas-etf-screener-cols" onChange={setVisibleCols} />
        <span className="ml-auto font-sans text-xs text-ink-tertiary whitespace-nowrap">
          {filtered.length} of {etfs.length} ETFs
        </span>
      </div>

      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Ticker" k="ticker" />
              <Th label="Theme" k="theme" />
              <Th label="RS State" k="rs_state" />
              <Th label="Mom" k="momentum_state" />
              <Th label="Risk" k="risk_state" />
              <Th label="1W" k="ret_1w" align="right" col="ret_1w" />
              <Th label="1M" k="ret_1m" align="right" />
              <Th label="3M" k="ret_3m" align="right" />
              <Th label="Vol 63D" k="vol_63" align="right" col="vol_63" />
              <Th label="DD" k="drawdown" align="right" col="drawdown" />
              <Th label="Days" k="days_in_state" align="right" col="days_in_state" />
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Gates</th>
              <Th label="RS Pctile" k="rs_pctile_3m" align="right" />
              <Th label="Deploy %" k="position_size_pct" align="right" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={14} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary">No ETFs match the current filter.</p>
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => (
                <tr key={row.ticker}
                  className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <Link href={`/etfs/${encodeURIComponent(row.ticker)}`} className="hover:opacity-80">
                      <div className="font-sans text-xs font-semibold text-ink-primary">{row.ticker}</div>
                      <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[200px]" title={row.etf_name ?? ''}>{row.etf_name ?? '—'}</div>
                    </Link>
                  </td>
                  <td className="px-3 py-2.5"><ThemeBadge theme={row.theme} /></td>
                  <td className="px-3 py-2.5"><RSStateChip value={row.rs_state} /></td>
                  <td className="px-3 py-2.5"><MomentumChip value={row.momentum_state} /></td>
                  <td className="px-3 py-2.5"><RiskChip value={row.risk_state} /></td>
                  {visibleCols.has('ret_1w') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1w)}`}>{pct(row.ret_1w)}</td>}
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>{pct(row.ret_1m)}</td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>{pct(row.ret_3m)}</td>
                  {visibleCols.has('vol_63') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{row.vol_63 ? (parseFloat(row.vol_63) * 100).toFixed(1) : '—'}</td>}
                  {visibleCols.has('drawdown') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.drawdown)}`}>{pct(row.drawdown)}</td>}
                  {visibleCols.has('days_in_state') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{row.days_in_state ?? '—'}</td>}
                  <td className="px-3 py-2.5"><GateBadge row={row} /></td>
                  <td className="px-3 py-2.5 text-right"><RSPctileBar value={row.rs_pctile_3m} /></td>
                  <td className="px-3 py-2.5 text-right"><div className="flex justify-end"><PosSizeBar value={row.position_size_pct} /></div></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/etfs/ETFScreener.tsx
git commit -m "feat(etfs): upgrade ETFScreener — optional cols, column settings, 6-gate badge"
```

---

### Task 15: stocks/page.tsx wiring

**Files:**
- Modify: `frontend/src/app/stocks/page.tsx`

Replace `getTopPicksAcrossSectors()` with `getAllStocksAggregates()`. Add `StocksIntelligencePanel`. Remove `StockTopPicks` import.

- [ ] **Step 1: Replace `stocks/page.tsx`**

```tsx
// frontend/src/app/stocks/page.tsx
export const dynamic = 'force-dynamic'

import { getAllStocks } from '@/lib/queries/stocks'
import { getAllStocksAggregates } from '@/lib/queries/stocks-aggregates'
import { StockScreener } from '@/components/stocks/StockScreener'
import { StockBreadthPanel } from '@/components/stocks/StockBreadthPanel'
import { StocksIntelligencePanel } from '@/components/stocks/StocksIntelligencePanel'

export default async function StocksPage() {
  const [stocks, aggregates] = await Promise.all([
    getAllStocks(),
    getAllStocksAggregates(),
  ])

  if (stocks.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No stock data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const above30wMaCount = stocks.filter(s => s.above_30w_ma).length

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Stock Universe
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-teal" />
              {aggregates.investable_count} Investable
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {aggregates.leader_count + aggregates.strong_count} Leader/Strong
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {aggregates.accel_count} Accel/Improving
            </span>
          </div>
        </div>
      </div>
      <div className="px-6 py-6 flex flex-col gap-6">
        <StocksIntelligencePanel aggregates={aggregates} />
        <StockScreener stocks={stocks} />
        <StockBreadthPanel stocks={stocks} above30wMaCount={above30wMaCount} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/stocks/page.tsx
git commit -m "feat(stocks): wire StocksIntelligencePanel, remove StockTopPicks from page"
```

---

### Task 16: etfs/page.tsx wiring

**Files:**
- Modify: `frontend/src/app/etfs/page.tsx`

- [ ] **Step 1: Replace `etfs/page.tsx`**

```tsx
// frontend/src/app/etfs/page.tsx
export const dynamic = 'force-dynamic'

import { getAllETFs } from '@/lib/queries/etfs'
import { getAllETFsAggregates } from '@/lib/queries/etfs-aggregates'
import { ETFScreener } from '@/components/etfs/ETFScreener'
import { ETFIntelligencePanel } from '@/components/etfs/ETFIntelligencePanel'

export default async function ETFsPage() {
  const [etfs, aggregates] = await Promise.all([
    getAllETFs(),
    getAllETFsAggregates(),
  ])

  if (etfs.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No ETF data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            ETF Universe
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-teal" />
              {aggregates.investable_count} Investable
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {aggregates.leader_count + aggregates.strong_count} Leader/Strong
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {aggregates.broad_investable} Broad Investable
            </span>
          </div>
        </div>
      </div>
      <div className="px-6 py-6 flex flex-col gap-6">
        <ETFIntelligencePanel aggregates={aggregates} />
        <ETFScreener etfs={etfs} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Run all tests**

```bash
cd frontend && bun run test
```

Expected: All tests pass (including pre-existing commentary/stocks tests).

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && bun run tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/etfs/page.tsx
git commit -m "feat(etfs): wire ETFIntelligencePanel and aggregates into ETF page"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| ETF state_since_date migration (028, not 027 which is taken) | 1 |
| getAllStocks() 10 new columns (all exist in DB — no migration needed) | 2 |
| Stocks aggregate query with RS/momentum distribution + top picks | 3 |
| getAllETFs() 4 new columns (ret_1w, vol_63, drawdown, days_in_state) | 4 |
| ETF aggregate query with distribution + top picks | 5 |
| buildETFCommentary CONDITIONS array pattern | 6 |
| /api/states-compact with full validation (400 for both/neither param, days 1-365) | 7 |
| ColumnSettings with Radix Popover + localStorage + QuotaExceededError safety | 8 |
| MetricTileRow presentational component | 9 |
| Shared DistributionBars (DRY — used by both Intelligence Panels) | 10 |
| StocksIntelligencePanel + ExpandableStateRow (300ms debounce + AbortController) | 11 |
| ETFIntelligencePanel | 12 |
| StockScreener: sector filter + optional cols + gate dots + expandable | 13 |
| ETFScreener: optional cols + column settings + 6-gate badge | 14 |
| stocks/page.tsx: remove StockTopPicks, add Intelligence Panel | 15 |
| etfs/page.tsx: add Intelligence Panel | 16 |

### Type Consistency

- `StocksAggregates.pct_leader_strong` — fraction 0–1 throughout Tasks 3, 11, 15 ✓
- `StocksAggregates.median_rs_pctile` — fraction 0–1, matches existing `StocksPageAggregates` and commentary tests ✓
- `ETFsAggregates.pct_leader_strong` — 0–100 scale throughout Tasks 5, 12, 16 ✓
- `ETFsAggregates.median_rs_pctile` — 0–100 scale; SQL uses `* 100` cast in Task 5 ✓
- `vol_63` column name consistent: `StockRowWithSector` (Task 2), `ETFRow` (Task 4), both screeners ✓
- `days_in_state` — `number | null`, `::int` cast in SQL (Tasks 2, 4) ✓
- `TopPickRow.rs_pctile_3m` — `string | null`, `parseFloat()` at display time in Intelligence Panels ✓
- `ColumnSettings` storageKey — `"atlas-stock-screener-cols"` (Task 13), `"atlas-etf-screener-cols"` (Task 14) ✓
- `OPTIONAL_COLUMNS[].key` strings match `visibleCols.has(col)` checks in screener rows ✓
- `ETFsPageAggregates` (commentary) receives `total_count` from `agg.total` in Task 12 ✓

### Placeholder Scan

No TODOs, TBDs, "similar to Task N", or incomplete steps found.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-10-sprint-2-stocks-etf-upgrade.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration. Invoke: `superpowers:subagent-driven-development`

**2. Inline Execution** — Execute tasks in this session. Invoke: `superpowers:executing-plans`

Which approach?
