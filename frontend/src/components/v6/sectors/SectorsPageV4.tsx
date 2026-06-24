// SectorsPageV4 — the merged Sectors ⊕ Markets-RS page (behind LENS_V4). All data native
// from foundation_staging. Order per spec: pulse + leading/lagging headline → 6-lens vector →
// multi-window heatmap (sortable, no verdict cruft) → breadth table → cap-tier RS charts →
// global cross-market RS grid → RRG at the bottom.
import { Suspense } from 'react'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorHeroReadout } from '@/components/v6/sectors/SectorHeroReadout'
import { SectorPulseGrid } from '@/components/v6/sectors/SectorPulseGrid'
import { SectorRRGChart } from '@/components/v6/sectors/SectorRRGChart'
import { SectorHeatmapV4 } from '@/components/v6/sectors/SectorHeatmapV4'
import { SectorBreadthTable } from '@/components/v6/sectors/SectorBreadthTable'
import { SectorLensHeatmap } from '@/components/v6/sectors/SectorLensHeatmap'
import { CapTierRSCharts } from '@/components/v6/sectors/CapTierRSCharts'
import { getSectorCards, getSectorRRG, getSectorBreadthMV } from '@/lib/queries/v6/sectors'
import { getSectorIndexRs } from '@/lib/queries/v6/sector_index_rs'
import { getSectorLensVectors } from '@/lib/queries/lens-scores'
import { getMarketsRsPage, type MarketsRsRow } from '@/lib/queries/v6/markets_rs'

function SectionHead({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-5">
      <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">{title}</h2>
      {subtitle && <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">{subtitle}</p>}
    </div>
  )
}

// Global cross-market RS grid (folded in from Markets-RS) — compact table.
function GlobalRsGrid({ grid }: { grid: MarketsRsRow[] }) {
  const W: [string, keyof MarketsRsRow][] = [['1W', 'ret_1w'], ['1M', 'ret_1m'], ['3M', 'ret_3m'], ['6M', 'ret_6m'], ['12M', 'ret_12m']]
  const fmt = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`)
  const col = (v: number | null) => (v == null ? 'text-ink-tertiary' : v > 0 ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-secondary')
  return (
    <table className="w-full text-right">
      <thead>
        <tr className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider border-b border-paper-rule">
          <th className="text-left py-1.5 font-medium">Baseline</th>
          {W.map(([l]) => <th key={l} className="py-1.5 font-medium">{l}</th>)}
        </tr>
      </thead>
      <tbody>
        {grid.map(r => (
          <tr key={r.baseline_name} className="border-b border-paper-rule/40">
            <td className="text-left py-1.5 font-sans text-xs text-ink-secondary">{r.baseline_name}</td>
            {W.map(([l, k]) => {
              const v = r[k] as number | null
              return <td key={l} className={`py-1.5 font-mono text-xs tabular-nums ${col(v)}`}>{fmt(v)}</td>
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export async function SectorsPageV4() {
  // Two sequential batches — the Supabase session pooler caps total clients at 15, and each
  // of these queries fans out internally; a single 7-way Promise.all overruns it.
  const [cards, rrg, breadth, indexRs] = await Promise.all([
    getSectorCards(),
    getSectorRRG(),
    getSectorBreadthMV(),
    getSectorIndexRs(),
  ])
  const [lensVectors, marketsRs] = await Promise.all([
    getSectorLensVectors().catch(() => []),
    getMarketsRsPage().catch(() => ({ grid: [] as MarketsRsRow[], as_of_date: null })),
  ])
  const latestDate = cards[0]?.as_of_date ?? null
  const idxRet1dBySector: Record<string, number | null> = Object.fromEntries(
    indexRs.sectors.map(s => [s.sector_name, s.ret.ret_1d]),
  )

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header + pulse + leading/lagging headline */}
      <div className="px-8 py-8 border-b border-paper-rule">
        <div className="font-sans text-[12px] text-ink-tertiary mb-3">
          <a href="/" className="text-teal no-underline hover:underline">Atlas</a> › Sectors
        </div>
        <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.1] mb-2">Sectors</h1>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[820px]">
          {cards.length} actionable sectors — where leadership is flowing, on which lens, and how each cap tier sits vs the broad market.
        </p>
        <SectorPulseGrid data={indexRs} />
        <Suspense fallback={<div className="h-40 bg-paper-rule/20 rounded-sm mt-6 animate-pulse" />}>
          <SectorHeroReadout cards={cards} rrg={rrg} />
        </Suspense>
      </div>

      {latestDate && <DataSourceBanner source="live" asOf={latestDate} />}

      {/* Six-lens sector vector */}
      {lensVectors.length > 0 && (
        <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector six-lens vector">
          <SectionHead title="Sector six-lens vector" subtitle="Average lens score per sector (technical · fundamental · valuation · catalyst · flow · policy). Sorted by composite." />
          <SectorLensHeatmap vectors={lensVectors} />
        </section>
      )}

      {/* Multi-window heatmap — moved up, sortable, no verdict cruft */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector return heatmap">
        <SectionHead title="Multi-window return heatmap" subtitle="Absolute returns + RS spread vs Nifty 500 across windows. Click any column to sort. 1D = NSE sector index; rest bottom-up." />
        <SectorHeatmapV4 cards={cards} idxRet1dBySector={idxRet1dBySector} />
      </section>

      {/* Sector breadth — compact table */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector breadth">
        <SectionHead title="Sector breadth · EMA participation" subtitle="Share of each sector's constituents above the 20 / 50 / 200-EMA. Sorted by EMA20 participation." />
        <SectorBreadthTable rows={breadth} />
      </section>

      {/* Cap-tier RS charts — direct TradingView ratio embeds */}
      <CapTierRSCharts />

      {/* Global cross-market RS grid — folded from Markets-RS */}
      {marketsRs.grid.length > 0 && (
        <section className="px-8 py-10 border-b border-paper-rule" aria-label="Cross-market relative strength">
          <SectionHead title="Cross-market relative strength" subtitle="Trailing returns of the India tiers vs global baselines (S&P 500, MSCI World/EM, Gold). Window returns, ranked across baselines." />
          <GlobalRsGrid grid={marketsRs.grid} />
        </section>
      )}

      {/* RRG — moved to the bottom */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector Relative Rotation Graph">
        <SectionHead title="Sector rotation graph (RRG)" subtitle="RS-ratio (x) vs RS-momentum (y). Sectors rotate Leading → Weakening → Lagging → Improving. Trails show the 6-week path." />
        <Suspense fallback={<div className="h-[560px] bg-paper-rule/20 rounded-sm animate-pulse" />}>
          <SectorRRGChart data={rrg} />
        </Suspense>
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — sector cards / RRG / breadth, index prices, and the lens journal.
      </div>
    </div>
  )
}
