'use client'
// src/components/explorer/FacetBar.tsx — the filters as ONE ROW above the table, not a column
// beside it.
//
// WHAT THIS REPLACES. A 260 px rail carried fourteen groups down the whole page — every peer
// group, every theme, forty countries, ten deciles, five tiers, four threshold ladders — open all
// at once, whether or not the reader wanted any of them. The FM: "don't think we need so many
// filters… make the filter part smarter so that it doesn't occupy so much space and the space can
// be occupied by the table." The table is the product; the filters are how you get to the rows.
//
// THE SAME STATE, A SMALLER SURFACE. Every group is still here, with the same option lists, the
// same counts and the same URL parameters, so nothing that could be filtered before cannot be
// filtered now and a bookmarked address still means what it meant. What changed is that a group is
// a BUTTON that says its current value ("Volatility ≤ 25%", "Theme · 2") and opens its options on
// demand; a group at its default reads as its name alone. The peer-group strip above the table
// remains the first control, so it is not repeated here.
//
// A FLAG IS A SWITCH, NOT A MENU. "Include leveraged" is one checkbox with a count; it renders as
// one toggle, because a popover with a single option in it is a door with nothing behind it.
import { useEffect, useRef, useState } from 'react'
import { ALL, ON, visibleOptions, type FacetGroup } from '@/lib/explorer'
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
  /** The group the strip above the table already controls; it is not drawn twice. */
  omit?: string
}

const single = (kind: FacetGroup<never>['kind']) => kind === 'one' || kind === 'min' || kind === 'max'

function optionLabel<R>(g: FacetGroup<R>, v: string): string {
  return g.labels?.[v] ?? (v === ALL ? 'All' : (g.format?.(v) ?? words(v)))
}

/** What the button says: the group's name at its default, otherwise the name and the choice. */
function summary<R>(g: FacetGroup<R>, sel: string[]): { text: string; active: boolean } {
  if (g.kind === 'flag') return { text: g.labels?.[ON] ?? g.label, active: sel.includes(ON) }
  if (single(g.kind)) {
    const v = sel[0]
    if (v == null || v === ALL || v === g.default) return { text: g.label, active: false }
    const glyph = g.kind === 'min' ? '≥' : g.kind === 'max' ? '≤' : '·'
    return { text: `${g.label} ${glyph} ${optionLabel(g, v)}`, active: true }
  }
  if (sel.length === 0) return { text: g.label, active: false }
  return { text: sel.length === 1 ? `${g.label} · ${optionLabel(g, sel[0])}` : `${g.label} · ${sel.length}`, active: true }
}

export function FacetBar<R>({ groups, values, counts, selected, onChange, onClear, omit }: Props<R>) {
  const [open, setOpen] = useState<string | null>(null)
  const bar = useRef<HTMLDivElement>(null)

  // One popover at a time; a click anywhere else, or Escape, closes it.
  useEffect(() => {
    if (open == null) return
    const away = (e: PointerEvent) => {
      if (!bar.current?.contains(e.target as Node)) setOpen(null)
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(null)
    }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    <div ref={bar} className="facetbar" role="group" aria-label="Filters">
      {groups.map((g) => {
        if (g.key === omit) return null
        const sel = selected[g.key] ?? []
        const options = single(g.kind) ? [...(g.options ?? []), ALL] : g.kind === 'flag' ? [ON] : (values[g.key] ?? [])
        // Hide what the current selection has emptied; hide the group when nothing is left. The
        // rule and its reasons live in src/lib/explorer.ts, where they are tested.
        const shown = visibleOptions(g.kind, options, counts[g.key], sel)
        if (shown.length === 0) return null
        const { text, active } = summary(g, sel)

        if (g.kind === 'flag') {
          const on = sel.includes(ON)
          const n = counts[g.key]?.[ON] ?? 0
          return (
            <button
              key={g.key}
              type="button"
              className={`facet-btn text-meta${on ? ' on' : ''}`}
              aria-pressed={on}
              title={on ? `${text} — click to leave them out again` : `${text} — ${formatNum(n)} more row(s)`}
              onClick={() => onChange(g.key, on ? [] : [ON])}
            >
              <span className="facet-btn-glyph" aria-hidden="true">{on ? '✓' : '+'}</span>
              {text}
              {!on && <span className="facet-btn-n num">{formatNum(n)}</span>}
            </button>
          )
        }

        const isOpen = open === g.key
        return (
          <div key={g.key} className="facet-group">
            <button
              type="button"
              className={`facet-btn text-meta${active ? ' on' : ''}${isOpen ? ' open' : ''}`}
              aria-expanded={isOpen}
              aria-haspopup="listbox"
              onClick={() => setOpen(isOpen ? null : g.key)}
            >
              {text}
              <span className="facet-btn-glyph" aria-hidden="true">▾</span>
            </button>
            {isOpen && (
              <fieldset className="facet-pop panel" aria-label={g.label}>
                <legend className="sr-only">{g.label}</legend>
                {shown.map((v) => {
                  const checked = sel.includes(v)
                  return (
                    <label key={v} className={`facet-opt text-table${checked ? ' is-on' : ''}`}>
                      <input
                        type={single(g.kind) ? 'radio' : 'checkbox'}
                        aria-label={optionLabel(g, v)}
                        name={g.key}
                        value={v}
                        checked={checked}
                        onChange={() => {
                          onChange(g.key, single(g.kind) ? [v] : checked ? sel.filter((x) => x !== v) : [...sel, v])
                          if (single(g.kind)) setOpen(null)
                        }}
                      />
                      <span className="facet-name">{optionLabel(g, v)}</span>
                      <span className="facet-n num">{formatNum(counts[g.key]?.[v] ?? 0)}</span>
                    </label>
                  )
                })}
              </fieldset>
            )}
          </div>
        )
      })}
      {onClear && (
        <button type="button" className="btn btn-quiet text-meta" onClick={onClear}>
          Clear filters
        </button>
      )}
    </div>
  )
}
