# Stream E — Methodology Page Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the `/methodology` page as a plain-English, fund-manager-grade explainer that covers the cell math, the Weinstein rules (with values from stream A), drift detection, and the verdict derivation logic. Honors the [[atlas-explainer-flywheel]] ethos — no black-box claims, every auto-action surfaces its math.

**Architecture:** One new React component `MethodologyV70.tsx` replaces the current `MethodologyV62.tsx`. Server-rendered, no client interactivity beyond expandable sections. Cross-links to every deep-dive page so reading the methodology and acting on it are one click apart.

**Tech Stack:** Next.js 15.3.9 App Router (React Server Component), Tailwind CSS, no new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-28-trader-view-redesign.html` §1-§7.
**Dependency:** stream A must land first — methodology needs the locked Weinstein lookback values to be honest.

---

### Task 1: Outline the new page structure

**Files:**
- Create: `docs/v6/methodology-v70-outline.md` (working doc, not shipped)

- [ ] **Step 1: Write the outline**

```markdown
# Methodology v7.0 — Page Outline

## Section 1 — The Atlas decision in one sentence
Single paragraph: "When you open a stock page you see one verdict (BUY / WATCH / WAIT / etc.).
That verdict is composed from four inputs in a fixed order. Here's how."

## Section 2 — The four inputs
- Cell math (what fires today)
- Weinstein stage (where we are in the price cycle)
- 5 gates (structural prerequisites)
- Drift (how the previous calls are tracking)

Each input gets a 200-word plain-English explainer + a small visual.

## Section 3 — How the verdict gets composed
Reproduce the precedence ladder from spec §4 as a flowchart. Walk through 3 worked examples.

## Section 4 — Weinstein rules in plain English
- What is a 30W moving average
- Why we use 5W / 10W / 20W / 30W per cap-tier (with the actual values from stream A)
- What Stage 1, 2, 3, 4 mean
- Why Stage 4 vetoes a positive cell

## Section 5 — Drift detection
- Why we track every call
- What Z-score means
- What "within band ✓" or "drift +1.8σ" means
- How drift events feed back into the engine

## Section 6 — The flywheel
- Daily: cells fire, verdicts compose
- Weekly: drift events accumulate, rolling IC updates
- Monthly: composite weights re-optimize
- Quarterly: cell-level IC re-validates, retire underperformers

## Section 7 — Honesty
- What we measure (IC, hit rate, realized excess)
- What we don't (alpha vs absolute return — we are RELATIVE-strength, not absolute-direction)
- Where the model breaks (regime shifts, low-liquidity stocks, news shocks)

## Section 8 — Click through to apply
Every section links to where you can see the math in action:
- Cell math → /stocks/[symbol] → "Show the math"
- Weinstein → /sectors/[name] → Stage history chart
- Drift → /admin/weight-performance
- Verdict → top of every stock/etf/sector/fund page
```

- [ ] **Step 2: Commit outline**

```bash
git add docs/v6/methodology-v70-outline.md
git commit -m "docs: methodology v7.0 outline"
```

---

### Task 2: Build the page component

**Files:**
- Create: `frontend/src/components/methodology/MethodologyV70.tsx`

- [ ] **Step 1: Write the component**

Write a single React Server Component that renders the 8 sections above. Use the Atlas design language (paper background, serif headers for section titles, mono for numbers, teal accent for cross-nav links).

```tsx
// frontend/src/components/methodology/MethodologyV70.tsx
import Link from 'next/link'
import { loadThresholds } from '@/lib/thresholds'

