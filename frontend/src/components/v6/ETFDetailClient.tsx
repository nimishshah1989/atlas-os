'use client'

// frontend/src/components/v6/ETFDetailClient.tsx
//
// Client component: hero + 3-tab layout for the v6 ETF detail page.
// Tabs: Overview (RankDecompositionCards + RSWaterfall) / Holdings / Audit
//
// Pattern mirrors StockDetailClient.tsx (C.16). All data fetched server-side
// and passed as props; this component owns only UI state (active tab).

import { useState, Suspense, lazy } from 'react'
import { ETFHero } from './ETFHero'
import { RankDecompositionCards } from './RankDecompositionCards'
import { MultiBenchmarkRSWaterfall } from './MultiBenchmarkRSWaterfall'
import { toNumber } from '@/lib/v6/decimal'
import type { ETFHeroData } from './ETFHero'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { AuditTrail } from '@/lib/queries/v6/audit_trail'
import type { RankComponent } from './RankDecompositionCards'

const AuditTrailTab = lazy(() => import('./AuditTrailTab'))

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ETFHolding = {
  ticker: string
  weight_pct: string | null
  sector: string | null
}

export interface ETFDetailClientProps {
  hero: ETFHeroData
  holdingState: HoldingState | null
  auditTrail: AuditTrail | null
  rankData: {
    composite_score: string
    components: RankComponent[]
    rank_in_category: number
    category_size: number
  } | null
  waterfallData: {
    stock_return: string
    cohort_return: string
    nifty50_return: string
    nifty500_return: string
    gold_return: string | null
    tenure: '1m' | '3m' | '6m' | '12m'
  } | null
  holdings: ETFHolding[]
}

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

type Tab = 'overview' | 'holdings' | 'audit'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'holdings', label: 'Holdings' },
  { id: 'audit', label: 'Audit' },
]

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

function TabNav({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <nav
      role="tablist"
      aria-label="ETF detail tabs"
      className="flex gap-0 border-b border-paper-rule px-6"
    >
      {TABS.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          aria-controls={`tabpanel-${t.id}`}
          id={`tab-${t.id}`}
          onClick={() => onChange(t.id)}
          className={[
            'px-4 py-3 font-sans text-sm font-medium border-b-2 transition-colors',
            active === t.id
              ? 'border-teal text-teal'
              : 'border-transparent text-ink-secondary hover:text-ink-primary',
          ].join(' ')}
        >
          {t.label}
        </button>
      ))}
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------

function OverviewTab({
  rankData,
  waterfallData,
}: {
  rankData: ETFDetailClientProps['rankData']
  waterfallData: ETFDetailClientProps['waterfallData']
}) {
  return (
    <div
      id="tabpanel-overview"
      role="tabpanel"
      aria-labelledby="tab-overview"
      className="px-6 py-6 flex flex-col gap-8"
    >
      {rankData ? (
        <RankDecompositionCards
          composite_score={rankData.composite_score}
          components={rankData.components}
          rank_in_category={rankData.rank_in_category}
          category_size={rankData.category_size}
        />
      ) : (
        <div className="font-sans text-sm text-ink-tertiary">
          Rank breakdown not available for this ETF.
        </div>
      )}

      {waterfallData ? (
        <div>
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            Relative Strength Waterfall ({waterfallData.tenure})
          </h2>
          <MultiBenchmarkRSWaterfall data={waterfallData} />
        </div>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Holdings tab
// ---------------------------------------------------------------------------

function HoldingsTab({ holdings }: { holdings: ETFHolding[] }) {
  if (holdings.length === 0) {
    return (
      <div
        id="tabpanel-holdings"
        role="tabpanel"
        aria-labelledby="tab-holdings"
        className="px-6 py-8 font-sans text-sm text-ink-tertiary"
      >
        Top holdings data not available for this ETF.
      </div>
    )
  }

  const top20 = holdings.slice(0, 20)

  return (
    <div
      id="tabpanel-holdings"
      role="tabpanel"
      aria-labelledby="tab-holdings"
      className="px-6 py-6 flex flex-col gap-4"
    >
      <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
        Top {top20.length} Holdings
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm font-sans border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="text-left py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                Ticker
              </th>
              <th className="text-left py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                Sector
              </th>
              <th className="text-right py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                Weight
              </th>
            </tr>
          </thead>
          <tbody>
            {top20.map((h, i) => (
              <tr
                key={`${h.ticker}-${i}`}
                className="border-b border-paper-rule hover:bg-paper-deep transition-colors"
              >
                <td className="py-2 px-3 text-ink-primary font-medium font-mono">
                  {h.ticker}
                </td>
                <td className="py-2 px-3 text-ink-secondary">
                  {h.sector ?? '—'}
                </td>
                <td className="py-2 px-3 text-right font-mono tabular-nums text-ink-secondary">
                  {formatHoldingWeight(h.weight_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function formatHoldingWeight(s: string | null): string {
  const n = toNumber(s)
  if (n === null) return '—'
  // weight_pct from JSONB may be fractional (0.05) or pct form (5.0)
  const pct = n > 1 ? n : n * 100
  return `${pct.toFixed(2)}%`
}

// ---------------------------------------------------------------------------
// Audit tab
// ---------------------------------------------------------------------------

function AuditTab({ auditTrail }: { auditTrail: AuditTrail | null }) {
  return (
    <div
      id="tabpanel-audit"
      role="tabpanel"
      aria-labelledby="tab-audit"
    >
      <Suspense
        fallback={
          <div className="px-6 py-8 text-center font-sans text-sm text-ink-tertiary">
            Loading audit trail…
          </div>
        }
      >
        <AuditTrailTab auditTrail={auditTrail} />
      </Suspense>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ETFDetailClient({
  hero,
  holdingState,
  auditTrail,
  rankData,
  waterfallData,
  holdings,
}: ETFDetailClientProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <ETFHero data={hero} holdingState={holdingState} />

      {/* Tab navigation */}
      <TabNav active={activeTab} onChange={setActiveTab} />

      {/* Tab panels */}
      {activeTab === 'overview' && (
        <OverviewTab rankData={rankData} waterfallData={waterfallData} />
      )}
      {activeTab === 'holdings' && (
        <HoldingsTab holdings={holdings} />
      )}
      {activeTab === 'audit' && (
        <AuditTab auditTrail={auditTrail} />
      )}
    </div>
  )
}

export default ETFDetailClient
