# v6 Page 03 Markets RS — Frontend Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline task-by-task execution. Steps use checkbox (`- [ ]`).

**Goal:** Wire the v6 Markets RS page (route `/v6/markets-rs`) to the live `atlas.mv_markets_rs_grid` materialized view, rendering the 9-baseline × 5-window grid + 4 hero readouts from mockup `03-markets-rs.html`.

**Architecture:** Next.js Server Component reads from Supabase via `postgres` template-literal helper (`@/lib/db`). Single MV query returns all 9 rows; hero readouts are derived in TS from the grid. Page composes the mockup using inline tags + Pretext-native HTML — no React-component extraction needed since this page has no shared atom dependencies. Follows the existing `regime.ts` + `app/regime/page.tsx` pattern.

**Tech Stack:** Next.js 14 App Router, React 18 Server Components, postgres-js (`@/lib/db`), TypeScript 5.

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `frontend/src/lib/queries/v6/markets-rs.ts` | CREATE | Query `mv_markets_rs_grid` → 9 baseline rows; derive 4 hero readouts |
| `frontend/src/app/v6/markets-rs/page.tsx` | CREATE | Server Component route at `/v6/markets-rs`; renders grid + heroes + footnote |
| `frontend/src/app/v6/markets-rs/loading.tsx` | CREATE | Skeleton loader |

---

## Task 1: Write the query module

**Files:**
- Create: `frontend/src/lib/queries/v6/markets-rs.ts`

- [ ] **Step 1.1: Write `markets-rs.ts`**

```typescript
// frontend/src/lib/queries/v6/markets-rs.ts
//
// Reads atlas.mv_markets_rs_grid (9 baselines × 5 time windows of return + rank).
// Derives 4 hero readouts (today's leader, India vs world, within India, India RS grade).
//
// MV is refreshed nightly via pg_cron (Phase D) — REFRESH CONCURRENTLY supported.

import 'server-only'
import sql from '@/lib/db'

export type RsBaselineRow = {
  rank_order: number
  baseline_name: string
  latest_close_inr: number | null
  as_of_date: string | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rank_1w: number | null
  rank_1m: number | null
  rank_3m: number | null
  rank_6m: number | null
  rank_12m: number | null
}

export type MarketsRsHero = {
  today_leader: string | null
  india_rank_1m: number | null
  large_vs_midsmall_spread_3m: number | null  // percentage points
  india_rs_grade: 'A' | 'B' | 'C' | 'D' | null
}

export type MarketsRsPage = {
  as_of_date: string | null
  baselines: RsBaselineRow[]
  hero: MarketsRsHero
}

type Row = {
  rank_order: number
  baseline_name: string
  latest_close_inr: string | null
  as_of_date: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rank_1w: number | null
  rank_1m: number | null
  rank_3m: number | null
  rank_6m: number | null
  rank_12m: number | null
}

function toNumber(s: string | null): number | null {
  if (s == null) return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

export async function getMarketsRsPage(): Promise<MarketsRsPage> {
  const rows = await sql<Row[]>`
    SELECT
      rank_order, baseline_name,
      latest_close_inr::text AS latest_close_inr,
      as_of_date::text       AS as_of_date,
      ret_1w::text  AS ret_1w,
      ret_1m::text  AS ret_1m,
      ret_3m::text  AS ret_3m,
      ret_6m::text  AS ret_6m,
      ret_12m::text AS ret_12m,
      rank_1w, rank_1m, rank_3m, rank_6m, rank_12m
    FROM atlas.mv_markets_rs_grid
    ORDER BY rank_order
  `

  const baselines: RsBaselineRow[] = rows.map(r => ({
    rank_order: r.rank_order,
    baseline_name: r.baseline_name,
    latest_close_inr: toNumber(r.latest_close_inr),
    as_of_date: r.as_of_date,
    ret_1w:  toNumber(r.ret_1w),
    ret_1m:  toNumber(r.ret_1m),
    ret_3m:  toNumber(r.ret_3m),
    ret_6m:  toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rank_1w: r.rank_1w,
    rank_1m: r.rank_1m,
    rank_3m: r.rank_3m,
    rank_6m: r.rank_6m,
    rank_12m: r.rank_12m,
  }))

  // Hero derivations
  const leader1m = baselines.find(b => b.rank_1w === 1)?.baseline_name ?? null
  const nifty500 = baselines.find(b => b.baseline_name === 'Nifty 500')
  const nifty100 = baselines.find(b => b.baseline_name === 'Nifty 100')
  const midcap = baselines.find(b => b.baseline_name === 'Nifty Midcap 150')
  const smallcap = baselines.find(b => b.baseline_name === 'Nifty Smallcap 250')

  let spread_3m: number | null = null
  if (nifty100?.ret_3m != null && midcap?.ret_3m != null && smallcap?.ret_3m != null) {
    spread_3m = (nifty100.ret_3m - (midcap.ret_3m + smallcap.ret_3m) / 2) * 100
  }

  // India RS Grade — rule per spec (avg rank across 1m/3m/6m of Nifty 500)
  let grade: 'A' | 'B' | 'C' | 'D' | null = null
  if (nifty500?.rank_1m != null && nifty500?.rank_3m != null && nifty500?.rank_6m != null) {
    const avg = (nifty500.rank_1m + nifty500.rank_3m + nifty500.rank_6m) / 3
    if      (avg <= 2.5) grade = 'A'
    else if (avg <= 4.5) grade = 'B'
    else if (avg <= 6.5) grade = 'C'
    else                 grade = 'D'
  }

  return {
    as_of_date: baselines[0]?.as_of_date ?? null,
    baselines,
    hero: {
      today_leader: leader1m,
      india_rank_1m: nifty500?.rank_1m ?? null,
      large_vs_midsmall_spread_3m: spread_3m,
      india_rs_grade: grade,
    },
  }
}
```

