# Stock Detail Page Redesign — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current stock detail page flat dump with a 7-section signal stack: Event Header → Chart + Commentary + Fundamentals → RS Confirmation → Lifecycle → Peer Matrix → Supporting Detail → Act.

**Architecture:** New `components/v6/stock-detail/` directory houses 6 focused server/client components. Page.tsx fetches 2 new API endpoints (rs-ratios, peer-matrix), assembles the 7 sections. Old components (StockDeepDiveBody, WithinStatePeers, TVChartPanel, TVMetricsBadge) removed. Recharts for RS ratio charts.

**Tech Stack:** Next.js 15 App Router, TypeScript strict, Tailwind CSS, Recharts, TradingView widget iframe

---

## Pre-flight checks

- [ ] Confirm worktree: `git -C /Users/nimishshah/Documents/GitHub/atlas-os-tv branch --show-current`
  - Expected output: `feat/tv-integration`
- [ ] Confirm key directories exist:
  ```bash
  ls /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/components/v6/stocks/TraderViewHeader.tsx
  ls /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/components/stocks/ComponentScorecard.tsx
  ls /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/components/stocks/DwellTimeline.tsx
  ls /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/components/stocks/HitRateRow.tsx
  ls /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/app/stocks/\[symbol\]/page.tsx
  ```
  All five must print a path (no "No such file" error).
- [ ] Confirm test suite is green before touching anything:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx vitest run 2>&1 | tail -10
  ```
  Expected: `Tests X passed` with 0 failures.
- [ ] Confirm TypeScript baseline:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx tsc --noEmit 2>&1 | head -20
  ```
  Record any pre-existing errors — do not introduce new ones.
- [ ] Create the new component directory:
  ```bash
  mkdir -p /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/components/v6/stock-detail
  ```
- [ ] Create the new test directory:
  ```bash
  mkdir -p /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend/src/__tests__/stock-detail
  ```

---

## Task 1: Extend TVMetricsRow type + new query helpers

Two sub-tasks: (a) add 5 fundamental fields to the existing `TVMetricsRow` interface; (b) create the new `stock-detail.ts` query file with RS ratios and peer matrix fetchers.

### 1a — Extend TVMetricsRow in `frontend/src/lib/api/v1.ts`

- [ ] Open `frontend/src/lib/api/v1.ts`. Locate the `TVMetricsRow` interface (currently around line 272). Add 5 new fields at the end of the interface:

```typescript
export interface TVMetricsRow {
  symbol: string
  tv_recommend_label: string | null
  recommend_all: string | null
  recommend_ma: string | null
  recommend_other: string | null
  rsi_14: string | null
  macd_macd: string | null
  ema_20: string | null
  ema_50: string | null
  ema_200: string | null
  atr_14: string | null
  price: string | null
  high_52w: string | null
  low_52w: string | null
  fetched_at: string | null
  is_stale: boolean
  // TV-fundamentals (migration 118 — may be null until backend deployed)
  pe_ttm: number | null
  ps_current: number | null
  pb_fbs: number | null
  debt_to_equity: number | null
  roe: number | null
}
```

  The new fields are nullable so the frontend degrades gracefully before migration 118 is applied on EC2.

- [ ] Run `npx tsc --noEmit 2>&1 | grep "v1.ts"` — must produce no output.

### 1b — Create `frontend/src/lib/queries/v6/stock-detail.ts`

- [ ] Create the file at `frontend/src/lib/queries/v6/stock-detail.ts` with the following content:

```typescript
// frontend/src/lib/queries/v6/stock-detail.ts
//
// Client-side fetchers for the two new stock detail endpoints:
//   GET /v1/stocks/{symbol}/rs-ratios?days=252
//   GET /v1/stocks/{symbol}/peer-matrix
//
// Both use the same ATLAS_V1_API_BASE env var as /lib/api/v1.ts.
// Both degrade gracefully (null / []) on network failure or 404.
// next: { revalidate: 3600 } — stale-while-revalidate, 1-hour TTL.

const API_BASE = process.env.ATLAS_V1_API_BASE ?? 'http://localhost:8002'

// ─── RS Ratios ──────────────────────────────────────────────────────────────

export interface RSRatioPoint {
  date: string
  ratio: number
}

export interface RSRatiosData {
  symbol: string
  sector: string | null
  sector_index_code: string
  vs_sector: RSRatioPoint[]
  vs_sector_resistance: number
  vs_sector_status: 'BREAKING_OUT' | 'AT_RESISTANCE' | 'BELOW_RESISTANCE'
  vs_nifty50: RSRatioPoint[]
  vs_nifty50_resistance: number
  vs_nifty50_status: 'BREAKING_OUT' | 'AT_RESISTANCE' | 'BELOW_RESISTANCE'
}

export async function getRSRatios(symbol: string): Promise<RSRatiosData | null> {
  try {
    const res = await fetch(
      `${API_BASE}/v1/stocks/${encodeURIComponent(symbol)}/rs-ratios?days=252`,
      { next: { revalidate: 3600 } },
    )
    if (!res.ok) return null
    const json = await res.json()
    return (json.data ?? null) as RSRatiosData | null
  } catch {
    return null
  }
}

// ─── Peer Matrix ─────────────────────────────────────────────────────────────

export interface PeerRow {
  symbol: string
  company_name: string
  is_parent: boolean
  stage: string
  conviction: string
  rs_vs_nifty: number | null
  ema20_slope: string
  volume: string
  ret_3m_pct: number | null
  extension_pct: number | null
}

export async function getPeerMatrix(symbol: string): Promise<PeerRow[]> {
  try {
    const res = await fetch(
      `${API_BASE}/v1/stocks/${encodeURIComponent(symbol)}/peer-matrix`,
      { next: { revalidate: 3600 } },
    )
    if (!res.ok) return []
    const json = await res.json()
    return (json.data?.peers ?? []) as PeerRow[]
  } catch {
    return []
  }
}
```

- [ ] Verify TypeScript: `cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx tsc --noEmit 2>&1 | grep "stock-detail.ts"` — must produce no output.

---

## Task 2: EventHeader component

**File:** `frontend/src/components/v6/stock-detail/EventHeader.tsx`

Server component — no `'use client'` directive.

- [ ] Create the file with the content below:

