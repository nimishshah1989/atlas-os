'use client'
// src/components/explorer/DataTable.tsx — the one table of design §5: sortable, tabular, and
// windowed over the PAGE's scroll rather than its own.
//
// IT USED TO OWN A SCROLLPORT — `height: calc(100vh - 372px)` with `overflow: auto` — so the
// list scrolled inside a box while the page around it stood still. The FM's words on seeing it:
// "the tables are not scrolling properly. There is no need for any scroll, only at least on the
// horizontal side." He is right, and it is also how Atlas India's tables have always worked: a
// div with `overflow-x: auto` and nothing else, the page scrolling as one document.
//
// So the box now scrolls only sideways and the window follows the VIEWPORT: rows above the fold
// are `-getBoundingClientRect().top`, the window is `innerHeight` tall. Rows are 44 px and the
// layout is fixed, so that window is still arithmetic — only the rows in view (plus an overscan)
// are in the DOM, with spacer rows holding the height — and four thousand funds do not all mount.
// Sorting is the caller's (the header buttons report the wanted sort).
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Icon } from '@/components/shell/icons'
import type { SortState } from '@/lib/explorer'

// MUST equal `.dt-table td { height }` in src/app/globals.css. The window over the list is
// arithmetic over this number: if the stylesheet's row height changes and this does not, the
// virtualiser reports the wrong rows for a scroll position. Change them together.
const ROW_HEIGHT = 44
const OVERSCAN = 10
/** What the first, server-rendered pass assumes the viewport is, before any measurement. */
const DEFAULT_HEIGHT = 900

export type Column<R> = {
  key: string
  label: string
  /** Column width in px. 0 means "take what is left": the column gets no `<col>` width, and in a
   *  `table-layout: fixed` table it absorbs whatever the sized columns do not use. */
  width: number
  /** The floor for a width-0 column, in px. It is counted into the table's own min-width, so the
   *  column still has this much when the table is narrower than the viewport and scrolls.
   *  WITHOUT IT a width-0 column collapses to the 160 px default and every fund name in the ETF
   *  list rendered as an ellipsis — the defect this whole surface was rebuilt to fix. */
  minWidth?: number
  align?: 'right'
  sortValue: (r: R) => string | number | null
  render: (r: R) => ReactNode
  /** A fuller header, shown on hover. */
  title?: string
  /** Per-row cell styling — the relative-strength tint. Colour is never the only channel: a
   *  tinted cell still prints its value. */
  cellStyle?: (r: R) => CSSProperties | undefined
  /** A separating rule to the LEFT of this column: where the risk overlay stops being the score. */
  divider?: boolean
}

type Props<R> = {
  rows: readonly R[]
  columns: Column<R>[]
  rowKey: (r: R) => string
  sort: SortState
  onSort: (sort: SortState) => void
  /** What the empty list says — an instruction, not a mood. */
  empty: ReactNode
}

// The risk overlay is NOT part of the score, so it is drawn behind a hairline instead of beside
// the lenses. One rule, one token, no new colour.
const DIVIDER: CSSProperties = { borderLeft: '1px solid var(--color-rule)' }

const cellClass = <R,>(c: Column<R>, kind: 'th' | 'td') =>
  [kind === 'td' && c.align === 'right' ? 'num' : '', c.align === 'right' ? 'r' : ''].filter(Boolean).join(' ') || undefined

function cellStyle<R>(c: Column<R>, r: R): CSSProperties | undefined {
  const tint = c.cellStyle?.(r)
  if (!c.divider) return tint
  return { ...DIVIDER, ...tint }
}

// Holds the scroll height of the rows outside the window (an empty <tr> may collapse to 0).
function Spacer({ height, span }: { height: number; span: number }) {
  return (
    <tr className="dt-spacer" aria-hidden="true">
      <td colSpan={span} style={{ height }} />
    </tr>
  )
}

export function DataTable<R>({ rows, columns, rowKey, sort, onSort, empty }: Props<R>) {
  const box = useRef<HTMLDivElement>(null)
  // How far the table's top edge has passed above the fold, and how tall the fold is. Both are
  // measured from the document's own scroll, so there is no inner scrollport to get out of step.
  const [view, setView] = useState({ above: 0, height: DEFAULT_HEIGHT })

  useLayoutEffect(() => {
    let queued = false
    const measure = () => {
      queued = false
      const top = box.current?.getBoundingClientRect().top ?? 0
      setView({ above: Math.max(0, -top), height: window.innerHeight })
    }
    // Scroll fires far faster than paint; one measurement per frame is enough and keeps the
    // listener passive, so it never blocks the scroll it is watching.
    const onScroll = () => {
      if (!queued) {
        queued = true
        requestAnimationFrame(measure)
      }
    }
    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', measure)
    }
  }, [])

  // A new sort or filter re-measures: the list under the same scroll position is a different list.
  useEffect(() => {
    const top = box.current?.getBoundingClientRect().top ?? 0
    setView({ above: Math.max(0, -top), height: window.innerHeight })
  }, [rows, sort])

  const n = rows.length
  const start = Math.max(0, Math.floor(view.above / ROW_HEIGHT) - OVERSCAN)
  const end = Math.min(n, Math.ceil((view.above + view.height) / ROW_HEIGHT) + OVERSCAN)
  const minWidth = columns.reduce((w, c) => w + (c.width || c.minWidth || 160), 0)

  function toggle(c: Column<R>) {
    onSort({ key: c.key, dir: sort.key === c.key && sort.dir === 'asc' ? 'desc' : 'asc' })
  }

  return (
    <div ref={box} className="dt panel">
      <table className="dt-table" style={{ minWidth }}>
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={c.width ? { width: c.width } : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort.key === c.key
              return (
                <th
                  key={c.key}
                  className={cellClass(c, 'th')}
                  style={c.divider ? DIVIDER : undefined}
                  aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  <button type="button" className="dt-sort" onClick={() => toggle(c)} title={c.title}>
                    <span>{c.label}</span>
                    {active && <Icon name={sort.dir === 'asc' ? 'up' : 'down'} className="text-accent" />}
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {n === 0 && (
            <tr>
              <td colSpan={columns.length} className="dt-empty text-ink-2">
                {empty}
              </td>
            </tr>
          )}
          {start > 0 && <Spacer height={start * ROW_HEIGHT} span={columns.length} />}
          {rows.slice(start, end).map((r) => (
            <tr key={rowKey(r)} data-row="">
              {columns.map((c) => (
                <td key={c.key} className={cellClass(c, 'td')} style={cellStyle(c, r)}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
          {end < n && <Spacer height={(n - end) * ROW_HEIGHT} span={columns.length} />}
        </tbody>
      </table>
    </div>
  )
}
