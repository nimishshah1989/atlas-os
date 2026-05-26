# v6 frontend primitives + Apache ECharts migration — design

Status: locked 2026-05-26
Source vocabulary: [CONTEXT.md](../../../CONTEXT.md) (v6 frontend redesign locks) and [DESIGN.md](../../../DESIGN.md) (standardization spec v1.0)
Reference mockup: `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/03-markets-rs.html`

## Goal

Lock the foundation layer for the v6 frontend rebuild:

1. Six primitive React components — the only authorised way to render their respective patterns.
2. Migrate from Recharts to Apache ECharts (the new MultidimChart primitive is ECharts-powered; Sparkline stays Recharts).
3. Storybook + Vitest snapshot tests per primitive.
4. PR-per-primitive workflow with the full review cadence (TDD → /codex → coderabbit → /design-review → /review).

Everything else in the v6 rebuild (Tremor wrappers, MVs, page rewires) depends on this. Ship before any page refactor.

## Non-goals

- Page rewires. Pages stay as-is; primitives ship side-by-side.
- Replacing existing components in place. Migration is a separate work-stream once primitives are stable.
- Tremor wrappers, materialized views, or backend changes.
- Sparkline migration (it stays on Recharts per DESIGN.md).

## Where things live

```
frontend/src/components/v6/primitives/
  InfoTooltip.tsx
  RAGChip.tsx
  SegmentedDots.tsx
  ActionVerb.tsx
  ClickableCard.tsx
  MultidimChart.tsx
  __tests__/
    InfoTooltip.test.tsx
    RAGChip.test.tsx
    SegmentedDots.test.tsx
    ActionVerb.test.tsx
    ClickableCard.test.tsx
    MultidimChart.test.tsx
  *.stories.tsx               # Storybook stories co-located with each primitive
  index.ts                    # barrel: { InfoTooltip, RAGChip, ... }
frontend/src/lib/charts/
  echarts.ts                  # registers only the chart types we use (tree-shake)
  multidim-option.ts          # builder for the four-lane chart ECharts option
  empty-state.tsx             # <ChartEmptyState> primitive
  tokens.ts                   # re-exports CHART_COLORS with ECharts-friendly aliases
.storybook/
  main.ts
  preview.tsx                 # loads globals.css + Atlas paper background
```

Existing `frontend/src/components/ui/Sparkline.tsx` is unchanged. Existing `frontend/src/lib/chart-colors.ts` is reused; `lib/charts/tokens.ts` is a thin alias layer.

## Primitive 1 — InfoTooltip

Locked in DESIGN.md §1. This spec adds the implementation contract.

### API

```ts
type TooltipVariant = 'brief' | 'detailed' | 'methodology';

interface InfoTooltipProps {
  variant: TooltipVariant;
  content: ReactNode;                              // body
  title?: string;                                  // required for detailed/methodology
  methodologyLink?: string;                        // required for methodology
  rawValue?: { label: string; value: string | number };  // required for methodology
  children?: ReactNode;                            // trigger; defaults to <Info /> icon
  side?: 'top' | 'right' | 'bottom' | 'left';      // default 'top'
  align?: 'start' | 'center' | 'end';              // default 'center'
}
```

### Behaviour contract

- `variant="brief" | "detailed"` → hover trigger with 200 ms open delay, 0 ms close delay.
- `variant="methodology"` → **click** trigger (touch-friendly), Escape and outside-click close.
- Default trigger when `children` is absent: a 14 px `lucide-react` `Info` icon at `text-ink-tertiary`, `aria-label="More information"`.
- Pointer events on the trigger never block underlying click handlers (Radix `asChild` pattern).
- Throws a typed dev-only error if `methodology` is missing `title`, `methodologyLink`, or `rawValue`. (No runtime cost in prod via `if (process.env.NODE_ENV !== 'production')`.)

### Visual contract

Per DESIGN.md §1: `bg-paper-soft border border-paper-rule rounded-sm p-3 shadow-1` plus per-variant widths (240 / 320 / 380 px). Motion: 120 ms ease-standard fade. No `translateY` or `scale`.

### Accessibility

