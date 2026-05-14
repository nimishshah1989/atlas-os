'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { rsStateColor } from '@/lib/chart-colors'
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

function RetCell({ v }: { v: string | null }) {
  if (v == null) return <td className="px-2 py-1.5 text-center text-ink-tertiary font-mono text-[11px]">—</td>
  const n = parseFloat(v) * 100
  const label = `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
  let cls = 'text-ink-tertiary'
  if (n >= 10)  cls = 'text-signal-pos font-semibold'
  else if (n >= 3)  cls = 'text-signal-pos/80'
  else if (n <= -10) cls = 'text-signal-neg font-semibold'
  else if (n <= -3)  cls = 'text-signal-neg/80'
  return <td className={`px-2 py-1.5 text-center font-mono text-[11px] ${cls}`}>{label}</td>
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

function ConsensusBadge({ bullish }: { bullish: number | null }) {
  if (bullish == null) return <span className="text-ink-tertiary">—</span>
  const score = bullish
  let cls = 'text-ink-tertiary'
  if (score >= 14) cls = 'text-signal-pos font-semibold'
  else if (score >= 10) cls = 'text-signal-pos/70'
  else if (score <= 4)  cls = 'text-signal-neg font-semibold'
  else if (score <= 8)  cls = 'text-signal-neg/70'
  return <span className={`font-mono text-[11px] ${cls}`}>{score}/20</span>
}

function StateChip({ state }: { state: string | null }) {
  if (!state) return <span className="text-ink-tertiary font-mono text-[10px]">—</span>
  const color = rsStateColor(state)
  return (
    <span
      className="font-sans text-[9px] font-semibold px-1.5 py-0.5 rounded"
      style={{ background: color + '22', color }}
    >
      {state}
    </span>
  )
}

const REGION_ORDER = [
  'Americas',
  'Europe Developed',
  'Asia-Pacific DM',
  'Asia Emerging',
  'Other Emerging',
]

type ViewMode = 'quintile' | 'returns'

const BENCHMARKS = ['ACWI', 'VT', 'EEM', 'Gold']
const TIMEFRAMES  = ['1M', '3M', '12M']

export function CountryRankingsTable({ countries }: { countries: CountryRow[] }) {
  const [view, setView] = useState<ViewMode>('quintile')
  const router = useRouter()

  return (
    <div>
      {/* Toggle */}
      <div className="flex items-center gap-2 mb-3">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">View:</span>
        {(['quintile', 'returns'] as ViewMode[]).map(v => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={[
              'px-2.5 py-1 rounded text-[10px] font-sans font-medium border transition-colors',
              view === v
                ? 'bg-teal text-white border-teal'
                : 'text-ink-secondary border-paper-rule hover:border-teal hover:text-teal',
            ].join(' ')}
          >
            {v === 'quintile' ? 'Q1–Q5' : 'Returns %'}
          </button>
        ))}
        <span className="ml-auto font-sans text-[10px] text-ink-tertiary">
          {view === 'quintile'
            ? 'Q1 = top 20% (strongest) · Q5 = bottom 20%'
            : 'Actual returns vs benchmark over timeframe'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider w-44">Country</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Seg</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">State</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-right">3M Ret</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-right">1Y Ret</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center">30W</th>
              {BENCHMARKS.map((bm, i) => (
                <th key={bm} colSpan={3} className={`px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center ${i === 0 ? 'border-l border-paper-rule' : 'border-l border-paper-rule'}`}>
                  vs {bm}
                </th>
              ))}
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center border-l border-paper-rule">Score</th>
            </tr>
            <tr className="border-b border-paper-rule bg-paper-bg/50">
              <th colSpan={6} />
              {BENCHMARKS.flatMap((_, bi) =>
                TIMEFRAMES.map((tf, ti) => (
                  <th
                    key={`${bi}-${ti}`}
                    className={`px-2 py-1 font-sans text-[9px] text-ink-tertiary text-center ${ti === 0 ? 'border-l border-paper-rule' : ''}`}
                  >
                    {tf}
                  </th>
                ))
              )}
              <th />
            </tr>
          </thead>
          <tbody>
            {REGION_ORDER.flatMap(region => {
              const rows = countries.filter(c => c.region === region)
              if (rows.length === 0) return []
              return [
                <tr key={`hdr-${region}`} className="bg-paper-bg/70">
                  <td colSpan={19} className="px-3 py-1 font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider">
                    {region}
                  </td>
                </tr>,
                ...rows.map(c => (
                  <tr
                    key={c.ticker}
                    className="border-b border-paper-rule/50 hover:bg-paper-bg/40 transition-colors cursor-pointer"
                    onClick={() => router.push(`/global/country/${encodeURIComponent(c.ticker)}`)}
                  >
                    <td className="px-3 py-1.5">
                      <div className="font-sans text-[12px] text-ink-primary hover:text-teal transition-colors">{c.country}</div>
                      <div className="font-mono text-[10px] text-ink-tertiary uppercase">{c.ticker}</div>
                    </td>
                    <td className="px-2 py-1.5">
                      <span className={`font-mono text-[9px] px-1 py-0.5 rounded ${c.is_developed_market ? 'bg-teal/10 text-teal' : 'bg-amber-500/10 text-amber-600'}`}>
                        {c.is_developed_market ? 'DM' : 'EM'}
                      </span>
                    </td>
                    <td className="px-2 py-1.5">
                      <StateChip state={c.rs_state} />
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
                    {/* ACWI */}
                    {view === 'quintile' ? <QCell q={c.q_1m_acwi} /> : <RetCell v={c.ret_1m} />}
                    {view === 'quintile' ? <QCell q={c.q_3m_acwi} /> : <RetCell v={c.ret_3m} />}
                    {view === 'quintile' ? <QCell q={c.q_12m_acwi} /> : <RetCell v={c.ret_12m} />}
                    {/* VT */}
                    {view === 'quintile' ? <QCell q={c.q_1m_vt} /> : <RetCell v={c.ret_1m} />}
                    {view === 'quintile' ? <QCell q={c.q_3m_vt} /> : <RetCell v={c.ret_3m} />}
                    {view === 'quintile' ? <QCell q={c.q_12m_vt} /> : <RetCell v={c.ret_12m} />}
                    {/* EEM */}
                    {view === 'quintile' ? <QCell q={c.q_1m_eem} /> : <RetCell v={c.ret_1m} />}
                    {view === 'quintile' ? <QCell q={c.q_3m_eem} /> : <RetCell v={c.ret_3m} />}
                    {view === 'quintile' ? <QCell q={c.q_12m_eem} /> : <RetCell v={c.ret_12m} />}
                    {/* Gold */}
                    {view === 'quintile' ? <QCell q={c.q_1m_gold} /> : <RetCell v={c.ret_1m} />}
                    {view === 'quintile' ? <QCell q={c.q_3m_gold} /> : <RetCell v={c.ret_3m} />}
                    {view === 'quintile' ? <QCell q={c.q_12m_gold} /> : <RetCell v={c.ret_12m} />}
                    <td className="px-2 py-1.5 text-center border-l border-paper-rule">
                      <ConsensusBadge bullish={c.rs_consensus_bullish} />
                    </td>
                  </tr>
                )),
              ]
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
