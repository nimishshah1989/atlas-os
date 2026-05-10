'use client'
import type { ReactNode } from 'react'
import { ArrowUp, ArrowDown, AlertTriangle, Info } from 'lucide-react'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorSnapshot } from '@/lib/queries/sectors'
import { RSStateChip, MomentumChip, RiskChip, VolumeChip } from '@/lib/stock-formatters'

type SectorWithDecision = SectorSnapshot & { decision: SectorDecision }

const DECISION_STYLE: Record<SectorDecision, string> = {
  'ENTER':     'bg-signal-pos/10 text-signal-pos border-signal-pos/30',
  'HOLD':      'bg-teal/10 text-teal border-teal/30',
  'ROTATE IN': 'bg-signal-warn/10 text-signal-warn border-signal-warn/30',
  'WATCH':     'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30',
  'PASS':      'bg-ink-tertiary/10 text-ink-tertiary border-ink-tertiary/30',
  'EXIT':      'bg-signal-neg/10 text-signal-neg border-signal-neg/30',
}

const STATE_COLOR: Record<string, string> = {
  Overweight:  'text-signal-pos',
  Neutral:     'text-signal-warn',
  Underweight: 'text-signal-neg',
  Avoid:       'text-signal-neg',
}

function pct(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function ReturnTile({ label, value }: { label: string; value: string | null }) {
  const n = value != null ? parseFloat(value) : null
  const colorClass = n == null ? 'text-ink-tertiary' : n >= 0 ? 'text-signal-pos' : 'text-signal-neg'
  const Icon = n == null ? null : n >= 0 ? ArrowUp : ArrowDown
  return (
    <div className="flex-1 px-3 py-2.5 border border-paper-rule rounded-sm bg-paper">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono text-base font-semibold tabular-nums flex items-center gap-1 ${colorClass}`}>
        {Icon && <Icon className="w-3.5 h-3.5" />}
        <span>{pct(value)}</span>
      </div>
    </div>
  )
}

function StateBadge({
  label,
  value,
  hint,
}: {
  label: string
  value: string | null
  hint?: string
}) {
  const colorClass = value && STATE_COLOR[value]
    ? STATE_COLOR[value]
    : value === 'Improving' || value === 'Leader' || value === 'Strong'
      ? 'text-signal-pos'
      : value === 'Deteriorating' || value === 'Weak' || value === 'Laggard'
        ? 'text-signal-neg'
        : 'text-ink-secondary'
  return (
    <div className="px-3 py-2 border border-paper-rule rounded-sm bg-paper">
      <div className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">
        <span>{label}</span>
        {hint && (
          <span title={hint}>
            <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
          </span>
        )}
      </div>
      <div className={`font-sans text-xs font-semibold ${colorClass}`}>
        {value ?? '—'}
      </div>
    </div>
  )
}

function ChipBadge({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="px-3 py-2 border border-paper-rule rounded-sm bg-paper">
      <div className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">
        <span>{label}</span>
        {hint && (
          <span title={hint}>
            <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

function ConcentrationGauge({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const display = (n * 100).toFixed(0) + '%'
  const color = n >= 0.6 ? '#B0492C' : n >= 0.4 ? '#B8860B' : '#2F6B43'
  const tone = n >= 0.6 ? 'High concentration — leadership narrow' : n >= 0.4 ? 'Moderate' : 'Broad participation'
  return (
    <div className="flex items-center gap-2">
      <div className="relative w-16 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.min(100, n * 100)}%`, background: color }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{display}</span>
      <span className="font-sans text-[10px] text-ink-tertiary">{tone}</span>
    </div>
  )
}

