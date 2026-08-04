# Fund Category vs Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/funds/compare` — pick a mutual-fund category and a period, get an equal-weighted composite equity curve against Nifty 50 / Nifty 500 / the category index, plus returns, rolling-return statistics, and the constituent list, on a page that prints cleanly to PDF.

**Architecture:** Three layers with hard boundaries. SQL (`lib/queries/fund_category_curve.ts`) does the chain-linked aggregation in Postgres and returns plain typed rows. A pure module (`lib/fundCategoryCurve.ts`) does every piece of arithmetic on arrays of `{d, v}` — no DB, no React, no clock — and is where the tests point. Components own layout and formatting only. Nothing under `atlas/`, the nightly pipeline, or the lens compute changes.

**Tech Stack:** Next.js App Router server components, `postgres` (porsager) tagged templates, `AtlasLightweightChart` (TradingView Lightweight Charts), Tailwind with the Atlas v4 tokens, vitest.

**Spec:** `docs/superpowers/specs/2026-08-04-fund-category-compare-design.md`

---

## Data findings that drive this plan

All verified against the live `atlas_foundation` on 2026-08-04. Read these before Task 1 — three of them changed the design after the spec was written.

**1. Three categories have a dead NAV feed.** This is a pre-existing pipeline defect, not something this page causes, but the page must not render a four-month-old curve as if it were current:

| Category | Funds w/ NAV | Fresh (≥2026-07-25) | Newest NAV |
|---|---:|---:|---|
| India Fund Index Funds | 245 | **0** | 2026-05-15 |
| India Fund Focused Fund | 30 | **0** | 2026-05-15 |
| India Fund Equity - ESG | 12 | **0** | 2026-04-06 |
| India Fund Value | 23 | **1** | 2026-07-31 |

Every other category is fresh to 2026-07-31. Task 6 puts the per-category last-NAV date in the picker and Task 11 puts a staleness banner on the page.

**2. Benchmarks must be joined as-of, not on equality.** `index_prices` has no row for 2024-03-31, 2025-03-31 or 2026-03-31 while fund NAVs exist on all three. An equality join silently drops those points. A `LEFT JOIN LATERAL … date <= nav_date ORDER BY date DESC LIMIT 1` fills them with the real prior close (53949.20 / 53589.80 / 45538.65 for `NIFTY FMCG`). The existing per-fund `FundEquityCurves.tsx` uses an equality join and has the same latent hole — noted, not changed here.

**3. The composite query is slow enough to need checking.** Worst case (Index Funds, 245 funds) measured over the `aws-1-` pooler from the laptop: 8.2s cold, ~2.5–2.9s warm, and 3y is no faster than max — the cost is the NAV scan, not the LATERAL. Task 4 includes an `EXPLAIN (ANALYZE, BUFFERS)` step and a decision gate.

**4. "Index Funds" is a mixed category.** It contains gilt and bond index funds alongside equity ones, so its composite is not an equity read. Not a bug; the constituents table makes it visible.

**5. Survivorship bias is unfixable here.** 2 of 4,209 master rows are inactive and none has both NAV and a category — closed and merged funds are absent from the source snapshot. The composite is *built* to handle entry and exit correctly, so it self-corrects if that history is ever ingested. Until then the page discloses it.

---

## File structure

| File | Responsibility | Kind |
|---|---|---|
| `frontend/src/lib/fundCategoryCurve.ts` | pure arithmetic — rebase, span/trailing returns, CAGR gate, rolling windows, rolling stats, period table | create |
| `frontend/src/lib/__tests__/fundCategoryCurve.test.ts` | unit tests over the pure module, real values only | create |
| `frontend/src/lib/queries/fund_category_curve.ts` | SQL only — category options, composite + benchmarks, constituents; the category→index map | create |
| `frontend/src/lib/queries/__tests__/fund_category_curve.int.test.ts` | integration test, skipped without `ATLAS_DB_URL` | create |
| `frontend/src/components/funds/CategoryCompareControls.tsx` | the five inputs, client component, writes to the URL | create |
| `frontend/src/components/funds/CategoryCompareChart.tsx` | growth / rolling chart + constituent-count strip | create |
| `frontend/src/components/funds/CategoryCompareTables.tsx` | returns table, rolling-stats table, constituents table | create |
| `frontend/src/app/funds/compare/page.tsx` | route shell — parse searchParams, fetch, compose, disclose | create |
| `frontend/src/components/funds/FundsPageV4.tsx` | add the entry link | modify |

Size limits: 600 LOC source / 800 LOC tests / 250 LOC page shell.

---

## Task 1: The pure module's types and `rebase`

**Files:**
- Create: `frontend/src/lib/fundCategoryCurve.ts`
- Create: `frontend/src/lib/__tests__/fundCategoryCurve.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/__tests__/fundCategoryCurve.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { rebase, type CurvePoint } from '../fundCategoryCurve'

// REAL composite output for "India Fund Sector - Energy" over 2026-03-30 → 2026-04-07,
// produced by the chain-link SQL in lib/queries/fund_category_curve.ts against
// atlas_foundation on 2026-08-04. NO synthetic inputs (rule #0).
// This window is chosen because it exercises three real conditions at once:
//   • 2026-03-31 n=4 — SBI Energy (F00001JAQ0) has no 03-30 NAV, so no return that day
//   • 2026-04-01 n=3 — two funds missing entirely (a real NAV gap)
//   • after 2026-04-02 n=4 — Groww BSE Power FOF (F00001RXVU) stops reporting (real exit)
export const ENERGY: CurvePoint[] = [
  { d: '2026-03-30', v: 100.000000 },
  { d: '2026-03-31', v: 99.995804 },
  { d: '2026-04-01', v: 101.772909 },
  { d: '2026-04-02', v: 102.067793 },
  { d: '2026-04-06', v: 102.120648 },
  { d: '2026-04-07', v: 102.398542 },
]

// REAL NIFTY ENERGY closes are not needed here; benchmark rebasing is covered in Task 2.

describe('rebase', () => {
  it('sets the first point to exactly 100 and scales the rest proportionally', () => {
    const raw: CurvePoint[] = [
      { d: '2026-03-30', v: 45538.65 }, // real NIFTY FMCG close 2026-03-30
      { d: '2026-04-30', v: 51072.10 }, // real NIFTY FMCG close 2026-04-30
      { d: '2026-07-31', v: 49642.05 }, // real NIFTY FMCG close 2026-07-31
    ]
    const out = rebase(raw)
    expect(out[0]).toEqual({ d: '2026-03-30', v: 100 })
    expect(out[1].v).toBeCloseTo(112.1490, 3) // 100 * 51072.10 / 45538.65
    expect(out[2].v).toBeCloseTo(109.0092, 3) // 100 * 49642.05 / 45538.65
  })

  it('leaves a series already anchored at 100 unchanged', () => {
    const out = rebase(ENERGY)
    expect(out.map((p) => p.d)).toEqual(ENERGY.map((p) => p.d))
    // Element-wise, not toEqual: 100 * 99.995804 / 100 need not be bit-identical.
    out.forEach((p, i) => expect(p.v).toBeCloseTo(ENERGY[i].v, 9))
  })

  it('returns an empty array for an empty series', () => {
    expect(rebase([])).toEqual([])
  })

  it('returns an empty array when the first value is zero or negative', () => {
    expect(rebase([{ d: '2026-01-01', v: 0 }, { d: '2026-01-02', v: 5 }])).toEqual([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/lib/__tests__/fundCategoryCurve.test.ts
```

Expected: FAIL — `Failed to resolve import "../fundCategoryCurve"`.

- [ ] **Step 3: Write the minimal implementation**

Create `frontend/src/lib/fundCategoryCurve.ts`:

```ts
// fundCategoryCurve — every number on /funds/compare is computed here.
//
// Pure by design: takes arrays of { d, v }, returns arrays and numbers. No DB, no React,
// no clock. The SQL module hands it real rows; the components hand it to the formatter.
// Keeping the arithmetic in one testable place is the whole point — the composite is a
// chain-linked index and getting the compounding subtly wrong is invisible on a chart.

/** One point on a series: ISO date, and a value (a rebased index level, or a percentage). */
export type CurvePoint = { d: string; v: number }

/** Rebase a series so its first point is exactly 100. Empty in, empty out. */
export function rebase(pts: CurvePoint[]): CurvePoint[] {
  const base = pts[0]?.v
  if (base == null || base <= 0) return []
  return pts.map((p) => ({ d: p.d, v: (100 * p.v) / base }))
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/lib/__tests__/fundCategoryCurve.test.ts
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/fundCategoryCurve.ts frontend/src/lib/__tests__/fundCategoryCurve.test.ts
git commit -m "feat(funds): add fundCategoryCurve rebase primitive"
```

