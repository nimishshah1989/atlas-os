'use client'
import { Zap } from 'lucide-react'
import { SectionHeader } from '@/components/regime/SectionHeader'
import { CategorySummary } from '@/components/regime/CategorySummary'
import type { GlobalRegimeRow, CountryRow } from '@/lib/queries/global'

type Props = {
  current: GlobalRegimeRow
  countries: CountryRow[]
}

const POS = '#22c55e'
const NEG = '#ef4444'
const WARN = '#f59e0b'
const TEAL = '#14b8a6'

function ReturnBadge({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const v = parseFloat(value)
  const pct = (v * 100).toFixed(1)
  const color = v > 0 ? POS : v < 0 ? NEG : '#94a3b8'
  return (
    <span className="font-mono text-xs font-medium tabular-nums" style={{ color }}>
      {v > 0 ? '+' : ''}{pct}%
    </span>
  )
}

function ConsensusBar({ bullish, bearish }: { bullish: number | null; bearish: number | null }) {
  const b = bullish ?? 0
  const total = 20 // consensus out of 20 cells
  const pct = Math.round((b / total) * 100)
  const color = pct >= 60 ? POS : pct >= 40 ? TEAL : pct >= 25 ? WARN : NEG
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-paper-rule rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono text-[10px] tabular-nums text-ink-tertiary w-7 text-right">
        {pct}%
      </span>
    </div>
  )
}