```typescript
// frontend/src/components/v6/stock-detail/EventHeader.tsx
//
// Section 1 of the redesigned stock detail page.
// Displays: symbol + name + badges | stage pill + dwell + rank | 4-metric row.
// Pure server component.

interface EventHeaderProps {
  symbol: string
  companyName: string
  sector: string | null
  indexBadges: string[]      // e.g. ['Nifty 50', 'Nifty 100']
  state: string | null       // 'stage_2b', 'stage_1', 'uninvestable', etc.
  dwellDays: number | null
  peerRank: number | null
  peerTotal: number
  convictionDirection: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | null
  convictionTenure: string | null  // '3m', '6m'
  currentPrice: number | null
  ret3m: number | null             // raw fraction e.g. 0.23 = +23%
  rsVsNifty: number | null         // rs_pctile_3m 0–1 scale
}

const STAGE_META: Record<string, { label: string; color: string }> = {
  stage_1:      { label: 'STAGE 1 BASE',         color: 'text-ink-3' },
  stage_2a:     { label: 'STAGE 2A BREAKOUT',     color: 'text-signal-pos' },
  stage_2b:     { label: 'STAGE 2B CONFIRMED',    color: 'text-signal-pos' },
  stage_2c:     { label: 'STAGE 2C MATURE',       color: 'text-signal-warn' },
  stage_3:      { label: 'STAGE 3 TOP',           color: 'text-signal-warn' },
  stage_4:      { label: 'STAGE 4 DECLINE',       color: 'text-signal-neg' },
  uninvestable: { label: 'UNINVESTABLE',           color: 'text-signal-neg' },
}

const CONVICTION_META: Record<string, { label: string; cls: string }> = {
  POSITIVE: { label: 'BULLISH',  cls: 'bg-signal-pos text-white' },
  NEGATIVE: { label: 'BEARISH',  cls: 'bg-signal-neg text-white' },
  NEUTRAL:  { label: 'NEUTRAL',  cls: 'bg-paper-deep text-ink-3 border border-paper-rule' },
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  return `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

function fmtRsPctile(v: number | null): string {
  if (v == null) return '—'
  // rs_pctile_3m is stored 0-1; display as 0-100
  return `${Math.round(v * 100)}`
}

export function EventHeader({
  symbol,
  companyName,
  sector,
  indexBadges,
  state,
  dwellDays,
  peerRank,
  peerTotal,
  convictionDirection,
  convictionTenure,
  currentPrice,
  ret3m,
  rsVsNifty,
}: EventHeaderProps) {
  const stageMeta = state ? (STAGE_META[state] ?? { label: state.toUpperCase(), color: 'text-ink-3' }) : null
  const convMeta = convictionDirection ? CONVICTION_META[convictionDirection] : null

  return (
    <section className="px-6 py-5 border-b border-paper-rule bg-paper">
      {/* Row 1: Symbol + company + sector badge + index badges */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
        <span className="font-mono text-[28px] font-semibold text-ink leading-none">{symbol}</span>
        <span className="font-sans text-base text-ink-3 leading-none">{companyName}</span>
        {sector && (
          <span className="inline-block border border-paper-rule rounded-[2px] px-2 py-0.5 font-mono text-[10px] text-ink-4 tracking-wide">
            {sector}
          </span>
        )}
        {indexBadges.map(badge => (
          <span
            key={badge}
            className="inline-block border border-paper-rule rounded-[2px] px-2 py-0.5 font-mono text-[10px] text-ink-4 tracking-wide"
          >
            {badge}
          </span>
        ))}
      </div>

      {/* Row 2: Stage pill + dwell + rank + conviction */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-4">
        {stageMeta && (
          <span className={`font-mono text-[11px] font-semibold tracking-wider ${stageMeta.color}`}>
            {stageMeta.label}
          </span>
        )}
        {dwellDays !== null && (
          <span className="font-sans text-[12px] text-ink-3">
            · {dwellDays} day{dwellDays !== 1 ? 's' : ''}
          </span>
        )}
        {peerRank !== null && (
          <span className="font-sans text-[12px] text-ink-3">
            · Rank {peerRank} of {peerTotal}
          </span>
        )}
        {convMeta && (
          <span className={`inline-block px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold tracking-wider ${convMeta.cls}`}>
            {convMeta.label}{convictionTenure ? ` ${convictionTenure.toUpperCase()}` : ''}
          </span>
        )}
      </div>

      {/* Row 3: 4-metric cells */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCell label="Price" value={fmtPrice(currentPrice)} valueClass="text-ink" />
        <MetricCell
          label="3M Return"
          value={fmtPct(ret3m)}
          valueClass={ret3m == null ? 'text-ink-3' : ret3m >= 0 ? 'text-signal-pos' : 'text-signal-neg'}
        />
        <MetricCell
          label="RS Percentile"
          value={fmtRsPctile(rsVsNifty)}
          valueClass={
            rsVsNifty == null
              ? 'text-ink-3'
              : rsVsNifty >= 0.8
              ? 'text-signal-pos'
              : rsVsNifty >= 0.5
              ? 'text-ink'
              : 'text-signal-neg'
          }
          unit="/100"
        />
        <MetricCell
          label="Conviction"
          value={convMeta?.label ?? '—'}
          valueClass={
            convictionDirection === 'POSITIVE'
              ? 'text-signal-pos'
              : convictionDirection === 'NEGATIVE'
              ? 'text-signal-neg'
              : 'text-ink-3'
          }
        />
      </div>
    </section>
  )
}

function MetricCell({
  label,
  value,
  valueClass,
  unit,
}: {
  label: string
  value: string
  valueClass: string
  unit?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">{label}</p>
      <p className={`font-mono text-[18px] font-semibold leading-none ${valueClass}`}>
        {value}
        {unit && <span className="font-sans text-[10px] text-ink-3 ml-0.5">{unit}</span>}
      </p>
    </div>
  )
}
```

- [ ] Verify: `cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx tsc --noEmit 2>&1 | grep "EventHeader"` — no output.

---

## Task 3: FundamentalsStrip component

**File:** `frontend/src/components/v6/stock-detail/FundamentalsStrip.tsx`

Server component — no `'use client'` directive.

- [ ] Create the file:

```typescript
// frontend/src/components/v6/stock-detail/FundamentalsStrip.tsx
//
// 5-pill horizontal strip: P/E · P/S · P/B · Debt/Eq · ROE
// Null values display as "—". No color coding (context without benchmarks is noise).
// Pure server component.

interface FundamentalsStripProps {
  pe: number | null
  ps: number | null
  pb: number | null
  debtToEquity: number | null
  roe: number | null
}

function fmt(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function fmtRoe(v: number | null): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

interface PillProps {
  label: string
  value: string
}

function Pill({ label, value }: PillProps) {
  return (
    <div className="flex flex-col items-start gap-0.5 px-3 py-2 border border-paper-rule rounded bg-paper-deep">
      <span className="font-mono text-[9px] uppercase tracking-wider text-ink-3">{label}</span>
      <span className="font-mono text-[15px] text-ink leading-none">{value}</span>
    </div>
  )
}

export function FundamentalsStrip({ pe, ps, pb, debtToEquity, roe }: FundamentalsStripProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <Pill label="P/E" value={fmt(pe)} />
      <Pill label="P/S" value={fmt(ps)} />
      <Pill label="P/B" value={fmt(pb)} />
      <Pill label="Debt/Eq" value={fmt(debtToEquity)} />
      <Pill label="ROE" value={fmtRoe(roe)} />
    </div>
  )
}
```

- [ ] Verify: `npx tsc --noEmit 2>&1 | grep "FundamentalsStrip"` — no output.

---

## Task 4: ChartCommentary utility + tests

### 4a — Create `frontend/src/components/v6/stock-detail/ChartCommentary.ts`

- [ ] Create the file (`.ts` not `.tsx` — no JSX):

```typescript
// frontend/src/components/v6/stock-detail/ChartCommentary.ts
//
// Pure function: derives plain-English Atlas chart reading from numeric signals.
// No JSX, no React, no imports — safe to call from server components and tests.

export interface CommentaryInput {
  state: string | null
  dwellDays: number | null
  stateSinceDate: string | null
  ema20Ratio: number | null      // price / EMA20; e.g. 1.05 = 5% above EMA20
  volRatio63: number | null      // 20D avg vol / 63D avg vol
  extension: number | null       // extension_pct (unused in prose; kept for future use)
  high52w: number | null
  price: number | null
}

export function generateChartCommentary(input: CommentaryInput): string {
  const parts: string[] = []

  // — State transition —
  if (input.state && input.dwellDays !== null) {
    const stateLabel = input.state
      .replace('stage_', 'Stage ')
      .replace('_', ' ')
      .toUpperCase()
    const freshness =
      input.dwellDays <= 20
        ? 'Recently entered'
        : input.dwellDays <= 60
        ? 'Confirmed in'
        : 'Established in'
    parts.push(`${freshness} ${stateLabel} ${input.dwellDays} days ago.`)
  }

  // — EMA20 position —
  if (input.ema20Ratio !== null) {
    const extPct = (input.ema20Ratio - 1) * 100
    if (Math.abs(extPct) < 3) {
      parts.push('Trading close to EMA 20 — not extended.')
    } else if (extPct > 8) {
      parts.push(
        `Running ${extPct.toFixed(1)}% above EMA 20 — extended, watch for a pullback to base.`,
      )
    } else if (extPct > 0) {
      parts.push(`${extPct.toFixed(1)}% above EMA 20 — not overextended.`)
    } else {
      parts.push(`Holding below EMA 20 — needs to reclaim.`)
    }
  }

  // — Volume —
  if (input.volRatio63 !== null) {
    if (input.volRatio63 > 1.3) {
      parts.push('Volume expanding — institutional participation confirming the move.')
    } else if (input.volRatio63 < 0.8) {
      parts.push('Volume fading — watch for re-acceleration before adding.')
    } else {
      parts.push('Volume steady — no distribution signal.')
    }
  }

  return parts.join(' ') || 'Insufficient data for commentary.'
}
```

### 4b — Create tests at `frontend/src/__tests__/stock-detail/ChartCommentary.test.ts`

- [ ] Create the test file:

```typescript
// frontend/src/__tests__/stock-detail/ChartCommentary.test.ts

import { describe, it, expect } from 'vitest'
import { generateChartCommentary } from '@/components/v6/stock-detail/ChartCommentary'

const BASE: Parameters<typeof generateChartCommentary>[0] = {
  state: null,
  dwellDays: null,
  stateSinceDate: null,
  ema20Ratio: null,
  volRatio63: null,
  extension: null,
  high52w: null,
  price: null,
}

describe('generateChartCommentary', () => {
  it('returns fallback when all inputs are null', () => {
    expect(generateChartCommentary(BASE)).toBe('Insufficient data for commentary.')
  })

  it('uses "Recently entered" for dwellDays <= 20', () => {
    const result = generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 14 })
    expect(result).toContain('Recently entered')
    expect(result).toContain('14 days ago')
  })

  it('uses "Confirmed in" for dwellDays 21-60', () => {
    const result = generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 45 })
    expect(result).toContain('Confirmed in')
    expect(result).toContain('45 days ago')
  })

  it('uses "Established in" for dwellDays > 60', () => {
    const result = generateChartCommentary({ ...BASE, state: 'stage_2b', dwellDays: 120 })
    expect(result).toContain('Established in')
    expect(result).toContain('120 days ago')
  })

  it('flags extension > 8% with extended warning', () => {
    const result = generateChartCommentary({ ...BASE, ema20Ratio: 1.09 })
    expect(result).toContain('above EMA 20 — extended')
  })

  it('reports moderate extension without warning', () => {
    const result = generateChartCommentary({ ...BASE, ema20Ratio: 1.05 })
    expect(result).toContain('above EMA 20 — not overextended')
    expect(result).not.toContain('extended,')
  })

  it('reports close-to-EMA within 3%', () => {
    const result = generateChartCommentary({ ...BASE, ema20Ratio: 1.02 })
    expect(result).toContain('close to EMA 20 — not extended')
  })

  it('reports below-EMA when ratio < 1', () => {
    const result = generateChartCommentary({ ...BASE, ema20Ratio: 0.97 })
    expect(result).toContain('below EMA 20 — needs to reclaim')
  })

  it('flags volume expanding when volRatio63 > 1.3', () => {
    const result = generateChartCommentary({ ...BASE, volRatio63: 1.5 })
    expect(result).toContain('Volume expanding')
  })

  it('flags volume fading when volRatio63 < 0.8', () => {
    const result = generateChartCommentary({ ...BASE, volRatio63: 0.7 })
    expect(result).toContain('Volume fading')
  })

  it('reports steady volume in the middle range', () => {
    const result = generateChartCommentary({ ...BASE, volRatio63: 1.0 })
    expect(result).toContain('Volume steady')
  })

  it('combines all three sections when all inputs are present', () => {
    const result = generateChartCommentary({
      ...BASE,
      state: 'stage_2b',
      dwellDays: 30,
      ema20Ratio: 1.03,
      volRatio63: 1.4,
    })
    expect(result).toContain('Confirmed in')
    expect(result).toContain('close to EMA 20')
    expect(result).toContain('Volume expanding')
  })
})
```

### 4c — Run the tests

- [ ] Run:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx vitest run src/__tests__/stock-detail/ChartCommentary.test.ts 2>&1 | tail -15
  ```
  Expected: `12 passed` (or the count matching the tests above), 0 failures.

