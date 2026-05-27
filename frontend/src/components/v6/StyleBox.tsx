// frontend/src/components/v6/StyleBox.tsx
//
// Morningstar-style 3×3 grid. Rows: Large / Mid / Small (top-down).
// Columns: Value / Blend / Growth (left-right).
// Each cell shows count + on-hover top funds list.

import type { StyleSize, StyleAxis } from '@/lib/api/v1'

type StyleCell = {
  size: StyleSize
  style: StyleAxis
  count: number
  topFunds?: { name: string; code: string }[]
}

type Props = {
  cells: StyleCell[]
  /** Active cell to highlight (e.g. fund's own slot on /funds/[code]). */
  activeCell?: { size: StyleSize; style: StyleAxis }
}

const SIZES: StyleSize[] = ['Large', 'Mid', 'Small']
const STYLES: StyleAxis[] = ['Value', 'Blend', 'Growth']

export function StyleBox({ cells, activeCell }: Props) {
  const lookup = new Map(cells.map(c => [`${c.size}-${c.style}`, c]))
  return (
    <div className="inline-block">
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1.5 text-center">
        Style Box
      </div>
      <div className="grid grid-cols-[28px_repeat(3,72px)] grid-rows-[20px_repeat(3,72px)] gap-px border border-paper-rule bg-paper-rule">
        {/* corner */}
        <div className="bg-paper" />
        {STYLES.map(s => (
          <div key={s} className="bg-paper font-sans text-[10px] uppercase tracking-wider text-ink-tertiary flex items-center justify-center">
            {s}
          </div>
        ))}
        {SIZES.map(size => (
          <RowFragment key={size} size={size} lookup={lookup} activeCell={activeCell} />
        ))}
      </div>
    </div>
  )
}

function RowFragment({
  size,
  lookup,
  activeCell,
}: {
  size: StyleSize
  lookup: Map<string, StyleCell>
  activeCell?: { size: StyleSize; style: StyleAxis }
}) {
  return (
    <>
      <div className="bg-paper font-sans text-[10px] uppercase tracking-wider text-ink-tertiary flex items-center justify-center" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>
        {size}
      </div>
      {STYLES.map(style => {
        const cell = lookup.get(`${size}-${style}`)
        const isActive = activeCell?.size === size && activeCell?.style === style
        const isEmpty = !cell || cell.count === 0
        return (
          <div
            key={`${size}-${style}`}
            className={`flex flex-col items-center justify-center font-mono tabular-nums ${
              isActive ? 'bg-teal/15 text-teal' :
              isEmpty ? 'bg-paper text-ink-tertiary' :
              'bg-paper hover:bg-paper-rule/20 text-ink-primary'
            } cursor-default`}
            title={cell?.topFunds?.map(f => f.name).join('\n') ?? ''}
          >
            <span className={`${isActive ? 'text-base font-semibold' : 'text-sm font-semibold'}`}>
              {cell?.count ?? 0}
            </span>
            <span className="text-[9px] text-ink-tertiary mt-0.5">
              {isActive ? '◆' : 'funds'}
            </span>
          </div>
        )
      })}
    </>
  )
}