- [ ] **Step 1.2: Commit**

```bash
git add frontend/src/lib/queries/v6/markets-rs.ts
git commit -m "feat(v6): markets-rs query module reads mv_markets_rs_grid + derives hero readouts"
```

---

## Task 2: Write the route page

**Files:**
- Create: `frontend/src/app/v6/markets-rs/page.tsx`
- Create: `frontend/src/app/v6/markets-rs/loading.tsx`

- [ ] **Step 2.1: Write `loading.tsx`**

```tsx
// frontend/src/app/v6/markets-rs/loading.tsx
export default function Loading() {
  return (
    <div className="container mx-auto px-8 py-16">
      <div className="animate-pulse">
        <div className="h-12 w-3/4 bg-paper-deep rounded mb-8" />
        <div className="grid grid-cols-4 gap-4 mb-12">
          <div className="h-32 bg-paper-deep rounded" />
          <div className="h-32 bg-paper-deep rounded" />
          <div className="h-32 bg-paper-deep rounded" />
          <div className="h-32 bg-paper-deep rounded" />
        </div>
        <div className="h-96 bg-paper-deep rounded" />
      </div>
    </div>
  )
}
```

- [ ] **Step 2.2: Write `page.tsx`**

```tsx
// frontend/src/app/v6/markets-rs/page.tsx
//
// Page 03 Markets RS — 9 baselines × 5 windows grid + 4 hero readouts.
// Reads from atlas.mv_markets_rs_grid via getMarketsRsPage().
//
// Data refresh: nightly pg_cron at 20:05 IST.

import { getMarketsRsPage } from '@/lib/queries/v6/markets-rs'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtPct(v: number | null, digits = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(digits)}%`
}

function fmtRank(r: number | null): string {
  if (r == null) return '—'
  return `${r} / 9`
}

function cellTint(ret: number | null): string {
  if (ret == null) return 'text-ink-tertiary'
  if (ret >= 0.05) return 'text-signal-pos font-medium'
  if (ret > 0)    return 'text-signal-pos'
  if (ret > -0.05) return 'text-signal-neg'
  return 'text-signal-neg font-medium'
}