export function GlobalMomentumSection({ current, countries }: Props) {
  const total = countries.length || 1

  const dmCountries = countries.filter((c) => c.is_developed_market)
  const emCountries = countries.filter((c) => !c.is_developed_market)

  // Signal 1: majority of countries have bullish RS consensus > 10/20
  const bullishConsensusCount = countries.filter((c) => (c.rs_consensus_bullish ?? 0) > 10).length
  const sig1 = bullishConsensusCount / total > 0.5

  // Signal 2: DM avg Q3m_vt < 3 (upper quintiles = outperforming)
  const dmAvgQ = dmCountries.length > 0
    ? dmCountries.reduce((s, c) => s + (c.q_3m_vt ?? 3), 0) / dmCountries.length
    : 3
  const sig2 = dmAvgQ < 3

  // Signal 3: EM avg Q3m_vt < 3
  const emAvgQ = emCountries.length > 0
    ? emCountries.reduce((s, c) => s + (c.q_3m_vt ?? 3), 0) / emCountries.length
    : 3
  const sig3 = emAvgQ < 3

  // Signal 4: majority of countries with positive 3m return
  const posRet3mCount = countries.filter((c) => c.ret_3m != null && parseFloat(c.ret_3m) > 0).length
  const ret3mDenom = countries.filter((c) => c.ret_3m != null).length || 1
  const sig4 = posRet3mCount / ret3mDenom > 0.5

  const bullishSignals = [sig1, sig2, sig3, sig4]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const momLabel =
    bullishCount >= 3 ? 'MOMENTUM IS POSITIVE' :
    bullishCount === 2 ? 'MOMENTUM IS FADING' :
    'MOMENTUM IS NEGATIVE'

  const dmAvgConsensus = dmCountries.length > 0
    ? dmCountries.reduce((s, c) => s + (c.rs_consensus_bullish ?? 0), 0) / dmCountries.length
    : 0
  const emAvgConsensus = emCountries.length > 0
    ? emCountries.reduce((s, c) => s + (c.rs_consensus_bullish ?? 0), 0) / emCountries.length
    : 0

  const momSummary =
    `${bullishConsensusCount} of ${total} country ETFs have a bullish RS consensus (>10/20 cells). ` +
    `DM avg RS score: ${dmAvgConsensus.toFixed(1)}/20 (Q avg ${dmAvgQ.toFixed(1)}); ` +
    `EM avg RS score: ${emAvgConsensus.toFixed(1)}/20 (Q avg ${emAvgQ.toFixed(1)}). ` +
    `${posRet3mCount} countries with positive 3-month return. ` +
    (bullishCount >= 3
      ? 'Global momentum is broadly positive.'
      : bullishCount === 2
        ? 'Momentum is mixed — DM/EM divergence or fading breadth.'
        : 'Momentum has turned negative — defensive posture required.')

  // Top 5 and bottom 5 countries by pctile_3m_vt
  const ranked = [...countries].sort((a, b) => {
    const pa = a.pctile_3m_vt != null ? parseFloat(a.pctile_3m_vt) : -999
    const pb = b.pctile_3m_vt != null ? parseFloat(b.pctile_3m_vt) : -999
    return pb - pa
  })
  const top5    = ranked.slice(0, 5)
  const bottom5 = ranked.slice(-5).reverse()

  return (
    <section>
      <SectionHeader
        icon={<Zap className="w-4 h-4" strokeWidth={2} />}
        title="Momentum"
        description="Global momentum measures whether country ETFs are accelerating or decelerating relative to the VT world benchmark. RS consensus tracks how many of 20 cross-benchmark/timeframe signals are bullish for each country. Q1/Q2 classification means the country is outperforming VT on a 3-month basis. DM vs EM breakdowns reveal whether the strength is concentrated in developed or emerging markets."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={momLabel}
        summary={momSummary}
      />

      <div className="px-6 pb-6 space-y-4">
        {/* Summary stat tiles */}
        <div className="grid grid-cols-2 gap-4">
          <div className="border border-paper-rule rounded-sm p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary">
                Developed Markets
              </span>
              <span className={`font-sans text-[10px] font-medium ${sig2 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {sig2 ? 'OUTPERFORMING' : 'LAGGING'}
              </span>
            </div>
            <p className="font-sans text-xs text-ink-tertiary mb-3">
              {dmCountries.length} DM country ETFs. Avg RS quintile vs VT (3M): {dmAvgQ.toFixed(1)}.
            </p>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-ink-tertiary font-sans">Avg RS consensus</span>
                <span className="font-mono text-ink-primary">{dmAvgConsensus.toFixed(1)}/20</span>
              </div>
              <ConsensusBar bullish={dmAvgConsensus} bearish={null} />
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-ink-tertiary font-sans">Avg Q vs VT (3M)</span>
                <span
                  className="font-mono font-medium"
                  style={{ color: dmAvgQ < 2 ? POS : dmAvgQ < 3 ? TEAL : dmAvgQ < 4 ? WARN : NEG }}
                >
                  Q{dmAvgQ.toFixed(1)}
                </span>
              </div>
            </div>
          </div>

          <div className="border border-paper-rule rounded-sm p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary">
                Emerging Markets
              </span>
              <span className={`font-sans text-[10px] font-medium ${sig3 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {sig3 ? 'OUTPERFORMING' : 'LAGGING'}
              </span>
            </div>
            <p className="font-sans text-xs text-ink-tertiary mb-3">
              {emCountries.length} EM country ETFs. Avg RS quintile vs VT (3M): {emAvgQ.toFixed(1)}.
            </p>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-ink-tertiary font-sans">Avg RS consensus</span>
                <span className="font-mono text-ink-primary">{emAvgConsensus.toFixed(1)}/20</span>
              </div>
              <ConsensusBar bullish={emAvgConsensus} bearish={null} />
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-ink-tertiary font-sans">Avg Q vs VT (3M)</span>
                <span
                  className="font-mono font-medium"
                  style={{ color: emAvgQ < 2 ? POS : emAvgQ < 3 ? TEAL : emAvgQ < 4 ? WARN : NEG }}
                >
                  Q{emAvgQ.toFixed(1)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Top / Bottom country tables */}
        <div className="grid grid-cols-2 gap-4">
          {/* Top 5 */}
          <div className="border border-paper-rule rounded-sm p-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary block mb-3">
              Top Countries — 3M vs VT
            </span>
            <div className="space-y-2">
              {top5.map((c) => (
                <div key={c.ticker} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-[10px] text-ink-tertiary w-8 shrink-0">{c.ticker}</span>
                    <span className="font-sans text-xs text-ink-primary truncate">{c.country}</span>
                    {c.is_developed_market ? (
                      <span className="font-sans text-[9px] text-ink-tertiary border border-paper-rule rounded px-1 shrink-0">DM</span>
                    ) : (
                      <span className="font-sans text-[9px] text-teal-600 border border-teal-200 rounded px-1 shrink-0">EM</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    <ReturnBadge value={c.ret_3m} />
                    {c.q_3m_vt != null && (
                      <span className="font-mono text-[10px] text-ink-tertiary">Q{c.q_3m_vt}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Bottom 5 */}
          <div className="border border-paper-rule rounded-sm p-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary block mb-3">
              Bottom Countries — 3M vs VT
            </span>
            <div className="space-y-2">
              {bottom5.map((c) => (
                <div key={c.ticker} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-[10px] text-ink-tertiary w-8 shrink-0">{c.ticker}</span>
                    <span className="font-sans text-xs text-ink-primary truncate">{c.country}</span>
                    {c.is_developed_market ? (
                      <span className="font-sans text-[9px] text-ink-tertiary border border-paper-rule rounded px-1 shrink-0">DM</span>
                    ) : (
                      <span className="font-sans text-[9px] text-teal-600 border border-teal-200 rounded px-1 shrink-0">EM</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    <ReturnBadge value={c.ret_3m} />
                    {c.q_3m_vt != null && (
                      <span className="font-mono text-[10px] text-ink-tertiary">Q{c.q_3m_vt}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