- Backed by `@radix-ui/react-tooltip` (already in package.json) for hover variants and `@radix-ui/react-popover` for the methodology click variant. (Both projects are pin-compatible.)
- Tooltip content is announced via Radix's default `aria-describedby` wiring on the trigger.
- Keyboard: Tab focuses the trigger; for hover variants the tooltip opens on focus as well (Radix default). Escape closes the popover variant.
- `prefers-reduced-motion` → fade duration drops to 0 ms.

### Replaces

`Tooltip.tsx`, `InfoPanel.tsx`, `TooltipWrapper`, `ELI5Tooltip.tsx`, all bare `title=` table headers. Replacement happens later, file-by-file; primitive ships first.

### Test plan (Vitest + RTL)

1. Renders trigger child when provided; renders default Info icon when not.
2. Brief and detailed variants open on hover/focus, close on blur.
3. Methodology variant opens on click and closes on Escape.
4. Dev-only throws when methodology variant misses required props.
5. Snapshot per variant.

## Primitive 2 — RAGChip

Locked in DESIGN.md §2.

### API

```ts
type RAGState = 'green' | 'amber' | 'red';
type RAGEmphasis = 'default' | 'strong';

interface RAGChipProps {
  state: RAGState;
  label: string;
  emphasis?: RAGEmphasis;        // default 'default'
  className?: string;            // escape hatch; lint-warned outside primitives
}
```

### Visual contract

| | default | strong |
|---|---|---|
| Background | `bg-signal-{state}/15` | `bg-signal-{state}` |
| Text | `text-signal-{state}` | `text-paper` |
| Border | `border-signal-{state}/30` | none |
| Padding | `px-1.5 py-0.5` | `px-2.5 py-1` |
| Font | Inter SemiBold 11 px | Inter Bold 12 px UPPERCASE |
| Tracking | 0.05 em | 0.14 em |
| Radius | `rounded-sm` | `rounded-sm` |

Tabular-nums forced on `label` to keep numeric chips aligned in tables.

### Replaces

`StateChip`, `DriftWarnChip`, `RecommendationCard` action span, inline status spans across 14+ files.

### Test plan

1. Renders the right Tailwind classes for each (state, emphasis) of the 6 combinations.
2. `strong` emphasis uppercases the label even if passed lowercase.
3. Snapshot per (state, emphasis) — 6 fixtures.
4. Accessibility: `role="status"` for screen-reader announce when chip changes value.

## Primitive 3 — SegmentedDots

Locked in DESIGN.md §3.

### API

```ts
interface SegmentedDotsProps {
  count: number;                 // total dots
  filled: number;                // 0 ≤ filled ≤ count
  state: 'green' | 'amber' | 'red';
  label?: string;                // optional inline label to the right
  tenureLabels?: string[];       // e.g. ['1m','3m','6m','12m'] when count===4
  size?: 'sm' | 'md';            // default 'md' (8 px); 'sm' is 6 px for table use
  ariaLabel?: string;            // defaults to `${filled} of ${count} ${label ?? ''}`
}
```

### Visual contract

8 px dots (6 px sm), 1 px gap. Filled dots: `bg-signal-{state}`. Unfilled: `bg-paper-deep border border-paper-rule`. Optional label right-aligned, `text-ink-tertiary text-[11px] font-medium`.

When `tenureLabels` is passed, each dot gets a `title` attribute with the tenure label and a `<span class="sr-only">` for screen-readers. Used for the conviction tape (`count=4`, tenures `1m/3m/6m/12m`).

### Replaces

`CrossRuleDepthIndicator`, inline conviction-tape spans, stage indicators across StockHero / FundHero / ETFHero, all ad-hoc "N of M" spans.

### Test plan

1. `filled > count` clamps to `count` and logs a dev warning.
2. Negative `filled` clamps to 0.
3. Renders 4 dots with correct tenure tooltips when `count=4` and `tenureLabels` matches.
4. `aria-label` defaults sensibly and overrides cleanly.
5. Snapshot for the conviction-tape case + the cross-rule-depth case.

## Primitive 4 — ActionVerb

Locked in DESIGN.md §4. Strict — the verb is computed, never passed in.

### API

```ts
type CellDirection = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE';

interface ActionVerbProps {
  direction: CellDirection;
  isHeld: boolean;
}
```

### Verb resolution (locked)

