// SectorFundamentalsTable — revenue-weighted sector margins (Σebitda/Σrevenue) + share of
// constituents that are profitable, vs the all-stock universe. Every row drills into the
// per-constituent "within the sector" view. Native foundation_staging.financials_quarterly.
import type { SectorFundamentals } from '@/lib/queries/v6/sector_lens'
import { MetricBreakdownTable, type MetricRow } from '@/components/v6/sectors/MetricBreakdownTable'

export function SectorFundamentalsTable({ data }: { data: SectorFundamentals }) {
  const c = data.constituents
  const rows: MetricRow[] = [
    {
      key: 'ebitda', label: 'EBITDA margin', term: 'ebitda_margin',
      sector: data.ebitda_margin, universe: data.u_ebitda_margin, format: 'pct',
      breakdown: c.map((x) => ({ symbol: x.symbol, value: x.ebitda_margin })),
    },
    {
      key: 'net', label: 'Net margin', term: 'net_margin',
      sector: data.net_margin, universe: data.u_net_margin, format: 'pct',
      breakdown: c.map((x) => ({ symbol: x.symbol, value: x.net_margin })),
    },
    {
      key: 'profitable', label: '% profitable', term: 'pct_profitable',
      sector: data.pct_profitable, universe: data.u_pct_profitable, format: 'pct', kind: 'flag',
      breakdown: c.map((x) => ({
        symbol: x.symbol,
        value: x.profitable == null ? null : x.profitable ? 1 : 0,
        note: x.profitable == null ? '—' : x.profitable ? 'Profitable' : 'Loss',
      })),
    },
  ]
  return (
    <MetricBreakdownTable
      title="Sector fundamentals"
      subtitle={`Revenue-weighted profitability (latest filed quarter) vs the all-stock universe — the big names count more, not equally. ${data.n} of the sector's stocks have financials.`}
      footnote="Click any row to expand every constituent's own figure (highest first). Margins are weighted by revenue, so one tiny loss-maker can't distort the sector read."
      rows={rows}
    />
  )
}
