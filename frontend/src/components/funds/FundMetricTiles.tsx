import React from 'react'
import type { FundRow } from '@/lib/queries/funds'
import type { Period } from '@/lib/url-params'
import type { TileCounts, FilterChip } from '@/components/funds/FundPageClient'

type Tone = 'pos' | 'neg' | 'warn' | 'neutral'

type TileProps = {
  label: string
  value: string
  sub?: string
  tone?: Tone
  filter?: FilterChip
  activeFilter?: FilterChip
  onTileClick?: (f: FilterChip) => void
}

function Tile({ label, value, sub, tone = 'neutral', filter, activeFilter, onTileClick }: TileProps) {
  const clickable = filter !== undefined && onTileClick !== undefined
  const isActive = clickable && activeFilter === filter
  const valueColor =
    tone === 'pos' ? 'text-signal-pos' :
    tone === 'neg' ? 'text-signal-neg' :
    tone === 'warn' ? 'text-signal-warn' :
    'text-ink-primary'

  return (
    <div
      className={`flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0 ${
        isActive ? 'bg-paper-rule/10' : ''
      } ${clickable ? 'cursor-pointer hover:bg-paper-rule/5' : ''}`}
      onClick={clickable ? () => onTileClick(filter) : undefined}
      role={clickable ? 'button' : undefined}
      aria-pressed={clickable ? isActive : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onTileClick(filter)
        }
      } : undefined}
    >
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap">{label}</div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${valueColor}`}>{value}</div>
      {sub && <div className="font-sans text-[10px] text-ink-tertiary">{sub}</div>}
    </div>
  )
}

type Props = {
  tileCounts: TileCounts
  medianRsPctile: number
  medianReturn: number | null
  period: Period
  funds: FundRow[]
  activeFilter: FilterChip
  onTileClick: (f: FilterChip) => void
}

export function FundMetricTiles({
  tileCounts,
  medianRsPctile,
  medianReturn,
  period,
  funds,
  activeFilter,
  onTileClick,
}: Props) {
  const n = funds.length
  if (n === 0) return null

  // Pct helpers — avoid division by zero
  const pct = (count: number, total: number): string =>
    total === 0 ? '0' : ((count / total) * 100).toFixed(0)

  // Recommended
  const recPct = pct(tileCounts.n_recommended, n)
  const recTone: Tone = tileCounts.n_recommended > 0 ? 'pos' : 'neutral'

  // Hold
  const holdPct = pct(tileCounts.n_hold, n)

  // Leader NAV
  const leaderPct = Number(pct(tileCounts.n_leader_nav, n))
  const leaderTone: Tone = leaderPct >= 20 ? 'pos' : leaderPct >= 10 ? 'warn' : 'neg'

  // Aligned
  const alignedPct = Number(pct(tileCounts.n_aligned, n))
  const alignedTone: Tone = alignedPct >= 50 ? 'pos' : alignedPct >= 25 ? 'warn' : 'neutral'

  // Strong Hold — pct of n_hold, not total
  const strongHoldSub =
    tileCounts.n_hold === 0
      ? '—'
      : `${pct(tileCounts.n_strong_hold, tileCounts.n_hold)}% of hold`
  const strongHoldPctOfHold = tileCounts.n_hold === 0
    ? 0
    : (tileCounts.n_strong_hold / tileCounts.n_hold) * 100
  const strongHoldTone: Tone = strongHoldPctOfHold >= 50 ? 'pos' : 'warn'

  // Median RS
  const medianRsTone: Tone =
    medianRsPctile >= 0.6 ? 'pos' : medianRsPctile >= 0.4 ? 'warn' : 'neg'

  // Median Return
  const medianRetValue =
    medianReturn === null
      ? '—'
      : `${medianReturn >= 0 ? '+' : ''}${(medianReturn * 100).toFixed(1)}%`
  const medianRetTone: Tone =
    medianReturn === null || medianReturn === 0
      ? 'neutral'
      : medianReturn > 0
        ? 'pos'
        : 'neg'

  return (
    <>
      <div className="flex overflow-x-auto border border-paper-rule rounded-sm bg-paper divide-x divide-paper-rule">
        <Tile
          label="RECOMMENDED"
          value={`${tileCounts.n_recommended}`}
          sub={`${recPct}% of universe`}
          tone={recTone}
          filter="recommended"
          activeFilter={activeFilter}
          onTileClick={onTileClick}
        />
        <Tile
          label="HOLD"
          value={`${tileCounts.n_hold}`}
          sub={`${holdPct}% of universe`}
          tone="neutral"
          filter="hold"
          activeFilter={activeFilter}
          onTileClick={onTileClick}
        />
        <Tile
          label="LEADER NAV"
          value={`${tileCounts.n_leader_nav}`}
          sub={`${leaderPct}% leader`}
          tone={leaderTone}
          filter="leader_nav"
          activeFilter={activeFilter}
          onTileClick={onTileClick}
        />
        <Tile
          label="ALIGNED"
          value={`${tileCounts.n_aligned}`}
          sub={`${alignedPct}% composition`}
          tone={alignedTone}
          filter="aligned"
          activeFilter={activeFilter}
          onTileClick={onTileClick}
        />
        <Tile
          label="STRONG HOLD"
          value={`${tileCounts.n_strong_hold}`}
          sub={strongHoldSub}
          tone={strongHoldTone}
          filter="strong_hold"
          activeFilter={activeFilter}
          onTileClick={onTileClick}
        />
        <Tile
          label="MEDIAN RS"
          value={`${(medianRsPctile * 100).toFixed(0)}th`}
          tone={medianRsTone}
        />
        <Tile
          label={`MEDIAN ${period} RET`}
          value={medianRetValue}
          tone={medianRetTone}
        />
      </div>
      <div className="mt-1 font-sans text-[10px] text-ink-tertiary">
        {funds.length} of 592 funds computed
      </div>
    </>
  )
}
