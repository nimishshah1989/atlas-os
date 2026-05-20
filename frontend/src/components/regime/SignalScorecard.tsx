// frontend/src/components/regime/SignalScorecard.tsx
// 4-tile bottom-up signal scorecard (Trend / Breadth / Momentum / Participation).
// Each tile shows a value + MetricTooltip. Pure presentational — data passed as props.
'use client'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { metric } from '@/lib/metric-registry'

export type ScorecardTile = {
  label: string
  value: string | null
  rawValue: number | null
  source: string
}

export type ScorecardData = {
  trend: ScorecardTile
  breadth: ScorecardTile
  momentum: ScorecardTile
  participation: ScorecardTile
}

const TILE_METRIC_KEYS: Record<keyof ScorecardData, string> = {
  trend:         'scorecard_trend_pct',
  breadth:       'scorecard_breadth_pct',
  momentum:      'scorecard_momentum_net',
  participation: 'scorecard_participation',
}

function tileSignal(key: keyof ScorecardData, rawValue: number | null): 'pos' | 'neg' | 'neutral' {
  if (rawValue == null) return 'neutral'
  switch (key) {
    case 'trend':         return rawValue >= 0.5  ? 'pos' : rawValue >= 0.35 ? 'neutral' : 'neg'
    case 'breadth':       return rawValue >= 0.5  ? 'pos' : rawValue >= 0.4  ? 'neutral' : 'neg'
    case 'momentum':      return rawValue > 0     ? 'pos' : rawValue === 0   ? 'neutral' : 'neg'
    case 'participation': return rawValue >= 0.6  ? 'pos' : rawValue >= 0.4  ? 'neutral' : 'neg'
    default:              return 'neutral'
  }
}

const SIGNAL_COLOR: Record<'pos' | 'neg' | 'neutral', string> = {
  pos:     'text-signal-pos',
  neg:     'text-signal-neg',
  neutral: 'text-signal-warn',
}

const SIGNAL_BG: Record<'pos' | 'neg' | 'neutral', string> = {
  pos:     'bg-signal-pos/5 border-signal-pos/20',
  neg:     'bg-signal-neg/5 border-signal-neg/20',
  neutral: 'bg-signal-warn/5 border-signal-warn/20',
}

type TileProps = {
  tileKey: keyof ScorecardData
  tile: ScorecardTile
}

function ScorecardTileCard({ tileKey, tile }: TileProps) {
  const signal = tileSignal(tileKey, tile.rawValue)
  const colorClass = SIGNAL_COLOR[signal]
  const bgClass    = SIGNAL_BG[signal]
  const metricDef  = metric(TILE_METRIC_KEYS[tileKey])

  return (
    <div className={`border rounded-sm p-4 flex flex-col gap-2 ${bgClass}`}>
      <div className="flex items-center justify-between">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          {tile.label}
        </span>
        {metricDef && (
          <InfoTooltip
            content={`${metricDef.definition} Formula: ${metricDef.formula}`}
          />
        )}
      </div>
      <div className={`font-mono text-2xl font-semibold tabular-nums leading-none ${colorClass}`}>
        {tile.value ?? 'n/a'}
      </div>
    </div>
  )
}

type Props = {
  data: ScorecardData
}

export function SignalScorecard({ data }: Props) {
  const tiles: [keyof ScorecardData, ScorecardTile][] = [
    ['trend',         data.trend],
    ['breadth',       data.breadth],
    ['momentum',      data.momentum],
    ['participation', data.participation],
  ]

  return (
    <div className="px-6 py-4 border-b border-paper-rule">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3">
        Bottom-Up Signals
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {tiles.map(([key, tile]) => (
          <ScorecardTileCard key={key} tileKey={key} tile={tile} />
        ))}
      </div>
    </div>
  )
}
