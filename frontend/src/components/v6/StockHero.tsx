// frontend/src/components/v6/StockHero.tsx
//
// Hero panel for the v6 stock detail page.
// Layers: grade chip + ticker + sector pill + ConvictionTape + action verb +
//         3-5 thesis bullets + PortfolioBadge (expanded) +
//         PositionSizingWidget + CrossRuleDepth metric +
//         52w-high distance + drawdown-from-peak.
//
// All Decimal columns arrive as strings; toNumber() converts at the boundary.

'use client'

import { GradeChip } from './GradeChip'
import { ConvictionTape } from './ConvictionTape'
import { PortfolioBadge } from './PortfolioBadge'
import { PositionSizingWidget } from './PositionSizingWidget'
import { toNumber } from '@/lib/v6/decimal'
import type { ScreenStock } from '@/lib/api/v1'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { StockTechnicals } from '@/lib/queries/v6/stock_technicals'
import type { Grade } from './GradeChip'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CrossRuleDepthData {
  /** Number of rules currently firing in support (0..5). null = unavailable. */
  depth: number | null
  /** Total candidate rules (denominator — typically 5). */
  total: number
}

export interface StockHeroProps {
  stock: ScreenStock
  holdingState: HoldingState | null
  technicals: StockTechnicals | null
  deploymentMultiplier: number
  sectorGapPp: number
  crossRuleDepth: CrossRuleDepthData | null
  /** Action verb from thesis registry (BUY/ACCUMULATE/HOLD/WATCH/AVOID/SELL). */
  actionVerb: string
  /** 3-5 thesis bullets. */
  bullets: string[]
  className?: string
}

// ---------------------------------------------------------------------------
// Grade derivation — map conviction tape dominant direction → Atlas grade chip
// ---------------------------------------------------------------------------

function deriveGrade(stock: ScreenStock): Grade {
  const tenures = ['12m', '6m', '3m', '1m'] as const
  for (const t of tenures) {
    const seg = stock.conviction_tape[t]
    if (seg.direction === 'POSITIVE') {
      const ic = seg.ic ?? 0
      if (ic >= 0.07) return 'AAA'
      if (ic >= 0.05) return 'AA'
      return 'A'
    }
  }
  // Check negative direction
  for (const t of tenures) {
    const seg = stock.conviction_tape[t]
    if (seg.direction === 'NEGATIVE') {
      const ic = seg.ic ?? 0
      if (ic >= 0.07) return 'B'
      return 'BB'
    }
  }
  return 'BBB'
}

// ---------------------------------------------------------------------------
// CrossRuleDepth chip
// ---------------------------------------------------------------------------

function crossRuleDepthClass(depth: number | null, total: number): string {
  if (depth === null) return 'text-ink-tertiary'
  if (depth >= total) return 'text-signal-pos'
  if (depth >= 3) return 'text-signal-warn'
  return 'text-signal-neg'
}

interface DepthChipProps {
  data: CrossRuleDepthData | null
}

