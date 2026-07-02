// SectorsPageV4 — the Sectors list page (behind LENS_V4). All data native from
// atlas_foundation. Order: pulse + leading/lagging headline → 6-lens vector →
// multi-window heatmap (sortable, no verdict cruft) → breadth table → cap-tier RS
// charts → RRG at the bottom.
import { Suspense } from 'react'
import { getLensWeights } from '@/lib/queries/v6/lens_weights'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { Panel } from '@/components/v4/ui/Panel'
import { SectorHeroReadout } from '@/components/v6/sectors/SectorHeroReadout'
import { SectorPulseGrid } from '@/components/v6/sectors/SectorPulseGrid'
import { SectorRRGChart } from '@/components/v6/sectors/SectorRRGChart'
import { SectorHeatmapV4 } from '@/components/v6/sectors/SectorHeatmapV4'
import { SectorBreadthTable } from '@/components/v6/sectors/SectorBreadthTable'
import { CapTierRSCharts } from '@/components/v6/sectors/CapTierRSCharts'
import { getSectorCards, getSectorRRG, getSectorBreadthMV, getSectorBreadthTrend, getAllSectorConstituents } from '@/lib/queries/v6/sectors'
import { getSectorIndexRs } from '@/lib/queries/v6/sector_index_rs'
import { getAllSectorLensVectors } from '@/lib/queries/v6/sector_lens'
import { getCapTierRS } from '@/lib/queries/v6/rs_charts'

