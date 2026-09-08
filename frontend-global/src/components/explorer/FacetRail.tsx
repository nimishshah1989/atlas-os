'use client'
// src/components/explorer/FacetRail.tsx — the 260 px rail of design § Layout: one fieldset per
// facet group, native checkboxes (any of) or radios (one of), a tabular count beside each value.
// Counts come from the explorer (the query and the other groups), so a value never hides its
// alternatives; a value with no rows stays listed at 0 rather than vanishing.
import { ALL, type FacetGroup } from '@/lib/explorer'
import { words } from '@/lib/facts'
import { formatNum } from '@/lib/format'

type Props<R> = {
  groups: FacetGroup<R>[]
  /** Every value each group takes over the full list (the option list). */
  values: Record<string, string[]>
  counts: Record<string, Record<string, number>>
  selected: Record<string, string[]>
  onChange: (key: string, selection: string[]) => void
  onClear?: () => void
}

export function FacetRail<R>({ groups, values, counts, selected, onChange, onClear }: Props<R>) {
  return (
    <aside className="facets" aria-label="Filters">
      {groups.map((g) => {
        const sel = selected[g.key] ?? []
        const options = g.kind === 'one' ? [...(g.options ?? []), ALL] : (values[g.key] ?? [])
        return (
          <fieldset key={g.key} className="facet">
            <legend className="facet-title text-meta">{g.label}</legend>
            {options.map((v) => {
              const checked = sel.includes(v)
              const label = v === ALL ? 'All' : (g.labels?.[v] ?? words(v))
              return (
                <label key={v} className={`facet-opt text-table${checked ? ' is-on' : ''}`}>
                  <input
                    type={g.kind === 'one' ? 'radio' : 'checkbox'}
                    name={g.key}
                    value={v}
                    checked={checked}
                    onChange={() =>
                      onChange(g.key, g.kind === 'one' ? [v] : checked ? sel.filter((x) => x !== v) : [...sel, v])
                    }
                  />
                  <span className="facet-name">{label}</span>
                  <span className="facet-n num">{formatNum(counts[g.key]?.[v] ?? 0)}</span>
                </label>
              )
            })}
          </fieldset>
        )
      })}
      {onClear && (
        <button type="button" className="btn btn-quiet text-body" onClick={onClear}>
          Clear filters
        </button>
      )}
    </aside>
  )
}
