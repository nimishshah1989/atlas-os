# Stocks Page Sprint 6 — Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Complete the stocks page to 100% finish line — deep dive upgrade, SQL cleanup, new columns, deep dive rolling page with better charts, StateHeatmap fix, and pagination.

**Architecture:** Pure frontend changes (SQL cleanup + new columns in queries/stocks.ts, new metric charts in StockDeepDiveBody, tab → rolling page in deep dive, StockBubbleChart fix). No backend migrations needed.

**Tech Stack:** Next.js 15, TypeScript, Recharts, postgres tagged-template SQL, Tailwind CSS

---

## Phase B — P2 Quick Fixes

### Task 1: Recharts minWidth fix + touch targets

**Files:**
- Modify: `frontend/src/components/stocks/StockBubbleChart.tsx`
- Modify: `frontend/src/components/stocks/StockScreener.tsx`

- [ ] **Step 1: Fix Recharts ResponsiveContainer width warning in StockBubbleChart**

Add `style={{ minWidth: 0 }}` to the wrapper div around `<ResponsiveContainer>`. Find the outer wrapper div that contains the ResponsiveContainer and add the style prop.

- [ ] **Step 2: Add min-h-[44px] to chip filter buttons in StockScreener**

Find the `CHIPS` array buttons (the RS filter chips at the top: All, Leader/Strong, etc.) and add `min-h-[44px]` class.

- [ ] **Step 3: Commit Phase B quick fixes**

```bash
git add frontend/src/components/stocks/StockBubbleChart.tsx frontend/src/components/stocks/StockScreener.tsx
git commit -m "fix(stocks): recharts minWidth warning + mobile touch targets on filter chips"
```

---

## Phase C — SQL Cleanup + New Columns

### Task 2: Remove 3 unused SQL fields, add ret_1d + rs_pctile_1w

**Files:**
- Modify: `frontend/src/lib/queries/stocks.ts`
- Modify: `frontend/src/components/stocks/StockScreener.tsx`

- [ ] **Step 1: Remove rs_3m_nifty500, rs_3m_tier_gold, stage1_base_qualifies from type and all 3 queries**

In `StockRowWithSector` type, remove `stage1_base_qualifies`. In all 3 query functions (getAllStocks, getTopPicksAcrossSectors, getStockBySymbol), remove the 3 SELECT lines:
- `m.rs_3m_tier::text AS rs_3m_nifty500`
- `m.rs_3m_tier_gold::text AS rs_3m_tier_gold`
- `s.stage1_base_qualifies`

Also remove `position_size_pct` from all 3 queries and from the type.

- [ ] **Step 2: Add ret_1d and rs_pctile_1w to the type and queries**

In `StockRowWithSector`, add:
```typescript
ret_1d: string | null
rs_pctile_1w: string | null
```

In all 3 queries, add to SELECT:
```sql
m.ret_1d::text AS ret_1d,
m.rs_pctile_1w::text AS rs_pctile_1w,
```

- [ ] **Step 3: Add ret_1d and rs_pctile_1w as optional columns in StockScreener**

In `OPTIONAL_COLS` array, add:
```typescript
{ key: 'ret_1d',         label: '1D',         defaultVisible: false },
{ key: 'rs_pctile_1w',   label: 'RS 1W',      defaultVisible: false },
```

Also update `ALWAYS_VISIBLE_COL_COUNT` and add column headers + cells in the table.

- [ ] **Step 4: Commit Phase C SQL changes**

```bash
git add frontend/src/lib/queries/stocks.ts frontend/src/components/stocks/StockScreener.tsx
git commit -m "feat(stocks): add ret_1d/rs_pctile_1w columns, remove 3 unused SQL fields + position_size_pct"
```

---

## Phase D — Deep Dive Page Upgrade

### Task 3: Add 3 more metric charts to StockDeepDiveBody

**Files:**
- Modify: `frontend/src/lib/queries/stocks.ts` (add drawdown_ratio_252, avg_volume_20, extension_pct to MetricHistoryRow)
- Modify: `frontend/src/app/stocks/[symbol]/page.tsx` (if needed for getStockMetricHistory)
- Modify: `frontend/src/components/stocks/StockDeepDiveBody.tsx`

- [ ] **Step 1: Add drawdown_ratio_252, avg_volume_20, extension_pct to MetricHistoryRow type**

```typescript
export type MetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  ret_3m: string | null
  ema_10_ratio: string | null
  drawdown_ratio_252: string | null
  avg_volume_20: string | null
  extension_pct: string | null
}
```

- [ ] **Step 2: Update getStockMetricHistory query to fetch new fields**

Add to the SELECT in `getStockMetricHistory`:
```sql
drawdown_ratio_252::text AS drawdown_ratio_252,
avg_volume_20::text AS avg_volume_20,
extension_pct::text AS extension_pct,
```

Remove `rs_3m_nifty500` from the MetricHistoryRow SELECT too.

- [ ] **Step 3: Add 3 new IndicatorChart blocks in StockDeepDiveBody**

After the EMA ratio chart block, add:

```tsx
{/* Drawdown chart */}
<div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
  <IndicatorChart
    title="Drawdown Ratio (252D)"
    description="Current drawdown from 252-day peak. Closer to 0 = near peak. More negative = deeper drawdown."
    currentValue={latest?.drawdown_ratio_252 != null ? parseFloat(latest.drawdown_ratio_252).toFixed(3) : '—'}
    isBullish={latest?.drawdown_ratio_252 != null ? parseFloat(latest.drawdown_ratio_252) > -0.1 : null}
    data={drawdownData}
    refLine={0}
    refLabel="0 = at peak"
    variant="area"
    yFormat="ratio"
  />
  <Commentary title="Drawdown">
    {interpretDrawdown(latest?.drawdown_ratio_252 ?? null)}
  </Commentary>
</div>
```

Add similar blocks for extension_pct (how far above 200D EMA) and avg_volume_20 (volume trend).

- [ ] **Step 4: Add interpreter functions for new charts**

Add to `@/lib/stock-formatters`:
- `interpretDrawdown(v: string | null)` 
- `interpretExtension(v: string | null)`
- `interpretVolumeRatio(v: string | null)`

- [ ] **Step 5: Convert deep dive tabs to rolling page**

In `frontend/src/app/stocks/[symbol]/page.tsx`, find where the tabs (History, Overview, etc.) are rendered. Remove the tabs and render all content as a continuous rolling page: StateJourneyCompact → StockDeepDiveBody → StateHeatmap (inline, no separate tab).

- [ ] **Step 6: Commit Phase D deep dive upgrade**

```bash
git add frontend/src/lib/queries/stocks.ts frontend/src/components/stocks/StockDeepDiveBody.tsx frontend/src/app/stocks/[symbol]/page.tsx
git commit -m "feat(stocks): deep dive page — 3 new metric charts, rolling page (no tabs), metric history fix"
```

---

## Phase E — StateHeatmap Visual Fix

### Task 4: Fix StateHeatmap in deep dive

**Files:**
- Modify: `frontend/src/components/stocks/StockHistoryTab.tsx`

- [ ] **Step 1: Improve StateHeatmap cell size and month labels**

Increase cell size from current (small) to at least 10px width, ensure month labels have proper spacing. Use flexbox with min-width per cell.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/stocks/StockHistoryTab.tsx
git commit -m "fix(stocks): improve StateHeatmap cell size and month label spacing"
```

---

## Final: Deploy to EC2

After all phases committed to main:
1. rsync frontend/src to EC2
2. npm run build on EC2
3. pm2 restart
4. Verify at atlas.jslwealth.in/stocks