---

## Task 2: Span and trailing returns with the CAGR gate

Absolute return under one year, CAGR at and above it, on actual day count — the financial-domain rule. Getting this wrong makes every number in the returns table wrong.

**Files:**
- Modify: `frontend/src/lib/fundCategoryCurve.ts`
- Modify: `frontend/src/lib/__tests__/fundCategoryCurve.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/__tests__/fundCategoryCurve.test.ts`:

```ts
import { spanReturn, trailingReturn, PERIODS } from '../fundCategoryCurve'

// REAL month-end NAVs for ICICI Pru FMCG Gr (mstar F0GBR06S3I), 2023-06-30 → 2026-07-31,
// pulled from atlas_foundation.de_mf_nav_daily on 2026-08-04. NO synthetic inputs (rule #0).
// This fund IS the whole "India Fund Sector - FMCG" category (1 of 1 with NAV), so its
// rebased NAV series is by definition that category's composite — which is exactly what
// the single-fund identity test in Task 5 asserts. The window is a real losing stretch
// (−4.8% over three years), so it exercises negative returns and negative CAGR.
const FMCG: CurvePoint[] = [
  { d: '2023-06-30', v: 438.57 }, { d: '2023-07-31', v: 449.35 }, { d: '2023-08-31', v: 440.41 },
  { d: '2023-09-29', v: 442.95 }, { d: '2023-10-31', v: 438.29 }, { d: '2023-11-30', v: 450.01 },
  { d: '2023-12-29', v: 472.96 }, { d: '2024-01-31', v: 456.96 }, { d: '2024-02-29', v: 449.04 },
  { d: '2024-03-31', v: 452.09 }, { d: '2024-04-30', v: 454.98 }, { d: '2024-05-31', v: 459.65 },
  { d: '2024-06-28', v: 481.94 }, { d: '2024-07-31', v: 520.97 }, { d: '2024-08-30', v: 531.92 },
  { d: '2024-09-30', v: 548.94 }, { d: '2024-10-31', v: 500.94 }, { d: '2024-11-29', v: 488.55 },
  { d: '2024-12-31', v: 476.21 }, { d: '2025-01-31', v: 480.25 }, { d: '2025-02-28', v: 437.20 },
  { d: '2025-03-31', v: 454.31 }, { d: '2025-04-30', v: 475.89 }, { d: '2025-05-30', v: 476.58 },
  { d: '2025-06-30', v: 477.95 }, { d: '2025-07-31', v: 480.09 }, { d: '2025-08-29', v: 484.34 },
  { d: '2025-09-30', v: 472.46 }, { d: '2025-10-31', v: 482.81 }, { d: '2025-11-28', v: 475.52 },
  { d: '2025-12-31', v: 471.16 }, { d: '2026-01-30', v: 437.43 }, { d: '2026-02-27', v: 439.49 },
  { d: '2026-03-31', v: 389.87 }, { d: '2026-04-30', v: 429.93 }, { d: '2026-05-29', v: 416.72 },
  { d: '2026-06-30', v: 413.55 }, { d: '2026-07-31', v: 417.52 },
]

describe('spanReturn', () => {
  it('annualises a span longer than a year on actual day count', () => {
    const r = spanReturn(FMCG)!
    expect(r.days).toBe(1127)          // 2023-06-30 → 2026-07-31
    expect(r.annualised).toBe(true)
    expect(r.pct).toBeCloseTo(-1.581500, 4)  // (417.52/438.57)^(365.25/1127) − 1
  })

  it('returns absolute return for a span of a year or less', () => {
    const r = spanReturn(FMCG.slice(-13))! // 2025-07-31 → 2026-07-31, 365 days
    expect(r.days).toBe(365)
    expect(r.annualised).toBe(false)
    expect(r.pct).toBeCloseTo(-13.032973, 4) // 417.52/480.09 − 1
  })

  it('returns null for a series with fewer than two points', () => {
    expect(spanReturn([])).toBeNull()
    expect(spanReturn([{ d: '2026-07-31', v: 417.52 }])).toBeNull()
  })
})

describe('trailingReturn', () => {
  // Each expectation below is the real answer for this real series. The anchor is the last
  // date minus N calendar months; the start point is the last observation on or before it.
  it.each([
    [1,  31,   false, 0.959981],
    [3,  92,   false, -2.886516],
    [6,  182,  false, -4.551585],   // anchor 2026-01-31 falls on a non-NAV day → uses 2026-01-30
    [12, 365,  false, -13.032973],
    [24, 730,  true,  -10.484269],
    [36, 1096, true,  -2.418699],
  ])('%i-month trailing return spans %i days, annualised=%s', (months, days, ann, pct) => {
    const r = trailingReturn(FMCG, months)!
    expect(r.days).toBe(days)
    expect(r.annualised).toBe(ann)
    expect(r.pct).toBeCloseTo(pct, 4)
  })

  it('returns null when the series is shorter than the requested period', () => {
    // 60 months back from 2026-07-31 is 2021-07-31; the series starts 2023-06-30.
    expect(trailingReturn(FMCG, 60)).toBeNull()
  })

  it('never reports 0 for a period it cannot cover', () => {
    const r = trailingReturn(FMCG, 60)
    expect(r).toBeNull()
    expect(r).not.toEqual({ pct: 0, annualised: false, days: 0 })
  })
})

describe('PERIODS', () => {
  it('lists the seven trailing periods the returns table renders', () => {
    expect(PERIODS.map((p) => p.key)).toEqual(['1m', '3m', '6m', '1y', '2y', '3y', '5y'])
    expect(PERIODS.map((p) => p.months)).toEqual([1, 3, 6, 12, 24, 36, 60])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/lib/__tests__/fundCategoryCurve.test.ts
```

Expected: FAIL — `spanReturn is not a function` (or an import resolution error for the new names).

- [ ] **Step 3: Write the minimal implementation**

Append to `frontend/src/lib/fundCategoryCurve.ts`:

```ts
/** A return over a span. `pct` is a percentage (−1.58 means −1.58%), not a fraction. */
export type SpanReturn = { pct: number; annualised: boolean; days: number }

/** The seven trailing periods the returns table renders. */
export const PERIODS = [
  { key: '1m', label: '1M', months: 1 },
  { key: '3m', label: '3M', months: 3 },
  { key: '6m', label: '6M', months: 6 },
  { key: '1y', label: '1Y', months: 12 },
  { key: '2y', label: '2Y', months: 24 },
  { key: '3y', label: '3Y', months: 36 },
  { key: '5y', label: '5Y', months: 60 },
] as const

const MS_PER_DAY = 24 * 3600 * 1000

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / MS_PER_DAY)
}

/**
 * Return between the first and last point. Absolute at a year or less; CAGR above it,
 * on actual day count — annualising a six-month number would overstate it.
 */
export function spanReturn(pts: CurvePoint[]): SpanReturn | null {
  const a = pts[0]
  const b = pts.at(-1)
  if (a == null || b == null || a === b || a.v <= 0) return null
  const days = daysBetween(a.d, b.d)
  if (days <= 0) return null
  const growth = b.v / a.v
  const annualised = days > 365
  const pct = annualised ? growth ** (365.25 / days) - 1 : growth - 1
  return { pct: pct * 100, annualised, days }
}

/** Subtract whole calendar months, clamping to the shorter month (31 Mar − 1m = 28/29 Feb). */
function minusMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const targetMonth = m - months
  const yy = y + Math.floor((targetMonth - 1) / 12)
  const mm = ((((targetMonth - 1) % 12) + 12) % 12) + 1
  const lastDay = new Date(Date.UTC(yy, mm, 0)).getUTCDate()
  const dd = Math.min(d, lastDay)
  return `${yy}-${String(mm).padStart(2, '0')}-${String(dd).padStart(2, '0')}`
}

/**
 * Trailing return over N calendar months, anchored on the last observation on or before
 * (last date − N months). Returns null — never 0 — when the series does not reach back
 * that far; a missing period must read "—", not "flat".
 */
export function trailingReturn(pts: CurvePoint[], months: number): SpanReturn | null {
  const last = pts.at(-1)
  if (last == null) return null
  const anchor = minusMonths(last.d, months)
  let startIdx = -1
  for (let i = 0; i < pts.length; i++) {
    if (pts[i].d <= anchor) startIdx = i
    else break
  }
  if (startIdx < 0) return null
  return spanReturn([pts[startIdx], last])
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/lib/__tests__/fundCategoryCurve.test.ts
```

