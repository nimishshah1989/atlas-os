export const dynamic = 'force-dynamic'

import { getUSSectorSummary, getUSSectorRRGHistory } from '@/lib/queries/us-sectors'
import { getUSStocks } from '@/lib/queries/us-stocks'
import { getUSETFs } from '@/lib/queries/us-etfs'
import { USPulseShell } from '@/components/us/USPulseShell'

export default async function USPulsePage() {
  const [sectors, rrgHistory, stocks, etfs] = await Promise.all([
    getUSSectorSummary(),
    getUSSectorRRGHistory(),
    getUSStocks(),
    getUSETFs(),
  ])

  const dataAsOf = sectors[0]?.data_as_of ?? null

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6 flex-wrap">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            US Pulse
          </h1>
          <span className="font-sans text-xs text-ink-secondary">
            {sectors.length} sectors &middot;{' '}
            {stocks.filter(s => s.history_gate_pass && s.liquidity_gate_pass).length} live stocks &middot;{' '}
            {etfs.length} ETFs
          </span>
        </div>
        {dataAsOf && (
          <span className="font-sans text-[11px] text-ink-tertiary">as of {dataAsOf}</span>
        )}
      </div>

      <USPulseShell sectors={sectors} rrgHistory={rrgHistory} stocks={stocks} etfs={etfs} />
    </div>
  )
}
