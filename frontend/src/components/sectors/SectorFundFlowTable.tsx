// SectorFundFlowTable — sector fund-flow: constituent-average delivery (30d/60d), up/down
// delivery asymmetry (smart-money accumulation vs distribution), and the institutional flow
// sub-score, vs the universe. Every row drills into the per-constituent "within the sector"
// view. Native atlas_foundation.delivery_daily + journal.
import type { SectorFundFlow } from '@/lib/queries/sector_lens'
import { MetricBreakdownTable, type MetricRow } from '@/components/sectors/MetricBreakdownTable'

export function SectorFundFlowTable({ data }: { data: SectorFundFlow }) {
  const c = data.constituents
  const rows: MetricRow[] = [
    {
      key: 'd30', label: 'Delivery % (30d avg)', term: 'delivery',
      sector: data.deliv_30d, universe: data.u_deliv_30d, format: 'pct',
      breakdown: c.map((x) => ({ symbol: x.symbol, value: x.deliv_30d })),
    },
    {
      key: 'd60', label: 'Delivery % (60d avg)', term: 'delivery',
      sector: data.deliv_60d, universe: data.u_deliv_60d, format: 'pct',
      breakdown: c.map((x) => ({ symbol: x.symbol, value: x.deliv_60d })),
    },
    {
      key: 'asym', label: 'Up/down delivery asym', term: 'delivery_asym',
      sector: data.updown, universe: data.u_updown, format: 'signed',
      breakdown: c.map((x) => ({ symbol: x.symbol, value: x.updown })),
    },
    {
      key: 'inst', label: 'Institutional flow score', term: 'inst_flow',
      sector: data.flow_inst, universe: data.u_flow_inst, format: 'num0',
      breakdown: c.map((x) => ({ symbol: x.symbol, value: x.flow_inst })),
    },
  ]
  return (
    <MetricBreakdownTable
      title="Sector fund flow"
      subtitle={`Constituent-average delivery (conviction of holding), up-vs-down-day delivery asymmetry (accumulation vs distribution), and the institutional-flow sub-score. ${data.n} stocks with data.`}
      footnote="Click any row to see which constituents drive the sector number (highest first)."
      rows={rows}
    />
  )
}
