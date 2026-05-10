import Link from 'next/link'
import { NavStateChip, RecommendationChip, formatWeeksInState } from '@/lib/fund-formatters'
import type { FundMasterRow } from '@/lib/queries/funds'

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).replace(',', '')
}

type TriggerBadgeProps = { label: string; active: boolean | null; tone: 'pos' | 'neg' | 'warn' }
function TriggerBadge({ label, active, tone }: TriggerBadgeProps) {
  if (!active) return null
  const colors = {
    pos:  'bg-signal-pos/15 text-signal-pos',
    neg:  'bg-signal-neg/15 text-signal-neg',
    warn: 'bg-signal-warn/15 text-signal-warn',
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${colors[tone]}`}>
      {label}
    </span>
  )
}

export function FundDeepDiveHeader({ master }: { master: FundMasterRow }) {
  const hasTrigger = master.entry_trigger || master.exit_trigger || master.reduce_trigger || master.add_trigger

  return (
    <div className="px-6 py-4 border-b border-paper-rule">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="mb-2">
        <Link href="/funds" className="font-sans text-xs text-teal hover:underline">
          ← Funds
        </Link>
      </nav>
      {/* Fund title row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-sans text-base font-semibold text-ink-primary leading-snug">
            {master.scheme_name}
          </h1>
          <div className="font-sans text-xs text-ink-tertiary mt-0.5">
            {master.amc} · {master.category_name}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <RecommendationChip value={master.recommendation} />
        </div>
      </div>
      {/* NAV state row */}
      <div className="flex items-center gap-2 mt-2">
        <NavStateChip value={master.nav_state} />
        <span className="font-mono text-[10px] text-ink-tertiary">
          {formatWeeksInState(master.weeks_in_current_state)} in current state
        </span>
        {master.data_as_of && (
          <span className="ml-auto font-sans text-[10px] text-ink-tertiary/60">
            Data as of {formatDate(master.data_as_of)}
          </span>
        )}
      </div>
      {/* Trigger indicators — only shown when at least one is active */}
      {hasTrigger && (
        <div className="flex items-center gap-1.5 mt-2">
          <span className="font-sans text-[10px] text-ink-tertiary mr-0.5">Triggers:</span>
          <TriggerBadge label="Entry" active={master.entry_trigger} tone="pos" />
          <TriggerBadge label="Add" active={master.add_trigger} tone="pos" />
          <TriggerBadge label="Reduce" active={master.reduce_trigger} tone="warn" />
          <TriggerBadge label="Exit" active={master.exit_trigger} tone="neg" />
        </div>
      )}
    </div>
  )
}
