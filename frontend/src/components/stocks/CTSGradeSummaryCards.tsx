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

const INDEX_TABS = [
  { label: 'N50',  name: 'Nifty 50' },
  { label: 'N100', name: 'Nifty 100' },
  { label: 'N500', name: 'Nifty 500' },
  { label: 'All',  name: 'All Tradeable' },
]

const GRADE_CONFIG = [
  {
    key: 'plus_a'  as const,
    grade: '+A',
    label: 'Buy · Act Now',
    badge: 'bg-teal text-white',
    count: 'text-teal',
    ring: 'ring-1 ring-teal/30',
    bar: 'bg-teal',
  },
  {
    key: 'plus_b'  as const,
    grade: '+B',
    label: 'Buy · Watch',
    badge: 'bg-teal/10 text-teal border border-teal/40',
    count: 'text-teal',
    ring: '',
    bar: 'bg-teal/40',
  },
  {
    key: 'neutral' as const,
    grade: '—',
    label: 'Neutral',
    badge: 'bg-paper-rule/40 text-ink-tertiary',
    count: 'text-ink-secondary',
    ring: '',
    bar: 'bg-paper-rule',
  },
  {
    key: 'minus_b' as const,
    grade: '−B',
    label: 'Sell · Watch',
    badge: 'bg-amber-500/10 text-amber-500 border border-amber-500/40',
    count: 'text-amber-500',
    ring: '',
    bar: 'bg-amber-400/60',
  },
  {
    key: 'minus_a' as const,
    grade: '−A',
    label: 'Sell · Act Now',
    badge: 'bg-signal-neg text-white',
    count: 'text-signal-neg',
    ring: 'ring-1 ring-signal-neg/30',
    bar: 'bg-signal-neg',
  },
]

const GLOSSARY = [
  {
    term: 'PPC · Pocket Pivot Candle',
    def:  'An up-day where volume exceeds the highest down-day volume across the prior 10 trading sessions. Signals institutional accumulation entering a position. Source: Morales & Kacher methodology.',
  },
  {
    term: 'NPC · Negative Pivot Candle',
    def:  'The bearish mirror of PPC. A down-day where volume exceeds the highest up-day volume in the prior 10 sessions. Signals institutional distribution — large players exiting.',
  },
  {
    term: 'Contraction',
    def:  'A day with narrowing price range (shrinking ATR slope), close within ~3% of the session high, on below-average volume. Indicates a quiet pause in an uptrend — tight base coiling before the next move. Often precedes a PPC.',
  },
  {
    term: 'Stage 1 · Basing',
    def:  'Stock moving sideways beneath a flat or declining 30-week MA. Accumulation may be happening but no confirmed uptrend. Wait for Stage 2 before buying.',
  },
  {
    term: 'Stage 2 · Advancing',
    def:  'Stock trading above a rising 30-week MA — the primary buy zone per Weinstein stage analysis. This is the only stage where new positions are initiated. PPC in Stage 2 = highest-conviction entry.',
  },
  {
    term: 'Stage 3 · Topping',
    def:  'MA flattening or turning down. Institutional distribution begins. Stocks here are at risk; existing positions should be tightened or exited. An NPC in Stage 3 escalates to −A.',
  },
  {
    term: 'Stage 4 · Declining',
    def:  'Stock below a declining 30-week MA. Avoid entirely. If held, this is an immediate exit signal (−A). No buying in Stage 4 regardless of short-term bounces.',
  },
  {
    term: 'Timing Grade +A / +B / — / −B / −A',
    def:  '+ = buy timing  ·  − = sell timing  ·  A = act now (trigger confirmed)  ·  B = watch (setup forming but no trigger yet)\n+A: Stage 2 + confirmed Pocket Pivot — highest conviction buy\n+B: Stage 2, no PPC yet — right stage, wait for volume trigger\n —: Stage 1 or Contraction — neutral, no action\n−B: Stage 3 topping — begin reducing / tighten stops\n−A: Stage 4 decline or Stage 3 + Negative Pivot — exit now',
  },
]