| direction | isHeld=false | isHeld=true |
|---|---|---|
| POSITIVE | BUY | ACCUMULATE |
| NEUTRAL | WATCH | HOLD |
| NEGATIVE | AVOID | SELL |

Maps to `<RAGChip emphasis="strong">` internally:
- POSITIVE → state="green"
- NEUTRAL → state="amber"
- NEGATIVE → state="red"

### Implementation

Internally renders `<RAGChip state={...} emphasis="strong" label={verb} />`. The primitive's purpose is API safety — callers cannot pass an arbitrary verb. The resolution table lives in one place: `frontend/src/lib/v6-vocabulary.ts` (a tiny module exporting `resolveActionVerb(direction, isHeld)`). Backend reads from CONTEXT.md cell-state vocabulary; this module is the JS mirror.

### Replaces

`deriveActionVerb()` utility, all inline action-verb rendering in StockHero, StockListRow, RecommendationCard, CellTile.

### Test plan

1. All 6 (direction × isHeld) combinations resolve to the correct verb + color.
2. Renders inside a `<RAGChip>` with `emphasis="strong"`.
3. Snapshot for each of the 6 combinations.
4. Compile-time check: TypeScript rejects `<ActionVerb direction="FOOBAR" />`.

## Primitive 5 — ClickableCard

Locked in DESIGN.md §5.

### API

```ts
interface ClickableCardProps {
  href: string;
  hoverElevation?: 'none' | 'subtle';      // default 'subtle'
  preserveFilters?: Record<string, string>; // optional cross-page filter propagation
  ariaLabel: string;                        // required for keyboard users
  children: ReactNode;
  className?: string;
}
```

### Visual contract

| State | Treatment |
|---|---|
| Default | `bg-paper border border-paper-rule rounded-sm` |
| Hover (`subtle`) | `bg-paper-soft border-ink-rule shadow-1`, color shift only — no `translateY` / `scale` |
| Focus-visible | `outline outline-2 outline-accent outline-offset-1` |
| Active (mouse-down, pre-nav) | `bg-paper-deep` for 80 ms |

`hoverElevation="none"` collapses to default; useful for cards that should not feel actionable but still wrap a link (rare; lint-warned at the call site via JSDoc).

### Cross-pollination contract

If `preserveFilters` is provided, on click the component pushes a URL composed of `href` plus the filter params plus `from=<current-page-slug>`. Destination pages read these on SSR and pre-filter their data; the page also surfaces a removable `"Filtered: Energy"` breadcrumb chip (the chip is the destination page's responsibility, not the primitive's).

Implementation uses Next.js `useRouter` from `next/navigation` and `next/link`. Server-side rendering safe (the click handler is only attached on the client).

### Test plan

1. Renders an `<a>` (next/link) with the right href.
2. Hover (`mouseenter`) applies hover class set; mouseleave removes it.
3. `preserveFilters={{sector: "Energy"}}` produces href `…?sector=Energy&from=<page>`.
4. Click event navigates via `router.push`; original `href` is the SSR fallback for no-JS users.
5. `aria-label` required (TS-enforced).
6. Snapshot of the default + hover + active visual states.

## Primitive 6 — MultidimChart

The canonical four-lane chart. Reference impl: `03-markets-rs.html` r3 (the detail-charts section in the design mockup). Used everywhere v6 needs the price + S/R + RS markers + volume composite — Markets RS detail cards, Sector deep-dive, Stock deep-dive, Calls Performance hero, ETF deep-dive.

### Lanes (top → bottom in one ECharts grid)

1. **Price** (~ 60 % of height) — index level (rebased OR absolute), 1.6 px solid `--ink` line. End-cap dot 3 px radius. Horizontal support / resistance lines (dashed 4 3, 1 px, `--signal-info` at 65 % opacity) with right-edge level labels. RS-signal markers: green diamonds at "RS new high" dates, red diamonds at "RS new low" dates — plotted on a fixed baseline near the bottom of the price lane.
2. **RS strip** (~ 12 % of height) — spread vs the selected baseline. Filled area: `--signal-pos` 22 % opacity above zero, `--signal-neg` 22 % below. Line stroke 1.3 px in the dominant color. Dashed-zero reference line (`--ink-4`, 3 3 dasharray).
3. **Volume** (~ 28 % of height) — daily bars, green when close ≥ open else red, 55 % opacity. 20-day average overlay: 1.5 px `--signal-info` solid line.

