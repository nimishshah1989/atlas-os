// frontend/src/components/v6/StockDetailClient.tsx
// Client component: hero + 3-tab layout for the v6 stock detail page.
// Tabs: Overview / Technicals / Audit
// AuditTrailTab is lazy-imported (E.1 fallback placeholder included).

'use client'

import { useState, Suspense, lazy } from 'react'
import { StockHero } from './StockHero'
import { MultiBenchmarkRSWaterfall } from './MultiBenchmarkRSWaterfall'
import { RankDecompositionCards } from './RankDecompositionCards'
import { MultiTenureReturnsTable } from './MultiTenureReturnsTable'
import { GradeChip } from './GradeChip'
import { toNumber, formatPct } from '@/lib/v6/decimal'
import type { ScreenStock } from '@/lib/api/v1'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { StockTechnicals } from '@/lib/queries/v6/stock_technicals'
import type { MultiTenureReturns } from '@/lib/queries/v6/multi_tenure_returns'
import type { FundHolding } from '@/lib/queries/v6/funds_holding_stock'
import type { AuditTrail } from '@/lib/queries/v6/audit_trail'
import type { CrossRuleDepthData } from './StockHero'
import type { Grade } from './GradeChip'

const AuditTrailTab = lazy(() => import('./AuditTrailTab'))

type Tab = 'overview' | 'technicals' | 'audit'

export interface StockDetailClientProps {
  stock: ScreenStock
  holdingState: HoldingState | null
  technicals: StockTechnicals | null
  returns: MultiTenureReturns | null
  fundsHolding: FundHolding[]
  auditTrail: AuditTrail | null
  crossRuleDepth: CrossRuleDepthData | null
  deploymentMultiplier: number
  sectorGapPp: number
  actionVerb: string
  bullets: string[]
  /** Waterfall data for Overview tab. null when no benchmark data available. */
  waterfallData: {
    stock_return: string
    cohort_return: string
    nifty50_return: string
    nifty500_return: string
    gold_return: string | null
    tenure: '1m' | '3m' | '6m' | '12m'
  } | null
  /** RankDecomposition props for Overview tab. null when not available. */
  rankData: {
    composite_score: string
    components: Array<{
      name: string
      raw_score: string
      percentile_in_category: string
      weight_pct: string
      delta_vs_cohort: string
    }>
    rank_in_category: number
    category_size: number
  } | null
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'technicals', label: 'Technicals' },
  { id: 'audit', label: 'Audit' },
]

