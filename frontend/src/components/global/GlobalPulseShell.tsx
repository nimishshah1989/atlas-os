'use client'
import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import dynamic from 'next/dynamic'
import type { GlobalRegimeRow, GlobalRegimeHistoryRow, CountryRow } from '@/lib/queries/global'
import { GlobalRegimeHeadline } from '@/components/global/GlobalRegimeHeadline'
import { GlobalTrendSection } from '@/components/global/GlobalTrendSection'
import { GlobalBreadthSection } from '@/components/global/GlobalBreadthSection'
import { GlobalMomentumSection } from '@/components/global/GlobalMomentumSection'
import { GlobalParticipationSection } from '@/components/global/GlobalParticipationSection'
import { CountryRankingsTable } from '@/components/global/CountryRankingsTable'

const GlobalRegimeOverlayChart = dynamic(
  () => import('@/components/global/GlobalRegimeOverlayChart').then(m => m.GlobalRegimeOverlayChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 flex items-center justify-center text-ink-tertiary font-sans text-sm">
        Loading chart...
      </div>
    ),
  },
)

const GlobalCountryBubbleChart = dynamic(
  () => import('@/components/global/GlobalCountryBubbleChart').then(m => m.GlobalCountryBubbleChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 flex items-center justify-center text-ink-tertiary font-sans text-sm">
        Loading chart...
      </div>
    ),
  },
)

type Tab = 'Regime' | 'Countries'
const TABS: Tab[] = ['Regime', 'Countries']

type Props = {
  regime: GlobalRegimeRow | null
  history: GlobalRegimeHistoryRow[]
  countries: CountryRow[]
}

export function GlobalPulseShell({ regime, history, countries }: Props) {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const rawTab       = searchParams.get('tab')
  const initialTab: Tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : 'Regime'
  const [activeTab, setActiveTab] = useState<Tab>(initialTab)

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', activeTab)
    router.replace(`?${params.toString()}`, { scroll: false })
  }, [activeTab, router, searchParams])

  const dmCount = countries.filter(c => c.is_developed_market).length
  const emCount = countries.filter(c => !c.is_developed_market).length

  return (
    <div>
      {/* Header strip */}
      <div className="px-6 py-3 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-5">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Global Pulse
          </h1>
          <div className="flex items-center gap-4">
            <span className="font-sans text-xs text-ink-secondary">{countries.length} countries</span>
            <span className="font-sans text-xs text-ink-secondary">{dmCount} DM · {emCount} EM</span>
          </div>
        </div>
        {regime?.date && (
          <span className="font-sans text-[11px] text-ink-tertiary">as of {regime.date}</span>
        )}
      </div>

      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule flex items-center gap-0">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={[
              'px-4 py-3 font-sans text-xs font-medium transition-colors border-b-2 -mb-px',
              activeTab === tab
                ? 'text-teal border-teal'
                : 'text-ink-secondary border-transparent hover:text-teal',
            ].join(' ')}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Regime tab — mirrors India home: Headline → Chart → Trend → Breadth → Momentum → Participation */}
      {activeTab === 'Regime' && (
        <div>
          {regime ? (
            <>
              <GlobalRegimeHeadline regime={regime} countries={countries} />

              <div className="px-6 py-6 border-b border-paper-rule">
                <GlobalRegimeOverlayChart history={history} />
              </div>

              <GlobalTrendSection current={regime} history={history} />
              <GlobalBreadthSection current={regime} history={history} countries={countries} />
              <GlobalMomentumSection current={regime} countries={countries} />
              <GlobalParticipationSection current={regime} countries={countries} />
            </>
          ) : (
            <div className="px-6 py-16 text-center">
              <p className="font-sans text-sm text-ink-secondary">
                No global regime data. Run the Global Atlas pipeline first.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Countries tab — mirrors India /sectors: bubble chart → rankings table */}
      {activeTab === 'Countries' && (
        <div>
          <div className="px-6 pt-4">
            <div className="border border-paper-rule rounded-sm p-4">
              <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
                Country Risk/Return Map — Volatility vs 3M Return
              </div>
              <p className="font-sans text-[11px] text-ink-tertiary mb-3">
                X = annualised volatility (63D), Y = 3-month return. Color = RS state vs VT.
              </p>
              <GlobalCountryBubbleChart countries={countries} />
            </div>
          </div>

          <div className="px-6 py-4">
            {countries.length > 0 ? (
              <>
                <div className="mb-3 font-sans text-[11px] text-ink-tertiary">
                  RS quintiles: <strong className="text-signal-pos">Q1 = top 20%</strong> (strongest),{' '}
                  <strong className="text-signal-neg">Q5 = bottom 20%</strong> (weakest).
                  Bull score = consensus bullish cells out of 20 (4 benchmarks × 5 timeframes).
                </div>
                <CountryRankingsTable countries={countries} />
              </>
            ) : (
              <div className="py-16 text-center">
                <p className="font-sans text-sm text-ink-secondary">
                  No country data. Run the Global Atlas pipeline first.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
