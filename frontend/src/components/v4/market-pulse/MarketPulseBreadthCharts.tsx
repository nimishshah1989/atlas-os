// Market Pulse §3.e — the breadth participation history as four small theme-aware
// charts (count of Nifty 500 names above each trend EMA + net 52-week new highs).
// Counts are integers (fixes the old "# stocks with 2 decimals" bug). Server
// component; AtlasLightweightChart is the client boundary.
import { AtlasLightweightChart, type SeriesColor } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '../ui/Panel'
import type { BreadthRow } from '@/lib/queries/v6/breadth'

type NumKey = 'above_21' | 'above_50' | 'above_200' | 'net_new_highs'
const CHARTS: { key: NumKey; label: string; color: SeriesColor }[] = [
  { key: 'above_21', label: 'Above 21-EMA', color: 'teal' },
  { key: 'above_50', label: 'Above 50-EMA', color: 'pos' },
  { key: 'above_200', label: 'Above 200-EMA', color: 'warn' },
  { key: 'net_new_highs', label: 'Net new highs · 52w H − L', color: 'pos' },
]

export function MarketPulseBreadthCharts({ series }: { series: BreadthRow[] }) {
  if (series.length < 2) return null
  return (
    <Panel
      eyebrow="Participation"
      title="Breadth — count of Nifty 500 names"
      info={{ title: 'Breadth history', body: 'How many of the ~500 Nifty 500 constituents sit above each trend EMA, plus the net 52-week new-high count (highs − lows). Counts are instruments (integers), tracked daily — rising breadth = a broadening advance.' }}
    >
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {CHARTS.map((c) => {
          const data = series.map((r) => ({ time: r.date, value: r[c.key] }))
          return (
            <div key={c.key}>
              <p className="mb-1.5 font-num text-[10px] uppercase tracking-wider text-txt-3">{c.label}</p>
              <AtlasLightweightChart height={148} precision={0} series={[{ name: c.label, color: c.color, data }]} />
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
