'use client'

import type { CountryRow } from '@/lib/queries/global'

const QUINTILE_COLORS: Record<number, string> = {
  1: 'bg-signal-pos/20 text-signal-pos font-semibold',
  2: 'bg-signal-pos/10 text-signal-pos/80',
  3: 'bg-paper-rule text-ink-tertiary',
  4: 'bg-signal-neg/10 text-signal-neg/80',
  5: 'bg-signal-neg/20 text-signal-neg font-semibold',
}

function QCell({ q }: { q: number | null }) {
  if (q == null) return <td className="px-2 py-1.5 text-center text-ink-tertiary font-mono text-[11px]">—</td>
  return (
    <td className={`px-2 py-1.5 text-center font-mono text-[11px] ${QUINTILE_COLORS[q] ?? ''}`}>
      Q{q}
    </td>
  )
}

function Pct({ v }: { v: string | null }) {
  if (v == null) return <span className="text-ink-tertiary">—</span>
  const n = parseFloat(v)
  const label = `${n >= 0 ? '+' : ''}${(n * 100).toFixed(1)}%`
  return (
    <span className={n >= 0 ? 'text-signal-pos' : 'text-signal-neg'}>
      {label}
    </span>
  )
}

function ConsensusBadge({ bullish, bearish }: { bullish: number | null; bearish: number | null }) {
  if (bullish == null) return <span className="text-ink-tertiary">—</span>
  const score = bullish ?? 0
  let cls = 'text-ink-tertiary'
  if (score >= 14) cls = 'text-signal-pos font-semibold'
  else if (score >= 10) cls = 'text-signal-pos/70'
  else if (score <= 4) cls = 'text-signal-neg font-semibold'
  else if (score <= 8) cls = 'text-signal-neg/70'
  return <span className={`font-mono text-[11px] ${cls}`}>{score}/20</span>
}

const REGION_ORDER = [
  'Americas',
  'Europe Developed',
  'Asia-Pacific DM',
  'Asia Emerging',
  'Other Emerging',
]

type SortKey = 'consensus' | 'pctile_vt' | 'ret_3m' | 'region'

export function CountryRankingsTable({ countries }: { countries: CountryRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider w-44">Country</th>
            <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Seg</th>
            <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-right">3M Ret</th>
            <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-right">1Y Ret</th>
            <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center">30W</th>
            {/* RS quintile columns */}
            <th colSpan={3} className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center border-l border-paper-rule">vs ACWI</th>
            <th colSpan={3} className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center border-l border-paper-rule">vs VT</th>
            <th colSpan={3} className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center border-l border-paper-rule">vs EEM</th>
            <th colSpan={3} className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center border-l border-paper-rule">vs Gold</th>
            <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center border-l border-paper-rule">Score</th>
          </tr>
          <tr className="border-b border-paper-rule bg-paper-bg/50">
            <th colSpan={5} />
            {['1M', '3M', '12M', '1M', '3M', '12M', '1M', '3M', '12M', '1M', '3M', '12M'].map((tf, i) => (
              <th key={i} className={`px-2 py-1 font-sans text-[9px] text-ink-tertiary text-center ${i % 3 === 0 ? 'border-l border-paper-rule' : ''}`}>{tf}</th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {REGION_ORDER.flatMap(region => {
            const rows = countries.filter(c => c.region === region)
            if (rows.length === 0) return []
            return [
              <tr key={`hdr-${region}`} className="bg-paper-bg/70">
                <td colSpan={18} className="px-3 py-1 font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider">
                  {region}
                </td>
              </tr>,
              ...rows.map(c => (
                <tr key={c.ticker} className="border-b border-paper-rule/50 hover:bg-paper-bg/40 transition-colors">
                  <td className="px-3 py-1.5">
                    <div className="font-sans text-[12px] text-ink-primary">{c.country}</div>
                    <div className="font-mono text-[10px] text-ink-tertiary uppercase">{c.ticker}</div>
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={`font-mono text-[9px] px-1 py-0.5 rounded ${c.is_developed_market ? 'bg-teal/10 text-teal' : 'bg-amber-500/10 text-amber-600'}`}>
                      {c.is_developed_market ? 'DM' : 'EM'}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-[11px]"><Pct v={c.ret_3m} /></td>
                  <td className="px-2 py-1.5 text-right font-mono text-[11px]"><Pct v={c.ret_12m} /></td>
                  <td className="px-2 py-1.5 text-center">
                    {c.above_30w_ma == null ? (
                      <span className="text-ink-tertiary">—</span>
                    ) : (
                      <span className={`w-2 h-2 rounded-full inline-block ${c.above_30w_ma ? 'bg-signal-pos' : 'bg-signal-neg'}`} />
                    )}
                  </td>
                  <QCell q={c.q_1m_acwi} />
                  <QCell q={c.q_3m_acwi} />
                  <QCell q={c.q_12m_acwi} />
                  <QCell q={c.q_1m_vt} />
                  <QCell q={c.q_3m_vt} />
                  <QCell q={c.q_12m_vt} />
                  <QCell q={c.q_1m_eem} />
                  <QCell q={c.q_3m_eem} />
                  <QCell q={c.q_12m_eem} />
                  <QCell q={c.q_1m_gold} />
                  <QCell q={c.q_3m_gold} />
                  <QCell q={c.q_12m_gold} />
                  <td className="px-2 py-1.5 text-center border-l border-paper-rule">
                    <ConsensusBadge bullish={c.rs_consensus_bullish} bearish={c.rs_consensus_bearish} />
                  </td>
                </tr>
              )),
            ]
          })}
        </tbody>
      </table>
    </div>
  )
}
