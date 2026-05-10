// allow-large: single client shell that owns filter/search state shared across all fund bands;
// bands 1-4 are placeholders until Tasks 3.3-3.6 add the real sub-components
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import type { FundRow } from '@/lib/queries/funds'
import type { CommentaryResult } from '@/lib/commentary/stocks'
import type { Period } from '@/lib/url-params'

// Placeholder imports — these components are created in Tasks 3.3-3.6
// They will be replaced by real imports once those tasks complete
export type TileCounts = {
  n_recommended: number
  n_hold: number
  n_leader_nav: number
  n_aligned: number
  n_strong_hold: number
  medianRet: number
  medianRsPctile: number
  total: number
  latestDate: Date | null
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
  topCategory: string | null
  topCategoryRsPctile: number
}

export function FundPageClient({
  funds,
  period,
  tileCounts,
  commentary,
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

  const filteredFunds = funds.filter(f => {
    if (activeFilter === 'recommended') return f.recommendation === 'Recommended'
    if (activeFilter === 'hold')        return f.recommendation === 'Hold'
    if (activeFilter === 'leader_nav')  return f.nav_state === 'Leader NAV' || f.nav_state === 'Strong NAV'
    if (activeFilter === 'aligned')     return f.composition_state === 'Aligned'
    if (activeFilter === 'strong_hold') return f.holdings_state === 'Strong-Holdings'
    return true
  })

  return (
    <div className="flex flex-col">
      {/* Band 1: Metric tiles — placeholder until Task 3.3 */}
      <div className="px-6 py-3 border-b border-paper-rule">
        <div className="flex items-center gap-4 text-xs text-ink-tertiary font-sans">
          <span>{tileCounts.n_recommended} Recommended</span>
          <span>{tileCounts.n_hold} Hold</span>
          <span>{tileCounts.n_leader_nav} Leader/Strong NAV</span>
          <span>{tileCounts.n_aligned} Aligned</span>
          <span>{tileCounts.n_strong_hold} Strong Holdings</span>
          <span className="ml-auto">{tileCounts.total} of 592 computed</span>
        </div>
      </div>

      {/* Band 2: Bubble + Intelligence panel — placeholder until Tasks 3.4-3.5 */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <p className="font-sans text-sm text-ink-secondary leading-relaxed">{commentary.narrative}</p>
        <div className="flex flex-wrap gap-2 mt-2">
          {commentary.contextCards?.map((card, i) => (
            <div key={i} className="bg-paper-rule/10 border border-paper-rule/40 rounded-sm px-2.5 py-1.5">
              <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">{card.label}</div>
              <div className="font-sans text-sm font-medium text-ink-primary">{card.value}</div>
            </div>
          ))}
        </div>
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

      {/* Band 4: Fund list — simple table placeholder until Task 3.6 */}
      <div className="px-6 py-4">
        <p className="font-sans text-xs text-ink-tertiary">
          {filteredFunds.length} funds · {search ? `matching "${search}"` : activeFilter !== 'all' ? `filtered: ${activeFilter}` : 'showing all'}
        </p>
        <table className="w-full mt-3">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="text-left font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider py-2 pr-4">Fund</th>
              <th className="text-left font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider py-2 pr-4">AMC</th>
              <th className="text-left font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider py-2 pr-4">NAV State</th>
              <th className="text-right font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider py-2">Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {filteredFunds
              .filter(f => {
                if (!search.trim()) return true
                const q = search.trim().toLowerCase()
                return f.scheme_name.toLowerCase().includes(q) || f.amc.toLowerCase().includes(q)
              })
              .slice(0, 50)
              .map(f => (
                <tr key={f.mstar_id} className="border-b border-paper-rule/40 hover:bg-paper-rule/5">
                  <td className="py-2 pr-4">
                    <a href={`/funds/${f.mstar_id}`} className="font-sans text-xs text-ink-primary hover:text-teal">
                      {f.scheme_name}
                    </a>
                  </td>
                  <td className="py-2 pr-4 font-sans text-xs text-ink-secondary">{f.amc}</td>
                  <td className="py-2 pr-4 font-sans text-xs text-ink-secondary">{f.nav_state ?? '—'}</td>
                  <td className="py-2 text-right font-sans text-xs text-ink-secondary">{f.recommendation ?? '—'}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
