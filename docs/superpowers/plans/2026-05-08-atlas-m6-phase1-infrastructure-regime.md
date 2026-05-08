# Atlas-OS M6 Frontend — Phase 1: Infrastructure, Auth, and Regime Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Atlas-OS M6 frontend foundation — design system, auth gate, DB client, shared UI components, and the `/` regime page (current market state + 6-month history timeline + all 18 breadth indicators with sparklines).

**Architecture:** Next.js 15 App Router, all pages Server Components. DB access via `postgres` npm package (server-only). Auth is an httpOnly-cookie password gate in `middleware.ts`. Temporal controls and benchmark selectors use URL search params so pages remain fully server-rendered. Atlas DS tokens live in Tailwind v4 CSS `@theme` block.

**Tech Stack:** Next.js 15, React 19, TypeScript (strict), Tailwind v4, `postgres` 3.4.5, Recharts, `@radix-ui/react-tooltip`, `lucide-react` 0.468.0, `server-only`, Vitest + React Testing Library (unit/component), Playwright (smoke)

**Working directory for all commands:** `frontend/`

---

## File Map

```
frontend/
  middleware.ts                                   AUTH: password gate
  vitest.config.ts                               TEST: vitest setup
  vitest.setup.ts                                TEST: jest-dom matchers
  playwright.config.ts                           TEST: e2e config
  .env.local.example                             DOCS: env var template

  src/
    app/
      globals.css                                DS: Tailwind v4 + Atlas tokens
      layout.tsx                                 LAYOUT: root layout, fonts, nav
      page.tsx                                   PAGE: / regime page (Server Component)
      error.tsx                                  LAYOUT: global error boundary
      loading.tsx                                LAYOUT: global loading skeleton
      login/
        page.tsx                                 AUTH: login form + server action

    components/
      nav/
        TopNav.tsx                               NAV: top navigation bar
        HealthDot.tsx                            NAV: last-run status dot
      ui/
        InfoTooltip.tsx                          UI: ⓘ tooltip (Radix, Client)
        StateBadge.tsx                           UI: regime/sector/stock state badge
        TimeRangeToggle.tsx                      UI: 1W|1M|3M|6M buttons (Client)
        BenchmarkSelector.tsx                    UI: benchmark dropdown (Client)
        Sparkline.tsx                            UI: SVG sparkline (pure, no deps)
        StateTimeline.tsx                        UI: horizontal state strip (SVG)
        DeltaBadge.tsx                           UI: ↑↓→ state change indicator
        Commentary.tsx                           UI: deterministic analysis paragraph
        LineChart.tsx                            UI: Recharts line + benchmark overlay (Client)
      regime/
        RegimeHeadline.tsx                       REGIME: Band 1 — current state
        RegimeHistoryTimeline.tsx                REGIME: Band 2 — history + Nifty overlay
        BreadthIndicators.tsx                    REGIME: Band 3 — all 18 indicators
        BreadthCategory.tsx                      REGIME: one indicator category card

    lib/
      db.ts                                      DB: postgres client (server-only)
      tooltips.ts                                DATA: all ⓘ tooltip strings
      queries/
        regime.ts                               DB: regime current + history queries
        benchmarks.ts                           DB: benchmark returns cache queries
        health.ts                               DB: run log query (for HealthDot)
      commentary/
        regime.ts                              LOGIC: generateRegimeCommentary()
        __tests__/
          regime.test.ts                       TEST: commentary unit tests

  playwright/
    smoke.spec.ts                              TEST: login + regime page loads
```

---

## Task 1: Install dependencies

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Install runtime dependencies**

```bash
cd frontend
npm install server-only @radix-ui/react-tooltip recharts
```

Expected: packages added to `dependencies` in `package.json`.

- [ ] **Step 2: Install dev dependencies**

```bash
npm install -D vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @playwright/test @types/recharts
```

Expected: packages added to `devDependencies`.

- [ ] **Step 3: Add test scripts to package.json**

Open `package.json` and add to `"scripts"`:

```json
"test": "vitest run",
"test:watch": "vitest",
"test:e2e": "playwright test",
"test:e2e:ui": "playwright test --ui"
```

- [ ] **Step 4: Install Playwright browsers**

```bash
npx playwright install chromium
```

Expected: Chromium browser downloaded.

- [ ] **Step 5: Verify install**

```bash
npm run dev &
sleep 3 && curl -s http://localhost:3000 | head -5
kill %1
```

Expected: some HTML output (even if it's an error about missing page — that's fine at this stage).

---

## Task 2: Configure Vitest

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`

- [ ] **Step 1: Create `vitest.config.ts`**

```typescript
// frontend/vitest.config.ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    exclude: ['node_modules', '.next', 'playwright'],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
})
```

- [ ] **Step 2: Create `vitest.setup.ts`**

```typescript
// frontend/vitest.setup.ts
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Run tests (should pass with 0 tests)**

```bash
npm test
```

Expected output: `0 tests passed` (no failures).

---

## Task 3: Configure Playwright

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/playwright/smoke.spec.ts` (placeholder)

- [ ] **Step 1: Create `playwright.config.ts`**

```typescript
// frontend/playwright.config.ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './playwright',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
})
```

- [ ] **Step 2: Create placeholder smoke spec**

```typescript
// frontend/playwright/smoke.spec.ts
import { test, expect } from '@playwright/test'

// Tests added in Task 25
test.describe('placeholder', () => {
  test('passes', async () => {
    expect(true).toBe(true)
  })
})
```

---

## Task 4: Environment variable template

**Files:**
- Create: `frontend/.env.local.example`

- [ ] **Step 1: Create `.env.local.example`**

```bash
# frontend/.env.local.example
# Copy to .env.local and fill in values. Never commit .env.local.

# Supabase Postgres connection string (atlas schema)
ATLAS_DB_URL=postgresql://user:password@host:5432/dbname?sslmode=require

# Internal auth password — shown on /login
ATLAS_PASSWORD=change-me
```

- [ ] **Step 2: Ensure .env.local is gitignored**

Check `frontend/.env.local` is in the root `.gitignore` (it already is per the project `.gitignore`). Confirm:

```bash
grep "frontend/.env.local" ../.gitignore
```

Expected: `frontend/.env.local` appears in output.

---

## Task 5: Atlas DS — Tailwind v4 tokens + globals

**Files:**
- Create: `frontend/src/app/globals.css`

- [ ] **Step 1: Create `globals.css` with Atlas DS tokens**

```css
/* frontend/src/app/globals.css */
@import "tailwindcss";

@theme {
  /* ── Atlas DS color palette ── */
  --color-paper:        #F8F4EC;
  --color-ink-primary:  #1A1714;
  --color-ink-secondary:#5A5248;
  --color-ink-tertiary: #8C8278;
  --color-paper-rule:   #C2B8A8;
  --color-signal-pos:   #2F6B43;   /* forest  — positive */
  --color-signal-neg:   #B0492C;   /* terracotta — negative */
  --color-signal-warn:  #B8860B;   /* ochre — warning */
  --color-accent:       #25394A;   /* slate */
  --color-teal:         #1D9E75;   /* Constructive regime */

  /* ── Typography — set by next/font CSS variables ── */
  --font-serif: var(--font-source-serif-4, "Georgia", serif);
  --font-sans:  var(--font-inter, system-ui, sans-serif);
  --font-mono:  var(--font-jetbrains-mono, "Menlo", monospace);

  /* ── Radii ── */
  --radius-card: 2px;

  /* ── Tabular numbers utility ── */
  --font-variant-numeric-card: tabular-nums;
}

/* Base resets */
*, *::before, *::after { box-sizing: border-box; }

html { font-family: var(--font-sans); background-color: var(--color-paper); color: var(--color-ink-primary); }

/* Tabular nums on all numeric elements */
[data-numeric], .tabular { font-variant-numeric: tabular-nums; }
```

- [ ] **Step 2: Verify Tailwind compiles**

```bash
npm run build 2>&1 | head -20
```

Expected: no CSS compilation errors (may fail on missing page.tsx — that's fine at this stage).

---

## Task 6: Fonts + Root Layout

**Files:**
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/error.tsx`
- Create: `frontend/src/app/loading.tsx`

- [ ] **Step 1: Create root layout**

