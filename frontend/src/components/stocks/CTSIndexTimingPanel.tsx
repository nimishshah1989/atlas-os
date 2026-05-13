'use client'
import { useState, useEffect } from 'react'

type IndexTimingRow = {
  index_name: string
  plus_a: number
  plus_b: number
  neutral: number
  minus_b: number
  minus_a: number
  total: number
}

type ApiResponse = { rows: IndexTimingRow[]; as_of: string }

type Grade = '+A' | '+B' | '—' | '−B' | '−A'

const GRADE_STYLES: Record<Grade, { badge: string; label: string; desc: string }> = {
  '+A': { badge: 'bg-teal text-white',                                        label: '+A', desc: 'Buy · Act now' },
  '+B': { badge: 'bg-teal/10 text-teal border border-teal/40',               label: '+B', desc: 'Buy · Watch' },
  '—':  { badge: 'bg-paper-rule/40 text-ink-tertiary',                       label: '—',  desc: 'Neutral' },
  '−B': { badge: 'bg-amber-500/10 text-amber-500 border border-amber-500/40', label: '−B', desc: 'Sell · Watch' },
  '−A': { badge: 'bg-signal-neg text-white',                                  label: '−A', desc: 'Sell · Act now' },
}

function aggregateGrade(row: IndexTimingRow): Grade {
  if (row.total === 0) return '—'
  const buyPct  = (row.plus_a  + row.plus_b)  / row.total
  const sellPct = (row.minus_a + row.minus_b) / row.total
  const net = buyPct - sellPct
  if (net >= 0.25 && row.plus_a  > 0) return '+A'
  if (net >= 0.10)                     return '+B'
  if (net <= -0.25 && row.minus_a > 0) return '−A'
  if (net <= -0.10)                    return '−B'
  return '—'
}

function GradeBar({ row }: { row: IndexTimingRow }) {
  const buyW   = Math.round(((row.plus_a  + row.plus_b)  / row.total) * 100)
  const neutW  = Math.round((row.neutral                 / row.total) * 100)
  const sellW  = Math.round(((row.minus_a + row.minus_b) / row.total) * 100)
  return (
    <div className="flex h-2 rounded-full overflow-hidden w-full gap-px">
      {buyW  > 0 && <div className="bg-teal"        style={{ width: `${buyW}%`  }} title={`Buy ${buyW}%`} />}
      {neutW > 0 && <div className="bg-paper-rule"  style={{ width: `${neutW}%` }} title={`Neutral ${neutW}%`} />}
      {sellW > 0 && <div className="bg-signal-neg"  style={{ width: `${sellW}%` }} title={`Sell ${sellW}%`} />}
    </div>
  )
}

function IndexCard({ row }: { row: IndexTimingRow }) {
  const grade = aggregateGrade(row)
  const gs    = GRADE_STYLES[grade]
  const buyPct  = row.total > 0 ? Math.round(((row.plus_a + row.plus_b)  / row.total) * 100) : 0
  const sellPct = row.total > 0 ? Math.round(((row.minus_a + row.minus_b) / row.total) * 100) : 0

  return (
    <div className="flex flex-col gap-2 p-3 border border-paper-rule rounded-sm bg-paper min-w-[160px]">
      <div className="flex items-center justify-between gap-2">
        <span className="font-sans text-xs font-semibold text-ink-primary">{row.index_name}</span>
        <span className={`inline-flex items-center justify-center w-8 h-6 rounded font-mono text-xs font-bold ${gs.badge}`}>
          {gs.label}
        </span>
      </div>

      <GradeBar row={row} />

      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1">
            <span className="font-mono text-[10px] font-semibold text-teal">{buyPct}%</span>
            <span className="font-sans text-[9px] text-ink-tertiary">buy</span>
            {row.plus_a > 0 && (
              <span className="font-mono text-[9px] text-teal">({row.plus_a} +A)</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <span className="font-mono text-[10px] font-semibold text-signal-neg">{sellPct}%</span>
            <span className="font-sans text-[9px] text-ink-tertiary">sell</span>
            {row.minus_a > 0 && (
              <span className="font-mono text-[9px] text-signal-neg">({row.minus_a} −A)</span>
            )}
          </div>
        </div>
        <span className="font-sans text-[9px] text-ink-tertiary text-right">{row.total} stocks</span>
      </div>
    </div>
  )
}

export function CTSIndexTimingPanel() {
  const [data, setData]       = useState<IndexTimingRow[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)

  useEffect(() => {
    fetch('/api/cts/index-timing')
      .then(r => r.json() as Promise<ApiResponse>)
      .then(d => { setData(d.rows); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  return (
    <div className="border border-paper-rule rounded-sm">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-paper-rule/10 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center gap-3">
          <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
            Market Timing
          </span>
          <span className="font-sans text-[10px] text-ink-tertiary" title={[
            'Grade aggregated from individual stock CTS signals across the index constituents.',
            '',
            'Each stock is graded: +A (Stage 2 + Pocket Pivot), +B (Stage 2), — (neutral),',
            '−B (Stage 3 topping), or −A (Stage 4 / Stage 3 + Negative Pivot).',
            '',
            'Index grade = net directional score across all constituents:',
            '  +A if (buy% − sell%) ≥ 25% and at least one +A stock',
            '  +B if net ≥ 10%  ·  −B if net ≤ −10%  ·  −A if net ≤ −25% and −A stocks present',
            '',
            'Weinstein stage analysis + Morales/Kacher Pocket Pivot methodology.',
          ].join('\n')}>
            Index-level buy/sell grade · Weinstein stage + Pocket Pivot signals
          </span>
          {loading && <span className="font-sans text-[10px] text-ink-tertiary">Loading…</span>}
        </div>
        <span className="font-mono text-xs text-ink-tertiary">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t border-paper-rule px-4 py-3">
          {error ? (
            <p className="font-sans text-xs text-signal-neg">{error}</p>
          ) : loading ? (
            <div className="flex gap-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-24 w-40 bg-paper-rule/40 rounded animate-pulse" />
              ))}
            </div>
          ) : !data || data.length === 0 ? (
            <p className="font-sans text-xs text-ink-tertiary">No CTS data available yet.</p>
          ) : (
            <div className="flex flex-wrap gap-3">
              {data.map(row => <IndexCard key={row.index_name} row={row} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
