// frontend/src/components/v6/india-pulse/HeroStrip.tsx
//
// 4-tile hero strip: the four regime inputs shown at the top of India Pulse.
// Server component (no interactivity needed).

import type { IndiaPulsePageData } from '@/lib/queries/v6/india_pulse'
import { fmtZ, fmtPctAbs, fmtNum } from './helpers'

type Props = {
  data: Pick<
    IndiaPulsePageData,
    | 'smallcap_rs_z'
    | 'breadth_pct_above_200dma'
    | 'india_vix'
    | 'cross_section_dispersion'
  >
}

function heroValueColor(
  id: 'sc_rs_z' | 'breadth' | 'vix' | 'dispersion',
  value: number | null,
): string {
  if (value == null) return 'text-ink-tertiary font-mono text-[28px] font-medium'
  const base = 'font-mono text-[28px] font-medium'
  switch (id) {
    case 'sc_rs_z':
      return value < 0 ? `${base} text-signal-neg` : `${base} text-signal-pos`
    case 'breadth':
      return value < 0.5 ? `${base} text-signal-warn` : `${base} text-signal-pos`
    case 'vix':
      return value > 20 ? `${base} text-signal-neg` : value > 15 ? `${base} text-signal-warn` : `${base} text-signal-pos`
    case 'dispersion':
      return `${base} text-signal-pos`
  }
}

export function HeroStrip({ data }: Props) {
  const { smallcap_rs_z, breadth_pct_above_200dma, india_vix, cross_section_dispersion } = data

  const tiles = [
    {
      label: 'Small-cap RS Z-score',
      value: fmtZ(smallcap_rs_z),
      colorId: 'sc_rs_z' as const,
      raw: smallcap_rs_z,
      foot: smallcap_rs_z != null && smallcap_rs_z < 0
        ? 'Small-caps lagging large-caps; leadership has shifted to large-cap.'
        : 'Small-caps leading or neutral vs large-caps.',
    },
    {
      label: 'Breadth — % above 200 DMA',
      value:
        breadth_pct_above_200dma != null
          ? `${(breadth_pct_above_200dma * 100).toFixed(0)}%`
          : '—',
      colorId: 'breadth' as const,
      raw: breadth_pct_above_200dma,
      foot:
        breadth_pct_above_200dma != null
          ? breadth_pct_above_200dma < 0.5
            ? 'Less than half the Nifty 500 trading above its 200-day average.'
            : 'Majority of Nifty 500 trading above 200-day average.'
          : 'Data unavailable.',
    },
    {
      label: 'India VIX',
      value: fmtNum(india_vix, 1),
      colorId: 'vix' as const,
      raw: india_vix,
      foot:
        india_vix != null
          ? india_vix > 20
            ? 'Elevated implied volatility — investor caution high.'
            : india_vix > 15
            ? 'VIX climbing — options markets starting to hedge.'
            : 'VIX at or below the 12-month average — calm environment.'
          : 'Data unavailable.',
    },
    {
      label: 'Cross-section dispersion',
      value:
        cross_section_dispersion != null
          ? cross_section_dispersion.toFixed(3)
          : '—',
      colorId: 'dispersion' as const,
      raw: cross_section_dispersion,
      foot:
        cross_section_dispersion != null
          ? cross_section_dispersion > 0.07
            ? 'Wide. Stocks moving differently — stock-picker environment.'
            : 'Narrow. Stocks highly correlated — regime, not stock-picking.'
          : 'Data unavailable.',
    },
  ]

  return (
    <div className="mt-6 grid grid-cols-4 bg-paper border border-paper-rule rounded-sm overflow-hidden">
      {tiles.map((tile, i) => (
        <div
          key={tile.label}
          className={`p-5 ${i < 3 ? 'border-r border-paper-rule' : ''}`}
        >
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1.5">
            {tile.label}
          </div>
          <div className={heroValueColor(tile.colorId, tile.raw)}>
            {tile.value}
          </div>
          <div className="text-[11px] text-ink-tertiary mt-1.5 leading-[1.45]">
            {tile.foot}
          </div>
        </div>
      ))}
    </div>
  )
}