export async function MethodologyV70() {
  // Pull live Weinstein thresholds + drift bands so the page never lies
  const t = await loadThresholds([
    'weinstein.ma_weeks.Large',
    'weinstein.ma_weeks.Mid',
    'weinstein.ma_weeks.Small',
    'drift.mild_z',
    'drift.significant_z',
  ])

  return (
    <article className="max-w-[760px] mx-auto px-6 py-12 prose prose-atlas">
      <h1 className="font-serif text-[34px] mb-1">Methodology</h1>
      <p className="text-ink-tertiary text-[13px] mb-10">
        How the Atlas engine decides what to BUY, HOLD, SELL or WAIT on — without hand-waving.
      </p>

      {/* Section 1 */}
      <section>
        <h2 className="font-serif text-[24px] mt-12 mb-3">The Atlas decision in one sentence</h2>
        <p>
          When you open a stock page you see <strong>one verdict</strong> — BUY, ACCUMULATE,
          WATCH, HOLD, AVOID, SELL, or WAIT. That verdict is composed from four inputs in a
          fixed order. Read on for what each input does and what wins when they disagree.
        </p>
      </section>

      {/* Section 2 — The four inputs (200 words each, with diagram placeholders) */}
      <section>
        <h2 className="font-serif text-[24px] mt-12 mb-3">The four inputs</h2>
        <h3 className="font-serif text-[18px] mt-6 mb-2">1. Cell math — what fires today</h3>
        <p>
          Every Indian stock is classified into one of 24 cells based on its cap-tier (Large /
          Mid / Small), tenure (1m, 3m, 6m, 12m), and direction signal (POS / NEG / NEUTRAL).
          Each cell has a historical Information Coefficient — how well that pattern has
          predicted forward returns. When a stock matches a high-IC cell today, it fires.
          The output is a label (POSITIVE / NEUTRAL / NEGATIVE), a confidence (0-1), and a
          predicted excess return. See <Link href="/admin/composite-proposals" className="text-accent">/admin/composite-proposals</Link>
          {' '}for the live cell weights.
        </p>

        <h3 className="font-serif text-[18px] mt-6 mb-2">2. Weinstein stage — where in the cycle</h3>
        <p>
          Cell math tells you what pattern fired. Weinstein tells you whether the stock is
          structurally going up or going down. A stock is in:
        </p>
        <ul className="text-[14px] my-2">
          <li><strong>Stage 1</strong> (base) — price above moving average, slope flat</li>
          <li><strong>Stage 2</strong> (uptrend) — price above moving average, slope positive</li>
          <li><strong>Stage 3</strong> (topping) — price below moving average, slope flat</li>
          <li><strong>Stage 4</strong> (downtrend) — price below moving average, slope negative</li>
        </ul>
        <p>
          The moving-average lookback we use depends on cap-tier (because small-caps move
          faster than large-caps):
        </p>
        <table className="text-[13px] my-3">
          <thead><tr><th>Tier</th><th>MA lookback</th></tr></thead>
          <tbody>
            <tr><td>Large</td><td className="font-mono">{t['weinstein.ma_weeks.Large']} weeks</td></tr>
            <tr><td>Mid</td><td className="font-mono">{t['weinstein.ma_weeks.Mid']} weeks</td></tr>
            <tr><td>Small</td><td className="font-mono">{t['weinstein.ma_weeks.Small']} weeks</td></tr>
            <tr><td>Micro</td><td className="font-mono">— (Weinstein veto disabled for Micro)</td></tr>
          </tbody>
        </table>

        <h3 className="font-serif text-[18px] mt-6 mb-2">3. The five gates — structural prerequisites</h3>
        <p>
          Even when the cell fires positive, we apply five filters before showing BUY:
        </p>
        <ol className="text-[14px] my-2">
          <li><strong>Strength</strong> — relative-strength percentile above 70 (top 30% of universe)</li>
          <li><strong>Direction</strong> — short-term EMA ratio rising (momentum confirms)</li>
          <li><strong>Risk</strong> — price not over-extended above the 200-day MA, vol not blown out</li>
          <li><strong>Sector</strong> — the linked sector is not in Avoid state</li>
          <li><strong>Market</strong> — the broader regime is not Risk-Off</li>
        </ol>
        <p>
          If any one fails, the cell signal is downgraded to <strong>WAIT</strong>. Open the
          {' '}<Link href="/stocks" className="text-accent">stocks list</Link> and click any
          row to see which gates pass for that name.
        </p>

        <h3 className="font-serif text-[18px] mt-6 mb-2">4. Drift — how previous calls are tracking</h3>
        <p>
          Every BUY/SELL call we issue is tracked daily. We compute a Z-score: how far the
          realized return has drifted from our predicted band. A call is:
        </p>
        <ul className="text-[14px] my-2">
          <li><strong>Within band</strong> when |Z| ≤ {t['drift.mild_z'] ?? '1.5'}</li>
          <li><strong>Mild drift</strong> when |Z| ≤ {t['drift.significant_z'] ?? '2.0'}</li>
          <li><strong>Significant drift</strong> when |Z| &gt; {t['drift.significant_z'] ?? '2.0'} — call is failing</li>
        </ul>
      </section>

      {/* Section 3 — Composition */}
      <section>
        <h2 className="font-serif text-[24px] mt-12 mb-3">How the verdict gets composed</h2>
        <p>The four inputs flow through a fixed precedence:</p>
        <pre className="text-[12px] bg-paper-soft p-4 border border-paper-rule rounded-sm">
{`if cell_state == NEGATIVE:           → SELL (own) / AVOID (don't own)
elif cell_state == NEUTRAL:          → HOLD (own) / WATCH (don't own)
elif cell_state == POSITIVE:
    if Weinstein Stage 4:            → WAIT (reason: "Stage 4 vetoes positive cell")
    elif any of 5 gates fails:       → WAIT (reason: named failing gate)
    elif Weinstein Stage 3:          → HOLD (own) / WATCH (don't own)
    else:                            → ACCUMULATE (own) / BUY (don't own)`}
        </pre>
        <p>
          Three worked examples — open in a new tab to see the math live:
        </p>
        <ul>
          <li>
            <Link href="/stocks/RELIANCE" className="text-accent">RELIANCE</Link>
            {' '}— clean BUY case (Cell POS · Stage 2 · all gates pass)
          </li>
          <li>
            <Link href="/etfs/JUNIORBEES" className="text-accent">JUNIORBEES</Link>
            {' '}— conflict case (Cell POS · Stage 4 · WAIT)
          </li>
          <li>
            <Link href="/stocks/YESBANK" className="text-accent">YESBANK</Link>
            {' '}— SELL case (Cell NEG · ownership-aware verb)
          </li>
        </ul>
      </section>

      {/* Sections 4-7 — Weinstein details, Drift, Flywheel, Honesty */}
      {/* (Each ~250 words with cross-links; omitted for brevity in this plan, but
         must be written in full when implementing) */}

      {/* Section 8 — Click through */}
      <section>
        <h2 className="font-serif text-[24px] mt-12 mb-3">Click through to see this in action</h2>
        <ul>
          <li><Link href="/stocks" className="text-accent">/stocks</Link> — see verdicts across the universe</li>
          <li><Link href="/sectors" className="text-accent">/sectors</Link> — verdicts rolled up to sector</li>
          <li><Link href="/calls" className="text-accent">/calls</Link> — every open call + its tracking</li>
          <li><Link href="/admin/weight-performance" className="text-accent">/admin/weight-performance</Link> — drift detection in real time</li>
        </ul>
      </section>
    </article>
  )
}
```

- [ ] **Step 2: Wire into /methodology route**

```tsx
// frontend/src/app/methodology/page.tsx
import { MethodologyV70 } from '@/components/methodology/MethodologyV70'