All three lanes share the same x-axis (`axisPointer` linked across grids). Time axis ticks render at top of price pane only.

### API

```ts
type MultidimSeries = {
  dates: string[];                     // ISO 'YYYY-MM-DD' for each x point
  price: number[];                     // index level or rebased
  volume: number[];                    // raw daily volume
  rsSpread?: number[];                 // spread vs baseline, in same percent units
  supportResistance?: Array<{
    level: number;
    kind: 'support' | 'resistance';
    label?: string;                    // e.g. 'R 25,420'
  }>;
  rsSignals?: Array<{
    date: string;                      // must exist in `dates`
    kind: 'new_high' | 'new_low';
  }>;
  volumeMA?: number[];                 // length === volume.length
};

interface MultidimChartProps {
  data: MultidimSeries;
  baseline?: string;                   // e.g. 'Nifty 50'; for tooltip + RS-strip label
  height?: number;                     // default 300 (matches the mockup card)
  showLanes?: {                        // toggle individual lanes; defaults all true
    supportResistance?: boolean;
    rsMarkers?: boolean;
    rsStrip?: boolean;
    volume?: boolean;
    volumeMA?: boolean;
  };
  rebase?: boolean;                    // if true, price[0] = 100; default false
  onPointHover?: (point: { date: string; price: number; rsSpread?: number }) => void;
  emptyMessage?: string;               // shown when dates.length === 0
  className?: string;
}
```

### Visual contract

- Background: parent decides (paper-soft inside a card).
- Animation: `animation: true, animationDuration: 360, animationDurationUpdate: 0` — first-paint only, never on update (DESIGN.md motion rule).
- Tooltip: single Atlas-styled tooltip (`bg-paper-soft border-paper-rule rounded-sm shadow-1`) showing date + price + RS spread + volume.
- Empty state: `<ChartEmptyState message={emptyMessage} />` — same primitive every chart uses.
- All colors sourced from `chart-colors.ts`. No hardcoded hex inside the component.

### Implementation note — why one ECharts instance

Three vertically stacked `grid` objects in a single `option`. ECharts has first-class support for shared `xAxis` across multiple `grid`s; using one instance keeps cross-lane axis-pointer linking trivial and avoids resize-listener fan-out.

### Replaces

`PerWindowChart.tsx`, `MultiBenchmarkRSWaterfall.tsx`, ad-hoc Recharts `<ComposedChart>` usage on stock and sector detail pages.

### Test plan

1. Renders `<canvas>` (ECharts uses canvas) — assert via test-id on wrapper since ECharts is hard to snapshot.
2. Empty data renders `<ChartEmptyState>` not the chart.
3. `showLanes.volume = false` hides the volume grid entirely (height shifts to price + RS strip).
4. `rebase` rebases price[0] to 100.
5. `onPointHover` fires when ECharts emits the hover event.
6. Snapshot of the ECharts `option` object (the safest determinism we can get — assert option JSON, not rendered pixels).

## Apache ECharts migration

### Adoption

- Add `echarts@^5.5.0` and `echarts-for-react@^3.0.2` to `frontend/package.json`.
- Custom-build registration in `lib/charts/echarts.ts` to keep the bundle small: register only `LineChart`, `BarChart`, `ScatterChart`, `HeatmapChart`, `TreemapChart`, plus `GridComponent`, `TooltipComponent`, `MarkLineComponent`, `MarkPointComponent`, `LegendComponent`, `DataZoomComponent` plus the canvas renderer. SVG renderer is not registered (matches the mockup which is canvas-by-default; SVG mode adds ~50 KB).
- Sparkline stays on Recharts. The existing `Sparkline.tsx` is untouched.

### Token integration

`lib/charts/tokens.ts` re-exports `CHART_COLORS` with the ECharts-friendly keys the multidim option uses (`PRICE_LINE`, `SUPPORT_RESISTANCE`, `RS_NEW_HIGH`, `RS_NEW_LOW`, `RS_FILL_POS`, `RS_FILL_NEG`, `VOL_UP`, `VOL_DOWN`, `VOL_MA`). Adding a token there is the only way to introduce a new chart color.

