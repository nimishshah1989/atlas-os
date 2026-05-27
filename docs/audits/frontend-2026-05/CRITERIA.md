# Atlas Frontend Audit — Criteria

Audit dimensions, derived directly from user-reported pain points (2026-05-16).
Every page report scores against these 10 dimensions on a 0/1/2 scale
(0 = absent or broken, 1 = partial, 2 = good). Total possible: 20/20.

---

## 1. Clickability completeness

**What to check:** Every element that *looks* clickable (cards, ticker chips,
sector names, instrument names, state badges, count pills, sparkline cells)
either navigates somewhere useful or signals "not clickable" via style.

**Red flags:**
- Sector name in plain text on a card → expect link to `/sectors/<name>`
- Stock symbol in a list → expect link to `/stocks/<symbol>`
- "Top 5 leaders" with names but no click target
- Count pill ("12 stocks") that begs for a filtered list but does nothing
- Card outline + hover state implying clickability that goes nowhere

## 2. Navigation correctness

**What to check:** Every link that exists actually routes to a working page.

**Red flags:**
- Link to `/sectors/Energy` but page 404s
- Link target points to old route that has since moved
- Breadcrumb missing or wrong
- Tab clicks update visual state but not URL (impossible to share or refresh)

## 3. Tooltips & transparency

**What to check:** Every metric, state badge, score, percentile, threshold,
or jargon term has hover tooltip explaining what it is and how it's computed.

**Red flags:**
- "RS pctile 87" with no tooltip → user has no idea what RS is
- "Tier 1" badge with no explanation
- Color-coded state (green/red/amber) with no legend
- Threshold value (e.g., "0.45") with no "why this number"
- Source/methodology not linkable from the metric

## 4. Toggled detail & expandable history

**What to check:** State histories, bands, breakdown tables let user expand
to see the underlying data without leaving the page.

**Red flags:**
- "State history" shown as 5 colored dots with no way to see the date/value
- Band ranges shown ("0.3 – 0.5") with no way to see where current value sits
- "Underlying components" not visible — only the rollup
- Composite score shown but not the contributing signals

## 5. Timestamps & freshness

**What to check:** Every data point displays a `data_as_of` or `fetched_at`
that updates correctly. Stale data is flagged visibly.

**Red flags:**
- "Updated 5h ago" that says 5h regardless of actual age
- No timestamp at all on tables/cards
- "Yesterday's close" when data is 3 days old
- Intraday badge missing during market hours
- Inconsistent timestamp formats across the page

## 6. Wasted space & visual rhythm

**What to check:** Empty margins, collapsed sections occupying real estate
without earning it, redundant whitespace.

**Red flags:**
- Collapsed accordion taking full row width with just a title visible
- Card with 80% empty space and one tiny number
- Section heading + 1 chart at 25% width, rest white
- Repeated information across two cards on same row
- Sidebar that's empty on this route

## 7. Consistency (typography, spacing, colors)

**What to check:** Cards, tables, badges, numbers follow the same visual
language across all pages. Numbers right-aligned. Money formatted same way.

**Red flags:**
- Card padding differs across sections
- Number format inconsistent (some use ₹, some plain numerics, some lakh/crore)
- Font sizes inconsistent for the same data type
- Mix of `text-gray-500` and `text-zinc-500` etc.
- Border-radius varies (some `rounded-md`, some `rounded-lg`, no system)

## 8. Hardcoded values & magic constants

**What to check:** Values that should be config-driven, thresholds from
`atlas_thresholds`, or computed dynamically are not hardcoded as literals.

**Red flags:**
- "Top 10" hardcoded; should be `LIMIT` from config
- Threshold "0.45" hardcoded in JSX
- "Last 30 days" hardcoded; should match a config window
- Color palette literals (`#1D9E75`) inline instead of design token
- Magic offsets in chart components (`xOffset: 47`)

## 9. Information architecture & hierarchy

**What to check:** Primary content gets primary visual weight. Secondary
context is secondary. Tabs grouped logically. Filters discoverable.

**Red flags:**
- Most important number buried in 12px text
- Tabs in wrong order (Recommendation tab buried after Composition)
- Filters in unexpected location
- "Show advanced" hiding the thing the user actually needs
- Action button (`+ New Portfolio`) hidden below the fold

## 10. Mobile / responsive behavior

**What to check:** Page renders intentionally at common widths (375 mobile,
768 tablet, 1280 desktop). Tables don't horizontally explode.

**Red flags:**
- Table overflows viewport with no scroll affordance
- Sidebar covers main content on mobile
- Hover-only interactions broken on touch
- Charts don't resize
- Tap targets < 44px

---

## Scoring rubric

For each page:

```
Dim 1 — Clickability:      _/2  notes...
Dim 2 — Navigation:        _/2  notes...
Dim 3 — Tooltips:          _/2  notes...
Dim 4 — Toggled detail:    _/2  notes...
Dim 5 — Timestamps:        _/2  notes...
Dim 6 — Wasted space:      _/2  notes...
Dim 7 — Consistency:       _/2  notes...
Dim 8 — Hardcoded values:  _/2  notes...
Dim 9 — IA & hierarchy:    _/2  notes...
Dim 10 — Responsive:       _/2  notes... (skipped if not tested)
TOTAL: __/20
```

## Severity tags for individual findings

- **P0** — Broken: link 404s, button doesn't work, page errors
- **P1** — Significant UX gap: missing tooltips on critical metrics,
  unclickable elements that should be clickable, stale timestamps
- **P2** — Polish: wasted space, minor inconsistency, hardcoded value
  that should be config-driven
- **P3** — Nice to have: typography refinement, micro-interaction
