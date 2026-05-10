// allow-large: single client shell that owns filter/search state shared across all fund bands;
// bands 1-4 are placeholders until Tasks 3.3-3.6 add the real sub-components
'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import type { FundRow } from '@/lib/queries/funds'
import type { CommentaryResult } from '@/lib/commentary/stocks'
import type { Period } from '@/lib/url-params'
import { matchesFundSearch } from '@/lib/fund-formatters'
import { FundMetricTiles } from '@/components/funds/FundMetricTiles'
import { FundBubbleChart } from '@/components/funds/FundBubbleChart'
import { FundIntelligencePanel } from '@/components/funds/FundIntelligencePanel'
import { FundScreener } from '@/components/funds/FundScreener'

// Placeholder imports — these components are created in Tasks 3.3-3.6
// They will be replaced by real imports once those tasks complete
export type TileCounts = {
  n_recommended: number
  n_hold: number
  n_leader_nav: number
  n_aligned: number
  n_strong_hold: number
  n_suspended: number
  n_weak_hold: number
}

export type FilterChip =
  | 'all'
  | 'recommended'
  | 'hold'
  | 'leader_nav'
  | 'aligned'
  | 'strong_hold'

type Props = {
  funds: FundRow[]
  period: Period
  tileCounts: TileCounts
  commentary: CommentaryResult
  medianRsPctile: number
  medianReturn: number | null
  topCategory: { name: string; mean: number } | null
}

export function FundPageClient({
  funds,
  period,
  tileCounts,
  commentary,
  medianRsPctile,                    // consumed in FundMetricTiles (Task 3.3) + Task 3.5
  medianReturn,                      // consumed in FundMetricTiles (Task 3.3) + Task 3.5
  topCategory,                       // consumed in FundIntelligencePanel
}: Props) {
  const [activeFilter, setActiveFilter] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')
  const router = useRouter()

  function handlePeriodChange(newPeriod: Period) {
    router.push(`/funds?period=${newPeriod}`)
  }

  function handleFilterChange(filter: FilterChip) {
    setActiveFilter(filter)
  }

  const filteredFunds = useMemo(() => {
    let result = funds
    if (activeFilter !== 'all') {
      result = result.filter(f => {
        if (activeFilter === 'recommended') return f.recommendation === 'Recommended'
        if (activeFilter === 'hold')        return f.recommendation === 'Hold'
        if (activeFilter === 'leader_nav')  return f.nav_state === 'Leader NAV'
        if (activeFilter === 'aligned')     return f.composition_state === 'Aligned'
        if (activeFilter === 'strong_hold') return f.recommendation === 'Hold' && f.holdings_state === 'Strong-Holdings'
        return true
      })
    }
    if (search.trim()) {
      result = result.filter(f => matchesFundSearch(f, search))
    }
    return result
  }, [funds, activeFilter, search])

  return (
    <div className="flex flex-col">
      {/* Band 1: Metric tiles */}
      <div className="px-6 py-3 border-b border-paper-rule">
        <FundMetricTiles
          tileCounts={tileCounts}
          medianRsPctile={medianRsPctile}
          medianReturn={medianReturn}
          period={period}
          funds={funds}
          activeFilter={activeFilter}
          onTileClick={handleFilterChange}
        />
      </div>

      {/* Band 2: Bubble chart */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <FundBubbleChart
          funds={funds}
          period={period}
          activeFilter={activeFilter}
          onFilterChange={handleFilterChange}
          onPeriodChange={handlePeriodChange}
        />
      </div>

      {/* Band 2.5: Intelligence Panel */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <FundIntelligencePanel
          funds={funds}
          commentary={commentary}
          medianRsPctile={medianRsPctile}
          medianReturn={medianReturn}
          topCategory={topCategory}
        />
      </div>

      {/* Band 3: Period selector + filter chips */}
      <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1">
          {(['1M', '3M', '6M', '1Y'] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => handlePeriodChange(p)}
              className={`px-3 py-1 rounded-sm font-sans text-xs font-medium transition-colors ${
                period === p
                  ? 'bg-teal text-white'
                  : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {([
            { key: 'all' as FilterChip,         label: 'All' },
            { key: 'recommended' as FilterChip, label: 'Recommended' },
            { key: 'hold' as FilterChip,        label: 'Hold' },
            { key: 'leader_nav' as FilterChip,  label: 'Leader/Strong NAV' },
            { key: 'aligned' as FilterChip,     label: 'Aligned' },
          ]).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => handleFilterChange(key)}
              className={`px-3 py-1 rounded-sm font-sans text-xs font-medium transition-colors ${
                activeFilter === key
                  ? 'bg-ink-primary text-paper'
                  : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          type="search"
          placeholder="Search funds..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="ml-auto px-3 py-1 rounded-sm border border-paper-rule bg-paper font-sans text-xs text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-teal"
        />
      </div>

      {/* Band 4: Fund Screener */}
      <div className="px-6 py-4">
        <FundScreener
          funds={filteredFunds}
          period={period}
          activeFilter={activeFilter}
          onFilterChange={handleFilterChange}
        />
      </div>
    </div>
  )
}
