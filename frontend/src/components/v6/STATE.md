# State persistence contract — v6 components

URL params are the primary source of truth. LocalStorage seeds the initial value
when no URL param is present. A click always writes both simultaneously.

---

## URL params

All params are handled via `useSearchParams` + `router.replace` (shallow, no
scroll) from `lib/v6/persistence.ts`. Param names are lower-snake-case; values
are plain strings (no JSON encoding in the URL).

### `tenure`

| | |
|---|---|
| Type | `1m \| 3m \| 6m \| 12m` |
| Default | `6m` |
| Scope | Every tenure-aware page (stocks list, sector detail, stock detail, fund detail) |
| Hook | `useTenurePreference(pageKey)` from `lib/v6/persistence.ts` |

### `benchmark`

| | |
|---|---|
| Type | `nifty50 \| nifty500 \| gold` |
| Default | `nifty500` |
| Scope | Every relative-strength-flavored view |
| Hook | `useBenchmarkPreference(pageKey)` from `lib/v6/persistence.ts` |
| Note | The `gold` value is only rendered when the parent passes `goldAvailable={true}` to `BenchmarkToggle`. When `goldAvailable` is false and the URL or LS carries `gold`, the component silently falls back to `nifty500`. Resolve `goldAvailable` server-side via `isGoldAvailable()`; do NOT call the query inside the client component. |

### `sector_filter`

| | |
|---|---|
| Type | URL-encoded sector name or the literal string `all` |
| Default | `all` (no filter) |
| Scope | Stocks list, stocks screener |
| Note | Sector names contain spaces — use `encodeURIComponent` / `decodeURIComponent`. An absent param is equivalent to `all`. |

### `tier_filter`

| | |
|---|---|
| Type | `Large \| Mid \| Small \| all` |
| Default | `all` (no filter) |
| Scope | Stocks list, cell matrix |
| Note | Values match `atlas_universe_stocks.cap_tier` enum literals exactly (case-sensitive). |

### `cell_id`

| | |
|---|---|
| Type | Atlas cell identifier string, e.g. `Mid_12m_Pullback` |
| Default | none (param absent = no cell filter active) |
| Scope | Cell detail page (`/v6/cells/[cell_id]`), screener filter |
| Note | Format is `<Tier>_<Window>_<Archetype>` per `atlas_cell_definitions.cell_id`. URL-encode the full value when embedding in a query string. |

---

## LocalStorage keys

All keys follow the pattern `v6.<type>.<pageKey>`. The `pageKey` is a
short string that uniquely names the page or table — it keeps preferences from
leaking between pages that share the same param type.

| Key | Value format | Set by |
|---|---|---|
| `v6.tenure.<pageKey>` | Plain string: `1m`, `3m`, `6m`, or `12m` | `useTenurePreference` |
| `v6.benchmark.<pageKey>` | Plain string: `nifty50`, `nifty500`, or `gold` | `useBenchmarkPreference` |
| `v6.columns.<pageKey>` | JSON-encoded string array: `["ticker","rs_pct","atlas_grade"]` | `useColumnPreferences` |

Column preferences are LS-only (no URL encoding). The `v6.columns.<pageKey>`
entry is absent until the user explicitly changes column visibility or the
hydration effect writes it on first mount.

---

## Resolution rules

1. **URL is the source of truth when present.** A URL param always overrides the
   LS value for the same key. Priority order: URL param > LS > hardcoded default.

2. **A click writes both.** Every setter (from `useTenurePreference`,
   `useBenchmarkPreference`, `useColumnPreferences`) writes the new value to LS
   AND updates the URL via `router.replace`. A hard refresh therefore restores the
   last user-selected state.

3. **Switching pages does not leak preferences.** The `pageKey` argument
   namespaces every LS key. `v6.tenure.stocks` and `v6.tenure.fund-detail` are
   independent entries; changing tenure on the stocks page has no effect on the
   fund detail page.

4. **SSR-safe initial render.** Server-rendered HTML uses hardcoded defaults
   (`6m`, `nifty500`, column defaults). On hydration, a `useEffect` reads LS and
   patches the state in. Because the patch happens after the first paint, there
   is no server/client HTML mismatch and no hydration error.

5. **No new state manager.** Do not introduce Zustand, Redux, Jotai, or any
   global state library for UI preferences. URL + LS is the only persistence
   mechanism permitted (eng-review decision #11). Cross-component coordination is
   done by lifting state or by reading the same URL param from sibling hooks.

6. **Client components only.** Any component that calls these hooks must carry
   the `"use client"` directive at the top of the file. The hooks call
   `useSearchParams`, `useRouter`, `useState`, and `useEffect` — all client-only
   React APIs.

---

## Example usage

### (a) Page using `useTenurePreference`

```tsx
"use client"

import { useTenurePreference } from "@/lib/v6/persistence"
import { TenureToggle } from "@/components/v6/TenureToggle"

export function StocksTableClient() {
  const { tenure, setTenure } = useTenurePreference("stocks")

  return (
    <div>
      <TenureToggle pageKey="stocks" />
      {/* tenure is now the resolved value: URL > LS > "6m" */}
      <p>Showing {tenure} returns</p>
    </div>
  )
}
```

### (b) Table using `useColumnPreferences`

```tsx
"use client"

import { useColumnPreferences } from "@/lib/v6/useColumnPreferences"
import { ColumnChooser, type ColumnDef } from "@/components/v6/ColumnChooser"
import { useState } from "react"

const COLUMN_DEFS: ColumnDef<string>[] = [
  { key: "ticker",     label: "Ticker",    group: "returns" },
  { key: "rs_pct",     label: "RS %",      group: "returns" },
  { key: "atlas_grade",label: "Grade",     group: "atlas"   },
]
const DEFAULTS = ["ticker", "rs_pct", "atlas_grade"]

export function StocksTable() {
  const { visible, setVisible, reset } = useColumnPreferences("stocks", DEFAULTS)
  const [chooserOpen, setChooserOpen] = useState(false)

  return (
    <div>
      <ColumnChooser
        columns={COLUMN_DEFS}
        visible={visible}
        defaults={DEFAULTS}
        onVisibleChange={setVisible}
        onReset={reset}
        open={chooserOpen}
        onOpenChange={setChooserOpen}
      />
      {/* render only columns in `visible` */}
    </div>
  )
}
```

---

## Source files

| Hook / export | File |
|---|---|
| `useTenurePreference` | `frontend/src/lib/v6/persistence.ts` |
| `useBenchmarkPreference` | `frontend/src/lib/v6/persistence.ts` |
| `useColumnPreferences` | `frontend/src/lib/v6/useColumnPreferences.ts` |
| `TenureToggle` | `frontend/src/components/v6/TenureToggle.tsx` |
| `BenchmarkToggle` | `frontend/src/components/v6/BenchmarkToggle.tsx` |
| `ColumnChooser` | `frontend/src/components/v6/ColumnChooser.tsx` |
