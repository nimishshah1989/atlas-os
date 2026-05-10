import Link from 'next/link'
import type { SectorFundRow } from '@/lib/queries/sector-funds'
import { NavStateChip, RecommendationChip } from '@/lib/fund-formatters'

function pct(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function weight(v: string | null): string {
  if (v == null) return '—'
  return `${parseFloat(v).toFixed(1)}%`
}

function GateDot({ pass }: { pass: boolean | null }) {
  if (pass === null) return <span className="font-mono text-[10px] text-ink-tertiary">?</span>
  return (
    <span className={`font-mono text-xs font-semibold ${pass ? 'text-signal-pos' : 'text-signal-neg'}`}>
      {pass ? '✓' : '✗'}
    </span>
  )
}

export function SectorFundsTab({
  funds,
  sectorName,
}: {
  funds: SectorFundRow[]
  sectorName: string
}) {
  if (funds.length === 0) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No mutual funds with {sectorName} in their top 3 sector allocations.
        </p>
      </div>
    )
  }

  return (
    <div className="px-6 py-6 space-y-4">
      <div className="font-sans text-xs text-ink-tertiary">
        {funds.length} fund{funds.length !== 1 ? 's' : ''} with {sectorName} as a top-3 sector holding — ranked by sector allocation weight.
      </div>

      <div className="overflow-x-auto">
        <table className="w-full font-sans text-xs border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">#</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Fund</th>
              <th
                className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]"
                title={`% of portfolio allocated to ${sectorName}`}
              >
                {sectorName} Wt
              </th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Rating</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">NAV State</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">RS Pctile</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">1M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">3M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">12M</th>
              <th
                className="px-3 py-2 text-center font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]"
                title="Quality gates: Performance / Sectors / Holdings / Market"
              >
                P/S/H/M
              </th>
            </tr>
          </thead>
          <tbody>
            {funds.map((f, i) => (
              <tr
                key={f.mstar_id}
                className="border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors"
              >
                <td className="px-3 py-2.5 font-mono text-ink-tertiary">{i + 1}</td>
                <td className="px-3 py-2.5">
                  <Link
                    href={`/funds/${f.mstar_id}`}
                    className="font-semibold text-ink-primary hover:text-teal transition-colors block"
                  >
                    {f.scheme_name}
                  </Link>
                  <div className="text-[10px] text-ink-tertiary">{f.amc} · {f.category_name}</div>
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-semibold text-teal">
                  {weight(f.sector_weight_pct)}
                </td>
                <td className="px-3 py-2.5">
                  <RecommendationChip value={f.recommendation} />
                </td>
                <td className="px-3 py-2.5">
                  <NavStateChip value={f.nav_state} />
                </td>
                <td className="px-3 py-2.5 text-right font-mono">
                  {f.rs_pctile_3m != null ? `${(parseFloat(f.rs_pctile_3m) * 100).toFixed(0)}` : '—'}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${f.ret_1m != null && parseFloat(f.ret_1m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pct(f.ret_1m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${f.ret_3m != null && parseFloat(f.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pct(f.ret_3m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${f.ret_12m != null && parseFloat(f.ret_12m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pct(f.ret_12m)}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center justify-center gap-1.5">
                    <GateDot pass={f.performance_gate} />
                    <GateDot pass={f.sectors_gate} />
                    <GateDot pass={f.stocks_gate} />
                    <GateDot pass={f.market_gate} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
