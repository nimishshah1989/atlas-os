'use client'

// frontend/src/components/v6/FundDetailClient.tsx
//
// Client component: hero + 3-tab layout for the v6 fund detail page.
// Tabs: Overview / Holdings / Audit Trail
//
// Overview: RankDecompositionCards + MultiBenchmarkRSWaterfall + returns grid
// Holdings: top-20 from top_holdings JSONB with Atlas verdict chips + sector tilt bar
// Audit: fund-flavored placeholder (stocks-first launch; fund audit trail in E.1)
//
// All Decimal transport as strings; toNumber() at render boundary.

import { useState } from 'react'
import { FundHero } from './FundHero'
import { RankDecompositionCards } from './RankDecompositionCards'
import { MultiBenchmarkRSWaterfall } from './MultiBenchmarkRSWaterfall'
import { GradeChip } from './GradeChip'
import { toNumber } from '@/lib/v6/decimal'
import type { FundDetail, FundHoldingEntry } from '@/lib/queries/v6/funds'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { SwitchProposal } from '@/lib/queries/v6/switch_proposals'
import type { Grade } from './GradeChip'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = 'overview' | 'holdings' | 'audit'

export interface FundDetailClientProps {
  fund: FundDetail
  holdingState: HoldingState | null
  switchProposals: SwitchProposal[]
  /** Waterfall data when available. null when no metric history. */
  waterfallData: {
    stock_return: string
    cohort_return: string
    nifty50_return: string
    nifty500_return: string
    gold_return: string | null
    tenure: '1m' | '3m' | '6m' | '12m'
  } | null
}

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'holdings', label: 'Holdings' },
  { id: 'audit', label: 'Audit Trail' },
]

