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

function MiniBar({ count, total, color }: { count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <div className="w-16 h-1.5 bg-paper-rule rounded-full overflow-hidden shrink-0">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-[10px] text-ink-tertiary tabular-nums w-6 text-right shrink-0">{count}</span>
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
    <div className="border border-paper-rule rounded-sm bg-paper px-5 py-3">
      <div className="flex flex-wrap gap-6 items-start">

        {/* RS Distribution — compact column */}
        <div className="flex flex-col gap-1 min-w-[160px]">
          <div className="font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
            RS Distribution
          </div>
          {RS_STATES.map(s => (
            <div key={s} className="flex items-center gap-1.5">
              <span className="w-[78px] text-[10px] text-ink-tertiary font-sans text-right shrink-0">{s}</span>
              <MiniBar count={rsCounts[s] ?? 0} total={n} color={rsStateColor(s)} />
            </div>
          ))}
        </div>

        {/* Divider */}
        <div className="w-px self-stretch bg-paper-rule/60 hidden md:block" />

        {/* Momentum Distribution — compact column */}
        <div className="flex flex-col gap-1 min-w-[160px]">
          <div className="font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
            Momentum
          </div>
          {MOM_STATES.map(s => (
            <div key={s} className="flex items-center gap-1.5">
              <span className="w-[78px] text-[10px] text-ink-tertiary font-sans text-right shrink-0">{s}</span>
              <MiniBar count={momCounts[s] ?? 0} total={n} color={MOM_COLORS[s] ?? CHART_COLORS.inkTertiary} />
            </div>
          ))}
        </div>

        {/* Divider */}
        <div className="w-px self-stretch bg-paper-rule/60 hidden md:block" />

        {/* Key signals strip */}
        <div className="flex flex-wrap gap-4 items-start flex-1 min-w-[180px]">
          <div className="flex flex-col gap-0.5">
            <span className="font-sans text-[9px] text-ink-tertiary uppercase tracking-wider">Leader/Strong</span>
            <span className="font-mono text-base font-semibold text-ink-primary tabular-nums">
              {leaderStrong}
              <span className="text-xs font-normal text-ink-tertiary ml-1">/ {n}</span>
            </span>
            <span className="font-mono text-[10px] text-signal-pos">{n > 0 ? Math.round((leaderStrong / n) * 100) : 0}%</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="font-sans text-[9px] text-ink-tertiary uppercase tracking-wider">Investable</span>
            <span className="font-mono text-base font-semibold text-ink-primary tabular-nums">
              {investable}
              <span className="text-xs font-normal text-ink-tertiary ml-1">/ {n}</span>
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="font-sans text-[9px] text-ink-tertiary uppercase tracking-wider">Accel/Improving</span>
            <span className="font-mono text-base font-semibold text-ink-primary tabular-nums">
              {accelImpr}
              <span className="text-xs font-normal text-ink-tertiary ml-1">/ {n}</span>
            </span>
            <span className="font-mono text-[10px] text-signal-pos">{n > 0 ? Math.round((accelImpr / n) * 100) : 0}%</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="font-sans text-[9px] text-ink-tertiary uppercase tracking-wider">Median RS Pctile</span>
            <span className="font-mono text-base font-semibold text-ink-primary tabular-nums">
              {Math.round(medianPctile * 100)}
              <span className="text-xs font-normal text-ink-tertiary ml-0.5">%ile</span>
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className="w-px self-stretch bg-paper-rule/60 hidden lg:block" />

        {/* Commentary — compact */}
        <div className="flex-1 min-w-[200px] max-w-[360px]">
          <CommentaryBlock
            narrative={commentary.narrative}
            contextCards={commentary.contextCards}
          />
        </div>
      </div>
    </div>
  )
}
