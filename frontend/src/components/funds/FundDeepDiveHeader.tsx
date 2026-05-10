import React from 'react'
import Link from 'next/link'
import {
  NavStateChip, CompositionStateChip, HoldingsStateChip,
  RecommendationChip, formatWeeksInState,
} from '@/lib/fund-formatters'
import type { FundMasterRow } from '@/lib/queries/funds'

function formatDate(d: Date | string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).replace(',', '')
}

function StateRow({ label, chip, asOf }: { label: string; chip: React.ReactNode; asOf: Date | null }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-sans text-[9px] text-ink-tertiary/60 uppercase tracking-wider w-20 shrink-0">{label}</span>
      {chip}
      {asOf && (
        <span className="font-sans text-[9px] text-ink-tertiary/70">as of {formatDate(asOf)}</span>
      )}
    </div>
  )
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
            {master.inception_date && (
              <span className="ml-2 text-ink-tertiary/60">
                · Since {formatDate(master.inception_date)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <RecommendationChip value={master.recommendation} />
        </div>
      </div>

      {/* State rows — NAV / Composition / Holdings each with as_of date */}
      <div className="flex flex-col gap-1 mt-3">
        <StateRow
          label="NAV State"
          chip={<NavStateChip value={master.nav_state} />}
          asOf={master.nav_state_as_of}
        />
        <StateRow
          label="Composition"
          chip={<CompositionStateChip value={master.composition_state} />}
          asOf={master.composition_as_of}
        />
        <StateRow
          label="Holdings"
          chip={<HoldingsStateChip value={master.holdings_state} />}
          asOf={master.holdings_as_of}
        />
      </div>

      {/* Weeks in state + data freshness */}
      <div className="flex items-center gap-2 mt-2">
        <span className="font-mono text-[10px] text-ink-tertiary">
          {formatWeeksInState(master.weeks_in_current_state)} in current state
        </span>
        {master.data_as_of && (
          <span className="ml-auto font-sans text-[10px] text-ink-tertiary/60">
            Metrics as of {formatDate(master.data_as_of)}
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