function TabNav({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <nav
      role="tablist"
      aria-label="Fund detail tabs"
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

function buildRankComponents(
  fund: FundDetail,
): Array<{ name: string; raw_score: string; percentile_in_category: string; weight_pct: string; delta_vs_cohort: string }> {
  const components = []
  const size = fund.category_size ?? 1
  const rank = fund.rank_in_category ?? 1

  function toPercentile(score: string | null): string {
    // Approximate: score is 0–100; percentile ≈ score value
    return score ?? '50'
  }
  function toDelta(score: string | null): string {
    const n = toNumber(score)
    if (n === null) return '0'
    return String((n - 50).toFixed(1))
  }

  if (fund.risk_adjusted_return_score != null) {
    components.push({
      name: 'Risk-Adj Returns',
      raw_score: fund.risk_adjusted_return_score,
      percentile_in_category: toPercentile(fund.risk_adjusted_return_score),
      weight_pct: '40',
      delta_vs_cohort: toDelta(fund.risk_adjusted_return_score),
    })
  }
  if (fund.holdings_conviction_score != null) {
    components.push({
      name: 'Holdings Conviction',
      raw_score: fund.holdings_conviction_score,
      percentile_in_category: toPercentile(fund.holdings_conviction_score),
      weight_pct: '30',
      delta_vs_cohort: toDelta(fund.holdings_conviction_score),
    })
  }
  if (fund.style_sector_score != null) {
    components.push({
      name: 'Style / Sector',
      raw_score: fund.style_sector_score,
      percentile_in_category: toPercentile(fund.style_sector_score),
      weight_pct: '20',
      delta_vs_cohort: toDelta(fund.style_sector_score),
    })
  }
  if (fund.cost_manager_score != null) {
    components.push({
      name: 'Cost + Manager',
      raw_score: fund.cost_manager_score,
      percentile_in_category: toPercentile(fund.cost_manager_score),
      weight_pct: '10',
      delta_vs_cohort: toDelta(fund.cost_manager_score),
    })
  }

  // Use rank-based percentile if we have category_size
  if (size > 1 && rank > 0) {
    const pctileFromRank = String(((size - rank) / (size - 1)) * 100)
    return components.map((c) => ({
      ...c,
      percentile_in_category: pctileFromRank,
    }))
  }

  return components
}

function OverviewTab({
  fund,
  waterfallData,
}: {
  fund: FundDetail
  waterfallData: FundDetailClientProps['waterfallData']
}) {
  const rankData =
    fund.composite_score != null && fund.rank_in_category != null && fund.category_size != null
      ? {
          composite_score: fund.composite_score,
          components: buildRankComponents(fund),
          rank_in_category: fund.rank_in_category,
          category_size: fund.category_size,
        }
      : null

  const sharpeStr = fund.sharpe != null ? `${Number(fund.sharpe).toFixed(2)}` : '—'
  const maxDdStr = fund.max_dd != null ? `${(Number(fund.max_dd) * 100).toFixed(1)}%` : '—'

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
          Rank breakdown not available for this fund.
        </div>
      )}

      {/* Waterfall */}
      {waterfallData ? (
        <div>
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            Relative Strength vs Benchmarks ({waterfallData.tenure})
          </h2>
          <MultiBenchmarkRSWaterfall data={waterfallData} />
        </div>
      ) : null}

      {/* Risk metrics strip */}
      <div>
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Risk Metrics
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(
            [
              { label: 'Sharpe (3Y)', value: sharpeStr, hint: '3-year Sharpe ratio' },
              { label: 'Max Drawdown', value: maxDdStr, valueClass: maxDdStr !== '—' ? 'text-signal-neg' : 'text-ink-tertiary', hint: 'Max drawdown in formation window' },
              { label: 'Fund Age', value: fund.fund_age_years != null ? `${Math.floor(Number(fund.fund_age_years))} yrs` : '—' },
              { label: 'Nav As Of', value: fund.nav_as_of ?? '—' },
            ] as Array<{ label: string; value: string; valueClass?: string; hint?: string }>
          ).map(({ label, value, valueClass, hint }) => (
            <div
              key={label}
              title={hint}
              className="border border-paper-rule rounded-[2px] p-3 bg-paper"
            >
              <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">{label}</div>
              <div className={`font-mono text-lg font-semibold tabular-nums ${valueClass ?? 'text-ink-primary'}`}>
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Holdings tab
// ---------------------------------------------------------------------------

function verdictChip(verdict: FundHoldingEntry['verdict'], inUniverse: boolean) {
  if (!inUniverse) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-paper-deep text-[10px] font-sans text-ink-tertiary border border-paper-rule">
        Not in universe
      </span>
    )
  }
  if (verdict === 'POSITIVE') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-signal-pos/20 text-signal-pos text-[10px] font-semibold uppercase">
        POSITIVE
      </span>
    )
  }
  if (verdict === 'NEGATIVE') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-signal-neg/20 text-signal-neg text-[10px] font-semibold uppercase">
        NEGATIVE
      </span>
    )
  }
  if (verdict === 'NEUTRAL') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-signal-warn/20 text-signal-warn text-[10px] font-semibold uppercase">
        NEUTRAL
      </span>
    )
  }
  // verdict null but in universe
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-paper-deep text-ink-tertiary text-[10px] font-sans">
      No signal
    </span>
  )
}

