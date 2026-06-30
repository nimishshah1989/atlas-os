// frontend/src/components/v6/stocks/ConvictionLandscapeSection.tsx
// Page 05 · Conviction landscape section wrapper
// 2-up layout: bubble chart (1.4fr) + 24-cell matrix (1fr)
// Client wrapper to house both interactive child components.

import type { LandscapeRow, MatrixCellAgg } from '@/lib/queries/v6/stocks-landscape'
import { ConvictionBubbleChart } from './ConvictionBubbleChart'
import { Matrix24Cell } from './Matrix24Cell'

export function ConvictionLandscapeSection({
  landscapeData,
  matrixCells,
}: {
  landscapeData: LandscapeRow[]
  matrixCells: MatrixCellAgg[]
}) {
  return (
    <section className="py-9 border-b border-paper-rule">
      <div className="max-w-[1680px] mx-auto px-8">
        <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
          <div>
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-none">
              Conviction landscape
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1 max-w-[760px] leading-snug">
              The full universe condensed into two views: a{' '}
              <strong className="text-ink-secondary">bubble chart</strong> placing each stock by RS-3M (x) and
              composite (y), sized by liquidity and coloured by action — and the{' '}
              <strong className="text-ink-secondary">24-cell methodology matrix</strong> showing how many names
              are firing in each (cap_tier × tenure × state) cell tonight, with validated IC.
            </p>
          </div>
        </div>

        {/* 2-up grid: 1.4fr bubble | 1fr matrix */}
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: '1.4fr 1fr' }}
        >
          <ConvictionBubbleChart data={landscapeData} />
          <Matrix24Cell cells={matrixCells} />
        </div>
      </div>
    </section>
  )
}
