import { RSStateChip } from '@/lib/stock-formatters'

// Strip " NAV" suffix from nav_state for display in RSStateChip.
// "Leader NAV" → "Leader" (which RSStateChip knows how to render)
// DISLOCATION_SUSPENDED is passed through as-is — rendered separately as grey chip.
export function navStateChipValue(navState: string | null): string | null {
  if (!navState || navState === 'DISLOCATION_SUSPENDED') return navState
  return navState.replace(/ NAV$/, '')
}

// Fund-specific search — searches scheme_name + amc (not symbol + companyName)
export function matchesFundSearch(
  row: { scheme_name: string; amc: string },
  query: string,
): boolean {
  if (!query.trim()) return true
  const q = query.trim().toLowerCase()
  return row.scheme_name.toLowerCase().includes(q) || row.amc.toLowerCase().includes(q)
}

// Cap weeks_in_current_state at "52+" when > 260 (data artifact: nightly job anomaly producing ~963 weeks)
// Shows days for <2w, weeks for 2w–12w, months for >12w.
export function formatWeeksInState(days: string | null): string {
  if (!days) return '—'
  const n = parseInt(days, 10)
  if (isNaN(n) || n < 1) return '—'
  if (n < 10) return `${n}d`
  const weeks = Math.round(n / 5)
  if (weeks < 13) return `${weeks}w`
  const months = Math.round(n / 21)
  return `${months}mo`
}

// ── Composition state chip ─────────────────────────────────────────────────

const COMPOSITION_STATE_STYLE: Record<string, string> = {
  Aligned:               'bg-signal-pos/20 text-signal-pos',
  Mixed:                 'bg-signal-warn/15 text-signal-warn',
  Misaligned:            'bg-signal-neg/15 text-signal-neg',
  NO_DISCLOSURE:         'bg-ink-tertiary/10 text-ink-tertiary',
  DISLOCATION_SUSPENDED: 'bg-ink-tertiary/10 text-ink-tertiary',
}

const COMPOSITION_STATE_LABEL: Record<string, string> = {
  Aligned:               'Aligned',
  Mixed:                 'Mixed',
  Misaligned:            'Misalign',
  NO_DISCLOSURE:         'N/A',
  DISLOCATION_SUSPENDED: 'Susp',
}

// ── Holdings state chip ────────────────────────────────────────────────────

const HOLDINGS_STATE_STYLE: Record<string, string> = {
  'Strong-Holdings':     'bg-signal-pos/20 text-signal-pos',
  'Mixed-Holdings':      'bg-signal-warn/15 text-signal-warn',
  'Weak-Holdings':       'bg-signal-neg/15 text-signal-neg',
  NO_DISCLOSURE:         'bg-ink-tertiary/10 text-ink-tertiary',
  DISLOCATION_SUSPENDED: 'bg-ink-tertiary/10 text-ink-tertiary',
}

const HOLDINGS_STATE_LABEL: Record<string, string> = {
  'Strong-Holdings':     'Strong',
  'Mixed-Holdings':      'Mixed',
  'Weak-Holdings':       'Weak',
  NO_DISCLOSURE:         'N/A',
  DISLOCATION_SUSPENDED: 'Susp',
}

// ── Recommendation chip ────────────────────────────────────────────────────

const RECOMMENDATION_STYLE: Record<string, string> = {
  Recommended: 'bg-signal-pos/20 text-signal-pos',
  Hold:        'bg-ink-tertiary/10 text-ink-secondary',
  Reduce:      'bg-signal-warn/15 text-signal-warn',
  Exit:        'bg-signal-neg/20 text-signal-neg',
}

const RECOMMENDATION_LABEL: Record<string, string> = {
  Recommended: 'Rec',
  Hold:        'Hold',
  Reduce:      'Reduce',
  Exit:        'Exit',
}

// ── Shared StateTag (internal — same pattern as stock-formatters.tsx) ──────

function StateTag({ raw, label, style }: { raw: string | null; label: string; style: string }) {
  if (!raw) return <span className="font-mono text-[10px] text-ink-tertiary">—</span>
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${style}`}
      title={raw}
    >
      {label}
    </span>
  )
}

export function CompositionStateChip({ value }: { value: string | null }) {
  const style = value ? (COMPOSITION_STATE_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (COMPOSITION_STATE_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

export function HoldingsStateChip({ value }: { value: string | null }) {
  const style = value ? (HOLDINGS_STATE_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (HOLDINGS_STATE_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

export function RecommendationChip({ value }: { value: string | null }) {
  const style = value ? (RECOMMENDATION_STYLE[value] ?? 'bg-ink-tertiary/10 text-ink-secondary') : ''
  const label = value ? (RECOMMENDATION_LABEL[value] ?? value) : ''
  return <StateTag raw={value} label={label} style={style} />
}

// Renders the NAV state using RSStateChip after stripping " NAV" suffix.
// For DISLOCATION_SUSPENDED, renders a grey "Susp" chip directly.
export function NavStateChip({ value }: { value: string | null }) {
  if (!value) return <span className="font-mono text-[10px] text-ink-tertiary">—</span>
  if (value === 'DISLOCATION_SUSPENDED') {
    return (
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold bg-ink-tertiary/10 text-ink-tertiary"
        title="Market dislocation — recommendation suspended"
      >
        Susp
      </span>
    )
  }
  return <RSStateChip value={navStateChipValue(value)} />
}