Expected: PASS, 14 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/fundCategoryCurve.ts frontend/src/lib/__tests__/fundCategoryCurve.test.ts
git commit -m "feat(funds): span and trailing returns with the CAGR gate"
```

---

## Task 3: Rolling returns and rolling statistics

**Files:**
- Modify: `frontend/src/lib/fundCategoryCurve.ts`
- Modify: `frontend/src/lib/__tests__/fundCategoryCurve.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/__tests__/fundCategoryCurve.test.ts`:

```ts
import { rollingReturns, rollingStats } from '../fundCategoryCurve'

describe('rollingReturns', () => {
  it('produces one window per date that has an observation a full year earlier', () => {
    const roll = rollingReturns(FMCG, 1)
    // 38 month-ends; the first 13 have no point 365 days back, leaving 25 windows.
    expect(roll).toHaveLength(25)
    expect(roll[0].d).toBe('2024-07-31')
    expect(roll[0].v).toBeCloseTo(15.938578, 4)  // 520.97/449.35 − 1, vs 2023-07-31
    expect(roll.at(-1)!.d).toBe('2026-07-31')
    expect(roll.at(-1)!.v).toBeCloseTo(-13.032973, 4) // 417.52/480.09 − 1, vs 2025-07-31
  })

  it('agrees with trailingReturn on the final window', () => {
    expect(rollingReturns(FMCG, 1).at(-1)!.v).toBeCloseTo(trailingReturn(FMCG, 12)!.pct, 6)
  })

  it('returns an empty array when the series is shorter than the window', () => {
    expect(rollingReturns(FMCG.slice(-6), 1)).toEqual([])
  })

  it('anchors on calendar months, never shortening the window', () => {
    // 2025-02-28 minus 12 months is 2025-02-28 → 2024-02-28, but the only nearby observation
    // is 2024-02-29, which is *after* the anchor. Falling back to 2024-01-31 gives a 13-month
    // window rather than an 11-month one. Erring long is deliberate: a window shorter than the
    // one requested would understate the return and quietly mislabel it.
    const w = rollingReturns(FMCG, 1).find((p) => p.d === '2025-02-28')!
    expect(w.v).toBeCloseTo(-4.324230, 4) // 437.20/456.96 − 1, vs 2024-01-31
  })
})