---

## Task 5: StockChartPanel component

**File:** `frontend/src/components/v6/stock-detail/StockChartPanel.tsx`

`'use client'` — needs `useState` for iframe error handling.

- [ ] Create the file:

```typescript
// frontend/src/components/v6/stock-detail/StockChartPanel.tsx
//
// Section 2: TradingView weekly chart iframe + Atlas commentary + fundamentals strip.
// 'use client' required for iframe onError handler.

'use client'

import { useState } from 'react'
import { FundamentalsStrip } from './FundamentalsStrip'

interface StockChartPanelProps {
  symbol: string
  commentary: string        // pre-generated server-side by generateChartCommentary
  pe: number | null
  ps: number | null
  pb: number | null
  debtToEquity: number | null
  roe: number | null
}

/**
 * Weekly TradingView chart with volume, EMA20/50/200 overlays.
 * Dark theme (#1A1714 matches --ink token).
 */
function tvUrl(symbol: string): string {
  const encodedSymbol = encodeURIComponent(`NSE:${symbol}`)
  return (
    `https://www.tradingview.com/widgetembed/?frameElementId=tradingview_atlas` +
    `&symbol=${encodedSymbol}` +
    `&interval=W` +
    `&hidesidetoolbar=1` +
    `&hidetoptoolbar=0` +
    `&symboledit=0` +
    `&saveimage=0` +
    `&toolbarbg=1A1714` +
    `&theme=Dark` +
    `&style=1` +
    `&timezone=Asia%2FKolkata` +
    `&locale=en`
  )
}