export function SectorDrawerSnapshot({ snapshot }: { snapshot: SectorWithDecision }) {
  const stateColor = STATE_COLOR[snapshot.sector_state] ?? 'text-ink-secondary'

  return (
    <div className="space-y-4 pb-4 border-b border-paper-rule">
      {/* Top row: state + decision + count */}
      <div className="flex items-stretch gap-2">
        <div className="flex-1 px-3 py-2.5 border border-paper-rule rounded-sm bg-paper" title="Overweight = above-benchmark allocation justified. Neutral = market-weight. Underweight = reduce. Avoid = no new positions.">
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">State</div>
          <div className={`font-sans text-base font-semibold ${stateColor}`}>{snapshot.sector_state}</div>
        </div>
        <div className={`flex-1 px-3 py-2.5 border rounded-sm ${DECISION_STYLE[snapshot.decision]}`} title="ENTER = open position. HOLD = maintain. ROTATE IN = shift from weaker sectors. WATCH = improving but not confirmed. PASS = no signal. EXIT = close positions.">
          <div className="font-sans text-[10px] uppercase tracking-wider mb-1 opacity-70">Decision</div>
          <div className="font-sans text-base font-bold">{snapshot.decision}</div>
        </div>
        <div className="flex-1 px-3 py-2.5 border border-paper-rule rounded-sm bg-paper" title="Number of stocks in the Atlas universe for this sector. Broader coverage = more reliable breadth and RS aggregation.">
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Stocks</div>
          <div className="font-sans text-base font-semibold text-ink-primary">{snapshot.constituent_count}</div>
        </div>
      </div>

      {/* Returns row */}
      <div>
        <div className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">
          <span>Bottom-up Returns (avg of constituents)</span>
          <span title="Average return of all stocks in this sector over each period. 'Bottom-up' = aggregated from individual stocks (not the NSE sector index). More representative of what the average stock holder experiences vs top-down index returns skewed by heavyweights.">
            <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
          </span>
        </div>
        <div className="flex items-stretch gap-2">
          {snapshot.bottomup_ret_1w != null && (
            <ReturnTile label="1 Week" value={snapshot.bottomup_ret_1w} />
          )}
          <ReturnTile label="1 Month" value={snapshot.bottomup_ret_1m} />
          <ReturnTile label="3 Month" value={snapshot.bottomup_ret_3m} />
          <ReturnTile label="6 Month" value={snapshot.bottomup_ret_6m} />
        </div>
      </div>

      {/* RS Momentum */}
      {snapshot.rs_momentum != null && (() => {
        const mom = parseFloat(snapshot.rs_momentum)
        const pp = (mom * 100).toFixed(1)
        const isPos = mom >= 0
        return (
          <div>
            <div className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">
              <span>RS Momentum (20-day change)</span>
              <span title="Change in 3-month relative strength over the last 20 trading days, in percentage points. +4pp = sector gained 4pp of RS vs Nifty 500 over 20 days. Positive = RS accelerating (gaining ground). Negative = RS fading. Key for timing: sectors with positive RS AND rising RS momentum have the strongest setup.">
                <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
              </span>
            </div>
            <div className={`inline-flex items-center gap-2 px-3 py-2 border rounded-sm ${isPos ? 'border-signal-pos/30 bg-signal-pos/5' : 'border-signal-neg/30 bg-signal-neg/5'}`}>
              <span className={`font-mono text-sm font-semibold tabular-nums ${isPos ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {isPos ? '+' : ''}{pp}pp
              </span>
              <span className={`font-sans text-xs ${isPos ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {isPos ? '▲ RS accelerating — gaining vs Nifty 500' : '▼ RS fading — losing vs Nifty 500'}
              </span>
            </div>
          </div>
        )
      })()}

      {snapshot.topdown_index_code && (
        <div>
          <div className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">
            <span>Top-down Returns ({snapshot.topdown_index_code} index)</span>
            <span title="Returns computed from the NSE sector benchmark index (e.g. Nifty Bank for Banking). Top-down = index level, driven by the largest-cap stocks. Can diverge from bottom-up when a few heavyweights dominate — divergence signals fragile sector leadership.">
              <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
            </span>
          </div>
          <div className="flex items-stretch gap-2">
            <ReturnTile label="1 Month" value={snapshot.topdown_ret_1m} />
            <ReturnTile label="3 Month" value={snapshot.topdown_ret_3m} />
            <ReturnTile label="RS 3M" value={snapshot.topdown_rs_3m_nifty500} />
          </div>
        </div>
      )}

      {/* State badges grid */}
      <div>
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">
          Signal Components
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StateBadge
            label="Bottom-up"
            value={snapshot.bottomup_state}
            hint="Derived from constituent stock signals: RS vs Nifty 500, % stocks above 50d EMA, and RS momentum direction. When bottom-up and top-down agree, conviction is highest. When they diverge, wait for confirmation."
          />
          <StateBadge
            label="Top-down"
            value={snapshot.topdown_state}
            hint="Derived from the NSE sector index itself — its trend, RS vs Nifty 500, and slope of the index. Top-down is more responsive to large-cap moves; bottom-up better reflects the average stock. Both must agree for high-conviction sector calls."
          />
          <ChipBadge
            label="RS"
            hint="7-level relative strength classification of the sector's constituent stocks vs Nifty 500. Leader = top RS decile. Laggard = bottom RS decile. Strong/Weak are mid-tier. Emerging = recently crossed into positive territory. Each level maps to a specific RS percentile band."
          >
            <RSStateChip value={snapshot.bottomup_rs_state} />
          </ChipBadge>
          <ChipBadge
            label="Momentum"
            hint="Direction of change in the sector's RS over the last 20 trading days. Improving = sector is gaining ground vs Nifty 500 (RS rising). Deteriorating = sector is losing ground (RS falling). Stable = no meaningful change. Accelerating = RS improving at a faster rate. Collapsing = RS falling sharply."
          >
            <MomentumChip value={snapshot.bottomup_momentum_state} />
          </ChipBadge>
          <ChipBadge
            label="Risk"
            hint="Aggregate risk posture of sector constituents. Combines extension above moving averages, historical volatility, and recent drawdown. Low/Normal = safe to add. Elevated = overextended, wait for pullback. High = significant extension, avoid new positions. Below Trend = in downtrend, capital at risk. Pipeline WIP — may show '—' until sector-level risk aggregation ships."
          >
            <RiskChip value={snapshot.bottomup_risk_state} />
          </ChipBadge>
          <ChipBadge
            label="Volume"
            hint="Volume-weighted buying/selling pressure across sector constituents. Accumulation = elevated volume on up-days (institutional buying). Steady-Buying = consistent positive flow. Distribution = elevated volume on down-days (institutional selling). Heavy Distribution = aggressive selling. Pipeline WIP — may show '—' until sector-level volume aggregation ships."
          >
            <VolumeChip value={snapshot.bottomup_volume_state} />
          </ChipBadge>
        </div>
      </div>

      {/* Concentration */}
      <div>
        <div className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">
          <span>Leadership Concentration</span>
          <span title="What share of the sector's total positive RS comes from just the top 1–2 stocks. Low (green, &lt;40%) = broad leadership — many stocks contributing. Moderate (amber, 40–60%) = concentration building. High (red, &gt;60%) = a few names carrying the sector; if they crack, the sector cracks. A sector with broad participation is more durable.">
            <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
          </span>
        </div>
        <ConcentrationGauge value={snapshot.leadership_concentration} />
      </div>

      {/* Divergence callout */}
      {snapshot.divergence_flag && (
        <div className="border border-signal-warn/30 bg-signal-warn/5 rounded-sm overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-signal-warn/20">
            <AlertTriangle className="w-3.5 h-3.5 text-signal-warn flex-shrink-0" />
            <div className="font-sans text-xs font-semibold text-signal-warn">
              Signal Divergence — confirmation required before acting
            </div>
          </div>
          <div className="px-3 py-2.5 space-y-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="px-2.5 py-2 bg-paper rounded-sm border border-paper-rule">
                <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">
                  Bottom-up (stocks say)
                </div>
                <div className={`font-sans text-xs font-semibold ${
                  snapshot.bottomup_state === 'Overweight' ? 'text-signal-pos'
                  : snapshot.bottomup_state === 'Neutral' ? 'text-signal-warn'
                  : 'text-signal-neg'
                }`}>
                  {snapshot.bottomup_state ?? '—'}
                </div>
                <div className="font-sans text-[10px] text-ink-tertiary mt-0.5 leading-snug">
                  Derived from RS, breadth, and momentum of constituent stocks
                </div>
              </div>
              <div className="px-2.5 py-2 bg-paper rounded-sm border border-paper-rule">
                <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">
                  Top-down (index says)
                </div>
                <div className={`font-sans text-xs font-semibold ${
                  snapshot.topdown_state === 'Overweight' ? 'text-signal-pos'
                  : snapshot.topdown_state === 'Neutral' ? 'text-signal-warn'
                  : 'text-signal-neg'
                }`}>
                  {snapshot.topdown_state ?? '—'}
                </div>
                <div className="font-sans text-[10px] text-ink-tertiary mt-0.5 leading-snug">
                  Derived from the NSE sector index trend and RS
                </div>
              </div>
            </div>
            <div className="font-sans text-[11px] text-ink-secondary leading-snug">
              When these disagree, the model lacks conviction. Wait for both signals to align
              before opening or closing a position — whichever flips first defines the resolution.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
