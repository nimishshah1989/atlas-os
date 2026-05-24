// frontend/src/app/v6/etfs/page.tsx
// v6 ETFs — POSITIVE/NEUTRAL only.

import { getScreenEtfs } from '@/lib/api/v1'
import { ConvictionTape } from '@/components/v6/ConvictionTape'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { LinkedETF } from '@/components/ui/LinkedToken'
import { StateBadge } from '@/components/ui/StateBadge'
import { formatINR } from '@/lib/format-inr'

export const dynamic = 'force-dynamic'

function pctSigned(v: number | null) {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  const sign = pct >= 0 ? '+' : ''
  return { text: `${sign}${pct.toFixed(1)}%`, cls: pct >= 0 ? 'text-signal-pos' : 'text-signal-neg' }
}

export default async function V6EtfsPage() {
  const { data: etfs, meta, source_kind } = await getScreenEtfs()

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          ETFs · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          ETF Universe
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {etfs.length} ETFs with conviction tape across 4 tenures. ETFs only carry
          POSITIVE/NEUTRAL directions (no shorting domain).
        </p>
      </div>

      <DataSourceBanner source={source_kind} asOf={meta.data_as_of} />

      <div className="overflow-x-auto border border-paper-rule rounded-[2px] mx-6 my-4">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Ticker</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Name</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Category</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">AUM</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Conviction</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">RS</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">1M</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">3M</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">12M</th>
            </tr>
          </thead>
          <tbody>
            {etfs.map((e, i) => {
              const r1 = pctSigned(e.ret_1m)
              const r3 = pctSigned(e.ret_3m)
              const r12 = pctSigned(e.ret_12m)
              return (
                <tr key={e.iid} className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <LinkedETF ticker={e.ticker} />
                  </td>
                  <td className="px-3 py-2.5 font-sans text-xs text-ink-secondary">{e.name}</td>
                  <td className="px-3 py-2.5 font-sans text-[11px] text-ink-tertiary whitespace-nowrap">{e.category}</td>
                  <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap">{formatINR(e.aum_inr)}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <ConvictionTape tape={e.conviction_tape} compact />
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {e.rs_state ? <StateBadge state={e.rs_state} size="sm" /> : <span className="font-mono text-xs text-ink-tertiary">—</span>}
                  </td>
                  <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r1.cls}`}>{r1.text}</td>
                  <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r3.cls}`}>{r3.text}</td>
                  <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r12.cls}`}>{r12.text}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
