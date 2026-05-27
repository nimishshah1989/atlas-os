# Chunk B.8 — PositionSizingWidget Approach

## Chosen approach

Pure client component: no DB calls. All data is passed via props (server-side calls already happened). `computeSizing()` (B.5) is a pure function — call it directly at render time.

**Decimal boundary**: `HoldingState.aggregate_weight` is a stringified NUMERIC decimal fraction (e.g. "0.035" = 3.5%). `toNumberOr()` converts it, then multiply ×100 to get the whole-number pct that `computeSizing` expects. Default to 0 when holdingState is null.

**Constraint routing**: Four binding constraint cases map to distinct headline copy:
- `max_per_stock` → "At cap (Xmax%; current Y%)"
- `conviction_floor` → "Conviction too thin"
- `sector_cap` → "Book overweight in sector"
- `deployment_cap` → "Regime cap: no room"

**Tooltip**: InfoTooltip wraps the binding-constraint chip with both `content` (technical) and `translation` (plain-English) props from the pre-built `CONSTRAINT_TOOLTIPS` map.

## Wiki patterns checked
- `PortfolioBadge.tsx` for Radix Tooltip + `HoldingState` consumption pattern
- `decimal.ts` for `toNumberOr()` boundary

## Edge cases handled
- holdingState=null → currentWeightPct=0, "first position" copy
- aggregate_weight="0.00" (v6.0 launch state) → correctly converts to 0 pct
- deployment_multiplier < 1.0 → "Regime cap: positions sized X% of normal" microcopy added
- All four binding constraints produce non-empty rationale (sourced directly from computeSizing)

## Files
- `frontend/src/components/v6/PositionSizingWidget.tsx` — 180 LOC
- `frontend/src/components/v6/__tests__/PositionSizingWidget.test.tsx` — 228 LOC

## Test results
10 tests, all pass. 0 TS errors in new files.
