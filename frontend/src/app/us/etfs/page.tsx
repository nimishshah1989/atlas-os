export const dynamic = 'force-dynamic'

import { getUSETFs } from '@/lib/queries/us-etfs'
import { USSectorHeatmap } from '@/components/us/USSectorHeatmap'
import { USETFScreener } from '@/components/us/USETFScreener'

export default async function USETFsPage() {
  const etfs = await getUSETFs()

  if (etfs.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No US ETF data available. Run the US stocks backfill first.
        </p>
      </div>
    )
  }

  const dataAsOf    = etfs.find(e => e.data_as_of)?.data_as_of ?? null
  const leaderCount = etfs.filter(e => e.rs_state === 'Leader' || e.rs_state === 'Strong').length
  const sectorCount = etfs.filter(e => e.etf_category?.toLowerCase().includes('sector')).length
  const avgPctile   = (() => {
    const vals = etfs.map(e => parseFloat(e.rs_pctile_3m_vt ?? '0')).filter(v => !isNaN(v))
    if (vals.length === 0) return null
    return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length * 100)
  })()

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6 flex-wrap">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            US ETF Universe
          </h1>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-ink-tertiary" />
            {etfs.length} ETFs
          </span>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-teal" />
            {sectorCount} Sector ETFs
          </span>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
            {leaderCount} Leader/Strong
          </span>
          {avgPctile !== null && (
            <span className="font-sans text-xs text-ink-secondary">
              Avg VT pctile: {avgPctile}%
            </span>
          )}
        </div>
        {dataAsOf && (
          <span className="font-sans text-[11px] text-ink-tertiary">as of {dataAsOf}</span>
        )}
      </div>

      {/* Sector rotation heatmap */}
      <div className="px-6 pt-4">
        <USSectorHeatmap etfs={etfs} />
      </div>

      {/* ETF screener */}
      <div className="px-6 py-4">
        <USETFScreener etfs={etfs} />
      </div>
    </div>
  )
}