```typescript
// frontend/src/app/layout.tsx
import type { Metadata } from 'next'
import { Source_Serif_4, Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'
import { TopNav } from '@/components/nav/TopNav'

const sourceSerif4 = Source_Serif_4({
  subsets: ['latin'],
  variable: '--font-source-serif-4',
  display: 'swap',
  weight: ['400', '600'],
})

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
  weight: ['400', '500'],
})

export const metadata: Metadata = {
  title: 'Atlas-OS',
  description: 'Fund manager research tool — Javeri Securities',
  robots: 'noindex, nofollow',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sourceSerif4.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body className="bg-paper min-h-screen">
        <TopNav />
        <main className="pt-14">{children}</main>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: Create error boundary**

```typescript
// frontend/src/app/error.tsx
'use client'
import { useEffect } from 'react'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => { console.error(error) }, [error])

  return (
    <div className="p-8 max-w-md mx-auto mt-16">
      <p className="font-sans text-sm text-ink-secondary mb-4">
        Something went wrong loading this page.
      </p>
      <button
        onClick={reset}
        className="font-sans text-sm text-accent underline"
      >
        Try again
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Create loading skeleton**

```typescript
// frontend/src/app/loading.tsx
export default function Loading() {
  return (
    <div className="p-8 max-w-5xl mx-auto animate-pulse">
      <div className="h-12 bg-paper-rule/40 rounded w-64 mb-4" />
      <div className="h-4 bg-paper-rule/40 rounded w-96 mb-2" />
      <div className="h-4 bg-paper-rule/40 rounded w-80" />
    </div>
  )
}
```

---

## Task 7: TopNav shell

**Files:**
- Create: `frontend/src/components/nav/TopNav.tsx`
- Create: `frontend/src/components/nav/HealthDot.tsx`

- [ ] **Step 1: Create HealthDot (async Server Component)**

```typescript
// frontend/src/components/nav/HealthDot.tsx
import { getLastRunStatus } from '@/lib/queries/health'

export async function HealthDot() {
  let status: 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'RUNNING' | 'UNKNOWN' = 'UNKNOWN'
  try {
    status = await getLastRunStatus()
  } catch {
    // DB unreachable — show unknown
  }

  const colors: Record<typeof status, string> = {
    SUCCESS: 'bg-signal-pos',
    FAILED: 'bg-signal-neg',
    PARTIAL: 'bg-signal-warn',
    RUNNING: 'bg-teal animate-pulse',
    UNKNOWN: 'bg-paper-rule',
  }

  return (
    <span
      title={`Last run: ${status}`}
      className={`inline-block w-2 h-2 rounded-full ${colors[status]}`}
    />
  )
}
```

- [ ] **Step 2: Create TopNav**

```typescript
// frontend/src/components/nav/TopNav.tsx
import Link from 'next/link'
import { Suspense } from 'react'
import { HealthDot } from './HealthDot'

const NAV_LINKS = [
  { href: '/',           label: 'Regime' },
  { href: '/sectors',    label: 'Sectors' },
  { href: '/stocks',     label: 'Stocks' },
  { href: '/etfs',       label: 'ETFs' },
  { href: '/funds',      label: 'Funds' },
  { href: '/health',     label: 'Health' },
]

export function TopNav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-14 bg-paper border-b border-paper-rule flex items-center px-6 gap-6">
      <span className="font-serif text-base font-semibold text-ink-primary mr-2">
        Atlas
      </span>

      {NAV_LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className="font-sans text-sm text-ink-secondary hover:text-ink-primary transition-colors"
        >
          {label}
        </Link>
      ))}

      <div className="ml-auto flex items-center gap-3">
        <Suspense fallback={<span className="inline-block w-2 h-2 rounded-full bg-paper-rule" />}>
          <HealthDot />
        </Suspense>
        {/* GlobalSearch added in Task 21 */}
      </div>
    </nav>
  )
}
```

---

## Task 8: Auth — middleware + login page

**Files:**
- Create: `frontend/middleware.ts`
- Create: `frontend/src/app/login/page.tsx`

- [ ] **Step 1: Create auth middleware**

```typescript
// frontend/middleware.ts
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const AUTH_COOKIE = 'atlas_auth'

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Always allow login page and Next.js internals
  if (pathname.startsWith('/login')) return NextResponse.next()

  const cookie = request.cookies.get(AUTH_COOKIE)
  const password = process.env.ATLAS_PASSWORD

  if (password && cookie?.value === password) {
    return NextResponse.next()
  }

  const loginUrl = new URL('/login', request.url)
  loginUrl.searchParams.set('from', pathname)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|robots.txt).*)'],
}
```

- [ ] **Step 2: Create login page with server action**

```typescript
// frontend/src/app/login/page.tsx
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>
}) {
  const { from } = await searchParams

  async function login(formData: FormData) {
    'use server'
    const password = formData.get('password') as string
    if (!password || password !== process.env.ATLAS_PASSWORD) {
      redirect(`/login?error=1${from ? `&from=${encodeURIComponent(from)}` : ''}`)
    }
    const cookieStore = await cookies()
    cookieStore.set('atlas_auth', password, {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60 * 24 * 7, // 7 days
    })
    redirect(from ?? '/')
  }

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center">
      <div className="border border-paper-rule rounded-[2px] p-8 w-80">
        <h1 className="font-serif text-xl text-ink-primary mb-1">Atlas-OS</h1>
        <p className="font-sans text-xs text-ink-tertiary mb-6">Javeri Securities</p>
        <form action={login} className="flex flex-col gap-3">
          <input
            type="password"
            name="password"
            placeholder="Password"
            autoFocus
            required
            className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-sans bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent"
          />
          <button
            type="submit"
            className="bg-accent text-paper font-sans text-sm py-2 rounded-[2px] hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Start dev server and verify redirect**

```bash
ATLAS_PASSWORD=test123 npm run dev &
sleep 4
curl -sI http://localhost:3000/ | grep -E "^(HTTP|location)"
kill %1
```

Expected: `HTTP/1.1 307` redirect to `/login`.

---

## Task 9: DB client

**Files:**
- Create: `frontend/src/lib/db.ts`

- [ ] **Step 1: Create server-only postgres client**

```typescript
// frontend/src/lib/db.ts
import 'server-only'
import postgres from 'postgres'

if (!process.env.ATLAS_DB_URL) {
  throw new Error('ATLAS_DB_URL is not defined. Set it in .env.local.')
}

const sql = postgres(process.env.ATLAS_DB_URL, {
  max: 5,
  idle_timeout: 20,
  connect_timeout: 10,
  ssl: process.env.ATLAS_DB_URL.includes('sslmode=require')
    ? { rejectUnauthorized: false }
    : false,
})

export default sql
```

---

## Task 10: Health query (for HealthDot)

**Files:**
- Create: `frontend/src/lib/queries/health.ts`

- [ ] **Step 1: Create health query**

```typescript
// frontend/src/lib/queries/health.ts
import 'server-only'
import sql from '@/lib/db'

export type RunStatus = 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'RUNNING' | 'UNKNOWN'

export async function getLastRunStatus(): Promise<RunStatus> {
  const rows = await sql<{ status: string }[]>`
    SELECT status
    FROM atlas.atlas_run_log
    ORDER BY business_date DESC, started_at DESC
    LIMIT 1
  `
  if (rows.length === 0) return 'UNKNOWN'
  return rows[0].status as RunStatus
}
```

---

## Task 11: Regime DB queries

**Files:**
- Create: `frontend/src/lib/queries/regime.ts`

- [ ] **Step 1: Define types and queries**

```typescript
// frontend/src/lib/queries/regime.ts
import 'server-only'
import sql from '@/lib/db'

// postgres returns NUMERIC as string — keep as string, parse at display time
export type MarketRegimeRow = {
  date: Date
  nifty500_close: string | null
  nifty500_ema_50: string | null
  nifty500_ema_200: string | null
  nifty500_above_ema_50: boolean
  nifty500_above_ema_200: boolean
  nifty500_ema_50_slope: string | null
  nifty500_ema_200_slope: string | null
  pct_above_ema_20: string | null
  pct_above_ema_50: string | null
  pct_above_ema_200: string | null
  advances_count: number | null
  declines_count: number | null
  unchanged_count: number | null
  ad_ratio: string | null
  ad_line: string | null
  ad_line_slope_21: string | null
  mcclellan_oscillator: string | null
  mcclellan_summation: string | null
  new_52w_highs: number | null
  new_52w_lows: number | null
  net_new_highs: number | null
  new_high_low_ratio: string | null
  pct_in_strong_states: string | null
  pct_weinstein_pass: string | null
  india_vix: string | null
  realized_vol_5d_nifty500: string | null
  vol_252_median_nifty500: string | null
  regime_state: string
  deployment_multiplier: string
  dislocation_active: boolean
  dislocation_started: Date | null
}

// Lighter type for history (sparkline data only)
export type RegimeHistoryRow = {
  date: Date
  regime_state: string
  deployment_multiplier: string
  nifty500_close: string | null
  pct_above_ema_20: string | null
  pct_above_ema_50: string | null
  pct_above_ema_200: string | null
  ad_ratio: string | null
  ad_line: string | null
  mcclellan_oscillator: string | null
  mcclellan_summation: string | null
  new_52w_highs: number | null
  new_52w_lows: number | null
  net_new_highs: number | null
  pct_in_strong_states: string | null
  pct_weinstein_pass: string | null
  india_vix: string | null
  nifty500_ema_50_slope: string | null
  nifty500_ema_200_slope: string | null
}

export async function getCurrentRegime(): Promise<MarketRegimeRow | null> {
  const rows = await sql<MarketRegimeRow[]>`
    SELECT *
    FROM atlas.atlas_market_regime_daily
    ORDER BY date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getRegimeHistory(days: number): Promise<RegimeHistoryRow[]> {
  return sql<RegimeHistoryRow[]>`
    SELECT
      date,
      regime_state,
      deployment_multiplier,
      nifty500_close,
      pct_above_ema_20,
      pct_above_ema_50,
      pct_above_ema_200,
      ad_ratio,
      ad_line,
      mcclellan_oscillator,
      mcclellan_summation,
      new_52w_highs,
      new_52w_lows,
      net_new_highs,
      pct_in_strong_states,
      pct_weinstein_pass,
      india_vix,
      nifty500_ema_50_slope,
      nifty500_ema_200_slope
    FROM atlas.atlas_market_regime_daily
    WHERE date >= NOW() - (${days} || ' days')::INTERVAL
    ORDER BY date ASC
  `
}
```

---

## Task 12: Benchmark DB queries

**Files:**
- Create: `frontend/src/lib/queries/benchmarks.ts`

- [ ] **Step 1: Define types and queries**

```typescript
// frontend/src/lib/queries/benchmarks.ts
import 'server-only'
import sql from '@/lib/db'

export type BenchmarkRow = {
  benchmark_code: string
  date: Date
  close: string
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
}

export type BenchmarkMeta = {
  benchmark_code: string
  benchmark_name: string
  benchmark_type: string
}

export async function getBenchmarkHistory(
  code: string,
  days: number
): Promise<BenchmarkRow[]> {
  return sql<BenchmarkRow[]>`
    SELECT benchmark_code, date, close, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m
    FROM atlas.atlas_benchmark_returns_cache
    WHERE benchmark_code = ${code}
      AND date >= NOW() - (${days} || ' days')::INTERVAL
    ORDER BY date ASC
  `
}

export async function getAllBenchmarks(): Promise<BenchmarkMeta[]> {
  return sql<BenchmarkMeta[]>`
    SELECT benchmark_code, benchmark_name, benchmark_type
    FROM atlas.atlas_benchmark_master
    WHERE is_active = TRUE
    ORDER BY benchmark_type, benchmark_code
  `
}
```

---

## Task 13: Commentary — regime

**Files:**
- Create: `frontend/src/lib/commentary/regime.ts`
- Create: `frontend/src/lib/commentary/__tests__/regime.test.ts`

- [ ] **Step 1: Write the failing test first**

```typescript
// frontend/src/lib/commentary/__tests__/regime.test.ts
import { describe, it, expect } from 'vitest'
import { generateRegimeCommentary, countBullishIndicators } from '../regime'
import type { MarketRegimeRow } from '@/lib/queries/regime'

const baseRegime: MarketRegimeRow = {
  date: new Date('2026-05-08'),
  regime_state: 'Risk-Off',
  deployment_multiplier: '0',
  dislocation_active: false,
  dislocation_started: null,
  india_vix: '22.5',
  nifty500_above_ema_50: false,
  nifty500_above_ema_200: false,
  pct_above_ema_20: '0.28',
  pct_above_ema_50: '0.32',
  pct_above_ema_200: '0.41',
  ad_ratio: '0.6',
  ad_line_slope_21: '-0.05',
  mcclellan_oscillator: '-45',
  mcclellan_summation: '-800',
  new_52w_highs: 12,
  new_52w_lows: 89,
  net_new_highs: -77,
  new_high_low_ratio: '0.13',
  pct_in_strong_states: '0.18',
  pct_weinstein_pass: '0.22',
  nifty500_ema_50_slope: '-0.3',
  nifty500_ema_200_slope: '-0.1',
  // unused in commentary
  nifty500_close: '21000',
  nifty500_ema_50: null,
  nifty500_ema_200: null,
  advances_count: 180,
  declines_count: 320,
  unchanged_count: 50,
  ad_line: '-1200',
  new_52w_lows: 89,
  new_52w_highs: 12,
  realized_vol_5d_nifty500: null,
  vol_252_median_nifty500: null,
}

describe('countBullishIndicators', () => {
  it('counts bearish indicators in risk-off regime', () => {
    const { bullish, total } = countBullishIndicators(baseRegime)
    expect(total).toBe(18)
    expect(bullish).toBeLessThan(9) // most should be bearish in risk-off
  })
})

describe('generateRegimeCommentary', () => {
  it('starts with regime state', () => {
    const result = generateRegimeCommentary(baseRegime)
    expect(result).toMatch(/^Market is in Risk-Off\./)
  })

  it('includes deployment percentage', () => {
    const result = generateRegimeCommentary(baseRegime)
    expect(result).toContain('0%')
  })

  it('includes VIX reading', () => {
    const result = generateRegimeCommentary(baseRegime)
    expect(result).toContain('22.5')
  })

  it('includes dislocation warning when active', () => {
    const result = generateRegimeCommentary({ ...baseRegime, dislocation_active: true })
    expect(result).toContain('Dislocation active')
  })

  it('does not include dislocation warning when inactive', () => {
    const result = generateRegimeCommentary(baseRegime)
    expect(result).not.toContain('Dislocation')
  })

  it('mentions breadth conviction', () => {
    const result = generateRegimeCommentary(baseRegime)
    expect(result).toMatch(/\d+ of 18/)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test src/lib/commentary/__tests__/regime.test.ts
```

Expected: FAIL — `generateRegimeCommentary is not a function`.

- [ ] **Step 3: Implement commentary module**

```typescript
// frontend/src/lib/commentary/regime.ts
import type { MarketRegimeRow } from '@/lib/queries/regime'

// Helper: parse string-NUMERIC to float, default 0
const f = (s: string | null | undefined): number =>
  s == null ? 0 : parseFloat(s)

// Classify each breadth indicator as bullish (true) or bearish (false)
function classifyIndicators(r: MarketRegimeRow): boolean[] {
  return [
    // Trend (4)
    r.nifty500_above_ema_50,
    r.nifty500_above_ema_200,
    f(r.nifty500_ema_50_slope) > 0,
    f(r.nifty500_ema_200_slope) > 0,
    // Breadth (7)
    f(r.pct_above_ema_20) > 0.5,
    f(r.pct_above_ema_50) > 0.5,
    f(r.pct_above_ema_200) > 0.5,
    f(r.ad_ratio) > 1,
    f(r.ad_line_slope_21) > 0,
    (r.new_52w_highs ?? 0) > (r.new_52w_lows ?? 0),
    f(r.new_high_low_ratio) > 1,
    // Momentum (4)
    f(r.mcclellan_oscillator) > 0,
    f(r.mcclellan_summation) > 0,
    f(r.net_new_highs ?? 0) > 0,
    (r.new_52w_highs ?? 0) > 20, // absolute new highs threshold
    // Participation (3)
    f(r.pct_in_strong_states) > 0.4,
    f(r.pct_weinstein_pass) > 0.4,
    f(r.pct_above_ema_50) > 0.45, // participation proxy (shared with breadth but distinct signal)
  ]
}

export function countBullishIndicators(r: MarketRegimeRow): {
  bullish: number
  total: number
} {
  const indicators = classifyIndicators(r)
  return {
    bullish: indicators.filter(Boolean).length,
    total: indicators.length,
  }
}

export function generateRegimeCommentary(r: MarketRegimeRow): string {
  const deployment = Math.round(f(r.deployment_multiplier) * 100)
  const vix = f(r.india_vix)
  const { bullish, total } = countBullishIndicators(r)
  const direction = bullish > total / 2 ? 'bullish' : 'bearish'
  const conviction =
    bullish <= total * 0.25 || bullish >= total * 0.75 ? 'high' : 'low'

  const parts: string[] = [
    `Market is in ${r.regime_state}.`,
    `${bullish} of ${total} breadth indicators are ${direction} — ${conviction}-conviction signal.`,
    `Deployment at ${deployment}%.`,
  ]

  if (vix > 0) {
    const vixLabel = vix > 25 ? 'elevated' : vix > 18 ? 'moderate' : 'low'
    parts.push(`India VIX at ${vix.toFixed(1)} — ${vixLabel} fear.`)
  }

  if (r.dislocation_active) {
    parts.push('Dislocation active — all new deployment suspended.')
  }

  return parts.join(' ')
}
```

- [ ] **Step 4: Run tests — must pass**

```bash
npm test src/lib/commentary/__tests__/regime.test.ts
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/commentary/
git commit -m "feat(M6): add regime commentary generator with tests"
```

---

## Task 14: Tooltip content — regime section

**Files:**
- Create: `frontend/src/lib/tooltips.ts`

- [ ] **Step 1: Create tooltip content module (regime section)**

```typescript
// frontend/src/lib/tooltips.ts

// Every ⓘ tooltip in the app. Add sections as pages are built.
// Format: one-sentence what-it-is, then how-it-works.

export const TOOLTIPS = {
  // ── Regime ──────────────────────────────────────────────────────────────
  regime_state: `The overall market environment: Risk-On (deploy fully), Constructive (deploy at 70%), Cautious (deploy at 40%), or Risk-Off (no new exposure). Determined by a weighted vote across 18 breadth indicators — see methodology §11.`,

  deployment_multiplier: `Scales all position sizes. 1.0× in Risk-On means a 3% base size stays 3%. 0.0× in Risk-Off means no new positions regardless of instrument signal. Applied as a multiplier to the base position size at the portfolio level.`,

  dislocation_active: `A macro shock event (e.g. circuit-breaker day, systemic volatility spike) that overrides the regime to 0× deployment regardless of breadth readings. Triggered when 5-day realized volatility on the Nifty 500 exceeds 3× the 252-day median.`,

  india_vix: `India VIX is the NSE's implied volatility index, derived from Nifty 50 options. Values above 20 indicate elevated fear. Not a directional signal on its own — used as a regime corroborator.`,

  pct_above_ema_20: `Percentage of the 750-stock universe whose closing price is above its 20-day exponential moving average. Values above 50% indicate broad short-term participation; below 30% indicate broad distribution.`,

  pct_above_ema_50: `Percentage of the 750-stock universe above their 50-day EMA. The primary breadth anchor in the Atlas methodology (§11.1). A reading above 60% supports Constructive or better; below 40% supports Cautious or worse.`,

  pct_above_ema_200: `Percentage of the universe above their 200-day EMA. A structural breadth measure. Persistent readings below 50% indicate a bear market environment.`,

  ad_ratio: `Advance/Decline ratio: stocks advancing today ÷ stocks declining. Values above 1 are bullish (more stocks rising than falling). Computed daily from close prices across the 750-stock universe.`,

  ad_line: `Cumulative Advance/Decline line: the running sum of (advances − declines) each day. A rising line confirms market breadth is healthy even if the index appears range-bound. Divergence between the index and A/D line is a leading warning signal.`,

  ad_line_slope_21: `21-day slope of the cumulative A/D line, expressed in σ units (standard deviation of daily A/D changes over the same period). Positive = line is rising; negative = line is falling. Values beyond ±1.5σ indicate strong directional breadth.`,

  mcclellan_oscillator: `EMA(19) of net daily advances minus EMA(39) of net daily advances. A momentum oscillator of breadth — positive values indicate improving breadth momentum, negative indicate deteriorating. Crossing zero is a transition signal.`,

  mcclellan_summation: `Running cumulative sum of the McClellan Oscillator. A rising Summation Index confirms a healthy market structure; declining confirms broad deterioration. The absolute level matters: deep negative values take time to recover.`,

  new_52w_highs: `Count of stocks in the universe making new 252-trading-day (52-week) closing highs today. A healthy bull market sees expanding new highs. Values below 20 in a rising index suggest a narrowing leadership — a warning sign.`,

  new_52w_lows: `Count of stocks in the universe making new 252-trading-day closing lows today. Rising new lows while the index holds its level is a classic breadth divergence — often precedes a broader decline.`,

  net_new_highs: `New 52-week highs minus new 52-week lows. Positive = more stocks at new highs than lows (bullish breadth expansion). Negative = more lows than highs (breadth deterioration or distribution).`,

  pct_in_strong_states: `Percentage of the universe classified as Leader, Strong, or Emerging in the Atlas RS state model. A high-quality breadth measure: it filters out stocks that are technically above a moving average but still in weak RS states.`,

  pct_weinstein_pass: `Percentage of the universe passing the Weinstein gate: price above the 30-week moving average AND that moving average has a positive slope over the last 4 weeks. A structural filter for Stage 2 uptrends per Stan Weinstein's Stage Analysis.`,

  nifty500_ema_50_slope: `Slope of the Nifty 500's 50-day EMA over the last 21 trading days, expressed in σ units. A positive slope confirms the index's trend is accelerating upward; a flattening or negative slope indicates a trend under stress.`,

  nifty500_ema_200_slope: `Slope of the Nifty 500's 200-day EMA over the last 21 trading days. A long-term structural indicator. Negative slope is a significant bear market signal.`,

  new_high_low_ratio: `New 52-week highs ÷ max(new 52-week lows, 1). Values above 1 are bullish (more highs than lows). Used as a normalized breadth measure that adjusts for total market participation.`,
} as const

export type TooltipKey = keyof typeof TOOLTIPS
```

---

## Task 15: Shared UI — InfoTooltip

**Files:**
- Create: `frontend/src/components/ui/InfoTooltip.tsx`
- Create: `frontend/src/components/ui/__tests__/InfoTooltip.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/ui/__tests__/InfoTooltip.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { InfoTooltip } from '../InfoTooltip'

describe('InfoTooltip', () => {
  it('renders the trigger button', () => {
    render(<InfoTooltip content="Test explanation" />)
    expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test — must fail**

```bash
npm test src/components/ui/__tests__/InfoTooltip.test.tsx
```

Expected: FAIL — `InfoTooltip is not a function`.

- [ ] **Step 3: Implement InfoTooltip**

```typescript
// frontend/src/components/ui/InfoTooltip.tsx
'use client'
import * as Tooltip from '@radix-ui/react-tooltip'
import { Info } from 'lucide-react'

type Props = {
  content: string
  className?: string
}

export function InfoTooltip({ content, className = '' }: Props) {
  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            aria-label="info"
            className={`inline-flex items-center text-ink-tertiary hover:text-ink-secondary transition-colors ml-0.5 ${className}`}
          >
            <Info size={12} strokeWidth={1.5} />
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            className="z-50 max-w-xs bg-paper border border-paper-rule rounded-[2px] px-3 py-2 text-xs font-sans text-ink-secondary shadow-sm"
            sideOffset={4}
          >
            {content}
            <Tooltip.Arrow className="fill-paper-rule" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
```

- [ ] **Step 4: Run test — must pass**

```bash
npm test src/components/ui/__tests__/InfoTooltip.test.tsx
```

Expected: PASS.

---

## Task 16: Shared UI — StateBadge

**Files:**
- Create: `frontend/src/components/ui/StateBadge.tsx`
- Create: `frontend/src/components/ui/__tests__/StateBadge.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/ui/__tests__/StateBadge.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StateBadge } from '../StateBadge'

describe('StateBadge', () => {
  it('renders the state label', () => {
    render(<StateBadge state="Risk-On" />)
    expect(screen.getByText('Risk-On')).toBeInTheDocument()
  })

  it('applies forest color for positive states', () => {
    const { container } = render(<StateBadge state="Risk-On" />)
    expect(container.firstChild).toHaveClass('text-signal-pos')
  })

  it('applies terracotta color for negative states', () => {
    const { container } = render(<StateBadge state="Risk-Off" />)
    expect(container.firstChild).toHaveClass('text-signal-neg')
  })

  it('applies ochre for warning states', () => {
    const { container } = render(<StateBadge state="Cautious" />)
    expect(container.firstChild).toHaveClass('text-signal-warn')
  })
})
```

- [ ] **Step 2: Run test — must fail**

```bash
npm test src/components/ui/__tests__/StateBadge.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement StateBadge**

```typescript
// frontend/src/components/ui/StateBadge.tsx

type StateColor = 'pos' | 'neg' | 'warn' | 'neutral' | 'accent'

const STATE_COLORS: Record<string, StateColor> = {
  // Regime
  'Risk-On':     'pos',
  'Constructive':'accent',
  'Cautious':    'warn',
  'Risk-Off':    'neg',
  'DISLOCATION_SUSPENDED': 'neg',
  // Sector
  'Overweight':  'pos',
  'Neutral':     'neutral',
  'Underweight': 'warn',
  'Avoid':       'neg',
  // RS states
  'Leader':      'pos',
  'Strong':      'pos',
  'Emerging':    'accent',
  'Average':     'neutral',
  'Consolidating': 'neutral',
  'Weak':        'warn',
  'Laggard':     'neg',
  // Momentum
  'Accelerating': 'pos',
  'Improving':    'pos',
  'Flat':         'neutral',
  'Deteriorating':'warn',
  'Collapsing':   'neg',
  // Risk
  'Low':          'pos',
  'Normal':       'neutral',
  'Elevated':     'warn',
  'High':         'neg',
  'Below Trend':  'neutral',
  // Fund
  'Recommended':  'pos',
  'Hold':         'neutral',
  'Reduce':       'warn',
  'Exit':         'neg',
  // Composition
  'Aligned':      'pos',
  'Mixed':        'neutral',
  'Misaligned':   'neg',
  // Holdings
  'Strong-Holdings': 'pos',
  'Decent':          'neutral',
  'Weak-Holdings':   'neg',
}

const COLOR_CLASSES: Record<StateColor, string> = {
  pos:     'text-signal-pos bg-signal-pos/10 border-signal-pos/20',
  neg:     'text-signal-neg bg-signal-neg/10 border-signal-neg/20',
  warn:    'text-signal-warn bg-signal-warn/10 border-signal-warn/20',
  neutral: 'text-ink-secondary bg-paper-rule/20 border-paper-rule',
  accent:  'text-accent bg-accent/10 border-accent/20',
}

type Props = {
  state: string
  size?: 'sm' | 'md'
  className?: string
}

export function StateBadge({ state, size = 'md', className = '' }: Props) {
  const color = STATE_COLORS[state] ?? 'neutral'
  const classes = COLOR_CLASSES[color]
  const sizeClasses = size === 'sm'
    ? 'text-xs px-1.5 py-0.5'
    : 'text-xs px-2 py-1'

  return (
    <span
      className={`inline-flex items-center font-sans font-medium border rounded-[2px] tabular-nums ${sizeClasses} ${classes} ${className}`}
    >
      {state}
    </span>
  )
}
```

- [ ] **Step 4: Run tests — must pass**

```bash
npm test src/components/ui/__tests__/StateBadge.test.tsx
```

Expected: PASS.

---

## Task 17: Shared UI — TimeRangeToggle + BenchmarkSelector

**Files:**
- Create: `frontend/src/components/ui/TimeRangeToggle.tsx`
- Create: `frontend/src/components/ui/BenchmarkSelector.tsx`

Both are Client Components because they manipulate URL search params.

- [ ] **Step 1: Create TimeRangeToggle**

```typescript
// frontend/src/components/ui/TimeRangeToggle.tsx
'use client'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

export type TimeRange = '1W' | '1M' | '3M' | '6M' | '1Y'

type Props = {
  value: TimeRange
  options?: TimeRange[]
  paramName?: string
}

export function TimeRangeToggle({
  value,
  options = ['1W', '1M', '3M', '6M'],
  paramName = 'range',
}: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  function select(range: TimeRange) {
    const params = new URLSearchParams(searchParams.toString())
    params.set(paramName, range)
    router.push(`${pathname}?${params.toString()}`)
  }

  return (
    <div className="inline-flex border border-paper-rule rounded-[2px] overflow-hidden" role="group" aria-label="Time range">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => select(opt)}
          className={`px-2 py-1 text-xs font-sans transition-colors
            ${opt === value
              ? 'bg-accent text-paper'
              : 'text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/20'
            }`}
          aria-pressed={opt === value}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}

export function rangeToDays(range: TimeRange): number {
  const map: Record<TimeRange, number> = {
    '1W': 7,
    '1M': 30,
    '3M': 90,
    '6M': 180,
    '1Y': 365,
  }
  return map[range]
}
```

- [ ] **Step 2: Create BenchmarkSelector**

```typescript
// frontend/src/components/ui/BenchmarkSelector.tsx
'use client'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

export type BenchmarkCode =
  | 'NIFTY50'
  | 'NIFTY500'
  | 'NIFTY100'
  | 'MIDCAP150'
  | 'SMALLCAP250'
  | 'GOLD'
  | 'MSCIWORLD'
  | 'SP500'

export const BENCHMARK_LABELS: Record<string, string> = {
  NIFTY50:       'Nifty 50',
  NIFTY500:      'Nifty 500',
  NIFTY100:      'Nifty 100',
  MIDCAP150:     'Midcap 150',
  SMALLCAP250:   'Smallcap 250',
  GOLD:          'Gold',
  MSCIWORLD:     'MSCI World',
  SP500:         'S&P 500',
  MICROCAP_CUSTOM: 'Microcap (Atlas)',
}

type Props = {
  value: string
  availableCodes: string[]
  paramName?: string
}

export function BenchmarkSelector({ value, availableCodes, paramName = 'benchmark' }: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  function select(code: string) {
    const params = new URLSearchParams(searchParams.toString())
    params.set(paramName, code)
    router.push(`${pathname}?${params.toString()}`)
  }

  return (
    <select
      value={value}
      onChange={(e) => select(e.target.value)}
      className="text-xs font-sans border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-secondary focus:outline-none focus:border-accent"
      aria-label="Benchmark"
    >
      {availableCodes.map((code) => (
        <option key={code} value={code}>
          vs. {BENCHMARK_LABELS[code] ?? code}
        </option>
      ))}
    </select>
  )
}
```

---

## Task 18: Shared UI — Sparkline

**Files:**
- Create: `frontend/src/components/ui/Sparkline.tsx`

The Sparkline is a pure presentational SVG component — no external chart library, no Client marker needed.

- [ ] **Step 1: Create Sparkline**

```typescript
// frontend/src/components/ui/Sparkline.tsx
type Props = {
  data: (number | null)[]
  width?: number
  height?: number
  color?: string
  className?: string
  /** Draw a horizontal reference line at this value */
  refLine?: number
}

export function Sparkline({
  data,
  width = 80,
  height = 24,
  color = 'currentColor',
  className = '',
  refLine,
}: Props) {
  const valid = data.filter((d): d is number => d !== null)
  if (valid.length < 2) return <span className={`inline-block w-[${width}px] h-[${height}px] ${className}`} />

  const min = Math.min(...valid)
  const max = Math.max(...valid)
  const range = max - min || 1

  const points = data
    .map((v, i) => {
      if (v === null) return null
      const x = (i / (data.length - 1)) * width
      const y = height - ((v - min) / range) * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .filter(Boolean)
    .join(' ')

  const refY = refLine !== undefined
    ? height - ((refLine - min) / range) * height
    : null

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`inline-block ${className}`}
      aria-hidden
    >
      {refY !== null && (
        <line
          x1={0} y1={refY} x2={width} y2={refY}
          stroke="var(--color-paper-rule)"
          strokeWidth={0.5}
          strokeDasharray="2,2"
        />
      )}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
```

---

## Task 19: Shared UI — StateTimeline

**Files:**
- Create: `frontend/src/components/ui/StateTimeline.tsx`

A horizontal strip showing state transitions over time. Used on the regime page (Band 2) and instrument detail pages.

- [ ] **Step 1: Create StateTimeline**

```typescript
// frontend/src/components/ui/StateTimeline.tsx
import type { RegimeHistoryRow } from '@/lib/queries/regime'

const STATE_COLORS: Record<string, string> = {
  'Risk-On':      'bg-signal-pos',
  'Constructive': 'bg-teal',
  'Cautious':     'bg-signal-warn',
  'Risk-Off':     'bg-signal-neg',
  // Sector states
  'Overweight':   'bg-signal-pos',
  'Neutral':      'bg-accent/40',
  'Underweight':  'bg-signal-warn',
  'Avoid':        'bg-signal-neg',
  // Generic fallback
  DEFAULT:        'bg-paper-rule',
}

type Segment = {
  state: string
  startDate: Date
  endDate: Date
  days: number
}

function buildSegments(rows: { date: Date; state: string }[]): Segment[] {
  if (rows.length === 0) return []
  const segments: Segment[] = []
  let current = rows[0]
  let startDate = rows[0].date

  for (let i = 1; i < rows.length; i++) {
    if (rows[i].state !== current.state) {
      segments.push({
        state: current.state,
        startDate,
        endDate: rows[i - 1].date,
        days: i - (segments.reduce((s, seg) => s + seg.days, 0)),
      })
      current = rows[i]
      startDate = rows[i].date
    }
  }
  segments.push({
    state: current.state,
    startDate,
    endDate: rows[rows.length - 1].date,
    days: rows.length - segments.reduce((s, seg) => s + seg.days, 0),
  })
  return segments
}

type Props = {
  rows: { date: Date; state: string }[]
  height?: number
  className?: string
}

export function StateTimeline({ rows, height = 12, className = '' }: Props) {
  const segments = buildSegments(rows)
  const total = segments.reduce((s, seg) => s + seg.days, 0)

  if (total === 0) return null

  return (
    <div
      className={`flex w-full rounded-[2px] overflow-hidden ${className}`}
      style={{ height }}
      role="img"
      aria-label={`State history: ${segments.map(s => s.state).join(' → ')}`}
    >
      {segments.map((seg, i) => {
        const pct = (seg.days / total) * 100
        const color = STATE_COLORS[seg.state] ?? STATE_COLORS.DEFAULT
        const label = formatDateLabel(seg.startDate)
        return (
          <div
            key={i}
            className={`${color} relative group`}
            style={{ width: `${pct}%` }}
            title={`${seg.state} — from ${label}`}
          />
        )
      })}
    </div>
  )
}

function formatDateLabel(d: Date): string {
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}
```

---

## Task 20: Shared UI — DeltaBadge + Commentary

**Files:**
- Create: `frontend/src/components/ui/DeltaBadge.tsx`
- Create: `frontend/src/components/ui/Commentary.tsx`

- [ ] **Step 1: Create DeltaBadge**

```typescript
// frontend/src/components/ui/DeltaBadge.tsx
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

type Direction = 'up' | 'down' | 'unchanged'

type Props = {
  direction: Direction
  label?: string
  className?: string
}

export function DeltaBadge({ direction, label, className = '' }: Props) {
  const config = {
    up:        { icon: TrendingUp,   color: 'text-signal-pos' },
    down:      { icon: TrendingDown, color: 'text-signal-neg' },
    unchanged: { icon: Minus,        color: 'text-ink-tertiary' },
  }[direction]

  const Icon = config.icon

  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-sans ${config.color} ${className}`}>
      <Icon size={12} strokeWidth={1.5} />
      {label && <span>{label}</span>}
    </span>
  )
}
```

- [ ] **Step 2: Create Commentary**

```typescript
// frontend/src/components/ui/Commentary.tsx
type Props = {
  text: string
  className?: string
}

export function Commentary({ text, className = '' }: Props) {
  return (
    <p className={`font-sans text-sm text-ink-secondary leading-relaxed ${className}`}>
      {text}
    </p>
  )
}
```

---

## Task 21: Shared UI — LineChart (Recharts, Client)

**Files:**
- Create: `frontend/src/components/ui/LineChart.tsx`

Used for the Nifty 500 price overlay on the regime history band and for NAV charts on fund detail pages.

- [ ] **Step 1: Create LineChart**

```typescript
// frontend/src/components/ui/LineChart.tsx
'use client'
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

type DataPoint = {
  date: string
  primary: number | null
  benchmark?: number | null
}

type Props = {
  data: DataPoint[]
  primaryLabel?: string
  benchmarkLabel?: string
  height?: number
  primaryColor?: string
  benchmarkColor?: string
  refLineY?: number
  className?: string
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

export function LineChart({
  data,
  primaryLabel = 'Value',
  benchmarkLabel,
  height = 120,
  primaryColor = 'var(--color-accent)',
  benchmarkColor = 'var(--color-paper-rule)',
  refLineY,
  className = '',
}: Props) {
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsLineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 10, fontFamily: 'var(--font-sans)', fill: 'var(--color-ink-tertiary)' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            width={36}
            tick={{ fontSize: 10, fontFamily: 'var(--font-mono)', fill: 'var(--color-ink-tertiary)' }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-paper)',
              border: '1px solid var(--color-paper-rule)',
              borderRadius: '2px',
              fontFamily: 'var(--font-sans)',
              fontSize: '11px',
              color: 'var(--color-ink-primary)',
            }}
            labelFormatter={formatDate}
          />
          {refLineY !== undefined && (
            <ReferenceLine y={refLineY} stroke="var(--color-paper-rule)" strokeDasharray="3 3" />
          )}
          <Line
            type="monotone"
            dataKey="primary"
            name={primaryLabel}
            stroke={primaryColor}
            strokeWidth={1.5}
            dot={false}
            connectNulls
          />
          {benchmarkLabel && (
            <Line
              type="monotone"
              dataKey="benchmark"
              name={benchmarkLabel}
              stroke={benchmarkColor}
              strokeWidth={1}
              strokeDasharray="4 2"
              dot={false}
              connectNulls
            />
          )}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

---

## Task 22: Regime page — Band 1 (RegimeHeadline)

**Files:**
- Create: `frontend/src/components/regime/RegimeHeadline.tsx`

- [ ] **Step 1: Create RegimeHeadline component**

```typescript
// frontend/src/components/regime/RegimeHeadline.tsx
import { StateBadge } from '@/components/ui/StateBadge'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { Commentary } from '@/components/ui/Commentary'
import { TOOLTIPS } from '@/lib/tooltips'
import { generateRegimeCommentary } from '@/lib/commentary/regime'
import type { MarketRegimeRow } from '@/lib/queries/regime'

type Props = {
  regime: MarketRegimeRow
}

const DEPLOYMENT_LABELS: Record<string, string> = {
  '1':   'Full deployment',
  '0.7': 'Reduced deployment',
  '0.4': 'Minimal deployment',
  '0':   'No new exposure',
}

export function RegimeHeadline({ regime }: Props) {
  const vix = regime.india_vix ? parseFloat(regime.india_vix).toFixed(1) : null
  const deployment = parseFloat(regime.deployment_multiplier)
  const deploymentPct = Math.round(deployment * 100)
  const deploymentLabel = DEPLOYMENT_LABELS[regime.deployment_multiplier] ?? `${deploymentPct}%`
  const commentary = generateRegimeCommentary(regime)
  const dataAsOf = regime.date instanceof Date
    ? regime.date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : String(regime.date)

  return (
    <div className="px-8 pt-8 pb-6 border-b border-paper-rule">
      <div className="flex items-start justify-between mb-2">
        {/* Regime state — dominant headline */}
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="font-serif text-4xl font-semibold text-ink-primary leading-none">
              {regime.regime_state}
            </h1>
            {regime.dislocation_active && (
              <span className="inline-flex items-center px-2 py-1 text-xs font-sans font-medium text-signal-neg border border-signal-neg/40 rounded-[2px] bg-signal-neg/5">
                Dislocation active since {regime.dislocation_started
                  ? new Date(regime.dislocation_started).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
                  : '–'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm font-sans text-ink-secondary">
            <span className="font-mono tabular-nums">
              Deployment: <span className="font-medium text-ink-primary">{deploymentPct}%</span>
              {' '}
              <span className="text-ink-tertiary">({deploymentLabel})</span>
              <InfoTooltip content={TOOLTIPS.deployment_multiplier} />
            </span>
            {vix && (
              <span className="font-mono tabular-nums">
                India VIX: <span className="font-medium text-ink-primary">{vix}</span>
                <InfoTooltip content={TOOLTIPS.india_vix} />
              </span>
            )}
          </div>
        </div>

        {/* Data freshness */}
        <span className="font-sans text-xs text-ink-tertiary mt-1">
          Data as of {dataAsOf}
        </span>
      </div>

      <Commentary text={commentary} className="mt-3 max-w-2xl" />
    </div>
  )
}
```

---

## Task 23: Regime page — Band 2 (RegimeHistoryTimeline)

**Files:**
- Create: `frontend/src/components/regime/RegimeHistoryTimeline.tsx`

- [ ] **Step 1: Create RegimeHistoryTimeline**

```typescript
// frontend/src/components/regime/RegimeHistoryTimeline.tsx
import { Suspense } from 'react'
import { StateTimeline } from '@/components/ui/StateTimeline'
import { LineChart } from '@/components/ui/LineChart'
import { TimeRangeToggle, type TimeRange } from '@/components/ui/TimeRangeToggle'
import { BenchmarkSelector } from '@/components/ui/BenchmarkSelector'
import type { RegimeHistoryRow } from '@/lib/queries/regime'
import type { BenchmarkRow } from '@/lib/queries/benchmarks'

type Props = {
  history: RegimeHistoryRow[]
  benchmarkData: BenchmarkRow[]
  benchmarkCode: string
  range: TimeRange
}

function buildPriceChartData(
  history: RegimeHistoryRow[],
  benchmarkData: BenchmarkRow[]
): { date: string; primary: number | null; benchmark: number | null }[] {
  const bmMap = new Map(benchmarkData.map((b) => [b.date.toISOString().slice(0, 10), b]))

  // Index both series to 100 at start
  let firstClose: number | null = null
  let firstBm: number | null = null

  return history.map((row) => {
    const dateKey = row.date instanceof Date
      ? row.date.toISOString().slice(0, 10)
      : String(row.date)
    const close = row.nifty500_close ? parseFloat(row.nifty500_close) : null
    const bm = bmMap.get(dateKey)?.close ? parseFloat(bmMap.get(dateKey)!.close) : null

    if (close !== null && firstClose === null) firstClose = close
    if (bm !== null && firstBm === null) firstBm = bm

    return {
      date: dateKey,
      primary: close !== null && firstClose !== null ? (close / firstClose) * 100 : null,
      benchmark: bm !== null && firstBm !== null ? (bm / firstBm) * 100 : null,
    }
  })
}

const BENCHMARK_LABELS: Record<string, string> = {
  NIFTY50:  'Nifty 50',
  NIFTY500: 'Nifty 500',
  NIFTY100: 'Nifty 100',
  GOLD:     'Gold',
}

export function RegimeHistoryTimeline({ history, benchmarkData, benchmarkCode, range }: Props) {
  const timelineRows = history.map((r) => ({
    date: r.date,
    state: r.regime_state,
  }))

  const priceData = buildPriceChartData(history, benchmarkData)

  // Build labeled segments for legend
  const uniqueStates = [...new Set(timelineRows.map((r) => r.state))]

  const STATE_LEGEND: Record<string, string> = {
    'Risk-On':      'bg-signal-pos',
    'Constructive': 'bg-teal',
    'Cautious':     'bg-signal-warn',
    'Risk-Off':     'bg-signal-neg',
  }

  return (
    <div className="px-8 py-6 border-b border-paper-rule">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h2 className="font-sans text-sm font-medium text-ink-primary">Regime history</h2>
          <div className="flex items-center gap-2">
            {uniqueStates.map((s) => (
              <span key={s} className="flex items-center gap-1 text-xs font-sans text-ink-secondary">
                <span className={`inline-block w-2.5 h-2.5 rounded-[1px] ${STATE_LEGEND[s] ?? 'bg-paper-rule'}`} />
                {s}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Suspense>
            <BenchmarkSelector
              value={benchmarkCode}
              availableCodes={['NIFTY50', 'NIFTY500', 'NIFTY100', 'GOLD', 'MSCIWORLD', 'SP500']}
            />
            <TimeRangeToggle value={range} options={['1M', '3M', '6M', '1Y']} />
          </Suspense>
        </div>
      </div>

      {/* State strip */}
      <StateTimeline rows={timelineRows} height={16} className="mb-3" />

      {/* Nifty 500 price line indexed to 100, with benchmark overlay */}
      <LineChart
        data={priceData}
        primaryLabel="Nifty 500"
        benchmarkLabel={BENCHMARK_LABELS[benchmarkCode] ?? benchmarkCode}
        height={100}
      />
    </div>
  )
}
```

---

## Task 24: Regime page — Band 3 (BreadthIndicators)

**Files:**
- Create: `frontend/src/components/regime/BreadthCategory.tsx`
- Create: `frontend/src/components/regime/BreadthIndicators.tsx`

- [ ] **Step 1: Create BreadthCategory**

```typescript
// frontend/src/components/regime/BreadthCategory.tsx
import { Sparkline } from '@/components/ui/Sparkline'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { TOOLTIPS, type TooltipKey } from '@/lib/tooltips'

export type IndicatorRow = {
  key: string
  label: string
  tooltipKey: TooltipKey
  current: number | null
  isBullish: boolean | null      // null = neutral/unknown
  history: (number | null)[]
  format: (v: number) => string  // display formatter
  refLine?: number               // horizontal reference line on sparkline
}

type Props = {
  title: string
  indicators: IndicatorRow[]
  bullishCount: number
  totalCount: number
  commentary: string
}

function SignalDot({ isBullish }: { isBullish: boolean | null }) {
  if (isBullish === null) return <span className="inline-block w-2 h-2 rounded-full bg-paper-rule" />
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${isBullish ? 'bg-signal-pos' : 'bg-signal-neg'}`}
    />
  )
}

function ArrowIndicator({ isBullish }: { isBullish: boolean | null }) {
  if (isBullish === null) return <span className="text-ink-tertiary text-xs">→</span>
  return (
    <span className={`text-xs font-mono ${isBullish ? 'text-signal-pos' : 'text-signal-neg'}`}>
      {isBullish ? '↑' : '↓'}
    </span>
  )
}

export function BreadthCategory({ title, indicators, bullishCount, totalCount, commentary }: Props) {
  const convictionPct = Math.round((bullishCount / totalCount) * 100)
  const convictionColor =
    convictionPct >= 70 ? 'text-signal-pos' :
    convictionPct <= 30 ? 'text-signal-neg' :
    'text-signal-warn'

  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      {/* Category header */}
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-sans text-sm font-medium text-ink-primary">{title}</h3>
        <span className={`font-mono text-xs tabular-nums font-medium ${convictionColor}`}>
          {bullishCount}/{totalCount} bullish
        </span>
      </div>
      <p className="font-sans text-xs text-ink-tertiary mb-4">{commentary}</p>

      {/* Indicator rows */}
      <div className="space-y-2">
        {indicators.map((ind) => (
          <div key={ind.key} className="flex items-center gap-2">
            <SignalDot isBullish={ind.isBullish} />
            <span className="font-sans text-xs text-ink-secondary w-40 truncate flex-shrink-0">
              {ind.label}
              <InfoTooltip content={TOOLTIPS[ind.tooltipKey]} />
            </span>
            <span className="font-mono text-xs tabular-nums text-ink-primary w-16 text-right flex-shrink-0">
              {ind.current !== null ? ind.format(ind.current) : '–'}
            </span>
            <ArrowIndicator isBullish={ind.isBullish} />
            <Sparkline
              data={ind.history}
              width={80}
              height={20}
              color={ind.isBullish ? 'var(--color-signal-pos)' : ind.isBullish === false ? 'var(--color-signal-neg)' : 'var(--color-ink-tertiary)'}
              refLine={ind.refLine}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create BreadthIndicators**

```typescript
// frontend/src/components/regime/BreadthIndicators.tsx
import { Suspense } from 'react'
import { BreadthCategory, type IndicatorRow } from './BreadthCategory'
import { TimeRangeToggle, type TimeRange } from '@/components/ui/TimeRangeToggle'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import type { RegimeHistoryRow, MarketRegimeRow } from '@/lib/queries/regime'

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const num = (v: number) => v.toFixed(2)
const int = (v: number) => v.toFixed(0)

type Props = {
  current: MarketRegimeRow
  history: RegimeHistoryRow[]
  range: TimeRange
}

export function BreadthIndicators({ current, history, range }: Props) {
  const f = (s: string | null | undefined) =>
    s == null ? null : parseFloat(s)

  // Extract sparkline data for a metric from history
  const spark = (getter: (r: RegimeHistoryRow) => string | number | null | undefined) =>
    history.map((r) => {
      const v = getter(r)
      return v !== null && v !== undefined ? parseFloat(String(v)) : null
    })

  const trendIndicators: IndicatorRow[] = [
    {
      key: 'above_ema_50',
      label: 'Above 50-day EMA',
      tooltipKey: 'nifty500_ema_50_slope',
      current: current.nifty500_above_ema_50 ? 1 : 0,
      isBullish: current.nifty500_above_ema_50,
      history: spark((r) => r.nifty500_ema_50_slope), // proxy
      format: (v) => v === 1 ? 'Yes' : 'No',
    },
    {
      key: 'above_ema_200',
      label: 'Above 200-day EMA',
      tooltipKey: 'nifty500_ema_200_slope',
      current: current.nifty500_above_ema_200 ? 1 : 0,
      isBullish: current.nifty500_above_ema_200,
      history: spark((r) => r.nifty500_ema_200_slope),
      format: (v) => v === 1 ? 'Yes' : 'No',
    },
    {
      key: 'ema50_slope',
      label: '50-day EMA slope',
      tooltipKey: 'nifty500_ema_50_slope',
      current: f(current.nifty500_ema_50_slope),
      isBullish: f(current.nifty500_ema_50_slope) !== null ? f(current.nifty500_ema_50_slope)! > 0 : null,
      history: spark((r) => r.nifty500_ema_50_slope),
      format: (v) => `${v.toFixed(2)}σ`,
      refLine: 0,
    },
    {
      key: 'ema200_slope',
      label: '200-day EMA slope',
      tooltipKey: 'nifty500_ema_200_slope',
      current: f(current.nifty500_ema_200_slope),
      isBullish: f(current.nifty500_ema_200_slope) !== null ? f(current.nifty500_ema_200_slope)! > 0 : null,
      history: spark((r) => r.nifty500_ema_200_slope),
      format: (v) => `${v.toFixed(2)}σ`,
      refLine: 0,
    },
  ]

  const breadthIndicators: IndicatorRow[] = [
    {
      key: 'pct_ema20',
      label: '% above 20-day EMA',
      tooltipKey: 'pct_above_ema_20',
      current: f(current.pct_above_ema_20),
      isBullish: f(current.pct_above_ema_20) !== null ? f(current.pct_above_ema_20)! > 0.5 : null,
      history: spark((r) => r.pct_above_ema_20),
      format: pct,
      refLine: 0.5,
    },
    {
      key: 'pct_ema50',
      label: '% above 50-day EMA',
      tooltipKey: 'pct_above_ema_50',
      current: f(current.pct_above_ema_50),
      isBullish: f(current.pct_above_ema_50) !== null ? f(current.pct_above_ema_50)! > 0.5 : null,
      history: spark((r) => r.pct_above_ema_50),
      format: pct,
      refLine: 0.5,
    },
    {
      key: 'pct_ema200',
      label: '% above 200-day EMA',
      tooltipKey: 'pct_above_ema_200',
      current: f(current.pct_above_ema_200),
      isBullish: f(current.pct_above_ema_200) !== null ? f(current.pct_above_ema_200)! > 0.5 : null,
      history: spark((r) => r.pct_above_ema_200),
      format: pct,
      refLine: 0.5,
    },
    {
      key: 'ad_ratio',
      label: 'Advance/Decline ratio',
      tooltipKey: 'ad_ratio',
      current: f(current.ad_ratio),
      isBullish: f(current.ad_ratio) !== null ? f(current.ad_ratio)! > 1 : null,
      history: spark((r) => r.ad_ratio),
      format: num,
      refLine: 1,
    },
    {
      key: 'ad_line_slope',
      label: 'A/D line slope (21D)',
      tooltipKey: 'ad_line_slope_21',
      current: f(current.ad_line_slope_21),
      isBullish: f(current.ad_line_slope_21) !== null ? f(current.ad_line_slope_21)! > 0 : null,
      history: spark((r) => r.ad_line),
      format: (v) => `${v.toFixed(2)}σ`,
      refLine: 0,
    },
    {
      key: 'new_highs',
      label: 'New 52W highs',
      tooltipKey: 'new_52w_highs',
      current: current.new_52w_highs,
      isBullish: current.new_52w_highs !== null && current.new_52w_lows !== null
        ? current.new_52w_highs > (current.new_52w_lows ?? 0)
        : null,
      history: spark((r) => r.new_52w_highs),
      format: int,
    },
    {
      key: 'hl_ratio',
      label: 'Highs/Lows ratio',
      tooltipKey: 'new_high_low_ratio',
      current: f(current.new_high_low_ratio),
      isBullish: f(current.new_high_low_ratio) !== null ? f(current.new_high_low_ratio)! > 1 : null,
      history: spark((r) => r.new_high_low_ratio),
      format: num,
      refLine: 1,
    },
  ]

  const momentumIndicators: IndicatorRow[] = [
    {
      key: 'mcclellan_osc',
      label: 'McClellan Oscillator',
      tooltipKey: 'mcclellan_oscillator',
      current: f(current.mcclellan_oscillator),
      isBullish: f(current.mcclellan_oscillator) !== null ? f(current.mcclellan_oscillator)! > 0 : null,
      history: spark((r) => r.mcclellan_oscillator),
      format: num,
      refLine: 0,
    },
    {
      key: 'mcclellan_sum',
      label: 'McClellan Summation',
      tooltipKey: 'mcclellan_summation',
      current: f(current.mcclellan_summation),
      isBullish: f(current.mcclellan_summation) !== null ? f(current.mcclellan_summation)! > 0 : null,
      history: spark((r) => r.mcclellan_summation),
      format: num,
      refLine: 0,
    },
    {
      key: 'net_new_highs',
      label: 'Net new highs',
      tooltipKey: 'new_52w_highs',
      current: current.net_new_highs,
      isBullish: current.net_new_highs !== null ? current.net_new_highs > 0 : null,
      history: spark((r) => r.net_new_highs),
      format: int,
      refLine: 0,
    },
    {
      key: 'new_lows',
      label: 'New 52W lows',
      tooltipKey: 'new_52w_lows',
      current: current.new_52w_lows,
      isBullish: current.new_52w_lows !== null ? current.new_52w_lows < 20 : null,
      history: spark((r) => r.new_52w_lows),
      format: int,
    },
  ]

  const participationIndicators: IndicatorRow[] = [
    {
      key: 'pct_strong',
      label: '% in Strong states',
      tooltipKey: 'pct_in_strong_states',
      current: f(current.pct_in_strong_states),
      isBullish: f(current.pct_in_strong_states) !== null ? f(current.pct_in_strong_states)! > 0.4 : null,
      history: spark((r) => r.pct_in_strong_states),
      format: pct,
      refLine: 0.4,
    },
    {
      key: 'pct_weinstein',
      label: '% Weinstein pass',
      tooltipKey: 'pct_weinstein_pass',
      current: f(current.pct_weinstein_pass),
      isBullish: f(current.pct_weinstein_pass) !== null ? f(current.pct_weinstein_pass)! > 0.4 : null,
      history: spark((r) => r.pct_weinstein_pass),
      format: pct,
      refLine: 0.4,
    },
    {
      key: 'participation_50',
      label: 'Broad participation (50D)',
      tooltipKey: 'pct_above_ema_50',
      current: f(current.pct_above_ema_50),
      isBullish: f(current.pct_above_ema_50) !== null ? f(current.pct_above_ema_50)! > 0.45 : null,
      history: spark((r) => r.pct_above_ema_50),
      format: pct,
      refLine: 0.45,
    },
  ]

  const allIndicators = [
    ...trendIndicators,
    ...breadthIndicators,
    ...momentumIndicators,
    ...participationIndicators,
  ]
  const totalBullish = allIndicators.filter((i) => i.isBullish === true).length
  const total = allIndicators.filter((i) => i.isBullish !== null).length

  const countBullish = (inds: IndicatorRow[]) => inds.filter((i) => i.isBullish === true).length

  return (
    <div className="px-8 py-6">
      {/* Overall corroboration header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h2 className="font-sans text-sm font-medium text-ink-primary">Breadth indicators</h2>
          <span className={`font-mono text-xs tabular-nums font-medium ${
            totalBullish / total < 0.3 ? 'text-signal-neg' :
            totalBullish / total > 0.7 ? 'text-signal-pos' : 'text-signal-warn'
          }`}>
            {totalBullish} of {total} bullish
          </span>
          <InfoTooltip content="Breadth indicators measure market participation. When multiple independent measures align, the regime signal has higher conviction." />
        </div>
        <Suspense>
          <TimeRangeToggle value={range} paramName="breadth_range" />
        </Suspense>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <BreadthCategory
          title="Trend"
          indicators={trendIndicators}
          bullishCount={countBullish(trendIndicators)}
          totalCount={trendIndicators.length}
          commentary="Nifty 500 position and slope relative to key EMAs."
        />
        <BreadthCategory
          title="Breadth"
          indicators={breadthIndicators}
          bullishCount={countBullish(breadthIndicators)}
          totalCount={breadthIndicators.length}
          commentary="Advance/decline dynamics and participation across the 750-stock universe."
        />
        <BreadthCategory
          title="Momentum"
          indicators={momentumIndicators}
          bullishCount={countBullish(momentumIndicators)}
          totalCount={momentumIndicators.length}
          commentary="McClellan oscillator and net new highs measure momentum of market breadth."
        />
        <BreadthCategory
          title="Participation"
          indicators={participationIndicators}
          bullishCount={countBullish(participationIndicators)}
          totalCount={participationIndicators.length}
          commentary="Quality of participation — Leader/Strong/Emerging stocks and Weinstein gate pass rate."
        />
      </div>
    </div>
  )
}
```

---

## Task 25: Regime page — root `page.tsx`

**Files:**
- Create: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create the regime page (Server Component)**

```typescript
// frontend/src/app/page.tsx
import { Suspense } from 'react'
import { getCurrentRegime, getRegimeHistory } from '@/lib/queries/regime'
import { getBenchmarkHistory } from '@/lib/queries/benchmarks'
import { RegimeHeadline } from '@/components/regime/RegimeHeadline'
import { RegimeHistoryTimeline } from '@/components/regime/RegimeHistoryTimeline'
import { BreadthIndicators } from '@/components/regime/BreadthIndicators'
import { rangeToDays, type TimeRange } from '@/components/ui/TimeRangeToggle'

type SearchParams = Promise<{ range?: string; benchmark?: string; breadth_range?: string }>

export default async function RegimePage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M', benchmark = 'NIFTY500', breadth_range = '3M' } = await searchParams

  const historyRange = range as TimeRange
  const breadthRange = breadth_range as TimeRange
  const historyDays = rangeToDays(historyRange)
  const breadthDays = rangeToDays(breadthRange)

  const [current, historyFull, breadthHistory, benchmarkData] = await Promise.all([
    getCurrentRegime(),
    getRegimeHistory(historyDays),
    getRegimeHistory(breadthDays),
    getBenchmarkHistory(benchmark, historyDays),
  ])

  if (!current) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No regime data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Band 1 — Current regime state */}
      <RegimeHeadline regime={current} />

      {/* Band 2 — History timeline */}
      <Suspense fallback={<div className="px-8 py-6 border-b border-paper-rule h-48 animate-pulse bg-paper-rule/10" />}>
        <RegimeHistoryTimeline
          history={historyFull}
          benchmarkData={benchmarkData}
          benchmarkCode={benchmark}
          range={historyRange}
        />
      </Suspense>

      {/* Band 3 — Breadth indicators */}
      <BreadthIndicators
        current={current}
        history={breadthHistory}
        range={breadthRange}
      />
    </div>
  )
}
```

---

## Task 26: Smoke tests (Playwright)

**Files:**
- Modify: `frontend/playwright/smoke.spec.ts`

- [ ] **Step 1: Write smoke tests**

```typescript
// frontend/playwright/smoke.spec.ts
import { test, expect } from '@playwright/test'

const PASSWORD = process.env.ATLAS_PASSWORD ?? 'test123'

test.describe('Auth gate', () => {
  test('redirects unauthenticated users to /login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
  })

  test('login page renders the form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Atlas-OS' })).toBeVisible()
    await expect(page.getByPlaceholder('Password')).toBeVisible()
  })

  test('correct password grants access', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL('/')
  })

  test('wrong password stays on login', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('Password').fill('wrong')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/login/)
  })
})

test.describe('Regime page', () => {
  test.beforeEach(async ({ page }) => {
    // Authenticate first
    await page.goto('/login')
    await page.getByPlaceholder('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForURL('/')
  })

  test('renders regime state headline', async ({ page }) => {
    // One of the four regime states should be visible
    const regimeStates = ['Risk-On', 'Constructive', 'Cautious', 'Risk-Off']
    const found = await Promise.any(
      regimeStates.map((s) =>
        page.getByRole('heading', { level: 1, name: s }).isVisible().then((v) => {
          if (!v) throw new Error()
          return s
        })
      )
    ).catch(() => null)
    expect(found).not.toBeNull()
  })

  test('renders deployment multiplier', async ({ page }) => {
    await expect(page.getByText(/Deployment:/)).toBeVisible()
  })

  test('renders breadth indicators section', async ({ page }) => {
    await expect(page.getByText('Breadth indicators')).toBeVisible()
  })

  test('time range toggle is visible and functional', async ({ page }) => {
    await expect(page.getByRole('group', { name: 'Time range' }).first()).toBeVisible()
    await page.getByRole('button', { name: '1M' }).first().click()
    await expect(page).toHaveURL(/range=1M/)
  })
})
```

- [ ] **Step 2: Run smoke tests (requires ATLAS_DB_URL and ATLAS_PASSWORD to be set in .env.local)**

```bash
ATLAS_PASSWORD=test123 npm run test:e2e 2>&1 | tail -20
```

Expected: Auth tests pass. Regime page tests pass if DB is available, or show graceful "No regime data" message.

---

## Task 27: Final commit

- [ ] **Step 1: Run all unit tests**

```bash
npm test
```

Expected: All pass.

- [ ] **Step 2: Run type check**

```bash
npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 3: Run lint**

```bash
npm run lint
```

Expected: No errors.

- [ ] **Step 4: Commit everything**

```bash
cd ..  # return to atlas-os root
git add frontend/
git commit -m "feat(M6-P1): infrastructure, auth, shared components, and regime page

- Tailwind v4 Atlas DS tokens, fonts (Source Serif 4, Inter, JetBrains Mono)
- env-var password gate middleware + login page
- Server-only postgres client
- Shared UI: InfoTooltip, StateBadge, TimeRangeToggle, BenchmarkSelector,
  Sparkline, StateTimeline, DeltaBadge, Commentary, LineChart
- Regime page: Band 1 (current state), Band 2 (6M history + benchmark overlay),
  Band 3 (18 breadth indicators in 4 categories with sparklines)
- Regime commentary generator with unit tests
- Tooltip content library (regime section)
- Playwright smoke tests: auth + regime page

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Spec coverage check

| Spec section | Task(s) |
|---|---|
| Auth gate (§3, §8) | Task 8 |
| Atlas DS tokens (§2) | Task 5 |
| Fonts (§2) | Task 6 |
| DB client (§8) | Task 9 |
| TopNav (§5) | Task 7 |
| HealthDot in nav (§5) | Task 7, 10 |
| Global search in nav (§5) | Deferred to Phase 2 (requires more routes to search) |
| ⓘ tooltips (§6.1) | Tasks 14, 15 |
| Temporal controls (§6.1) | Task 17 |
| Benchmark overlay (§6.2) | Tasks 12, 17, 21 |
| Deterministic commentary (§6.4) | Tasks 13, 20 |
| Delta badges (§6.5) | Task 20 |
| Regime page Band 1 (§7.1) | Task 22 |
| Regime page Band 2 (§7.1) | Task 23 |
| Regime page Band 3 — all 18 indicators (§7.1) | Task 24 |
| `/` page assembly (§7.1) | Task 25 |

**GlobalSearch deferred:** GlobalSearch (Task 21 slot in TopNav) requires searching stocks + ETFs + funds. Deferred to Phase 2 when those query modules exist. TopNav has a comment marking where it plugs in.
