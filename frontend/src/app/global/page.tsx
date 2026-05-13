export const dynamic = 'force-dynamic'

import { getGlobalRegime, getCountryRankings } from '@/lib/queries/global'
import { CountryRankingsTable } from '@/components/global/CountryRankingsTable'

const REGIME_STYLE: Record<string, string> = {
  Strong:  'bg-signal-pos/10 text-signal-pos border-signal-pos/20',
  Healthy: 'bg-teal/10 text-teal border-teal/20',
  Caution: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
  Weak:    'bg-signal-neg/10 text-signal-neg border-signal-neg/20',
}

export default async function GlobalPulsePage() {
  const [regime, countries] = await Promise.all([
    getGlobalRegime().catch(() => null),
    getCountryRankings().catch(() => []),
  ])

  const regimeState = regime?.regime_state ?? null
  const dmCount = countries.filter(c => c.is_developed_market).length
  const emCount = countries.filter(c => !c.is_developed_market).length
  const q1Count = countries.filter(c => (c.q_3m_vt ?? 5) <= 2).length

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Global Pulse
          </h1>
          <div className="flex items-center gap-4">
            <span className="font-sans text-xs text-ink-secondary">{countries.length} countries</span>
            <span className="font-sans text-xs text-ink-secondary">{dmCount} DM · {emCount} EM</span>
            <span className="font-sans text-xs text-ink-secondary">{q1Count} in Q1/Q2 vs VT (3M)</span>
          </div>
        </div>
        {regime?.date && (
          <span className="font-sans text-[11px] text-ink-tertiary">as of {regime.date}</span>
        )}
      </div>

      {/* Regime banner */}
      {regime && (
        <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-6 flex-wrap">
          {regimeState && (
            <div className={`flex items-center gap-2 px-3 py-1 rounded border text-sm font-semibold ${REGIME_STYLE[regimeState] ?? 'bg-paper-bg text-ink-secondary border-paper-rule'}`}>
              Global Regime: {regimeState}
              {regime.dislocation_flag && (
                <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-signal-neg/20 text-signal-neg">
                  DISLOCATION
                </span>
              )}
            </div>
          )}
          <div className="flex items-center gap-4 font-mono text-[11px] text-ink-secondary">
            {regime.pct_countries_above_200dma != null && (
              <span>
                {Math.round(parseFloat(regime.pct_countries_above_200dma) * 100)}% above 200DMA
              </span>
            )}
            {regime.pct_countries_above_50dma != null && (
              <span>
                {Math.round(parseFloat(regime.pct_countries_above_50dma) * 100)}% above 50DMA
              </span>
            )}
            {regime.benchmark_above_ema_200 != null && (
              <span className={regime.benchmark_above_ema_200 ? 'text-signal-pos' : 'text-signal-neg'}>
                VT {regime.benchmark_above_ema_200 ? '▲' : '▼'} 200MA
              </span>
            )}
          </div>
        </div>
      )}

      {/* Rankings table */}
      <div className="px-6 pt-4 pb-8">
        {countries.length === 0 ? (
          <div className="py-16 text-center">
            <p className="font-sans text-sm text-ink-secondary">
              No data yet. Run the Global Atlas backfill pipeline first.
            </p>
            <p className="font-mono text-xs text-ink-tertiary mt-2">
              python3 scripts/global_backfill.py
            </p>
          </div>
        ) : (
          <>
            <div className="mb-3 font-sans text-[11px] text-ink-tertiary">
              RS quintiles: <strong className="text-signal-pos">Q1 = top 20%</strong> (strongest),{' '}
              <strong className="text-signal-neg">Q5 = bottom 20%</strong> (weakest).
              Score = bullish consensus cells out of 20 (4 benchmarks × 5 timeframes).
            </div>
            <CountryRankingsTable countries={countries} />
          </>
        )}
      </div>
    </div>
  )
}
