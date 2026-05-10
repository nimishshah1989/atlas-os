import type { StockRowWithSector } from '@/lib/queries/stocks'
import { CommentaryBlock } from '@/components/ui/CommentaryBlock'
import { buildStocksCommentary, type StocksPageAggregates } from '@/lib/commentary/stocks'
import { CHART_COLORS, rsStateColor } from '@/lib/chart-colors'

const MOM_COLORS: Record<string, string> = {
  Accelerating:  CHART_COLORS.momAccelerating,
  Improving:     CHART_COLORS.momImproving,
  Flat:          CHART_COLORS.momFlat,
  Deteriorating: CHART_COLORS.momDeteriorating,
  Collapsing:    CHART_COLORS.momCollapsing,
}

const RS_STATES  = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_STATES = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']

function DistBar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="w-16 text-ink-tertiary font-mono shrink-0 text-right">{label}</span>
      <div className="flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-6 text-ink-tertiary font-mono text-right">{count}</span>
    </div>
  )
}

type Props = {
  stocks: StockRowWithSector[]
  regimeState?: string
  deploymentMultiplier?: number
}

export function StockIntelligencePanel({ stocks, regimeState = 'Cautious', deploymentMultiplier = 0.6 }: Props) {
  const n = stocks.length
  if (n === 0) return null

  const rsCounts = Object.fromEntries(RS_STATES.map(s => [s, 0])) as Record<string, number>
  const momCounts = Object.fromEntries(MOM_STATES.map(s => [s, 0])) as Record<string, number>
  for (const stock of stocks) {
    if (stock.rs_state && rsCounts[stock.rs_state] !== undefined) rsCounts[stock.rs_state]++
    if (stock.momentum_state && momCounts[stock.momentum_state] !== undefined) momCounts[stock.momentum_state]++
  }

  const leaderStrong = (rsCounts['Leader'] ?? 0) + (rsCounts['Strong'] ?? 0)
  const investable   = stocks.filter(s => s.is_investable).length
  const accelImpr    = (momCounts['Accelerating'] ?? 0) + (momCounts['Improving'] ?? 0)
  const pctiles      = stocks.map(s => s.rs_pctile_3m ? parseFloat(s.rs_pctile_3m) : null).filter(v => v != null) as number[]
  pctiles.sort((a, b) => a - b)
  const medianPctile = pctiles.length > 0 ? pctiles[Math.floor(pctiles.length / 2)] : 0

  const aggregates: StocksPageAggregates = {
    total: n,
    investable_count: investable,
    leader_count: rsCounts['Leader'] ?? 0,
    strong_count: rsCounts['Strong'] ?? 0,
    pct_leader_strong: n > 0 ? leaderStrong / n : 0,
    median_rs_pctile: medianPctile,
    accel_count: accelImpr,
    regime_state: regimeState,
    deployment_multiplier: deploymentMultiplier,
  }

  const commentary = buildStocksCommentary(aggregates)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">RS Distribution</div>
          {RS_STATES.map(s => (
            <DistBar key={s} label={s} count={rsCounts[s] ?? 0} total={n} color={rsStateColor(s)} />
          ))}
        </div>
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">Momentum</div>
          {MOM_STATES.map(s => (
            <DistBar key={s} label={s} count={momCounts[s] ?? 0} total={n} color={MOM_COLORS[s] ?? CHART_COLORS.inkTertiary} />
          ))}
        </div>
      </div>
      <div className="border-t border-paper-rule pt-3">
        <CommentaryBlock
          narrative={commentary.narrative}
          contextCards={commentary.contextCards}
        />
      </div>
    </div>
  )
}
