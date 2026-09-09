'use client'
// src/components/explorer/DataTable.tsx — the one table of design §5: virtualised, sortable,
// tabular. Rows are 44 px and the layout is fixed, so the window over the list is arithmetic:
// only the rows in view (plus an overscan) are in the DOM, with spacer rows holding the scroll
// height. Sorting is the caller's (the header buttons report the wanted sort).
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Icon } from '@/components/shell/icons'
import type { SortState } from '@/lib/explorer'

// MUST equal `.dt-table td { height }` in src/app/globals.css. The window over the list is
// arithmetic over this number: if the stylesheet's row height changes and this does not, the
// virtualiser reports the wrong rows for a scroll position. Change them together.
const ROW_HEIGHT = 44
const OVERSCAN = 10
const MIN_HEIGHT = 320
/** The stylesheet's pre-hydration height (.dt: 100vh minus the header) at a 900 px viewport. */
const DEFAULT_HEIGHT = 528

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
  const [scrollTop, setScrollTop] = useState(0)
  // Until hydration the stylesheet's default height stands (.dt in globals.css); then the box is
  // fitted to the viewport below its top edge and re-fitted on resize.
  const [height, setHeight] = useState<number | null>(null)

  useLayoutEffect(() => {
    const fit = () => {
      const top = box.current?.getBoundingClientRect().top ?? 0
      setHeight(Math.max(MIN_HEIGHT, window.innerHeight - top - 24))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [])

  // A new sort or filter starts at the top.
  useEffect(() => {
    if (box.current) box.current.scrollTop = 0
    setScrollTop(0)
  }, [rows, sort])

  const n = rows.length
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN)
  const end = Math.min(n, Math.ceil((scrollTop + (height ?? DEFAULT_HEIGHT)) / ROW_HEIGHT) + OVERSCAN)
  const minWidth = columns.reduce((w, c) => w + (c.width || c.minWidth || 160), 0)

  function toggle(c: Column<R>) {
    onSort({ key: c.key, dir: sort.key === c.key && sort.dir === 'asc' ? 'desc' : 'asc' })
  }

  return (
    <div
      ref={box}
      className="dt panel"
      style={height ? { height } : undefined}
      onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
    >
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
