export const dynamic = 'force-dynamic'

import { getRecommendationsToday, type RecommendationRow } from '@/lib/queries/strategy_lab'

function bandColor(band: RecommendationRow['confidence_band']): string {
  if (band === 'HIGH') return 'text-teal-700 bg-teal-50 border-teal-200'
  if (band === 'MEDIUM') return 'text-amber-700 bg-amber-50 border-amber-200'
  return 'text-stone-600 bg-stone-50 border-stone-200'
}

function fmtPct(s: string | null, decimals = 2): string {
  if (s === null) return '—'
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(decimals)}%`
}

function fmtNum(s: string | null, decimals = 2): string {
  if (s === null) return '—'
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(decimals)
}

function fmtPrice(s: string | null): string {
  if (s === null) return '—'
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

export default async function TodayPage() {
  const recs = await getRecommendationsToday()

  if (recs.length === 0) {
    return (
      <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
        <h1 className="font-serif text-3xl text-ink-900 mb-2">Today&apos;s Recommendations</h1>
        <p className="text-ink-600 mb-8">No recommendations yet. The Strategy Lab nightly job has not produced a leaderboard or today&apos;s picks have not been written.</p>
      </main>
    )
  }

  const asOf = recs[0].date
  const byGenome = new Map<string, RecommendationRow[]>()
  for (const r of recs) {
    if (!byGenome.has(r.genome_id)) byGenome.set(r.genome_id, [])
    byGenome.get(r.genome_id)!.push(r)
  }

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      <header className="mb-8">
        <h1 className="font-serif text-3xl text-ink-900">Today&apos;s Recommendations</h1>
        <p className="text-sm text-ink-500 mt-1">
          As of {new Date(asOf).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
        </p>
      </header>

      <div className="space-y-8">
        {Array.from(byGenome.entries()).map(([gid, rows]) => {
          const head = rows[0]
          return (
            <section key={gid} className="border border-paper-rule rounded-lg bg-white">
              <header className="px-5 py-4 border-b border-paper-rule flex items-baseline justify-between">
                <div>
                  <div className="font-serif text-xl text-ink-900">{head.strategy_name}</div>
                  <div className="text-xs text-ink-500 mt-0.5">Rank #{head.rank} · genome {gid.slice(0, 8)}</div>
                </div>
                <div className={`px-3 py-1 text-xs font-medium border rounded ${bandColor(head.confidence_band)}`}>
                  {head.confidence_band} confidence
                </div>
              </header>
              <div className="px-5 py-3 grid grid-cols-4 gap-4 text-sm border-b border-paper-rule bg-stone-50/50">
                <div>
                  <div className="text-xs text-ink-500">Alpha (OOS)</div>
                  <div className="font-mono text-ink-900">{fmtPct(head.genome_alpha_oos, 2)}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-500">Information ratio</div>
                  <div className="font-mono text-ink-900">{fmtNum(head.genome_information_ratio, 2)}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-500">Hit rate</div>
                  <div className="font-mono text-ink-900">{fmtPct(head.genome_hit_rate, 0)}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-500">Alpha t-stat</div>
                  <div className="font-mono text-ink-900">{fmtNum(head.genome_t_stat, 2)}</div>
                </div>
              </div>
              <table className="w-full text-sm">
                <thead className="text-xs text-ink-500 border-b border-paper-rule">
                  <tr>
                    <th className="text-left px-5 py-2 font-normal">Stock</th>
                    <th className="text-right px-5 py-2 font-normal">Size</th>
                    <th className="text-right px-5 py-2 font-normal">Stop</th>
                    <th className="text-right px-5 py-2 font-normal">Conviction</th>
                    <th className="text-left px-5 py-2 font-normal">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.genome_id}-${r.instrument_id}-${r.action}`} className="border-b border-paper-rule/40 last:border-0">
                      <td className="px-5 py-2">
                        <div className="font-medium text-ink-900">{r.ticker ?? r.instrument_id.slice(0, 8)}</div>
                        {r.company_name ? (
                          <div className="text-xs text-ink-500">{r.company_name}</div>
                        ) : null}
                      </td>
                      <td className="px-5 py-2 text-right font-mono">{fmtPct(r.position_size_pct, 2)}</td>
                      <td className="px-5 py-2 text-right font-mono">{fmtPrice(r.stop_price)}</td>
                      <td className="px-5 py-2 text-right font-mono">{fmtNum(r.conviction, 2)}</td>
                      <td className="px-5 py-2 font-medium text-ink-900">{r.action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )
        })}
      </div>
    </main>
  )
}
