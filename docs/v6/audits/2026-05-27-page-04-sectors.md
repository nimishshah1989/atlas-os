# F.0 Audit · /v6/sectors vs 04-sectors.html

**Audit date:** 2026-05-27
**Live URL:** https://atlas.jslwealth.in/v6/sectors
**Mockup file:** ~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/04-sectors.html
**Verdict:** major

## Section presence

| Section (from mockup) | One-line spec | Live status | Notes |
|---|---|---|---|
| Page header | "Sectors" serif title + sub-line (22 actionable sectors…) + breadcrumb | partial | Live title is "Sector Intelligence"; sub-line shows sector count. Breadcrumb absent (no `Sectors ›` nav). |
| Hero enriched readout | 3-column panel: Leading sectors (4 rows with RS delta) / Lagging sectors (5 rows) / To-watch + summary thesis | absent | Live page has a state-summary pill bar (Overweight/Neutral/Underweight/Avoid counts) but no 3-col hero readout with bullet rows of leading/lagging sectors |
| Hero stat strip | 3-tile readout: e.g. "4 Overweight · 8 Neutral · 5 Underweight · 5 Avoid" with sector narratives | absent | The counts are shown in StateSummaryPill row but not in a card-style stat strip with narrative text per column |
| RRG (Relative Rotation Graph) | 540px SVG with 4 quadrants (Leading/Improving/Lagging/Weakening), sector bubble trails, legend card, 4W/8W/12W toggle | present | `RRGChart` from `@/components/sectors/RRGChart` is rendered; height 560px; toggle missing (no timeframe chip controls) |
| RRG side panel | Legend card + returns mini-table (sector name + 1M/3M return + RS pp vs index) | absent | RRGChart fills full width; no side panel with legend + mini-returns table |
| Multi-window heatmap (v2 dense) | Dense table: sector × return windows (1W/1M/3M/6M/12M) + confidence bar + verdict chip, column chooser chips | absent | No heatmap table on the live sectors page; the mockup's dense `heatmap-table-v2` with color-coded return cells does not appear anywhere |
| Sector card grid (3-col enriched) | 3-col cards with border-left accent, multidim mini-chart, thesis text, confidence pill stack, 3 key metrics, deep-dive link | absent | Live page shows no sector card grid; mockup has `sc-card-v2` cards for top Overweight + top Underweight sectors |
| Sector ladder | 30-row table with rank, delta arrow, sector name, state badge, breadth bar, vol regime, RS %, 1M/3M return, 12W trajectory sparkline | present | `SectorsListV6` renders this table with all these columns; 12W trajectory sparkline present (though built from flat `buildTrajectory()` stub, not real history) |
| Column chooser | Toggle chips to show/hide heatmap columns | absent | Column chooser exists for the ladder sort (rank/breadth/RS), but not for column visibility of return windows |
| Footnote | Data source + methodology link | absent | No footnote block |

## Token compliance

- [x] `SectorsListV6.tsx` uses semantic Tailwind tokens: `bg-signal-pos`, `bg-signal-neg`, `bg-signal-warn`, `bg-teal`, `border-paper-rule`, `text-ink-tertiary`, etc. Clean.
- [x] `RankSparkline` uses CSS var strings `var(--color-signal-pos, #2F6B43)` etc. as style fallback — acceptable pattern for SVG stroke.
- [x] Font classes: `font-serif`, `font-sans`, `font-mono` throughout. Clean.

## Component reuse

- [x] Page imports `SectorBookStrip`, `BubbleRiskReturnChart`, `RRGChart`, `DataSourceBanner`, `SectorsListV6` — all proper v6 components.
- [ ] Missing component: a "Hero enriched readout" / sector summary panel. No `SectorHeroReadout` component in `components/v6/`.
- [ ] Missing component: multi-window heatmap. The `SignatureMatrix` component exists but is not used on this page; neither is a dedicated return-window heatmap.
- [ ] Missing component: sector card grid (`SectorCards` variant for the v2 enriched cards). `SectorDetailClient` has sector card logic but no list-level card grid.

## Data correctness

- [x] Sector ladder rows: state, rank, breadth bar, vol regime, RS%, 1M/3M all render real values from `getSectorsForDate()`.
- [ ] 12W trajectory sparkline: `buildTrajectory(rank)` at `SectorsListV6.tsx` line ~133 returns `Array(12).fill(rank)` — a flat line (no actual history). The sparkline renders a dot, not a trajectory. Real trajectory data would require weekly snapshots from `atlas_sector_states_daily`.
- [x] State summary pills (Overweight/Neutral/Underweight/Avoid counts) show real counts.
- [ ] Hero enriched readout (leading/lagging sectors with RS delta) absent — no data populated for this section.
- [ ] Multi-window heatmap cells — absent, no data populated.

## Per-gap closure plan

1. **Hero enriched readout (3-col) absent** — files: `frontend/src/app/v6/sectors/page.tsx` (pass top-N sectors by state); `frontend/src/components/v6/SectorsListV6.tsx` (add a hero section above the RRG); the section should show "Leading sectors" (top 3-4 Overweight by RS delta), "Lagging" (top Underweight), and one "Watch" col. Data available from the existing `sectors` array — sort by RS and group by state.

2. **Multi-window heatmap table absent** — files: create `frontend/src/components/v6/SectorHeatmap.tsx`; render a `<table>` with sectors as rows, return windows (1W/1M/3M/6M/12M) as columns; color cells with the pos/neg heat scale; add verdict chip column. Data: `ret_1m`, `ret_3m` are already in `ScreenSector`; `ret_6m` and `ret_12m` need to be added to `getSectorsForDate()` query from `atlas_sector_metrics_daily`. Wire into `SectorsListV6.tsx`.

3. **Sector enriched card grid absent** — files: create `frontend/src/components/v6/SectorCardGrid.tsx`; each card has sector name, border-left colored accent, multidim mini-chart (reuse `PerWindowChart`), thesis text, confidence pills, 3 key metrics (breadth, RS%, 1M return), deep-dive link. Render the top 6 sectors (3 Overweight + 3 Underweight) above the heatmap.

4. **RRG timeframe toggle (4W/8W/12W) absent** — file: `frontend/src/components/v6/SectorsListV6.tsx` (RRG section around line 171); add chip-controls to toggle the history passed to `RRGChart`; `rrgHistory` is already fetched with 84 days — slice to 28/56/84 days based on toggle.

5. **RRG side panel (legend + returns mini-table) absent** — file: `frontend/src/components/v6/SectorsListV6.tsx`; change RRG section from full-width to `grid grid-cols-[2fr_1fr]`; add a side panel with quadrant legend and per-sector 1M/3M return + RS delta mini-table.

6. **12W trajectory sparkline is flat stub** — file: `frontend/src/components/v6/SectorsListV6.tsx` line ~133 `buildTrajectory()`; change: fetch actual weekly rank snapshots from `atlas_sector_states_daily` (a new query `getWeeklyRankHistory()` in `lib/queries/v6/sectors.ts`); pass as prop to `SectorsListV6`. The sparkline SVG rendering is already correct — only the data is stub.

7. **Column chooser for heatmap absent** — file: `SectorHeatmap.tsx` (when created); add `ColumnChooser` with toggles for return window columns (1W/1M/3M/6M/12M) + verdict + confidence bar. Pattern identical to `StocksListV6.tsx`.