function TabNav({
  active,
  onChange,
}: {
  active: Tab
  onChange: (t: Tab) => void
}) {
  return (
    <nav
      role="tablist"
      aria-label="Stock detail tabs"
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

function OverviewTab({
  stock,
  waterfallData,
  rankData,
  fundsHolding,
  returns,
}: {
  stock: ScreenStock
  waterfallData: StockDetailClientProps['waterfallData']
  rankData: StockDetailClientProps['rankData']
  fundsHolding: FundHolding[]
  returns: MultiTenureReturns | null
}) {
  return (
    <div
      id="tabpanel-overview"
      role="tabpanel"
      aria-labelledby="tab-overview"
      className="px-6 py-6 flex flex-col gap-8"
    >
      {/* Rank decomposition */}
      {rankData ? (
        <RankDecompositionCards
          composite_score={rankData.composite_score}
          components={rankData.components}
          rank_in_category={rankData.rank_in_category}
          category_size={rankData.category_size}
        />
      ) : (
        <div className="font-sans text-sm text-ink-tertiary">
          Rank breakdown not available for this stock.
        </div>
      )}

      {/* Waterfall */}
      {waterfallData ? (
        <div>
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            Relative Strength Waterfall ({waterfallData.tenure})
          </h2>
          <MultiBenchmarkRSWaterfall data={waterfallData} />
        </div>
      ) : null}

      {/* Multi-tenure returns */}
      {returns ? (
        <div>
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            Returns
          </h2>
          <MultiTenureReturnsTable rows={[returns]} highlightIid={stock.iid} />
        </div>
      ) : (
        <ReturnsFromConviction stock={stock} />
      )}

      {/* Funds holding */}
      <FundsHoldingSection fundsHolding={fundsHolding} />
    </div>
  )
}

function ReturnsFromConviction({ stock }: { stock: ScreenStock }) {
  const tiles = [
    { label: '1M', value: stock.ret_1m },
    { label: '3M', value: stock.ret_3m },
    { label: '6M', value: stock.ret_6m },
    { label: '12M', value: stock.ret_12m },
  ]
  return (
    <div>
      <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
        Returns
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {tiles.map(({ label, value }) => {
          if (value == null) {
            return (
              <div key={label} className="border border-paper-rule rounded-[2px] p-3 bg-paper">
                <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
                <div className="font-mono text-xl font-semibold tabular-nums text-ink-tertiary mt-1">—</div>
              </div>
            )
          }
          const pct = value * 100
          const sign = pct >= 0 ? '+' : ''
          const cls = pct >= 0 ? 'text-signal-pos' : 'text-signal-neg'
          return (
            <div key={label} className="border border-paper-rule rounded-[2px] p-3 bg-paper">
              <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
              <div className={`font-mono text-xl font-semibold tabular-nums ${cls} mt-1`}>
                {sign}{pct.toFixed(1)}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FundsHoldingSection({ fundsHolding }: { fundsHolding: FundHolding[] }) {
  if (fundsHolding.length === 0) {
    return (
      <div>
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Funds Holding This Stock
        </h2>
        <p className="font-sans text-sm text-ink-tertiary">No funds hold this stock (≥0.5% threshold).</p>
      </div>
    )
  }

  return (
    <div>
      <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
        Funds Holding This Stock
        <span className="ml-2 font-normal normal-case text-ink-tertiary">top {fundsHolding.length}</span>
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm font-sans border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="text-left py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">Fund</th>
              <th className="text-right py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">AUM (Cr)</th>
              <th className="text-right py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">Weight</th>
              <th className="text-center py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">Grade</th>
            </tr>
          </thead>
          <tbody>
            {fundsHolding.map((f) => (
              <tr key={f.fund_code} className="border-b border-paper-rule hover:bg-paper-deep transition-colors">
                <td className="py-2 px-3 text-ink-primary">
                  <span className="font-medium">{f.fund_name}</span>
                  <span className="block text-[10px] text-ink-tertiary">{f.fund_code}</span>
                </td>
                <td className="py-2 px-3 text-right font-mono text-ink-secondary tabular-nums">
                  {toNumber(f.aum_cr) != null ? `₹${parseFloat(f.aum_cr).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr` : '—'}
                </td>
                <td className="py-2 px-3 text-right font-mono text-ink-secondary tabular-nums">
                  {formatPct(String(parseFloat(f.weight_pct) / 100), { signed: false })}
                </td>
                <td className="py-2 px-3 text-center">
                  <GradeChip grade={f.atlas_grade as Grade} size="sm" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TechnicalsTab({
  technicals,
  returns,
}: {
  technicals: StockTechnicals | null
  returns: MultiTenureReturns | null
}) {
  if (!technicals) {
    return (
      <div
        id="tabpanel-technicals"
        role="tabpanel"
        aria-labelledby="tab-technicals"
        className="px-6 py-8 font-sans text-sm text-ink-tertiary"
      >
        No technical data available for this stock.
      </div>
    )
  }

  function techNum(s: string | null | undefined): string {
    const n = toNumber(s)
    if (n === null) return '—'
    return (n * 100).toFixed(2) + '%'
  }

  function rawNum(s: string | null | undefined, decimals = 2): string {
    const n = toNumber(s)
    if (n === null) return '—'
    return n.toFixed(decimals)
  }

  const metrics: Array<{ label: string; value: string; hint: string }> = [
    {
      label: 'EMA Distance (20)',
      value: techNum(technicals.ema_distance_20),
      hint: '% above/below 20-day EMA proxy',
    },
    {
      label: 'EMA Distance (50)',
      value: techNum(technicals.ema_distance_50),
      hint: '% above/below 50-day EMA proxy',
    },
    {
      label: 'EMA Distance (200)',
      value: techNum(technicals.ema_distance_200),
      hint: '% above/below 200-day EMA',
    },
    {
      label: 'RSI (14)',
      value: rawNum(technicals.rsi_14, 1),
      hint: '14-day RSI (0–100)',
    },
    {
      label: 'RS vs Nifty 500',
      value: techNum(technicals.rs_pct_nifty500),
      hint: '6M RS residual vs Nifty 500',
    },
    {
      label: 'Vol (252d)',
      value: techNum(technicals.vol_252d),
      hint: '252-day annualised realised volatility',
    },
    {
      label: 'OBV Slope (60d)',
      value: rawNum(technicals.obv_20d, 4),
      hint: 'On-balance volume slope over 60 days',
    },
    {
      label: 'ATR (14)',
      value: techNum(technicals.atr_14),
      hint: 'Average True Range over 14 days as % of price',
    },
    {
      label: '% from 52W High',
      value: techNum(technicals.pct_from_52w_high),
      hint: 'Distance from 52-week high',
    },
    {
      label: '% from 52W Low',
      value: techNum(technicals.pct_from_52w_low),
      hint: 'Distance from 52-week low',
    },
    {
      label: 'Drawdown (Peak)',
      value: techNum(technicals.drawdown_from_peak),
      hint: 'Max drawdown in formation window',
    },
  ]

  return (
    <div
      id="tabpanel-technicals"
      role="tabpanel"
      aria-labelledby="tab-technicals"
      className="px-6 py-6 flex flex-col gap-6"
    >
      <div className="font-sans text-[10px] text-ink-tertiary">
        Data as of: {technicals.date}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {metrics.map(({ label, value, hint }) => (
          <div
            key={label}
            title={hint}
            className="border border-paper-rule rounded-[2px] p-3 bg-paper"
          >
            <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
              {label}
            </div>
            <div className="font-mono text-lg font-semibold tabular-nums text-ink-primary">
              {value}
            </div>
          </div>
        ))}
      </div>

      {returns && (
        <div>
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            Multi-Tenure Returns
          </h2>
          <MultiTenureReturnsTable rows={[returns]} highlightIid={technicals?.iid} />
        </div>
      )}
    </div>
  )
}

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

export function StockDetailClient({
  stock,
  holdingState,
  technicals,
  returns,
  fundsHolding,
  auditTrail,
  crossRuleDepth,
  deploymentMultiplier,
  sectorGapPp,
  actionVerb,
  bullets,
  waterfallData,
  rankData,
}: StockDetailClientProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <StockHero
        stock={stock}
        holdingState={holdingState}
        technicals={technicals}
        deploymentMultiplier={deploymentMultiplier}
        sectorGapPp={sectorGapPp}
        crossRuleDepth={crossRuleDepth}
        actionVerb={actionVerb}
        bullets={bullets}
      />

      {/* Tab navigation */}
      <TabNav active={activeTab} onChange={setActiveTab} />

      {/* Tab panels */}
      {activeTab === 'overview' && (
        <OverviewTab
          stock={stock}
          waterfallData={waterfallData}
          rankData={rankData}
          fundsHolding={fundsHolding}
          returns={returns}
        />
      )}
      {activeTab === 'technicals' && (
        <TechnicalsTab technicals={technicals} returns={returns} />
      )}
      {activeTab === 'audit' && (
        <AuditTab auditTrail={auditTrail} />
      )}
    </div>
  )
}

export default StockDetailClient