export function StockChartPanel({
  symbol,
  commentary,
  pe,
  ps,
  pb,
  debtToEquity,
  roe,
}: StockChartPanelProps) {
  const [chartError, setChartError] = useState(false)

  return (
    <section className="border-b border-paper-rule">
      {/* Chart */}
      {chartError ? (
        <div className="bg-paper-deep flex items-center justify-center h-[300px]">
          <div className="text-center">
            <p className="font-sans text-sm text-ink-3 mb-2">Chart unavailable</p>
            <a
              href={`https://www.tradingview.com/chart/?symbol=NSE:${symbol}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-sans text-sm text-accent hover:underline"
            >
              Open in TradingView ↗
            </a>
          </div>
        </div>
      ) : (
        <iframe
          src={tvUrl(symbol)}
          className="w-full h-[340px] md:h-[420px] border-0"
          onError={() => setChartError(true)}
          title={`${symbol} weekly price chart`}
          loading="lazy"
        />
      )}

      {/* Atlas chart reading */}
      <div className="px-6 py-4 border-t border-paper-rule bg-paper">
        <p className="font-mono text-[10px] text-teal uppercase tracking-wider mb-2">
          Atlas Chart Reading
        </p>
        <p className="font-sans text-sm text-ink leading-relaxed">{commentary}</p>
      </div>

      {/* Fundamentals strip */}
      <div className="px-6 pb-4">
        <FundamentalsStrip pe={pe} ps={ps} pb={pb} debtToEquity={debtToEquity} roe={roe} />
      </div>
    </section>
  )
}
```

- [ ] Verify: `npx tsc --noEmit 2>&1 | grep "StockChartPanel"` — no output.

---

## Task 6: RSConfirmationPanel component

**File:** `frontend/src/components/v6/stock-detail/RSConfirmationPanel.tsx`

`'use client'` — uses Recharts.

- [ ] Create the file:

```typescript
// frontend/src/components/v6/stock-detail/RSConfirmationPanel.tsx
//
// Section 3: Dual Recharts line charts (RS vs sector + RS vs Nifty 50) with
// resistance reference line and breakout status badge.
// Includes plain-English entry-timing synthesis.

'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { RSRatiosData } from '@/lib/queries/v6/stock-detail'

interface RSConfirmationPanelProps {
  rsData: RSRatiosData | null
  symbol: string
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_META = {
  BREAKING_OUT:     { label: 'BREAKING OUT',     cls: 'bg-signal-pos text-white' },
  AT_RESISTANCE:    { label: 'AT RESISTANCE',    cls: 'bg-signal-warn text-white' },
  BELOW_RESISTANCE: { label: 'BELOW RESISTANCE', cls: 'bg-signal-neg text-white' },
} as const

function StatusBadge({ status }: { status: keyof typeof STATUS_META }) {
  const meta = STATUS_META[status]
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold tracking-wider ${meta.cls}`}
    >
      {meta.label}
    </span>
  )
}

// ─── Single ratio chart ───────────────────────────────────────────────────────

function RatioChart({
  data,
  resistance,
  label,
}: {
  data: { date: string; ratio: number }[]
  resistance: number
  label: string
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">{label}</p>
      <ResponsiveContainer width="100%" height={130}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(194,184,168,0.3)" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: '#9A8F82' }}
            tickLine={false}
            interval="preserveStartEnd"
            tickFormatter={(d: string) => d.slice(5)}
          />
          <YAxis
            tick={{ fontSize: 9, fill: '#9A8F82' }}
            tickLine={false}
            width={44}
            tickFormatter={(v: number) => v.toFixed(3)}
          />
          <Tooltip
            formatter={(v: number) => [v.toFixed(4), 'Ratio']}
            labelStyle={{ fontSize: 11 }}
            contentStyle={{ fontSize: 11 }}
          />
          <ReferenceLine
            y={resistance}
            stroke="#B8860B"
            strokeDasharray="4 2"
            strokeWidth={1.5}
            label={{ value: 'Resistance', position: 'insideTopRight', fontSize: 9, fill: '#B8860B' }}
          />
          <Line
            type="monotone"
            dataKey="ratio"
            stroke="#1D9E75"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─── Entry-timing synthesis ───────────────────────────────────────────────────

function generateRSSynthesis(rsData: RSRatiosData): string {
  const sectorLabel = rsData.sector_index_code ?? 'sector index'
  const { vs_sector_status: ss, vs_nifty50_status: ns } = rsData

  if (ss === 'BREAKING_OUT' && ns === 'BREAKING_OUT') {
    return `Both RS ratios are breaking out above resistance. Strong dual confirmation — full position entry supported.`
  }
  if (ss === 'BREAKING_OUT' && ns !== 'BREAKING_OUT') {
    return `RS vs ${sectorLabel} confirmed above resistance. RS vs Nifty 50 still lagging — consider a partial position until the Nifty ratio confirms.`
  }
  if (ss !== 'BREAKING_OUT' && ns === 'BREAKING_OUT') {
    return `RS vs Nifty 50 is breaking out but the sector ratio is still lagging — broad market leadership without sector-relative leadership yet. Monitor sector ratio for confirmation.`
  }
  if (ss === 'AT_RESISTANCE' || ns === 'AT_RESISTANCE') {
    return `One or both RS ratios are testing resistance. Watch for a confirmed close above resistance before entering.`
  }
  return `Both RS ratios remain below resistance. Wait for at least one ratio to break out before entering.`
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function RSConfirmationPanel({ rsData, symbol }: RSConfirmationPanelProps) {
  const hasSector = (rsData?.vs_sector?.length ?? 0) > 0
  const hasNifty = (rsData?.vs_nifty50?.length ?? 0) > 0

  if (!rsData || (!hasSector && !hasNifty)) {
    return (
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">
          Relative Strength Confirmation
        </p>
        <p className="font-sans text-sm text-ink-3">
          RS ratio data unavailable for {symbol}. Backend endpoint may not be deployed yet.
        </p>
      </section>
    )
  }

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">
        Relative Strength Confirmation — Is the move confirmed?
      </p>

      {/* Dual chart grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
        {hasSector && (
          <div className="bg-paper border border-paper-rule rounded p-4">
            <RatioChart
              data={rsData.vs_sector}
              resistance={rsData.vs_sector_resistance}
              label={`${symbol} ÷ ${rsData.sector_index_code}`}
            />
            <div className="mt-2">
              <StatusBadge status={rsData.vs_sector_status} />
            </div>
          </div>
        )}
        {hasNifty && (
          <div className="bg-paper border border-paper-rule rounded p-4">
            <RatioChart
              data={rsData.vs_nifty50}
              resistance={rsData.vs_nifty50_resistance}
              label={`${symbol} ÷ Nifty 50`}
            />
            <div className="mt-2">
              <StatusBadge status={rsData.vs_nifty50_status} />
            </div>
          </div>
        )}
      </div>

      {/* Entry timing synthesis */}
      <div className="bg-paper-deep border border-paper-rule rounded p-4">
        <p className="font-mono text-[10px] text-teal uppercase tracking-wider mb-2">
          Entry Timing
        </p>
        <p className="font-sans text-sm text-ink leading-relaxed">
          {generateRSSynthesis(rsData)}
        </p>
      </div>
    </section>
  )
}
```

- [ ] Verify: `npx tsc --noEmit 2>&1 | grep "RSConfirmationPanel"` — no output.

---

## Task 7: LifecyclePanel component

**File:** `frontend/src/components/v6/stock-detail/LifecyclePanel.tsx`

Server component — no `'use client'` directive.

- [ ] Create the file:

```typescript
// frontend/src/components/v6/stock-detail/LifecyclePanel.tsx
//
// Section 4: Weinstein lifecycle position — how far into the stage, volume
// classification, EMA20 extension, and plain-English lifecycle synthesis.
// Pure server component.

interface LifecyclePanelProps {
  state: string | null
  dwellDays: number | null
  ema20Ratio: number | null      // price / EMA20
  volRatio63: number | null      // 20D avg / 63D avg volume
  extensionPct: number | null    // extension_pct from metrics
}

// Typical dwell context per stage — based on methodology lock
const DWELL_CONTEXT: Record<string, string> = {
  stage_1:      'Base formation — duration varies (weeks to years).',
  stage_2a:     'Typical Stage 2A breakout: 10–90 days.',
  stage_2b:     'Typical Stage 2B confirmed: 60–360 days.',
  stage_2c:     'Typical Stage 2C mature: 90–400 days. Watch for distribution.',
  stage_3:      'Distribution phase — typically short-lived (weeks to 3 months).',
  stage_4:      'Decline phase — can last 6–24 months.',
  uninvestable: 'Structurally impaired — no actionable signal.',
}

const STAGE_LABEL: Record<string, string> = {
  stage_1:      'Stage 1 Base',
  stage_2a:     'Stage 2A Breakout',
  stage_2b:     'Stage 2B Confirmed',
  stage_2c:     'Stage 2C Mature',
  stage_3:      'Stage 3 Distribution',
  stage_4:      'Stage 4 Decline',
  uninvestable: 'Uninvestable',
}

function volumeClassification(v: number | null): { label: string; cls: string } {
  if (v == null) return { label: '— Unavailable', cls: 'text-ink-3' }
  if (v > 1.3) return { label: '↑ Expanding', cls: 'text-signal-pos' }
  if (v < 0.8) return { label: '↓ Fading',    cls: 'text-signal-neg' }
  return { label: '→ Stable', cls: 'text-ink-3' }
}

function ema20Classification(ema20Ratio: number | null): { label: string; cls: string } {
  if (ema20Ratio == null) return { label: '— Unavailable', cls: 'text-ink-3' }
  const extPct = (ema20Ratio - 1) * 100
  if (extPct > 8)  return { label: `⚠ Extended (+${extPct.toFixed(1)}% above EMA 20)`, cls: 'text-signal-warn' }
  if (extPct >= 0) return { label: `Not stretched (+${extPct.toFixed(1)}%)`,             cls: 'text-signal-pos' }
  return { label: `Below EMA 20 (${extPct.toFixed(1)}%)`,                                 cls: 'text-signal-neg' }
}

function synthesize(
  state: string | null,
  dwellDays: number | null,
  volRatio63: number | null,
  ema20Ratio: number | null,
): string {
  if (!state) return 'No lifecycle classification available.'

  const parts: string[] = []

  // Dwell context
  const dwell = DWELL_CONTEXT[state] ?? ''
  if (dwellDays !== null && dwell) {
    const early = dwellDays <= 30
    const late =
      (state === 'stage_2b' && dwellDays > 300) ||
      (state === 'stage_2c' && dwellDays > 350) ||
      (state === 'stage_4'  && dwellDays > 365)
    if (early) parts.push(`Early in ${STAGE_LABEL[state] ?? state} (${dwellDays} days). ${dwell}`)
    else if (late) parts.push(`Deep into ${STAGE_LABEL[state] ?? state} (${dwellDays} days) — ${dwell}`)
    else parts.push(`${dwellDays} days into ${STAGE_LABEL[state] ?? state}. ${dwell}`)
  }

  // Volume context
  if (volRatio63 !== null) {
    if (volRatio63 > 1.3) {
      parts.push('Volume is expanding — institutional demand confirmed.')
    } else if (volRatio63 < 0.8) {
      parts.push('Volume is contracting — re-acceleration needed before adding.')
    } else {
      parts.push('Volume is steady — no distribution signal.')
    }
  }

  // EMA20 extension
  if (ema20Ratio !== null) {
    const extPct = (ema20Ratio - 1) * 100
    if (extPct > 8) {
      parts.push(`Running ${extPct.toFixed(1)}% above EMA 20 — not an ideal entry point; prefer waiting for a pullback into base.`)
    } else if (extPct < 0) {
      parts.push('Trading below EMA 20 — needs to reclaim before entry is confirmed.')
    }
  }

  return parts.join(' ') || 'Insufficient data for lifecycle synthesis.'
}

interface MetricRowProps {
  label: string
  value: string
  valueClass: string
}

function MetricRow({ label, value, valueClass }: MetricRowProps) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-paper-rule last:border-0">
      <span className="font-sans text-[12px] text-ink-3">{label}</span>
      <span className={`font-mono text-[12px] font-medium ${valueClass}`}>{value}</span>
    </div>
  )
}

export function LifecyclePanel({
  state,
  dwellDays,
  ema20Ratio,
  volRatio63,
  extensionPct,
}: LifecyclePanelProps) {
  const vol = volumeClassification(volRatio63)
  const ema = ema20Classification(ema20Ratio)

  const ext =
    extensionPct != null
      ? {
          label: extensionPct >= 0 ? `+${(extensionPct * 100).toFixed(1)}% above 200D EMA` : `${(extensionPct * 100).toFixed(1)}% below 200D EMA`,
          cls: extensionPct >= 0 ? 'text-signal-pos' : 'text-signal-neg',
        }
      : { label: '—', cls: 'text-ink-3' }

  const synthesis = synthesize(state, dwellDays, volRatio63, ema20Ratio)
  const dwellContext = state ? (DWELL_CONTEXT[state] ?? null) : null

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">
        Lifecycle Position — Where in the stage?
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left: metric rows */}
        <div className="bg-paper border border-paper-rule rounded p-4">
          <MetricRow
            label="Days in current stage"
            value={dwellDays !== null ? `${dwellDays} days` : '—'}
            valueClass="text-ink"
          />
          <MetricRow
            label="Volume trend"
            value={vol.label}
            valueClass={vol.cls}
          />
          <MetricRow
            label="EMA 20 position"
            value={ema.label}
            valueClass={ema.cls}
          />
          <MetricRow
            label="Extension from 200D EMA"
            value={ext.label}
            valueClass={ext.cls}
          />
          {dwellContext && (
            <p className="font-sans text-[11px] text-ink-3 mt-3 italic">{dwellContext}</p>
          )}
        </div>

        {/* Right: synthesis */}
        <div className="bg-paper-deep border border-paper-rule rounded p-4">
          <p className="font-mono text-[10px] text-teal uppercase tracking-wider mb-2">
            Lifecycle Reading
          </p>
          <p className="font-sans text-sm text-ink leading-relaxed">{synthesis}</p>
        </div>
      </div>
    </section>
  )
}
```

- [ ] Verify: `npx tsc --noEmit 2>&1 | grep "LifecyclePanel"` — no output.

---

## Task 8: PeerMatrix component

**File:** `frontend/src/components/v6/stock-detail/PeerMatrix.tsx`

Server component — no `'use client'` directive.

- [ ] Create the file:

```typescript
// frontend/src/components/v6/stock-detail/PeerMatrix.tsx
//
// Section 5: Sector peer comparison table.
// Parent row (the stock itself) is highlighted with teal left border.
// All cells use color-coded values per type.
// Every symbol is a link to its own deep-dive page.
// Pure server component.