export async function SectorsPageV4() {
  // Two sequential batches — the Supabase session pooler caps total clients at 15, and each
  // of these queries fans out internally; a single 6-way Promise.all overruns it.
  const [cards, rrg, breadth, breadthTrend, indexRs] = await Promise.all([
    getSectorCards(),
    getSectorRRG(),
    getSectorBreadthMV(),
    getSectorBreadthTrend(),
    getSectorIndexRs(),
  ])
  const capTierRS = await getCapTierRS(10).catch(() => [])
  // All sectors' constituents in ONE query → the heatmap expands a sector row inline (no 21× fetch).
  const constituents = await getAllSectorConstituents().catch(() => ({}))
  // All sectors' lens vectors → the scores table shows the composite + component lens scores.
  const lensVectors = await getAllSectorLensVectors().catch(() => ({}))
  const lensWeights = await getLensWeights().catch(() => undefined)
  const latestDate = cards[0]?.as_of_date ?? null

  // CANONICAL 21 sectors = exactly what mv_sector_cards carries at the latest snapshot.
  // The pulse grid (atlas_sector_master) and RRG (mv_sector_rrg) still carry the old
  // 30-name taxonomy (EV & Auto, Housing, Consumption, Diversified, Services, Telecom…),
  // so filter every sector list down to the canonical set — one source of truth for the page.
  const canonical = new Set(cards.map(c => c.sector_name))
  const indexRsC = { ...indexRs, sectors: indexRs.sectors.filter(s => canonical.has(s.sector_name)) }
  // Heatmap rows use the REAL stored sector-index returns (atlas_index_metrics_daily via
  // getSectorIndexRs) — mv_sector_cards' return columns are a corrupt bottom-up reconstruction
  // (inflated 2–5×). RS = sector return − Nifty 500 return over the same window.
  const n500 = indexRs.bases['NIFTY 500']
  const retBySector = Object.fromEntries(indexRsC.sectors.map(s => [s.sector_name, s.ret]))
  const cardBySector = Object.fromEntries(cards.map(c => [c.sector_name, c]))
  const rel = (a: number | null, b: number | null) => (a != null && b != null ? a - b : null)
  // Heatmap gets raw sector returns + both base vectors; it computes RS for the selected
  // base (Nifty 50 / 500) client-side, so the toggle needs no refetch.
  const heatRows = [...canonical].map((name) => {
    const r = retBySector[name]
    return {
      sector_name: name,
      constituent_count: cardBySector[name]?.constituent_count ?? 0,
      ret_1d: r?.ret_1d ?? null, ret_1w: r?.ret_1w ?? null, ret_1m: r?.ret_1m ?? null,
      ret_3m: r?.ret_3m ?? null, ret_6m: r?.ret_6m ?? null, ret_12m: r?.ret_12m ?? null,
    }
  })
  const pick = (w: typeof n500) => ({ ret_1m: w?.ret_1m ?? null, ret_3m: w?.ret_3m ?? null, ret_6m: w?.ret_6m ?? null })
  const heatBases = { 'NIFTY 50': pick(indexRs.bases['NIFTY 50']), 'NIFTY 500': pick(n500) }
  // Hero readout (Leading/Lagging/Rotation) reads the SAME corrected returns — RS vs
  // Nifty 500 over 1m/3m drives the split; breadth + signal counts come from the cards.
  const heroRows = [...canonical].map((name) => {
    const r = retBySector[name]
    const c = cardBySector[name]
    return {
      sector_name: name,
      ret_1m: r?.ret_1m ?? null, ret_3m: r?.ret_3m ?? null,
      rs_1m: rel(r?.ret_1m ?? null, n500?.ret_1m ?? null),
      rs_3m: rel(r?.ret_3m ?? null, n500?.ret_3m ?? null),
      pct_above_ema21: c?.pct_above_ema21 ?? null,
      buy_signal_count: c?.buy_signal_count ?? 0,
    }
  })

  return (
    <div className="mx-auto max-w-[1680px] px-6 py-7 space-y-6">
      {/* Header */}
      <div>
        <div className="font-num text-[11px] uppercase tracking-[0.14em] text-txt-3 mb-2">
          <a href="/" className="text-brand no-underline hover:underline">Atlas</a> › Sectors
        </div>
        <h1 className="font-display text-[40px] font-medium tracking-[-0.011em] text-txt-1 leading-[1.1] mb-2">Sectors</h1>
        <p className="font-sans text-[14px] text-txt-2 max-w-[820px]">
          {cards.length} actionable sectors — where leadership is flowing, on which lens, and how each cap tier sits vs the broad market.
        </p>
      </div>

      {/* Pulse + leading/lagging headline */}
      <Panel
        eyebrow="Market pulse"
        title="Sector relative-return pulse"
        info={{ body: 'Each sector index’s return minus a selectable base index (Nifty 50 / 500) over the chosen window. Tiles open the sector.' }}
        bodyClassName="px-5 py-4 space-y-6"
      >
        <SectorPulseGrid data={indexRsC} />
        <Suspense fallback={<div className="h-40 rounded-tile bg-surface-inset animate-pulse" />}>
          <SectorHeroReadout rows={heroRows} />
        </Suspense>
      </Panel>

      {latestDate && <DataSourceBanner source="live" asOf={latestDate} />}

      {/* (Removed the composite-sorted six-lens heatmap — FM 2026-06-26: sectors are read by
          VERDICT + returns + breadth, not a composite score. The per-sector six-lens vector
          lives on the sector DETAIL page, where it's decile-framed.) */}

      {/* Multi-window heatmap — sortable, no verdict cruft */}
      <Panel
        eyebrow="Returns"
        title="Multi-window return heatmap"
        info={{ body: 'Two blocks, both in %. “Return” is each sector index’s own move. “vs Nifty 500” is the sector’s return minus the Nifty 500’s over the same window — positive means it beat the broad market. Greener = stronger, redder = weaker. Click any column to sort; click the ▸ on a sector to drop its constituent stocks inline in the same matrix.' }}
        bodyClassName="px-2 py-2"
      >
        <SectorHeatmapV4 rows={heatRows} bases={heatBases} constituents={constituents} />
      </Panel>

      {/* Sector scores — composite + component lens scores; click a row to derive the score */}
      <Panel
        eyebrow="Scores"
        title="Sector scores · conviction & breadth"
        info={{ body: 'Each sector’s 0–100 conviction score (composite = 0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst, over the free-float-weighted sector lens vector) plus its four component lens scores and one breadth read. Click a sector to see exactly how its score is derived, the rest of the breadth detail, and its top movers.' }}
        bodyClassName="px-5 py-4"
      >
        <SectorBreadthTable rows={breadth} trend={breadthTrend} lensBySector={lensVectors} weights={lensWeights} />
      </Panel>

      {/* Cap-tier RS charts — native */}
      {capTierRS.length > 0 && <CapTierRSCharts series={capTierRS} />}

      {/* RRG — at the bottom */}
      <Panel
        eyebrow="Rotation"
        title="Sector rotation graph (RRG)"
        info={{ body: 'RS-ratio (x) vs RS-momentum (y). Sectors rotate Leading → Weakening → Lagging → Improving. Trails show the 6-week path.' }}
        bodyClassName="px-5 py-4"
      >
        <Suspense fallback={<div className="h-[560px] rounded-tile bg-surface-inset animate-pulse" />}>
          <SectorRRGChart data={rrg} />
        </Suspense>
      </Panel>

      <div className="font-sans text-[12px] text-txt-3 leading-[1.6]">
        Native from <strong className="text-txt-2">atlas_foundation</strong> — sector cards / RRG / breadth, index prices, and the lens journal.
      </div>
    </div>
  )
}
