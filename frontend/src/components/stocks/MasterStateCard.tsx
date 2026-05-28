// frontend/src/components/stocks/MasterStateCard.tsx
// Sticky top-of-page card showing master Weinstein state, dwell context,
// urgency, action guidance, and within-state rank breakdown.
// Pure server component — no interactivity needed. Sticky via CSS only.
import { AlertTriangle, Clock } from 'lucide-react'
import type { StockState, CohortBaseline } from '@/lib/queries/states'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { metric } from '@/lib/metric-registry'

interface MasterStateCardProps {
  symbol: string
  state: StockState
  cohortBaseline: CohortBaseline | null
  /** Rank of this stock among same-state peers today (1 = top). null if not computed. */
  peerRank: number | null
  /** Total count of stocks in the same state today. */
  peerTotal: number
}

// ---------------------------------------------------------------------------
// State → display label + color token
// ---------------------------------------------------------------------------

const STATE_LABEL: Record<StockState['state'], string> = {
  stage_1:      'STAGE 1 BASE',
  stage_2a:     'STAGE 2A FRESH BREAKOUT',
  stage_2b:     'STAGE 2B CONFIRMED',
  stage_2c:     'STAGE 2C MATURE',
  stage_3:      'STAGE 3 TOP',
  stage_4:      'STAGE 4 DECLINE',
  uninvestable: 'UNINVESTABLE',
}

const STATE_COLOR: Record<StockState['state'], string> = {
  stage_1:      'text-ink-secondary',
  stage_2a:     'text-signal-pos',
  stage_2b:     'text-signal-pos',
  stage_2c:     'text-signal-warn',
  stage_3:      'text-signal-warn',
  stage_4:      'text-signal-neg',
  uninvestable: 'text-ink-tertiary',
}

// ---------------------------------------------------------------------------
// (state, urgency) → action text
// ---------------------------------------------------------------------------

type UrgencyScore = StockState['urgency_score']

const ACTION_TABLE: Partial<Record<StockState['state'], Partial<Record<UrgencyScore, string>>>> = {
  stage_2a: {
    urgent: 'Act today — fresh breakout window open',
    normal: 'Confirmed entry candidate',
    late:   'Fresh window expiring; pass if not in by tomorrow',
  },
  stage_2b: {
    normal: 'Hold; trail stop below SMA-50',
    late:   'Approaching mature phase; tighten stop',
  },
  stage_2c: {
    normal: 'Mature trend — tighten stop, no add-ons',
    late:   'Extension risk rising; consider trim',
    urgent: 'Beyond cohort norms; trim',
  },
  stage_3: {
    normal: 'Topping — watch for breakdown',
    urgent: 'Distribution prolonged — exit',
  },
  stage_4: {
    'n/a': 'Avoid; exit if held',
  },
  stage_1: {
    'n/a': 'Watch — base forming',
  },
  uninvestable: {
    'n/a': 'Excluded: liquidity, data quality, or price filter',
  },
}

function getActionText(state: StockState['state'], urgency: UrgencyScore): string {
  return ACTION_TABLE[state]?.[urgency] ?? ''
}

// ---------------------------------------------------------------------------
// Urgency icon
// ---------------------------------------------------------------------------

function UrgencyIcon({ urgency }: { urgency: UrgencyScore }) {
  if (urgency === 'urgent') {
    return <AlertTriangle className="w-3.5 h-3.5 text-signal-warn inline mr-1" aria-hidden="true" />
  }
  if (urgency === 'late') {
    return <Clock className="w-3.5 h-3.5 text-signal-warn inline mr-1" aria-hidden="true" />
  }
  return null
}

// ---------------------------------------------------------------------------
// Urgency label text
// ---------------------------------------------------------------------------

const URGENCY_LABEL: Record<UrgencyScore, string> = {
  urgent: 'URGENT',
  late:   'LATE',
  normal: '',
  'n/a':  '',
}

// ---------------------------------------------------------------------------
// Freshness calculation
// ---------------------------------------------------------------------------