export default async function MarketsRsPage() {
  const data = await getMarketsRsPage()
  const { baselines, hero, as_of_date } = data

  return (
    <main className="container mx-auto px-8 py-12 max-w-7xl">
      {/* Header */}
      <header className="mb-12 pb-8 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-3">
          Cross-market relative strength
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
          Where is money working today?
        </h1>
        <p className="text-base text-ink-secondary max-w-3xl">
          Nine baselines across India, cross-market, and commodities — ranked across five time windows.
          All returns in INR (foreign baselines USD-converted at RBI reference rate).
        </p>
        {as_of_date && (
          <div className="text-xs font-mono text-ink-tertiary mt-3">
            As of {as_of_date} · refreshed nightly 20:00 IST
          </div>
        )}
      </header>

      {/* Hero readouts — 4 cards */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-12">
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            Today's leadership
          </div>
          <div className="font-serif text-xl text-ink leading-tight">
            {hero.today_leader ?? '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Top performer this week
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            India vs world
          </div>
          <div className="font-mono text-2xl text-ink leading-tight">
            {hero.india_rank_1m != null ? `${hero.india_rank_1m} / 9` : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Nifty 500 rank on 1-month
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            Within India
          </div>
          <div className={`font-mono text-2xl leading-tight ${hero.large_vs_midsmall_spread_3m != null && hero.large_vs_midsmall_spread_3m > 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
            {hero.large_vs_midsmall_spread_3m != null
              ? `${hero.large_vs_midsmall_spread_3m > 0 ? '+' : ''}${hero.large_vs_midsmall_spread_3m.toFixed(1)}pp`
              : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Large vs mid+small (3M spread)
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            India RS grade
          </div>
          <div className="font-serif text-4xl text-ink leading-none">
            {hero.india_rs_grade ?? '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Nifty 500 vs all 9 baselines
          </div>
        </div>
      </section>

      {/* 9 × 5 RS grid */}
      <section className="mb-12">
        <h2 className="font-serif text-2xl text-ink mb-4">RS grid · 9 baselines × 5 windows</h2>
        <div className="border border-paper-rule rounded-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-paper-deep border-b border-paper-rule">
              <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                <th className="px-4 py-3 text-left">Baseline</th>
                <th className="px-4 py-3 text-right">1W</th>
                <th className="px-4 py-3 text-right">1M</th>
                <th className="px-4 py-3 text-right">3M</th>
                <th className="px-4 py-3 text-right">6M</th>
                <th className="px-4 py-3 text-right">12M</th>
              </tr>
            </thead>
            <tbody>
              {baselines.map(b => (
                <tr key={b.baseline_name} className="border-t border-paper-rule hover:bg-paper-soft transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{b.baseline_name}</td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_1w)}`}>
                    {fmtPct(b.ret_1w)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_1w)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_1m)}`}>
                    {fmtPct(b.ret_1m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_1m)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_3m)}`}>
                    {fmtPct(b.ret_3m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_3m)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_6m)}`}>
                    {fmtPct(b.ret_6m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_6m)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_12m)}`}>
                    {fmtPct(b.ret_12m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_12m)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footnote */}
      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6">
        All returns are total return in INR. Foreign baselines are USD-converted at the prevailing RBI reference rate.
        Gold is GOLDBEES (₹/g, Mumbai), not the international USD spot. MSCI EM is proxied by VWO (USD-denominated, FX-adjusted).
      </footer>
    </main>
  )
}
```

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/app/v6/markets-rs/page.tsx frontend/src/app/v6/markets-rs/loading.tsx
git commit -m "feat(v6): /v6/markets-rs route — 9×5 RS grid + 4 hero readouts (live from mv_markets_rs_grid)"
```

---

## Task 3: Smoke test

- [ ] **Step 3.1: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: zero new errors involving `markets-rs`.

- [ ] **Step 3.2: Manual sanity check of query (optional, requires dev server)**

If dev server runs:
```bash
cd frontend && npm run dev
# visit http://localhost:3000/v6/markets-rs
# verify 9 baselines visible, hero readouts populated, ranks 1-9
```

---

## Self-review

**1. Spec coverage:**
- ✅ Query module reads `mv_markets_rs_grid` — Task 1
- ✅ 9 baselines surfaced — Task 1, page table
- ✅ 5 time windows — Task 1, query SELECT
- ✅ 4 hero readouts — Task 1 derivation + Task 2 rendering
- ✅ Server Component pattern — Task 2 (no 'use client')
- ✅ Follows regime.ts pattern — uses `@/lib/db` + 'server-only'
- ✅ Loading skeleton — Task 2.1

**2. Placeholder scan:** No TODO, no "fill in", all code complete inline. ✅

**3. Type consistency:**
- `RsBaselineRow` shape matches MV columns exactly
- `MarketsRsHero` fields match what page.tsx consumes
- Numeric coercion via `toNumber()` helper applied consistently
- ✅

Plan complete. Inline execution.