export function CTSGradeSummaryCards() {
  const [data, setData]         = useState<IndexTimingRow[] | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [selected, setSelected] = useState('All Tradeable')
  const [showDefs, setShowDefs] = useState(false)

  useEffect(() => {
    fetch('/api/cts/index-timing')
      .then(r => r.json() as Promise<ApiResponse>)
      .then(d => { setData(d.rows); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  const row = data?.find(r => r.index_name === selected) ?? null

  const buyCount  = row ? row.plus_a + row.plus_b : 0
  const sellCount = row ? row.minus_a + row.minus_b : 0
  const buyPct    = row && row.total > 0 ? Math.round((buyCount        / row.total) * 100) : 0
  const neutPct   = row && row.total > 0 ? Math.round((row.neutral     / row.total) * 100) : 0
  const sellPct   = row && row.total > 0 ? Math.round((sellCount       / row.total) * 100) : 0

  return (
    <div className="border border-paper-rule rounded-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-paper-rule">
        <div className="flex items-center gap-3">
          <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
            Timing Grade Distribution
          </span>
          {row != null && !loading && (
            <span className="font-sans text-[10px] text-ink-tertiary">
              {row.plus_a > 0 && (
                <span className="text-teal font-medium">{row.plus_a} act-now buys · </span>
              )}
              {buyCount} stocks in buy position
            </span>
          )}
          {loading && <span className="font-sans text-[10px] text-ink-tertiary">Loading…</span>}
        </div>

        {/* Index tabs */}
        <div className="flex items-center gap-0.5">
          {INDEX_TABS.map(tab => (
            <button
              key={tab.name}
              onClick={() => setSelected(tab.name)}
              className={`px-2 py-0.5 font-mono text-[10px] rounded transition-colors ${
                selected === tab.name
                  ? 'bg-teal/10 text-teal font-semibold'
                  : 'text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 py-3 space-y-3">
        {error ? (
          <p className="font-sans text-xs text-signal-neg">{error}</p>
        ) : loading ? (
          <div className="flex gap-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-24 flex-1 bg-paper-rule/40 rounded animate-pulse" />
            ))}
          </div>
        ) : !row ? (
          <p className="font-sans text-xs text-ink-tertiary">No CTS data available yet.</p>
        ) : (
          <>
            {/* Grade cards */}
            <div className="grid grid-cols-5 gap-2">
              {GRADE_CONFIG.map(cfg => {
                const count = row[cfg.key]
                const pct   = row.total > 0 ? Math.round((count / row.total) * 100) : 0
                return (
                  <div
                    key={cfg.key}
                    className={`flex flex-col items-center gap-1.5 p-3 border border-paper-rule rounded-sm bg-paper ${cfg.ring}`}
                  >
                    <span className={`inline-flex items-center justify-center w-10 h-6 rounded font-mono text-xs font-bold ${cfg.badge}`}>
                      {cfg.grade}
                    </span>
                    <span className={`font-mono text-3xl font-bold tabular-nums leading-none ${cfg.count}`}>
                      {count}
                    </span>
                    <span className="font-sans text-[10px] text-ink-tertiary text-center leading-tight">
                      {cfg.label}
                    </span>
                    <span className="font-mono text-[10px] text-ink-tertiary tabular-nums">
                      {pct}%
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Distribution bar + legend */}
            <div className="space-y-1.5">
              <div className="flex h-2 rounded-full overflow-hidden gap-px">
                {GRADE_CONFIG.map(cfg => {
                  const count = row[cfg.key]
                  const pct   = row.total > 0 ? (count / row.total) * 100 : 0
                  return pct > 0 ? (
                    <div
                      key={cfg.key}
                      className={cfg.bar}
                      style={{ width: `${pct}%` }}
                      title={`${cfg.grade}: ${count} stocks (${Math.round(pct)}%)`}
                    />
                  ) : null
                })}
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-teal" />
                    <span className="font-sans text-[10px] text-ink-secondary">
                      Buy {buyPct}%
                      <span className="text-ink-tertiary"> ({buyCount} stocks)</span>
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-paper-rule border border-ink-tertiary/20" />
                    <span className="font-sans text-[10px] text-ink-secondary">
                      Neutral {neutPct}%
                      <span className="text-ink-tertiary"> ({row.neutral})</span>
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
                    <span className="font-sans text-[10px] text-ink-secondary">
                      Sell {sellPct}%
                      <span className="text-ink-tertiary"> ({sellCount} stocks)</span>
                    </span>
                  </span>
                </div>
                <span className="font-sans text-[10px] text-ink-tertiary">
                  {row.total} stocks in {selected}
                </span>
              </div>
            </div>
            {/* Glossary toggle */}
            <div className="border-t border-paper-rule/60 pt-2">
              <button
                type="button"
                onClick={() => setShowDefs(d => !d)}
                className="flex items-center gap-1.5 font-sans text-[10px] text-ink-tertiary hover:text-ink-secondary transition-colors"
              >
                <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-ink-tertiary/40 text-[8px] font-bold">ⓘ</span>
                {showDefs ? 'Hide signal definitions' : 'How are these signals calculated?'}
              </button>

              {showDefs && (
                <div className="mt-3 grid grid-cols-1 gap-3">
                  {GLOSSARY.map(item => (
                    <div key={item.term} className="flex gap-3">
                      <div className="shrink-0 w-[180px]">
                        <span className="font-mono text-[10px] font-semibold text-ink-secondary">{item.term}</span>
                      </div>
                      <div className="flex-1">
                        {item.def.split('\n').map((line, i) => (
                          <p key={i} className={`font-sans text-[10px] text-ink-tertiary leading-relaxed ${i > 0 ? 'mt-0.5' : ''}`}>
                            {line}
                          </p>
                        ))}
                      </div>
                    </div>
                  ))}
                  <p className="font-sans text-[9px] text-ink-tertiary/60 pt-1 border-t border-paper-rule/40">
                    Stage analysis: Mark Weinstein (1988). Pocket Pivot: Gil Morales &amp; Chris Kacher. Volume thresholds computed daily against trailing 10-session window.
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