function CrossRuleDepthChip({ data }: DepthChipProps) {
  if (data === null || data.depth === null) {
    return (
      <span
        data-testid="cross-rule-depth"
        className="font-mono text-[11px] text-ink-tertiary"
        aria-label="Conviction depth unavailable"
      >
        Conviction depth: —
      </span>
    )
  }

  const cls = crossRuleDepthClass(data.depth, data.total)
  return (
    <span
      data-testid="cross-rule-depth"
      className={`font-mono text-[11px] font-medium ${cls}`}
      aria-label={`Conviction depth: ${data.depth} of ${data.total} rules`}
    >
      Conviction depth: <strong>{data.depth}/{data.total} rules</strong>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Metric tile helper
// ---------------------------------------------------------------------------

function MetricTile({
  label,
  value,
  valueClass = 'text-ink-primary',
}: {
  label: string
  value: string
  valueClass?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</span>
      <span className={`font-mono text-sm font-semibold tabular-nums ${valueClass}`}>{value}</span>
    </div>
  )
}

function formatDistancePct(s: string | null | undefined): { text: string; cls: string } {
  const n = toNumber(s)
  if (n === null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = n * 100
  const sign = pct >= 0 ? '+' : ''
  const cls = pct >= 0 ? 'text-signal-pos' : 'text-signal-neg'
  return { text: `${sign}${pct.toFixed(1)}%`, cls }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StockHero({
  stock,
  holdingState,
  technicals,
  deploymentMultiplier,
  sectorGapPp,
  crossRuleDepth,
  actionVerb,
  bullets,
  className = '',
}: StockHeroProps) {
  const grade = deriveGrade(stock)

  const highDist = formatDistancePct(technicals?.pct_from_52w_high)
  const ddPeak = formatDistancePct(technicals?.drawdown_from_peak)

  // Determine dominant direction for thesis/action verb color
  const actionVerbColor: Record<string, string> = {
    BUY: 'text-signal-pos',
    ACCUMULATE: 'text-signal-pos',
    HOLD: 'text-ink-secondary',
    WATCH: 'text-signal-warn',
    AVOID: 'text-signal-neg',
    SELL: 'text-signal-neg',
  }
  const verbColor = actionVerbColor[actionVerb] ?? 'text-ink-primary'

  // Cell conviction depth for sizing widget
  const convictionDepthForSizing = crossRuleDepth?.depth ?? 0

  return (
    <div className={`px-6 py-6 border-b border-paper-rule ${className}`}>
      {/* ── Row 1: grade + ticker + company + sector pill ── */}
      <div className="flex items-start justify-between flex-wrap gap-4 mb-5">
        <div className="flex items-center gap-3 flex-wrap">
          <GradeChip grade={grade} size="md" />
          <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
            {stock.symbol}
          </h1>
          {stock.company_name && (
            <span className="font-sans text-sm text-ink-secondary">
              {stock.company_name}
            </span>
          )}
          {stock.sector && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-paper-deep text-[10px] font-sans text-ink-tertiary uppercase tracking-wide">
              {stock.sector}
            </span>
          )}
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            {stock.tier}
          </span>
        </div>

        {/* PortfolioBadge expanded — silent when null */}
        <PortfolioBadge
          state={holdingState}
          variant="expanded"
          data-testid="portfolio-badge"
        />
      </div>

      {/* ── Row 2: ConvictionTape ── */}
      <div className="mb-5">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
          Conviction Tape
        </div>
        <ConvictionTape tape={stock.conviction_tape} />
      </div>

      {/* ── Row 3: Action verb + thesis bullets ── */}
      <div className="mb-5">
        <span className={`font-sans text-base font-semibold uppercase tracking-wide ${verbColor}`}>
          {actionVerb}
        </span>
        {bullets.length > 0 && (
          <ul className="mt-2 space-y-1">
            {bullets.slice(0, 5).map((b, i) => (
              <li
                key={i}
                className="font-sans text-sm text-ink-secondary leading-relaxed flex items-start gap-2"
              >
                <span className="text-ink-tertiary mt-0.5 shrink-0">·</span>
                <span dangerouslySetInnerHTML={{ __html: b.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── Row 4: Metrics strip ── */}
      <div className="flex flex-wrap gap-6 mb-5 pb-4 border-b border-paper-rule">
        <MetricTile
          label="52W High Dist."
          value={highDist.text}
          valueClass={highDist.cls}
        />
        <MetricTile
          label="Drawdown Peak"
          value={ddPeak.text}
          valueClass={ddPeak.cls}
        />
        <div className="flex flex-col gap-0.5 justify-end">
          <CrossRuleDepthChip data={crossRuleDepth} />
        </div>
      </div>

      {/* ── Row 5: Position sizing ── */}
      <PositionSizingWidget
        holdingState={holdingState}
        deploymentMultiplier={deploymentMultiplier}
        sectorGapPp={sectorGapPp}
        cellConvictionDepth={convictionDepthForSizing}
        className="w-full lg:max-w-lg"
      />
    </div>
  )
}

export default StockHero
