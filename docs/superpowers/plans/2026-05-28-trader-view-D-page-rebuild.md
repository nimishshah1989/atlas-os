# Stream D — Per-Page UI Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert every instrument deep-dive page to the trader-view pattern (verdict pill + return + tier badge + first-called line + why-strip + tracking grid + collapsed math). Start with `/stocks/[symbol]`, hold a checkpoint, then propagate to `/etfs`, `/sectors`, `/funds`, and the homepage top-conviction list.

**Architecture:** Five new shared components in `frontend/src/components/v6/trader-view/`. Each consuming page imports them and feeds the data from stream C's verdict columns. Old per-page header components retired only after the new pattern is QA'd live.

**Tech Stack:** Next.js 15.3.9 App Router, React Server Components, Tailwind CSS, Recharts (for tracking sparkline if added). No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-28-trader-view-redesign.html` §8.
**Visual reference:** `docs/v6/mockup-trader-view.html`.

**Dependency:** stream C must land first — components read `combined_verdict`, `verdict_reason`, `first_called_at`, `since_call_return` columns.

---

### Task 1: Build the five shared components

**Files:**
- Create: `frontend/src/components/v6/trader-view/VerdictPill.tsx`
- Create: `frontend/src/components/v6/trader-view/ReturnLine.tsx`
- Create: `frontend/src/components/v6/trader-view/SinceCallLine.tsx`
- Create: `frontend/src/components/v6/trader-view/WhyStrip.tsx`
- Create: `frontend/src/components/v6/trader-view/TrackingGrid.tsx`
- Create: `frontend/src/components/v6/trader-view/index.ts`

- [ ] **Step 1: VerdictPill component**

```tsx
// frontend/src/components/v6/trader-view/VerdictPill.tsx
import type { Verdict } from '@/lib/queries/v6/types'

const COLORS: Record<Verdict, string> = {
  BUY:        'bg-signal-pos text-paper',
  ACCUMULATE: 'bg-signal-pos text-paper',
  WATCH:      'bg-ink-tertiary text-paper',
  HOLD:       'bg-ink-tertiary text-paper',
  AVOID:      'bg-signal-neg text-paper',
  SELL:       'bg-signal-neg text-paper',
  WAIT:       'bg-signal-warn text-paper',
}

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-block font-serif text-[34px] font-medium px-[22px] py-[6px] leading-[1.1] rounded-sm ${COLORS[verdict]}`}
      data-testid="verdict-pill"
      data-verdict={verdict}
    >
      {verdict}
    </span>
  )
}
```

- [ ] **Step 2: ReturnLine component**

```tsx
// frontend/src/components/v6/trader-view/ReturnLine.tsx
import { fmtSignedPct } from '@/lib/format-number'

interface ReturnLineProps {
  predictedExcess: number | null
  tenure: '1m' | '3m' | '6m' | '12m'
  tier: string | null    // T1 / T2 / T3 …
  isVeto: boolean
}

export function ReturnLine({ predictedExcess, tenure, tier, isVeto }: ReturnLineProps) {
  const numClass = predictedExcess == null
    ? 'text-ink-tertiary'
    : predictedExcess >= 0 ? 'text-signal-pos' : 'text-signal-neg'

  const label = isVeto ? 'Cell suggests' : 'Expected'
  return (
    <div className="font-mono text-[15px] text-ink-secondary flex items-center gap-3 flex-wrap">
      <span>
        {label}{' '}
        <span className={`font-semibold ${numClass}`}>
          {predictedExcess != null ? fmtSignedPct(predictedExcess) : '—'}
        </span>
        {' '}over {tenure.toUpperCase()}
      </span>
      {tier && (
        <span className="text-[10px] font-bold tracking-wider px-2 py-0.5 bg-accent/10 text-accent rounded-sm">
          {tier} conviction
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 3: SinceCallLine component**

```tsx
// frontend/src/components/v6/trader-view/SinceCallLine.tsx
import { formatIST } from '@/lib/format-date'
import { fmtSignedPct } from '@/lib/format-number'