### ESLint rule

```js
'no-restricted-imports': ['error', {
  patterns: [
    {
      group: ['recharts'],
      message: 'Use @/components/v6/primitives/MultidimChart or other ECharts wrappers; Recharts only allowed in components/ui/Sparkline.tsx',
    },
  ]
}]
```

The existing `Sparkline.tsx` gets a `// allow-recharts: sparkline stays Recharts per DESIGN.md` escape-hatch comment.

### Migration order

1. This PR sequence: primitives + `lib/charts/` infrastructure.
2. Later PRs (out of scope here): migrate `PerWindowChart`, `MultiBenchmarkRSWaterfall`, etc., one component per PR. Each migration deletes the Recharts version and replaces it with a primitive call site.

## Storybook

### Why add it

The mockup is the visual contract; Storybook is how the primitives stay aligned with it across PRs. /design-review consumes Storybook URLs the same way it consumes the rendered app.

### Stack

- `@storybook/react-vite` (Vite builder; Next.js framework not needed for primitives) — version 9.x.
- Stories co-located with primitives: `*.stories.tsx`.
- `preview.tsx` loads `frontend/src/app/globals.css` so primitives render against `--paper` and inherit the Atlas tokens.
- One story file per primitive with at minimum: default state, every variant, hover + focus states (Storybook interactions add-on).

### Scripts

```jsonc
{
  "scripts": {
    "storybook": "storybook dev -p 6006",
    "build-storybook": "storybook build -o storybook-static"
  }
}
```

CI does not yet build Storybook — /design-review uses `storybook-static` snapshots locally for now.

## Vitest snapshot tests

Already set up in `frontend/package.json` (`vitest@4.1.5` + `@testing-library/react` + `jsdom`). Per-primitive plan above. Snapshots live in `__tests__/__snapshots__/`. Run as part of the existing `npm test`.

Two snapshot styles:

1. **DOM snapshots** for the five DOM-rendered primitives — `expect(container.firstChild).toMatchInlineSnapshot()` or `.toMatchSnapshot()`.
2. **Option-object snapshot** for MultidimChart — `expect(buildMultidimOption(data, props)).toMatchSnapshot()` to keep the test deterministic without depending on ECharts' canvas output.

## PR-per-primitive workflow

Branch from `main` (currently `feat/v6-deep-search-all-cells` is a sibling — primitives need their own branch). Per primitive:

1. `git checkout -b feat/v6-primitives-<name>` from `main`.
2. Invoke `superpowers:test-driven-development`.
3. Red: write the snapshot + behavior tests; verify they fail.
4. Green: implement the primitive + Storybook story.
5. Refactor.
6. `/codex review` (autonomous adversarial pass).
7. `coderabbit:code-review`.
8. `/design-review` against the matching mockup section.
9. `/review` (final pre-merge).
10. Squash-merge to `main` with PR title `feat(v6/primitives): <Name>` (memory permits direct squash-merge).

Shared infra (ECharts setup, Storybook config, `lib/charts/`, ESLint rule) lands first in a small `feat(v6/primitives): scaffold` PR. The six primitive PRs then stack on top of that one in any order — they are independent.

## Open questions deferred to writing-plans

These are tactical decisions the implementation plan settles, not design decisions:

1. Whether the methodology variant of InfoTooltip uses Radix Popover or a custom dialog. (Lean: Popover; Radix Popover supports the same trigger pattern as Tooltip and avoids a dialog's focus-trap behavior which is wrong here.)
2. Whether Storybook 9 requires a Next.js polyfill for `next/link` in ClickableCard stories. (Probably yes; address in scaffold PR.)
3. Whether SegmentedDots' `tenureLabels` should be a positional `string[]` or a `Record<string,string>` mapping. (Lean: positional `string[]` length must equal `count`; runtime-validated.)

## Acceptance criteria (whole-deliverable)

- All six primitives compile, lint, and pass tests.
- All six primitives have Storybook stories that visually match the locked mockup.
- ECharts is the only chart library used by new code (Recharts confined to `Sparkline.tsx` via escape-hatch).
- `npm test` passes; no existing tests break.
- Six PRs merged into `main` plus one scaffold PR. Tag: `feat(v6/primitives): <Name>`.