function computeFreshness(dwellDays: number, p75: number | null): string {
  if (p75 == null || p75 === 0) return 'n/a'
  const raw = 1 - dwellDays / p75
  const clamped = Math.max(0, Math.min(1, raw))
  return clamped.toFixed(2)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MasterStateCard({
  symbol,
  state,
  cohortBaseline,
  peerRank,
  peerTotal,
}: MasterStateCardProps) {
  const label     = STATE_LABEL[state.state]
  const color     = STATE_COLOR[state.state]
  const action    = getActionText(state.state, state.urgency_score)
  const urgency   = state.urgency_score

  // Dwell line — plain English describing how long this stock has been
  // in its current state vs the typical for its cap-tier cohort.
  // Avoids jargon (no "p75", no "median" exposed as a stat term).
  const dwellLine = ((): string => {
    if (cohortBaseline == null) {
      return `In ${label.toLowerCase()} for ${state.dwell_days} day${state.dwell_days === 1 ? '' : 's'}`
    }
    const tier = cohortBaseline.cohort_key.split('_')[0]  // "large" / "mid" / "small"
    const typical = cohortBaseline.median_dwell_days
    const long = cohortBaseline.p75_dwell_days
    if (typical == null) {
      return `In ${label.toLowerCase()} for ${state.dwell_days} day${state.dwell_days === 1 ? '' : 's'}`
    }
    // How does this stock compare to the typical?
    const ratio = state.dwell_days / typical
    let comparison = ''
    if (ratio >= 4) {
      comparison = ` · ${Math.round(ratio)}× longer than typical ${tier}-cap (~${typical} days)`
    } else if (ratio >= 1.5) {
      comparison = ` · longer than typical ${tier}-cap (~${typical} days)`
    } else if (ratio <= 0.5) {
      comparison = ` · still early (typical ${tier}-cap: ~${typical} days)`
    } else {
      comparison = ` · near typical ${tier}-cap (~${typical} days)`
    }
    const longRow = long != null && state.dwell_days > long
      ? ` · past 75th percentile (~${long} days)`
      : ''
    return `In ${label.toLowerCase()} for ${state.dwell_days} day${state.dwell_days === 1 ? '' : 's'}${comparison}${longRow}`
  })()

  // within_state_rank breakdown
  const wsr           = state.within_state_rank
  const freshness     = computeFreshness(state.dwell_days, cohortBaseline?.p75_dwell_days ?? null)
  const rsDisplay     = state.rs_rank_12m != null ? state.rs_rank_12m.toFixed(2) : 'n/a'
  const wsrDisplay    = wsr != null ? wsr.toFixed(2) : '—'

  // Peer rank
  const peerLine = peerRank != null
    ? `Ranked #${peerRank} of ${peerTotal} today`
    : `${peerTotal} peers in this state today`

  return (
    <div
      className="sticky top-14 z-30 bg-paper border-b border-paper-rule py-4 px-6"
      data-testid="master-state-card"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        {/* Left: symbol — visually-hidden on this row since the symbol is
            already shown in the breadcrumb + headline of StockDeepDiveHeader
            directly above. Kept in the DOM for accessibility tooling that
            may anchor to it. */}
        <div className="sr-only">
          <div className="font-serif text-xl font-semibold text-ink-primary tracking-tight leading-none">
            {symbol}
          </div>
        </div>

        {/* Right: state + dwell + urgency + rank */}
        <div className="flex flex-col gap-1.5 sm:items-end">
          {/* Master state label */}
          <div
            className={`font-sans text-sm font-semibold tracking-[0.22em] ${color} flex items-center`}
            data-testid="state-label"
          >
            {label}
            <InfoTooltip content={metric('engine_state')?.definition ?? 'IC-validated Weinstein stage classification.'} />
          </div>

          {/* Dwell line */}
          <div className="font-sans text-xs text-ink-secondary">
            {dwellLine}
          </div>

          {/* Urgency + action */}
          {(urgency === 'urgent' || urgency === 'late') && (
            <div className="font-sans text-xs text-signal-warn">
              <UrgencyIcon urgency={urgency} />
              {URGENCY_LABEL[urgency]}
              {action ? ` — ${action}` : ''}
            </div>
          )}
          {urgency === 'normal' && action && (
            <div className="font-sans text-xs text-ink-secondary">
              {action}
            </div>
          )}
          {urgency === 'n/a' && action && (
            <div className="font-sans text-xs text-ink-secondary">
              {action}
            </div>
          )}

          {/* Peer rank — linked to on-page peers table */}
          <div className="font-sans text-xs text-ink-tertiary">
            <a
              href="#within-state-peers"
              className="hover:text-ink-secondary hover:underline transition-colors"
            >
              {peerLine}
            </a>
            {wsr != null && (
              <span className="ml-1">
                · within-state rank <span className="font-mono">{wsrDisplay}</span>
              </span>
            )}
          </div>

          {/* within_state_rank breakdown */}
          {wsr != null && (
            <div
              className="font-mono text-[11px] text-ink-tertiary"
              title="freshness = 1 − (dwell / p75), clamped [0,1]. Realized-vol rank requires cross-sectional context — Phase 5b adds it."
            >
              freshness {freshness} · rs {rsDisplay} · vol n/a
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
