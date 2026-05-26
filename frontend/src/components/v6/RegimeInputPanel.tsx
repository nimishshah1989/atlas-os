'use client'
// frontend/src/components/v6/RegimeInputPanel.tsx
//
// 4-panel grid of regime classifier input sparklines:
//   1. Smallcap RS Z-score
//   2. Breadth % above 200 DMA
//   3. VIX percentile
//   4. Cross-sectional dispersion

import { Sparkline } from '@/components/ui/Sparkline'
import { CHART_COLORS } from '@/lib/chart-colors'
import type { RegimeInputRow } from '@/lib/queries/v6/regime'

type Props = {
  inputs: RegimeInputRow[]
}

// ---------------------------------------------------------------------------
// Single input tile
// ---------------------------------------------------------------------------

type TileProps = {
  label: string
  description: string
  data: (number | null)[]
  latestValue: number | null
  formatValue: (v: number) => string
  color: string
  refLine?: number
}

function InputTile({
  label,
  description,
  data,
  latestValue,
  formatValue,
  color,
  refLine,
}: TileProps) {
  const displayValue = latestValue != null ? formatValue(latestValue) : '—'

  return (
    <div
      className="border border-paper-rule rounded-[2px] bg-paper p-3"
      role="figure"
      aria-label={`${label}: ${displayValue}`}
    >
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            {label}
          </div>
          <div className="font-mono text-lg font-semibold tabular-nums text-ink-primary leading-none mt-0.5">
            {displayValue}
          </div>
        </div>
      </div>

      <Sparkline
        data={data}
        width={160}
        height={36}
        color={color}
        refLine={refLine}
        className="w-full"
        aria-label={`${label} sparkline, ${data.length} data points`}
      />

      <p className="font-sans text-[10px] text-ink-tertiary leading-snug mt-2">
        {description}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export function RegimeInputPanel({ inputs }: Props) {
  if (inputs.length === 0) {
    return (
      <div className="py-4 text-center font-sans text-sm text-ink-tertiary">
        No input data available
      </div>
    )
  }

  const latest = inputs[inputs.length - 1]

  const smallcapData = inputs.map(r => r.smallcap_rs_z)
  const breadthData  = inputs.map(r => r.breadth_pct_above_200dma)
  const vixData      = inputs.map(r => r.vix_percentile)
  const dispData     = inputs.map(r => r.cross_sectional_dispersion)

  return (
    <section
      aria-label="Regime classifier inputs"
      className="grid grid-cols-2 md:grid-cols-4 gap-3"
    >
      <InputTile
        label="Smallcap RS Z"
        description="Z-score of small-cap relative strength vs large-cap. Negative = small-cap lagging."
        data={smallcapData}
        latestValue={latest.smallcap_rs_z}
        formatValue={v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2)}
        color={CHART_COLORS.constructive}
        refLine={0}
      />

      <InputTile
        label="Breadth > 200 DMA"
        description="% of Nifty 500 stocks trading above their 200-day moving average."
        data={breadthData}
        latestValue={latest.breadth_pct_above_200dma}
        formatValue={v => `${(v * 100).toFixed(1)}%`}
        color={CHART_COLORS.rsStrong}
        refLine={0.5}
      />

      <InputTile
        label="India VIX"
        description="India VIX absolute level. >20 = elevated fear; <12 = complacency."
        data={vixData}
        latestValue={latest.vix_percentile}
        formatValue={v => v.toFixed(2)}
        color={CHART_COLORS.cautious}
        refLine={20}
      />

      <InputTile
        label="Cross-Sect. Dispersion"
        description="Realized cross-sectional return dispersion. High = stock-picker's market."
        data={dispData}
        latestValue={latest.cross_sectional_dispersion}
        formatValue={v => v.toFixed(3)}
        color={CHART_COLORS.rsConsolidating}
      />
    </section>
  )
}