import Link from 'next/link'
import type { PeerRow } from '@/lib/queries/v6/stock-detail'

interface PeerMatrixProps {
  peers: PeerRow[]
}

// ─── Stage color ──────────────────────────────────────────────────────────────

function stageColor(stage: string): string {
  if (stage.includes('2a') || stage.includes('2b')) return 'text-signal-pos'
  if (stage.includes('2c') || stage.includes('3'))  return 'text-signal-warn'
  if (stage.includes('4') || stage.includes('uninv')) return 'text-signal-neg'
  return 'text-ink-3'
}

function stageLabel(stage: string): string {
  return stage
    .replace('stage_', 'S')
    .replace('_', '')
    .replace('uninvestable', 'UNINV')
    .toUpperCase()
}

// ─── Cell color helpers ───────────────────────────────────────────────────────

function convictionColor(val: string): string {
  if (val === 'Bullish' || val === 'POSITIVE') return 'text-signal-pos'
  if (val === 'Bearish' || val === 'NEGATIVE') return 'text-signal-neg'
  return 'text-ink-3'
}

function slopeColor(val: string): string {
  if (val === 'Rising' || val === 'Expanding') return 'text-signal-pos'
  if (val === 'Declining' || val === 'Fading')  return 'text-signal-neg'
  return 'text-ink-3'
}

