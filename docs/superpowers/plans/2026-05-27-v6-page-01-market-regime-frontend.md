# v6 Page 01 Market Regime Landing — Frontend Wiring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Wire the v6 Market Regime landing page (route `/v6/regime`) to `atlas.mv_market_regime_landing`, rendering hero strip + 12-week journey + 4 pulse tiles + 6 cells-favored cards + 3-tab conviction (stocks/funds/ETFs).

**Architecture:** Server Component reads single wide MV row via `@/lib/db`. JSONB fields (`twelve_week_journey`, `cells_favored`, `conviction_stocks/funds/etfs`, `recent_60d_segments`, `next_state_probs`, `deployment_defaults`) are parsed to typed shapes in the query module. Tabs are CSS-only (no client state for v6.0; tab switching deferred).

**Tech Stack:** Next.js 14 App Router, React 18 Server Components, postgres-js, TypeScript 5.

---

## File Structure

| File | Action |
|---|---|
| `frontend/src/lib/queries/v6/market-regime.ts` | CREATE |
| `frontend/src/app/v6/regime/page.tsx` | CREATE |
| `frontend/src/app/v6/regime/loading.tsx` | CREATE |

---

## Task 1: Query module

- [ ] **Step 1.1: Write `market-regime.ts`** (typed parse of all JSONB sections)

- [ ] **Step 1.2: Commit `feat(v6): market-regime query module`**

## Task 2: Route page

- [ ] **Step 2.1: Write `page.tsx`** (composes hero + journey + tiles + cells + conviction)
- [ ] **Step 2.2: Write `loading.tsx`**
- [ ] **Step 2.3: Commit `feat(v6): /v6/regime route wired to mv_market_regime_landing`**

---

## Self-review

Pattern mirrors markets-rs exactly: query module → typed shape → Server Component. JSONB parsing is the only differentiator. Plan complete; inline execution.