export default function Page() {
  return <MethodologyV70 />
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/methodology/MethodologyV70.tsx frontend/src/app/methodology/page.tsx
git commit -m "feat(methodology): v7.0 page — fund-manager-grade explainer with live thresholds"
```

---

### Task 3: Fill in sections 4-7 in detail

The skeleton above leaves Sections 4-7 partially stubbed. Write each in full:

- [ ] **Section 4 — Weinstein rules:** 400-word section walking through the 30W convention, why we deviate for Mid/Small, what "slope" means computationally, and the fast-confirm overlay if/when it's enabled. Pull live values from atlas_thresholds.

- [ ] **Section 5 — Drift:** 300 words on what Z represents, why it scales with √elapsed_time, what gets written to atlas_drift_event_log, and how the user can see drift on every stock page (the DriftChip from stream B).

- [ ] **Section 6 — Flywheel:** 250 words plus the daily/weekly/monthly/quarterly diagram. Each timescale has one or two bullets describing what runs. Cross-link to /admin/engine-activity for the activity log.

- [ ] **Section 7 — Honesty:** 200 words on RELATIVE strength vs absolute return, where the model breaks (regime shifts, news shocks, illiquid stocks), what the documented hit-rate is, and the 60-day fast-confirm A/B status.

- [ ] **Commit:**

```bash
git commit -am "docs(methodology): fill sections 4-7 with live thresholds + drift + flywheel + honesty"
```

---

### Task 4: Cross-link audit

- [ ] **Step 1:** Verify every methodology section that mentions a feature has a working `<Link>` to the page where you can see it.

- [ ] **Step 2:** Verify every other Atlas page that mentions a methodology term (e.g. "Weinstein Stage 4", "Z-score drift") has a Link back to the relevant methodology section anchor.

```bash
grep -rn "Weinstein\|drift_z\|Z-score" frontend/src/components/ | grep -v methodology | head
```

- [ ] **Step 3:** Commit any added links

---

### Task 5: Retire MethodologyV62

After QA confirms v7.0 reads well and the cross-links work, delete the v6.2 component.

```bash
git rm frontend/src/components/methodology/MethodologyV62.tsx
git commit -m "chore: retire MethodologyV62 (superseded by V70)"
```

---

### Definition of Done

- [ ] `/methodology` renders with 8 sections, all written in full, no `[TBD]` markers
- [ ] Weinstein lookback table reads live values from atlas_thresholds (no hardcoded numbers in JSX)
- [ ] Drift Z bands read live values from atlas_thresholds
- [ ] Every cross-link in the page resolves to a live route (no 404s)
- [ ] Fund manager can read the page top-to-bottom in 10 minutes and answer: "what would make this verdict change?"
- [ ] No use of forbidden vocabulary (delve, crucial, robust, comprehensive, etc.)
- [ ] Page passes Lighthouse content-readability audit (FK reading grade ≤ 11)

### Self-review checklist

- [ ] No claim made on the page that isn't backed by code or atlas_thresholds — page never lies
- [ ] Every section either explains a mechanism OR points to a UI where the mechanism is visible
- [ ] Cross-nav links use the canonical paths (per [[everything-clickable]] memory)
- [ ] Mobile readable (line length 60-70 chars, no horizontal scroll)