function numColor(val: number | null): string {
  if (val == null) return 'text-ink-3'
  if (val > 0) return 'text-signal-pos'
  if (val < 0) return 'text-signal-neg'
  return 'text-ink-3'
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

function fmtRs(v: number | null): string {
  if (v == null) return '—'
  return Math.round(v * 100).toString()
}

// ─── Table header ─────────────────────────────────────────────────────────────

const HEADERS = [
  'Stock',
  'Stage',
  'Conviction',
  'RS Rank',
  'EMA20 Slope',
  'Volume',
  '3M Return',
  'Extension',
]

// ─── Main export ──────────────────────────────────────────────────────────────

export function PeerMatrix({ peers }: PeerMatrixProps) {
  if (peers.length === 0) return null

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">
        Peer Matrix — How does this stock stack up in its sector?
      </p>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-paper-rule">
              {HEADERS.map(h => (
                <th
                  key={h}
                  className="text-left py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {peers.map(peer => {
              const isParent = peer.is_parent
              return (
                <tr
                  key={peer.symbol}
                  className={[
                    'border-b border-paper-rule last:border-0',
                    isParent
                      ? 'bg-[rgba(29,158,117,0.08)] border-l-2 border-teal'
                      : 'hover:bg-paper-deep/50',
                  ].join(' ')}
                >
                  {/* Stock */}
                  <td className="py-2 px-2 whitespace-nowrap">
                    <Link
                      href={`/stocks/${peer.symbol}`}
                      className="font-mono text-accent hover:text-teal hover:underline"
                    >
                      {peer.symbol}
                    </Link>
                    {peer.company_name && (
                      <span className="block font-sans text-[10px] text-ink-3 truncate max-w-[120px]">
                        {peer.company_name}
                      </span>
                    )}
                  </td>

                  {/* Stage */}
                  <td className={`py-2 px-2 font-mono whitespace-nowrap ${stageColor(peer.stage)} ${isParent ? 'font-semibold' : ''}`}>
                    {stageLabel(peer.stage)}
                  </td>

                  {/* Conviction */}
                  <td className={`py-2 px-2 font-mono whitespace-nowrap ${convictionColor(peer.conviction)} ${isParent ? 'font-semibold' : ''}`}>
                    {peer.conviction || '—'}
                  </td>

                  {/* RS Rank (rs_pctile_3m → 0-100) */}
                  <td className={`py-2 px-2 font-mono text-right whitespace-nowrap ${numColor(peer.rs_vs_nifty)} ${isParent ? 'font-semibold' : ''}`}>
                    {fmtRs(peer.rs_vs_nifty)}
                  </td>

                  {/* EMA20 Slope */}
                  <td className={`py-2 px-2 font-mono whitespace-nowrap ${slopeColor(peer.ema20_slope)} ${isParent ? 'font-semibold' : ''}`}>
                    {peer.ema20_slope || '—'}
                  </td>

                  {/* Volume */}
                  <td className={`py-2 px-2 font-mono whitespace-nowrap ${slopeColor(peer.volume)} ${isParent ? 'font-semibold' : ''}`}>
                    {peer.volume || '—'}
                  </td>

                  {/* 3M Return */}
                  <td className={`py-2 px-2 font-mono text-right whitespace-nowrap ${numColor(peer.ret_3m_pct)} ${isParent ? 'font-semibold' : ''}`}>
                    {fmtPct(peer.ret_3m_pct)}
                  </td>

                  {/* Extension */}
                  <td className={`py-2 px-2 font-mono text-right whitespace-nowrap ${numColor(peer.extension_pct)} ${isParent ? 'font-semibold' : ''}`}>
                    {fmtPct(peer.extension_pct)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
```

- [ ] Verify: `npx tsc --noEmit 2>&1 | grep "PeerMatrix"` — no output.

---

## Task 9: Page assembly — update `page.tsx`

**File:** `frontend/src/app/stocks/[symbol]/page.tsx`

This is the integration step. Read the current file in full before editing.

### 9a — Add imports

- [ ] At the top of `page.tsx`, after the existing imports, add:

```typescript
import { getRSRatios, getPeerMatrix } from '@/lib/queries/v6/stock-detail'
import { EventHeader } from '@/components/v6/stock-detail/EventHeader'
import { StockChartPanel } from '@/components/v6/stock-detail/StockChartPanel'
import { RSConfirmationPanel } from '@/components/v6/stock-detail/RSConfirmationPanel'
import { LifecyclePanel } from '@/components/v6/stock-detail/LifecyclePanel'
import { PeerMatrix } from '@/components/v6/stock-detail/PeerMatrix'
import { generateChartCommentary } from '@/components/v6/stock-detail/ChartCommentary'
```

### 9b — Extend the `Promise.all` block

- [ ] In the `Promise.all([...])` call, add two new fetches **after** `getTVMetrics(symbol).catch(() => null)`:

```typescript
    getRSRatios(symbol).catch(() => null),
    getPeerMatrix(symbol).catch(() => []),
```

- [ ] Update the destructuring assignment to capture the two new values:

```typescript
  const [
    metricHistory,
    stockState,
    cohortKey,
    stateHistory,
    obvSeries,
    atrContraction,
    validations,
    hitRate,
    footerMetrics,
    traderHeader,
    tvMetrics,
    rsRatios,
    peerMatrix,
  ] = await Promise.all([...])
```

### 9c — Compute server-side commentary

- [ ] After the `Promise.all` block (after `peerRank` is computed), add:

```typescript
  // Latest metric row — history is ordered ASC, so last element is most recent.
  const latestMetrics = metricHistory.length > 0
    ? metricHistory[metricHistory.length - 1]
    : null

  // Pre-generate commentary server-side so StockChartPanel can receive it as a string prop.
  const commentary = generateChartCommentary({
    state: stockState?.state ?? null,
    dwellDays: stockState?.dwell_days ?? null,
    stateSinceDate: stockState?.state_since_date ?? null,
    ema20Ratio: latestMetrics?.ema_20_ratio != null
      ? parseFloat(latestMetrics.ema_20_ratio)
      : null,
    volRatio63: latestMetrics?.vol_ratio_63 != null
      ? parseFloat(latestMetrics.vol_ratio_63)
      : null,
    extension: latestMetrics?.extension_pct != null
      ? parseFloat(latestMetrics.extension_pct)
      : null,
    high52w: tvMetrics?.high_52w != null ? parseFloat(tvMetrics.high_52w) : null,
    price: tvMetrics?.price != null ? parseFloat(tvMetrics.price) : null,
  })
```

### 9d — Replace the JSX return block

- [ ] Replace the entire `return (...)` block with the new 7-section layout below.
  - Keep all logic above `return` unchanged (Act affordance, portfolioId, sizing, etc.).

```tsx
  return (
    <div className="max-w-[1200px] mx-auto">
      {/* Always-on trader-view header */}
      <TraderViewHeader data={traderHeader} />

      {/* Section 1: Event Header */}
      <EventHeader
        symbol={stock.symbol}
        companyName={stock.company_name ?? stock.symbol}
        sector={stock.sector ?? null}
        indexBadges={[
          stock.in_nifty_50  ? 'Nifty 50'  : null,
          stock.in_nifty_100 ? 'Nifty 100' : null,
          stock.in_nifty_500 ? 'Nifty 500' : null,
        ].filter(Boolean) as string[]}
        state={stockState?.state ?? null}
        dwellDays={stockState?.dwell_days ?? null}
        peerRank={peerRank}
        peerTotal={peers.length}
        convictionDirection={null}
        convictionTenure="3m"
        currentPrice={tvMetrics?.price != null ? parseFloat(tvMetrics.price) : null}
        ret3m={latestMetrics?.ret_3m != null ? parseFloat(latestMetrics.ret_3m) : null}
        rsVsNifty={latestMetrics?.rs_pctile_3m != null
          ? parseFloat(latestMetrics.rs_pctile_3m)
          : null}
      />

      {/* Section 2: Chart + Commentary + Fundamentals */}
      <StockChartPanel
        symbol={stock.symbol}
        commentary={commentary}
        pe={tvMetrics?.pe_ttm ?? null}
        ps={tvMetrics?.ps_current ?? null}
        pb={tvMetrics?.pb_fbs ?? null}
        debtToEquity={tvMetrics?.debt_to_equity ?? null}
        roe={tvMetrics?.roe ?? null}
      />

      {/* Section 3: RS Confirmation */}
      <RSConfirmationPanel rsData={rsRatios} symbol={stock.symbol} />

      {/* Section 4: Lifecycle Position */}
      <LifecyclePanel
        state={stockState?.state ?? null}
        dwellDays={stockState?.dwell_days ?? null}
        ema20Ratio={latestMetrics?.ema_20_ratio != null
          ? parseFloat(latestMetrics.ema_20_ratio)
          : null}
        volRatio63={latestMetrics?.vol_ratio_63 != null
          ? parseFloat(latestMetrics.vol_ratio_63)
          : null}
        extensionPct={latestMetrics?.extension_pct != null
          ? parseFloat(latestMetrics.extension_pct)
          : null}
      />

      {/* Section 5: Peer Matrix */}
      {peerMatrix.length > 0 && <PeerMatrix peers={peerMatrix} />}

      {/* Section 6: Supporting Detail */}
      <section className="px-6 py-6 border-b border-paper-rule space-y-6">
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          Supporting Detail
        </h2>
        {stateHistory.length > 0 && (
          <details className="font-sans text-[12px] text-ink-3">
            <summary className="cursor-pointer text-accent font-medium select-none">
              Show Weinstein stage history (context only — not a verdict input)
            </summary>
            <div className="pt-4">
              <DwellTimeline history={stateHistory} />
            </div>
          </details>
        )}
        {stockState && (
          <ComponentScorecard
            state={stockState}
            validations={validations}
            obvSlope={footerMetrics.obv_slope}
            atrRatio={footerMetrics.atr_ratio}
            realizedVolTier={footerMetrics.realized_vol_tier}
          />
        )}
        <HitRateRow hitRate={hitRate} />
      </section>

      {/* Section 7: Act */}
      <div className="px-6 pb-10 border-t border-paper-rule pt-6">
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">Act</h2>
        <ActButton
          portfolioId={portfolioId}
          portfolioName={actPortfolioName}
          instrumentId={stock.instrument_id}
          suggestedPct={actSuggestedPct}
          bindingConstraint={actBindingConstraint}
          sectorGapApplied={actSectorGapApplied}
        />
      </div>
    </div>
  )
```

---

## Task 10: Remove old components

Now that the new layout is in place, remove the obsolete imports and their renders.

### 10a — Remove imports from `page.tsx`

- [ ] Remove these import lines (they are no longer referenced in the return block):

```typescript
import { StockDeepDiveHeader } from '@/components/stocks/StockDeepDiveHeader'
import { StockDeepDiveBody } from '@/components/stocks/StockDeepDiveBody'
import { IntradayStockBadge } from '@/components/stocks/IntradayStockBadge'
import { MasterStateCard } from '@/components/stocks/MasterStateCard'
import { OBVContinuousChart } from '@/components/stocks/OBVContinuousChart'
import { ATRContractionGauge } from '@/components/stocks/ATRContractionGauge'
import { WithinStatePeers } from '@/components/stocks/WithinStatePeers'
import { TVMetricsBadgeFromRow } from '@/components/v6/TVMetricsBadge'
import { TVChartPanel } from '@/components/v6/TVChartPanel'
```

### 10b — Remove `obvSeries` and `atrContraction` fetches

- [ ] Remove these two import lines from the `stocks` query import:

```typescript
  getStockOBVSeries,
  getStockATRContraction,
```

- [ ] Remove these two entries from `Promise.all`:

```typescript
    getStockOBVSeries(stock.instrument_id, 50),
    getStockATRContraction(stock.instrument_id),
```

- [ ] Remove `obvSeries` and `atrContraction` from the destructuring assignment.

> **Note:** `getStockFooterMetrics` (for `footerMetrics`) must be **kept** — `ComponentScorecard` still reads `obv_slope`, `atr_ratio`, `realizedVolTier` from it.

---

## Task 11: Verification

### 11a — TypeScript

- [ ] Run:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx tsc --noEmit 2>&1 | grep -E "stock-detail|EventHeader|StockChartPanel|RSConf|Lifecycle|PeerMatrix|ChartCommentary"
  ```
  Expected: **no output** (zero errors in the new files).

- [ ] Run full TS check and compare against the pre-flight baseline:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx tsc --noEmit 2>&1 | wc -l
  ```
  Must not exceed the baseline error count recorded in pre-flight.

### 11b — Tests

- [ ] Run the new test suite:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx vitest run src/__tests__/stock-detail/ 2>&1 | tail -15
  ```
  Expected: all tests pass, 0 failures.

- [ ] Run full test suite to confirm no regressions:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npx vitest run 2>&1 | tail -10
  ```
  Expected: same count as pre-flight baseline + the new ChartCommentary tests.

### 11c — Build

- [ ] Run:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv/frontend && npm run build 2>&1 | tail -30
  ```
  Expected: build completes. Any TS errors will appear here — all must be resolved before proceeding.

  Common gotchas:
  - `'use client'` components importing from `server-only` modules → move server imports to the page and pass data as props (already the pattern here).
  - Recharts `isAnimationActive` causing SSR warnings → already set to `false` in `RatioChart`.
  - `stockState?.state_since_date` — confirm this field exists on the `StockState` type from `@/lib/queries/states`. If not, remove it from the `CommentaryInput` call (it is optional and unused in the current prose).

---

## Task 12: Commit

- [ ] Stage and commit:
  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os-tv && git add \
    frontend/src/lib/queries/v6/stock-detail.ts \
    frontend/src/lib/api/v1.ts \
    frontend/src/components/v6/stock-detail/EventHeader.tsx \
    frontend/src/components/v6/stock-detail/FundamentalsStrip.tsx \
    frontend/src/components/v6/stock-detail/ChartCommentary.ts \
    frontend/src/components/v6/stock-detail/StockChartPanel.tsx \
    frontend/src/components/v6/stock-detail/RSConfirmationPanel.tsx \
    frontend/src/components/v6/stock-detail/LifecyclePanel.tsx \
    frontend/src/components/v6/stock-detail/PeerMatrix.tsx \
    frontend/src/app/stocks/\[symbol\]/page.tsx \
    frontend/src/__tests__/stock-detail/ChartCommentary.test.ts
  ```

  ```bash
  git commit -m "feat(stock-detail): 7-section page redesign — event header, chart, RS confirmation, lifecycle, peer matrix"
  ```

---

## Appendix A: Component summary

| Component | File | Type | Section |
|---|---|---|---|
| `EventHeader` | `v6/stock-detail/EventHeader.tsx` | Server | 1 — Identity + key metrics |
| `StockChartPanel` | `v6/stock-detail/StockChartPanel.tsx` | Client | 2 — Chart + commentary + fundamentals |
| `FundamentalsStrip` | `v6/stock-detail/FundamentalsStrip.tsx` | Server | (child of Section 2) |
| `generateChartCommentary` | `v6/stock-detail/ChartCommentary.ts` | Pure fn | (called server-side in page.tsx) |
| `RSConfirmationPanel` | `v6/stock-detail/RSConfirmationPanel.tsx` | Client | 3 — RS confirmation |
| `LifecyclePanel` | `v6/stock-detail/LifecyclePanel.tsx` | Server | 4 — Lifecycle position |
| `PeerMatrix` | `v6/stock-detail/PeerMatrix.tsx` | Server | 5 — Peer comparison |
| (existing) `DwellTimeline` | `stocks/DwellTimeline.tsx` | Server | 6 — Supporting detail |
| (existing) `ComponentScorecard` | `stocks/ComponentScorecard.tsx` | Server | 6 — Supporting detail |
| (existing) `HitRateRow` | `stocks/HitRateRow.tsx` | Server | 6 — Supporting detail |
| (existing) `ActButton` | `portfolio/ActButton.tsx` | Client | 7 — Act |

## Appendix B: Data flow

```
page.tsx (server)
  │
  ├── Promise.all([
  │     getStockMetricHistory()   → metricHistory → latestMetrics
  │     getStockState()           → stockState
  │     getStateHistory()         → stateHistory
  │     getStockFooterMetrics()   → footerMetrics
  │     getStockTraderHeader()    → traderHeader
  │     getTVMetrics()            → tvMetrics (pe/ps/pb/d2e/roe now included)
  │     getRSRatios()             → rsRatios
  │     getPeerMatrix()           → peerMatrix
  │   ])
  │
  ├── generateChartCommentary()  → commentary (string)
  │
  └── JSX
        ├── TraderViewHeader(traderHeader)
        ├── EventHeader(stock, stockState, tvMetrics, latestMetrics)
        ├── StockChartPanel(symbol, commentary, tvMetrics[fundamentals])
        │     └── FundamentalsStrip(pe, ps, pb, d2e, roe)
        ├── RSConfirmationPanel(rsRatios)
        ├── LifecyclePanel(stockState, latestMetrics)
        ├── PeerMatrix(peerMatrix)
        ├── Section 6: DwellTimeline + ComponentScorecard + HitRateRow
        └── ActButton(portfolioId, sizing)
```

## Appendix C: API dependency matrix

| Component | Endpoint | Graceful fallback |
|---|---|---|
| `RSConfirmationPanel` | `GET /v1/stocks/{symbol}/rs-ratios?days=252` | Shows "unavailable" message |
| `PeerMatrix` | `GET /v1/stocks/{symbol}/peer-matrix` | Hidden (renders nothing when `peers.length === 0`) |
| `StockChartPanel` (fundamentals) | `GET /v1/tv/metrics/{symbol}` (extended) | Shows `—` in each pill |
| `StockChartPanel` (chart iframe) | TradingView widget CDN | Shows fallback with external link |

All four degrade gracefully — the page renders without error even if backend plan A is not yet deployed on EC2.

## Appendix D: Known type adjustments

1. **`stockState?.state_since_date`** — Check whether `StockState` in `@/lib/queries/states` includes `state_since_date`. If not, pass `null` explicitly for that field in the `generateChartCommentary` call. The field is in `CommentaryInput` for future use but not currently used in the prose output.

2. **`TVMetricsRow` fundamental fields** — `pe_ttm`, `ps_current`, `pb_fbs`, `debt_to_equity`, `roe` are typed as `number | null` after Task 1a. The backend returns them as `NUMERIC` which postgres.js may hand back as `string`. If the build emits type errors on those fields, cast with `Number(tvMetrics.pe_ttm)` rather than `parseFloat` (handles both `string` and `number` inputs).

3. **`metricHistory` ordering** — `getStockMetricHistory` returns rows `ORDER BY date ASC`. `metricHistory[metricHistory.length - 1]` is the most recent row. This is correct.