interface SinceCallLineProps {
  firstCalledAt: string | null         // ISO date
  verdict: string                      // human-readable verb ("BUY", "SELL", etc.)
  daysHeld: number | null
  sinceCallReturn: number | null
}

export function SinceCallLine({ firstCalledAt, verdict, daysHeld, sinceCallReturn }: SinceCallLineProps) {
  if (firstCalledAt == null) {
    return <div className="text-[12px] text-ink-tertiary">No tracked call yet.</div>
  }
  const retCls = sinceCallReturn == null
    ? 'text-ink-tertiary'
    : sinceCallReturn >= 0 ? 'text-signal-pos font-semibold' : 'text-signal-neg font-semibold'

  return (
    <div className="text-[12px] text-ink-tertiary">
      First called <strong className="text-ink-secondary">{verdict}</strong> on{' '}
      <span className="font-mono">{formatIST(firstCalledAt)}</span>
      {' · '}
      {daysHeld != null && <>{daysHeld} days held · </>}
      since-call return{' '}
      <span className={retCls}>
        {sinceCallReturn != null ? fmtSignedPct(sinceCallReturn) : '—'}
      </span>
    </div>
  )
}
```

- [ ] **Step 4: WhyStrip component**

```tsx
// frontend/src/components/v6/trader-view/WhyStrip.tsx
type ChipState = 'pass' | 'warn' | 'fail' | 'neutral'

export interface Chip {
  label: string
  value: string
  state: ChipState
}

const STATE_CLS: Record<ChipState, string> = {
  pass:    'bg-signal-pos-soft text-ink-secondary',
  warn:    'bg-signal-warn-soft text-ink-secondary',
  fail:    'bg-signal-neg-soft text-ink-secondary',
  neutral: 'bg-paper-soft text-ink-tertiary',
}
const DOT_CLS: Record<ChipState, string> = {
  pass:    'bg-signal-pos',
  warn:    'bg-signal-warn',
  fail:    'bg-signal-neg',
  neutral: 'bg-ink-quaternary',
}