function HoldingsTab({ fund }: { fund: FundDetail }) {
  const holdings = fund.top_holdings

  if (!holdings || holdings.length === 0) {
    return (
      <div
        id="tabpanel-holdings"
        role="tabpanel"
        aria-labelledby="tab-holdings"
        className="px-6 py-8 text-center font-sans text-sm text-ink-tertiary"
      >
        Holdings data not available for this fund.
      </div>
    )
  }

  const top20 = holdings.slice(0, 20)

  // Sector conviction histogram (verdicts count)
  const positiveCount = top20.filter((h) => h.verdict === 'POSITIVE').length
  const neutralCount = top20.filter((h) => h.verdict === 'NEUTRAL').length
  const negativeCount = top20.filter((h) => h.verdict === 'NEGATIVE').length
  const noSignalCount = top20.filter((h) => h.verdict === null && h.instrument_id != null).length
  const notInUniverseCount = top20.filter((h) => h.instrument_id == null || h.symbol == null).length
  const total = top20.length

  return (
    <div
      id="tabpanel-holdings"
      role="tabpanel"
      aria-labelledby="tab-holdings"
      className="px-6 py-6 flex flex-col gap-6"
    >
      {/* Holdings conviction histogram */}
      <div>
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Holdings Conviction Mix (top {total})
        </h2>
        <div className="flex gap-3 flex-wrap" data-testid="conviction-histogram">
          {positiveCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-signal-pos/15 text-signal-pos text-[11px] font-semibold">
              POSITIVE <span className="font-mono">{positiveCount}</span>
            </span>
          )}
          {neutralCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-signal-warn/15 text-signal-warn text-[11px] font-semibold">
              NEUTRAL <span className="font-mono">{neutralCount}</span>
            </span>
          )}
          {negativeCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-signal-neg/15 text-signal-neg text-[11px] font-semibold">
              NEGATIVE <span className="font-mono">{negativeCount}</span>
            </span>
          )}
          {noSignalCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-paper-deep text-ink-tertiary text-[11px]">
              No Signal <span className="font-mono">{noSignalCount}</span>
            </span>
          )}
          {notInUniverseCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-paper-deep text-ink-tertiary text-[11px] border border-paper-rule">
              Not in Universe <span className="font-mono">{notInUniverseCount}</span>
            </span>
          )}
        </div>
      </div>

      {/* Holdings table */}
      <div>
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Top {top20.length} Holdings
          {fund.holdings_as_of && (
            <span className="ml-2 font-normal normal-case text-ink-tertiary">
              as of {fund.holdings_as_of}
            </span>
          )}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans border-collapse">
            <thead>
              <tr className="border-b border-paper-rule">
                <th className="text-left py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                  #
                </th>
                <th className="text-left py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                  Stock
                </th>
                <th className="text-right py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                  Weight
                </th>
                <th className="text-center py-2 px-3 font-medium text-ink-tertiary text-[11px] uppercase tracking-wide">
                  Atlas Verdict
                </th>
              </tr>
            </thead>
            <tbody>
              {top20.map((h, i) => {
                const inUniverse = h.instrument_id != null && h.symbol != null
                return (
                  <tr
                    key={h.instrument_id ?? `row-${i}`}
                    className="border-b border-paper-rule hover:bg-paper-deep transition-colors"
                  >
                    <td className="py-2 px-3 font-mono text-ink-tertiary text-xs w-8">
                      {i + 1}
                    </td>
                    <td className="py-2 px-3 text-ink-primary">
                      <span className="font-medium">{h.symbol ?? '—'}</span>
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-ink-secondary tabular-nums">
                      {h.weight_pct > 0 ? `${h.weight_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className="py-2 px-3 text-center">
                      {verdictChip(h.verdict, inUniverse)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Audit Trail tab (fund-flavored)
// ---------------------------------------------------------------------------

function AuditTrailTab() {
  return (
    <div
      id="tabpanel-audit"
      role="tabpanel"
      aria-labelledby="tab-audit"
      className="px-6 py-8"
    >
      <div className="border border-paper-rule rounded-[2px] p-6 bg-paper max-w-2xl">
        <h3 className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-4">
          Fund Audit Trail
        </h3>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mb-3">
          The Atlas audit trail for funds records scorecard provenance: composite
          score lineage, layer score inputs (risk-adjusted returns, holdings
          conviction, style/sector, cost+manager), and NAV data source.
        </p>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mb-3">
          Full fund audit (holdings provenance, benchmark drift events,
          manager-change triggers) is scoped for v6.0 final (Task E.1).
          v6.0 launch is stocks-first per the methodology lock — the cell-matrix
          audit trail (Sections 1–5) applies to equity instruments, not funds.
        </p>
        <p className="font-sans text-[11px] text-ink-tertiary italic">
          Fund scoring methodology: peer-quartile composite across 4 layers.
          See CONTEXT.md §MF-Scorecard for the locked methodology.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function FundDetailClient({
  fund,
  holdingState,
  switchProposals,
  waterfallData,
}: FundDetailClientProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <FundHero
        fund={fund}
        holdingState={holdingState}
        switchProposals={switchProposals}
      />

      {/* Tab navigation */}
      <TabNav active={activeTab} onChange={setActiveTab} />

      {/* Tab panels */}
      {activeTab === 'overview' && (
        <OverviewTab fund={fund} waterfallData={waterfallData} />
      )}
      {activeTab === 'holdings' && (
        <HoldingsTab fund={fund} />
      )}
      {activeTab === 'audit' && (
        <AuditTrailTab />
      )}
    </div>
  )
}

export default FundDetailClient
