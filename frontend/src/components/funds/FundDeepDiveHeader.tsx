import Link from 'next/link'
import { NavStateChip, RecommendationChip, formatWeeksInState } from '@/lib/fund-formatters'
import type { FundMasterRow } from '@/lib/queries/funds'

export function FundDeepDiveHeader({ master }: { master: FundMasterRow }) {
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
      </div>
    </div>
  )
}