export function WhyStrip({ chips }: { chips: Chip[] }) {
  return (
    <div className="flex gap-2 flex-wrap py-4 border-b border-paper-rule">
      {chips.map((c) => (
        <span
          key={c.label}
          className={`inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 border border-paper-rule rounded-full ${STATE_CLS[c.state]}`}
          data-testid="why-chip"
          data-state={c.state}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${DOT_CLS[c.state]}`} />
          <strong className="text-ink-primary font-semibold">{c.label}</strong> {c.value}
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: TrackingGrid component**

```tsx
// frontend/src/components/v6/trader-view/TrackingGrid.tsx
import { fmtSignedPct } from '@/lib/format-number'

export interface TrackingPoint {
  label: string
  value: string
  sub: string
  variant?: 'pos' | 'neg' | 'neutral'
}

export function TrackingGrid({ firstCalledAt, points }: { firstCalledAt: string; points: TrackingPoint[] }) {
  return (
    <div className="py-3.5 border-b border-paper-rule">
      <div className="text-[10px] font-semibold tracking-wider uppercase text-ink-tertiary mb-2">
        Tracking since first call ({firstCalledAt})
      </div>
      <div className="grid grid-cols-4 gap-3">
        {points.map((p) => (
          <div key={p.label}>
            <div className="text-[10px] uppercase tracking-wider text-ink-tertiary">{p.label}</div>
            <div className={`font-mono text-[18px] font-semibold mt-1 ${
              p.variant === 'pos' ? 'text-signal-pos' :
              p.variant === 'neg' ? 'text-signal-neg' :
              'text-ink-secondary'
            }`}>
              {p.value}
            </div>
            <div className="text-[11px] text-ink-tertiary mt-0.5">{p.sub}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Barrel export**

```ts
// frontend/src/components/v6/trader-view/index.ts
export { VerdictPill } from './VerdictPill'
export { ReturnLine } from './ReturnLine'
export { SinceCallLine } from './SinceCallLine'
export { WhyStrip, type Chip } from './WhyStrip'
export { TrackingGrid, type TrackingPoint } from './TrackingGrid'
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/v6/trader-view/
git commit -m "feat(trader-view): 5 shared components (VerdictPill, ReturnLine, SinceCallLine, WhyStrip, TrackingGrid)"
```

---

### Task 2: Convert /stocks/[symbol]

**Files:**
- Modify: `frontend/src/lib/queries/v6/stocks.ts` (add verdict + tracking fields to getStockDetail)
- Modify: `frontend/src/app/stocks/[symbol]/page.tsx`
- Create: `frontend/src/components/v6/stocks/TraderViewHeader.tsx`

- [ ] **Step 1: Extend getStockDetail() to include verdict + tracking**

Add to the SQL SELECT in `getStockDetail`:
```
mv.combined_verdict,
mv.verdict_reason,
mv.first_called_at::text,
mv.since_call_return::text,
mv.weinstein_stage,
mv.weinstein_ma_pct,
mv.predicted_excess::text,
mv.sigma_predicted::text,
mv.tenure,
mv.cap_tier,
mv.cell_state,
mv.conviction_tier,
-- existing gate booleans
mv.strength_gate, mv.direction_gate, mv.risk_gate, mv.sector_gate, mv.market_gate,
-- drift
d.drift_status, d.drift_z::text,
-- ownership
(pp.instrument_id IS NOT NULL) AS user_owns
```

Update the StockDetailRow TypeScript type accordingly.

- [ ] **Step 2: Build TraderViewHeader composite**

```tsx
// frontend/src/components/v6/stocks/TraderViewHeader.tsx
import {
  VerdictPill,
  ReturnLine,
  SinceCallLine,
  WhyStrip,
  TrackingGrid,
  type Chip,
} from '@/components/v6/trader-view'
import { DriftChip } from './DriftChip'
import { formatIST } from '@/lib/format-date'
import type { StockDetailRow } from '@/lib/queries/v6/stocks'

export function TraderViewHeader({ stock }: { stock: StockDetailRow }) {
  const isVeto = stock.combined_verdict === 'WAIT'

  const chips: Chip[] = [
    {
      label: 'Cell',
      value: `${stock.tenure} ${stock.cell_state === 'POSITIVE' ? 'POS' : stock.cell_state === 'NEGATIVE' ? 'NEG' : 'NEU'} · IC ${stock.cell_ic?.toFixed(3) ?? '—'}`,
      state: stock.cell_state === 'POSITIVE' ? 'pass' : stock.cell_state === 'NEGATIVE' ? 'fail' : 'neutral',
    },
    {
      label: 'Weinstein',
      value: stock.weinstein_stage ? `Stage ${stock.weinstein_stage}` : '—',
      state: stock.weinstein_stage === 2 ? 'pass' : stock.weinstein_stage === 4 ? 'fail' : stock.weinstein_stage === 3 ? 'warn' : 'neutral',
    },
    {
      label: 'Investable',
      value: `${[stock.strength_gate, stock.direction_gate, stock.risk_gate, stock.sector_gate, stock.market_gate].filter(Boolean).length}/5 gates`,
      state: stock.strength_gate && stock.direction_gate && stock.risk_gate && stock.sector_gate && stock.market_gate ? 'pass' : 'fail',
    },
    {
      label: 'Sector',
      value: `${stock.sector_name} · ${stock.sector_verdict_abbr ?? '—'}`,
      state: stock.sector_verdict_abbr === 'OW' ? 'pass' : stock.sector_verdict_abbr === 'UW' ? 'fail' : 'neutral',
    },
  ]
  if (stock.verdict_reason) {
    chips.push({ label: 'Reconcile', value: stock.verdict_reason, state: 'warn' })
  }

  const verdictVerb = stock.combined_verdict ?? 'WATCH'

  return (
    <div className="bg-paper border-b border-ink-rule">
      <div className="px-6 py-5">
        <div className="flex flex-col gap-2">
          <VerdictPill verdict={verdictVerb} />
          <div className="flex items-center gap-3 flex-wrap">
            <ReturnLine
              predictedExcess={stock.predicted_excess}
              tenure={stock.tenure as '1m' | '3m' | '6m' | '12m'}
              tier={stock.conviction_tier}
              isVeto={isVeto}
            />
            <DriftChip status={stock.drift_status} z={stock.drift_z} />
          </div>
          <SinceCallLine
            firstCalledAt={stock.first_called_at}
            verdict={verdictVerb}
            daysHeld={stock.days_held}
            sinceCallReturn={stock.since_call_return}
          />
        </div>

        <WhyStrip chips={chips} />

        {stock.first_called_at && (
          <TrackingGrid
            firstCalledAt={formatIST(stock.first_called_at)}
            points={[
              { label: 'At call', value: `₹${stock.price_at_call?.toFixed(2) ?? '—'}`, sub: `close on ${formatIST(stock.first_called_at)}`, variant: 'neutral' },
              { label: '1M target', value: stock.target_1m ?? '—', sub: 'predicted ± band', variant: 'pos' },
              { label: '3M target', value: stock.target_3m ?? '—', sub: 'predicted ± band', variant: 'pos' },
              { label: 'Realized today', value: stock.since_call_return != null ? `${stock.since_call_return >= 0 ? '+' : ''}${(stock.since_call_return * 100).toFixed(1)}%` : '—', sub: stock.drift_status === 'within_band' ? 'within band ✓' : 'drift', variant: stock.since_call_return != null && stock.since_call_return >= 0 ? 'pos' : 'neg' },
            ]}
          />
        )}

        <details className="py-3 border-b border-paper-rule">
          <summary className="text-[12px] text-accent cursor-pointer font-medium">
            Show the math · cell IC, gate breakdown, composite components, σ band
          </summary>
          {/* expanded math panel — defer to per-page Math component */}
        </details>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Wire into the page**

In `frontend/src/app/stocks/[symbol]/page.tsx`, replace the existing per-page header with `<TraderViewHeader stock={stock} />`. Keep all charts/tables below unchanged.

- [ ] **Step 4: Local smoke test**

```bash
cd frontend && npm run dev
```

Open http://localhost:3000/stocks/RELIANCE. Confirm:
- Verdict pill renders
- Return line shows predicted + tier
- Since-call line shows correct date + return
- Why-strip has 4 chips (Cell · Weinstein · Investable · Sector)
- Tracking grid renders
- "Show the math" collapses by default

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/v6/stocks/TraderViewHeader.tsx frontend/src/lib/queries/v6/stocks.ts frontend/src/app/stocks/[symbol]/page.tsx
git commit -m "feat(stocks): convert /stocks/[symbol] to trader-view pattern"
```

---

### Task 3: Checkpoint — review /stocks live before propagating

- [ ] **Step 1: Deploy to EC2**

```bash
bash scripts/deploy_frontend_v6.sh
ssh atlas "pm2 reload atlas-frontend-v2"
```

- [ ] **Step 2: User review on atlas.jslwealth.in/stocks/RELIANCE**

Surface to user with 3-5 sample stocks (one BUY, one WAIT, one SELL, one HOLD). Confirm visual polish matches the mockup, copy is correct, no layout regressions.

- [ ] **Step 3: Hold for sign-off before Task 4**

Do NOT propagate to ETFs/sectors/funds until user confirms /stocks looks right in production. This is the "learn from one page before propagating" checkpoint per the spec rollout sequence.

---

### Task 4: Convert /etfs/[ticker]

**Files:**
- Modify: `frontend/src/lib/queries/v6/etfs.ts`
- Modify: `frontend/src/app/etfs/[ticker]/page.tsx`
- Create: `frontend/src/components/v6/etfs/TraderViewHeader.tsx`

- [ ] **Step 1: Copy the /stocks pattern**

Same shape as TraderViewHeader for stocks. Differences for ETFs:
- No "user_owns" (ETFs don't have paper portfolio integration yet — treat as user_owns=false)
- Why-strip chip 4 is "Linked sector/index" instead of "Sector verdict"
- "Show the math" expands to the existing ETFGatesPanel (already exists)

- [ ] **Step 2-5:** Same as Task 2 but for ETFs

---

### Task 5: Convert /sectors/[name]

**Files:**
- Modify: `frontend/src/lib/queries/v6/sectors.ts`
- Modify: `frontend/src/app/sectors/[sector]/page.tsx`
- Create: `frontend/src/components/v6/sectors/TraderViewHeader.tsx`

- [ ] **Step 1: Adapt for sectors**

Verdict pill renders the sector-level verdict (OW/Neutral/UW/Avoid translated to BUY-leaning / WATCH / AVOID per the mapping). Why-strip:
- "Constituents" — N stocks
- "RS 3m" — sector RS vs Nifty 500
- "Verdict source" — bottom-up vs top-down (if both available)
- "Pulse" — sector pulse cell summary

- [ ] **Step 2-5:** Same pattern

---

### Task 6: Convert /funds/[mstar_id]

**Files:**
- Modify: `frontend/src/lib/queries/v6/funds.ts`
- Modify: `frontend/src/app/funds/[mstar_id]/page.tsx`
- Create: `frontend/src/components/v6/funds/TraderViewHeader.tsx`

- [ ] **Step 1: Adapt for funds**

Fund verdict derives from the underlying-holdings cell distribution. Why-strip:
- "Holdings" — N holdings, % in POSITIVE cells
- "Performance" — 1Y / 3Y / 5Y CAGR
- "Style" — fund style (e.g. Mid-cap Value)
- "Manager" — fund manager + tenure

- [ ] **Step 2-5:** Same pattern

---

### Task 7: Homepage top-conviction list

**Files:**
- Modify: `frontend/src/app/page.tsx` and/or `frontend/src/components/v6/today/TopConviction.tsx`

- [ ] **Step 1: Replace the existing top-conviction grid**

Each row shows: symbol (Link to /stocks/[symbol]), verdict pill (small), expected return, days-held since first call. Click row → /stocks/[symbol].

- [ ] **Step 2: Cross-nav audit**

Per [[everything-clickable]] memory: every symbol on the homepage must Link. Audit and fix.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/components/v6/today/
git commit -m "feat(home): top-conviction list converted to trader-view pattern + Link wrappers"
```

---

### Task 8: Retire legacy header components

After all five pages convert and QA passes, delete the old header components (e.g. the old StockOverviewHeader, ETFSummaryStrip, etc.).

```bash
git rm frontend/src/components/v6/stocks/StockOverviewHeader.tsx
git rm frontend/src/components/v6/etfs/ETFSummaryStrip.tsx
# … etc
git commit -m "chore: retire legacy per-page header components (superseded by trader-view)"
```

---

### Definition of Done

- [ ] All 5 surfaces (stocks, etfs, sectors, funds, homepage) render the trader-view header
- [ ] Verdict pill colors match the spec mapping (POS green / NEUTRAL grey / NEG red / WAIT amber)
- [ ] Every symbol, sector name, ETF ticker, fund name on every page is a `<Link>` (no dead text identifiers — per [[everything-clickable]])
- [ ] Tracking grid renders correctly for instruments with first_called_at populated; degrades to "No tracked call yet" otherwise
- [ ] "Show the math" expands to per-page detail components (cell breakdown, gate details, σ band)
- [ ] WAIT case renders the warn-colored Reconcile chip with the specific veto reason
- [ ] Mobile (≤640px) collapses verdict pill to ~24px, stacks chips vertically — no horizontal scroll
- [ ] Lighthouse perf score ≥ 80 on /stocks/[symbol] (no regression vs current)
- [ ] Visual diff vs `docs/v6/mockup-trader-view.html` confirmed by user

### Self-review checklist

- [ ] No legacy "Action: POSITIVE" rendering left on any page header
- [ ] Cross-nav links use `encodeURIComponent` for symbols with special chars (e.g. "M&M")
- [ ] Server components fetch with parallel `Promise.all` where possible (no waterfall)
- [ ] All money/percentage rendering uses existing helpers (`fmtSignedPct`, `formatIST`) — no inline formatting