describe('rollingStats', () => {
  it('summarises the distribution of a real rolling-1Y series', () => {
    const s = rollingStats(rollingReturns(FMCG, 1), [])!
    expect(s.n).toBe(25)
    expect(s.min).toBeCloseTo(-14.184147, 4)
    expect(s.p25).toBeCloseTo(-8.487246, 4)
    expect(s.median).toBeCloseTo(-3.619196, 4)
    expect(s.p75).toBeCloseTo(4.747461, 4)
    expect(s.max).toBeCloseTo(23.928209, 4)
  })

  it('reports beatRate as null when there is no benchmark to compare against', () => {
    expect(rollingStats(rollingReturns(FMCG, 1), [])!.beatRate).toBeNull()
  })

  it('counts the share of dates where the composite beat the benchmark', () => {
    const comp = rollingReturns(FMCG, 1)
    // Compare the series against itself shifted: identical series never beats itself.
    expect(rollingStats(comp, comp)!.beatRate).toBe(0)
    const worse = comp.map((p) => ({ d: p.d, v: p.v - 1 }))
    expect(rollingStats(comp, worse)!.beatRate).toBe(100)
  })

  it('returns null for an empty series', () => {
    expect(rollingStats([], [])).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/lib/__tests__/fundCategoryCurve.test.ts
```

Expected: FAIL — `rollingReturns is not a function`.

- [ ] **Step 3: Write the minimal implementation**

Append to `frontend/src/lib/fundCategoryCurve.ts`:

```ts
/**
 * Rolling return through time: for each date, the return since the last observation on or
 * before (date − N years). Windows are calendar-anchored, so a 1Y window means a year,
 * not "250 rows back" — trading-day counts drift and a row-count window silently isn't
 * a year any more once a series has gaps. Values are percentages.
 */
export function rollingReturns(pts: CurvePoint[], years: number): CurvePoint[] {
  const out: CurvePoint[] = []
  let start = 0
  for (const p of pts) {
    const anchor = minusMonths(p.d, years * 12)
    while (start + 1 < pts.length && pts[start + 1].d <= anchor) start++
    const from = pts[start]
    if (from.d > anchor || from.v <= 0 || from === p) continue
    out.push({ d: p.d, v: (p.v / from.v - 1) * 100 })
  }
  return out
}

export type RollingStats = {
  n: number
  min: number
  p25: number
  median: number
  p75: number
  max: number
  /** % of dates where the composite beat the benchmark, or null with no benchmark. */
  beatRate: number | null
}

/** Linear-interpolated percentile over a sorted array. */
function percentile(sorted: number[], p: number): number {
  const k = (sorted.length - 1) * p
  const lo = Math.floor(k)
  const hi = Math.min(lo + 1, sorted.length - 1)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (k - lo)
}

/** Distribution of a rolling series, plus how often it beat a benchmark on matching dates. */
export function rollingStats(comp: CurvePoint[], bench: CurvePoint[]): RollingStats | null {
  if (comp.length === 0) return null
  const sorted = comp.map((p) => p.v).sort((a, b) => a - b)
  const byDate = new Map(bench.map((p) => [p.d, p.v]))
  const paired = comp.filter((p) => byDate.has(p.d))
  return {
    n: comp.length,
    min: sorted[0],
    p25: percentile(sorted, 0.25),
    median: percentile(sorted, 0.5),
    p75: percentile(sorted, 0.75),
    max: sorted[sorted.length - 1],
    beatRate: paired.length === 0
      ? null
      : (100 * paired.filter((p) => p.v > byDate.get(p.d)!).length) / paired.length,
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/lib/__tests__/fundCategoryCurve.test.ts
```

Expected: PASS, 25 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/fundCategoryCurve.ts frontend/src/lib/__tests__/fundCategoryCurve.test.ts
git commit -m "feat(funds): rolling returns and distribution statistics"
```

---

## Task 4: The composite SQL query

**Files:**
- Create: `frontend/src/lib/queries/fund_category_curve.ts`

- [ ] **Step 1: Write the query module**

Create `frontend/src/lib/queries/fund_category_curve.ts`:

```ts
// fund_category_curve — SQL for /funds/compare. This module owns queries and nothing else;
// all arithmetic beyond the chain-link itself lives in lib/fundCategoryCurve.ts.
import sql from '@/lib/db'
import { toNumber, toNumberOr } from '@/lib/decimal'

/**
 * Category → the NSE index that category is measured against. A reference mapping, not a
 * methodology number, so it lives here rather than in atlas_thresholds. Every code below
 * was verified present in atlas_foundation.index_prices with 3,795+ days of history.
 *
 * de_mf_master.primary_benchmark is deliberately NOT used: it holds Morningstar display
 * strings ("Nifty Smallcap 250 TR INR", "BSE 500 India TR INR") that join to nothing we
 * store, and its BSE entries have no series in index_prices at all.
 */
export const CATEGORY_INDEX: Record<string, string> = {
  'India Fund Index Funds': 'NIFTY 500',
  'India Fund Flexi Cap': 'NIFTY 500',
  'India Fund ELSS (Tax Savings)': 'NIFTY 500',
  'India Fund Focused Fund': 'NIFTY 500',
  'India Fund Large-Cap': 'NIFTY 100',
  'India Fund Large & Mid-Cap': 'NIFTY LARGEMID250',
  'India Fund Mid-Cap': 'NIFTY MIDCAP 150',
  'India Fund Small-Cap': 'NIFTY SMLCAP 250',
  'India Fund Multi-Cap': 'NIFTY500 MULTICAP',
  'India Fund Value': 'NIFTY500 VALUE 50',
  'India Fund Equity - Consumption': 'NIFTY CONSUMPTION',
  'India Fund Equity - Infrastructure': 'NIFTY INFRA',
  'India Fund Equity - ESG': 'NIFTY100 ESG',
  'India Fund Sector - Financial Services': 'NIFTY FIN SERVICE',
  'India Fund Sector - Healthcare': 'NIFTY HEALTHCARE',
  'India Fund Sector - Technology': 'NIFTY IT',
  'India Fund Sector - Energy': 'NIFTY ENERGY',
  'India Fund Sector - FMCG': 'NIFTY FMCG',
}

export type CategoryOption = {
  category: string
  /** Funds in the category that have any NAV history — the composite's real population. */
  nFunds: number
  /** Latest NAV date across the category; drives the staleness warning. */
  lastNav: string | null
}

export type CompositeRow = {
  d: string
  /** Chain-linked equal-weighted index, 100 at the first date in range. */
  v: number
  /** Funds contributing a return on this date. 0 on the anchor date by construction. */
  n: number
  nifty50: number | null
  nifty500: number | null
  catIndex: number | null
}

export type ConstituentRow = {
  mstarId: string
  name: string
  first: string
  last: string
  /** Simple return over the fund's own span inside the window, in percent. */
  pct: number
  /** False when the fund entered or exited inside the window. */
  full: boolean
}

/** The categories worth offering, with their real fund count and freshness. */
export async function getCategoryOptions(): Promise<CategoryOption[]> {
  const rows = await sql<{ category: string; n: string; last_nav: string | null }[]>`
    SELECT m.category_name AS category,
           count(DISTINCT m.mstar_id)::text AS n,
           to_char(max(l.last_d), 'YYYY-MM-DD') AS last_nav
    FROM atlas_foundation.de_mf_master m
    JOIN (SELECT mstar_id, max(nav_date) AS last_d
          FROM atlas_foundation.de_mf_nav_daily GROUP BY mstar_id) l USING (mstar_id)
    WHERE m.category_name IS NOT NULL
    GROUP BY m.category_name
    ORDER BY m.category_name`
  return rows.map((r) => ({
    category: r.category,
    nFunds: toNumberOr(r.n, 0),
    lastNav: r.last_nav,
  }))
}

/**
 * The category's equal-weighted composite, chain-linked, plus the three benchmark closes.
 *
 * Chain-linked, not an average of rebased NAVs: 215 funds' NAV histories start in 2026
 * alone, and averaging levels would let a newcomer rebased at 100 drag the whole curve.
 * Averaging daily returns across the funds alive on both ends of each day, then
 * compounding, makes fund entry and exit a non-event.
 *
 * Postgres has no product aggregate, so exp(sum(ln(1+r))) does the compounding. The
 * r > -1 guard keeps ln defined — one NAV collapsing to zero would otherwise abort the
 * whole series. nav > 0 and prev > 0 together mean a missing NAV yields no return for that
 * fund that day rather than a zero return: a data gap must never read as a flat day.
 *
 * Benchmarks join as-of (last close on or before the NAV date), not on equality —
 * index_prices has no row for 2024-03-31, 2025-03-31 or 2026-03-31 while NAVs do, and an
 * equality join would silently drop those points.
 */
export async function getCategoryComposite(
  category: string,
  from: string,
  to: string,
): Promise<CompositeRow[]> {
  const catIndex = CATEGORY_INDEX[category] ?? 'NIFTY 500'
  const rows = await sql<{
    d: string; v: string; n: string
    n50: string | null; n500: string | null; ncat: string | null
  }[]>`
    WITH nav AS (
      SELECT n.mstar_id, n.nav_date, n.nav,
             lag(n.nav) OVER (PARTITION BY n.mstar_id ORDER BY n.nav_date) AS prev
      FROM atlas_foundation.de_mf_nav_daily n
      JOIN atlas_foundation.de_mf_master m USING (mstar_id)
      WHERE m.category_name = ${category}
        AND n.nav_date BETWEEN ${from} AND ${to}
        AND n.nav > 0
    ),
    daily AS (
      SELECT nav_date, avg(nav / prev - 1) AS r, count(*)::int AS n
      FROM nav
      WHERE prev IS NOT NULL AND prev > 0 AND nav / prev - 1 > -1
      GROUP BY nav_date
    ),
    anchored AS (
      SELECT min(nav_date) AS nav_date, 0::numeric AS r, 0 AS n
      FROM nav HAVING min(nav_date) IS NOT NULL
      UNION ALL
      SELECT nav_date, r, n FROM daily
    ),
    comp AS (
      SELECT nav_date, 100 * exp(sum(ln(1 + r)) OVER (ORDER BY nav_date)) AS v, n
      FROM anchored
    )
    SELECT to_char(c.nav_date, 'YYYY-MM-DD') AS d, c.v::text AS v, c.n::text AS n,
           b50.close::text AS n50, b500.close::text AS n500, bcat.close::text AS ncat
    FROM comp c
    LEFT JOIN LATERAL (
      SELECT close FROM atlas_foundation.index_prices
      WHERE index_code = 'NIFTY 50' AND date <= c.nav_date
      ORDER BY date DESC LIMIT 1) b50 ON true
    LEFT JOIN LATERAL (
      SELECT close FROM atlas_foundation.index_prices
      WHERE index_code = 'NIFTY 500' AND date <= c.nav_date
      ORDER BY date DESC LIMIT 1) b500 ON true
    LEFT JOIN LATERAL (
      SELECT close FROM atlas_foundation.index_prices
      WHERE index_code = ${catIndex} AND date <= c.nav_date
      ORDER BY date DESC LIMIT 1) bcat ON true
    ORDER BY c.nav_date`
  return rows.map((r) => ({
    d: r.d,
    v: toNumberOr(r.v, 0),
    n: toNumberOr(r.n, 0),
    nifty50: toNumber(r.n50),
    nifty500: toNumber(r.n500),
    catIndex: toNumber(r.ncat),
  }))
}

/** Every fund in the composite, with its own return over its own span inside the window. */
export async function getCategoryConstituents(
  category: string,
  from: string,
  to: string,
): Promise<ConstituentRow[]> {
  const rows = await sql<{
    mstar_id: string; name: string; first_d: string; last_d: string
    first_nav: string; last_nav: string; window_first: string; window_last: string
  }[]>`
    WITH nav AS (
      SELECT n.mstar_id, n.nav_date, n.nav
      FROM atlas_foundation.de_mf_nav_daily n
      JOIN atlas_foundation.de_mf_master m USING (mstar_id)
      WHERE m.category_name = ${category}
        AND n.nav_date BETWEEN ${from} AND ${to}
        AND n.nav > 0
    ),
    span AS (SELECT min(nav_date) AS w_first, max(nav_date) AS w_last FROM nav),
    ends AS (
      SELECT DISTINCT ON (mstar_id) mstar_id, nav_date AS first_d, nav AS first_nav
      FROM nav ORDER BY mstar_id, nav_date ASC
    ),
    tails AS (
      SELECT DISTINCT ON (mstar_id) mstar_id, nav_date AS last_d, nav AS last_nav
      FROM nav ORDER BY mstar_id, nav_date DESC
    )
    SELECT e.mstar_id, m.fund_name AS name,
           to_char(e.first_d, 'YYYY-MM-DD') AS first_d,
           to_char(t.last_d, 'YYYY-MM-DD') AS last_d,
           e.first_nav::text AS first_nav, t.last_nav::text AS last_nav,
           to_char(s.w_first, 'YYYY-MM-DD') AS window_first,
           to_char(s.w_last, 'YYYY-MM-DD') AS window_last
    FROM ends e
    JOIN tails t USING (mstar_id)
    JOIN atlas_foundation.de_mf_master m ON m.mstar_id = e.mstar_id
    CROSS JOIN span s
    WHERE e.first_d < t.last_d`
  return rows
    .map((r) => ({
      mstarId: r.mstar_id,
      name: r.name,
      first: r.first_d,
      last: r.last_d,
      pct: (toNumberOr(r.last_nav, 0) / toNumberOr(r.first_nav, 1) - 1) * 100,
      full: r.first_d === r.window_first && r.last_d === r.window_last,
    }))
    .sort((a, b) => b.pct - a.pct)
}
```

- [ ] **Step 2: Verify the composite against the live DB by hand**

The composite is the load-bearing calculation. Prove it produces the exact values the Task 1–3 fixtures assert before wiring any UI.

```bash
cd "/Users/nimishshah/All AI/atlas-os" && .venv/bin/python - <<'PY'
import psycopg2
url=[l.split('=',1)[1].strip().strip('"\'') for l in open('.env') if l.startswith('ATLAS_DB_URL')][0]
cur=psycopg2.connect(url).cursor()
SQL="""
WITH nav AS (
  SELECT n.mstar_id, n.nav_date, n.nav,
         lag(n.nav) OVER (PARTITION BY n.mstar_id ORDER BY n.nav_date) AS prev
  FROM atlas_foundation.de_mf_nav_daily n
  JOIN atlas_foundation.de_mf_master m USING (mstar_id)
  WHERE m.category_name=%(cat)s AND n.nav_date BETWEEN %(f)s AND %(t)s AND n.nav>0),
daily AS (SELECT nav_date, avg(nav/prev-1) AS r, count(*)::int AS n FROM nav
  WHERE prev IS NOT NULL AND prev>0 AND nav/prev-1>-1 GROUP BY nav_date),
anchored AS (SELECT min(nav_date) AS nav_date, 0::numeric AS r, 0 AS n FROM nav
  HAVING min(nav_date) IS NOT NULL UNION ALL SELECT nav_date,r,n FROM daily)
SELECT to_char(nav_date,'YYYY-MM-DD'),
       round(100*exp(sum(ln(1+r)) OVER (ORDER BY nav_date))::numeric,6), n
FROM anchored ORDER BY nav_date"""
cur.execute(SQL, dict(cat='India Fund Sector - Energy', f='2026-03-30', t='2026-04-07'))
for r in cur.fetchall(): print(r)
PY
```

Expected, exactly:

```
('2026-03-30', Decimal('100.000000'), 0)
('2026-03-31', Decimal('99.995804'), 4)
('2026-04-01', Decimal('101.772909'), 3)
('2026-04-02', Decimal('102.067793'), 5)
('2026-04-06', Decimal('102.120648'), 4)
('2026-04-07', Decimal('102.398542'), 4)
```

These are the values hard-coded as `ENERGY` in the Task 1 test. If they differ, the SQL was mistyped — fix the SQL, not the fixture.

- [ ] **Step 3: Check the query plan and decide on performance**

```bash
cd "/Users/nimishshah/All AI/atlas-os" && .venv/bin/python - <<'PY'
import psycopg2, time
url=[l.split('=',1)[1].strip().strip('"\'') for l in open('.env') if l.startswith('ATLAS_DB_URL')][0]
cur=psycopg2.connect(url).cursor()
cur.execute("""EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT n.mstar_id, n.nav_date, n.nav,
       lag(n.nav) OVER (PARTITION BY n.mstar_id ORDER BY n.nav_date)
FROM atlas_foundation.de_mf_nav_daily n
JOIN atlas_foundation.de_mf_master m USING (mstar_id)
WHERE m.category_name='India Fund Index Funds'
  AND n.nav_date BETWEEN '2023-08-04' AND '2026-12-31' AND n.nav>0""")
for r in cur.fetchall(): print(r[0])
PY
```

Baseline measured on 2026-08-04 over the `aws-1-` pooler: Index Funds 3y ≈ 2.8s warm, 8.2s cold; 1y ≈ 0.64s. Decision gate:

- If the plan shows a **sequential scan** on `de_mf_nav_daily`, that is the cost. The fix is to help the planner use `ix_de_mf_nav_daily_mstar_id_nav_date` by resolving the category to an explicit id list first: run a cheap `SELECT mstar_id FROM de_mf_master WHERE category_name = $1`, then pass `WHERE n.mstar_id = ANY($ids)`. Re-time.
- If it already uses the index and is still slow, leave it and set `export const revalidate = 3600` on the page so the cost is paid once an hour per category.
- Do **not** move the aggregation into TypeScript, and do **not** add a materialized view in this task.

Record the plan output and the timing in the commit message.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queries/fund_category_curve.ts
git commit -m "feat(funds): chain-linked category composite query"
```

---

## Task 5: Integration test for the composite

Locks the SQL against regression. Skips cleanly in CI where there is no DB.

**Files:**
- Create: `frontend/src/lib/queries/__tests__/fund_category_curve.int.test.ts`

- [ ] **Step 1: Write the test**

Create `frontend/src/lib/queries/__tests__/fund_category_curve.int.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { getCategoryComposite, getCategoryOptions, CATEGORY_INDEX } from '../fund_category_curve'

// Integration test — hits the real atlas_foundation. Runs on the laptop (point ATLAS_DB_URL
// at the aws-1- pooler); skipped in CI where there is no DB. Per rule #0 every expected
// value below is real produced output, verified 2026-08-04.
const hasDb = Boolean(process.env.ATLAS_DB_URL)

describe.skipIf(!hasDb)('getCategoryComposite', () => {
  it('reproduces the real Energy composite across a gap, an exit and a partial day', async () => {
    const rows = await getCategoryComposite('India Fund Sector - Energy', '2026-03-30', '2026-04-07')
    expect(rows.map((r) => [r.d, Number(r.v.toFixed(6)), r.n])).toEqual([
      ['2026-03-30', 100.000000, 0],
      ['2026-03-31', 99.995804, 4],  // SBI Energy has no 03-30 NAV → contributes no return
      ['2026-04-01', 101.772909, 3], // two funds missing entirely — a real gap
      ['2026-04-02', 102.067793, 5],
      ['2026-04-06', 102.120648, 4], // Groww BSE Power FOF stopped reporting
      ['2026-04-07', 102.398542, 4],
    ])
  })

  it('does not step the curve when a fund enters mid-window', async () => {
    // Groww BSE Power ETF FOF (F00001RXVU) reports its first NAV on 2025-08-08. That day it
    // must contribute NOTHING — it has no previous NAV, so it has no return — and the count
    // must stay at 4. It joins the average from 2025-08-11, taking the count to 5. If a new
    // fund's arrival ever moves the composite, the aggregation is averaging levels, not returns.
    const rows = await getCategoryComposite('India Fund Sector - Energy', '2025-08-05', '2025-08-13')
    expect(rows.map((r) => [r.d, Number(r.v.toFixed(6)), r.n])).toEqual([
      ['2025-08-05', 100.000000, 0],
      ['2025-08-06', 99.514021, 4],
      ['2025-08-07', 99.419794, 4],
      ['2025-08-08', 99.357428, 4], // Groww's first NAV — no return, no effect
      ['2025-08-11', 99.859997, 5], // now contributing
      ['2025-08-12', 100.255663, 5],
      ['2025-08-13', 100.293999, 5],
    ])
  })

  it('equals the fund itself when the category holds exactly one fund', async () => {
    // "India Fund Sector - FMCG" is ICICI Pru FMCG Gr alone, so the composite must be that
    // fund's own rebased NAV: 100 × 413.69 / 407.80 = 101.444335 on 2026-06-10.
    const rows = await getCategoryComposite('India Fund Sector - FMCG', '2026-06-01', '2026-06-10')
    expect(rows[0]).toMatchObject({ d: '2026-06-01', n: 0 })
    expect(rows[0].v).toBeCloseTo(100, 9)
    expect(rows.at(-1)!.d).toBe('2026-06-10')
    expect(rows.at(-1)!.v).toBeCloseTo(101.444335, 5)
    expect(rows.every((r) => r.n <= 1)).toBe(true)
  })

  it('fills benchmark closes on dates the index did not trade', async () => {
    // index_prices has no NIFTY FMCG row for 2026-03-31, but the fund has a NAV. The as-of
    // join must supply the 2026-03-30 close of 45538.65 rather than leaving a hole.
    const rows = await getCategoryComposite('India Fund Sector - FMCG', '2026-03-31', '2026-03-31')
    expect(rows).toHaveLength(1)
    expect(rows[0].catIndex).toBeCloseTo(45538.65, 2)
  })

  it('returns an empty array for a range with no NAV data', async () => {
    expect(await getCategoryComposite('India Fund Sector - FMCG', '1990-01-01', '1990-01-31')).toEqual([])
  })
})

describe.skipIf(!hasDb)('getCategoryOptions', () => {
  it('returns a benchmark mapping for every category that has NAV data', async () => {
    const opts = await getCategoryOptions()
    expect(opts.length).toBeGreaterThanOrEqual(18)
    for (const o of opts) expect(CATEGORY_INDEX[o.category]).toBeDefined()
  })

  it('surfaces the stale categories rather than hiding them', async () => {
    const opts = await getCategoryOptions()
    const idx = opts.find((o) => o.category === 'India Fund Index Funds')!
    expect(idx.nFunds).toBeGreaterThan(200)
    expect(idx.lastNav! < '2026-06-01').toBe(true) // feed died 2026-05-15
  })
})
```

- [ ] **Step 2: Run the test with a DB and verify it passes**

```bash
cd frontend && npx vitest run src/lib/queries/__tests__/fund_category_curve.int.test.ts
```

Expected: PASS, 7 tests. If `ATLAS_DB_URL` is unset the suite reports 7 skipped — that is the CI path, not a pass.

- [ ] **Step 3: Verify it skips without a DB**

```bash
cd frontend && env -u ATLAS_DB_URL npx vitest run src/lib/queries/__tests__/fund_category_curve.int.test.ts
```

Expected: 7 skipped, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queries/__tests__/fund_category_curve.int.test.ts
git commit -m "test(funds): integration cover for the category composite SQL"
```

---

## Task 6: The controls

**Files:**
- Create: `frontend/src/components/funds/CategoryCompareControls.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/funds/CategoryCompareControls.tsx`:

```tsx
'use client'
// Controls for /funds/compare. State lives in the URL, so the server component re-renders
// and the page is shareable and printable as-is. Native select and date inputs — no
// picker dependency, and the browser gets keyboard and mobile behaviour right for free.
import { useRouter, useSearchParams } from 'next/navigation'
import type { CategoryOption } from '@/lib/queries/fund_category_curve'

const PERIOD_OPTIONS = [
  { v: '1m', l: '1 month' }, { v: '3m', l: '3 months' }, { v: '6m', l: '6 months' },
  { v: '1y', l: '1 year' }, { v: '2y', l: '2 years' }, { v: '3y', l: '3 years' },
  { v: '5y', l: '5 years' }, { v: 'max', l: 'Max' }, { v: 'custom', l: 'Custom range' },
]

const cleanCat = (c: string): string =>
  c.replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || c

const label = 'font-num text-[9px] uppercase tracking-[0.14em] text-txt-3'
const field =
  'rounded-tile border border-edge-hair bg-surface-panel px-2.5 py-1.5 font-sans text-[13px] text-txt-1'

export function CategoryCompareControls({ options }: { options: CategoryOption[] }) {
  const router = useRouter()
  const params = useSearchParams()

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    router.push(`/funds/compare?${next}`)
  }

  const period = params.get('period') ?? '3y'
  const view = params.get('view') ?? 'growth'

  return (
    <div className="print:hidden flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <label className={label} htmlFor="cat">Category</label>
        <select id="cat" className={`${field} min-w-[280px]`}
                value={params.get('cat') ?? 'India Fund Flexi Cap'}
                onChange={(e) => set('cat', e.target.value)}>
          {options.map((o) => (
            <option key={o.category} value={o.category}>
              {cleanCat(o.category)} · {o.nFunds} funds
              {o.lastNav && o.lastNav < '2026-07-01' ? ` · stale to ${o.lastNav}` : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className={label} htmlFor="period">Period</label>
        <select id="period" className={field} value={period}
                onChange={(e) => set('period', e.target.value)}>
          {PERIOD_OPTIONS.map((p) => <option key={p.v} value={p.v}>{p.l}</option>)}
        </select>
      </div>

      {period === 'custom' && (
        <>
          <div className="flex flex-col gap-1">
            <label className={label} htmlFor="from">From</label>
            <input id="from" type="date" className={field} value={params.get('from') ?? ''}
                   onChange={(e) => set('from', e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label className={label} htmlFor="to">To</label>
            <input id="to" type="date" className={field} value={params.get('to') ?? ''}
                   onChange={(e) => set('to', e.target.value)} />
          </div>
        </>
      )}

      <div className="flex flex-col gap-1">
        <label className={label} htmlFor="view">View</label>
        <select id="view" className={field} value={view}
                onChange={(e) => set('view', e.target.value)}>
          <option value="growth">Growth of ₹100</option>
          <option value="rolling">Rolling returns</option>
        </select>
      </div>

      {view === 'rolling' && (
        <div className="flex flex-col gap-1">
          <label className={label} htmlFor="window">Rolling window</label>
          <select id="window" className={field} value={params.get('window') ?? '3y'}
                  onChange={(e) => set('window', e.target.value)}>
            <option value="1y">1 year</option>
            <option value="3y">3 years</option>
            <option value="5y">5 years</option>
          </select>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep CategoryCompareControls
```

Expected: no output (no errors in this file).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/funds/CategoryCompareControls.tsx
git commit -m "feat(funds): URL-driven controls for the category compare page"
```

---

## Task 7: The chart

**Files:**
- Create: `frontend/src/components/funds/CategoryCompareChart.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/funds/CategoryCompareChart.tsx`:

```tsx
// The compare page's two chart modes. Growth: composite vs three benchmarks, all rebased to
// 100 at the window start so the lines share an origin. Rolling: the composite's rolling
// return through time against the category index's. A count strip under either shows how
// many funds were in the composite on each date — coverage changes, and a curve built from
// three funds should not look like one built from ninety.
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '@/components/ui/Panel'
import { rebase, rollingReturns, type CurvePoint } from '@/lib/fundCategoryCurve'
import type { CompositeRow } from '@/lib/queries/fund_category_curve'

const pick = (rows: CompositeRow[], key: 'nifty50' | 'nifty500' | 'catIndex'): CurvePoint[] =>
  rows.filter((r) => r[key] != null).map((r) => ({ d: r.d, v: r[key] as number }))

const toChart = (pts: CurvePoint[]) => pts.map((p) => ({ time: p.d, value: p.v }))

export function CategoryCompareChart({
  rows, view, windowYears, categoryLabel, indexLabel,
}: {
  rows: CompositeRow[]
  view: 'growth' | 'rolling'
  windowYears: number
  categoryLabel: string
  indexLabel: string
}) {
  const composite: CurvePoint[] = rows.map((r) => ({ d: r.d, v: r.v }))
  const catIdx = pick(rows, 'catIndex')

  const series: ChartSeries[] = view === 'rolling'
    ? [
        { name: `${categoryLabel} rolling ${windowYears}Y`,
          data: toChart(rollingReturns(composite, windowYears)), color: 'teal', lineWidth: 2 },
        { name: `${indexLabel} rolling ${windowYears}Y`,
          data: toChart(rollingReturns(rebase(catIdx), windowYears)), color: 'warn', lineWidth: 2 },
      ]
    : [
        { name: `${categoryLabel} composite`, data: toChart(composite), color: 'teal', lineWidth: 2 },
        { name: indexLabel, data: toChart(rebase(catIdx)), color: 'warn', lineWidth: 1 },
        { name: 'Nifty 500', data: toChart(rebase(pick(rows, 'nifty500'))), color: 'pos', lineWidth: 1 },
        { name: 'Nifty 50', data: toChart(rebase(pick(rows, 'nifty50'))), color: 'ink', lineWidth: 1 },
      ]

  const counts: ChartSeries[] = [{
    name: 'Funds in composite',
    data: rows.slice(1).map((r) => ({ time: r.d, value: r.n })),
    color: 'ink',
    lineWidth: 1,
  }]

  return (
    <Panel
      eyebrow={view === 'rolling' ? `Rolling ${windowYears}-year returns` : 'Growth of ₹100'}
      title={view === 'rolling'
        ? `${categoryLabel} rolling returns vs ${indexLabel}`
        : `${categoryLabel} equal-weighted composite vs benchmarks`}
      info={{
        title: 'How this curve is built',
        body: (
          <>Each day we average the daily return of every fund in the category that reported a NAV
          on both that day and the previous one, then compound those averages. Funds entering or
          leaving the category do not step the curve. Benchmarks are price-return indices and
          exclude dividends, so the composite is flattered by roughly 1–1.5% a year.</>
        ),
      }}
      bodyClassName="break-inside-avoid"
    >
      <AtlasLightweightChart
        series={series}
        height={360}
        yLabel={view === 'rolling' ? 'Return %' : 'Index (start = 100)'}
        precision={1}
      />
      <div className="mt-3 border-t border-edge-hair pt-3">
        <p className="mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          Funds in the composite
        </p>
        <AtlasLightweightChart series={counts} height={72} precision={0} compact />
      </div>
    </Panel>
  )
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep CategoryCompareChart
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/funds/CategoryCompareChart.tsx
git commit -m "feat(funds): growth and rolling charts with a coverage strip"
```

---

## Task 8: The three tables

**Files:**
- Create: `frontend/src/components/funds/CategoryCompareTables.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/funds/CategoryCompareTables.tsx`:

```tsx
// The three tables on /funds/compare: trailing returns, rolling-return distribution, and the
// constituent funds. All formatting, no arithmetic — every number comes from
// lib/fundCategoryCurve.ts so there is one place where the maths can be wrong.
import Link from 'next/link'
import { Panel } from '@/components/ui/Panel'
import {
  PERIODS, rebase, rollingReturns, rollingStats, trailingReturn,
  type CurvePoint, type SpanReturn,
} from '@/lib/fundCategoryCurve'
import type { CompositeRow, ConstituentRow } from '@/lib/queries/fund_category_curve'

const pct = (v: number | null | undefined): string =>
  v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`

const tone = (v: number | null | undefined): string =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const num = 'px-3 py-1.5 text-right font-num text-[12px] tabular-nums'
const txt = 'px-3 py-1.5 text-left font-sans text-[12px]'
const head = 'px-3 py-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3'

const pick = (rows: CompositeRow[], key: 'nifty50' | 'nifty500' | 'catIndex'): CurvePoint[] =>
  rows.filter((r) => r[key] != null).map((r) => ({ d: r.d, v: r[key] as number }))

function ReturnCell({ r }: { r: SpanReturn | null }) {
  return (
    <td className={`${num} ${tone(r?.pct)}`} title={r ? `${r.days} days` : 'insufficient history'}>
      {pct(r?.pct)}
      {r?.annualised && <span className="ml-1 text-[9px] text-txt-3">p.a.</span>}
    </td>
  )
}

export function ReturnsTable({
  rows, categoryLabel, indexLabel,
}: { rows: CompositeRow[]; categoryLabel: string; indexLabel: string }) {
  const series: { label: string; pts: CurvePoint[] }[] = [
    { label: `${categoryLabel} composite`, pts: rows.map((r) => ({ d: r.d, v: r.v })) },
    { label: indexLabel, pts: pick(rows, 'catIndex') },
    { label: 'Nifty 500', pts: pick(rows, 'nifty500') },
    { label: 'Nifty 50', pts: pick(rows, 'nifty50') },
  ]

  return (
    <Panel eyebrow="Trailing returns" title="Composite vs benchmarks"
           bodyClassName="overflow-x-auto break-inside-avoid p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Series</th>
            {PERIODS.map((p) => <th key={p.key} className={`${head} text-right`}>{p.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.label} className="border-b border-edge-hair last:border-0">
              <td className={`${txt} text-txt-1`}>{s.label}</td>
              {PERIODS.map((p) => (
                <ReturnCell key={p.key} r={trailingReturn(s.pts, p.months)} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-3">
        Absolute return up to one year; CAGR on actual day count beyond it (marked p.a.).
        A dash means the series does not reach back that far — never a zero.
        Benchmarks are price-return and exclude dividends.
      </p>
    </Panel>
  )
}

export function RollingStatsTable({
  rows, windowYears, categoryLabel, indexLabel,
}: { rows: CompositeRow[]; windowYears: number; categoryLabel: string; indexLabel: string }) {
  const comp = rollingReturns(rows.map((r) => ({ d: r.d, v: r.v })), windowYears)
  const bench = rollingReturns(rebase(pick(rows, 'catIndex')), windowYears)
  const cs = rollingStats(comp, bench)
  const bs = rollingStats(bench, [])

  if (!cs) {
    return (
      <Panel eyebrow={`Rolling ${windowYears}-year returns`} title="Distribution">
        <p className="font-sans text-[13px] text-txt-2">
          The selected window is shorter than {windowYears} year{windowYears > 1 ? 's' : ''},
          so there are no rolling windows to summarise.
        </p>
      </Panel>
    )
  }

  const cols: [string, number | null][] = [
    ['Worst', cs.min], ['25th', cs.p25], ['Median', cs.median],
    ['75th', cs.p75], ['Best', cs.max],
  ]
  const bcols: [string, number | null][] = bs
    ? [['Worst', bs.min], ['25th', bs.p25], ['Median', bs.median], ['75th', bs.p75], ['Best', bs.max]]
    : []

  return (
    <Panel eyebrow={`Rolling ${windowYears}-year returns`}
           title={`Distribution across ${cs.n} windows`}
           bodyClassName="overflow-x-auto break-inside-avoid p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Series</th>
            {cols.map(([l]) => <th key={l} className={`${head} text-right`}>{l}</th>)}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-edge-hair">
            <td className={`${txt} text-txt-1`}>{categoryLabel} composite</td>
            {cols.map(([l, v]) => <td key={l} className={`${num} ${tone(v)}`}>{pct(v)}</td>)}
          </tr>
          {bcols.length > 0 && (
            <tr>
              <td className={`${txt} text-txt-1`}>{indexLabel}</td>
              {bcols.map(([l, v]) => <td key={l} className={`${num} ${tone(v)}`}>{pct(v)}</td>)}
            </tr>
          )}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-2">
        {cs.beatRate == null
          ? `No overlapping ${indexLabel} history to compare against.`
          : `The composite beat ${indexLabel} in ${cs.beatRate.toFixed(0)}% of the ${cs.n} rolling ${windowYears}-year windows.`}
      </p>
    </Panel>
  )
}

export function ConstituentsTable({
  funds, from, to,
}: { funds: ConstituentRow[]; from: string; to: string }) {
  const partial = funds.filter((f) => !f.full).length
  return (
    <Panel eyebrow="Constituents"
           title={`${funds.length} funds in the composite`}
           bodyClassName="overflow-x-auto break-inside-avoid p-0">
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Fund</th>
            <th className={`${head} text-left`}>From</th>
            <th className={`${head} text-left`}>To</th>
            <th className={`${head} text-right`}>Return</th>
          </tr>
        </thead>
        <tbody>
          {funds.map((f) => (
            <tr key={f.mstarId} className="border-b border-edge-hair last:border-0">
              <td className={txt}>
                <Link href={`/funds/${f.mstarId}`} className="text-txt-1 no-underline hover:text-brand">
                  {f.name}
                </Link>
                {!f.full && (
                  <span className="ml-2 font-num text-[9px] uppercase tracking-wider text-txt-3">
                    partial
                  </span>
                )}
              </td>
              <td className={`${txt} text-txt-2`}>{f.first}</td>
              <td className={`${txt} text-txt-2`}>{f.last}</td>
              <td className={`${num} ${tone(f.pct)}`}>{pct(f.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 font-sans text-[11px] text-txt-3">
        Returns are each fund&apos;s own span inside {from} → {to}, so they are not comparable
        across funds with different spans.
        {partial > 0 && ` ${partial} fund${partial > 1 ? 's' : ''} covered only part of the window.`}
      </p>
    </Panel>
  )
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep CategoryCompareTables
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/funds/CategoryCompareTables.tsx
git commit -m "feat(funds): returns, rolling-distribution and constituents tables"
```

---

## Task 9: The page shell

**Files:**
- Create: `frontend/src/app/funds/compare/page.tsx`

- [ ] **Step 1: Write the page**

Create `frontend/src/app/funds/compare/page.tsx`:

```tsx
// /funds/compare — equal-weighted category composite vs benchmarks. Everything the reader
// needs to distrust the numbers appropriately is on the page: the fund count, the last NAV
// date, the price-return mismatch and the survivorship bias.
export const revalidate = 3600

import { Suspense } from 'react'
import { PrintButton } from '@/components/maal/PrintButton'
import { CategoryCompareControls } from '@/components/funds/CategoryCompareControls'
import { CategoryCompareChart } from '@/components/funds/CategoryCompareChart'
import {
  ConstituentsTable, ReturnsTable, RollingStatsTable,
} from '@/components/funds/CategoryCompareTables'
import {
  CATEGORY_INDEX, getCategoryComposite, getCategoryConstituents, getCategoryOptions,
} from '@/lib/queries/fund_category_curve'

const PERIOD_MONTHS: Record<string, number | null> = {
  '1m': 1, '3m': 3, '6m': 6, '1y': 12, '2y': 24, '3y': 36, '5y': 60, max: null,
}

const cleanCat = (c: string): string =>
  c.replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || c

const isoDaysAgo = (from: string, months: number): string => {
  const d = new Date(`${from}T00:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() - months)
  return d.toISOString().slice(0, 10)
}

export default async function ComparePage({
  searchParams,
}: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams
  const one = (k: string): string | undefined =>
    Array.isArray(sp[k]) ? (sp[k] as string[])[0] : (sp[k] as string | undefined)

  const options = await getCategoryOptions()
  const requested = one('cat')
  const chosen = options.find((o) => o.category === requested)
    ?? options.find((o) => o.category === 'India Fund Flexi Cap')
    ?? options[0]

  if (!chosen) {
    return <main className="report-page mx-auto max-w-[1180px] px-6 py-8">
      <p className="font-sans text-[14px] text-txt-2">No fund categories carry NAV history.</p>
    </main>
  }

  const period = one('period') ?? '3y'
  const view = one('view') === 'rolling' ? 'rolling' : 'growth'
  const windowYears = ({ '1y': 1, '3y': 3, '5y': 5 } as const)[one('window') ?? '3y'] ?? 3

  const to = period === 'custom' ? (one('to') ?? chosen.lastNav ?? '2026-12-31')
                                 : (chosen.lastNav ?? '2026-12-31')
  const months = PERIOD_MONTHS[period]
  const from = period === 'custom'
    ? (one('from') ?? '2000-01-01')
    : months == null ? '2000-01-01' : isoDaysAgo(to, months)

  const [rows, funds] = await Promise.all([
    getCategoryComposite(chosen.category, from, to),
    getCategoryConstituents(chosen.category, from, to),
  ])

  const label = cleanCat(chosen.category)
  const indexLabel = CATEGORY_INDEX[chosen.category] ?? 'NIFTY 500'
  const stale = chosen.lastNav != null && chosen.lastNav < isoDaysAgo('2026-08-04', 1)

  return (
    <main className="report-page mx-auto max-w-[1180px] px-6 py-8">
      <header className="mb-6">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          Funds · Category vs benchmark
        </p>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="font-display text-[26px] font-medium tracking-tight text-txt-1">
            {label} — equal-weighted composite
          </h1>
          <div className="print:hidden"><PrintButton /></div>
        </div>
        <p className="mt-1 font-sans text-[13px] text-txt-2">
          {funds.length} of {chosen.nFunds} funds with NAV history contributed over{' '}
          {from} → {to}. Composite as of {rows.at(-1)?.d ?? '—'}.
        </p>
        {stale && (
          <p className="mt-2 rounded-tile border border-sig-neg/40 bg-sig-neg/10 px-3 py-2 font-sans text-[12px] text-txt-1">
            This category&apos;s NAV feed stopped on {chosen.lastNav}. The curve below ends there
            and is not current.
          </p>
        )}
      </header>

      <div className="mb-6">
        <Suspense fallback={null}>
          <CategoryCompareControls options={options} />
        </Suspense>
      </div>

      {rows.length < 2 ? (
        <p className="font-sans text-[14px] text-txt-2">
          No NAV data for {label} between {from} and {to}.
        </p>
      ) : (
        <div className="flex flex-col gap-6">
          <CategoryCompareChart rows={rows} view={view} windowYears={windowYears}
                                categoryLabel={label} indexLabel={indexLabel} />
          <ReturnsTable rows={rows} categoryLabel={label} indexLabel={indexLabel} />
          <RollingStatsTable rows={rows} windowYears={windowYears}
                             categoryLabel={label} indexLabel={indexLabel} />
          <ConstituentsTable funds={funds} from={from} to={to} />
        </div>
      )}

      <footer className="mt-8 border-t border-edge-hair pt-4 font-sans text-[11px] leading-relaxed text-txt-3">
        <p className="mb-1.5">
          <strong className="text-txt-2">Sources.</strong> Fund NAVs from
          atlas_foundation.de_mf_nav_daily (AMFI / Morningstar). Index levels from
          atlas_foundation.index_prices (NSE). Composite computed as a chain-linked
          equal-weighted daily return series.
        </p>
        <p className="mb-1.5">
          <strong className="text-txt-2">Benchmarks exclude dividends.</strong> Every index here is
          price-return; fund NAVs are total-return. The composite is therefore flattered by roughly
          1–1.5% a year against these benchmarks.
        </p>
        <p>
          <strong className="text-txt-2">Survivorship bias.</strong> Our fund master carries live
          funds only — schemes that closed or merged are absent from the source data entirely. The
          composite therefore omits the losers that disappeared and reads better than the category
          truly performed.
        </p>
      </footer>
    </main>
  )
}
```

- [ ] **Step 2: Verify it compiles and stays inside the page-shell limit**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep "funds/compare"
wc -l src/app/funds/compare/page.tsx
```

Expected: no tsc output; line count at or under 250. If it exceeds 250, lift the header block into `CategoryCompareHeader.tsx` rather than adding an `allow-large` pragma.

- [ ] **Step 3: Render the page against real data**

```bash
cd frontend && npm run dev
```

Then open each of these and confirm what is listed:

| URL | Confirm |
|---|---|
| `http://localhost:3000/funds/compare` | Flexi Cap, 3y, four lines, no stale banner |
| `?cat=India+Fund+Sector+-+FMCG&period=3y` | composite is a single fund; count strip flat at 1 |
| `?cat=India+Fund+Index+Funds&period=1y` | **red stale banner naming 2026-05-15** |
| `?cat=India+Fund+Sector+-+Energy&period=1y` | count strip steps as funds enter |
| `?period=custom&from=2024-01-01&to=2024-12-31` | both date inputs appear and drive the window |
| `?view=rolling&window=1y` | rolling chart plus a populated distribution table |
| `?cat=nonsense&period=nonsense` | falls back to Flexi Cap / 3y, no crash |

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/funds/compare/page.tsx
git commit -m "feat(funds): the category compare page shell with data disclosures"
```

---

## Task 10: Print layout

**Files:**
- Modify: `frontend/src/app/funds/compare/page.tsx` (only if the print check finds problems)

- [ ] **Step 1: Print the page to PDF and inspect it**

With the dev server running, open `http://localhost:3000/funds/compare?cat=India+Fund+Small-Cap&period=5y`, press Cmd-P, and check:

1. The fixed top nav and sub-nav do not appear (the `@media print` block in `globals.css:144` hides `nav` and `.fixed`).
2. The controls row is absent (`print:hidden`).
3. Colours are the light print palette, not the dark theme.
4. No panel or table is split across a page break (`break-inside-avoid` on each panel body).
5. The footer disclosures appear in full.
6. Nothing overflows the page width.

- [ ] **Step 2: Fix only what the check found**

If a table splits across pages, add `break-inside-avoid` to the offending `<tbody>`. If the chart overflows, add `print:max-w-full` to the panel. Make no speculative changes — the existing print stylesheet already handles the general case.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/funds/compare/page.tsx
git commit -m "fix(funds): print layout for the category compare report"
```

Skip the commit if Step 2 changed nothing.

---

## Task 11: Link it from the Funds page

**Files:**
- Modify: `frontend/src/components/funds/FundsPageV4.tsx`

- [ ] **Step 1: Read the page header block**

```bash
cd frontend && grep -n "export async function FundsPageV4" -A 45 src/components/funds/FundsPageV4.tsx
```

Find the returned header where the page title and as-of stamp are rendered.

- [ ] **Step 2: Add the link beside the page title**

Insert this into that header, matching the surrounding class conventions:

```tsx
<a href="/funds/compare"
   className="rounded-tile border border-edge-hair px-3 py-1.5 font-sans text-[12px] text-txt-2 no-underline hover:border-edge-strong hover:text-txt-1">
  Compare a category →
</a>
```

- [ ] **Step 3: Verify the link renders and navigates**

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000/funds`, confirm the link is present, click it, confirm it lands on the compare page.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/funds/FundsPageV4.tsx
git commit -m "feat(funds): link the category compare page from /funds"
```

---

## Task 12: Full verification

- [ ] **Step 1: Run the repo gate**

```bash
cd "/Users/nimishshah/All AI/atlas-os" && make gate
```

Expected: PASS. Not `make check` — that runs raw pyright and exits non-zero by design on the grandfathered baseline.

- [ ] **Step 2: Run the full frontend test suite**

```bash
cd frontend && npm test
```

Expected: all suites pass, including 25 unit tests in `fundCategoryCurve.test.ts` and 7 integration tests in `fund_category_curve.int.test.ts` (or 7 skipped without `ATLAS_DB_URL`).

- [ ] **Step 3: Confirm a production build succeeds**

```bash
cd frontend && npm run build
```

Expected: build completes; `/funds/compare` appears in the route list as a dynamic route (it reads `searchParams`).

- [ ] **Step 4: Confirm file sizes are within the tiered limits**

```bash
cd frontend && wc -l src/lib/fundCategoryCurve.ts src/lib/queries/fund_category_curve.ts \
  src/lib/__tests__/fundCategoryCurve.test.ts \
  src/components/funds/CategoryCompare*.tsx src/app/funds/compare/page.tsx
```

Expected: source files ≤600, tests ≤800, `page.tsx` ≤250.

- [ ] **Step 5: Confirm no synthetic data entered the tests**

```bash
cd frontend && grep -nE "mock|fake|stub|dummy|synthetic|Math\.random" \
  src/lib/__tests__/fundCategoryCurve.test.ts \
  src/lib/queries/__tests__/fund_category_curve.int.test.ts
```

Expected: no output. Every fixture value must be traceable to a documented query against `atlas_foundation`.

- [ ] **Step 6: Open a PR**

```bash
cd "/Users/nimishshah/All AI/atlas-os" && git push -u origin feat/fund-category-compare
gh pr create --title "feat(funds): category-vs-benchmark compare page" --body "$(cat <<'EOF'
Adds `/funds/compare`: pick a fund category and a period, get an equal-weighted composite
equity curve against Nifty 50 / Nifty 500 / the category index, with trailing returns,
rolling-return distribution, the constituent fund list, and print-to-PDF.

The composite is a chain-linked equal-weighted daily return series computed in Postgres, so
funds entering and leaving the category do not step the curve.

Three data limits are disclosed on the page rather than papered over:
- the fund master carries live funds only, so the composite is survivorship-biased at source
- every index in `index_prices` is price-return while NAVs are total-return, flattering the
  composite by roughly 1–1.5%/yr
- the Index Funds, Focused Fund and Equity-ESG NAV feeds are stale (newest 2026-05-15,
  2026-05-15 and 2026-04-06); those categories render a warning banner

Nothing under `atlas/`, the nightly pipeline, or the lens compute changes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Follow-up work this plan deliberately excludes

Raise these separately; none of them belongs in this PR.

1. **The dead NAV feeds.** Index Funds, Focused Fund and Equity-ESG stopped updating in April/May 2026 — 287 funds. This page exposes the defect but cannot fix it; the cause is in `scripts/foundation/`.
2. **Closed and merged fund history**, which is what would actually remove the survivorship bias.
3. **TRI index ingestion**, which is what would actually fix the price-return mismatch.
4. **The equality join in `FundEquityCurves.tsx:207-208`**, which silently drops benchmark points on dates the index did not trade — the same bug this page fixes with an as-of join.
